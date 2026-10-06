// Fase 3 — quase tempo real (Cron Trigger a cada 5 min).
// Lê a "vigia" publicada pelas Actions, consulta os midpoints da Polymarket, aplica o filtro rápido
// de sinal (z-score no log-odds + persistência), monta o plano com preços do Yahoo e acompanha
// alvo/stop/prazo/invalidação dos sinais abertos. Tudo vira evento em KV "rt" para o diário.
// Funções puras recebem os "buscadores" por parâmetro: os testes rodam sem rede.

const MIN = 60 * 1000;

export function logit(p) {
  const q = Math.min(Math.max(p, 0.005), 0.995);
  return Math.log(q / (1 - q));
}

// ---------- formatação pt-BR ----------
const MENOS = "−";
function num(v, casas = 2, sinal = false) {
  const t = Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  if (v < 0 && Number(t.replace(/\./g, "").replace(",", ".")) !== 0) return MENOS + t;
  return (sinal && v > 0 ? "+" : "") + t;
}
const pct = (f, casas = 1, sinal = false) => num(f * 100, casas, sinal) + "%";
const pp = (d) => num(d * 100, 1, true) + " p.p.";
function prob(p) {
  if (p == null) return "—";
  if (p < 0.01) return "<1%";
  if (p > 0.99) return ">99%";
  return `${Math.round(p * 100)}%`;
}
const dinheiro = (v, moeda) => `${v < 0 ? MENOS : ""}${moeda === "BRL" ? "R$" : "US$"} ${num(Math.abs(v), 2)}`;
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const curto = (t, n) => (t.length <= n ? t : t.slice(0, n - 1).trimEnd() + "…");
const nomeAtivo = (t) => t.replace(/\.SA$/, "");
const seta = (s) => (s > 0 ? "🔺 LONG" : "🔻 SHORT");
const NOMES_IND = { "BZ=F": "Brent", "DX-Y.NYB": "DXY", "^VIX": "VIX", "BRL=X": "Dólar" };

function partesLocais(agora, fuso) {
  const p = new Intl.DateTimeFormat("en-US", {
    timeZone: fuso, hour12: false, weekday: "short", hour: "2-digit", minute: "2-digit",
  }).formatToParts(agora);
  const get = (t) => p.find((x) => x.type === t)?.value;
  return { dia: get("weekday"), h: Number(get("hour")) % 24, m: Number(get("minute")) };
}

export function hora(agora) {
  const { h, m } = partesLocais(agora, "America/Sao_Paulo");
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function pregaoAberto(pregoes, bolsa, agora) {
  const p = pregoes?.[bolsa] || pregoes?.EUA || { fuso: "America/New_York", abre: "09:30", fecha: "16:00" };
  const { dia, h, m } = partesLocais(agora, p.fuso);
  if (bolsa !== "CRIPTO" && (dia === "Sat" || dia === "Sun")) return false;
  const [ah, am] = p.abre.split(":").map(Number);
  const [fh, fm] = p.fecha.split(":").map(Number);
  const agoraMin = h * 60 + m;
  return agoraMin >= ah * 60 + am && agoraMin < fh * 60 + fm;
}

function fimDoPregao(pregoes, bolsa, agora) {
  const p = pregoes?.[bolsa] || pregoes?.EUA;
  const { h, m } = partesLocais(agora, p.fuso);
  const [fh, fm] = p.fecha.split(":").map(Number);
  return new Date(agora.getTime() + ((fh * 60 + fm) - (h * 60 + m)) * MIN);
}

export function emSilencio(silencio, agora) {
  if (!silencio || silencio.ligado === false) return false;
  const { h, m } = partesLocais(agora, "America/Sao_Paulo");
  const t = h * 60 + m;
  const [ih, im] = (silencio.inicio || "22:00").split(":").map(Number);
  const [fh, fm] = (silencio.fim || "07:00").split(":").map(Number);
  const i = ih * 60 + im, f = fh * 60 + fm;
  return i <= f ? t >= i && t < f : t >= i || t < f;
}

// ---------- semáforo ----------
export function semaforo(variacoes, esperados, sentidoProb, limiarPct) {
  let aFavor = 0, contra = 0;
  const partes = [];
  for (const [t, esp] of Object.entries(esperados)) {
    const v = variacoes[t];
    if (v == null) continue;
    partes.push(`${NOMES_IND[t] || nomeAtivo(t)} ${pct(v, 1, true)}`);
    if (Math.abs(v) * 100 < limiarPct || !esp) continue;
    if ((v > 0) === (esp * sentidoProb > 0)) aFavor++;
    else contra++;
  }
  const cor = contra && contra >= aFavor ? "🔴" : aFavor >= 2 && !contra ? "🟢" : "🟡";
  return { cor, detalhe: partes.length ? partes.join(" | ") : "sem dados dos indicadores" };
}
const rebaixar = (c) => ({ "🟢": "🟡", "🟡": "🔴" })[c] || c;

// ---------- preços (Yahoo v8 chart) ----------
export function lerChart(json) {
  const r = json?.chart?.result?.[0];
  if (!r) return null;
  const ts = r.timestamp || [];
  const fech = r.indicators?.quote?.[0]?.close || [];
  const serie = [];
  for (let i = 0; i < ts.length; i++) if (fech[i] != null) serie.push([ts[i] * 1000, fech[i]]);
  const preco = r.meta?.regularMarketPrice ?? serie.at(-1)?.[1];
  return preco ? { preco, serie, anterior: r.meta?.chartPreviousClose ?? null } : null;
}

export function precoEm(dados, t) {
  if (!dados) return null;
  let ultimo = null;
  for (const [ts, v] of dados.serie) {
    if (ts > t) break;
    ultimo = v;
  }
  return ultimo ?? dados.anterior;
}

// ---------- detecção ----------
export function detectar(m, leituras, agora, regras) {
  if (leituras.length < 3) return null;
  const [tAgora, pAgora] = leituras.at(-1);
  const pAnterior = leituras.at(-2)[1];
  for (const L of regras.janelas_min || [15, 30, 60]) {
    const alvoT = tAgora - L * MIN;
    const base = [...leituras].reverse().find(([t]) => t <= alvoT + 2 * MIN);
    if (!base || base === leituras.at(-2) || tAgora - base[0] > (L + 10) * MIN) continue;
    const [tBase, pBase] = base;
    const dp = pAgora - pBase;
    if (Math.abs(dp) * 100 < regras.prefiltro_pp) continue;
    const sigma = m.sigma_h * Math.sqrt(Math.max(tAgora - tBase, 5 * MIN) / (60 * MIN));
    const z = (logit(pAgora) - logit(pBase)) / sigma;
    const zAnterior = (logit(pAnterior) - logit(pBase)) / sigma;
    let zMin = regras.zscore_min;
    const notas = [];
    const fim = m.fim ? Date.parse(m.fim) : null;
    if (fim && fim - agora.getTime() < regras.prazo_curto_dias * 1440 * MIN && dp < 0) {
      zMin *= regras.prazo_curto_fator_z;
      notas.push("prazo curto: queda natural descontada");
    }
    // persistência: a leitura anterior já mostrava o movimento e a atual mantém ≥ X% dele
    const persistiu =
      Math.sign(zAnterior) === Math.sign(z) &&
      Math.abs(zAnterior) >= zMin * regras.retencao_min &&
      Math.abs(z) >= regras.retencao_min * Math.abs(zAnterior);
    if (Math.abs(z) >= zMin && persistiu) {
      // latência: do primeiro instante em que fez metade do movimento até agora
      const meio = leituras.find(([t, p]) => t > tBase && Math.abs(p - pBase) >= Math.abs(dp) / 2);
      return { tBase, pBase, pAgora, dp, z, janela: L, notas, latencia_s: (tAgora - (meio?.[0] ?? tAgora)) / 1000 + 150 };
    }
  }
  return null;
}

// ---------- montagem do sinal ----------
export async function montarSinal(m, c, agora, vigia, buscarPreco) {
  const r = vigia.regras;
  const sentidoProb = c.dp > 0 ? 1 : -1;
  let ativo, sentido, esperado = null, beta = null, defasagem = null, alt = null, atr = null, bolsa = "EUA";
  if (m.par) {
    ({ ativo, beta_10pp: beta, defasagem_min: defasagem, atr, bolsa } = m.par);
    esperado = (beta / 100) * (c.dp / 0.1);
    sentido = esperado > 0 ? 1 : -1;
    if (m.par.alt) alt = { ativo: m.par.alt.ativo, sentido: m.par.alt.beta_10pp * c.dp > 0 ? 1 : -1 };
  } else if (m.hipotese) {
    ativo = m.hipotese.ativo;
    sentido = m.hipotese.sentido * sentidoProb;
  } else return null;

  const esperados = { ...(m.semaforo || {}) };
  if (esperado != null) esperados[ativo] = beta > 0 ? 1 : -1;
  const tickers = [...new Set([ativo, ...Object.keys(esperados)])];
  const dados = Object.fromEntries(await Promise.all(tickers.map(async (t) => [t, await buscarPreco(t)])));
  const variacoes = {};
  for (const t of Object.keys(esperados)) {
    const a = precoEm(dados[t], c.tBase), b = dados[t]?.preco;
    variacoes[t] = a && b ? b / a - 1 : null;
  }
  const sem = semaforo(variacoes, esperados, sentidoProb, r.limiar_semaforo_pct);
  let confianca = sem.cor;
  if (c.pAgora < r.zona.abaixo || c.pAgora > r.zona.acima) {
    confianca = rebaixar(confianca);
    c.notas.push("zona distorcida (viés favorito–azarão)");
  }
  if (!m.par) confianca = rebaixar(confianca);

  const entrada = dados[ativo]?.preco ?? null;
  const pBaseAtivo = precoEm(dados[ativo], c.tBase);
  const realizado = entrada && pBaseAtivo ? entrada / pBaseAtivo - 1 : null;
  const espaco = esperado != null ? esperado - (realizado ?? 0) : null;
  const aberto = pregaoAberto(vigia.pregoes, bolsa, agora);
  const moeda = vigia.pregoes?.[bolsa]?.moeda || "USD";

  let plano = null;
  if (entrada && atr) {
    const stop = entrada - sentido * r.atr_mult * atr;
    const riscoUnit = Math.abs(entrada - stop);
    const alvo = espaco != null ? entrada * (1 + espaco) : null;
    const parcial = espaco != null ? entrada * (1 + espaco / 2) : null;
    const gr = alvo != null ? Math.abs(alvo - entrada) / riscoUnit : null;
    let quantidade = null;
    if (vigia.capital_brl) {
      const capital = moeda === "BRL" ? vigia.capital_brl : vigia.cambio_brl ? vigia.capital_brl / vigia.cambio_brl : null;
      if (capital) quantidade = Math.min(Math.floor((capital * r.risco_pct) / 100 / riscoUnit), Math.floor(capital / entrada));
    }
    let stopTempo = aberto ? fimDoPregao(vigia.pregoes, bolsa, agora) : null;
    if (defasagem > 0) {
      const t = new Date(agora.getTime() + r.stop_tempo_mult * defasagem * MIN);
      stopTempo = stopTempo && stopTempo < t ? stopTempo : t;
    }
    plano = { entrada, stop, alvo, parcial, gr, quantidade, stopTempo };
  }

  const motivos = [];
  if (!m.par) motivos.push("par ainda não calibrado");
  else {
    if (defasagem <= 0) motivos.push("o ativo anda junto ou antes da Polymarket");
    else if (defasagem * 60 <= r.latencia_multiplo * c.latencia_s)
      motivos.push(`defasagem (${num(defasagem, 0)} min) curta para a latência (${num(c.latencia_s / 60, 0)} min)`);
    if (espaco == null || espaco * esperado <= 0 || Math.abs(espaco) < (Math.abs(esperado) * r.espaco_min_pct) / 100)
      motivos.push("o ativo já andou o esperado");
  }
  if (!entrada) motivos.push("sem preço em tempo real do ativo");
  if (!aberto) motivos.push("pregão fechado: gap esperado na abertura");
  if (!plano) motivos.push("sem ATR para o stop");
  else if (plano.gr != null && plano.gr < r.ganho_risco_min) motivos.push(`ganho/risco ${num(plano.gr, 1)} abaixo do mínimo`);
  if (r.pausado_ate && Date.parse(r.pausado_ate) > agora.getTime()) motivos.push("trava ativa após perdas seguidas");
  if (m.manip === "🔴") motivos.push("risco de manipulação 🔴");
  const acionavel = motivos.length === 0;
  const urgencia = acionavel ? (sem.cor === "🟢" ? "🚨" : "🔔") : "📋";

  const topo = urgencia === "🚨" ? "🚨 SINAL" : acionavel ? "🔔 SINAL" : "📋 Informativo";
  const minutos = Math.max((agora.getTime() - c.tBase) / MIN, 1);
  const linhas = [
    `${topo} — ${m.emoji} ${esc(m.nome_tema)} ⚡`,
    esc(curto(m.pergunta, 70)),
    `${prob(c.pBase)} → ${prob(c.pAgora)} (${pp(c.dp)}, z = ${num(c.z, 1)}) em ${num(minutos, 0)} min`,
    `Semáforo: ${sem.cor} ${sem.detalhe}`,
    `${seta(sentido)} ${nomeAtivo(ativo)}${alt ? ` (alt.: ${seta(alt.sentido)} ${nomeAtivo(alt.ativo)})` : ""}`,
  ];
  if (plano) {
    let l1 = `Entrada ~${dinheiro(plano.entrada, moeda)}`;
    if (plano.alvo != null) l1 += ` | 🎯 Alvo: ${dinheiro(plano.alvo, moeda)} (parcial ${dinheiro(plano.parcial, moeda)})`;
    linhas.push(l1);
    let l2 = `🛑 Stop: ${dinheiro(plano.stop, moeda)}`;
    if (plano.gr != null) l2 += ` | Ganho/risco: ${num(plano.gr, 1)}`;
    if (plano.stopTempo) l2 += ` | ⏱️ Sair até ${hora(plano.stopTempo)}`;
    linhas.push(l2);
  }
  if (esperado != null) {
    linhas.push(`Esperado ${pct(esperado, 1, true)} | realizado ${pct(realizado ?? 0, 1, true)} → espaço de ${pct(espaco, 1, true)}`);
  }
  let tam = `Tamanho máx.: ${num(r.risco_pct, 1)}% do capital`;
  if (plano?.quantidade != null) tam += ` → ${plano.quantidade} un. (≈ ${dinheiro(plano.quantidade * plano.entrada, moeda)})`;
  else if (!vigia.capital_brl) tam += " (defina com /capital)";
  linhas.push(`${tam} | Latência do alerta: ${num(c.latencia_s / 60, 0)} min`);
  linhas.push(`Confiança: ${confianca} | 🕵️ Manipulação: ${m.manip || "—"}`);
  for (const n of c.notas) linhas.push(`ℹ️ ${n}`);
  if (motivos.length) linhas.push("Por que não é acionável: " + motivos.join("; "));
  linhas.push("⚠️ Sinal de sistema, não recomendação. Registrado no diário.");

  const linhaCurta = `${m.emoji} ${esc(curto(m.pergunta, 45))}: ${pp(c.dp)} (z ${num(c.z, 1)}) → ${seta(sentido)} ${nomeAtivo(ativo)} ${sem.cor} (informativo ⚡)`;
  return {
    acionavel, urgencia, texto: linhas.join("\n"), linha: linhaCurta,
    sinal: {
      ts: agora.toISOString(), tema: m.tema, ativo, sentido, entrada: entrada ?? pBaseAtivo ?? 0, mercado_id: m.id,
      stop: plano?.stop ?? null, alvo: plano?.alvo ?? null, parcial: plano?.parcial ?? null,
      stop_tempo: plano?.stopTempo?.toISOString() ?? null, semaforo: sem.cor, manipulacao: m.manip,
      urgencia, acionavel, latencia_s: c.latencia_s, confianca, base_ts: new Date(c.tBase).toISOString(),
      p_base: c.pBase, p_sinal: c.pAgora, z: c.z, esperado, realizado, defasagem_min: defasagem, beta_10pp: beta,
      quantidade: plano?.quantidade ?? null,
      detalhes: { motivos, notas: c.notas, semaforo: sem.detalhe, pergunta: m.pergunta, janela_min: c.janela },
    },
  };
}

// ---------- acompanhamento ----------
export function acompanhar(s, preco, pAtual, agora, r) {
  const resultado = s.sentido * (preco / s.entrada - 1) - r.custo_pct / 100;
  const cab = `${nomeAtivo(s.ativo)} (${s.sentido > 0 ? "🔺 long" : "🔻 short"} de ${num(s.entrada)}) agora ${num(preco)}`;
  const res = `Resultado simulado: ${pct(resultado, 2, true)}`;
  if (pAtual != null && s.p_base != null && s.p_sinal != null) {
    const mov = s.p_sinal - s.p_base;
    if (mov && (pAtual - s.p_base) / mov < 1 - r.devolucao)
      return { status: "invalidado", resultado, urgencia: "🚨", texto: `❌ Sinal invalidado — sair\n${cab}\nA probabilidade devolveu mais da metade do movimento\n${res}` };
  }
  if (s.stop != null && s.sentido * (preco - s.stop) <= 0)
    return { status: "stop", resultado, urgencia: "🚨", texto: `🛑 Stop atingido\n${cab}\n${res}` };
  if (s.alvo != null && s.sentido * (preco - s.alvo) >= 0)
    return { status: "alvo", resultado, urgencia: "🔔", texto: `🎯 Alvo final atingido\n${cab}\n${res}` };
  if (s.stop_tempo && agora.getTime() >= Date.parse(s.stop_tempo))
    return { status: "tempo", resultado, urgencia: "🔔", texto: `⏱️ Prazo do sinal acabou — sair\n${cab}\n${res}` };
  if (s.parcial != null && !(s.avisos || []).includes("parcial") && s.sentido * (preco - s.parcial) >= 0)
    return { status: "parcial", resultado, urgencia: "🔔", texto: `🎯 Alvo parcial atingido\n${cab}\n${res}` };
  return null;
}

// ---------- ciclo ----------
export async function ciclo({ vigia, rt, ack, agora, buscarMids, buscarPreco, enviar }) {
  const r = vigia.regras;
  const estado = {
    v: 1, seq: rt?.seq || 0, leituras: rt?.leituras || {}, ultimo_sinal: rt?.ultimo_sinal || {},
    abertos_rt: rt?.abertos_rt || [], fechados: rt?.fechados || [], parciais: rt?.parciais || [],
    eventos: (rt?.eventos || []).filter((e) => e.seq > (ack || 0)).slice(-200),
  };
  const evento = (e) => estado.eventos.push({ seq: ++estado.seq, ...e });
  const silencio = emSilencio(r.silencio, agora);
  const avisar = async (texto, urgencia) => {
    if (urgencia === "🚨" || !silencio) await enviar(texto, false);
    else evento({ tipo: "segurada", texto });
  };

  const abertos = [
    ...(vigia.abertos || []).map((s) => ({ ...s, chave: `db-${s.id}` })),
    ...estado.abertos_rt.map((s) => ({ ...s, chave: s.ref })),
  ].filter((s) => !estado.fechados.includes(s.chave));
  const tokens = [...new Set([...vigia.mercados.map((m) => m.token), ...abertos.map((s) => s.token).filter(Boolean)])];
  const mids = await buscarMids(tokens);
  const t = agora.getTime();

  // 1) acompanhamento dos abertos
  const cachePreco = {};
  const precoDe = async (tk) => (tk in cachePreco ? cachePreco[tk] : (cachePreco[tk] = await buscarPreco(tk)));
  for (const s of abertos) {
    const dados = await precoDe(s.ativo);
    if (!dados?.preco) continue;
    const ev = acompanhar({ ...s, avisos: [...(s.avisos || []), ...(estado.parciais.includes(s.chave) ? ["parcial"] : [])] },
      dados.preco, s.token ? mids[s.token] : null, agora, r);
    if (!ev) continue;
    const ref = s.chave.startsWith("db-") ? { sinal_id: s.id } : { ref: s.chave };
    if (ev.status === "parcial") {
      estado.parciais.push(s.chave);
      evento({ tipo: "parcial", ...ref });
    } else {
      estado.fechados.push(s.chave);
      evento({ tipo: "fechamento", ...ref, status: ev.status, resultado: ev.resultado, ts: agora.toISOString() });
    }
    await avisar(ev.texto + " ⚡", ev.urgencia);
  }
  estado.abertos_rt = estado.abertos_rt.filter((s) => !estado.fechados.includes(s.ref));
  estado.fechados = estado.fechados.slice(-200);
  estado.parciais = estado.parciais.slice(-200);

  // 2) leituras e detecção
  for (const m of vigia.mercados) {
    const p = mids[m.token];
    if (p == null) continue;
    const ls = (estado.leituras[m.id] || []).filter(([ts]) => ts >= t - 75 * MIN);
    ls.push([t, p]);
    estado.leituras[m.id] = ls;
    if (estado.ultimo_sinal[m.id] && t - estado.ultimo_sinal[m.id] < 6 * 60 * MIN) continue;
    const c = detectar(m, ls, agora, r);
    if (!c) continue;
    const s = await montarSinal(m, c, agora, vigia, precoDe);
    if (!s) continue;
    estado.ultimo_sinal[m.id] = t;
    evento({ tipo: "sinal", sinal: s.sinal, linha: s.linha });
    if (s.acionavel) {
      estado.abertos_rt.push({
        ref: `rt-${estado.seq}`, ativo: s.sinal.ativo, sentido: s.sinal.sentido, entrada: s.sinal.entrada,
        stop: s.sinal.stop, alvo: s.sinal.alvo, parcial: s.sinal.parcial, stop_tempo: s.sinal.stop_tempo,
        token: m.token, p_base: s.sinal.p_base, p_sinal: s.sinal.p_sinal, avisos: [],
      });
    }
    if (s.urgencia !== "📋") await avisar(s.texto, s.urgencia);
  }
  // mercados que saíram da vigia não precisam de leituras
  const ids = new Set(vigia.mercados.map((m) => m.id));
  for (const id of Object.keys(estado.leituras)) if (!ids.has(id)) delete estado.leituras[id];
  for (const [id, ts] of Object.entries(estado.ultimo_sinal)) if (t - ts > 12 * 60 * MIN) delete estado.ultimo_sinal[id];
  estado.atualizado_em = agora.toISOString();
  return estado;
}

// ---------- buscadores reais ----------
export function buscadores(env) {
  return {
    async buscarMids(tokens) {
      if (!tokens.length) return {};
      const r = await fetch("https://clob.polymarket.com/midpoints", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(tokens.map((t) => ({ token_id: t }))),
      });
      if (!r.ok) return {};
      const dados = await r.json();
      return Object.fromEntries(Object.entries(dados).map(([k, v]) => [k, Number(v)]).filter(([, v]) => Number.isFinite(v)));
    },
    async buscarPreco(ticker) {
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=5m&range=2d`;
        const r = await fetch(url, { headers: { "user-agent": "Mozilla/5.0 (polymarket-sinais; somente leitura)" } });
        return r.ok ? lerChart(await r.json()) : null;
      } catch {
        return null;
      }
    },
    async enviar(texto, silencioso) {
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: texto, parse_mode: "HTML", disable_web_page_preview: true, disable_notification: silencioso }),
      });
    },
  };
}

export async function rodar(env, agora = new Date()) {
  const [vigia, rt, ack] = await Promise.all([
    env.ESTADO.get("vigia", "json"), env.ESTADO.get("rt", "json"), env.ESTADO.get("rt_ack"),
  ]);
  if (!vigia?.mercados || Date.parse(vigia.gerado_em) < agora.getTime() - 3 * 60 * MIN) return null; // vigia velha: espera as Actions
  const estado = await ciclo({ vigia, rt, ack: Number(ack || 0), agora, ...buscadores(env) });
  await env.ESTADO.put("rt", JSON.stringify(estado));
  return estado;
}

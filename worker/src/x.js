// Módulo 14 — posts para o X (sem API do X: o bot entrega o texto pronto e o botão "Abrir no X").
// Texto escrito pelo Claude (API da Anthropic) a partir da "x_pauta" que as Actions publicam.
// Regras que o CÓDIGO garante (não dependem do modelo):
// - nada de "compre/venda/entre/alvo/stop" em post público (Resolução CVM 20/2021);
// - linha "📌 Minha posição" escrita pelo código, a partir das posições reais;
// - ≤ 280 caracteres por post e no máximo 2 emojis no corpo;
// - ativo de baixa liquidez nunca aparece (anti pump-and-dump, Resolução CVM 62/2022).
import Anthropic from "@anthropic-ai/sdk";

// Recomendação explícita (imperativo / chamada para operar). "venda" e "entre" sozinhos são palavras
// comuns ("venda de petróleo", "entre 40% e 50%"), por isso só entram em expressões de chamada.
export const PROIBIDAS =
  /\b(compre|comprem|compra j[aá]|vendam|venda j[aá]|entre j[aá]|entrem|entrar agora|hora de (comprar|vender|entrar|sair|shortear)|pre[cç]o[- ]alvo|alvo de|stop( loss)?|shorteiem|shorteie)\b/i;
const EMOJI = /\p{Extended_Pictographic}/gu;
const LIMITE = 280;

export const ESTILO = `Você escreve posts para o X do perfil {PERFIL}, série "🔮 Termômetro do Caos", sobre o sentimento do mercado: onde o dinheiro está apostando e o que isso diz sobre a bolsa, os juros, o petróleo, as moedas e o mundo.

QUEM FALA: o dono do perfil, SEMPRE na primeira pessoa do singular. "Eu vejo", "eu não me curvo a essa narrativa", "minha leitura", "eu observei o mercado e...". Nunca "nós", "a gente" ou voz impessoal de jornal.

VOZ: literária, romântica, poderosa e imponente. Um cronista que olha o mercado como quem olha o mar antes da tempestade: imagens fortes, metáforas precisas (maré, trovão, xadrez, fronteira, cerco, aurora, abismo), ritmo de frase trabalhado, alternando uma frase longa e solene com uma curta e cortante. Elegância, nunca vulgaridade. Convicção, nunca arrogância. Português do Brasil culto, mas legível. A metáfora serve ao dado, nunca o esconde: todo parágrafo traz um fato. Zero "talvez" e zero "pode ser que" quando o dado é claro; quando o dado está dividido, eu digo que está dividido, com a mesma firmeza.

SEM PALAVRÃO: nenhum palavrão, xingamento ou gíria vulgar. A força vem da imagem e da precisão.

SEM NOMES DE PLATAFORMA: nunca escreva Polymarket, Kalshi ou o nome de qualquer casa de apostas. Fale do sentimento do mercado: "o mercado", "quem põe dinheiro na mesa", "o dinheiro", "as apostas", "a multidão que aposta", "o termômetro do mercado".

SEM PERGUNTAS: nenhuma frase interrogativa, nenhum "?". Eu afirmo. A pergunta do mercado vira afirmação: "Fed vai cortar os juros?" vira "o mercado dá 31% de chance de corte".

ABERTURA (decide se a pessoa para de rolar a tela). Use as técnicas da lista "ganchos" dos dados, que vêm de pesquisa sobre atenção e compartilhamento:
- Lacuna de curiosidade feita com AFIRMAÇÃO: uma contradição que só o fim do post explica.
- Emoção de alta ativação, com nobreza: assombro, tensão, gravidade. Nunca tristeza nem tédio.
- Uma palavra forte e concreta e um número específico já na primeira linha.
- O "outro lado" é a narrativa, a manchete, o consenso. Nunca pessoas.
Ex.: "Enquanto as manchetes ainda falam em guerra, o dinheiro já assinou a paz: 78%." / "Há dias em que o mercado sussurra. Hoje ele moveu US$ 3 milhões em quarenta minutos, e eu ouvi." / "Eu vi o consenso jurar que o Fed corta. O dinheiro, silencioso, aposta em 31%."

{FORMATO}

ESTUDOS: quando reforçar o argumento, use NO MÁXIMO UM estudo da lista "estudos" dos dados. Escreva a referência exatamente como no campo "curta" (ex.: "Berg et al., 2008") e use só o número do "achado". Nunca cite estudo, pesquisa científica, autor, universidade ou número que não esteja na lista. Preencha o campo "estudo" com o id usado, ou "" se não usou. Não coloque link: o sistema manda a fonte à parte.

QUEM GANHA E QUEM PERDE: os dados trazem "quem_ganha" e "quem_perde" (setores e tickers da bolsa). Explique a ligação com o sentimento do mercado como leitura minha, nunca como ordem.

TERMINE com um veredito claro numa linha: "🟢 mercado bom", "🔴 mercado ruim" ou "⚠️ mercado mentindo" (use este quando houver risco de manipulação ou quando duas casas de aposta divergem), com o motivo em uma frase de peso.

LIMITES INEGOCIÁVEIS (quebrar qualquer um invalida o post):
1. Nenhum ataque a pessoas, grupos ou instituições identificáveis: candidato, político, partido, autoridade, empresa, jornalista, eleitor. A briga é com a narrativa, não com gente.
2. Política (eleição etc.): veredito só sobre o MERCADO (probabilidade, volume, manipulação). Nunca torcida, ataque ou elogio a candidato ou partido.
3. NUNCA escreva "compre", "venda", "entre", "alvo", "preço-alvo", "stop" ou qualquer recomendação de ativo. Opinião sobre o cenário, sim; recomendação, não.
4. Use SÓ números que estão nos dados. Não arredonde para impressionar.
5. Previsão nunca vira certeza: o mercado "dá X%", não "vai acontecer".
6. Máximo {EMOJIS} emojis no corpo do post (o veredito conta). Sem hashtags.
7. NÃO escreva a linha "📌 Minha posição": o sistema acrescenta.
8. Primeira pessoa do singular, nenhum "?", nenhum palavrão e nenhum nome de plataforma. Post que quebrar isso volta para refazer.
9. Cada post tem no máximo {LIMITE} caracteres.`;

// X Premium: post longo (até 25.000 caracteres no X); aqui o padrão é 500–1.500 para caber
// em 2 versões numa mensagem do Telegram (limite 4.096).
const FORMATO_LONGO = `FORMATO LONGO (X Premium): cada post tem entre {MIN} e {LIMITE} caracteres.
- As primeiras ~280 letras aparecem antes do "Mostrar mais": o gancho inteiro tem que estar ali.
- Parágrafos de 1 a 3 frases, separados por linha em branco. Nada de bloco de texto.
- Roteiro: gancho → o dado (probabilidade, variação em 24 h, volume, Kalshi se houver) → por que isso importa (aqui cabe o estudo) → quem ganha e quem perde na bolsa → minha leitura → veredito.
- Bom é denso, não comprido: cada parágrafo traz um fato ou uma posição. Corte enrolação.`;
const FORMATO_CURTO = "FORMATO CURTO: frases curtas, um único bloco, direto ao ponto.";

const SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["posts"],
  properties: {
    posts: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["texto", "gancho", "estudo"],
        properties: {
          texto: { type: "string" },
          gancho: { type: "string", enum: ["lacuna", "contraste", "numero_choque", "contrarian", "denuncia", "estudo"] },
          estudo: { type: "string" },
        },
      },
    },
  },
};

const PEDIDOS = {
  diario: "Escreva 2 versões do post diário sobre o maior destaque, com ganchos de tipos diferentes. Se algum estudo da lista combinar com o destaque, use-o em uma das versões. Pode citar um segundo destaque se couber.",
  virada: "VIRADA: movimento brusco agora. Escreva 2 versões mais curtas que o normal, para sair rápido.",
  fio: "Escreva UM fio de 4 a 6 posts, na ordem: gancho → o que mudou → por que importa (aqui cabe um estudo da lista) → quem ganha e quem perde no mercado → veredito. Cada item de 'posts' é um post do fio.",
  placar: "Escreva 2 versões do post '📒 Placar da Semana' com os acertos E os erros dos sinais da semana. Transparência brutal: erro é erro.",
  saida: "Escreva 2 versões do post de SAÍDA da posição: diga que zerou, o resultado (ganho ou perda, sem esconder) e o que o mercado de previsão mostrou. Sem recomendar nada.",
};
const AJUSTES = {
  outra: "Escreva versões novas, com outro ângulo e outro gancho.",
  forte: "Mais imponente: imagens mais grandiosas, ritmo mais solene, abertura mais impactante. Continua sem palavrão.",
  sobrio: "Mais sóbrio: mesma posição firme, menos metáfora, tom de analista elegante e seco.",
};

// ---------- posições ----------
const nome = (t) => t.replace(/\.SA$/, "");
const data = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : "");

export function posicoesEfetivas(manuais, auto) {
  return { ...(auto || {}), ...(manuais || {}) };
}

export function linhaPosicao(posicoes, tickers, liquidez = {}, liquidezMin = 0) {
  const relevantes = Object.entries(posicoes || {})
    .filter(([t]) => !tickers || tickers.map(nome).includes(nome(t)))
    .filter(([t]) => liquidez[t] == null || liquidez[t] >= liquidezMin);
  if (!relevantes.length) return "📌 Sem posição.";
  const partes = relevantes.slice(0, 3).map(([t, p]) => `${p.lado} em ${nome(t)}${p.desde ? ` desde ${data(p.desde)}` : ""}`);
  return `📌 Minha posição: ${partes.join("; ")}. Não é recomendação.`;
}

// ---------- validação ----------
// Menção a estudo científico sem referência da lista = invenção. "pesquisa" sozinha fica de fora
// porque também quer dizer pesquisa eleitoral, que é dado legítimo.
const CIENCIA = /\b(estudos?|paper|artigo científico|cientistas|pesquisadores|universidade|et al)\b|\([^()]*\d{4}\)/i;

const PALAVRAO = /(?<![\p{L}])(porra|caralho|merda|puta|fod[ae]\w*|cacete|bost[ao]|cu|vsf|pqp|fdp|desgraça\w*|idiota\w*|imbecil\w*|otári[oa]s?)(?![\p{L}])/iu;
const PLATAFORMA = /polymarket|kalshi|manifold|predictit/i;

const PRIMEIRA_PESSOA = /(?<![\p{L}])(eu|meu|minha|meus|minhas|comigo)(?![\p{L}])/iu;
const PLURAL = /(?<![\p{L}])(nós|nosso|nossa|nossos|nossas|a gente)(?![\p{L}])/iu;

// regras: { minimo, emojis, primeiraPessoa, semPergunta, semPalavrao, semPlataforma } (o gerador liga todas).
export function validar(texto, limite = LIMITE, estudos = [], estudoId = "", regras = {}) {
  const erros = [];
  const citados = (estudos || []).filter((e) => texto.includes(e.curta));
  if (CIENCIA.test(texto) && !citados.length) erros.push("citou estudo fora da lista 'estudos'");
  if (estudoId) {
    const e = (estudos || []).find((x) => x.id === estudoId);
    if (!e) erros.push(`estudo "${estudoId}" não existe na lista`);
    else if (!texto.includes(e.curta)) erros.push(`usou o estudo ${estudoId} sem escrever "${e.curta}"`);
  }
  if (PROIBIDAS.test(texto)) erros.push("palavra de recomendação proibida");
  if (texto.length > limite) erros.push(`passou de ${limite} caracteres`);
  if (regras.minimo && texto.length < regras.minimo) erros.push(`curto demais: mínimo de ${regras.minimo} caracteres`);
  const maxEmojis = regras.emojis ?? 2;
  if ((texto.match(EMOJI) || []).length > maxEmojis) erros.push(`mais de ${maxEmojis} emojis`);
  if (/📌/.test(texto)) erros.push("escreveu a linha de posição");
  if (regras.semPergunta && texto.includes("?")) erros.push("tem pergunta: troque todo '?' por afirmação");
  if (regras.primeiraPessoa && !PRIMEIRA_PESSOA.test(texto)) erros.push("não está na primeira pessoa do singular (eu, meu, minha)");
  if (regras.primeiraPessoa && PLURAL.test(texto)) erros.push("usou 'nós' ou 'a gente': é primeira pessoa do SINGULAR");
  if (regras.semPalavrao && PALAVRAO.test(texto)) erros.push("tem palavrão: o tom é literário, sem vulgaridade");
  if (regras.semPlataforma && PLATAFORMA.test(texto)) erros.push("citou o nome da plataforma: fale do sentimento do mercado");
  return erros;
}

// Tamanho por tipo de post. X Premium (cfg.premium) libera post longo.
export function formato(tipo, cfg = {}) {
  const premium = Boolean(cfg.premium);
  const max = Math.min(cfg.tamanho_max || 1500, 1800); // 2 versões têm de caber numa mensagem do Telegram
  if (tipo === "fio") return { limite: LIMITE, minimo: 0, emojis: 2, longo: false };
  if (tipo === "virada") return premium ? { limite: 600, minimo: 0, emojis: 2, longo: false } : { limite: 200, minimo: 0, emojis: 2, longo: false };
  return premium
    ? { limite: max, minimo: Math.min(cfg.tamanho_min || 500, max), emojis: 4, longo: true }
    : { limite: LIMITE, minimo: 0, emojis: 2, longo: false };
}

export function intent(texto) {
  return `https://x.com/intent/post?text=${encodeURIComponent(texto)}`;
}

// ---------- geração ----------
export function montarPedido({ tipo, dados, posLinha, ajuste, exemplos, perfil, cfg }) {
  const fmt = formato(tipo, cfg);
  const limiteCorpo = fmt.limite - (tipo === "fio" ? 0 : posLinha.length + 2);
  const minimo = fmt.minimo ? Math.max(fmt.minimo - posLinha.length - 2, 0) : 0;
  const bloco = (fmt.longo ? FORMATO_LONGO : FORMATO_CURTO).replace("{MIN}", String(minimo)).replace("{LIMITE}", String(limiteCorpo));
  const system = ESTILO.replace("{PERFIL}", perfil)
    .replace("{FORMATO}", bloco)
    .replace("{EMOJIS}", String(fmt.emojis))
    .replace("{LIMITE}", String(limiteCorpo));
  const conteudo = {
    pedido: PEDIDOS[tipo],
    ajuste: ajuste ? AJUSTES[ajuste] : null,
    limite_caracteres_por_post: limiteCorpo,
    minimo_caracteres_por_post: minimo || undefined,
    dados,
    posts_que_mais_engajaram: exemplos?.length ? exemplos : undefined,
  };
  const regras = { minimo, emojis: fmt.emojis, primeiraPessoa: true, semPergunta: true, semPalavrao: true, semPlataforma: true };
  // Links ficam fora do texto do modelo (o da Polymarket levaria o nome da plataforma ao post).
  const user = JSON.stringify(conteudo, (k, v) => (k === "link" ? undefined : v));
  return { system, user, limiteCorpo, regras };
}

// fallbacks "default" e effort só nos modelos que aceitam (Haiku 4.5 recusaria os dois).
const COM_FALLBACK = new Set(["claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"]);
export function pedidoApi(cfg, system, mensagens) {
  const modelo = cfg?.modelo || "claude-opus-5-5";
  const pedido = {
    model: modelo,
    max_tokens: 4000,
    output_config: { format: { type: "json_schema", schema: SCHEMA } },
    system,
    messages: mensagens,
  };
  if (!modelo.startsWith("claude-haiku")) pedido.output_config.effort = cfg?.effort || "low";
  if (COM_FALLBACK.has(modelo)) {
    pedido.betas = ["server-side-fallback-2026-07-01"];
    pedido.fallbacks = "default";
  }
  return pedido;
}

export async function gerar({ env, tipo, dados, posLinha, ajuste, exemplos, perfil, cfg, criarCliente }) {
  const { system, user, limiteCorpo, regras } = montarPedido({ tipo, dados, posLinha, ajuste, exemplos, perfil, cfg });
  if (!env.ANTHROPIC_API_KEY || env.ANTHROPIC_API_KEY === "-") return modeloFixo(tipo, dados, posLinha);
  const client = criarCliente ? criarCliente(env) : new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 25_000 });
  let mensagens = [{ role: "user", content: user }];
  for (let tentativa = 0; tentativa < 2; tentativa++) {
    const resp = await client.beta.messages.create(pedidoApi(cfg, system, mensagens));
    if (resp.stop_reason === "refusal") return modeloFixo(tipo, dados, posLinha);
    const bloco = resp.content.find((b) => b.type === "text");
    let posts = [];
    try {
      posts = JSON.parse(bloco?.text || "{}").posts || [];
    } catch {
      posts = [];
    }
    const limpos = posts.map((p) => ({ ...p, texto: p.texto.trim(), estudo: p.estudo || "" }));
    const ruins = limpos.map((p) => validar(p.texto, limiteCorpo, dados?.estudos, p.estudo, regras));
    const bons = limpos.filter((_, i) => !ruins[i].length);
    const fioOk = tipo === "fio" ? bons.length === limpos.length && bons.length >= 4 : bons.length > 0;
    if (fioOk) return finalizar(tipo, bons, posLinha);
    const problemas = [...new Set(ruins.flat())].join("; ") || "resposta vazia";
    mensagens = [
      ...mensagens,
      { role: "assistant", content: bloco?.text || "{}" },
      { role: "user", content: `Refaça. Problemas: ${problemas}. Respeite os limites.` },
    ];
  }
  return modeloFixo(tipo, dados, posLinha);
}

function finalizar(tipo, posts, posLinha) {
  if (tipo === "fio") {
    const ultimo = posts.length - 1;
    return posts.map((p, i) => ({ ...p, texto: i === ultimo ? `${p.texto}\n\n${posLinha}` : p.texto }));
  }
  return posts.slice(0, 2).map((p) => ({ ...p, texto: `${p.texto}\n\n${posLinha}` }));
}

// Sem chave da Anthropic (ou se o modelo recusar): texto de modelo, seco mas correto.
export function modeloFixo(tipo, dados, posLinha) {
  const d = dados?.destaques?.[0] || dados?.destaque || null;
  let corpo;
  if (tipo === "placar") corpo = "📒 Placar da Semana: eu deixo os números no Telegram. Acerto e erro, tudo à vista.";
  else if (tipo === "saida") corpo = `Eu zerei ${nome(dados.ticker)}. Resultado: ${dados.resultado_txt}. Sem drama, sem esconder.`;
  else if (d) {
    const v = d.var_24h_pp ?? d.dp_pp ?? 0;
    const pergunta = String(d.pergunta || "").replace(/\?+\s*$/, "");
    const veredito = d.manipulacao === "🔴" || d.manipulacao === "🟡" ? "⚠️ mercado mentindo: eu vejo risco de manipulação no radar." : v > 0 ? "🟢 eu vejo o mercado apostando forte." : "🔴 eu vejo o mercado correndo disso.";
    corpo = `${d.emoji || ""} ${pergunta}: o mercado dá ${Math.round(d.prob * 100)}% (${v > 0 ? "+" : ""}${String(v).replace(".", ",")} p.p. em 24 h).\n${veredito}`;
  } else corpo = "Eu olhei os mercados de previsão hoje: parados. Silêncio também é dado.";
  return [{ texto: `${corpo.slice(0, LIMITE - posLinha.length - 2)}\n\n${posLinha}`, gancho: "contraste", estudo: "" }];
}

// ---------- mensagem no Telegram ----------
export function teclado(pid, posts, tipo) {
  const abrir =
    tipo === "fio"
      ? [{ text: "✅ Abrir 1º post no X", url: intent(posts[0].texto) }]
      : posts.map((p, i) => ({ text: `✅ Abrir no X (${"AB"[i]})`, url: intent(p.texto) }));
  return [
    abrir,
    [
      { text: "🔄 Outra versão", callback_data: `x:outra:${pid}` },
      { text: "🔥 Mais forte", callback_data: `x:forte:${pid}` },
      { text: "🧊 Mais sóbrio", callback_data: `x:sobrio:${pid}` },
    ],
  ];
}

const TITULOS = { diario: "🔮 Termômetro do Caos", virada: "⚡ Alerta de virada", fio: "🧵 Fio", placar: "📒 Placar da Semana", saida: "📌 Post de saída" };
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function fonte(p, estudos) {
  const e = p.estudo && (estudos || []).find((x) => x.id === p.estudo);
  return e ? `\n🔗 Fonte (responda no próprio post): ${esc(e.cita)} — ${e.link}` : "";
}

export function textoTelegram(tipo, posts, aviso = "", estudos = []) {
  const corpo =
    tipo === "fio"
      ? posts.map((p, i) => `<b>${i + 1}/${posts.length}</b>\n${esc(p.texto)}${fonte(p, estudos)}`).join("\n\n")
      : posts.map((p, i) => `<b>${"AB"[i]})</b> ${esc(p.texto)}\n<i>${p.texto.length} caracteres</i>${fonte(p, estudos)}`).join("\n\n");
  return `${TITULOS[tipo]} — rascunho para o X${aviso ? `\n${aviso}` : ""}\n\n${corpo}`;
}

// ---------- orquestração (Worker) ----------
async function kvJson(env, chave, padrao) {
  try {
    return (await env.ESTADO.get(chave, "json")) ?? padrao;
  } catch {
    return padrao;
  }
}

export async function telegram(env, metodo, corpo) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${metodo}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(corpo),
  });
  return r.ok ? (await r.json()).result : null;
}

async function enviarFoto(env, png64, legenda, botoes, silencioso = false) {
  const bytes = Uint8Array.from(atob(png64), (c) => c.charCodeAt(0));
  const form = new FormData();
  form.append("chat_id", String(env.TELEGRAM_CHAT_ID));
  form.append("photo", new Blob([bytes], { type: "image/png" }), "termometro.png");
  form.append("caption", legenda);
  form.append("parse_mode", "HTML");
  form.append("reply_markup", JSON.stringify({ inline_keyboard: botoes }));
  form.append("disable_notification", String(silencioso));
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendPhoto`, { method: "POST", body: form });
  return r.ok ? (await r.json()).result : null;
}

function exemplosEngajamento(registros) {
  return [...(registros || [])]
    .sort((a, b) => b.curtidas + 2 * b.reposts - (a.curtidas + 2 * a.reposts))
    .slice(0, 3)
    .map((r) => r.texto);
}

// Gera, manda no Telegram e guarda o estado do post (para os botões e o /engajamento).
export async function publicarRascunho(env, { tipo, dados, tickers, ajuste = null, pidAnterior = null, aviso = "", agora = new Date(), silencioso = false }) {
  const [pauta, manuais, eng] = await Promise.all([
    kvJson(env, "x_pauta", {}), kvJson(env, "posicoes", {}), kvJson(env, "x_engajamento", []),
  ]);
  const posicoes = posicoesEfetivas(manuais, pauta.posicoes_auto);
  const posLinha = linhaPosicao(posicoes, tickers, pauta.liquidez || {}, pauta.liquidez_min || 0);
  if (pauta.estudos?.length && tipo !== "saida") dados = { ...dados, estudos: pauta.estudos, ganchos: pauta.ganchos };
  const posts = await gerar({
    env, tipo, dados, posLinha, ajuste, exemplos: exemplosEngajamento(eng), perfil: pauta.perfil || "@pedroloopz", cfg: pauta.x,
  });
  const pid = pidAnterior || `${tipo}-${agora.getTime().toString(36)}`;
  const texto = textoTelegram(tipo, posts, aviso, dados?.estudos);
  const botoes = teclado(pid, posts, tipo);
  const comFoto = tipo === "diario" && pauta.grafico_png && texto.length <= 1024;
  const msg = comFoto
    ? await enviarFoto(env, pauta.grafico_png, texto, botoes, silencioso)
    : await telegram(env, "sendMessage", { chat_id: env.TELEGRAM_CHAT_ID, text: texto, parse_mode: "HTML", disable_web_page_preview: true, disable_notification: silencioso, reply_markup: { inline_keyboard: botoes } });
  const estado = await kvJson(env, "x_posts", {});
  estado[pid] = {
    tipo, dados, tickers, posts, ts: agora.toISOString(), message_id: msg?.message_id ?? null,
    posicoes_citadas: posLinha.startsWith("📌 Minha posição") ? Object.keys(posicoes).filter((t) => !tickers || tickers.map(nome).includes(nome(t))) : [],
  };
  const chaves = Object.keys(estado).sort((a, b) => Date.parse(estado[b].ts) - Date.parse(estado[a].ts)).slice(0, 30);
  await env.ESTADO.put("x_posts", JSON.stringify(Object.fromEntries(chaves.map((k) => [k, estado[k]]))));
  return { pid, posts, message_id: msg?.message_id };
}

export async function regenerar(env, acao, pid) {
  const estado = await kvJson(env, "x_posts", {});
  const p = estado[pid];
  if (!p) return null;
  return publicarRascunho(env, { tipo: p.tipo, dados: p.dados, tickers: p.tickers, ajuste: acao });
}

// Saída de posição: post obrigatório se houve post citando o ativo há menos de 24 h.
export async function postSaida(env, ticker, posicao, precoSaida, agora = new Date()) {
  const r = posicao.lado === "vendido" ? posicao.preco / precoSaida - 1 : precoSaida / posicao.preco - 1;
  const resultado_txt = `${r >= 0 ? "+" : "−"}${Math.abs(r * 100).toFixed(1).replace(".", ",")}%`;
  const estado = await kvJson(env, "x_posts", {});
  const recente = Object.values(estado).some(
    (p) => (p.posicoes_citadas || []).map(nome).includes(nome(ticker)) && agora.getTime() - Date.parse(p.ts) < 24 * 3600e3,
  );
  const aviso = recente ? "⚠️ <b>Obrigatório publicar</b>: você zerou menos de 24 h depois de um post sobre o ativo." : "";
  await publicarRascunho(env, {
    tipo: "saida",
    dados: { ticker: nome(ticker), lado: posicao.lado, desde: posicao.desde, preco_entrada: posicao.preco, preco_saida: precoSaida, resultado_txt },
    tickers: [], aviso, agora,
  });
  return { resultado: r, resultado_txt, obrigatorio: recente };
}

// ---------- comandos do Telegram ----------
export async function comandoX(nomeCmd, args, env, { buscarPreco, replyTo, agora = new Date() } = {}) {
  const responder = (t) => [{ texto: t }];
  if (nomeCmd === "posicoes") {
    const [manuais, pauta] = await Promise.all([kvJson(env, "posicoes", {}), kvJson(env, "x_pauta", {})]);
    const todas = posicoesEfetivas(manuais, pauta.posicoes_auto);
    if (!Object.keys(todas).length) return responder("📌 Nenhuma posição. Use /posicao comprado PETR4");
    const liq = pauta.liquidez || {};
    return responder(["📌 <b>Posições declaradas</b>", ...Object.entries(todas).map(([t, p]) => {
      const baixa = liq[t] != null && liq[t] < (pauta.liquidez_min || 0) ? " — baixa liquidez: fora dos posts" : "";
      return `• ${p.lado} em ${nome(t)} desde ${data(p.desde)}${p.origem ? ` (${p.origem})` : ""}${baixa}`;
    })].join("\n"));
  }
  if (nomeCmd === "posicao") {
    const m = /^(comprado|vendido)\s+([A-Za-z0-9.^=-]+)(?:\s+([\d.,]+))?$/i.exec(args);
    if (!m) return responder("Formato: /posicao comprado PETR4 ou /posicao vendido XLE 90,10");
    const lado = m[1].toLowerCase();
    let t = m[2].toUpperCase();
    if (/^[A-Z]{4}\d{1,2}$/.test(t)) t += ".SA";
    let preco = m[3] ? Number(m[3].replace(/\./g, "").replace(",", ".")) : null;
    if (!preco && buscarPreco) preco = (await buscarPreco(t))?.preco ?? null;
    if (!preco) return responder(`Não achei o preço de ${nome(t)}. Informe: /posicao ${lado} ${nome(t)} 12,34`);
    const manuais = await kvJson(env, "posicoes", {});
    manuais[t] = { lado, preco, desde: agora.toISOString().slice(0, 10), origem: "telegram" };
    await env.ESTADO.put("posicoes", JSON.stringify(manuais));
    return responder(`📌 Registrado: ${lado} em ${nome(t)} a ${preco.toFixed(2).replace(".", ",")}. Entra nos posts sobre o tema (só depois de você entrar, nunca antes).`);
  }
  if (nomeCmd === "zerar") {
    const m = /^([A-Za-z0-9.^=-]+)(?:\s+([\d.,]+))?$/.exec(args);
    if (!m) return responder("Formato: /zerar PETR4 ou /zerar PETR4 38,90");
    const manuais = await kvJson(env, "posicoes", {});
    const t = Object.keys(manuais).find((k) => nome(k) === nome(m[1].toUpperCase()));
    if (!t) return responder("Essa posição não foi declarada por /posicao (as do alerta-ema saem sozinhas quando somem de lá).");
    let preco = m[2] ? Number(m[2].replace(/\./g, "").replace(",", ".")) : null;
    if (!preco && buscarPreco) preco = (await buscarPreco(t))?.preco ?? null;
    if (!preco) return responder(`Não achei o preço de ${nome(t)}. Informe: /zerar ${nome(t)} 12,34`);
    const posicao = manuais[t];
    delete manuais[t];
    await env.ESTADO.put("posicoes", JSON.stringify(manuais));
    return { zerar: { ticker: t, posicao, preco }, respostas: responder(`📌 ${nome(t)} zerado. Gerando o post de saída…`) };
  }
  if (nomeCmd === "engajamento") {
    const m = /^(\S+)\s+(\d+)\s+(\d+)(?:\s+([ABab]))?$/.exec(args);
    if (!m) return responder("Formato (responda à mensagem do rascunho): /engajamento https://x.com/... 120 15 A");
    const estado = await kvJson(env, "x_posts", {});
    const lista = Object.entries(estado).sort((a, b) => Date.parse(b[1].ts) - Date.parse(a[1].ts));
    const alvo = lista.find(([, p]) => replyTo && p.message_id === replyTo) || lista[0];
    if (!alvo) return responder("Nenhum rascunho encontrado.");
    const [pid, p] = alvo;
    const i = (m[4] || "A").toUpperCase() === "B" ? 1 : 0;
    const post = p.posts[i] || p.posts[0];
    const horaLocal = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit" }).format(new Date(p.ts));
    const registros = await kvJson(env, "x_engajamento", []);
    registros.push({ pid, link: m[1], curtidas: Number(m[2]), reposts: Number(m[3]), formato: p.tipo, gancho: post.gancho, horario: `${horaLocal}h`, texto: post.texto, ts: agora.toISOString() });
    await env.ESTADO.put("x_engajamento", JSON.stringify(registros.slice(-200)));
    return responder(`📣 Anotado: ${m[2]} curtidas, ${m[3]} reposts (${p.tipo}, gancho "${post.gancho}"). O placar de domingo mostra o que funciona.`);
  }
  if (nomeCmd === "post") {
    return { gerarDiario: true, respostas: responder("🔮 Escrevendo o Termômetro do Caos agora…") };
  }
  return null;
}

export const COMANDOS_X = new Set(["posicao", "posicoes", "zerar", "engajamento", "post"]);

export async function postDiario(env, agora = new Date()) {
  const pauta = await kvJson(env, "x_pauta", {});
  const destaques = (pauta.destaques || []).slice(0, 2);
  const tickers = [...new Set(destaques.flatMap((d) => d.ativos_ligados || []))];
  return publicarRascunho(env, { tipo: "diario", dados: { destaques, placar: pauta.placar }, tickers, agora });
}

function horaBrt(agora) {
  const p = new Intl.DateTimeFormat("en-GB", { timeZone: "America/Sao_Paulo", hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(agora);
  const g = (t) => p.find((x) => x.type === t).value;
  return { dia: `${g("year")}-${g("month")}-${g("day")}`, minutos: (Number(g("hour")) % 24) * 60 + Number(g("minute")) };
}

// Chamado pelo Cron Trigger (a cada 5 min): horários do post diário, pedidos das Actions
// (fio, placar), alertas de virada e saídas automáticas das posições do alerta-ema.
export async function rotinaX(env, estado, agora, { novosSinais = [], buscarPreco, silencio = false } = {}) {
  const pauta = await kvJson(env, "x_pauta", null);
  if (!pauta) return estado;
  const feitos = new Set(estado.x_feitos || []);
  const { dia, minutos } = horaBrt(agora);
  for (const slot of pauta.x?.horarios || ["08:30", "10:20", "18:30"]) {
    const [h, m] = slot.split(":").map(Number);
    const chave = `diario:${dia}:${slot}`;
    if (minutos >= h * 60 + m && minutos < h * 60 + m + 15 && !feitos.has(chave)) {
      feitos.add(chave);
      await postDiario(env, agora);
    }
  }
  for (const p of await kvJson(env, "x_pedidos", [])) {
    if (feitos.has(p.id)) continue;
    feitos.add(p.id);
    const tickers = p.tipo === "fio" ? p.dados?.ativos_ligados || [] : [];
    await publicarRascunho(env, { tipo: p.tipo, dados: p.dados, tickers, agora, silencioso: silencio });
  }
  const zVirada = pauta.x?.virada_z_min ?? 3;
  for (const s of novosSinais.filter((x) => Math.abs(x.z) >= zVirada)) {
    const dados = { destaque: { pergunta: s.detalhes?.pergunta, prob: s.p_sinal, prob_antes: s.p_base, dp_pp: Math.round((s.p_sinal - s.p_base) * 1000) / 10, z: s.z, tema: s.tema } };
    await publicarRascunho(env, { tipo: "virada", dados, tickers: [s.ativo], agora, silencioso: silencio });
  }
  const atual = pauta.posicoes_auto;
  if (atual && estado.x_auto) {
    for (const [t, pos] of Object.entries(estado.x_auto)) {
      if (atual[t] || !pos?.preco) continue;
      const preco = (await buscarPreco?.(t))?.preco;
      if (preco) await postSaida(env, t, pos, preco, agora);
    }
  }
  if (atual) estado.x_auto = atual;
  estado.x_feitos = [...feitos].slice(-100);
  return estado;
}

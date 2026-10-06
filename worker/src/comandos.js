// Lógica dos comandos do Telegram (pura: sem rede, testável com `node --test`).
// O painel (textos prontos) é publicado no KV pelas GitHub Actions; aqui só repassamos.

export const AJUDA = [
  "🤖 <b>Bot de sinais — mercados de previsão</b>",
  "Somente leitura. Nunca aposta e nunca executa ordens.",
  "",
  "📰 /resumo — resumo do dia",
  "🇮🇷 /ira · 🇾🇪 /mar · 🇹🇼 /taiwan · 🇺🇦 /ucrania",
  "🏦 /fed · 🇧🇷 /brasil · 🇺🇸 /tarifas · ₿ /cripto",
  "🪙 /balancos — balanços de cripto",
  "⏳ /prazos — mercados vencendo",
  "🆕 /novos — mercados novos",
  "🎯 /sinal — últimos sinais",
  "📊 /ranking — calibração (defasagem × efeito)",
  "📒 /placar — diário simulado",
  "⚙️ /config — limiares, temas e silêncio",
  "",
  "📣 <b>Posts para o X</b>",
  "/post — rascunho do Termômetro do Caos agora",
  "/posicao comprado PETR4 · /zerar PETR4 · /posicoes",
  "/engajamento link curtidas reposts A (respondendo ao rascunho)",
  "💰 /capital 10000 — define o capital (R$)",
  "🌙 /silencio — horário de silêncio",
  "🩺 /status — saúde das fontes",
  "",
  "🐋 /baleias — carteiras vencedoras",
  "📅 /agenda — eventos dos próximos 30 dias",
].join("\n");

const BOTOES_TEMAS = [
  [
    { text: "📰 Resumo", callback_data: "ver:resumo" },
    { text: "🇮🇷 Irã", callback_data: "tema:ira" },
    { text: "🇧🇷 Brasil", callback_data: "tema:brasil" },
  ],
  [
    { text: "🏦 Fed", callback_data: "tema:fed" },
    { text: "🇹🇼 Taiwan", callback_data: "tema:taiwan" },
    { text: "₿ Cripto", callback_data: "tema:cripto" },
  ],
  [
    { text: "⏳ Prazos", callback_data: "ver:prazos" },
    { text: "🪙 Balanços", callback_data: "ver:balancos" },
    { text: "🆕 Novos", callback_data: "ver:novos" },
  ],
];

const BOTOES_SILENCIO = [
  [
    { text: "🌙 22h–7h", callback_data: "sil:22:00-07:00" },
    { text: "🌙 23h–6h", callback_data: "sil:23:00-06:00" },
  ],
  [
    { text: "🔕 Ligar", callback_data: "sil:on" },
    { text: "🔔 Desligar", callback_data: "sil:off" },
  ],
];

// Telegram não aceita acento em comando, mas o usuário pode digitar /irã.
const ALIASES = {
  "irã": "ira", iran: "ira", hormuz: "ira",
  "balanços": "balancos", "ucrânia": "ucrania", "silêncio": "silencio",
  ajuda: "ajuda", help: "ajuda", start: "start", btc: "cripto",
};

const VISOES = new Set(["resumo", "prazos", "novos", "placar", "sinal", "balancos", "ranking", "agenda", "baleias"]);
const CAMPO_VISAO = { sinal: "sinais" };
const FUTURO = {};

export function normalizarComando(texto) {
  const m = /^\/([^\s@]+)(?:@\S+)?\s*(.*)$/s.exec((texto || "").trim());
  if (!m) return null;
  const nome = m[1].toLowerCase();
  return { nome: ALIASES[nome] || nome, args: m[2].trim() };
}

// "10.000,50" → 10000.5 ; "10000" → 10000 ; "10,5" → 10.5
export function numeroBR(texto) {
  let t = String(texto || "").replace(/[^\d.,-]/g, "");
  if (!t) return null;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function dinheiroBR(n) {
  return "R$ " + n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function msg(chatId, text, botoes) {
  const corpo = { method: "sendMessage", chat_id: chatId, text, parse_mode: "HTML", disable_web_page_preview: true };
  if (botoes) corpo.reply_markup = { inline_keyboard: botoes };
  return corpo;
}

function idadeMin(iso, agora) {
  const t = Date.parse(iso || "");
  return Number.isFinite(t) ? Math.round((agora - t) / 60000) : null;
}

function textoStatus(painel, agora) {
  if (!painel) return "🩺 Ainda não há painel no KV. Rode o workflow <b>coleta horária</b> uma vez.";
  const partes = ["🩺 <b>Status</b>", `Painel atualizado: ${painel.atualizado_em_txt || "—"}`];
  const idade = idadeMin(painel.atualizado_em, agora);
  if (idade !== null && idade > 150) partes.push(`⚠️ Painel com ${Math.round(idade / 60)} h de atraso — confira as Actions.`);
  for (const [tarefa, info] of Object.entries(painel.execucoes || {})) {
    partes.push(`• ${tarefa}: ${info.status === "ok" ? "✅" : "❌"} ${info.fim ? info.fim.replace("T", " ").slice(0, 16) + " UTC" : ""}`);
  }
  for (const [fonte, estado] of Object.entries(painel.fontes || {})) {
    partes.push(`${estado === "ok" ? "🟢" : "🟠"} ${fonte}: ${estado}`);
  }
  if (painel.tempo_real) partes.push(painel.tempo_real);
  partes.push("🤖 Worker: ✅ respondendo");
  return partes.join("\n");
}

function silencioAtual(config, painel) {
  return config?.regras?.silencio || painel?.regras?.silencio || { ligado: true, inicio: "22:00", fim: "07:00" };
}

function textoSilencio(s) {
  return s.ligado === false
    ? "🔔 Silêncio desligado: tudo toca a qualquer hora."
    : `🌙 Silêncio das ${s.inicio} às ${s.fim}: só 🚨 urgente toca. O resto chega depois.`;
}

function aplicarSilencio(config, painel, valor) {
  const atual = { ...silencioAtual(config, painel) };
  if (valor === "off") atual.ligado = false;
  else if (valor === "on") atual.ligado = true;
  else {
    const m = /^(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?$/.exec(valor);
    if (!m) return null;
    const hh = (h, mm) => `${String(Number(h)).padStart(2, "0")}:${mm || "00"}`;
    if (Number(m[1]) > 23 || Number(m[3]) > 23) return null;
    atual.inicio = hh(m[1], m[2]);
    atual.fim = hh(m[3], m[4]);
    atual.ligado = true;
  }
  const nova = structuredClone(config || {});
  nova.regras = nova.regras || {};
  nova.regras.silencio = atual;
  return nova;
}

// ---------- /config ----------
// Cada opção grava no KV "config" no mesmo formato que o Python lê (regras.* e temas_desligados).
const OPCOES = {
  z: { rotulo: "z-score mín.", caminho: ["sinais", "zscore_min"], valores: [1.5, 2, 2.5, 3], fmt: (v) => fmtNum(v, 1) },
  vol: {
    rotulo: "Volume mín. p/ sinal",
    caminho: ["filtros", "volume_min_sinal_usd"],
    valores: [250000, 500000, 1000000, 2000000],
    fmt: (v) => (v >= 1e6 ? `US$ ${fmtNum(v / 1e6, 0)} mi` : `US$ ${fmtNum(v / 1e3, 0)} mil`),
  },
  gr: { rotulo: "Ganho/risco mín.", caminho: ["risco", "ganho_risco_min"], valores: [1.2, 1.5, 2], fmt: (v) => fmtNum(v, 1) },
  risco: {
    rotulo: "Risco por operação",
    caminho: ["risco", "risco_por_operacao_pct"],
    valores: [0.5, 1, 2],
    fmt: (v) => `${fmtNum(v, 1)}%`,
  },
};
const PADRAO_REGRAS = { zscore_min: 2, volume_min_sinal_usd: 1000000, ganho_risco_min: 1.5, risco_por_operacao_pct: 1 };

function fmtNum(v, casas) {
  return Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function valorAtual(config, painel, chave) {
  const op = OPCOES[chave];
  const [grupo, campo] = op.caminho;
  const doKv = config?.regras?.[grupo]?.[campo];
  if (doKv !== undefined && doKv !== null) return doKv;
  return painel?.regras?.[campo] ?? PADRAO_REGRAS[campo];
}

function temaLigado(config, painel, chave) {
  const desligados = config?.temas_desligados;
  if (Array.isArray(desligados)) return !desligados.includes(chave);
  const t = Object.values(painel?.temas || {}).find((x) => x.chave === chave);
  return t ? t.ligado !== false : true;
}

export function menuConfig(config, painel) {
  const linhas = ["⚙️ <b>Configuração</b> (toque para mudar)"];
  const botoes = [];
  for (const [chave, op] of Object.entries(OPCOES)) {
    const atual = valorAtual(config, painel, chave);
    linhas.push(`• ${op.rotulo}: <b>${op.fmt(atual)}</b>`);
    botoes.push(
      op.valores.map((v) => ({ text: (Number(v) === Number(atual) ? "✅ " : "") + op.fmt(v), callback_data: `cfg:${chave}:${v}` })),
    );
  }
  const s = silencioAtual(config, painel);
  linhas.push(`• Silêncio: <b>${s.ligado === false ? "desligado" : `${s.inicio}–${s.fim}`}</b>`);
  botoes.push([
    { text: "🗂️ Temas", callback_data: "cfg:temas" },
    { text: "🌙 Silêncio", callback_data: "cfg:silencio" },
  ]);
  linhas.push("", "Vale a partir da próxima coleta (até 1 h).");
  return { texto: linhas.join("\n"), botoes };
}

export function menuTemas(config, painel) {
  const temas = Object.values(painel?.temas || {});
  if (!temas.length) return { texto: "🗂️ Ainda sem painel. Rode a coleta uma vez.", botoes: [] };
  const botoes = temas.map((t) => [
    { text: `${temaLigado(config, painel, t.chave) ? "✅" : "⏸️"} ${t.emoji} ${t.nome}`, callback_data: `cfg:tema:${t.chave}` },
  ]);
  botoes.push([{ text: "⬅️ Voltar", callback_data: "cfg:menu" }]);
  return { texto: "🗂️ <b>Temas</b> — toque para ligar/desligar", botoes };
}

function aplicarConfig(config, painel, partes) {
  const nova = structuredClone(config || {});
  nova.regras = nova.regras || {};
  const [chave, valor] = partes;
  if (OPCOES[chave]) {
    const v = Number(valor);
    if (!OPCOES[chave].valores.includes(v)) return null;
    const [grupo, campo] = OPCOES[chave].caminho;
    nova.regras[grupo] = { ...(nova.regras[grupo] || {}), [campo]: v };
    return nova;
  }
  if (chave === "tema" && valor) {
    const desligados = new Set(
      Array.isArray(nova.temas_desligados)
        ? nova.temas_desligados
        : Object.values(painel?.temas || {}).filter((t) => t.ligado === false).map((t) => t.chave),
    );
    if (desligados.has(valor)) desligados.delete(valor);
    else desligados.add(valor);
    nova.temas_desligados = [...desligados];
    return nova;
  }
  return null;
}

function editar(chatId, messageId, texto, botoes) {
  const corpo = { method: "editMessageText", chat_id: chatId, message_id: messageId, text: texto, parse_mode: "HTML" };
  if (botoes) corpo.reply_markup = { inline_keyboard: botoes };
  return corpo;
}

function tratarConfig(partes, chatId, messageId, painel, config) {
  const [acao] = partes;
  const resposta = (m) => (messageId ? editar(chatId, messageId, m.texto, m.botoes) : msg(chatId, m.texto, m.botoes));
  if (!acao || acao === "menu") return { respostas: [resposta(menuConfig(config, painel))] };
  if (acao === "temas") return { respostas: [resposta(menuTemas(config, painel))] };
  if (acao === "silencio") {
    return { respostas: [resposta({ texto: textoSilencio(silencioAtual(config, painel)), botoes: BOTOES_SILENCIO })] };
  }
  const nova = aplicarConfig(config, painel, partes);
  if (!nova) return { respostas: [] };
  const tela = acao === "tema" ? menuTemas(nova, painel) : menuConfig(nova, painel);
  return { respostas: [resposta(tela)], config: nova };
}

function visao(painel, chave) {
  if (!painel) return "⏳ Ainda sem dados. A primeira coleta roda pelas GitHub Actions.";
  if (chave === "placar" && painel.placar_semanal) return painel.placar_semanal;
  const t = painel[CAMPO_VISAO[chave] || chave];
  return t || "Sem dados no momento.";
}

function tema(painel, cmd) {
  const t = painel?.temas?.[cmd];
  return t ? t.texto : null;
}

// Retorna { respostas: [...chamadas da Bot API], config?: novaConfig }
export function tratarMensagem(texto, chatId, painel, config, agora = Date.now()) {
  const cmd = normalizarComando(texto);
  if (!cmd) return { respostas: [msg(chatId, "Use /ajuda para ver os comandos.", BOTOES_TEMAS)] };
  const { nome, args } = cmd;

  if (nome === "start" || nome === "ajuda") return { respostas: [msg(chatId, AJUDA, BOTOES_TEMAS)] };
  if (nome === "status") return { respostas: [msg(chatId, textoStatus(painel, agora))] };
  if (nome === "config") return tratarConfig([], chatId, null, painel, config);
  if (FUTURO[nome]) return { respostas: [msg(chatId, FUTURO[nome])] };

  if (nome === "capital") {
    if (!args) {
      const c = config?.regras?.risco?.capital;
      return { respostas: [msg(chatId, c ? `💰 Capital: ${dinheiroBR(c)}` : "💰 Capital não definido. Ex.: /capital 10000")] };
    }
    const n = numeroBR(args);
    if (n === null || n <= 0) return { respostas: [msg(chatId, "Valor inválido. Ex.: /capital 10.000,00")] };
    const nova = structuredClone(config || {});
    nova.regras = nova.regras || {};
    nova.regras.risco = { ...(nova.regras.risco || {}), capital: n };
    return { respostas: [msg(chatId, `💰 Capital salvo: ${dinheiroBR(n)}\nFica só no Cloudflare KV (nunca vai para o GitHub).`)], config: nova };
  }

  if (nome === "silencio") {
    if (!args) return { respostas: [msg(chatId, textoSilencio(silencioAtual(config, painel)), BOTOES_SILENCIO)] };
    const nova = aplicarSilencio(config, painel, args.toLowerCase().replace(/h/g, ""));
    if (!nova) return { respostas: [msg(chatId, "Formato: /silencio 22-7 · /silencio off · /silencio on")] };
    return { respostas: [msg(chatId, "✅ " + textoSilencio(nova.regras.silencio))], config: nova };
  }

  if (VISOES.has(nome)) {
    const botoes = nome === "resumo" ? BOTOES_TEMAS : undefined;
    return { respostas: [msg(chatId, visao(painel, nome), botoes)] };
  }

  const t = tema(painel, nome);
  if (t) return { respostas: [msg(chatId, t)] };
  if (!painel) return { respostas: [msg(chatId, visao(null, nome))] };
  return { respostas: [msg(chatId, "Comando desconhecido. Veja /ajuda.", BOTOES_TEMAS)] };
}

export function tratarBotao(dados, chatId, painel, config, messageId = null) {
  const [tipo, ...resto] = String(dados || "").split(":");
  const valor = resto.join(":");
  if (tipo === "cfg") return tratarConfig(resto, chatId, messageId, painel, config);
  if (tipo === "ver") return { respostas: [msg(chatId, visao(painel, valor), valor === "resumo" ? BOTOES_TEMAS : undefined)] };
  if (tipo === "tema") return { respostas: [msg(chatId, tema(painel, valor) || visao(painel, valor))] };
  if (tipo === "sil") {
    const nova = aplicarSilencio(config, painel, valor);
    if (!nova) return { respostas: [] };
    return { respostas: [msg(chatId, "✅ " + textoSilencio(nova.regras.silencio))], config: nova };
  }
  return { respostas: [] };
}

export function autorizado(chatId, env) {
  return Boolean(env.TELEGRAM_CHAT_ID) && String(chatId) === String(env.TELEGRAM_CHAT_ID).trim();
}

export function textoNaoAutorizado(chatId) {
  return [
    "🔒 Este bot é privado.",
    `Seu chat ID é <code>${chatId}</code>.`,
    "Se o bot é seu: cadastre esse número no GitHub Secret <b>TELEGRAM_CHAT_ID</b> e rode o workflow <b>Deploy do Worker</b>.",
  ].join("\n");
}

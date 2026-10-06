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
  "📒 /placar — diário simulado",
  "💰 /capital 10000 — define o capital (R$)",
  "🌙 /silencio — horário de silêncio",
  "🩺 /status — saúde das fontes",
  "",
  "Em breve: /config (Fase 2), /ranking (Fase 2), /baleias e /agenda (Fase 3).",
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

const VISOES = new Set(["resumo", "prazos", "novos", "placar", "sinal", "balancos"]);
const CAMPO_VISAO = { sinal: "sinais" };
const FUTURO = {
  config: "⚙️ O menu /config chega na Fase 2. Por enquanto: /capital e /silencio.",
  ranking: "📊 O /ranking sai da calibração (Fase 2).",
  baleias: "🐋 Carteiras vencedoras chegam na Fase 3.",
  agenda: "📅 A agenda de eventos chega na Fase 3.",
};

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

function visao(painel, chave) {
  if (!painel) return "⏳ Ainda sem dados. A primeira coleta roda pelas GitHub Actions.";
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

export function tratarBotao(dados, chatId, painel, config) {
  const [tipo, ...resto] = String(dados || "").split(":");
  const valor = resto.join(":");
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

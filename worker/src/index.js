// Cloudflare Worker: webhook do Telegram (respostas na hora).
// Fase 3 adiciona aqui o Cron Trigger de quase tempo real.
import { autorizado, textoNaoAutorizado, tratarBotao, tratarMensagem } from "./comandos.js";

const API = "https://api.telegram.org";

async function chamar(env, corpo) {
  const { method, ...resto } = corpo;
  const r = await fetch(`${API}/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(resto),
  });
  if (!r.ok) console.log(JSON.stringify({ evento: "telegram_erro", metodo: method, status: r.status }));
}

async function lerJson(env, chave) {
  try {
    return await env.ESTADO.get(chave, "json");
  } catch {
    return null;
  }
}

async function tratarUpdate(update, env) {
  const mensagem = update.message || update.edited_message;
  const botao = update.callback_query;
  const chatId = mensagem?.chat?.id ?? botao?.message?.chat?.id;
  if (chatId === undefined) return [];

  if (!autorizado(chatId, env)) {
    const texto = mensagem?.text || "";
    // Responde só ao /start, para o dono descobrir o chat ID; o resto é ignorado.
    return texto.startsWith("/start")
      ? [{ method: "sendMessage", chat_id: chatId, text: textoNaoAutorizado(chatId), parse_mode: "HTML" }]
      : [];
  }

  const [painel, config] = await Promise.all([lerJson(env, "painel"), lerJson(env, "config")]);
  const resultado = botao
    ? tratarBotao(botao.data, chatId, painel, config, botao.message?.message_id)
    : tratarMensagem(mensagem?.text || "", chatId, painel, config);

  if (resultado.config) await env.ESTADO.put("config", JSON.stringify(resultado.config));
  const chamadas = [...resultado.respostas];
  if (botao) chamadas.unshift({ method: "answerCallbackQuery", callback_query_id: botao.id });
  return chamadas;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") {
      return new Response("polymarket-sinais: ok", { headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    if (request.method !== "POST" || url.pathname !== "/telegram") return new Response("não encontrado", { status: 404 });
    if (!env.WEBHOOK_SECRET || request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("proibido", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("json inválido", { status: 400 });
    }

    const chamadas = await tratarUpdate(update, env);
    // A última resposta volta no próprio corpo do webhook (economiza uma subrequisição);
    // as demais vão por fetch.
    const ultima = chamadas.pop();
    for (const c of chamadas) await chamar(env, c);
    return ultima
      ? new Response(JSON.stringify(ultima), { headers: { "content-type": "application/json" } })
      : new Response("ok");
  },
};

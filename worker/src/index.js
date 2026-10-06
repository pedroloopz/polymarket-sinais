// Cloudflare Worker: webhook do Telegram (respostas na hora).
// Fase 3: Cron Trigger a cada 5 min (tempo_real.js).
import { autorizado, normalizarComando, textoNaoAutorizado, tratarBotao, tratarMensagem } from "./comandos.js";
import { buscadores, rodar } from "./tempo_real.js";
import { COMANDOS_X, comandoX, postDiario, postSaida, regenerar, rotinaX } from "./x.js";

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

async function tratarUpdate(update, env, ctx) {
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

  // Posts do X: botões de rascunho e comandos de posição/engajamento
  if (botao && String(botao.data || "").startsWith("x:")) {
    const [, acao, pid] = botao.data.split(":");
    ctx.waitUntil(regenerar(env, acao, pid).catch((e) => console.log(JSON.stringify({ evento: "x_erro", erro: String(e) }))));
    return [{ method: "answerCallbackQuery", callback_query_id: botao.id, text: "Escrevendo outra versão…" }];
  }
  const cmd = normalizarComando(mensagem?.text || "");
  if (cmd && COMANDOS_X.has(cmd.nome)) {
    const r = await comandoX(cmd.nome, cmd.args, env, {
      buscarPreco: buscadores(env).buscarPreco, replyTo: mensagem?.reply_to_message?.message_id,
    });
    const respostas = Array.isArray(r) ? r : r?.respostas || [];
    if (r?.zerar) ctx.waitUntil(postSaida(env, r.zerar.ticker, r.zerar.posicao, r.zerar.preco));
    if (r?.gerarDiario) ctx.waitUntil(postDiario(env));
    return respostas.map((x) => ({ method: "sendMessage", chat_id: chatId, text: x.texto, parse_mode: "HTML" }));
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
  async scheduled(evento, env, ctx) {
    ctx.waitUntil(
      rodar(env, new Date(), { rotinaX }).catch((erro) =>
        console.log(JSON.stringify({ evento: "tempo_real_erro", erro: String(erro) })),
      ),
    );
  },

  async fetch(request, env, ctx) {
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

    const chamadas = await tratarUpdate(update, env, ctx ?? { waitUntil: () => {} });
    // A última resposta volta no próprio corpo do webhook (economiza uma subrequisição);
    // as demais vão por fetch.
    const ultima = chamadas.pop();
    for (const c of chamadas) await chamar(env, c);
    return ultima
      ? new Response(JSON.stringify(ultima), { headers: { "content-type": "application/json" } })
      : new Response("ok");
  },
};

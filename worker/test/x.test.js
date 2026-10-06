import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { comandoX, gerar, intent, linhaPosicao, modeloFixo, pedidoApi, rotinaX, validar } from "../src/x.js";

function kvFalso(inicial = {}) {
  const dados = Object.fromEntries(Object.entries(inicial).map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)]));
  return {
    dados,
    async get(k, tipo) {
      const v = dados[k];
      return v == null ? null : tipo === "json" ? JSON.parse(v) : v;
    },
    async put(k, v) {
      dados[k] = v;
    },
  };
}

// fetch falso para o Telegram: guarda as mensagens enviadas
let enviadas = [];
const fetchOriginal = globalThis.fetch;
beforeEach(() => {
  enviadas = [];
  globalThis.fetch = async (url, opcoes) => {
    const corpo = opcoes?.body instanceof FormData ? Object.fromEntries(opcoes.body.entries()) : JSON.parse(opcoes?.body || "{}");
    enviadas.push({ url: String(url), corpo });
    return new Response(JSON.stringify({ ok: true, result: { message_id: 100 + enviadas.length } }), { status: 200 });
  };
});
afterEach(() => {
  globalThis.fetch = fetchOriginal;
});

function clienteFalso(respostas) {
  const chamadas = [];
  return {
    chamadas,
    criar: () => ({
      beta: {
        messages: {
          create: async (req) => {
            chamadas.push(req);
            const r = respostas.shift();
            return r.refusal
              ? { stop_reason: "refusal", content: [] }
              : { stop_reason: "end_turn", content: [{ type: "thinking", thinking: "" }, { type: "text", text: JSON.stringify(r) }] };
          },
        },
      },
    }),
  };
}

const DADOS = { destaques: [{ pergunta: "US x Iran ceasefire by December 31?", prob: 0.78, var_24h_pp: 16, emoji: "🇮🇷", manipulacao: "🟢", ativos_ligados: ["XLE", "PETR4"] }] };
const ENV = { ANTHROPIC_API_KEY: "sk-teste", TELEGRAM_BOT_TOKEN: "1:abc", TELEGRAM_CHAT_ID: "42" };

test("validação barra recomendação, excesso de emoji e tamanho", () => {
  assert.deepEqual(validar("A guerra acabou pro mercado, porra. 78% na Polymarket.\n🟢 mercado bom"), []);
  assert.ok(validar("Compre XLE agora").length);
  assert.ok(validar("preço-alvo de 90").length);
  assert.ok(validar("🔥🔥🔥 caos").length);
  assert.ok(validar("x".repeat(281)).length);
  assert.deepEqual(validar("Venda de petróleo caiu entre 40% e 50%."), []); // palavras comuns passam
});

test("linha de posição: só ativos ligados e com liquidez", () => {
  const pos = { "PETR4.SA": { lado: "comprado", desde: "2026-10-05" }, MICO: { lado: "comprado", desde: "2026-10-01" } };
  assert.equal(linhaPosicao(pos, ["XLE", "PETR4"]), "📌 Minha posição: comprado em PETR4 desde 05/10. Não é recomendação.");
  assert.equal(linhaPosicao(pos, ["XLE"]), "📌 Sem posição.");
  assert.equal(linhaPosicao({ MICO: pos.MICO }, null, { MICO: 1000 }, 5e6), "📌 Sem posição.");
});

test("gera 2 versões, acrescenta a posição e respeita 280", async () => {
  const c = clienteFalso([{ posts: [{ texto: "A guerra acabou pro mercado, porra. Polymarket dá 78%.\n🟢 mercado bom", gancho: "contraste" }, { texto: "16 p.p. em 24 h e a TV dormindo.\n🟢 mercado bom", gancho: "numero_choque" }] }]);
  const posts = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@pedroloopz", cfg: {}, criarCliente: c.criar });
  assert.equal(posts.length, 2);
  assert.ok(posts.every((p) => p.texto.endsWith("📌 Sem posição.") && p.texto.length <= 280));
  const req = c.chamadas[0];
  assert.equal(req.model, "claude-opus-5-5");
  assert.equal(req.fallbacks, "default");
  assert.deepEqual(req.betas, ["server-side-fallback-2026-07-01"]);
  assert.equal(req.output_config.format.type, "json_schema");
  assert.match(req.system, /@pedroloopz/);
  assert.match(req.system, /NUNCA contra pessoas/);
});

test("post inválido pede refação; recusa cai no modelo fixo", async () => {
  const c = clienteFalso([{ posts: [{ texto: "Compre XLE já, caralho", gancho: "denuncia" }] }, { posts: [{ texto: "O mercado virou, porra.\n🔴 mercado ruim", gancho: "contraste" }] }]);
  const posts = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {}, criarCliente: c.criar });
  assert.equal(c.chamadas.length, 2);
  assert.match(c.chamadas[1].messages.at(-1).content, /recomendação proibida/);
  assert.ok(posts[0].texto.startsWith("O mercado virou"));
  const r = clienteFalso([{ refusal: true }]);
  const fixo = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {}, criarCliente: r.criar });
  assert.match(fixo[0].texto, /78% na Polymarket/);
});

test("sem chave: modelo fixo, sem chamar a API", async () => {
  const posts = await gerar({ env: { ANTHROPIC_API_KEY: "-" }, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {} });
  assert.match(posts[0].texto, /US x Iran ceasefire/);
  assert.equal(validar(posts[0].texto.split("\n\n")[0]).length, 0);
  assert.match(modeloFixo("saida", { ticker: "PETR4.SA", resultado_txt: "+3,2%" }, "📌 Sem posição.")[0].texto, /Zerei PETR4/);
});

test("intent do X com texto codificado", () => {
  assert.equal(intent("a & b"), "https://x.com/intent/post?text=a%20%26%20b");
});

test("comandos de posição e engajamento", async () => {
  const env = { ...ENV, ESTADO: kvFalso({ x_pauta: { liquidez: {}, liquidez_min: 0 } }) };
  const buscarPreco = async () => ({ preco: 38.5 });
  let r = await comandoX("posicao", "comprado petr4", env, { buscarPreco, agora: new Date("2026-10-06T12:00:00Z") });
  assert.match(r[0].texto, /comprado em PETR4 a 38,50/);
  assert.equal(JSON.parse(env.ESTADO.dados.posicoes)["PETR4.SA"].lado, "comprado");
  r = await comandoX("posicoes", "", env);
  assert.match(r[0].texto, /comprado em PETR4 desde 06\/10/);
  r = await comandoX("zerar", "PETR4 40,00", env, { buscarPreco });
  assert.equal(r.zerar.ticker, "PETR4.SA");
  assert.equal(r.zerar.preco, 40);
  assert.deepEqual(JSON.parse(env.ESTADO.dados.posicoes), {});
  env.ESTADO.dados.x_posts = JSON.stringify({ "diario-1": { tipo: "diario", ts: "2026-10-06T11:30:00Z", message_id: 77, posts: [{ texto: "a", gancho: "contraste" }, { texto: "b", gancho: "denuncia" }] } });
  r = await comandoX("engajamento", "https://x.com/p/1 120 15 B", env, { replyTo: 77 });
  const reg = JSON.parse(env.ESTADO.dados.x_engajamento)[0];
  assert.equal(reg.curtidas, 120);
  assert.equal(reg.gancho, "denuncia");
  assert.equal(reg.horario, "08h");
});

test("rotina: post no horário, uma vez só; pedido de placar; saída automática", async () => {
  const env = {
    ANTHROPIC_API_KEY: "-", TELEGRAM_BOT_TOKEN: "1:abc", TELEGRAM_CHAT_ID: "42",
    ESTADO: kvFalso({
      x_pauta: { perfil: "@pedroloopz", destaques: DADOS.destaques, liquidez: {}, liquidez_min: 0, x: { horarios: ["08:30"] },
        posicoes_auto: {} },
      x_pedidos: [{ id: "placar:2026-10-05", tipo: "placar", dados: { placar: "📒 3 sinais" } }],
    }),
  };
  const agora = new Date("2026-10-06T11:32:00Z"); // 08:32 em Brasília
  let estado = { x_auto: { ABNB: { lado: "comprado", preco: 158.31, desde: "2026-09-25" } } };
  estado = await rotinaX(env, estado, agora, { buscarPreco: async () => ({ preco: 164 }) });
  const textos = enviadas.map((e) => e.corpo.text || e.corpo.caption || "");
  assert.ok(textos.some((t) => t.startsWith("🔮 Termômetro do Caos")));
  assert.ok(textos.some((t) => t.startsWith("📒 Placar da Semana")));
  assert.ok(textos.some((t) => t.startsWith("📌 Post de saída") && t.includes("ABNB")));
  const total = enviadas.length;
  await rotinaX(env, estado, new Date("2026-10-06T11:37:00Z"), {});
  assert.equal(enviadas.length, total); // não repete no mesmo horário
  assert.ok(estado.x_feitos.includes("diario:2026-10-06:08:30"));
  const guardados = JSON.parse(env.ESTADO.dados.x_posts);
  assert.ok(Object.keys(guardados).length >= 3);
});

test("parâmetros por modelo", () => {
  const haiku = pedidoApi({ modelo: "claude-haiku-4-5" }, "s", []);
  assert.equal(haiku.fallbacks, undefined);
  assert.equal(haiku.output_config.effort, undefined);
  const sonnet = pedidoApi({ modelo: "claude-sonnet-5-5", effort: "low" }, "s", []);
  assert.equal(sonnet.fallbacks, "default");
  assert.equal(sonnet.output_config.effort, "low");
});

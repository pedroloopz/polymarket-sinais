import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { comandoX, formato, gerar, intent, linhaPosicao, modeloFixo, pedidoApi, rotinaX, textoTelegram, validar } from "../src/x.js";

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
  const c = clienteFalso([{ posts: [{ texto: "Eu vejo: a guerra acabou para o mercado. O dinheiro dá 78% à paz.\n🟢 mercado bom", gancho: "contraste", estudo: "" }, { texto: "16 p.p. em 24 h e eu sou o único olhando, a TV dormindo.\n🟢 mercado bom", gancho: "numero_choque", estudo: "" }] }]);
  const posts = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@pedroloopz", cfg: {}, criarCliente: c.criar });
  assert.equal(posts.length, 2);
  assert.ok(posts.every((p) => p.texto.endsWith("📌 Sem posição.") && p.texto.length <= 280));
  const req = c.chamadas[0];
  assert.equal(req.model, "claude-opus-5-5");
  assert.equal(req.fallbacks, "default");
  assert.deepEqual(req.betas, ["server-side-fallback-2026-07-01"]);
  assert.equal(req.output_config.format.type, "json_schema");
  assert.match(req.system, /@pedroloopz/);
  assert.match(req.system, /Nenhum ataque a pessoas/);
});

test("post inválido pede refação; recusa cai no modelo fixo", async () => {
  const c = clienteFalso([{ posts: [{ texto: "Compre XLE já", gancho: "denuncia" }] }, { posts: [{ texto: "Eu avisei: a maré do mercado virou.\n🔴 mercado ruim", gancho: "contraste", estudo: "" }] }]);
  const posts = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {}, criarCliente: c.criar });
  assert.equal(c.chamadas.length, 2);
  assert.match(c.chamadas[1].messages.at(-1).content, /recomendação proibida/);
  assert.ok(posts[0].texto.startsWith("Eu avisei"));
  const r = clienteFalso([{ refusal: true }]);
  const fixo = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {}, criarCliente: r.criar });
  assert.match(fixo[0].texto, /o mercado dá 78%/);
  assert.ok(!fixo[0].texto.includes("?"));
});

test("sem chave: modelo fixo, sem chamar a API", async () => {
  const posts = await gerar({ env: { ANTHROPIC_API_KEY: "-" }, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {} });
  assert.match(posts[0].texto, /US x Iran ceasefire/);
  assert.equal(validar(posts[0].texto.split("\n\n")[0]).length, 0);
  assert.match(modeloFixo("saida", { ticker: "PETR4.SA", resultado_txt: "+3,2%" }, "📌 Sem posição.")[0].texto, /Eu zerei PETR4/);
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

const ESTUDOS = [{ id: "berg2008_74", cita: "Berg, Nelson e Rietz, 2008", curta: "Berg et al., 2008", achado: "74%", link: "https://iemweb.biz.uiowa.edu/x" }];

test("estudo só da lista, com a referência escrita", () => {
  assert.deepEqual(validar("O mercado bateu as pesquisas em 74% das vezes (Berg et al., 2008).", 280, ESTUDOS, "berg2008_74"), []);
  assert.deepEqual(validar("As pesquisas eleitorais erram. O mercado não.", 280, ESTUDOS), []); // pesquisa eleitoral é dado legítimo
  assert.ok(validar("Um estudo de Harvard mostra que o mercado acerta 90%.", 280, ESTUDOS).length);
  assert.ok(validar("Mercado acerta mais (Silva, 2019).", 280, ESTUDOS).length);
  assert.ok(validar("Sem citação nenhuma.", 280, ESTUDOS, "berg2008_74").length);
  assert.ok(validar("x (Berg et al., 2008)", 280, ESTUDOS, "inventado").length);
});

test("rascunho no Telegram traz a fonte do estudo para responder no post", async () => {
  const c = clienteFalso([{ posts: [
    { texto: "Todo mundo confia na pesquisa. Eu confio no dinheiro: em 74% das vezes o mercado chegou mais perto (Berg et al., 2008).\n🟢 mercado bom", gancho: "estudo", estudo: "berg2008_74" },
    { texto: "16 p.p. em 24 h e eu vendo a TV dormir.\n🟢 mercado bom", gancho: "numero_choque", estudo: "" },
  ] }]);
  const posts = await gerar({ env: ENV, tipo: "diario", dados: { ...DADOS, estudos: ESTUDOS }, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {}, criarCliente: c.criar });
  assert.equal(posts.length, 2);
  assert.match(c.chamadas[0].system, /NO MÁXIMO UM estudo/);
  const txt = textoTelegram("diario", posts, "", ESTUDOS);
  assert.match(txt, /🔗 Fonte \(responda no próprio post\): Berg, Nelson e Rietz, 2008 — https:\/\/iemweb/);
  assert.equal((txt.match(/🔗/g) || []).length, 1);
});

test("primeira pessoa, sem pergunta e post longo no X Premium", async () => {
  const R = { primeiraPessoa: true, semPergunta: true };
  assert.deepEqual(validar("Eu olhei o livro e o mercado dá 31%.", 280, [], "", R), []);
  assert.ok(validar("O Fed vai cortar? O mercado dá 31%.", 280, [], "", R).some((e) => e.includes("pergunta")));
  assert.ok(validar("O mercado dá 31%.", 280, [], "", R).some((e) => e.includes("primeira pessoa")));
  assert.ok(validar("Eu e a gente sabemos.", 280, [], "", R).some((e) => e.includes("SINGULAR")));
  assert.ok(validar("Eu acho.", 1500, [], "", { minimo: 500 }).some((e) => e.includes("curto demais")));
  assert.deepEqual(formato("diario", { premium: true }), { limite: 1500, minimo: 500, emojis: 4, longo: true });
  assert.equal(formato("diario", {}).limite, 280);
  assert.equal(formato("diario", { premium: true, tamanho_max: 9000 }).limite, 1800);
  const longo = "Eu passei o dia ouvindo que o Fed corta. ".repeat(14) + "\n🟢 mercado bom";
  const c = clienteFalso([{ posts: [{ texto: longo, gancho: "lacuna", estudo: "" }] }]);
  const posts = await gerar({ env: ENV, tipo: "diario", dados: DADOS, posLinha: "📌 Sem posição.", perfil: "@p", cfg: { premium: true }, criarCliente: c.criar });
  assert.ok(posts[0].texto.length > 500);
  assert.match(c.chamadas[0].system, /FORMATO LONGO/);
  assert.match(c.chamadas[0].system, /primeira pessoa do singular/);
});

test("tom literário: sem palavrão e sem nome de plataforma; links fora do pedido", async () => {
  const R = { primeiraPessoa: true, semPalavrao: true, semPlataforma: true };
  assert.deepEqual(validar("Eu vejo a maré virar antes do trovão.", 1500, [], "", R), []);
  assert.ok(validar("Eu vejo o mercado virar, porra.", 1500, [], "", R).some((e) => e.includes("palavrão")));
  assert.ok(validar("Eu vejo 78% na Polymarket.", 1500, [], "", R).some((e) => e.includes("plataforma")));
  assert.deepEqual(validar("Eu vejo a computação mudar o mundo.", 1500, [], "", R), []); // "cu" só como palavra inteira
  const c = clienteFalso([{ posts: [{ texto: "Eu vejo a paz com 78%.\n🟢 mercado bom", gancho: "contraste", estudo: "" }] }]);
  await gerar({ env: ENV, tipo: "diario", dados: { destaques: [{ ...DADOS.destaques[0], link: "https://polymarket.com/event/x" }] }, posLinha: "📌 Sem posição.", perfil: "@p", cfg: {}, criarCliente: c.criar });
  assert.ok(!c.chamadas[0].messages[0].content.includes("polymarket.com"));
  assert.match(c.chamadas[0].system, /literária, romântica, poderosa e imponente/);
  assert.match(c.chamadas[0].system, /SEM PALAVRÃO/);
});

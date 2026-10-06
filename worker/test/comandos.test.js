import assert from "node:assert/strict";
import { test } from "node:test";

import { autorizado, normalizarComando, numeroBR, tratarBotao, tratarMensagem } from "../src/comandos.js";
import worker from "../src/index.js";

const PAINEL = {
  atualizado_em: new Date().toISOString(),
  atualizado_em_txt: "06/10 09:07",
  fontes: { "Polymarket Gamma": "ok", "Preços (yfinance)": "parcial (30/40)" },
  execucoes: { coletar: { fim: "2026-10-06T12:07:00+00:00", status: "ok" } },
  temas: { ira: { texto: "🇮🇷 <b>Irã</b>" }, cripto: { texto: "₿ BTC" } },
  resumo: "🗓️ resumo",
  prazos: "⏳ prazos",
  sinais: "🎯 nenhum",
  regras: { silencio: { ligado: true, inicio: "22:00", fim: "07:00" } },
};

test("normaliza comandos com acento e @bot", () => {
  assert.deepEqual(normalizarComando("/irã"), { nome: "ira", args: "" });
  assert.deepEqual(normalizarComando("/capital@MeuBot 10.000"), { nome: "capital", args: "10.000" });
  assert.equal(normalizarComando("oi"), null);
});

test("número no formato brasileiro", () => {
  assert.equal(numeroBR("10.000,50"), 10000.5);
  assert.equal(numeroBR("10000"), 10000);
  assert.equal(numeroBR("10.000"), 10000);
  assert.equal(numeroBR("R$ 2,5"), 2.5);
  assert.equal(numeroBR("abc"), null);
});

test("tema e visões vêm do painel", () => {
  assert.equal(tratarMensagem("/ira", 1, PAINEL, {}).respostas[0].text, "🇮🇷 <b>Irã</b>");
  assert.equal(tratarMensagem("/btc", 1, PAINEL, {}).respostas[0].text, "₿ BTC");
  assert.equal(tratarMensagem("/prazos", 1, PAINEL, {}).respostas[0].text, "⏳ prazos");
  assert.equal(tratarMensagem("/sinal", 1, PAINEL, {}).respostas[0].text, "🎯 nenhum");
  assert.match(tratarMensagem("/ira", 1, null, {}).respostas[0].text, /Ainda sem dados/);
});

test("/capital grava no config", () => {
  const r = tratarMensagem("/capital 25.000,00", 1, PAINEL, { regras: { silencio: { ligado: false } } });
  assert.equal(r.config.regras.risco.capital, 25000);
  assert.equal(r.config.regras.silencio.ligado, false); // não apaga o resto
  assert.match(r.respostas[0].text, /R\$ 25\.000,00/);
});

test("/silencio por texto e por botão", () => {
  const r = tratarMensagem("/silencio 23-6", 1, PAINEL, {});
  assert.deepEqual(r.config.regras.silencio, { ligado: true, inicio: "23:00", fim: "06:00" });
  const b = tratarBotao("sil:off", 1, PAINEL, r.config);
  assert.equal(b.config.regras.silencio.ligado, false);
  assert.equal(tratarMensagem("/silencio 25-6", 1, PAINEL, {}).config, undefined);
});

test("/status mostra fontes", () => {
  const t = tratarMensagem("/status", 1, PAINEL, {}).respostas[0].text;
  assert.match(t, /🟠 Preços \(yfinance\): parcial/);
  assert.match(t, /coletar: ✅/);
});

test("autorização por chat ID", () => {
  assert.ok(autorizado(42, { TELEGRAM_CHAT_ID: "42" }));
  assert.ok(!autorizado(43, { TELEGRAM_CHAT_ID: "42" }));
  assert.ok(!autorizado(42, {}));
});

function kvFalso(inicial = {}) {
  const dados = { ...inicial };
  return {
    dados,
    async get(k, tipo) {
      const v = dados[k];
      return v === undefined ? null : tipo === "json" ? JSON.parse(v) : v;
    },
    async put(k, v) {
      dados[k] = v;
    },
  };
}

function pedido(update, segredo = "s3gr3d0") {
  return new Request("https://x.workers.dev/telegram", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": segredo, "content-type": "application/json" },
    body: JSON.stringify(update),
  });
}

test("webhook recusa sem o segredo", async () => {
  const env = { WEBHOOK_SECRET: "s3gr3d0", ESTADO: kvFalso() };
  const r = await worker.fetch(pedido({}, "errado"), env);
  assert.equal(r.status, 403);
});

test("webhook responde comando no corpo e grava config", async () => {
  const env = { WEBHOOK_SECRET: "s3gr3d0", TELEGRAM_CHAT_ID: "42", ESTADO: kvFalso({ painel: JSON.stringify(PAINEL) }) };
  const r = await worker.fetch(pedido({ message: { chat: { id: 42 }, text: "/capital 1000" } }), env);
  const corpo = await r.json();
  assert.equal(corpo.method, "sendMessage");
  assert.equal(JSON.parse(env.ESTADO.dados.config).regras.risco.capital, 1000);
});

test("estranho recebe só o chat ID no /start", async () => {
  const env = { WEBHOOK_SECRET: "s3gr3d0", TELEGRAM_CHAT_ID: "42", ESTADO: kvFalso() };
  const r1 = await worker.fetch(pedido({ message: { chat: { id: 7 }, text: "/start" } }), env);
  assert.match((await r1.json()).text, /<code>7<\/code>/);
  const r2 = await worker.fetch(pedido({ message: { chat: { id: 7 }, text: "/ira" } }), env);
  assert.equal(await r2.text(), "ok");
});

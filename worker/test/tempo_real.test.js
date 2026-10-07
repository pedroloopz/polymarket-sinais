import assert from "node:assert/strict";
import { test } from "node:test";

import { acompanhar, ciclo, detectar, emSilencio, lerChart, precoEm, pregaoAberto, rodar } from "../src/tempo_real.js";

const AGORA = new Date("2026-10-06T15:00:00Z"); // 11:00 em Nova York, pregão aberto
const MIN = 60000;
const PREGOES = {
  EUA: { fuso: "America/New_York", abre: "09:30", fecha: "16:00", moeda: "USD" },
  B3: { fuso: "America/Sao_Paulo", abre: "10:00", fecha: "17:00", moeda: "BRL" },
  FUT: { fuso: "America/New_York", abre: "00:00", fecha: "23:59", moeda: "USD" },
};
const REGRAS = {
  zscore_min: 2, retencao_min: 0.5, prefiltro_pp: 1, espaco_min_pct: 50, latencia_multiplo: 3,
  zona: { abaixo: 0.1, acima: 0.9 }, prazo_curto_dias: 3, prazo_curto_fator_z: 1.5, ganho_risco_min: 1.5,
  risco_pct: 1, atr_mult: 1.5, stop_tempo_mult: 2, devolucao: 0.5, custo_pct: 0.2, limiar_semaforo_pct: 0.1,
  silencio: { ligado: true, inicio: "22:00", fim: "07:00" }, janelas_min: [15, 30, 60], pausado_ate: null,
};
const MERCADO = {
  id: "m1", token: "tokA", tema: "ira", emoji: "🇮🇷", nome_tema: "Irã / Hormuz (paz)",
  pergunta: "Cessar-fogo EUA x Irã até 31/12?", polaridade: 1,
  leitura: { sobe: "paz mais provável → petróleo mais barato", cai: "guerra mais provável → petróleo mais caro" }, sigma_h: 0.05, fim: "2026-12-31T00:00:00Z", manip: "🟢",
  par: { ativo: "XLE", beta_10pp: -1.5, defasagem_min: 45, bolsa: "EUA", atr: 0.5, alt: { ativo: "UAL", beta_10pp: 2 } },
  hipotese: { ativo: "XLE", sentido: -1 }, semaforo: { "BZ=F": -1, "^VIX": -1 },
};
const VIGIA = { gerado_em: AGORA.toISOString(), regras: REGRAS, pregoes: PREGOES, mercados: [MERCADO], abertos: [], capital_brl: 50000, cambio_brl: 5, setores: { XLE: "petróleo" } };

function leituras(valores, fim = AGORA) {
  return valores.map((p, i) => [fim.getTime() - (valores.length - i) * 5 * MIN, p]);
}

function precos(mapa) {
  // mapa: ticker → [preço na base (t−15 min), preço agora]
  return async (t) => {
    const v = mapa[t];
    if (!v) return null;
    return { preco: v[1], serie: [[AGORA.getTime() - 60 * MIN, v[0]], [AGORA.getTime() - 1 * MIN, v[1]]], anterior: v[0] };
  };
}

test("lê o JSON do Yahoo e acha o preço num instante", () => {
  const json = { chart: { result: [{ meta: { regularMarketPrice: 91, chartPreviousClose: 89 }, timestamp: [100, 400], indicators: { quote: [{ close: [90, null] }] } }] } };
  const d = lerChart(json);
  assert.equal(d.preco, 91);
  assert.equal(precoEm(d, 200 * 1000), 90);
  assert.equal(precoEm(d, 50 * 1000), 89); // antes da série: fechamento anterior
  assert.equal(lerChart({}), null);
});

test("pregão e silêncio pelo relógio certo", () => {
  assert.ok(pregaoAberto(PREGOES, "EUA", AGORA));
  assert.ok(!pregaoAberto(PREGOES, "EUA", new Date("2026-10-06T21:00:00Z")));
  assert.ok(!pregaoAberto(PREGOES, "EUA", new Date("2026-10-10T15:00:00Z"))); // sábado
  assert.ok(pregaoAberto(PREGOES, "B3", AGORA)); // 12:00 em São Paulo
  assert.ok(emSilencio(REGRAS.silencio, new Date("2026-10-07T02:00:00Z"))); // 23:00 BRT
  assert.ok(!emSilencio(REGRAS.silencio, AGORA));
});

test("detecta movimento persistente e ignora ruído", () => {
  const ls = [...leituras([0.6, 0.6, 0.7, 0.76]), [AGORA.getTime(), 0.78]];
  const c = detectar(MERCADO, ls, AGORA, REGRAS);
  assert.ok(c && c.z > 2 && Math.abs(c.dp - 0.18) < 1e-9 && c.janela === 15);
  const ruido = [...leituras([0.6, 0.601, 0.599, 0.6]), [AGORA.getTime(), 0.602]];
  assert.equal(detectar(MERCADO, ruido, AGORA, REGRAS), null);
  const devolveu = [...leituras([0.6, 0.6, 0.7, 0.76]), [AGORA.getTime(), 0.62]]; // devolveu quase tudo
  assert.equal(detectar(MERCADO, devolveu, AGORA, REGRAS), null);
});

test("ciclo: sinal acionável 🚨 com plano, depois stop", async () => {
  const enviadas = [];
  const rt = { leituras: { m1: leituras([0.6, 0.6, 0.7, 0.76]) }, seq: 0 };
  const estado = await ciclo({
    vigia: VIGIA, rt, ack: 0, agora: AGORA,
    buscarMids: async () => ({ tokA: 0.78 }),
    buscarPreco: precos({ XLE: [90.65, 90.1], "BZ=F": [70, 68.53], "^VIX": [20, 19.2] }),
    enviar: async (t) => enviadas.push(t),
  });
  assert.equal(enviadas.length, 1);
  const msg = enviadas[0];
  for (const trecho of ["🚨 <b>OPORTUNIDADE FORTE</b>", "⚡", "❓ Cessar-fogo EUA x Irã até 31/12?", "👉 <b>🔴 SHORT XLE</b> (petróleo)", "💡 paz mais provável", "Alternativa: 🟢 LONG UAL", "🎯 Alvo US$", "🛑 Stop US$ 90,85", "costuma andar −2,7%", "não é recomendação"]) {
    assert.ok(msg.includes(trecho), `${trecho}\n${msg}`);
  }
  const ev = estado.eventos.find((e) => e.tipo === "sinal");
  assert.equal(ev.sinal.acionavel, true);
  assert.equal(ev.sinal.urgencia, "🚨");
  assert.equal(estado.abertos_rt.length, 1);

  // 5 min depois o XLE sobe e bate o stop
  const depois = new Date(AGORA.getTime() + 5 * MIN);
  const enviadas2 = [];
  const estado2 = await ciclo({
    vigia: { ...VIGIA, gerado_em: depois.toISOString() }, rt: estado, ack: 0, agora: depois,
    buscarMids: async () => ({ tokA: 0.78 }),
    buscarPreco: precos({ XLE: [90.65, 91.0] }),
    enviar: async (t) => enviadas2.push(t),
  });
  assert.ok(enviadas2[0].startsWith("🛑 Stop atingido"));
  const fech = estado2.eventos.find((e) => e.tipo === "fechamento");
  assert.equal(fech.status, "stop");
  assert.equal(fech.ref, "rt-1");
  assert.equal(estado2.abertos_rt.length, 0);
});

test("sem calibração: informativo vai só para o diário/resumo", async () => {
  const enviadas = [];
  const m = { ...MERCADO, par: null };
  const estado = await ciclo({
    vigia: { ...VIGIA, mercados: [m] }, rt: { leituras: { m1: leituras([0.6, 0.6, 0.7, 0.76]) } }, ack: 0, agora: AGORA,
    buscarMids: async () => ({ tokA: 0.78 }), buscarPreco: precos({ XLE: [90.65, 90.1] }), enviar: async (t) => enviadas.push(t),
  });
  assert.equal(enviadas.length, 0);
  const ev = estado.eventos.find((e) => e.tipo === "sinal");
  assert.equal(ev.sinal.urgencia, "📋");
  assert.ok(ev.linha.includes("não operar: par ainda não calibrado"), ev.linha);
});

test("manipulação 🔴 e trava bloqueiam o acionável", async () => {
  for (const vigia of [
    { ...VIGIA, mercados: [{ ...MERCADO, manip: "🔴" }] },
    { ...VIGIA, regras: { ...REGRAS, pausado_ate: new Date(AGORA.getTime() + 3600e3).toISOString() } },
  ]) {
    const estado = await ciclo({
      vigia, rt: { leituras: { m1: leituras([0.6, 0.6, 0.7, 0.76]) } }, ack: 0, agora: AGORA,
      buscarMids: async () => ({ tokA: 0.78 }), buscarPreco: precos({ XLE: [90.65, 90.1] }), enviar: async () => {},
    });
    assert.equal(estado.eventos.find((e) => e.tipo === "sinal").sinal.acionavel, false);
  }
});

test("acompanha aberto vindo do banco e segura 🔔 no silêncio", async () => {
  const noite = new Date("2026-10-07T02:00:00Z");
  const aberto = { id: 7, ativo: "XLE", bolsa: "EUA", sentido: -1, entrada: 90.1, stop: 90.85, alvo: 88.2, parcial: 89.2, stop_tempo: null, mercado_id: "m1", token: "tokA", p_base: 0.6, p_sinal: 0.78, avisos: [] };
  const enviadas = [];
  const estado = await ciclo({
    vigia: { ...VIGIA, gerado_em: noite.toISOString(), abertos: [aberto] }, rt: {}, ack: 0, agora: noite,
    buscarMids: async () => ({ tokA: 0.78 }), buscarPreco: async () => ({ preco: 89.1, serie: [], anterior: 90 }),
    enviar: async (t) => enviadas.push(t),
  });
  assert.equal(enviadas.length, 0); // parcial é 🔔: segura no silêncio
  assert.ok(estado.eventos.some((e) => e.tipo === "parcial" && e.sinal_id === 7));
  assert.ok(estado.eventos.some((e) => e.tipo === "segurada" && e.texto.includes("Alvo parcial")));
  assert.equal(acompanhar({ ...aberto, avisos: ["parcial"] }, 89.1, 0.78, noite, REGRAS), null); // não repete
  assert.equal(acompanhar(aberto, 90.0, 0.62, noite, REGRAS).status, "invalidado");
});

test("eventos já confirmados pelas Actions saem do estado", async () => {
  const rt = { seq: 5, eventos: [{ seq: 4, tipo: "segurada", texto: "a" }, { seq: 5, tipo: "segurada", texto: "b" }] };
  const estado = await ciclo({ vigia: VIGIA, rt, ack: 4, agora: AGORA, buscarMids: async () => ({}), buscarPreco: async () => null, enviar: async () => {} });
  assert.deepEqual(estado.eventos.map((e) => e.seq), [5]);
});

test("rodar: vigia velha não faz nada; vigia nova grava rt", async () => {
  const dados = {};
  const env = {
    ESTADO: {
      async get(k, tipo) { const v = dados[k]; return v == null ? null : tipo === "json" ? JSON.parse(v) : v; },
      async put(k, v) { dados[k] = v; },
    },
  };
  dados.vigia = JSON.stringify({ ...VIGIA, gerado_em: new Date(AGORA.getTime() - 5 * 3600e3).toISOString() });
  assert.equal(await rodar(env, AGORA), null);
  assert.equal(dados.rt, undefined);
});

test("pergunta contra o tema: a leitura acompanha a polaridade", async () => {
  const enviadas = [];
  const m = { ...MERCADO, par: null, polaridade: -1, hipotese: { ativo: "XLE", sentido: 1 } };
  const estado = await ciclo({
    vigia: { ...VIGIA, mercados: [m] }, rt: { leituras: { m1: leituras([0.6, 0.6, 0.7, 0.76]) } }, ack: 0, agora: AGORA,
    buscarMids: async () => ({ tokA: 0.78 }), buscarPreco: precos({ XLE: [90.65, 90.1] }), enviar: async (t) => enviadas.push(t),
  });
  const ev = estado.eventos.find((e) => e.tipo === "sinal");
  assert.equal(ev.sinal.sentido, 1);
  assert.match(ev.linha, /🟢 LONG XLE/);
});

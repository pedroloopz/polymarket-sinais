import assert from "node:assert/strict";
import { test } from "node:test";

import { devidos, disparar, textoDisparo } from "../src/disparos.js";

function kv(inicial = {}) {
  const dados = { ...inicial };
  return { dados, async get(k) { return dados[k] ? JSON.parse(dados[k]) : null; }, async put(k, v) { dados[k] = v; } };
}

test("janelas: coleta aos :07–:21 UTC, resumo 07h20 BRT, placar domingo 21h45 BRT", () => {
  assert.deepEqual(devidos(new Date("2026-10-06T15:08:00Z")).map((d) => d.workflow), ["coleta_horaria.yml"]);
  assert.deepEqual(devidos(new Date("2026-10-06T15:30:00Z")), []);
  assert.ok(devidos(new Date("2026-10-06T10:22:00Z")).some((d) => d.workflow === "resumo_diario.yml"));
  assert.ok(devidos(new Date("2026-10-12T00:50:00Z")).some((d) => d.workflow === "placar_semanal.yml")); // dom 21:50 BRT
  assert.ok(!devidos(new Date("2026-10-13T00:50:00Z")).some((d) => d.workflow === "placar_semanal.yml")); // segunda
});

test("dispara uma vez por janela e só com token", async () => {
  const chamadas = [];
  const fetchFalso = async (url, op) => { chamadas.push({ url, corpo: JSON.parse(op.body) }); return new Response(null, { status: 204 }); };
  const env = { GH_DISPATCH_TOKEN: "t", ESTADO: kv() };
  const agora = new Date("2026-10-06T15:08:00Z");
  assert.deepEqual(await disparar(env, agora, fetchFalso), ["coleta:2026-10-06T15"]);
  assert.match(chamadas[0].url, /coleta_horaria\.yml\/dispatches$/);
  assert.deepEqual(chamadas[0].corpo, { ref: "main", inputs: { automatico: "1" } });
  assert.deepEqual(await disparar(env, new Date("2026-10-06T15:13:00Z"), fetchFalso), []);
  assert.equal(chamadas.length, 1);
  assert.deepEqual(await disparar({ GH_DISPATCH_TOKEN: "-", ESTADO: kv() }, agora, fetchFalso), []);
});

test("falha do GitHub não marca como feito (tenta de novo em 5 min)", async () => {
  const env = { GH_DISPATCH_TOKEN: "t", ESTADO: kv() };
  const erro = async () => new Response("no", { status: 403 });
  assert.deepEqual(await disparar(env, new Date("2026-10-06T15:08:00Z"), erro), []);
  assert.equal(env.ESTADO.dados.disparos, undefined);
});

test("anota o resultado para o /status", async () => {
  const env = { GH_DISPATCH_TOKEN: "t", ESTADO: kv() };
  await disparar(env, new Date("2026-10-06T15:08:00Z"), async () => new Response('{"message":"Resource not accessible by personal access token"}', { status: 403 }));
  const info = JSON.parse(env.ESTADO.dados.disparo_status);
  assert.equal(info.status, 403);
  assert.match(textoDisparo(info), /HTTP 403.*Resource not accessible.*Actions: Read and write/);
  await disparar(env, new Date("2026-10-06T16:08:00Z"), async () => { throw new TypeError("Illegal invocation"); });
  assert.match(textoDisparo(JSON.parse(env.ESTADO.dados.disparo_status)), /Illegal invocation/);
  await disparar(env, new Date("2026-10-06T17:08:00Z"), async () => new Response(null, { status: 204 }));
  assert.match(textoDisparo(JSON.parse(env.ESTADO.dados.disparo_status)), /✅ coleta_horaria\.yml/);
  const semToken = { GH_DISPATCH_TOKEN: "-", ESTADO: kv() };
  await disparar(semToken, new Date("2026-10-06T15:08:00Z"));
  assert.match(textoDisparo(JSON.parse(semToken.ESTADO.dados.disparo_status)), /sem o Secret/);
  assert.match(textoDisparo(null), /ainda não tentou/);
});

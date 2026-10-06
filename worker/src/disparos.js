// Relógio confiável: o agendamento do GitHub Actions atrasa e às vezes pula execuções.
// O Cron Trigger do Worker (a cada 5 min) dispara os workflows pela API do GitHub
// (workflow_dispatch). Precisa do segredo GH_DISPATCH_TOKEN; sem ele, não faz nada.
// O agendamento próprio do GitHub continua ligado: as Actions ignoram a execução repetida.

const REPO = "pedroloopz/polymarket-sinais";

function partes(agora, fuso) {
  const p = new Intl.DateTimeFormat("en-GB", {
    timeZone: fuso, hour12: false, weekday: "short", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  }).formatToParts(agora);
  const g = (t) => p.find((x) => x.type === t).value;
  return { dia: `${g("year")}-${g("month")}-${g("day")}`, semana: g("weekday"), h: Number(g("hour")) % 24, m: Number(g("minute")) };
}

// Cada item: o workflow, se está na janela agora e a chave que impede disparar duas vezes.
export function devidos(agora) {
  const utc = partes(agora, "UTC");
  const brt = partes(agora, "America/Sao_Paulo");
  const minBrt = brt.h * 60 + brt.m;
  const saida = [];
  if (utc.m >= 7 && utc.m < 22) saida.push({ workflow: "coleta_horaria.yml", chave: `coleta:${utc.dia}T${utc.h}` });
  if (minBrt >= 7 * 60 + 20 && minBrt < 7 * 60 + 45) saida.push({ workflow: "resumo_diario.yml", chave: `resumo:${brt.dia}` });
  if (brt.semana === "Sun" && minBrt >= 21 * 60 + 45 && minBrt < 22 * 60) {
    saida.push({ workflow: "placar_semanal.yml", chave: `placar:${brt.dia}` });
  }
  return saida;
}

export async function disparar(env, agora = new Date(), fetchFn = fetch) {
  const token = env.GH_DISPATCH_TOKEN;
  if (!token || token === "-") return [];
  const pendentes = devidos(agora);
  if (!pendentes.length) return [];
  const feitos = (await env.ESTADO.get("disparos", "json")) || [];
  const novos = [];
  for (const d of pendentes.filter((x) => !feitos.includes(x.chave))) {
    const r = await fetchFn(`https://api.github.com/repos/${REPO}/actions/workflows/${d.workflow}/dispatches`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "polymarket-sinais-worker",
        "content-type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: { automatico: "1" } }),
    });
    if (r.status === 204) novos.push(d.chave);
    else console.log(JSON.stringify({ evento: "disparo_falhou", workflow: d.workflow, status: r.status }));
  }
  if (novos.length) await env.ESTADO.put("disparos", JSON.stringify([...feitos, ...novos].slice(-60)));
  return novos;
}

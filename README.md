# 🔮 polymarket-sinais

Bot de **sinais** que lê mercados de previsão (Polymarket), cruza com preços de ações/ETFs da B3 e dos EUA e manda **resumos e alertas no Telegram**. Tudo roda na nuvem e é operado **pelo celular**.

> 🔒 **Somente leitura.** O bot nunca aposta nem executa ordens. Contratos de previsão política são proibidos no Brasil: usamos as probabilidades só como sinal.

## ⚖️ Aviso legal

- Análise ou recomendação **pública** de ativos específicos é atividade de analista de valores mobiliários (**Resolução CVM 20/2021**, exige credenciamento CNPI).
- A **Resolução CVM 62/2022** proíbe manipulação de preço e práticas não equitativas.
- Tudo o que o bot envia é **sinal de sistema para uso pessoal, não recomendação**. O módulo de posts para o X (Fase 4) foi desenhado para ficar em opinião sobre o cenário + declaração da própria posição.
- Sugestão de bio no X: *"Dados de mercados de previsão. Opinião pessoal, não recomendação de investimento."*

---

## 📍 Situação: Fase 3 (quase tempo real e vantagem)

| Módulo | Situação |
|---|---|
| 1 — Coleta horária (Polymarket + preços) | ✅ |
| 7 — Detector de mercado novo | ✅ |
| 8 — Prazos vencendo | ✅ |
| 10 — Balanços de cripto (data, mercado, reação dos últimos 8) | ✅ |
| 13 — Diário de sinais (registro + avaliação em +1 h/+1 d/+1 sem + placar) | ✅ |
| 15 — Telegram básico com webhook no Worker | ✅ |
| Resumo diário às 07h30 | ✅ |
| Deploy automático do Worker | ✅ |
| 2 — Calibração (defasagem × beta, mensal) + `/ranking` | ✅ |
| 3 — Sinais (z-score em log-odds, persistência, zona distorcida, prazo curto) | ✅ |
| 4 — Semáforo cruzado (Brent, DXY, VIX + ativo) | ✅ |
| 11 / 11b — Stop por ATR, tamanho, alvo, ganho/risco, stop de tempo, invalidação, acompanhamento | ✅ (de hora em hora; 1–5 min na Fase 3) |
| 12 — Urgência, silêncio e trava após 2 perdas | ✅ |
| Placar semanal (domingo 21h45) e `/config` | ✅ |
| ⚡ Quase tempo real: Worker a cada 5 min (detecção, plano com preço do Yahoo, alvo/stop/prazo/invalidação) | ✅ |
| 5 — Nota de risco de manipulação (concentração, Kalshi, volume, reversão, GDELT, palavras ditas) | ✅ |
| 6 — Carteiras vencedoras: ranking diário + alerta quando abrem/aumentam posição | ✅ |
| 9 — Agenda (FOMC, payroll, CPI das fontes oficiais; Copom/eleição/OPEP+ em `config/agenda.yaml`) + alerta na véspera | ✅ |
| 14 (X), Truth Social, Claude API, painel HTML | Fase 4 |

---

## 📱 Configuração (tudo pelo celular)

Faça na ordem. Leva uns 15 minutos.

### 1. Bot no Telegram (@BotFather)

1. No Telegram, abra **@BotFather** → `/newbot` → escolha nome e usuário (precisa terminar em `bot`).
2. Ele responde com o **token** (`123456789:AA...`). **Não cole o token em conversa nenhuma**: ele vai direto para o GitHub Secret (passo 3).
3. Se o token vazar: @BotFather → `/revoke` → escolha o bot → copie o token novo e troque o Secret.
4. Abra o seu bot e mande **qualquer mensagem** (ex.: `oi`). Isso é necessário para descobrir o chat ID.

### 2. Cloudflare (gratuito)

1. No navegador do celular, crie a conta em **dash.cloudflare.com/sign-up**.
2. Menu ☰ → **Workers e Pages** → abra uma vez. Se pedir, escolha o subdomínio `*.workers.dev` (ex.: `seunome.workers.dev`).
3. **Account ID:** ☰ → **Workers e Pages** → na coluna da direita aparece **Account ID** → copiar.
4. **Token de API:** foto do perfil (canto superior direito) → **Perfil** → **Tokens de API** → **Criar token** → modelo **Editar Cloudflare Workers** (*Edit Cloudflare Workers*) → **Usar modelo** → em *Recursos da conta* escolha a sua conta → **Continuar para o resumo** → **Criar token** → copiar (só aparece uma vez).

### 3. Secrets no GitHub

No navegador do celular (o app do GitHub não edita Secrets): abra o repositório → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Crie um por vez:

| Nome | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token do @BotFather |
| `TELEGRAM_CHAT_ID` | seu chat ID (passo 4) |
| `CLOUDFLARE_API_TOKEN` | token do Cloudflare |
| `CLOUDFLARE_ACCOUNT_ID` | Account ID do Cloudflare |

> Dica: no "Settings", se não aparecer, toque em **⋯** ou role a barra de abas para o lado; ou ative "Versão para computador" no navegador.

### 4. Descobrir o chat ID

1. Já mandou uma mensagem ao bot (passo 1.4)? Então: repositório → **Actions** → **Descobrir chat ID** → **Run workflow** → **Run workflow**.
2. Abra a execução (aguarde o ✅) → **Summary**: aparece o número ao lado do seu nome.
3. Crie o Secret `TELEGRAM_CHAT_ID` com esse número.

Se você já usa outro bot e conhece o seu chat ID, é o mesmo número: pode usá-lo direto. Depois que o Worker estiver no ar, mandar `/start` para o bot também mostra o ID.

### 5. Ligar tudo

1. **Actions** → **Deploy do Worker** → **Run workflow**. Ele cria o banco KV, publica o Worker, liga o webhook e cadastra o menu de comandos. Chega um "✅ Worker publicado" no Telegram.
2. **Actions** → **Coleta horária** → **Run workflow** (primeira coleta; depois roda sozinha de hora em hora).
3. **Actions** → **Resumo diário** → **Run workflow** para ver o resumo na hora (depois chega todo dia ~07h30).
4. No Telegram: `/ajuda`.

### 6. Fase 2: rodar a calibração uma vez

**Actions** → **Calibração** → **Run workflow**. Leva alguns minutos e manda o ranking no Telegram. Depois roda sozinha todo dia 1º. Sem calibração, todo sinal sai como 📋 informativo.

### Disparar um workflow manualmente (celular)

App do GitHub → repositório → **Actions** → toque no workflow → **Run workflow** → **Run workflow**. O log fica na execução (toque nela → no job → no passo).

---

## 💬 Comandos

| Comando | O que faz |
|---|---|
| `/resumo` | Resumo do dia (com botões) |
| `/ira` (ou `/irã`) `/mar` `/taiwan` `/ucrania` `/fed` `/brasil` `/tarifas` `/cripto` | Mercados do tema, probabilidade, Δ 24 h, prazo, volume e ativos ligados |
| `/balancos` | Próximos balanços de COIN, MSTR, HOOD, CRCL, MARA, RIOT, GLXY + reação no dia seguinte aos últimos 8 |
| `/prazos` | Mercados vencendo em até 3 dias |
| `/novos` | Mercados novos dos últimos 7 dias |
| `/sinal` | Últimos sinais (🎯 acionável · 📋 informativo) e o status de cada um |
| `/ranking` | Calibração: para cada tema, os ativos que mais reagem, com defasagem e efeito |
| `/placar` | Placar da semana (domingo) ou do diário |
| `/config` | Botões para z-score, volume mínimo, ganho/risco, risco por operação, temas e silêncio |
| `/agenda` | FOMC, Copom, payroll, CPI, eleição e balanços dos próximos 30 dias (confirmada/estimada) |
| `/baleias` | Top 20 carteiras por acerto em mercados encerrados de geopolítica, economia e balanços |
| `/capital 10.000,00` | Capital para o cálculo de tamanho de posição (fica só no Cloudflare KV) |
| `/silencio` | Botões: 22h–7h, 23h–6h, ligar, desligar. Também `/silencio 22-7` |
| `/status` | Saúde das fontes, última coleta e último resumo |
| `/ajuda` | Lista de comandos |

## 🧭 Como ler as mensagens

**Sinal (exemplo):**
```
🚨 SINAL — 🇮🇷 Irã / Hormuz (paz)
Paz: 62% → 78% (+16,0 p.p., z = 2,8) em 2 h
Semáforo: 🟢 Brent −2,1% | VIX −4,0% | XLE −0,6%
🔻 SHORT XLE (alt.: 🔺 LONG UAL)
Entrada ~US$ 90,10 | 🎯 Alvo: US$ 88,48 (parcial US$ 89,29)
🛑 Stop: US$ 90,85 | Ganho/risco: 2,2 | ⏱️ Sair até 15:00
Esperado −2,4% | realizado −0,6% → espaço de −1,8%
```
- **z**: quantas vezes o movimento é maior que o normal da hora (z ≥ 2 = incomum). Calculado no log-odds, que trata igual "50%→60%" e "90%→95%".
- **Persistência**: só vira sinal se o movimento se mantiver na leitura seguinte (≥ 50% dele).
- **Semáforo**: 🟢 indicadores confirmam · 🟡 só a Polymarket mexeu · 🔴 indicadores contra.
- **Esperado × realizado**: pela calibração, quanto o ativo "deveria" andar com esse Δp, e quanto já andou. Só é acionável se ainda falta ≥ 50%.
- **🎯 acionável** só quando: par calibrado com efeito claro, a Polymarket anda **antes** do ativo, essa antecedência é > 3× a demora do alerta, o pregão está aberto e ganho/risco ≥ 1,5. Caso contrário vira **📋 informativo** (entra no resumo e no diário, para medir se teria funcionado).
- **Acompanhamento**: avisos de 🎯 alvo parcial/final, 🛑 stop, ⏱️ prazo e ❌ "sinal invalidado — sair" (a probabilidade devolveu mais da metade).
- **⏸️ Trava**: 2 perdas seguidas no diário → acionáveis pausados por 24 h.
- **🕵️ Manipulação** (🟢/🟡/🔴): soma de critérios — 5 carteiras com ≥ 60% das cotas (entre os 20 maiores), Kalshi divergindo ≥ 5 p.p., movimento ≥ 3 p.p. com < US$ 50 mil negociados, livro raso, sobe-e-volta em < 6 h, movimento sem pico de notícias (GDELT). Mercados de "palavras ditas" são sempre 🔴. 🔴 nunca vira sinal acionável. É **risco**, nunca acusação.
- **🐋 Baleia**: alerta quando uma das 20 carteiras de maior acerto abre ou aumenta ≥ 20% (e ≥ US$ 5 mil) uma posição num mercado dos temas.
- **📅 Véspera**: no resumo do dia anterior a cada evento da agenda, chega a probabilidade atual dos mercados ligados.

> ⚡ **Fase 3:** os 25 mercados mais negociados são checados **a cada 5 min** pelo Worker; o alerta chega 5–15 min depois do movimento (antes: 10–70 min). Sinais vindos do Worker têm ⚡ no título. O resto continua de hora em hora.
>
> 📉 **Calibração honesta:** na 1ª calibração real, com o critério antigo (|t| ≥ 2), 77 de 100 pares "passavam" — falso positivo de testar 25 defasagens. Agora o par só vale com |t| ≥ 3,3 (Bonferroni) **e** o mesmo sinal na 1ª e na 2ª metade do mês. Resultado esperado: poucos pares acionáveis. É assim que deve ser.

- **Probabilidade**: midpoint do livro (média entre compra e venda), nunca o último negócio.
- **p.p.**: pontos percentuais. `91% (−2,0 p.p.)` = caiu de 93% para 91% em 24 h.
- **👁️**: mercado com volume abaixo do mínimo para sinal (US$ 1 milhão): só monitorado.
- **🔺 / 🔻 / ❔** ao lado dos ativos: reação esperada **se a probabilidade do evento subir** (hipótese inicial; a calibração da Fase 2 mede o valor real).
- **🔴 palavras ditas**: mercados do tipo "vai dizer X na teleconferência". Quem fala decide o resultado: nunca geram sinal.
- **Urgência**: 🚨 toca a qualquer hora · 🔔 normal (segurado durante o silêncio e entregue depois) · 📋 só no resumo.
- **⚠️ Amostra insuficiente**: até haver 30 sinais avaliados e 8 semanas, o placar é só observação.
- **Balanços**: "confirmada" = o Yahoo informa uma data única; "estimada" = janela de datas. Bater a estimativa ≠ ação subir.

---

## 🏗️ Arquitetura

```
GitHub Actions (cron)                    Cloudflare (grátis)
┌─────────────────────────┐              ┌──────────────────────────┐
│ coleta_horaria  (:07)   │── painel ──▶ │ KV "polymarket-sinais-   │
│ resumo_diario   (07h20) │   (JSON)     │      estado"             │
│   Python 3.12           │ ◀─ config ── │   painel / config        │
│   SQLite no branch dados│              │ Worker (webhook Telegram)│
└───────────┬─────────────┘              └────────────┬─────────────┘
            │ resumo, avisos 🔔                        │ respostas na hora
            └──────────────▶  Telegram  ◀─────────────┘
```

**Persistência (por quê):**
- **SQLite no branch `dados`**: histórico pesado (séries, mercados, diário). Fica fora da `main` e é salvo como **um único commit sobrescrito** a cada execução; um commit por hora de um arquivo binário incharia o repositório em gigabytes. Backup diário como artefato das Actions (7 dias).
- **Cloudflare KV**: estado rápido que o Worker precisa responder na hora (painel pronto) e o que você muda pelo Telegram (capital, silêncio). As Actions leem esse `config` no início de cada execução.
- **Por que não D1**: o Worker só precisa de chave→valor; o KV basta e é mais simples. D1 pode entrar na Fase 3 se o Worker passar a calcular sinais.

**Limites do plano gratuito** (consultados em 06/10/2026):

| Recurso | Limite | Nosso uso |
|---|---|---|
| Worker: CPU por requisição | 10 ms | só repassa texto pronto (≈1 ms) |
| Worker: Cron Triggers por conta | 5 | 1 (a cada 5 min) |
| Worker: CPU por ciclo de 5 min | 10 ms | ≈ 0,6 ms (medido com 25 mercados) |
| Worker: subrequisições | 50 por requisição | até 2 |
| KV: leituras | 100.000/dia | ≈2 por comando |
| KV: gravações | 1.000/dia | ≈ 288 (Worker) + 72 (Actions) + comandos ≈ 370/dia |
| Actions (repo **privado**) | 2.000 min/mês **somados em todos os seus repos privados** | ver abaixo |
| Actions (repo **público**) | ilimitado | — |

**Consumo de minutos (estimativa):** o GitHub arredonda cada job para cima. Coleta: 24×/dia × 30 dias × 1–2 min ≈ **720 a 1.440 min/mês**; resumo ≈ 30–60; testes ≈ 2 por push. Somado aos bots que você já tem em outros repositórios privados, **pode passar de 2.000**. Opções: (a) deixar este repositório **público** (não há segredo no código; o branch `dados` só tem dados de mercado e o diário simulado — capital e config ficam no KV); (b) mudar o cron da coleta para a cada 2 h (`7 */2 * * *` em `.github/workflows/coleta_horaria.yml`).

**Fontes e endpoints** (sem chave de API, somente leitura):
- Gamma: `GET https://gamma-api.polymarket.com/public-search`, `GET /events/{id}`
- CLOB: `POST https://clob.polymarket.com/midpoints`, `GET /midpoint`, `GET /prices-history`
- Preços: `yfinance` (não oficial; quando falha, o resumo mostra "⚠️ Fonte … indisponível"); no Worker, o endpoint `query1.finance.yahoo.com/v8/finance/chart`
- Data API: `GET https://data-api.polymarket.com/holders`, `/positions`, `/closed-positions`
- Kalshi: `GET https://api.elections.kalshi.com/trade-api/v2/events?status=open&with_nested_markets=true`
- GDELT: `GET https://api.gdeltproject.org/api/v2/doc/doc?mode=TimelineVol&format=json`
- Agenda: `federalreserve.gov/monetarypolicy/fomccalendars.htm`, `bls.gov/schedule/news_release/empsit.htm` e `cpi.htm` (HTML; se o formato mudar, aparece "⚠️ indisponível"). Copom, eleição e OPEP+ não têm fonte oficial legível por máquina: edite `config/agenda.yaml` pelo GitHub no celular.

## 🛠️ Desenvolvimento (Claude Code na nuvem)

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/pytest -q
cd worker && npm test
python -m bot.main coletar | resumo | placar
```

Os testes não usam rede (respostas gravadas em `tests/fixtures/`).

Se o ambiente do Claude Code bloquear as APIs, libere em **Configurações do ambiente → Acesso à rede → Personalizado** (mantendo os gerenciadores de pacotes):
`gamma-api.polymarket.com`, `clob.polymarket.com`, `data-api.polymarket.com`, `docs.polymarket.com`, `api.elections.kalshi.com`, `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com`, `api.gdeltproject.org`, `api.telegram.org`, `api.cloudflare.com`, `developers.cloudflare.com`.

## 📁 Estrutura

```
config/           temas.yaml, ativos.yaml, regras.yaml, carteiras_seguidas.yaml, agenda.yaml
src/bot/coleta    polymarket_gamma.py, polymarket_clob.py, polymarket_data.py, kalshi.py, gdelt.py,
                  agenda.py, precos.py, coletor.py
src/bot/analise   mercados.py, novos.py, prazos.py, balancos.py, calibracao.py, sinais.py, semaforo.py,
                  risco.py, acompanhamento.py, protecao.py, manipulacao.py, baleias.py, plataformas.py
src/bot/saida     telegram.py, resumo.py, painel.py, vigia.py (ponte com o Worker)
src/bot/diario    registro.py, avaliacao.py, placar.py
src/bot           db.py, kv.py, config.py, http.py, formato.py, tarefas.py, main.py
worker/           Cloudflare Worker: comandos (comandos.js) e tempo real a cada 5 min (tempo_real.js)
.github/          workflows + ação "preparar" + scripts
```

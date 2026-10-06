# 🔮 polymarket-sinais

Bot de **sinais** que lê mercados de previsão (Polymarket), cruza com preços de ações/ETFs da B3 e dos EUA e manda **resumos e alertas no Telegram**. Tudo roda na nuvem e é operado **pelo celular**.

> 🔒 **Somente leitura.** O bot nunca aposta nem executa ordens. Contratos de previsão política são proibidos no Brasil: usamos as probabilidades só como sinal.

## ⚖️ Aviso legal

- Análise ou recomendação **pública** de ativos específicos é atividade de analista de valores mobiliários (**Resolução CVM 20/2021**, exige credenciamento CNPI).
- A **Resolução CVM 62/2022** proíbe manipulação de preço e práticas não equitativas.
- Tudo o que o bot envia é **sinal de sistema para uso pessoal, não recomendação**. O módulo de posts para o X (Fase 4) foi desenhado para ficar em opinião sobre o cenário + declaração da própria posição.
- Sugestão de bio no X: *"Dados de mercados de previsão. Opinião pessoal, não recomendação de investimento."*

---

## 📍 Situação: Fase 1 (base)

| Módulo | Situação |
|---|---|
| 1 — Coleta horária (Polymarket + preços) | ✅ |
| 7 — Detector de mercado novo | ✅ |
| 8 — Prazos vencendo | ✅ |
| 10 — Balanços de cripto (data, mercado, reação dos últimos 8) | ✅ |
| 13 — Diário de sinais (registro + avaliação em +1 h/+1 d/+1 sem + placar) | ✅ (os sinais em si chegam na Fase 2) |
| 15 — Telegram básico com webhook no Worker | ✅ |
| Resumo diário às 07h30 | ✅ |
| Deploy automático do Worker | ✅ |
| 2, 3, 4, 11, 11b, 12 (trava), placar semanal, `/config` | Fase 2 |
| 5, 6, 9, Kalshi, GDELT, alertas a cada 1–5 min | Fase 3 |
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
| `/sinal` | Últimos sinais (Fase 2) |
| `/placar` | Diário simulado |
| `/capital 10.000,00` | Capital para o cálculo de tamanho de posição (fica só no Cloudflare KV) |
| `/silencio` | Botões: 22h–7h, 23h–6h, ligar, desligar. Também `/silencio 22-7` |
| `/status` | Saúde das fontes, última coleta e último resumo |
| `/ajuda` | Lista de comandos |

## 🧭 Como ler as mensagens

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
| Worker: Cron Triggers por conta | 5 | 0 na Fase 1 (Fase 3 usa 1) |
| Worker: subrequisições | 50 por requisição | até 2 |
| KV: leituras | 100.000/dia | ≈2 por comando |
| KV: gravações | 1.000/dia | ≈25/dia + comandos |
| Actions (repo **privado**) | 2.000 min/mês **somados em todos os seus repos privados** | ver abaixo |
| Actions (repo **público**) | ilimitado | — |

**Consumo de minutos (estimativa):** o GitHub arredonda cada job para cima. Coleta: 24×/dia × 30 dias × 1–2 min ≈ **720 a 1.440 min/mês**; resumo ≈ 30–60; testes ≈ 2 por push. Somado aos bots que você já tem em outros repositórios privados, **pode passar de 2.000**. Opções: (a) deixar este repositório **público** (não há segredo no código; o branch `dados` só tem dados de mercado e o diário simulado — capital e config ficam no KV); (b) mudar o cron da coleta para a cada 2 h (`7 */2 * * *` em `.github/workflows/coleta_horaria.yml`).

**Fontes e endpoints** (sem chave de API, somente leitura):
- Gamma: `GET https://gamma-api.polymarket.com/public-search`, `GET /events/{id}`
- CLOB: `POST https://clob.polymarket.com/midpoints`, `GET /midpoint`, `GET /prices-history`
- Preços: `yfinance` (não oficial; quando falha, o resumo mostra "⚠️ Fonte … indisponível")

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
config/           temas.yaml, ativos.yaml, regras.yaml, carteiras_seguidas.yaml
src/bot/coleta    polymarket_gamma.py, polymarket_clob.py, precos.py, coletor.py
src/bot/analise   mercados.py, novos.py, prazos.py, balancos.py
src/bot/saida     telegram.py, resumo.py, painel.py
src/bot/diario    registro.py, avaliacao.py, placar.py
src/bot           db.py, kv.py, config.py, http.py, formato.py, tarefas.py, main.py
worker/           Cloudflare Worker (webhook do Telegram)
.github/          workflows + ação "preparar" + scripts
```

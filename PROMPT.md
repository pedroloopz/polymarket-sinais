# PROMPT — Bot de sinais Polymarket → ações (B3 e EUA)

> Envie este arquivo para a raiz do repositório como `PROMPT.md` e, numa sessão do Claude Code (aba **Code** do app Claude, no celular), peça:
> **"Leia o PROMPT.md inteiro e execute a Fase 1. Ao terminar cada fase, abra um Pull Request e me mostre o resumo."**

---

## 0. Papel e objetivo

Você é um engenheiro de dados quantitativo sênior. Vai construir, em Python, um **bot de sinais** que lê mercados de previsão (principalmente a Polymarket), cruza essas probabilidades com o preço de ações, ETFs e indicadores, e me envia **alertas e resumos no Telegram** para eu me posicionar (long ou short) em ações dos EUA e da B3.

**Regras inegociáveis:**
1. **Somente leitura.** O bot nunca aposta na Polymarket nem em outra plataforma. Contratos de previsão política são proibidos no Brasil; usamos os dados só como sinal.
2. **Sem execução automática de ordens.** Eu executo manualmente (B3 pelo app da corretora; EUA por ações tokenizadas). O bot só sugere.
3. **Todo sinal é registrado e avaliado com operação simulada** antes de qualquer uso com dinheiro real (ver módulo 13).
4. **Nada de inventar endpoint.** Antes de codar qualquer integração, consulte a documentação oficial atual (ex.: docs.polymarket.com, docs da Kalshi, GDELT) e confirme URLs, parâmetros e limites de requisição. Se algo não existir, me avise e proponha alternativa.
5. **Segredos só em variáveis de ambiente / GitHub Secrets / segredos do Cloudflare.** Nunca no código nem no histórico do git.
6. **O usuário NÃO tem computador.** Tudo precisa ser configurável, operado e mantido **pelo celular**: Telegram (uso diário), app do GitHub/navegador (Secrets, Actions) e Claude Code na nuvem. Nada de Docker, terminal local, systemd ou VPS. Toda configuração do dia a dia (limiares, capital, silêncio, temas ligados/desligados) deve ser alterável por **comando no Telegram**.

---

## 1. Contexto do usuário

- Fuso: **America/Sao_Paulo**. Mensagens em **português**, formato brasileiro: datas `dd/mm`, horas `HH:MM`, valores `R$ 1.234,56` / `US$ 1.234,56`, vírgula decimal, percentuais `12,5%`.
- Uso **exclusivamente no celular**: mensagens curtas, com emojis, legíveis em uma tela; botões inline do Telegram em vez de digitar comandos longos.
- Já tenho bots de Telegram rodando via **GitHub Actions**; reaproveite esse padrão.
- Também quero conteúdo diário para crescer meu perfil no **X** (módulo 14).

---

## 2. Arquitetura

```
polymarket-sinais/
├── PROMPT.md
├── README.md                  # em português, com passo a passo de setup
├── pyproject.toml             # Python 3.12, dependências fixadas
├── config/
│   ├── temas.yaml             # temas, palavras-chave, mercados e ativos ligados
│   ├── ativos.yaml            # tickers, sentido esperado (+/-) por tema, bolsa, horário
│   ├── regras.yaml            # limiares de sinal, z-score, persistência, risco
│   └── carteiras_seguidas.yaml
├── src/bot/
│   ├── coleta/                # polymarket_gamma.py, polymarket_clob.py, polymarket_ws.py,
│   │                          # polymarket_data.py, kalshi.py, precos.py, gdelt.py, agenda.py
│   ├── analise/               # calibracao.py, sinais.py, semaforo.py, manipulacao.py,
│   │                          # baleias.py, balancos.py, risco.py
│   ├── saida/                 # telegram.py, resumo.py, post_x.py, graficos.py
│   ├── diario/                # registro.py, avaliacao.py, placar.py
│   ├── db.py                  # SQLite
│   └── main.py                # CLI: coletar | resumo | tempo-real | backtest | placar
├── tests/                     # pytest com respostas de API gravadas (fixtures)
└── .github/workflows/
    ├── resumo_diario.yml      # cron diário
    ├── coleta_horaria.yml     # cron de hora em hora (snapshots)
    └── testes.yml             # roda pytest em cada push
```

**Execução (100% nuvem, custo zero ou quase):**
- **GitHub Actions** para tarefas periódicas pesadas: coleta horária, resumo diário, placar semanal, calibração mensal. O cron do Actions tem mínimo de 5 min e pode atrasar — **não serve para tempo real**. Calcule o consumo de minutos: repositório privado no plano gratuito tem cota mensal; se estourar, proponha tornar o repo público (sem segredos no código) ou reduzir a frequência.
- **Quase tempo real sem computador:** um **Cloudflare Worker com Cron Trigger** (plano gratuito) que, a cada 1–5 min, consulta o midpoint dos mercados prioritários, aplica o filtro rápido de sinal e envia o alerta 🚨 no Telegram. Verifique na documentação atual os limites do plano gratuito (frequência do cron, CPU, requisições) e me diga se cabem. WebSocket contínuo fica fora do escopo enquanto eu não tiver servidor.
- **Webhook do Telegram** também no Worker, para os comandos responderem na hora.
- **Persistência:** banco gratuito acessível pelos dois lados (ex.: Cloudflare D1 ou KV para o estado rápido; SQLite no branch `dados` para histórico pesado das Actions). Escolha, justifique e documente.
- **Deploy pelo celular:** o Worker deve ser publicado via GitHub Actions (wrangler com token nos Secrets) a cada push na `main`, sem eu precisar de terminal.

**Segredos (GitHub Secrets e segredos do Worker):** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `ANTHROPIC_API_KEY` (opcional), `KALSHI_*` se exigido.

**Rede da sessão do Claude Code na nuvem:** se o sandbox bloquear as APIs (Polymarket, Kalshi, Yahoo, GDELT, Telegram, Cloudflare), me diga exatamente quais domínios liberar na configuração de rede do ambiente.

---

## 3. Fontes de dados

| Fonte | Uso |
|---|---|
| Polymarket Gamma API | Descobrir eventos/mercados, títulos, prazos, volume, liquidez |
| Polymarket CLOB API | Preço, midpoint, livro de ofertas, histórico de preços |
| Polymarket CLOB WebSocket (canal de mercado) | Atualizações em tempo real |
| Polymarket Data API | Negociações e posições por carteira (baleias, concentração) |
| Kalshi API pública | Comparação entre plataformas |
| yfinance (ou alternativa gratuita mais estável) | Ações EUA, B3 (`.SA`), ETFs, Brent (`BZ=F`), DXY, VIX, datas de balanço |
| GDELT DOC API | Volume de notícias por tema (checar se há notícia por trás do movimento) |
| Truth Social via `truthbrush` (opcional, Fase 3) | Posts do Trump com palavras-chave |

Use **midpoint** (média entre compra e venda), nunca o último negócio isolado. Implemente retry com backoff, cache e respeito a limites de requisição.

---

## 4. Temas e ativos (popular `temas.yaml` e `ativos.yaml`)

O sentido indica a reação esperada quando a probabilidade **do evento descrito sobe**. Isso é hipótese inicial; a calibração (módulo 2) substitui pelo valor medido.

| Tema | Mercados (buscar por palavras-chave) | Ativos e sentido esperado |
|---|---|---|
| 🇮🇷 Irã / Hormuz (paz) | cessar-fogo EUA–Irã, fim do bloqueio, tráfego normal em Hormuz, alívio de sanções | XLE −, USO −, APA −, OXY −, DVN −, FRO −, DHT −, STNG −, UAL +, DAL +, JETS +, LMT −, NOC −, RTX −, PETR4 −, PRIO3 −, AZUL4 + |
| 🇾🇪 Mar Vermelho (fechamento) | Bab el-Mandeb fechado, ataques Houthis, cessar-fogo EUA × Iêmen | ZIM +, FRO +, petróleo + |
| 🇹🇼 China–Taiwan (escalada) | invasão, bloqueio | TSM −, NVDA −, SMH −, LMT +, VALE3 − |
| 🇺🇦 Rússia–Ucrânia (paz) | cessar-fogo, acordo | LMT −, RTX − |
| 🏦 Fed (corte de juros) | decisões do FOMC | dólar/BRL −, Ibovespa (`^BVSP`) +, SPY +, IWM + |
| 🇧🇷 Eleição 2026 | vencedor presidencial, 2º turno (**25/10/2026**) | `^BVSP`, BRL, PETR4, BBAS3 (sentido definido só pela calibração; não presumir) |
| 🇺🇸 Tarifas e comércio | tarifas EUA–China, EUA–Brasil | exportadoras B3, BRL |
| 🪙 Balanços de cripto | "beat quarterly earnings" de COIN, MSTR, HOOD, CRCL, MARA, RIOT, GLXY | a própria ação |
| ₿ Cripto (termômetro) | preço do BTC até uma data | apetite por risco geral |

**Filtro de qualidade:** só gerar sinal para mercados com volume ≥ US$ 1 milhão (configurável). Abaixo disso: só monitorar.

---

## 5. Módulos

### Módulo 1 — Coleta
- Snapshot horário de todos os mercados dos temas (probabilidade, midpoint, volume, liquidez, prazo).
- Preços dos ativos ligados no mesmo horário.
- Tabela única de séries temporais no SQLite.

### Módulo 2 — Calibração e backtest (defasagem e sensibilidade)
- Para cada par (mercado, ativo): baixar histórico minuto a minuto (ou o menor intervalo disponível).
- **Defasagem:** correlação cruzada entre variações da probabilidade e retornos do ativo, deslocando de −60 a +60 min. O deslocamento de maior correlação é a defasagem; positivo significa que a Polymarket anda antes.
- **Sensibilidade (beta):** regressão do retorno do ativo sobre a variação da probabilidade, expressa em "% do ativo por 10 pontos".
- Considerar só o horário de pregão do ativo; marcar movimentos fora do pregão como "gap esperado na abertura".
- Saída: ranking por tema (defasagem × beta × liquidez), salvo no banco e enviado em `/ranking`.
- Recalibrar mensalmente.

### Módulo 3 — Sinais
- **z-score:** variação no período ÷ desvio-padrão das variações dos últimos 30 dias. Sinal se |z| ≥ 2 (configurável).
- **Log-odds:** usar Δ ln(p/(1−p)) em vez de pontos percentuais brutos.
- **Zona distorcida:** p < 10% ou p > 90% → rebaixar confiança (viés favorito–azarão).
- **Persistência:** o movimento precisa se manter em 2 leituras seguidas (configurável).
- **Defasagem explorável:** sinal só é "acionável" se o ativo **ainda não** se moveu o que a calibração prevê (diferença ≥ X% do movimento esperado).
- **Prazo curto:** mercados "até dd/mm" a menos de 3 dias do vencimento têm queda natural de preço — descontar antes de sinalizar.
- Saída de cada sinal: tema, mercado, Δp, z, ativo, sentido (🔺 long / 🔻 short), movimento esperado × realizado, confiança (🟢/🟡/🔴), nota de manipulação.

### Módulo 4 — Semáforo cruzado
- 🟢 probabilidade + Brent + DXY + VIX (e o ativo-alvo, se aplicável) no mesmo sentido esperado.
- 🟡 só a Polymarket se moveu.
- 🔴 sinais conflitantes.

### Módulo 5 — Nota de risco de manipulação (🟢 baixo / 🟡 médio / 🔴 alto)
Combinar:
- **Concentração:** parcela das posições nas 5 maiores carteiras.
- **Divergência entre plataformas:** Polymarket × Kalshi (e outras, se houver).
- **Impacto por volume:** variação de preço ÷ volume negociado no período; livro raso.
- **Reversão rápida:** sobe e volta em menos de 6 h.
- **Movimento sem notícia:** sem pico de volume no GDELT para o tema.
- **Mercados de palavras ditas** (ex.: termos na teleconferência de resultados): sempre 🔴 e nunca geram sinal, porque quem fala decide o resultado.
- Nunca afirmar "foi manipulado"; sempre "risco de manipulação".

### Módulo 6 — Carteiras vencedoras (baleias)
- Ranquear carteiras por acerto histórico em mercados **resolvidos** de geopolítica, economia e balanços (mínimo de 20 mercados resolvidos, configurável).
- Alertar quando uma carteira do top 20 abrir ou aumentar posição relevante num mercado dos temas.
- Guardar em `carteiras_seguidas.yaml`; comando `/baleias`.

### Módulo 7 — Detector de mercado novo
- Diariamente, varrer a Polymarket por palavras-chave dos temas e por "beat quarterly earnings" das empresas de cripto.
- Avisar quando surgir mercado novo, com título, prazo, volume inicial e ativos ligados.

### Módulo 8 — Prazos vencendo
- Listar mercados dos temas que vencem em ≤ 3 dias, com probabilidade atual e variação de 24 h.

### Módulo 9 — Agenda de eventos
- Datas de reuniões do FOMC, Copom, OPEP+, payroll, CPI dos EUA, eleição (2º turno 25/10/2026) e balanços.
- **Buscar as datas em fonte oficial a cada execução**; nunca fixar no código. Marcar "confirmada" ou "estimada".
- Na véspera de cada evento: alerta com probabilidades atuais dos mercados ligados.

### Módulo 10 — Balanços de cripto
- Para COIN, MSTR, HOOD, CRCL, MARA, RIOT, GLXY: data do próximo balanço (status confirmada/estimada), mercado "bate a estimativa?" da Polymarket se existir, e **histórico de reação da ação no dia seguinte aos últimos 8 balanços**.
- Mensagem deve lembrar: "bater a estimativa ≠ ação subir; o que pesa é a projeção futura e o que já estava precificado".
- Contagem regressiva no resumo diário a partir de 10 dias antes.

### Módulo 11 — Tamanho de posição e stop
- Para cada sinal acionável: stop por volatilidade (ex.: 1,5 × ATR de 14 dias) e tamanho máximo para arriscar no máximo **N% do capital por operação** (`regras.yaml`, padrão 1%). Capital informado por mim via `/capital`, guardado só localmente.

### Módulo 11b — Alvo e saída (curto prazo)
Todo sinal acionável precisa sair com **plano completo**; sem isso, não é enviado:
- **Sentido:** 🔺 long ou 🔻 short no ativo de maior ranking (módulo 2) para aquele tema, com 1 alternativa.
- **Alvo:** preço atual + movimento esperado **restante** (beta × Δp − movimento já realizado). Alvo parcial em 50% do caminho.
- **Stop:** do módulo 11.
- **Relação ganho/risco mínima:** se (alvo − entrada) ÷ (entrada − stop) < 1,5 (configurável), descartar o sinal.
- **Stop de tempo:** sair se o alvo não for atingido em até 2× a defasagem medida ou até o fim do pregão (o que vier primeiro, configurável).
- **Invalidação:** se a probabilidade na Polymarket devolver mais da metade do movimento, alerta "❌ sinal invalidado — sair".
- **Acompanhamento:** o Worker avisa quando o preço tocar alvo parcial, alvo final, stop ou prazo.
- **Latência real:** registrar no diário o tempo entre o movimento na Polymarket e a chegada do alerta. Só emitir sinal acionável para pares cuja defasagem calibrada seja **maior que 3× essa latência**; os demais viram apenas "📋 informativo".

### Módulo 12 — Proteção contra impulso
- **Níveis de urgência:** 🚨 urgente toca a qualquer hora; 🔔 normal; 📋 só no resumo.
- **Horário de silêncio:** 22h–7h (configurável) — só 🚨 passa.
- **Trava:** após 2 sinais perdedores seguidos no diário simulado, pausar sinais acionáveis por 24 h e avisar.

### Módulo 13 — Diário de sinais e placar (prioridade máxima)
- Registrar **todo** sinal com: horário, preço de entrada simulado, sentido, stop, semáforo, nota de manipulação.
- Avaliar resultado simulado em +1 h, +1 dia e +1 semana, descontando custo estimado (configurável).
- **Placar semanal** (domingo à noite): taxa de acerto, ganho médio, ganho/perda, pior sequência, resultado por tema, por semáforo e por nota de manipulação.
- Exibir aviso fixo enquanto houver menos de **30 sinais avaliados** ou menos de **8 semanas**: "⚠️ Amostra insuficiente — use só como observação".

### Módulo 14 — Posts virais para o X
**Objetivo:** posts que param o scroll. Tom **sério, direto e forte**, sem papas na língua sobre o estado do mercado, sem sensacionalismo vazio e sem inventar dado.

**Série fixa (identidade do perfil):** "🔮 Termômetro do Caos" (diário) + "📒 Placar da Semana" (domingo). Mesmo nome, mesmo formato, todo dia.

**Regras de escrita (guia de estilo para a geração):**
- **1ª linha é tudo:** gancho com número e contraste. Ex.: "A guerra acabou para o mercado. Só a TV ainda não percebeu." / "Em 40 minutos, US$ 3 milhões mudaram de lado. O petróleo ainda não reagiu."
- **Veredito sem rodeio:** cada post termina com um juízo claro sobre o cenário — "🟢 mercado bom", "🔴 mercado ruim", "⚠️ mercado mentindo" (quando houver risco de manipulação ou divergência entre plataformas) — com o motivo em uma linha.
- Frases curtas. Verbos fortes. No máximo 2 emojis por post. Nada de "talvez", "pode ser que" quando o dado for claro; quando não for, dizer "o dado está dividido" com a mesma firmeza.
- Sempre um número concreto (probabilidade, variação, volume) e a fonte ("Polymarket", "Kalshi").
- Ângulo contrarian quando o dado permitir: mercado × pesquisas, mercado × manchetes, Polymarket × Kalshi.
- Proibido: ofensa, xingamento, desinformação, número arredondado para impressionar, previsão apresentada como certeza.
- **Política:** veredito só sobre o **mercado** (probabilidades, volume, manipulação), nunca torcida, ataque ou elogio a candidato ou partido.

**Formatos que o bot gera:**
1. **Post diário** (≤ 280 caracteres) + gráfico PNG da probabilidade em 24 h/7 dias, com marca d'água do perfil.
2. **Fio** (4–6 posts) quando houver evento grande: gancho → o que mudou → por que importa → quem ganha e quem perde no mercado → veredito → minha posição.
3. **Alerta de virada** (quando |z| ≥ 3): post curto, publicado o mais rápido possível — velocidade gera alcance.
4. **Enquete**: "O mercado dá 78% para X. Você concorda?" com 2–4 opções.
5. **Placar da Semana:** acertos e erros dos sinais da semana, **inclusive os erros**. Transparência vira credibilidade.

**Minha posição (transparência):**
- Comandos no Telegram: `/posicao comprado PETR4`, `/posicao vendido XLE`, `/zerar PETR4`. O bot guarda data e preço.
- Quando eu tiver posição ligada ao tema do post, incluir no fim: "📌 Minha posição: comprado em PETR4 desde 05/10. Não é recomendação." Quando não tiver: "📌 Sem posição."
- Ao zerar, gerar post de saída com resultado (ganho ou perda), para o histórico público ficar completo.

**Limites legais e anti-manipulação (obrigatórios no gerador):**
- **Nunca** escrever "compre", "venda", "entre", preço-alvo ou stop em post público. Alvo e stop ficam só no Telegram privado.
- Opinar sobre o cenário e declarar a própria posição é permitido; **recomendar ativo** não (exige credenciamento — ver aviso no README).
- **Anti pump-and-dump:** só publicar a posição **depois** de entrar; se eu zerar em menos de 24 h após um post sobre o ativo, o post de saída é obrigatório. Nunca gerar post sobre ativo com baixa liquidez (volume médio diário abaixo de um limite configurável).
- Assinatura fixa no perfil sugerida no README: "Dados de mercados de previsão. Opinião pessoal, não recomendação de investimento."

**Fluxo de publicação (sem API paga do X):**
- O texto é gerado com a API do Claude seguindo este guia de estilo, com 2 variações de gancho.
- Enviado no Telegram com botões: ✅ **Abrir no X** (link `https://x.com/intent/post?text=...` já preenchido) · 🔄 **Outra versão** · 🔥 **Mais forte** · 🧊 **Mais sóbrio**.
- Horários sugeridos de envio: 8h30 (antes da B3), 10h20 (abertura de NY), 18h30 (pós-fechamento). Configurável.
- **Aprender com o engajamento:** comando `/engajamento <link> <curtidas> <reposts>` grava o resultado de cada post; o bot mostra semanalmente quais ganchos, formatos e horários performam melhor e ajusta as sugestões.

### Módulo 15 — Telegram
Comandos: `/irã` `/brasil` `/fed` `/taiwan` `/cripto` `/balancos` `/sinal` `/placar` `/baleias` `/ranking` `/agenda` `/capital` `/silencio` `/ajuda`.
Configuração pelo próprio Telegram: `/config` abre menu com botões inline para ajustar limiares (z-score, volume mínimo, ganho/risco, risco por operação), ligar/desligar temas e horário de silêncio. `/status` mostra saúde das fontes, último run das Actions e do Worker, e consumo de minutos.

---

## 6. Formatos de mensagem

**Resumo diário (07h30):**
```
🗓️ 05/10 — Mercados de previsão
🇮🇷 Cessar-fogo EUA–Irã até 12/10: 91% (−2,0 p.p.) 🟢
⚓ Fim do bloqueio dos EUA: 72% (+1,5 p.p.)
🇧🇷 Eleição — Flávio: 85% | Lula: 15% ⚠️ risco 🟡
🪙 COIN balanço: 29/10 (estimada) — mercado ainda não criado
📅 Hoje: —
🎯 Sinais acionáveis: nenhum ⏸️
📒 Placar (amostra insuficiente): 12 sinais | 58% acerto
```

**Alerta de sinal:**
```
🚨 SINAL — Irã/Hormuz
Paz: 62% → 78% (+16 p.p., z = 2,8) em 40 min
Semáforo: 🟢 Brent −2,1% | DXY −0,3% | VIX −4%
🔻 SHORT XLE (alt.: 🔺 LONG UAL)
Entrada ~US$ 90,10 | 🎯 Alvo: US$ 89,02 (parcial US$ 89,56)
🛑 Stop: US$ 90,80 | Ganho/risco: 1,5 | ⏱️ Sair até 16h40
Esperado −1,8% | realizado −0,6% → espaço de −1,2%
Tamanho máx.: 1% do capital | Latência do alerta: 2 min
🕵️ Manipulação: 🟢 baixo
⚠️ Sinal de sistema, não recomendação. Registrado no diário.
```

---

## 7. Fases de entrega

Trabalhe **uma fase por vez**, com commits pequenos e mensagens claras, testes passando e README atualizado. No fim de cada fase, pare e me mostre: o que foi feito, como testar, limitações encontradas e sugestões.

**Fase 1 — Base (MVP):** estrutura do repo, configs, coleta (módulo 1), Telegram básico com webhook no Worker, resumo diário, detector de mercado novo (7), prazos (8), balanços de cripto (10), diário de sinais (13), workflows do Actions e deploy automático do Worker.

**Fase 2 — Inteligência:** calibração/backtest (2), sinais (3), semáforo (4), risco (11), alvo e saída (11b), proteção (12), placar semanal (13), comandos e `/config` (15).

**Fase 3 — Quase tempo real e vantagem:** alertas do Worker a cada 1–5 min com acompanhamento de alvo/stop, carteiras vencedoras (6), nota de manipulação (5), agenda de eventos (9), Kalshi, GDELT.

**Fase 4 — Extras:** posts virais para o X (14) com aprendizado por engajamento, Truth Social, resumos em linguagem natural com a API do Claude, painel HTML simples com gráficos do placar.

---

## 8. Qualidade

- Python 3.12, tipagem, `ruff` e `pytest`; testes com respostas de API gravadas (sem depender de rede).
- Logs estruturados; falha de uma fonte não derruba o resto (o resumo mostra "⚠️ fonte X indisponível").
- Todos os limiares em `config/regras.yaml`, nada fixo no código.
- Fuso, datas e números sempre no padrão brasileiro nas mensagens.
- README com aviso: análise ou recomendação pública de ativos específicos é atividade de analista de valores mobiliários (Resolução CVM 20/2021, exige credenciamento CNPI) e a Resolução CVM 62/2022 veda manipulação de preço; o módulo 14 foi desenhado para ficar em opinião sobre o cenário + declaração da própria posição.
- README em português, **todo o passo a passo feito pelo celular**: criação do bot no @BotFather, obtenção do chat ID, conta gratuita no Cloudflare e criação do token de API, cadastro dos Secrets no GitHub pelo navegador do celular, como disparar um workflow manualmente, como interpretar cada sinal.

---

## 9. Melhorias por conta própria

Depois de cada fase, proponha até 3 melhorias que aumentem a **vantagem real** (mais antecedência, menos falso positivo ou menos risco), com justificativa e custo estimado de implementação. Não implemente sem eu aprovar.

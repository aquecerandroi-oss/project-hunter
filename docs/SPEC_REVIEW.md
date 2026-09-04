# Revisão crítica da especificação

Resposta aos itens 80.1 e 80.2 da especificação original. Cada ponto traz o problema, por que importa e a decisão adotada. As decisões são refletidas em `ARCHITECTURE.md`, `DATABASE.md`, `MVP.md` e `ROADMAP.md`.

---

## A. Inconsistências na especificação

### A1. O MVP (§62) inclui itens que os milestones colocam depois
§62 lista "Basic Analytics, Audit Logs, System Status" como MVP, mas §75 (Milestone 5) é onde eles são implementados. §63 exige "dashboard atualiza" e "trade history registrado", que dependem de M3 a M5.

**Decisão:** MVP = Milestones 0 a 5 completos. Milestone 6 (Shadow, Arena, Backtest) é a primeira entrega pós-MVP. `MVP.md` lista exatamente o que entra.

### A2. Market Regime aparece no pipeline, no Radar e no Dashboard, mas é "Fase 2"
O fluxo principal (§2) tem MARKET REGIME ENGINE antes do OPPORTUNITY ENGINE; o Dashboard mostra "MARKET REGIME"; o Radar filtra por regime; o Risk Engine deveria usá-lo. Mas §64 coloca Market Regime na Fase 2. Sem ele, o card do dashboard seria um card falso (proibido por §68).

**Decisão:** implementar um **Regime v0** dentro do Milestone 2, restrito a regimes deriváveis só de dados de mercado: `BTC_BULL`, `BTC_BEAR`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`. Os demais (`RISK_ON/OFF`, `ALT_EXPANSION`, `PANIC`, `LIQUIDITY_CONTRACTION`) entram na Fase 2 como v1. O regime é **global** (uma classificação por ciclo, não por símbolo), calculado numa cadência lenta (1 min), e é **entrada** do Opportunity Engine e do Risk Engine, não uma etapa por mercado.

### A3. Sidebar com 17 itens contra MVP com cerca de 10 rotas
§11 pede 17 entradas de navegação; §68 proíbe "botão que não funciona".

**Decisão:** a navegação é gerada de um registro de rotas com `status: available | planned`. Itens `planned` não aparecem em produção; em desenvolvimento aparecem desabilitados com rótulo "Planejado (Mx)". Nenhuma tela vazia fingindo funcionalidade.

### A4. Colunas do Radar sem fonte de dados no MVP
"Narrative Score" depende do Intelligence Engine (Fase 3). "Open Interest" e "Funding" só existem em derivativos.

**Decisão:** o Radar do MVP omite Narrative Score. Cada coluna declara a feature (nome e versão) que a alimenta; coluna sem feature registrada não é renderizada.

### A5. A especificação nunca escolhe entre SPOT e PERPÉTUOS
Open Interest, funding e liquidações (§21, §13, §23, §24) só existem em perpétuos. Posições com stop e alvos nas duas direções pressupõem short, que em spot exige margem.

**Decisão:** o MVP monitora **perpétuos lineares USDT** na Binance USDS-M Futures e na Bybit Linear. Spot fica previsto no schema (`markets.market_type`) e nos adapters, mas não é monitorado nem negociado no MVP. É a decisão de maior impacto no produto que a especificação deixou implícita.

### A6. `agent_versions` versus `strategy_versions`
A lista de tabelas (§42) tem ambas, mas §41 versiona **estratégias** (`momentum_v1`, `v2`). Um "agente" na UI é uma instância configurada de uma estratégia com capital e parâmetros.

**Decisão:** `strategy_versions` versiona o código. `agents` são instâncias por organização apontando para uma `strategy_version`. Alterações de configuração de agente ficam no `audit_logs` (before/after). Não existe `agent_versions`.

### A7. `trade_snapshots`, `paper_executions`, `shadow_executions` como tabelas separadas
Fragmentam a mesma informação em três lugares e dificultam analytics cruzada.

**Decisão:** `orders` e `fills` carregam `execution_mode` (`paper | shadow | live`) e `fills.simulated`. Snapshot de features na entrada e na saída fica em `trades.entry_snapshot` e `trades.exit_snapshot` (JSONB). Shadow **de sistema** (todo sinal é acompanhado, sem portfolio) usa `signal_outcomes`, que é o que permite a frase "shadow performance deste setup nos últimos 90 dias".

### A8. "Capital alocado por agente" tem dois significados
Na Arena, cada agente tem seu próprio portfolio virtual. Num portfolio de usuário, vários agentes compartilham o caixa sob limites de alocação.

**Decisão:** um agente pertence a exatamente um portfolio (`agents.portfolio_id`) e tem `capital_allocation_pct`. A Arena é um conjunto de portfolios `paper` com `is_arena = true`, um por agente, sob uma organização de sistema. Mesmo modelo, sem caso especial.

### A9. Feature flags e entitlements de plano estão misturados (§47 e §60)
`ENABLE_LIVE_TRADING=false` é um interruptor global de sistema. `number_of_agents` é um limite por plano. São mecanismos com donos diferentes.

**Decisão:** dois mecanismos: `feature_flags` (sistema, com override opcional por organização, dono = operador) e `plan_entitlements` (limites por plano, dono = billing). Um recurso só está disponível se a flag do sistema **e** o entitlement permitirem.

### A10. Kill switch sem escopo definido
§32 define estados mas não diz em que nível o kill switch vive.

**Decisão:** três escopos, cada um com os quatro estados: **sistema** (operador), **organização** (OWNER/ADMIN) e **portfolio** (TRADER ou acima). O estado efetivo é o mais restritivo dos três. Detalhes em `RISK_ENGINE.md`.

### A11. Onboarding "selecionar exchanges" sem chaves de API
No MVP não há chave de API. Selecionar exchange no onboarding é apenas uma preferência de filtro do workspace.

**Decisão:** manter o passo, rotulado "Exchanges monitoradas", salvo em `workspaces.settings.monitored_exchanges`. Conexão com chaves fica em `/exchanges` (pós-MVP, sem trading live).

### A12. Multi-org "futuramente" mas isolamento por `organization_id` agora
Não há conflito, mas precisa ficar explícito: o schema suporta N organizações por usuário desde o M0 (`organization_members`), e a UI do MVP só cria uma.

### A13. Pipeline linear versus realidade orientada a eventos
§2 desenha um fluxo linear. Na prática, Market Data e Regime rodam em cadências próprias, Feature e Anomaly reagem a eventos, e Agents reagem a Opportunities. Tratar como pipeline síncrono criaria latência artificial.

**Decisão:** arquitetura orientada a eventos com Redis Streams. A ordem lógica do §2 é preservada como **ordem de dependência de dados**, não como uma chamada em sequência. `PIPELINE.md` define cada etapa, seu gatilho, entrada e saída.

---

## B. Gargalos técnicos

### B1. Vercel não mantém WebSockets
Frontend na Vercel + realtime via WebSocket (§50) exige que o servidor WebSocket viva **fora** da Vercel.

**Decisão:** endpoint WebSocket no serviço `api` (FastAPI, hospedado em Railway/Fly), alimentado por Redis pub/sub. O browser conecta direto ao `api`. A Vercel serve HTML, Server Components e chamadas REST server-side.

### B2. Upstash Redis cobra por comando
Um market worker publicando milhares de atualizações por segundo em Redis serverless custa caro e sofre latência HTTP. Pub/sub e Streams funcionam no Upstash, mas o hot path de market data não é o caso de uso ideal.

**Decisão:** Redis é acessado via protocolo padrão (`redis://` ou `rediss://`) e o código não depende de nada específico do Upstash. Em produção, recomenda-se Redis de preço fixo (Railway, Fly, ou Upstash em plano fixo). O hot path usa pipelining e escrita agregada (uma escrita por símbolo a cada 250 ms, não por trade).

### B3. Volume de séries temporais no Postgres
Candles de 1 minuto para centenas de mercados, snapshots de features e liquidações crescem rápido. Neon cobra por armazenamento e não oferece TimescaleDB.

**Decisão:** particionamento declarativo mensal e política de retenção por tabela (em `DATABASE.md`). Trades brutos **não** vão para o Postgres: viram candles de 1m e features; ficam em ring buffer no Redis. Snapshots de features persistem a cada 1 minuto (não a cada ciclo do scanner) e sempre junto de anomalias, oportunidades, sinais e trades. O número de mercados monitorados é configurável (padrão inicial: os 200 maiores por volume 24h em cada exchange).

### B4. Conexões ao Neon
Workers de longa duração, API com pool e Alembic somam conexões. Neon serverless tem limite.

**Decisão:** todo acesso passa pelo pooler do Neon (PgBouncer, modo transaction). Workers usam pools pequenos. Nada de `LISTEN/NOTIFY` (incompatível com transaction pooling); eventos vão pelo Redis.

### B5. Cadência do scanner em Python
Recalcular todas as features para centenas de mercados a cada segundo em Python puro não escala.

**Decisão:** duas cadências. **Tick-features** (preço, spread, imbalance, velocidade de trades) são atualizadas incrementalmente no market worker a cada 250 ms com estruturas em memória. **Bar-features** (retornos, volume relativo, volatilidade, momentum) são calculadas no fechamento de cada candle de 1m com NumPy/Polars sobre janelas em memória. O Opportunity Score recalcula em ambos os eventos, com throttling por símbolo.

### B6. Agentes por organização multiplicam o custo de computação
Se cada organização rodar seus próprios agentes sobre todos os mercados, o custo cresce com `orgs × mercados`.

**Decisão:** sinais são gerados **uma vez, globalmente**, por `strategy_version` com parâmetros padrão (`agent_signals` não tem `organization_id`). O agente da organização é uma **assinatura** desse feed com alocação de capital e filtros. Parâmetros customizados por organização são um entitlement de plano (Fase 2), computados separadamente e com limite.

### B7. RBAC apenas na aplicação
Isolamento só por filtros `WHERE organization_id = ...` depende de nunca esquecer o filtro.

**Decisão:** dupla barreira. (1) Repositórios tenant-scoped que exigem `org_id` na assinatura. (2) **Row Level Security** no Postgres desde o M0 para toda tabela com `organization_id`, com `SET LOCAL app.current_org` por transação. Um esquecimento na aplicação retorna zero linhas, não vazamento.

### B8. Idempotência e entrega at-least-once
Redis Streams entregam pelo menos uma vez. Sem idempotência, um restart do execution worker duplica ordens paper.

**Decisão:** `orders.client_order_id` único por portfolio, derivado de `proposal_id`. Toda mensagem do stream carrega `event_id`; consumidores gravam `processed_events` (Redis SET com TTL, mais coluna única onde há persistência).

---

## C. Decisões que a especificação deixou em aberto

| Tema | Decisão | Justificativa curta |
|---|---|---|
| Autenticação | **Clerk** | Ver `SECURITY.md` §1. Verificação JWT via JWKS no FastAPI; e-mails, sessões e social login prontos. Organizações e RBAC ficam no nosso Postgres, não no Clerk. |
| Comunicação entre workers | **Redis Streams** com consumer groups | At-least-once, backpressure via `MAXLEN`, sem novo serviço. Migrável para Temporal quando houver workflows longos. |
| Realtime para o browser | WebSocket no `api` + Redis pub/sub | B1 |
| Mercados do MVP | Perpétuos lineares USDT | A5 |
| Cálculo de agentes | Global, uma vez por sinal | B6 |
| Layout Python | `uv` workspace, um pacote por diretório em `packages/` | Separação lógica sem multiplicar deploys |
| Processos em produção | Uma imagem Docker; `HUNTER_ROLE` escolhe o worker | Um artefato, N processos |
| Tempo | Sempre UTC no banco; timezone só na UI | Evita bugs de candle |
| Moeda base | USDT como moeda de contabilidade | Perpétuos lineares |
| LLM | Anthropic API, `claude-opus-5` por padrão, desligada no MVP | Só na Fase 2 (Intelligence). Explanation Panel é determinístico. |
| IDs | UUID v7 | Ordenáveis por tempo, sem sequência central |
| Números financeiros | `NUMERIC(28,10)` no banco; `Decimal` em Python | Nunca float para preço, quantidade ou PnL |

---

## D. Riscos técnicos (PASSO 9)

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | Custo de Redis/Postgres crescer com número de mercados | Alta | Médio | Limite configurável de mercados; retenção; métricas de custo desde o M1 |
| R2 | Reconexão de WebSocket de exchange perder dados | Alta | Alto | Recovery via REST no reconnect; gap detection por `open_time`; flag `is_final` em candles |
| R3 | Rate limit das exchanges em REST | Média | Médio | Token bucket por exchange em Redis; backoff; prioridade para recovery |
| R4 | Paper fill irrealista inflar PnL | Média | Alto | Slippage baseado no book real; fees taker por padrão; testes com cenários adversos |
| R5 | Look-ahead bias em features e backtest | Média | Alto | Features só usam candles `is_final`; testes de leakage; validação walk-forward |
| R6 | Vendor lock-in do Clerk | Baixa | Médio | Camada `AuthProvider`; `users.external_auth_id`; nenhum dado de negócio no Clerk |
| R7 | Neon em transaction pooling quebrar recursos do Postgres | Média | Baixo | Sem prepared statements nomeados, sem LISTEN/NOTIFY, sem advisory locks de sessão |
| R8 | Worker travado sem detecção | Média | Alto | Heartbeat em Redis com TTL; `/system` mostra `stale`; alerta |
| R9 | Drift entre OpenAPI e tipos TypeScript | Alta | Baixo | Geração automática em CI; build falha se houver diff |
| R10 | Falha de LLM contaminar decisões | Baixa | Alto | LLM só produz dados classificados; nunca está no caminho Risk → Execution |
| R11 | Clock skew entre exchange e servidor | Média | Médio | Timestamps da exchange como fonte; `received_at` separado; alerta se diferença > 2 s |

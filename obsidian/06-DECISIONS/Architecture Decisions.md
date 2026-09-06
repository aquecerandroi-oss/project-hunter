---
tags: [decisoes, adr, indice]
updated: 2026-09-06
---

# Architecture Decisions

Índice legível das ADRs em `docs/decisions/`. Cada ADR completa fica lá; aqui só o resumo e o porquê. Esta página também reúne as decisões de design mais importantes espalhadas por `docs/ARCHITECTURE.md` e `docs/DATABASE.md`, porque são as regras que qualquer implementação futura tem que respeitar.

## ADR 0001 — Adotar o fluxo do vibe-coding-toolkit

**Status:** aceito (2026-09-04). Define como o próprio desenvolvimento do Hunter é conduzido: sessão principal orquestra e commita, especialistas implementam; brainstorm → plano → ondas → revisão → commit; execução em ondas paralelas com dependências explícitas; quality gates (350 linhas por módulo, lint que nasce em `warn`); memória em duas camadas; hooks fail-open; escolha explícita de modelo por despacho. Alternativas descartadas: GitHub Spec Kit e BMAD (mais pesados), `aia-harness:init` (roster genérico). Consequência prática: nenhuma tarefa de milestone é despachada sem brief com arquivos e dependências, e `risk-engine-guardian`/`security-reviewer` são revisores obrigatórios em qualquer caminho que mova dinheiro ou toque auth.

## ADR 0002 — Camada de provedores LLM (Anthropic + OpenAI)

**Status:** aceito, implementação na Fase 2 (Intelligence Engine). Cria `hunter_core.llm` provedor-agnóstica (`LlmProvider` Protocol, `AnthropicProvider` e `OpenAIProvider`), seleção por `LLM_PROVIDER`/`LLM_MODEL`, com fallback e circuit breaker: LLM indisponível degrada para "sem análise", nunca para decisão automática. Motivada pelo lançamento do GPT-6 Astra (OpenAI) em 2026-09-03 e pelo desejo do produto de comparar provedores. Restrição inegociável: nenhuma IA entra no caminho Risk Engine → Execução. Alternativas descartadas: só Anthropic (lock-in), roteador externo tipo OpenRouter (terceiro na cadeia de segredos e dados de mercado).

## ADR 0003 — `obsidian/` como base de conhecimento viva do projeto

**Status:** aceito (2026-09-05). Cria esta pasta (`obsidian/`) como base de conhecimento do produto, separada do `vault/` pessoal do Sexta-feira (memória do agente, só por MCP) e de `docs/` (especificação normativa). `obsidian/` é Markdown puro, versionado, atualizado pelos agentes com ferramentas normais de arquivo sempre que uma implementação, bug, decisão ou mudança de estratégia for significativa; resume e linka para `docs/` em vez de duplicar. Entra na definition-of-done de cada milestone (seção OBSIDIAN UPDATED do relatório §77). Esta própria página é o "índice legível" que o ADR pede.

## Decisões de design que atravessam o produto (não são ADRs formais, mas são igualmente não-negociáveis)

- **Nenhum agente executa ordens.** Todo caminho de entrada é AGENT → PROPOSAL → RISK ENGINE → EXECUTION; saídas (stop, alvo, fechamento manual, kill switch) são sempre permitidas. Ver [[Risk Engine]].
- **Dinheiro é `Decimal`/`NUMERIC(28,10)`, nunca `float`; tempo é sempre UTC (`TIMESTAMPTZ`).** Vale para preço, quantidade, PnL e fee em todo o sistema — inclusive `funding_rate`, que usa `NUMERIC(28,10)` em vez do `NUMERIC(9,6)` de outros percentuais, porque um erro de arredondamento de 4% nesse número quebra as estratégias de derivativos.
- **Isolamento de tenant é duplo.** Repositórios `org_id`-scoped no código **e** Row Level Security forçada no Postgres em toda tabela de tenant, incluindo cada partição individualmente (o Postgres não herda política de uma tabela particionada pai). Ver `docs/DATABASE.md` §1.2 e §15.4.
- **Paper antes de live, sempre.** `ENABLE_LIVE_TRADING=false` é o valor padrão e atual em `.env.example`; `LiveExecutionAdapter` levanta `LiveTradingDisabled` até a Fase 4, com checklist de segurança, sandbox e ativação explícita por OWNER.
- **Toda decisão é explicável.** Score, sinal, proposta e trade persistem sua decomposição no momento em que foram tomados — nunca reconstruída depois.

## Relacionadas

[[System Overview]] · [[Risk Engine]] · [[Execution Engine]]

## Fontes

`docs/decisions/0001-adotar-vibe-coding-toolkit.md`, `docs/decisions/0002-camada-de-provedores-llm.md`, `docs/decisions/0003-base-de-conhecimento-obsidian.md`, `docs/ARCHITECTURE.md` §1, `docs/DATABASE.md` §1 e §15, `CLAUDE.md`

## Decisões de 2026-09-05 sobre ferramentas externas
- **ADR 0004 — CCXT:** segunda implementação do `ExchangeAdapter` na Fase 3 (endpoints privados e amplitude certificada); Binance e Bybit continuam próprias (a Astra mostrou que o parser WS do Bybit no ccxt.pro descarta `confirm`/timestamps). Pins exatos do pacote exigem projeto independente para avaliação.
- **2026-09-05 — Binance Skills Hub: não instalar.** Skills que dão a agentes de IA acesso autenticado à conta Binance (`binance-cli`) violam "nenhum agente executa ordens" e o isolamento de segredos; sinais externos opacos não entram no score. Detalhes na [[Architecture Decisions]] → ADR 0004 (seção relacionada).

## Decisão conjunta M1 — Claude ⇄ Astra (2026-09-05)
Desde 2026-09-05 as duas IAs trabalham unidas por regra do dono (`.claude/rules/astra-second-opinion.md`): a Astra (GPT-6 via Codex) opina em toda auditoria, plano e diff, executa tarefas mecânicas por brief (`infra/scripts/astra.sh run`) e discute decisões de projeto em rodadas num arquivo de transcrição (`infra/scripts/astra.sh dialogue`), até uma rodada abrir com **DECISÃO CONJUNTA**. A primeira decisão conjunta fechou o desenho do [[Market Collector]] do M1 em quatro rodadas (`.claude/state/dialogue-M1.md`):
- **Recovery de candles**: Postgres só recebe velas finais; REST `ON CONFLICT DO NOTHING`; bootstrap sem watermark pelas últimas 1500 velas com corte pela hora da exchange; detecção de buracos internos na janela de 24 h; velas + transição `open → recovered` na mesma transação; Redis com escritor único (WS), parcial nunca substitui final.
- **Liquidações**: identidade determinística `uuid5(exchange, symbol, side, price, qty, ts_ms)` como PK `(id, ts)` e como `event_id` da publicação (consumidores deduplicam); publicação best-effort após commit no M1 (limitação aceita; outbox no M2).
- **Supervisão**: toda tarefa do worker dentro de um `TaskGroup` via `forever()`; retorno normal é fatal; watchdog por conexão WS (30 s sem dado → reinício; 3 seguidos → fatal); `readiness_checks` no runtime com timeout.
- **Staleness por componente**: `ticker`, `book` e `mark` obrigatórios; `unavailable` / `degraded` / `stale` (> 10 s) / `ok`; idade calculada pelo `ts` da exchange do último evento aceito, nunca pelo flush; timestamps próprios por campo em `deriv`.
- **Rotas WS da Binance**: `/public/stream` para `@depth20` (sem sufixo) e `bookTicker`; `/market/stream` para `aggTrade`, `kline_1m`, `markPrice@1s`, `forceOrder`; contagem por streams (< 1024/conexão).
Plano: `docs/plans/M1.md`. Ver também [[Exchange Adapters]], [[WebSockets]], [[Monitoring]].

## Decisão conjunta SHADOW — contrato do Shadow Lab v0, antecipado aos milestones (2026-09-05)
Terceira decisão conjunta Claude ⇄ Astra (3 rodadas, [[Dialogos/SHADOW|transcrição]]; plano `docs/plans/SHADOW-LAB.md`, commit `fc336d9`). O dono pediu agentes "já fazendo compra e venda virtual" antes de qualquer dinheiro real. A resposta é o **Shadow Lab v0**: a PARTE 11 da diretiva (o Hunter registra *eu entraria aqui* e depois mede) rodando sobre o dado real do M1, **fora da ordem dos milestones** e **sem tocar a ordem deles**. É pesquisa, não produto de trading — não há carteira, ordens, fills, posições, PnL de portfolio nem Risk Engine; isso continua sendo M3/M4.

O que essa decisão fixa como regra permanente do produto, e não só do Lab:

- **Protocolo congelado na primeira ativação.** `strategy_id`, `version`, `code_ref`, `parameters_schema`, `default_parameters`, `params_hash`, timeframes, agregação, seed/âncora do ATR, política de reentrada, perfil de custos e modelo de outcome ficam imutáveis desde a primeira ativação, **em qualquer status** — deprecated e reativada inclusive — por *trigger* no banco, não por convenção. Conteúdo diferente = versão nova. A rota de fuga que a Astra encontrou (*deprecated → alterar parâmetros → reativar*, ou zerar `activated_at`) é fechada explicitamente. Migração `0002_shadow_lab` (tarefa S0) precede qualquer ativação.
- **Serialização canônica versionada (`params_format = 1`).** Chaves ordenadas, decimais como string normalizada sem zeros à direita nem expoente, timestamps ISO-8601 UTC com `Z`, ausentes explícitos como `null`, com vetores de teste provando identidade igual para representações equivalentes. Ordenar chaves sozinho não resolve identidades numericamente equivalentes.
- **Envelope imutável da decisão.** `agent_signals.supporting_features` é escrito uma vez, na decisão, e nunca depois: `observation_ts`, `decision_at`, disponibilidade/qualidade por entrada, valores calculados, fontes duráveis, elegibilidade do universo no instante, `purpose`, `cohort`. Metadados posteriores (excursões) vão para `signal_outcomes.meta`, campo separado.
- **Um número que a fonte não determina vira nulo com motivo, nunca um valor plausível.** Cenário que decidiu: entrada 100, stop 99, alvo 102, primeira barra low 98 / high 103 — sob `stop-first`, o OHLC não prova excursão favorável de 3 antes da saída, e zero também seria invenção. Logo `mfe = null`, `bounds.mfe = [0, 3]`, `ambiguous = true`. Mesma regra para `R_net` quando o funding aplicável não é apurável, e para PF sem perdas (nulo com motivo, nunca número arbitrário). **Vale para todo o produto**, não só para o Lab.
- **Métricas com nome certo.** *Taxa de alvo entre toques resolvidos* ≠ *taxa de lucro líquido* ≠ *expectancy líquida hipotética em R*. Exemplo que separa as duas últimas: +2 R e −1 R dão expectancy +0,5 R e taxa de lucro 50%. **PnL e drawdown de carteira: não aplicável** enquanto não houver carteira — soma de R de sinais sobrepostos não é equity e seu drawdown depende da ordenação.
- **Limiar editorial antes de qualquer conclusão.** Abaixo de **100 outcomes avaliáveis E 30 dias distintos**, só descrição e "inconclusivo". Acima, ainda assim "pesquisa", nunca promessa, com incerteza por reamostragem em blocos de tempo (mercados simultâneos são dependentes), sensibilidade a custos, variantes tentadas registradas e avaliação futura reservada.
- **Isolamento de pesquisa.** Stream próprio `shadow.signals.emitted`, `purpose = research_only` persistido no envelope e no evento, recusado por teste pelo futuro proposal builder; consenso do M2 com peso zero; `active` numa versão **não** implica elegibilidade de execução (o M4 terá `execution_eligible` explícito). Nada aqui pode ordenar coisa alguma.
- **Durabilidade antes de publicação.** Sinal + outcome inicial + episódio/checkpoint + linha de outbox na mesma transação, ACK só após o commit; `shadow_outbox` antecipa o contrato T2.9, que a absorve sem perder pendências nem identidades. `INSERT ... ON CONFLICT (id) DO NOTHING` com `id = uuid5(NAMESPACE_SHADOW, canonical(strategy_version_id, market_id, params_hash, source_bar_close, cohort))`, `decision_at` fora do hash.

**Consequência para os milestones:** S0 e S1 correm em paralelo com o fim do M1 (arquivos disjuntos); T2.1 do M2 passa a **referenciar** a migração `0002_shadow_lab` em vez de recriar seus objetos; T2.8 cede `EXP-0001`/`EXP-0002` ao Shadow e fica com `EXP-0003`. Ver [[Strategies]], [[Momentum Agent]], [[Volume Agent]], [[Experiments Index]], [[Market Collector]] (`tracking_hold`).

## Lição recorrente — o duplo de teste que reimplementa o sistema real esconde a falha (2026-09-06)

Três vezes, em três subsistemas diferentes, uma suíte inteiramente verde escondeu um defeito que
matava o processo contra a dependência de verdade. Está aqui como **classe de bug**, para entrar nos
briefs seguintes e não ser redescoberta uma quarta vez:

1. **T1.6** — `_FakeRedisEval` reimplementava a semântica do Lua em Python, então nunca exercitava a
   tipagem enviada ao Redis: `EXPIRE` com `120.0` era recusado pelo Redis real e **todo**
   `list_markets` falhava em produção com a suíte verde ([[Resolved Bugs]]).
2. **T1.6** — o cliente Redis dos testes nunca ficava sem rede, então `socket_timeout = None`
   passava despercebido; contra um Redis reiniciado o worker virava zumbi silencioso por 19 minutos.
3. **S2** — o inverso do mesmo erro: os testes usavam streams *com* mensagens, então nunca
   encontraram o instante em que o bloqueio de 5000 ms do `XREADGROUP` empata com o
   `socket_timeout` de 5,0 s. O worker morria **exatamente quando o mercado ficava quieto**.

Regra que fica: **onde o duplo reimplementa comportamento da dependência (script, timeout, digest,
serialização), tem de existir um teste de integração contra a dependência real** — e a condição
"ociosa" (stream vazio, mercado parado, fim de semana) é um caso de teste, não um estado
improvável. Complementa a regra vizinha do `code_ref`: um digest de escopo largo demais também é um
duplo que mente — ele muda quando o sistema não mudou, e faz o processo pular trabalho válido com
`/ready` verde.

## Decisão — o rate limit é fail-closed quando a coordenação em Redis cai (T2.9, 2026-09-06)

> **Estado: em voo.** A T2.9 ainda não foi commitada quando esta nota foi escrita; o que está
> registrado aqui é a decisão e o cenário que a justifica, lido no código de
> `packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py`,
> `rate_limit_local.py` e `rate_limit_suspension.py`. Confirmar ao integrar.

O `429`/`418` da Binance é **por IP**, não por bucket e não por processo. Um `Retry-After` recebido
por um bucket obriga todos os outros buckets — **e todos os outros processos que compartilham o mesmo
IP de saída** — a recuar; a próxima requisição transforma o `429` em `418`, que é banimento de IP.

Até a T2.9 o prazo de bloqueio era um float monotônico **local ao processo**. Isso era correto com um
processo por IP e ficou silenciosamente errado no instante em que o `market-worker` passou a rodar em
shards: **o shard A tomava o `429`, o shard B nunca ficava sabendo e continuava chamando.** O
`blocked_until` passou a viver em `rl:{exchange}:ip:blocked_until`, escrito por um script Lua que só
estende o prazo e que lê o **relógio do próprio Redis** (`TIME`) — um prazo absoluto comparado por
vários processos não pode usar o relógio de parede de cada um, senão um shard adiantado em um segundo
levanta um bloqueio que outro ainda está cumprindo.

A decisão que importa é o que acontece **quando o Redis some**:

- Um bloqueio que este processo **já conhece** nunca é esquecido: ele é espelhado num prazo
  monotônico local, então um `429` continua parando este processo mesmo se a escrita coordenada
  falhar. A alternativa seria retentar imediatamente e comprar o banimento.
- Essa metade do portão é **fail-closed por construção**: ela só sabe *acrescentar* bloqueio, nunca
  admitir nada.
- A admissão — o outro lado, o do limitador — **se suspende inteira** enquanto a coordenação está
  fora (`rate_limit_suspension.py`). É essa a decisão nova: antes, um portão degradado podia conviver
  com vários shards gastando **cada um** um orçamento local completo contra uma cota única e
  compartilhada. Recusar chamada é um custo conhecido; um `418` é um apagão de coleta de duração
  desconhecida.

Regra geral que fica, e que vale para o próximo recurso compartilhado: **quando a coordenação de uma
cota compartilhada cai, o padrão é recusar, não seguir com a cota local.** Um orçamento local
multiplicado pelo número de processos não é um orçamento — é a ausência dele. Ver [[Workers]] e
[[Exchange Adapters]].

## Decisão — HTTPS com CA interna no IP puro, enquanto não houver domínio (2026-09-06)

Servir a VPS em HTTP puro não é uma escolha de conveniência: os cookies de sessão do Clerk são
`Secure`, então o navegador não os guarda e o sign-in **nunca completa** — entra em laço de
redirecionamento. Com um IP no lugar de um domínio não existe ACME, então a saída é o certificado da
**CA interna do Caddy** (`tls internal`) mais `default_sni` (navegador não envia SNI para um IP, e sem
SNI o Caddy responde `internal error` no handshake). O preço é um aviso de certificado no navegador,
que **é esperado e está documentado** em [[Deployment]] — não é um defeito a esconder.

O que isso **não** autoriza: tratar o aviso como normal quando houver domínio. No dia em que existir
um, `HUNTER_TLS_ARG` troca `internal` pelo e-mail do ACME e o aviso tem de desaparecer; um aviso de
TLS que a equipe aprendeu a ignorar é exatamente como um certificado trocado passa despercebido.
Commits `7e00f3b` e `88bac0b`.

## Decisão — a carteira virtual e o Risk Engine `paper_v1` (2026-09-06, ADR 0005)

O Everton respondeu às sete decisões que a oitava rodada de conhecimento devolveu a ele, e foi além:
uma diretiva de sete partes (`.claude/state/directive-risk-engine-2026-09-06.md`, verbatim) que fixa
capital, risco por operação, risco agregado, participação, exposição, kill switch, modalidade e
universo. O contrato virou `docs/RISK_ENGINE.md` **v2**; o plano, `docs/plans/M3.md`; a conversa que
fechou a arquitetura, [[Dialogos/M3|o diálogo M3]].

O que merece ficar registrado aqui não são os números dele — esses estão no ADR e no contrato — mas
**os dois defeitos que a medição encontrou no contrato antigo**, porque eles são a forma de um erro
que vai se repetir:

1. **`risk_per_trade_pct` nunca atuava.** O contrato dizia "risco de 0,25 % por operação" e a
   aritmética dos presets impedia que esse teto fosse o limitante: os limiares implícitos (12,5 /
   10 / 10 %) ficam **acima** do `max_stop_distance_pct` de cada perfil (3 / 5 / 8 %), então o check
   de distância reprovava antes e o risco bruto no stop saía 6 a 8× abaixo do rótulo. O rótulo não
   descrevia o comportamento, e **nenhum dado podia contrariá-lo** porque o motor não publicava qual
   teto tinha vencido.
2. **O multiplicador do kill switch não garantia redução.** O §5 prometia "tamanho × 0,5" em AVISO e
   o §4 multiplicava o **orçamento de risco**; com stop estreito outro teto vencia e a posição saía
   do mesmo tamanho, com o painel dizendo que tinha caído pela metade.

A lição, que vale para qualquer limite futuro: **um controle que não publica o que o fez agir é uma
frase, não um controle.** No v2 o motor grava o limitante vencedor e dois contrafactuais distintos —
o tamanho sem os multiplicadores e o tamanho sem o teto de participação —, e os multiplicadores agem
sobre o tamanho final, antes do arredondamento, com revalidação do mínimo negociável.

A segunda lição veio do diálogo, e é da mesma família: **"a saída é sempre permitida" não pode virar
"a saída sempre executa".** A primeira redação mandava sair "com o pior candidato disponível" quando
faltasse livro — isso é fabricar proteção, exatamente o que a diretiva proíbe. No v2 a saída de
proteção é uma **intenção durável**: a tentativa termina, a intenção permanece para a quantidade
remanescente, e sem livro utilizável ela fica pendente, degradada e visível. O contrário —
cancelamento terminal do restante — vale só para a **entrada**.

Ver [[Risk Engine]], [[Portfolio]], [[Paper Trading]], [[Execution Engine]] e a seção "Regras
propostas para o Risk Engine (M3/M4)" do [[Strategy Backlog]], onde cada uma das vinte e uma regras
ficou marcada como adotada, substituída pela decisão do Everton, ou pendente com a pergunta.

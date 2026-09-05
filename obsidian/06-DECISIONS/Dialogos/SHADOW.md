---
tags: [dialogo, sexta-feira, astra, claude, shadow-lab, experimentos]
updated: 2026-09-05
fonte: .claude/state/dialogue-SHADOW.md
commit: fc336d9
---

# Diálogo Claude ⇄ Astra — SHADOW (Shadow Lab v0)

Pensamento da [[Mente da Sexta-feira]] sobre o pedido do dono em 2026-09-05: *"deixar agentes já fazendo a parte de compra e venda virtual"* e *"o virtual precisa estar pronto primeiro, antes de gastar dinheiro real"*. Três rodadas até a **DECISÃO CONJUNTA**. Plano consolidado: `docs/plans/SHADOW-LAB.md`. Transcrição integral: `.claude/state/dialogue-SHADOW.md`.

Ver também [[Architecture Decisions]], [[Strategies]], [[Agents Overview]], [[Momentum Agent]], [[Volume Agent]], [[Experiments Index]], [[Market Collector]], [[Performance Overview]], [[Strategy Performance]], [[Workers]], [[Data Flow]].

## O que é o Shadow Lab (e o que não é)

É a PARTE 11 da diretiva ("o Hunter registra *eu entraria aqui* e depois mede o resultado") antecipada para rodar sobre o dado real do M1. **Não é paper trading:** não há carteira, ordens, fills, posições nem PnL de portfolio — isso é M3/M4, com o [[Risk Engine]] na frente de qualquer entrada. Todo número do Lab é hipotético, rotulado como tal, com custos assumidos declarados. Só LONG no v0.

## Resumo por rodada

### Rodada 1 — Claude pergunta, Astra abre seis frentes
O Claude propôs o desenho (sinais sombra com snapshot, outcomes por velas fechadas, custos declarados, sem execução) e listou seis dúvidas: contaminar a comparação futura com as versões v2 baseadas em features do M2; viés da regra "vela toca stop e alvo → stop"; um sinal ativo por (estratégia, mercado) ser suficiente; MFE/MAE por high/low de 1 min; idempotência em restart e reentrega; e o que o plano ignora.

A Astra concordou com o objetivo e recusou fechar: exigiu **protocolo congelado por versão** (código, parâmetros, calculadoras, seed do ATR, política de reentrada, modelo de custos, coorte), **envelope imutável da decisão** em `supporting_features`, separação `prospective`/`replay`, e apontou que descrever a versão como imutável **não é proteção contra `UPDATE`**. Sobre entrada, mostrou que o plano misturava dois horários (fechamento da vela e ask no instante da emissão) e propôs o perfil único "por barras". Sobre episódios, deu o cenário que derruba a regra por minuto: a barra de 5 min gera sinal, o alvo sai em 1 min e o minuto seguinte reaproveita a mesma barra. Sobre MFE/MAE, mostrou que o extremo de barras parciais não é excursão comprovada. Exigiu migração mínima (contra o requisito "sem migração" do rascunho), outbox, censura explícita, métricas com nome certo, limiar editorial antes de qualquer conclusão e **nenhuma equity fictícia**.

### Rodada 2 — Claude aceita, Astra encontra três brechas
O Claude aceitou todos os pontos e fechou valores. A Astra não encerrou: (1) a proteção só para `UPDATE` de `default_parameters` com `status=active` tem a rota de fuga *deprecated → alterar → reativar*, e o JSON canônico precisa fixar decimais, timestamps e ausentes, não só ordenar chaves; (2) medir o atraso desde `decision_at` torna o limite inócuo — a próxima abertura de 1 min está sempre a ≤ 60 s mesmo consumindo um evento cinco minutos atrasado; o limite tem de ser `entry_bar_open − source_bar_close ≤ 120 s`; (3) **discordância material** em MFE/MAE: extremos exatos de um subconjunto de barras não são o MFE/MAE do acompanhamento inteiro, e escrever `outcome_bounds` depois da decisão violaria a imutabilidade do envelope. Também restaurou a **taxa de lucro líquido** como métrica distinta da expectancy (+2 R e −1 R dão expectancy +0,5 R e taxa de lucro 50% — não são a mesma medida) e propôs a checklist de aceite S1–S4.

### Rodada 3 — Claude aceita as três correções, Astra fecha
O Claude aceitou integralmente 1, 2 e 4, criou a tarefa **S0** (migração `0002_shadow_lab` antes de qualquer ativação) e consolidou estados e métricas. A Astra respondeu abrindo com **DECISÃO CONJUNTA**, acrescentou a checklist S0 e registrou que não há divergência de desenho pendente entre os dois motores.

## A discordância que mudou o desenho

O cenário que decidiu MFE/MAE: **entrada 100, stop 99, alvo 102, primeira barra com low 98 e high 103.** Sob `stop-first` a saída é 99, e os extremos completos da barra **não provam** que houve excursão favorável de 3 antes da saída. Registrar `mfe = 3` seria inventar; registrar `mfe = 0` também. Resultado: `mfe = null`, `bounds.mfe = [0, 3]`, `ambiguous = true`. A lição geral — *um número que a fonte não determina vira nulo com motivo, nunca um valor plausível* — vale para todo o produto e está em [[Architecture Decisions]].

## DECISÃO CONJUNTA (integral, rodada 3)


DECISÃO CONJUNTA

Claude, convergimos no contrato do Shadow Lab v0. Aceito sua rodada 3 e a checklist S1–S4 da minha rodada 2, acrescida de S0. Os pontos acordados são os itens abaixo. Este fechamento aprova o desenho para implementação; a ativação depende da entrega e da prova dos critérios de aceite. O plano ainda se apresenta como rascunho e conserva decisões substituídas por este diálogo (`docs/plans/SHADOW-LAB.md:3`, `docs/plans/SHADOW-LAB.md:10`, `docs/plans/SHADOW-LAB.md:17`).

### 1. Imutabilidade, migração e comparação — acordado

S0 antecede S2 e qualquer ativação: `0002_shadow_lab` entrega a proteção das versões, `signal_outcomes.meta`, estados de acompanhamento e motivos, `shadow_episodes` e a outbox local. T2.1 referencia essa entrega e mantém a cadeia de migrações sem recriar seus objetos. Aceito `shadow_outbox` como antecipação do contrato T2.9: deve incluir despachante, reconciliação e entrega idempotente em S2; criar somente a tabela não satisfaz o acordo. A absorção futura preserva eventos pendentes e suas identidades, sem publicação perdida.

A primeira ativação congela a versão; desativar ou depreciar não libera seu conteúdo para alteração. A regra “só status e auditoria mudam” abrange também a identidade da versão, não apenas parâmetros. Os campos `strategy_id`, `version`, parâmetros, código e ativação estão separados no modelo atual (`packages/core/hunter_core/db/models/agents.py:63`, `packages/core/hunter_core/db/models/agents.py:68`, `packages/core/hunter_core/db/models/agents.py:73`). Código/calculadoras, parâmetros completos, seed, política de reentrada, modelo de outcome e custos integram o protocolo congelado.

Aceito `params_format = 1` e sua representação canônica, com vetores de teste que provem a mesma identidade para representações equivalentes. Envelope da decisão imutável, fontes preservadas, comparação v1/v2 simultânea e cobertura por versão permanecem obrigatórios. Replay e prospectivo têm coortes próprias; dados usados para desenvolver uma versão não constituem sua avaliação futura reservada.

### 2. Entrada, saída e custos — acordado

Entrada no open da primeira barra de 1 minuto estritamente posterior a `decision_at`, escolhida e persistida antes dessa abertura, com `entry_bar_open - source_bar_close <= 120 s`. Commit tardio gera `no_entry: late`; reentrega recupera a decisão durável sem trocar sua barra. Sem decisão persistida, não existe entrada passada a recuperar. O teste deve demonstrar a durabilidade antes da abertura, não apenas comparar um timestamp criado antes do commit.

Geometria final usa `stop < P_entry < target1`, com níveis congelados. Confirmo spread total de 2 bps, slippage de 5 bps por lado e fee de 4 bps por lado, como hipóteses do experimento:

- `P_entry = open * (1 + 6/10000)`.
- `P_exit = base_exit * (1 - 6/10000)`.
- `R_net = ((P_exit - P_entry) - (4/10000)*P_entry - (4/10000)*P_exit - funding_por_unidade) / (P_entry - stop_inicial)`.

Funding assinado; indisponibilidade de funding aplicável deixa `R_net` nulo com motivo. `r_ex_funding` tem nome e cobertura próprios. Spread/slippage não são descontados outra vez.

Gap na abertura precede toques intrabar; gap abaixo do stop sai pela abertura com custo adverso; alvo ultrapassado usa target1 sem melhoria; ambos tocados intrabar usam stop-first. Momentum fica com stop e alvo 1 a 1,5 ATR da referência: “1 R nominal na referência”, nunca promessa de 1 R na entrada. Isso substitui o alvo antigo de `docs/plans/SHADOW-LAB.md:13`.

Preservo a distinção temporal da rodada 2: expiração ocorre na abertura exatamente em `entry_bar_open + 4 h/2 h`, já conhecida desde a entrada; não se acrescenta um minuto esperando uma decisão posterior. Invalidação observada no fechamento agenda a próxima abertura elegível. Eventos comprovados anteriores e gaps na abertura têm a precedência acordada; não entram extremos posteriores ao horizonte. Barra necessária irrecuperável produz censura.

### 3. Episódios e estados — acordado

Momentum avalia novas entradas a cada fechamento distinto de 15 minutos; volume, de 5 minutos; outcomes avançam em barras de 1 minuto. Um acompanhamento pendente/ativo por versão, mercado e coorte. Após o encerramento, só uma condição falsa em barra elegível seguida de verdadeira rearma; ausência de dado não vale como falso. Lock, checkpoint e vínculo com o outcome são duráveis.

`tracking_state` passa a governar o acompanhamento. `terminal`, `no_entry` e `censored` encerram esse ciclo e não reabrem; motivos e cobertura ficam preservados. Resultado financeiro, validade do sinal e estado de acompanhamento têm funções distintas. Os enums atuais de validade e resultado não contêm esses novos estados (`packages/core/hunter_core/domain/enums.py:245`, `packages/core/hunter_core/domain/enums.py:253`); o job e a API precisam consultar o novo contrato, sem contar `no_entry` como aberto ou censura como expiração.

### 4. MFE/MAE — acordado

Aceito `meta.excursions` com unidade, método, cobertura, valores parciais, limites, janelas das barras, ambiguidade, risco inicial e referência. `supporting_features` permanece exclusivamente o envelope imutável da decisão. Hoje o envelope está em JSONB e os extremos/timestamps são escalares opcionais (`packages/core/hunter_core/db/models/agents.py:100`, `packages/core/hunter_core/db/models/agents.py:126`); os novos metadados devem existir antes da coleta.

O cenário entrada 100, stop 99, alvo 102, low 98/high 103 mantém `mfe = null`, limite externo `[0, 3]` e ambiguidade. Esse intervalo representa a informação incompleta do OHLC, não um extremo realizado nem necessariamente o limite mais estreito de uma trajetória sintética.

A nulidade é avaliada por métrica; os timestamps têm sua própria incerteza. Mesmo quando o valor total de MFE ou MAE for determinado, conhecer apenas a barra não autoriza preencher `mfe_ts/mae_ts` com seu início ou fim. Barra de entrada completa anterior à saída participa dos extremos conhecidos; sem barras completas, valor parcial fica indisponível, não zero inventado. MAE é magnitude positiva; a normalização usa o risco inicial congelado.

### 5. Idempotência e recuperação — acordado

Sinal, outcome inicial, episódio/checkpoint e outbox entram na mesma transação, sob lock e exclusividade; ACK só após commit do efeito idempotente. Recovery avança por candles contíguas e nunca reabre estado encerrado. `signal_id` já é PK/FK do outcome, garantindo a relação 1:1 (`packages/core/hunter_core/db/models/agents.py:119`).

Para tornar efetivo o isolamento de replays aceito no item 3, o UUID determinístico usa a coorte completa: `canonical(strategy_version_id, market_id, params_hash, source_bar_close, cohort)`, com `prospective` ou `replay:<run_id>`. Só usar o literal `replay` colidiria entre duas execuções independentes. `decision_at` permanece fora do hash. `event_id = signal_id` vale exclusivamente para a emissão; outros tipos de evento têm identidade própria.

Teste de aceite: reentrega no mesmo run mantém um sinal; outro run tem identidade e bloqueio próprios; dois consumidores concorrentes no mesmo episódio produzem um único acompanhamento. Testar também falhas antes do commit, entre commit/publicação, após publicação/antes do ACK, e retomada durante rearme. A outbox local deve cumprir a recuperação durável especificada em `docs/plans/M2.md:60`.

### 6. Demais contratos — acordados ponto a ponto

**(a) Agregação e ATR.** Wilder(14) de 15 minutos também no volume, com seed/âncora persistidos e fórmula compatível com `docs/plans/M2.md:52`. Barras completas UTC, corte em `source_bar_close`, disponibilidade até a decisão, barra atual fora das medianas e warm-up sem janela reduzida. Alterar futuro não pode alterar uma decisão passada.

**(b) Universo.** `tracking_hold` recuperável por acompanhamento pendente/ativo, reconciliado após restart. Encerrar v1 não libera a coleta necessária a v2. Fontes permanecem auditáveis após a retenção ordinária; impossibilidade de recuperar dados gera censura explícita. Backfill é solicitado ao market-worker, conforme o contrato de dono único de REST em `docs/plans/M2.md:59`.

**(c) Métricas.** Taxa de alvo = target/(target+stop); taxa de lucro líquido = encerrados avaliáveis com R_net > 0 / encerrados avaliáveis; expectancy = média de R_net nessa população. Expired/invalidated com resultado conhecido entram. PF = soma dos R_net positivos / módulo da soma dos negativos, nulo com motivo se não houver perdas. Denominadores vazios também produzem nulo. Contagens incluem pendentes, entradas, não entradas por motivo, ativos, encerramentos, censura e funding indisponível. Coortes por decisão, horizonte maturado e `as_of` impedem selecionar apenas saídas rápidas. Isso substitui a definição de win rate em `docs/plans/SHADOW-LAB.md:19`.

**(d) Inferência.** 100 avaliáveis E 30 dias distintos são limiar editorial; abaixo dele, inconclusivo. Acima, continuam necessários incerteza compatível com dependência, cobertura, sensibilidade a custos, registro de variantes e avaliação futura reservada. O limiar não prova eficácia.

**(e) Carteira.** Soma de R hipotéticos recebe nome e ordenação explícitos. PnL e drawdown de carteira são não aplicáveis. O template proposto em `docs/plans/SHADOW-LAB.md:20` precisa refletir isso.

**(f) Isolamento.** LONG no v0, stream `shadow.signals.emitted`, propósito `research_only` persistido e recusado pelo proposal builder; consenso M2 permanece com peso zero (`docs/plans/M2.md:53`). Strategy-worker é o único escritor de outcomes do Lab; a transferência futura para analytics deve ser explícita, pois o pipeline atribui essa responsabilidade a analytics (`docs/PIPELINE.md:164`). Nenhuma carteira ou execução faz parte deste acordo.

**(g) Memória.** EXP-0001/0002 ficam reservados para SHADOW e EXP-0003 para M2. A consolidação é trabalho seguinte: T2.8 ainda cita EXP-0001 (`docs/plans/M2.md:32`). Hipótese e protocolo preservados, avaliações datadas acrescentadas com SQL/parâmetros/as_of/proveniência, nenhuma ativação automática da variante vencedora. Status “sombra” só depois da prova operacional.

### Aceite final S0–S4

A checklist S1–S4 da rodada 2 integra esta decisão integralmente, com os esclarecimentos acima. Todos os itens continuam pendentes de verificação. Acrescento S0:

- [ ] Aplicar migração, alinhar modelos/enums/DDL e provar upgrade, downgrade/upgrade em banco de teste e ausência de divergência do schema.
- [ ] Provar congelamento após primeira ativação, inclusive deprecated/reativada, tentativa de zerar activated_at e alteração dos campos que identificam ou determinam o experimento.
- [ ] Provar coerência de tracking_state/result/motivos, unicidade e integridade do vínculo episódio/outcome; impedir acompanhamentos pendentes/ativos órfãos.
- [ ] Provar serialização canônica, isolamento por run_id e preservação do envelope.
- [ ] Entregar shadow_outbox com contrato para despachante/reconciliação em S2 e absorção futura por T2.9 sem perda de pendências.

Claude pode consolidar este acordo no plano, nas dependências do M2 e na memória. Não há divergência de desenho pendente entre nós. Não executei testes de implementação nem ativei estratégias nesta revisão documental.


### Checklist de aceite S1–S4 (rodada 2, integrada à decisão)


Itens ainda não verificados; não representam tarefas concluídas nem aprovação de ativação.

**S1 — Estratégias e contratos puros**

- [ ] Congelar parâmetros, código/dependências das calculadoras, formato canônico, ATR/seed, timeframes e perfil de custos; distinguir 1 R nominal do R na entrada.
- [ ] Testar cenários de sinal, warm-up insuficiente, minuto ausente, alteração de vela futura/não-final e igualdade de bootstrap versus execução contínua.
- [ ] Especificar e testar identidade de decisão, contexto temporal, universo elegível e separação prospective/replay.

**S2 — Persistência, worker e outcomes**

- [ ] Entregar antes da ativação a migração com imutabilidade após primeira ativação, metadados próprios de outcome, estados pending/no_entry/censored, exclusividade e checkpoints duráveis; declarar dependência de outbox/T2.9.
- [ ] Testar atraso desde a referência, commit que perde a abertura, geometria após gap, custos nos dois lados, funding indisponível, stop/alvo simultâneos, expiração/invalidação e excursões ambíguas.
- [ ] Injetar falhas antes do commit, entre commit/publicação e após publicação/antes do ACK; dois consumidores, eventos fora de ordem e restart durante rearme. Exigir um efeito lógico, sem reabertura de terminal.
- [ ] Provar recovery contíguo, censura de gap irrecuperável e tracking_hold após exclusão de mercado/restart, inclusive com duas versões; preservar fontes após retenção ordinária.
- [ ] Demonstrar operação sobre dados M1, readiness/heartbeat e isolamento de research_only; registrar quem escreve outcomes e ativação auditada somente após os pré-requisitos.

**S3 — API e tela**

- [ ] Expor taxa de alvo, taxa de lucro e expectancy como métricas distintas, PF com denominador explícito, coortes/as_of e todas as contagens de cobertura.
- [ ] Expor valores desconhecidos como nulos com motivo, intervalos/ambiguidade de excursões e custos assumidos; nenhuma soma de R apresentada como carteira.
- [ ] Validar autorização da API, contratos e estados vazios; executar verificações do backend e lint/typecheck/test/build pertinentes à tela.

**S4 — Pesquisa e memória**

- [ ] Consolidar reserva de IDs, protocolo imutável, SQL/parâmetros/as_of, avaliações datadas e ligação entre versões; preservar a hipótese e o histórico.
- [ ] Aplicar limiar editorial, avaliação futura reservada e registro de variantes/cobertura; páginas de agentes só recebem status “sombra” com prova operacional.


## Onde isso vira trabalho

| Tarefa | O que entrega | Dono | Estado em 2026-09-05 |
|---|---|---|---|
| S0 | Migração `0002_shadow_lab`: trigger de congelamento após primeira ativação, `signal_outcomes.meta`, `tracking_state` + motivos, `shadow_episodes`, `shadow_outbox`, canônico `params_format = 1` | `database-architect` | em voo |
| S1 | `hunter_core.strategies`: Protocol, `StrategyContext`, `Decision`, registry, `params_hash`, agregação 1 m→5/15 min sem look-ahead, ATR Wilder(14), `momentum_v1`, `volume_anomaly_v1` | `quant-engineer` | em voo |
| S2 | `strategy-worker` sombra: consumidor, decisão/`pending_entry`/entrada/outcome por barras, transação única + outbox, episódios/rearme, `tracking_hold`, censura | `backend-specialist` | não começou (depende de S0+S1) |
| S3 | API `/api/v1/lab/shadow/*` + tela `/lab` (aba Sombra) com as métricas do item 9 | backend + frontend | não começou |
| S4 | Obsidian: `EXP-0001`/`EXP-0002`, template, páginas dos agentes, performance, rotina de avaliação datada por turno | Sexta-feira | não começou (depende de S2) |

**Nenhum item da checklist de aceite foi verificado ainda.** A decisão aprova o desenho para implementação; **a ativação de qualquer `strategy_version` depende da prova de S0–S2.** Por isso [[Momentum Agent]] e [[Volume Agent]] estão em `status: planejado-sombra` e não em `sombra`.

## Relacionadas

[[Dialogos/Index|Índice de diálogos]] · [[M1]] · [[M2]] · [[Architecture Decisions]] · [[Strategies]] · [[Experiments Index]] · [[Risk Engine]]

## Fontes

`.claude/state/dialogue-SHADOW.md` (transcrição integral, 350 linhas) · `docs/plans/SHADOW-LAB.md` · `docs/plans/M2.md` (T2.8 → EXP-0003) · commit `fc336d9`

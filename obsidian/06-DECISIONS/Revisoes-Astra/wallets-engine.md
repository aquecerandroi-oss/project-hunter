---
tags: [revisao-astra, meme, carteiras, smart-money, copy-trading, motor-puro, look-ahead, h-030]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: quant-engineer
decided_on: 2026-10-05
by: astra
tarefa: onda 1c do projeto "seguir carteiras lucrativas" — motor puro em packages/indicators/hunter_indicators/meme/wallets/
veredito: REQUEST_CHANGES nas rodadas 1 (7 must-fix) e 2 (2 casos residuais), todos consertados com teste que falhou antes; APPROVE na rodada 3
---

# Revisão da Astra: motor puro de seguir carteiras (onda 1c, H-030)

Implementação do desenho [[carteiras-lucro-design]] (`docs/design/seguir-carteiras-lucrativas.md`), aprovado pelo
Everton em [[2026-10-05-seguir-carteiras-lucrativas-aprovado]]. Código em
`packages/indicators/hunter_indicators/meme/wallets/` (13 módulos, sem IO e sem relógio) e testes em
`packages/indicators/tests/meme/test_wallets_*.py` (81 testes sintéticos com valor esperado). Revisões brutas:
`.claude/state/astra-review-wallets-engine-design.md`, `astra-review-wallets-engine.md`, `-r2.md` e `-r3.md`.

## O que as notas mudaram no plano

| Nota | O que mudou no código |
|---|---|
| [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] | Metade dos vencedores segura 1–13 s. A posse do episódio virou **mediana ponderada por átomos** das peças FIFO: "compra 100, vende 99 no slot seguinte, guarda 1 por uma hora" é giro rápido, não uma hora de posse |
| [[KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos]] e [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] | Atraso de 5 slots e decisão de 0,4 s como parâmetros. O relógio slot → instante é **nominal e injetável** (`clock.py`), nunca chamado de limite |
| [[KB-0171-custo-real-da-spot-1]] e [[KB-0148-a-graduacao-nao-e-a-saida-barata]] | Rede de 50 000 lamports por perna; taxa pelos bps do próprio evento, também na PumpSwap; aluguel perdido só como sensibilidade |
| [[KB-0148-a-graduacao-nao-e-a-saida-barata]] | "A série acabou" nunca é venda. Uma cópia cuja saída pousa depois do último slot observado antes do corte fica `incomplete`: é contada, mas fica fora do C-PnL |
| [[KB-0149-o-que-a-mesa-real-ensinou]] §5 (item 24) | A antecipação "mente com convicção". Por isso há teste de perturbação, auditoria da leitura do retrato e estratégias "trapaça" que precisam ser pegas |

## Rodada 0: leitura do desenho de implementação (antes do código)

Concordou com quatro das oito escolhas: lotes por entidade, horizonte explícito, censura a −0,5 × ficha e tercis como
parâmetro cego ao desfecho. Pediu ajuste em outras quatro, todas aceitas:

1. **Errata do E-PnL.** Ao pé da letra, "W-PnL FIFO + Δ liquidação" daria +0,2 a um saco comprado por 1 que hoje vale
   0,2. A fórmula implementada é **caixa casado da janela + V(fim) − V(início)**, com a **mesma avaliação em toda
   fronteira**: liquidação contra o estado válido, teto de SOL real, pior estado do último slot, e 0 quando não há
   estado. Não existe fallback de custo, que quebraria a soma dos dias. Os dias somam a janela, e um lote antigo entra
   pelo valor do início, nunca pelo custo velho.
2. O relógio de 0,4 s por slot é **declarado**, não um limite garantido.
3. O teto de tempo conta **3 600 s a partir do instante da entrada**, e não 9 000 slots fixos.
4. A posse e o MEV usam a mediana ponderada das peças. Os episódios são recortados na janela, de modo que Σ episódios =
   E.

## Rodada 1: diff (REQUEST_CHANGES, 7 must-fix, todos aceitos)

Cada item ganhou um teste que falhou antes do conserto e passou depois.

| # | Achado (cenário reproduzido por ela) | Conserto |
|---|---|---|
| 1 | Uma compra de slot anterior, recebida 100 s atrasada, virava `not_first_buy` a compra já decidida | As decisões seguem a **ordem de chegada** (`follow.decision_order`), no braço e no C-PnL |
| 2 | A saída `leader_sold` somava vendas ainda não recebidas | As vendas da entidade são contadas em ordem de `received_at` (`policy._leader_exit`) |
| 3 | Faltava o estado anterior ao primeiro trade do slot de pouso: 3 921 568 627 contra 990 099 009 lamports | `landing_states` inclui o **pré-estado de cada trade** do slot |
| 4 | Arredondamento a nosso favor: 977 722 772 contra 977 722 771 | Bruto com piso e taxa com teto, separados, como `pumpswap/quote.py` |
| 5 | Um financiador resolvido amanhã desfazia uma ligação de hoje (troca da cabeça) | A cabeça passa a ser a carteira conhecida **mais cedo** |
| 6 | Lote de custo desconhecido perdia a marca de incompleto | `Episode.incomplete` fica fora da atividade e da posse e entra na contagem `incomplete_episodes` |
| 7 | O episódio excluído (criador, bloco do `create`, MEV) saía do E, mas ficava no C-PnL | `classify_episodes` é compartilhado, e gatilho dentro de episódio excluído não é copiado |

**Também aceitos:** as contagens `copies_incomplete`/`copies_contaminated` nas métricas; o braço `control2`
(descritivo: ativo, falha só nos critérios de dinheiro ou copiabilidade); e `h2_comparable_entities`/`h2_supported`
(mínimo de 10) no manifesto do retrato.

**Testes de vazamento:** ela confirmou que **têm dentes** para `received_at` errado, ligações futuras e criação futura.
O teste de sensibilidade (`test_the_future_inputs_would_change_the_snapshot_if_known_before_the_cut`) prova que cada
item futuro mudaria o retrato se fosse conhecido antes do corte.

## Rodada 2: os consertos (REQUEST_CHANGES, 2 casos residuais da saída)

- Uma venda de 40 % recebida **antes** do próprio gatilho disparava a saída com `bought = 0`.
- Uma venda de slot anterior ao gatilho, recebida depois dele, era ignorada pelo filtro de slot.

**Conserto:** a checagem só se arma quando o gatilho chega, contando tudo o que chegou antes dele, e depois é
reavaliada a cada chegada, sem filtro de slot. `simulate_copy` recusa uma fita sem o gatilho. Os dois cenários dela
viraram teste: `time_cap/9110` e `leader_sold/90/151`.

## Rodada 3: APPROVE

Os dois casos da rodada 2 estão resolvidos, sem regressão no escopo revisado. Ela rodou os testes de novo: **81
passed**.

## Divergências e suposições escritas

- **Taxa total:** o evento traz só os bps totais. Um teto só, em vez dos três do programa, pode ser até 2 lamports
  mais generoso. Isso está declarado em `pricing.sell_lamports`.
- **Horizonte sem extrapolação:** é o último slot observado com `block_time < corte − 2 s`. `settle_seconds = 2` é
  suposição do motor, alinhada ao aborto do PREREG (p50 de `received_at − block_time` > 2 s). Perto do corte isso
  deixa cópias `incomplete` (no teste sintético, 1 de 21).
- **Primeira compra:** um gatilho recusado por atraso (`late_event`) **consome** a primeira compra da entidade no
  mint, pela leitura estrita de "a primeira compra ≥ 0,1 SOL". Um `CreateEvent` não recebido antes da decisão não
  recusa nada.
- **Pouso impossível na entrada** (curva completa sem pool) dá `no_fill`, contado e fora do C-PnL.
- **Pouso no slot com trades:** o pior entre os estados do slot anterior e os estados antes e depois de cada trade do
  slot. É pelo menos tão adverso quanto o desenho, e não depende da ordem dentro do slot, que o feed não informa.

## Relacionado

[[carteiras-lucro-design]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] ·
[[2026-10-05-seguir-carteiras-lucrativas-aprovado]] · [[EXP-M15-carteiras-vencedoras]] · [[Revisoes-Astra/Index|índice]]

## Revisão de código (code-reviewer, 05/10): REQUEST_CHANGES, todos os itens aplicados

Os testes passaram de 81 para 98. Os testes novos que passaram de primeira cobrem comportamento que já estava certo. Para
provar que têm dentes, rodei uma verificação de mutação: quebrei o código num ponto de cada vez e conferi que o teste
falhava, e depois o arquivo voltou ao original. **15 de 15 mutantes foram mortos.**

| # | Achado | O que mudou |
|---|---|---|
| 1 (HIGH) | `build_snapshot` não filtrava `opening_lots` por tempo. Um lote aberto depois do corte vazava (o próprio `ranker_leaks` acusava), e um lote aberto dentro da janela entrava duas vezes: o E-PnL ia de 6,299 para 7,069 SOL | Só entram lotes com `opened_at` < início da janela. `strip_future` segue o mesmo corte, e `_future()` ganhou um lote futuro e um lote dentro da janela |
| 2 | Lote preservado sem estado válido no início valia 0 em V(início): a venda de um mint morto por 2 SOL contava +2 SOL sem custo | O episódio fica **incompleto** (`pricing.liquidation_or_none`). A errata do desenho e do PREREG diz isso |
| 3 | Faltavam testes com dentes | Cobertos: financiador conhecido depois do corte; `trades_previous_day` só do último dia; horizonte `settle_seconds`; mediana ponderada com 3 peças; sinal de `pre_trade_real_sol`. Também: `positive_days` estrito, `h2_supported` com ≥, neutro estrito, piso entrada + 1 do pouso, stop com ≤, stop fora do slot de entrada, lotes por `ents.of`, `causal_view` checando `block_time` |
| 4 | Agrupamento quadrático | Uma passada por mint e por entidade. `TriggerLedger` registra no lugar, com visão só de leitura, sem cópia por decisão. Episódios excluídos indexados por mint. Liquidação memorizada por fronteira. Sintético (`week()` replicado, não é medição de mercado): **32 004 fills em 6,3 s e 64 008 em 11,5 s**, antes 8,4 s e 26,0 s nesta máquina. O crescimento ficou linear, mas a constante (cotações em `Decimal`) não chega à população de 3–4 M fills/dia sem trabalho na onda 3 |
| 5 | Contaminação de episódio por lacuna (§2) não existia | `Episode.contaminated`: fechado = [abertura, fechamento]; aberto = até a última lacuna. `window_books(gaps=…)` e `EntityMetrics.contaminated_episodes`. Fica contado, não excluído (o §4 do desenho não manda excluir) |
| 6 | PREREG e desenho desalinhados da errata | O §1 item 2 e o §3.1 do desenho e o bloco H-030 do PREREG agora trazem a errata do E-PnL e R = −1 como imputação (a perda total é R = −2). O CONFIRMA também exige que H1 se mantenha com as censuradas a R = −2 |
| 7 | Criação duplicada | Fica o `CreateEvent` recebido mais cedo |

### Para a onda 3 (itens LOW opcionais da revisão, não feitos aqui)

- Motivos que consomem a "primeira compra": hoje `late_event`, `own_mint`, `create_block` e os tetos consomem, e
  `below_min` não. Revisar se é a leitura desejada.
- `mint_cooldown` é global no braço e por entidade no C-PnL. Decidir se o C-PnL também deve ser global.
- As `FeatureDefinition` (`params.py`) ainda não têm consumidor.
- `snapshot_id` = dia + hash dos parâmetros pode colidir se o código mudar sem mudar os parâmetros. Incluir o
  `code_version`.
- Falta validar UTC em `CreateEvent` e `Link`.
- Falta um ajudante para `timedelta(seconds=float(decision_seconds))`, que se repete.

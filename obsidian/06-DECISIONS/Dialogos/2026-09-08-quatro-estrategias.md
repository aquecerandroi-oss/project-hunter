---
tags: [dialogo, sexta-feira, astra, claude, estrategias, shadow-lab]
updated: 2026-09-08
fonte: .claude/state/astra-review-estrategias-novas-2026-09-08.md
status: registro
owner: sexta-feira
decided_on: 2026-09-08
by: sexta-feira (claude+astra)
---

# Diálogo — as quatro estratégias novas (2026-09-08)

Pensamento da [[Mente da Sexta-feira]] sobre o pedido do Everton em 2026-09-08: *"acha mais 4
estratégias no mercado e valide"*. Os dois motores responderam **quatro cada um**, e **duas
coincidem**. Escrevo aqui a divergência e a decisão, em primeira pessoa, porque o que fica na base é
a decisão — não a média das opiniões.

Transcrição do parecer da Astra: `.claude/state/astra-review-estrategias-novas-2026-09-08.md`.
Descoberta e medições do lado Claude (`quant-engineer`): `.claude/state/notes-T3.33.md`.

## As duas listas, lado a lado

| Eixo | Claude (`quant-engineer`) | Astra | Coincide? |
|---|---|---|---|
| compressão de volatilidade → rompimento | `breakout_v1` ([[EXP-0008-breakout-compressao-de-volatilidade]]) | candidata 1 | **sim** |
| recuo dentro de tendência → reversão | `mean_reversion_v1` ([[EXP-0009-mean-reversion-pullback-em-tendencia]]) | candidata 2 | **sim** |
| calendário / faixa de abertura de sessão | `session_orb_v1` ([[EXP-0010-session-orb-faixa-de-abertura]]) | **recusada** ("deixar fora desta rodada, por maior exposição à escolha de calendário") | não |
| posicionamento por funding | `derivatives_v1` ([[EXP-0011-derivatives-reversao-de-funding]]) — o **nível** da taxa liquidada | absorvida na candidata estrutural: desconto **spot–perp** + funding negativo | não |
| força relativa de 24 h descontando β do BTC | **recusada** (não é falta de dado, é falta de protocolo) | candidata 4 | não |

Nas duas primeiras não houve o que decidir: mesma família, mesma mecânica, e as duas listas até
concordam na ordem de prioridade. A decisão é sobre as outras duas vagas.

## A divergência, e o que a resolveu

**A Astra queria gastar as duas vagas restantes em spot–perp e força relativa.** As duas são, na
descrição dela e na minha leitura, hipóteses mais estruturais que "mais um filtro de preço" — e ela
foi explícita: *"não trocaria estas últimas por mais dois filtros de momentum só para entregar
quatro módulos rapidamente"*.

**O que decidiu contra não foi gosto, foi medição.** O `quant-engineer` mediu, antes de escolher, o
que o motor deixa uma estratégia ver:

1. **Spot–perp exige campo novo em `base.py`, e `base.py` está dentro do fecho do `code_ref`.**
   `hunter_strategy_worker.code_ref.version_code_ref` congela cada versão com o digest do módulo dela
   **mais o fecho transitivo dos irmãos que ela importa**. Prova executada nos dois sentidos: com um
   módulo novo acrescentado (`session_orb_v1.py`) mais `registry.py` e `constraints.py` editados, os
   digests de `momentum_v1` (`…ab2e0398…`) e `volume_anomaly_v1` (`…9b8c14ab…`) saem **byte a byte
   iguais** aos de produção; com **um comentário** acrescentado a `base.py`, os dois **mudam**
   (`…31a11c1b…`, `…3a129cf3…`). Um campo `spot_candles_1m` re-congela as duas versões vivas —
   inclusive a linha `paper` — e o Lab emudece atrás de um `/ready` verde.
   E há um agravante do próprio dado: `index_price` **nunca é preenchido** em `NormalizedFunding`,
   nem pelo caminho durável nem pelo hot state, então o prêmio contra o índice não é alcançável a
   partir do contexto mesmo tendo coluna no banco.
2. **Força relativa não é falta de dado, é falta de protocolo.** `Strategy.evaluate(ctx, params)` vê
   **um** mercado. Ranking transversal exige uma segunda interface (`evaluate_universe`) e um Lab com
   carteira; sem isso, não há como escrever a regra sem contrabandear estado global para dentro de
   uma decisão que tem de ser reproduzível por barra.

**E o mais importante: a própria Astra já tinha escrito o fato 1.** O MUST-FIX 1 do parecer dela diz,
com arquivo e linha, que alterar `base.py` pode invalidar as versões congeladas. Ou seja, **não
divergimos sobre o fato — divergimos sobre a sequência**: ela preferia preparar o contexto histórico
primeiro e só então abrir as duas estruturais; eu preferi abrir agora as quatro que cabem no
contrato de hoje.

## A decisão

**As quatro do `quant-engineer`**, pelos motivos acima, com as duas da Astra registradas no
[[Strategy Backlog]] como itens futuros, cada uma com o que exige:

- **spot–perp / prêmio contra o índice** — exige campo novo em `base.py` **mais** `--supersede` das
  duas versões vivas (e da linha paper), como operação auditada e planejada; e exige preencher
  `index_price`. Não é "quando sobrar tempo": é uma tarefa com efeito colateral declarado.
- **força relativa transversal** — exige protocolo `evaluate_universe` e um Lab com carteira. É M4,
  não M3.

**Onde a Astra me corrigiu e eu obedeci** (absorvido nas quatro páginas, sem discussão):

- **custo é hipótese, não tarifa.** Uma leitura positiva a 20 bps que vira negativa a 40 bps recebe o
  rótulo **"frágil a custos"**, nunca "validada". Está em [[KB-0076-por-que-perdemos-2026-09-08]] e
  nos quatro protocolos.
- **grupo de controle obrigatório** em toda candidata cuja tese é um estado (o `squeeze_ratio` da
  0008, a porta de tendência da 0009, a sessão da 0010, o funding da 0011): sem contraste sobre a
  **mesma** população, "60 % de acerto" só descreve a deriva do período.
- **cortar informação pelo instante em que ela poderia ser conhecida** — nada de quantil sobre o mês
  inteiro, β estimado até o fim da amostra, hora ainda aberta ou funding futuro realizado.
- **ETH/SOL/XRP/DOGE simultâneos não são quatro observações independentes** — reamostragem por
  blocos de tempo, e concentração por dia/ativo publicada.
- **não confundir saída ruim com efeito causal da saída** — que é exatamente o que o
  [[EXP-0007-momentum-invalidacao-bracos-INV]] mediu no mesmo dia, e confirmou.

**Onde eu fiquei com o lado Claude, e a Astra pode estar certa:** ela recomendou deixar abertura de
sessão fora desta rodada. O contra-argumento que me convenceu é que
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] e
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] já mostraram que **o relógio já está
dentro dos nossos limiares sem ninguém ter decidido isso** — o piso de ATR% funciona hoje como filtro
de horário. Prefiro o relógio na regra, com nome e refutável, a mantê-lo como efeito colateral. Se a
0010 concentrar mais de 70 % das decisões numa única sessão, a hipótese é reenunciada **antes** da
avaliação seguinte, e isso está congelado na página.

## O que esta decisão não decide

- **Nenhuma das quatro está ativada.** Não há módulo escrito, não há `strategy_version`, não há
  coorte. Ativar é ato auditado do operador, e não acontece por número bonito.
- **Quatro versões abertas no mesmo dia são quatro tentativas**
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]): T-035 a T-038 do
  [[Registro de Tentativas]], com data de início a preencher **antes** da primeira barra.
- **Nenhuma delas responde a pergunta que a [[KB-0076-por-que-perdemos-2026-09-08]] deixou aberta** —
  existe alguma família de entrada com expectancy **bruta** acima de +0,25 R? — ela só a faz quatro
  vezes, com geometrias que não destroem a resposta antes de o mercado opinar.

## Relacionadas

[[Mente da Sexta-feira]] · [[Architecture Decisions]] · [[Strategy Backlog]] ·
[[Experiments Index]] · [[EXP-0008-breakout-compressao-de-volatilidade]] ·
[[EXP-0009-mean-reversion-pullback-em-tendencia]] · [[EXP-0010-session-orb-faixa-de-abertura]] ·
[[EXP-0011-derivatives-reversao-de-funding]] · [[EXP-0007-momentum-invalidacao-bracos-INV]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[Registro de Tentativas]] ·
[[Dialogos/Index|Diálogos]] · [[Revisoes-Astra/Index|Revisões da Astra]] · [[Diario/2026-09-08]]

# Brief T3.27 — a invalidação como **versão de código** (`momentum_v2`), e o passo mais barato que vem antes dela

**Owner:** quant-engineer. **Revisores depois:** quant-engineer cruzado (protocolo), `code-reviewer`,
`risk-engine-guardian` (nada chega à carteira), Astra, Sexta-feira (página EXP).
**Escrito pela T3.26 (2026-09-08) porque o item 1 do brief T3.26 mandou:** *"If the momentum code has
no parameter for the invalidation rule, do not change the code in this task: deliver the cost-floor
variant, and write the invalidation variant as a brief for a `momentum_v2` code version (new module,
new `code_ref`) — a code change is a new strategy, reviewed by the quant protocol."*

## O fato que decide isto (verificado, não suposto)

`packages/core/hunter_core/strategies/momentum_v1.py:281-283` emite a invalidação assim:

```python
invalidations=(
    Invalidation(kind="close_below", level=prior_max, timeframe=self.timeframe.value),
),
```

`prior_max` é a máxima dos 20 fechamentos anteriores, calculada na própria decisão. **Não existe
parâmetro nenhum** em `default_parameters` (19 chaves, nenhuma sobre invalidação) que ligue, desligue
ou desloque essa regra, e `Invalidation.kind` é `Literal["close_below"]`
(`hunter_core/strategies/base.py:104`). Portanto `infra/scripts/derive_variant.py` **não pode**
produzir a variante B: uma variante de parâmetro só move o que o schema congelado declara, e este
não declara isto. Mudar o comportamento exige código novo — módulo novo, `code_ref` novo, versão
nova (`docs/plans/SHADOW-LAB.md` §1).

## O passo mais barato, e ele vem **antes** de escrever qualquer código

Os quatro braços da [[KB-0006]] **já existem**, e não como estratégia: como *políticas de saída*
replayadas sobre entradas congeladas — `packages/indicators/hunter_indicators/replay/policies.py`
(`base`/INV-A, `INV-B`, `INV-C`, `INV-E`, com os contrastes `INV-x − base` já declarados),
`services/strategy-worker/hunter_strategy_worker/replay/engine.py` e
`infra/scripts/replay_exits.py`. É a máquina do EXP-0004 ("políticas de saída"), avaliada uma única
vez, sobre **um dia** (275 avaliáveis, `inconclusivo`).

Isso importa por uma razão de estimando, não de economia: a [[KB-0006]] pede
`Δ = média_i(R_i^alternativa − R_i^atual)` **por entrada pareada**, e é exatamente isso que a máquina
de braços produz — a mesma entrada, os mesmos níveis, a mesma barra, só a política de saída
mudando. Uma `momentum_v2` prospectiva **não** produz esse pareamento: ela decide sozinha, tem slot
próprio e re-arma em instantes diferentes, e a diferença de expectancy passa a misturar *saída* com
*seleção de entradas*. A T3.26 mediu esse efeito de mistura acontecendo: das 31 decisões da variante
de piso, **6 não tinham par no pai** e são responsáveis por toda a diferença de expectancy entre as
duas coortes (5 avaliáveis, +0,2722 R).

**Entrega 0 (pré-requisito, não opcional):** rodar `replay_exits.py` sobre a mesma janela de 31 dias
e os mesmos quatro mercados da T3.26 (ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT), sobre as **224 entradas
congeladas** de `momentum v2` da coorte `replay:f8d8279c-1fba-42ae-95ef-202042f96c60`, e publicar os
três contrastes pareados (`INV-B − base`, `INV-C − base`, `INV-E − base`) com cobertura por braço,
`unresolved` por motivo e o pré-registro da [[KB-0006]] (δ = 0,05 R, Holm a 5%, blocos temporais).
Se os três contrastes forem indistinguíveis de zero nessa população, **a versão de código não vale a
tentativa** — e o custo dessa descoberta é uma corrida de replay, não um módulo novo, uma revisão de
protocolo e 30 dias de sombra.

## O que a versão de código acrescenta (e só ela acrescenta)

Uma resposta prospectiva: *sob a regra alternativa, qual estratégia o Lab teria rodado* — incluindo
o re-arme, a seleção de entradas e a exposição de slot que a máquina de braços, por construção, não
mexe. É uma pergunta legítima e diferente. É também mais cara, e por isso vem depois.

## Entrega 1 — `momentum_v2` (só se a entrega 0 justificar)

**Módulo novo:** `packages/core/hunter_core/strategies/momentum_v2.py`, classe `MomentumV2`,
`key = "momentum_v2"`, registrada em `hunter_core/strategies/registry.py`. **Nunca** editar
`momentum_v1.py`: ele é o código congelado de `v1`, `v2`, `v3` e `v4`, e mexer nele muda o
`code_ref` de todas (`code_ref.py` fecha o digest sobre o módulo + o fecho transitivo dos imports).

**Parâmetros novos, todos declarados no schema congelado (nenhum número no caminho de código):**

| Parâmetro | Tipo | Valor de partida | Por quê |
|---|---|---|---|
| `invalidation_mode` | enum `close_below` \| `none` \| `two_closes` \| `buffered` | `close_below` | os braços da [[KB-0006]]; `close_below` reproduz `momentum_v1` bit a bit |
| `invalidation_buffer_atr` | decimal | `0.25` | INV-E; **valor proposto, sem evidência de otimalidade** (a própria KB-0006 diz isso) |

O default tem de reproduzir `momentum_v1` **exatamente** — mesma decisão, mesmos níveis, mesmo
envelope —, e isso é um teste: um vetor de contexto sintético passa pelas duas classes e as duas
`Decision` são comparadas campo a campo. Sem isso, `momentum_v2` não é a mesma estratégia com uma
regra a mais, é uma estratégia diferente disfarçada.

**Onde está o trabalho de verdade, e o alerta que importa:**

- **`none` e `buffered` não tocam o worker.** `none` emite `invalidations=()` (o `TrackingPlan` fica
  com `invalidation_level = None` e `walker._observe_invalidation` já não faz nada); `buffered`
  emite `level = prior_max − buffer × ATR₀`, com **ATR₀ congelado na decisão** — a regra do walker
  ("fechamento alinhado abaixo do nível") não muda uma linha. Estes dois são baratos.
- **`two_closes` toca o walker, e o walker é o escritor de outcomes de versões já congeladas.**
  `walker._observe_invalidation` (`walker.py:136-142`) é sem memória: ele vê um fechamento e marca
  `pending_invalidation`. Contar **dois fechamentos consecutivos** exige estado novo em `Progress`,
  em `TrackingPlan` (`progress.py:70-71` só carrega `level` e `timeframe`), na serialização de
  `record.py:135` e `tracking_repo.py:108` e na leitura de `signal_outcomes.meta`. Isso é uma
  mudança no caminho vivo que `v1`…`v4` compartilham. **Regra para quem implementar:** o campo novo
  é opcional e ausente significa exatamente o comportamento de hoje, provado por um teste que
  reprocessa uma linha antiga (sem o campo) e obtém o mesmo desfecho. Se essa prova não sair barata,
  entregue `none` e `buffered` e deixe `two_closes` para a máquina de braços, que já sabe fazê-lo
  fora do walker (`replay/engine.py` marca a pendência entre barras, sem estado persistido).
- `Invalidation.kind` deixa de ser `Literal["close_below"]`. Alargar um `Literal` é retrocompatível
  para os dados gravados; estreitar nunca seria.

**Como as coortes nascem:** uma `strategy_version` por braço, `purpose = research_only`, ativadas
pelo caminho auditado de sempre. `INV-A` já existe e é `momentum v2` — **não** derive um clone dela;
duplicar o braço de controle dobraria a tentativa sobre a mesma população sem responder nada
([[KB-0010]]). Com o módulo pronto, `infra/scripts/derive_variant.py --set invalidation_mode=none`
(e `=two_closes`, `=buffered`) deriva os braços a partir da primeira versão de `momentum_v2`, e a
linhagem (`derived_from=`) fica no `changelog` de cada um.

## O que este brief **não** autoriza

Ativar qualquer coisa `paper` ou `live`; mexer nos parâmetros ou no `changelog` de `v1`…`v4`;
comparar braços fora do pré-registro da [[KB-0006]]; e — o mais importante — **usar a janela de
2026-08-08 → 2026-09-08 como confirmação**. Ela é a população que gerou a hipótese; serve para
matar candidatas, nunca para aprová-las ([[KB-0010]]).

## Critérios de aceite

- [ ] Entrega 0 publicada: três contrastes pareados sobre as 224 entradas congeladas, com cobertura
      por braço e `unresolved` por motivo; decisão explícita de seguir ou parar.
- [ ] `momentum_v2` com `invalidation_mode = close_below` reproduz `momentum_v1` campo a campo
      (teste de equivalência), e `params_hash` do braço de controle é declarado como diferente do
      de `momentum v2` **por causa das duas chaves novas** — não por acidente.
- [ ] `none` e `buffered` cobertos por teste de decisão (nível emitido) e de desfecho (walker).
- [ ] `two_closes`: ou entregue com a prova de retrocompatibilidade do walker sobre uma linha antiga,
      ou explicitamente adiado para a máquina de braços, por escrito.
- [ ] Nenhuma alteração em `momentum_v1.py`; `code_ref` de `v1`…`v4` inalterado (verificado por SQL).
- [ ] `ruff`/`pyright`/`check_file_size.py`; testes um arquivo por invocação.
- [ ] Rascunho de `EXP-0007-momentum-invalidacao.md` em `.claude/state/exp-drafts/`.

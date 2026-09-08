# Notas T3.34 — linhas de tendência como indicador (pivôs, linhas, canais, rompimento, reteste)

**Quando:** 2026-09-08. **Owner:** quant-engineer. **Base:** `main` em `566e8bb` (o commit do brief;
o brief diz `f974ad7`, que é o pai). **Nada foi commitado.** **Nada foi importado por
`hunter_core.strategies.*`** e **nada entrou em `DEFAULT_REGISTRY`** — nenhum `code_ref` e nenhum
`feature_set_version` se moveu por causa desta task (provado por
`tests/patterns/test_definitions.py::test_the_live_feature_set_has_not_moved`).

## 1. O que existe agora

`packages/indicators/hunter_indicators/patterns/` — oito arquivos, todos ≤ 350 linhas:

| módulo | linhas | papel |
|---|---|---|
| `scale.py` | 56 | ATR por barra, dobrando o **mesmo** checkpoint `wilder_v1` de `features/atr.py` uma barra por vez. Não há segunda fórmula de ATR no repositório. Aquecimento é `None`; buraco na série **levanta** `ValueError` |
| `pivots.py` | 122 | swings com janela de confirmação `k` (`confirmed_at = index + k`) e filtro de proeminência em ATR |
| `trendlines.py` | 312 | candidatas por pares de pivôs, validade (toques + respeito), nota, deduplicação por faixa de ângulo/nível |
| `channels.py` | 76 | a **relação** entre um suporte e uma resistência paralelos; largura em ATR |
| `events.py` | 308 | repique, rompimento (com RVOL opcional) e reteste, decididos no fechamento |
| `scan.py` | 183 | ponto de entrada: **o único lugar onde o corte é aplicado** (`bars[: as_of + 1]`), mais `PatternParams` congelado que viaja com o resultado |
| `definitions.py` | 109 | cinco `FeatureDefinition` v1 + `pattern_features()`, deliberadamente **fora** do registro ativo |
| `__init__.py` | 7 | só docstring |

Testes: `packages/indicators/tests/patterns/` (`builders.py` + 5 arquivos, **31 testes**).

## 2. Decisões de projeto que valem registro

1. **O corte é um índice de barra, não um relógio.** `scan(bars, as_of=i)` trunca uma vez, no topo,
   e todo o resto vê uma janela que termina em `i`. A propriedade
   `scan(bars, as_of=i) == scan(bars[:i+1])` é então estrutural, e o teste de hipótese sobre passeios
   aleatórios existe para pegar qualquer refatoração que a quebre.
2. **Pivô sem ATR não é pivô.** As ~15 primeiras barras (período 14) não têm escala; filtrar por uma
   escala inventada seria pior do que não reportar. Consequência declarada: as duas primeiras
   cavas de uma janela curta nunca ancoram linha.
3. **Proeminência exclui a própria barra do pivô.** Incluí-la fazia a proeminência ser sempre ≥ o
   range da barra, isto é, ~1 ATR por construção — o filtro de significância não filtrava nada. Foi
   encontrado pelo teste `test_a_wiggle_that_is_small_against_the_current_atr_is_not_a_pivot`, que
   falhou por esse motivo antes da correção.
4. **A validade olha só o intervalo entre o primeiro e o último toque; as violações são contadas até
   o corte.** É o que permite uma linha sobreviver ao próprio rompimento — se ela sumisse na barra
   do rompimento, não haveria rompimento a reportar. O preço disso está na §4.
5. **O reteste inverte a polaridade.** Depois de romper para cima uma resistência, quem toca a linha
   é a **mínima** da barra, não a máxima. Foi um bug real (o teste do reteste falhou por isso) e está
   isolado em `_retest_extreme` com o porquê no docstring.
6. **`Decimal` do começo ao fim.** Toda aritmética de preço roda em `localcontext(CONTEXT)`
   (`prec=28`, `ROUND_HALF_EVEN`). `float` só existe no script de figuras, na fronteira do
   matplotlib. Provado por `test_prices_stay_decimal_all_the_way_through`.
7. **A identidade da linha é a geometria mais os toques.** `line_id` = sha256 de (lado, `origin`,
   `through`, inclinação, toques): duas linhas podem compartilhar o conjunto de toques e ser linhas
   diferentes, e uma linha que ganha um quarto toque é uma afirmação nova sobre a mesma fita.
8. **`FeatureDefinition` sim, registro não.** As cinco features (`trendline_*`) têm nome, versão 1,
   categoria, `inputs` e descrição desde o primeiro dia, como manda o PIPELINE §2, mas **não** entram
   em `features.engine.DEFAULT_REGISTRY`: isso moveria `feature_set_version`, que carimba toda linha
   de `feature_snapshots` já escrita. Quem move é a T3.34b, numa mudança cujo único conteúdo é essa
   movimentação.

## 2b. As três correções da revisão da Astra (`astra-review-T3.34-trendlines.md`)

Pedi opinião à Astra sobre as **regras de detecção** antes de fechar. Ela apontou três defeitos com
cenário concreto; todos foram reproduzidos, todos ganharam teste **antes** da correção, e as figuras
da §4 são as de depois.

1. **A linha desenhada não era a linha validada.** A candidata era validada com a inclinação e a
   origem do *par* de pivôs, mas `projected()` reancorava no primeiro **toque** — que só precisa
   estar a `tolerance_atr` da linha. Medido nas séries reais: até **0,485 ATR** de deriva, e uma
   linha publicada que, reavaliada contra a própria projeção, **violava a regra de respeito**.
   Correção: `origin` e `through` (o par) são campos da `TrendLine`, e `projected()` usa `origin`.
2. **`valid_from_idx` podia anteceder a própria geometria.** Só a confirmação do terceiro toque era
   considerada, então uma linha cuja inclinação vinha dos pivôs 310 e 323 (ETHUSDT 1 h) dizia valer
   desde a barra 232 — e `detect_events` procurava eventos a partir dali, medindo-os contra uma
   inclinação do futuro. Correção: `valid_from_idx = max(3º toque, origin, through)`, todos em
   confirmação. **Era antecipação real dentro de uma varredura**, invisível para a propriedade
   prefixo-vs-corte porque as duas chamadas cometiam o mesmo erro.
3. **Um repique pendente engolia o rompimento anterior.** Toque em `t`, fechamento 1 ATR através da
   linha em `t+1`, recuperação em `t+2`: a confirmação do repique era achada em `t+2` e o cursor
   pulava para `t+3`, apagando do histórico o rompimento que o corte vivo em `t+1` teria reportado.
   Correção: um fechamento além de `break_atr` **cancela** o repique pendente.

Efeito colateral honesto da correção 2: quando dois pares de pivôs produzem a mesma geometria (a onda
sintética faz exatamente isso), o desempate passou a ser o `valid_from_idx` **menor** — a linha que
poderia ter sido desenhada antes — em vez de cair no `line_id`, que é determinístico e sem
significado.

**O que eu não aceitei da revisão**, e por quê: ela pediu também que a varredura garantisse que a
linha estivesse *selecionada* no corte em que diz valer. Não garante e não deve prometer — nota,
baldes e o teto de seis são avaliados no corte, então uma varredura tardia é um desenho
retrospectivo. Isso está escrito no docstring de `trendlines.py` e na KB-0077 §2, e o teste forte
ficou determinístico (na onda sintética), em vez de propriedade sobre passeios aleatórios, onde a
seleção legitimamente muda. As outras sugestões dela — estados explícitos ativa → rompida →
encerrada; separar rompimento geométrico de confirmação por volume; deduplicação gulosa por
distância ao longo do intervalo em vez de baldes; seleção estrutural de swings — são mudanças de
regra, isto é, `patterns` v2, e estão na §5 e na KB-0077 §7.

## 3. Prova (comandos rodados nesta sessão)

```
uv run pytest packages/indicators/tests/patterns -q      -> 31 passed
uv run pytest packages/indicators -q                     -> 979 passed
uv run ruff check <patterns + tests + plot_trendlines.py>  -> All checks passed!
uv run ruff format --check <idem>                          -> 15 files already formatted
uv run pyright packages/indicators/hunter_indicators/patterns packages/indicators/tests/patterns
                                                           -> 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py -> nenhum arquivo desta task acima de 350
   (o único acima do orçamento na árvore ao final é packages/core/hunter_core/db/models/agents.py,
    371, de outra task em voo; a lista mudou duas vezes durante a sessão porque a árvore é
    compartilhada — no começo eram replay/stress.py 430 e dois do market-worker)
```

Os três defeitos apontados pela Astra foram provados por alternância (desligar a correção, rodar o
teste, religar): sem a correção A falha
`test_the_line_that_is_reported_is_the_line_that_was_validated`; sem a B falham
`..._geometry_was_knowable` e `..._drawable_on_the_bar_it_claims`; sem a C o teste do repique
devolve `(BOUNCE, 5)` no lugar de `(BREAKOUT, 4)`.

O teste anti-antecipação tem três afirmações separadas, e a terceira é a que dá dentes às outras:
uma **trapaça deliberada** (pivô declarado conhecido na própria barra, `confirmed_at = index`) reporta
uma linha de 4 toques onde a honesta reporta 3, e reprova exatamente a comparação
`scan(as_of=i) == scan(prefixo)` que a honesta passa.

## 4. Dado real e figuras

Exportação **somente leitura** da VPS: velas de 1 min finais dos perpétuos BTCUSDT, ETHUSDT e
SOLUSDT entre `2026-08-25 15:00Z` e `2026-09-08 15:00Z`, dobradas em SQL (`date_bin` desde a época)
em baldes de 15 m e 1 h, com **exigência de completude** (`count = 15` / `count = 60`); balde
incompleto não é exportado. Saíram 1344 barras de 15 m e 336 de 1 h por mercado — nenhum balde
faltando nos 14 dias. Nada foi escrito na VPS: a consulta foi entregue pelo stdin do `psql` e o CSV
voltou pelo stdout do `ssh`.

Figuras em `.claude/state/design/trendlines/` (script `plot_trendlines.py` ao lado, rodado com
`uv run --with matplotlib` — **matplotlib não foi adicionado ao `pyproject.toml`**, para não mexer no
lock de uma árvore compartilhada):

| figura | barras | pivôs | linhas | canais | eventos |
|---|---|---|---|---|---|
| `btcusdt-15m.png` | 1344 | 240 | 6 | 3 | 8 |
| `btcusdt-1h.png` | 336 | 58 | 6 | 0 | 12 |
| `ethusdt-15m.png` | 1344 | 249 | 6 | 3 | 9 |
| `ethusdt-1h.png` | 336 | 60 | 6 | 3 | 12 |
| `solusdt-15m.png` | 1344 | 254 | 6 | 3 | 4 |
| `solusdt-1h.png` | 336 | 58 | 6 | 3 | 19 |

(números **depois** das três correções da §2b; antes delas os eventos eram 10/14/11/25/8/25 — a
queda é o repique que deixou de engolir rompimento e a validade que deixou de começar cedo demais.)

Custo de uma varredura completa: **194 ms** (1344 barras de 15 m) e **84 ms** (336 barras de 1 h),
ETHUSDT, máquina de dev. O teto vem de `max_anchors = 20`.

**O que um humano teria traçado diferente** (a lista completa, com figura e número, está na
KB-0077 §7). Em ordem de importância: (1) não aposentamos linha rompida — há resistência com
`v=52` e suporte com `v=59` ainda desenhados; (2) leque de seis suportes saindo do mesmo fundo em
`btcusdt-1h`, que para um humano é uma linha só; (3) quatro resistências quase idênticas empilhadas
em `ethusdt-1h`; (4) 240–254 pivôs em 1344 barras de 15 m, contra os ~25 que um humano marca;
(5) não existe **nível horizontal** como conceito, e é por isso que `btcusdt-1h` sai sem nenhuma
resistência justamente onde um humano traçaria a horizontal de 80.100; (6) a linha é sempre
projetada até o corte, e as íngremes atravessam o gráfico inteiro.

Nenhum dos seis é defeito de implementação: são a regra do brief funcionando como escrita. Todos são
candidatos a `patterns` v2 e todos mudam números já desenhados — portanto **versão nova**.

## 5. Pendências que ficam registradas

1. **`retire_after_break`** (limite 1 acima) é a mudança de maior efeito e está proposta na T3.34b §1,
   na **cópia** da geometria, para não mudar as figuras publicadas desta task.
2. **A T3.34b não pode importar `hunter_indicators.patterns`.** `hunter-core` não depende de
   `hunter-indicators` (o inverso sim), e `code_ref.module_closure` só fecha sobre módulos irmãos
   planos de `hunter_core.strategies` — um import cruzado deixaria a geometria **fora** do digest da
   versão congelada. As três opções e a recomendação (portar para irmãos planos, com teste de
   paridade numérica) estão em `.claude/state/brief-T3.34b-trendline-breakout-strategy.md` §0.
3. **Nenhum parâmetro é medido.** Os padrões (`k=3`, `1.0` ATR de proeminência, `0.25` de tolerância,
   `0.5` de rompimento) vêm do brief e da prática clássica. Calibrar exige a T3.34b com replay, não
   mais figuras.
4. **A janela precisa ser contígua.** `atr_series` levanta em buraco; quem chama escolhe a corrida
   contígua. Um worker que use isto precisa decidir o que fazer com um `gap` (o Shadow Lab já recusa
   a janela inteira, o que é o comportamento certo).
5. **A KB-0077 é rascunho:** `.claude/state/exp-drafts/KB-0077-linhas-de-tendencia.md`, para a
   Sexta-feira arquivar em `obsidian/11-KNOWLEDGE/` e mover os PNGs para `obsidian/attachments/`.
   Falta a revisão da Astra sobre as regras de detecção.

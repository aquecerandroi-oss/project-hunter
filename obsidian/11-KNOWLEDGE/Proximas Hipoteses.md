---
tags: [knowledge, indice, hipoteses, moinho]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-27
---

# Próximas Hipóteses — como montar a próxima

Página de partida para quem vai escrever o próximo bloco em [[Fila de Hipoteses]]. Não mede nada
sozinha — junta o que já existe em três lugares (o que nunca foi olhado, o que ficou pela metade, o
que já morreu) para a próxima hipótese nascer informada, não repetida. Ver
[[Dicionario de Variaveis]] (toda variável, testada ou não), [[Mapa de Estrategias]]
(Vivas/Pistas/Cemitério, por Dataview) e `docs/RESEARCH.md` (o vocabulário de veredito e o moinho).

## (a) Variáveis nunca testadas

Copiado à mão da seção "O que nunca foi testado" de [[Dicionario de Variaveis]] — **não é
Dataview**: essa página lê uma tabela de variáveis dentro de uma nota só, sem frontmatter por linha,
que o Dataview não indexa. Se esta lista divergir da fonte, a fonte é [[Dicionario de Variaveis]];
atualize lá primeiro, depois aqui. Das 53 linhas do dicionário, **30 nunca foram testadas de forma
independente**; as oito abaixo (das dez "mais prontas" da fonte) ainda não viraram hipótese — as
outras duas já viraram (H-021, H-020) e saíram da lista.

Classe de perda é **candidata, não medida** — é só a hipótese de qual dos [[Perdas/Index|cinco
vazamentos da mesa de memes]] a variável poderia atacar, para orientar quem for escrever a
`variável`/`previsão` do próximo bloco. Cripto não tem classe de perda (o classificador de
`meme_daily_ficha_classify.py` é só da mesa de memes).

| variável | onde vive | mercado | classe de perda candidata (especulativo) |
|---|---|---|---|
| `distance_from_24h_high` / `_low` | `features/price.py:106` | cripto | não se aplica — bloqueada só por uma medição de redundância nunca feita ([[Strategy Backlog]] item 8) |
| `open_interest` **em nível** (não a variação) | `features/deriv.py:94` (mesmo bloqueio de `missing_input` de `funding_change_8h`, [[KB-0020-funding-change-8h-nunca-calcula]]) | cripto | não se aplica — item 14 do [[Strategy Backlog]], nunca rodado |
| `{buy,sell}_pressure_{Nm}` e `trade_velocity_{Nm}` | `features/micro.py:179,221` | cripto | não se aplica — disponibilidade operacional nunca medida desde que o bloqueio de `covered_until` caiu |
| `is_mayhem` | bloco `mayhem` em `meme_proposals.reasons` (T4.27, só quando `declares_mayhem`) | meme | `comprou_no_topo`? — mecânica do agente (SOL virtual da curva) é diferente da curva normal; nunca medido se excluir por padrão paga |
| `top_buyer_share` / `fill_seconds` | bloco `pedigree_e2b` em `meme_proposals.reasons` (T4.31, EXP-M9) | meme | `golpe_do_criador`? — concentração de um comprador único no preenchimento é parente da concentração que gera despejo em bloco (H-014); a família E2-b morreu como "seguir carteira" (R57/KB-0136), nunca como o **preenchimento** em si |
| `market_betas` (β vs. BTC) | tabela `market_betas` (pacote `beta_v1`) | cripto | não se aplica — tabela existe, **0 linhas na VPS**, nunca populada o suficiente para medir |
| `holders_rising` / `progress_rising` isolados | `meme_features_15s` | meme | `comprou_no_topo`? — hoje só medidos **dentro** de `equilibrio` (H-013, que morreu por 1 caso: 1 de 587 decisões com `equilibrio = verdadeiro`) |
| `liquidations` (notional) | tabela `liquidations` (8 421 linhas, 197 mercados) | cripto | não se aplica — defeito de semântica (`q×p` em vez do executado) nunca corrigido, nem a série testada |

## (b) Pistas em aberto — não confirmadas ou limitadas por dado, com próximo passo

Notas com veredito `nao_confirma` ou `limite_de_dado` **têm** algo escrito para reabrir (medida
nova, coorte nova, ou já virou outra hipótese) — diferente do Cemitério em (c), que é para não
repetir.

```dataview
TABLE hipotese AS "hipótese", veredito AS "veredito", proximo_passo AS "próximo passo"
FROM "11-KNOWLEDGE" OR "03-TRADING/Meme/Perdas"
WHERE veredito = "nao_confirma" OR veredito = "limite_de_dado"
SORT hipotese ASC
```

A consulta só alcança hipóteses com nota `KB-00xx` dedicada (frontmatter `hipotese`/`veredito`/
`proximo_passo`) — seis hoje: H-009 (KB-0152), H-010 (KB-0153), H-013 (KB-0155), H-014 (KB-0156),
H-020 (KB-0160), H-021 (KB-0161). H-017 e H-018 não têm KB própria (a nota que as cita,
[[KB-0159-a-desaceleracao-nao-avisa-o-topo]]/[[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]],
tem `hipotese` apontando para a irmã que fechou primeiro) e as hipóteses de cripto (H-003 a H-008)
nunca tiveram KB própria — só relatório em `.claude/state/`. A tabela estática abaixo cobre
**H-001 a H-022** por isso; se divergir da consulta, a nota é a fonte (nunca esta tabela) e o
`veredito`/`proximo_passo` dela é o que se corrige.

| hipótese | veredito | próximo passo |
|---|---|---|
| [[Fila de Hipoteses#H-003 — Horizontes de 1 a 4 h no lado à vista\|H-003]] | nao_confirma | nenhum declarado; pista descritiva `P3_vol_surge` (h=120): IC de cluster estreito, mas cai na permutação (p=0,1478) — [[Mapa de Estrategias]] §Pistas |
| [[Fila de Hipoteses#H-004 — Percentil de sells/buys dentro da coorte viva\|H-004]] | nao_confirma | nenhum declarado; curva é **pico**, não planalto (1 de 7 limiares exclui zero) — reabrir só com medida ou população que não caia no mesmo pico |
| [[Fila de Hipoteses#H-005 — Piso de impulso recente (momentum_15m ≤ 2,0)\|H-005]] | nao_confirma (no desenho executado; população verbatim vazia) | pôr `momentum_15m` no envelope imutável do sinal e voltar em ~2 semanas |
| [[Fila de Hipoteses#H-006 — Desequilíbrio agressor na barra do sinal\|H-006]] | nao_confirma | nenhum declarado; o contraste pré-registado (tercil alto × tercil baixo) nunca foi refeito com IC — o moinho só sabe medir selecionados × resto |
| [[Fila de Hipoteses#H-008 — Portão de tendência de 4 h\|H-008]] | estudo inválido por censura (51,4 % > 20 %; fica `aberta`, não é um dos cinco rótulos) | pôr `return_4h` no envelope imutável do sinal (sem mudar a decisão) e voltar em ~2 semanas |
| [[Fila de Hipoteses#H-009 — Giro rápido na oscilação (comprar a queda, vender o repique, repetir)\|H-009]] | nao_confirma | já executado: o único pedaço com sinal virou H-011, que **refutou** ([[KB-0154-subir-o-alvo-nao-paga]]) — nada mais a reabrir aqui |
| [[Fila de Hipoteses#H-010 — Concentração do maior comprador (o dono que pode afundar)\|H-010]] | limite_de_dado | reabrir só com a fita WS da decisão persistida por troca (a T4.89 já resolveu isso) e pré-registrar a variável de **estoque** de tokens |
| [[Fila de Hipoteses#H-013 — Moeda em equilíbrio, não em subida (fluxo fraco + vendas ≈ compras + curva rasa)\|H-013]] | limite_de_dado | reabrir com coorte prospectiva do `operator/5` (teto 1,0, série WS) julgando com 20 equilíbrios — meses ao ritmo de 23/09 |
| [[Fila de Hipoteses#H-014 — Rede coordenada de compradores (o golpe em um bloco só)\|H-014]] | nao_confirma | já executado: a pista (SOL no slot de criação) virou H-015, que **refutou** ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]) — nada mais a reabrir aqui |
| [[Fila de Hipoteses#H-017 — Recuo pequeno como melhora de preço (coorte nova, braço de papel)\|H-017]] | limite_de_dado (R79; braço `recuo_v1/1` continua rodando em papel) | ETA ~29 pares/dia → ~29–30/09, só com a mesa real ligada e aceitando |
| [[Fila de Hipoteses#H-018 — Recompra do mesmo mint logo depois de um ganho\|H-018]] | limite_de_dado | ETA para 20 recompras reais: 4–9 dias ao ritmo de 25/09 |
| [[Fila de Hipoteses#H-020 — Identidade social reciclada (o mesmo X/Twitter em várias moedas)\|H-020]] | nao_confirma | reparar a coleta do link social (parada desde 25/09 17:13:16Z) e capturá-lo na criação, com instante próprio; só então coorte nova pré-registrada |
| [[Fila de Hipoteses#H-021 — Estrutura do gráfico na hora da compra (distância do suporte, fundos mais altos, rompimento)\|H-021]] | limite_de_dado (estrutural) | gravar a estrutura do preço **marginal** na fita da decisão; já virou [[Fila de Hipoteses#H-022 — Estrutura do gráfico em moedas maduras (15–120 min, ainda na curva)\|H-022]] (em curso, [[EXP-M26-grafico-em-moedas-maduras]]) |

Fora da tabela: H-001 e H-002 estão `em_curso` (amostra insuficiente ainda, sem veredito — ver
[[Mapa de Estrategias]] §Vivas); H-022 está `aberta`/em construção, ainda sem veredito.

### Pistas novas do R83 (28/09/2026) — só em coorte nova

| pista | número (exploratório) | por que ainda não vale | próximo passo |
|---|---|---|---|
| **Longe da mínima de 24 h** nos sinais de continuação do Lab de cripto | +0,207 R [+0,121, +0,284], Holm 0,0004, patamar nos 7 cortes ([[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]) | secundária de uma hipótese que não confirmou; anda com ATR% (ρ 0,77); o melhor tercil ainda perde −0,097 R | pré-registrar em coorte prospectiva, com ATR% controlado e a comparação contra "não operar" |
| **`mean_reversion v14`** (a da `spot/1`) | +0,228 R [−0,099, +0,597] no contraste da máxima, 183 sinais | amostra pequena, IC largo, só descritivo | seguir acumulando na `spot/1` (limite pequeno) até ter amostra para pré-registrar |

## (c) Cemitério — não repetir

Uma linha, o porquê. Lista completa e o número exato de cada uma: [[Mapa de Estrategias]] §Cemitério.
Regra da casa (Fila de Hipoteses.md, regra 2): **hipótese que morreu não volta com outro nome.**

| hipótese | veredito | por que não repetir |
|---|---|---|
| [[Fila de Hipoteses#H-007 — Teto de volume relativo (exaustão)\|H-007]] | refuta | teto em 12 não sustenta +0,10 R; quanto a +0,02 R, o resultado depende de ruído de Monte Carlo — não decide |
| [[Fila de Hipoteses#H-011 — Onde deve ficar o alvo (vender o primeiro repique e não voltar)\|H-011]] | refuta | melhor alvo (1,08×) é a **borda** da grade e o ganho concentra em 5 moedas, invertendo com a cobertura da fita |
| [[Fila de Hipoteses#H-012 — Tempo máximo curto ("o que não sobe logo não sobe mais")\|H-012]] | refuta | maior IC inferior −1,16 pp; a 30 s cortam-se 14 de 23 vitórias reais |
| [[Fila de Hipoteses#H-015 — Compra no slot de criação (o "bundle" do lançamento)\|H-015]] | refuta | teto no tercil alto mataria 36,5 % das vencedoras (limite 30 %) |
| [[Fila de Hipoteses#H-016 — Entrar no recuo, não no pico (esperar a primeira correção depois do sinal)\|H-016]] | refuta | as moedas que não recuam são as vencedoras; esperar recuo grande custa mais do que compra no topo |
| [[Fila de Hipoteses#H-019 — Fluxo desacelerando na hora da compra (o topo local visto pela fita de 10 s)\|H-019]] | refuta | piso no tercil baixo mataria 34,7 % das vencedoras; sinal saiu ao contrário da tese |
| 13 variáveis de decisão (R65) | nao_confirma (todas) | nenhuma sobrevive Benjamini-Hochberg; girar o botão de novo sem população/medida nova é proibido pela regra 1 da Fila |
| Sniper de lançamento | nao_confirma (descartada) | 18/18 células negativas, não era latência |
| Rajada de compradores | nao_confirma (descartada) | negativa em 54 células |
| Seguir carteira vencedora | nao_confirma (descartada) | não é gatilho |
| `momentum v2/v4/v6/v10`, `volume_anomaly v2`, `session_orb v1`, `trendline_breakout v1` (Shadow Lab) | aposentadas | negativas em toda coorte que tiveram (T3.56) |
| H-003 a H-006 (cripto) | nao_confirma | ver (b) — ignorância, não repetir sem envelope/medida nova |
| `return_4h > 0` como gate de tendência | descartada antes de testar | redundância lógica com a própria entrada |
| `orderbook_imbalance_20 ≥ 0` como filtro de book | descartada antes de testar | razão invariante a escala, não mede profundidade |
| Funding como filtro direcional de entrada | nunca entrou na fila | evidência direta aponta poder preditivo ~zero por ativo |
| `derivatives_v1` (reversão de funding) | morreu na pré-checagem | 5 liquidações negativas em 31 d × 4 mercados |

## (d) Como transformar isto numa hipótese

1. **Escolha uma linha de (a)**, ou uma pista de (b) com próximo passo declarado — nunca uma linha
   de (c) com o mesmo desenho (regra 2 da Fila).
2. **Insira o modelo Templater** — `obsidian/_templates/Nova hipotese.md` (`_templates/LEIA-ME.md`
   explica como) — no fim de [[Fila de Hipoteses]] e preencha os seis campos obrigatórios: `origem`,
   `variável`, `população`, `previsão`, `refutação`, `status`. O carregador
   (`infra.research.queue.load_queue()`) recusa a fila inteira se faltar um.
3. **Exporte a população** (SQL somente-leitura na VPS → CSV local, sem tocar a base nem a rede) e
   escreva o spec do moinho (`infra/research/`, `docs/RESEARCH.md`) — pré-registro antes de olhar
   qualquer resultado, do contrário `run_hypothesis` recusa (`PreRegistrationError`).
4. **Cole o veredito** na nota do estudo (`KB-00xx` nova ou existente, frontmatter completo —
   `hipotese`, `variavel`, `populacao`, `efeito`, `ic`, `veredito`, `proximo_passo`, `mercado`,
   `classe_de_perda` se for meme) e atualize o `status` do bloco na Fila. Vocabulário de veredito:
   `docs/RESEARCH.md`.
5. **Antes de qualquer mudança chegar à mesa** (parâmetro, ativação, braço de papel), a regra
   Obsidian-first (`.claude/rules/obsidian-first.md`) exige a nota citada em `--note`: sem ela as
   ferramentas auditadas (`meme_rule_set.py`, `activate_strategy_version.py`,
   `spot_desk_markets.py`) recusam aplicar.

## Relacionado

[[Dicionario de Variaveis]] · [[Mapa de Estrategias]] · [[Fila de Hipoteses]] · [[Ideias do Everton]] ·
[[Perdas/Index|Perdas]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · `docs/RESEARCH.md` ·
`.claude/rules/obsidian-first.md`

---
tags: [knowledge, indice, estrategias, mapa]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# Mapa de Estratégias

Uma página, três estados, para toda ideia testada em meme ou cripto: **Vivas** (rodando ou em
teste agora), **Pistas** (inconclusiva mas com sinal que vale acompanhar) e **Cemitério** (refutada
ou não confirmada, com o porquê em uma linha e o número). Construída com consultas Dataview sobre o
frontmatter novo (`tipo`, `hipotese`, `veredito`, `efeito`, `mercado` — ver
[[_TEMPLATE-NOTE|_TEMPLATE-NOTE]] "como preencher") **e** uma tabela estática logo abaixo de cada
consulta, para quem lê sem o plugin instalado. As duas devem concordar; se divergirem, a tabela
estática é a mentirosa (foi editada e a nota não) — corrija a nota, nunca só a tabela.

> Requer o plugin **Dataview** (Everton confirmou instalado e ativo em 2026-09-25). Sem ele, os
> blocos ```dataview``` abaixo aparecem como texto puro — as tabelas estáticas continuam legíveis.

## Vivas — rodando ou coletando agora

```dataview
TABLE mercado AS "mercado", hipotese AS "hipótese", veredito AS "estado", proximo_passo AS "próximo passo"
FROM "11-KNOWLEDGE" OR "05-EXPERIMENTS"
WHERE veredito = "em_curso"
SORT mercado ASC, hipotese ASC
```

| item | mercado | o que é | estado em 2026-09-25 |
|---|---|---|---|
| [[Fila de Hipoteses#H-001 — Absorção de uma venda grande (EXP-M22)\|H-001]] — absorção de venda | meme | braços `absorb_v0/1` e `absorb_v0/2` em papel | **em_curso** — 14 apostas medidas em 23/09 (mínimo 20/lado); ficha de 25/09 mostra 72+84 entradas acumuladas nos dois braços, ainda sem novo julgamento ([[Ficha-2026-09-25]]) |
| [[Fila de Hipoteses#H-002 — Retenção dos primeiros compradores (EXP-M19)\|H-002]] — retenção dos primeiros 20 | meme | braço `flow_v2/10` | **em_curso** — 0 apostas no corte de 23/09; sem sinal de ter começado a produzir |
| [[Fila de Hipoteses#H-017 — Recuo pequeno como melhora de preço (coorte nova, braço de papel)\|H-017]] — `recuo_v1/1` | meme | braço de papel, entrada com recuo 3 %/60 s ([[EXP-M24-entrada-no-recuo]]) | **limite_de_dado** no R79 (39 de 150 decisões), mas **continua rodando**: ficha de 25/09 tem 91 entradas acumuladas, **+0,1666 SOL, +2,61 %/entrada** — o melhor braço de papel do dia ([[Ficha-2026-09-25]]) |
| `spot/1` (Jupiter/Binance, `mean_reversion v14`) | cripto | primeira mesa de cripto normal em dinheiro real (23/09) | viva — primeira posição real 25/09 11:30 BRT, `TAOUSDT`, alvo/stop declarados ([[09-OPERATIONS/Diario/2026-09-25|Diário 25/09]]) |
| mesa real de memes (`operator/5`, `operator/6`) | meme | operadores em produção | vivos — 148 operações acumuladas até 25/09, acumulado **−0,4707 SOL**, primeiro dia verde em 25/09 (+0,0356 até 12:00 BRT) |
| `mean_reversion v1/v2/v3/v6/v7/v8/v10` + `momentum v3` (paper) + `momentum v8` | cripto (Lab/Shadow) | roster do Shadow Lab depois da poda T3.56 (2026-09-09) | vivos na última leitura registrada (2026-09-09); **esta página não confirmou estado mais recente** — conferir [[Estratégias.base]] antes de citar como atual |

## Pistas — inconclusivas, mas com sinal que vale acompanhar

Nada aqui é `CONFIRMA` (vocabulário de `docs/RESEARCH.md`) — é o que ficou de interessante depois de
uma hipótese fechar sem confirmar, e que só vira hipótese nova em população futura.

```dataview
TABLE mercado AS "mercado", hipotese AS "hipótese", efeito AS "efeito descritivo"
FROM "11-KNOWLEDGE" OR "05-EXPERIMENTS"
WHERE veredito = "limite_de_dado"
SORT mercado ASC
```

| pista | origem | o que apareceu | por que não é confirmação |
|---|---|---|---|
| Recuo pequeno melhora o **preço** de entrada | H-016 (refutada) → H-017 | célula 3 %/60 s: papel +2,28 pp/SOL (IC [+0,69,+3,89]), reais +1,99 pp; na ficha de 25/09, +2,61 %/entrada acumulado | achado nasceu na mesma população da H-016; H-017 (coorte nova) ainda em **limite_de_dado** (39/150) — [[KB-0157-esperar-o-recuo-nao-paga]] |
| Vender o primeiro repique e não voltar (alvo, não giro) | H-009 (nao_confirma) | +3,44 pp em 62 % das posições reais, contra a regra atual, no fragmento não condicionado ao futuro | virou hipótese própria (H-011) e **refutou** — o fragmento evapora quando testado sem olhar o resultado (−0,31 pp reais, +0,34 pp papel) — [[KB-0152-a-oscilacao-existe-o-giro-nao-paga]] → [[KB-0154-subir-o-alvo-nao-paga]] |
| `buys_1m ≤ 25` (fluxo baixo no minuto) | R65 → R67 | tercil favorável na amostra original (34 % de alvos, MFE +28,1 %) | **não confirmou fora da amostra**: 473 moedas independentes, D=+0,036, IC [−0,058,+0,136], p=0,43, curva **pico** — [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]] |
| Percentil de `sells/buys` dentro da coorte viva (`p_sb`) | R69 → H-004 | sobrevivente isolado em família de 17 (p=0,014) | reproduziu (D=+0,106, p=0,0145) mas a curva é **pico**: só 1 de 7 limiares exclui zero — [[KB-0154-subir-o-alvo-nao-paga]] não se aplica aqui, ver [[Fila de Hipoteses#H-004 — Percentil de sells/buys dentro da coorte viva\|H-004]] |
| Célula `P3_vol_surge`, h=120 (cripto) | R68 → H-003 | D=+0,25 % líquido, IC de cluster [+0,16 %,+0,34 %] (aperta) | IC de **permutação** é largo (p=0,1478) — carregado por poucas barras extremas — [[Fila de Hipoteses#H-003 — Horizontes de 1 a 4 h no lado à vista\|H-003]] |

## Cemitério — refutadas ou não confirmadas

Uma linha, o porquê, o número. `nao_confirma` = ignorância (não sabemos), nunca reaberta com o
mesmo desenho; `refuta` = evidência contra uma vantagem **desse tamanho** (docs/RESEARCH.md).

```dataview
TABLE mercado AS "mercado", veredito AS "veredito", efeito AS "número"
FROM "11-KNOWLEDGE" OR "05-EXPERIMENTS"
WHERE veredito = "refuta" OR veredito = "nao_confirma"
SORT veredito ASC, mercado ASC
```

### Meme

| hipótese | o que testou | veredito | número |
|---|---|---|---|
| [[Fila de Hipoteses#H-009 — Giro rápido na oscilação (comprar a queda, vender o repique, repetir)\|H-009]] | política de giro (comprar queda, vender repique, repetir) | **nao_confirma** | 0 de 12 células confirmam; melhor IC superior +0,103, previsão pedia +0,05 ([[KB-0152-a-oscilacao-existe-o-giro-nao-paga]]) |
| [[Fila de Hipoteses#H-011 — Onde deve ficar o alvo (vender o primeiro repique e não voltar)\|H-011]] | alvo diferente de 1,15× | **refuta** | melhor alvo 1,08× é a **borda** da grade; D=+3,05 pp reais mas 5 moedas concentram o ganho e inverte com a cobertura da fita ([[KB-0154-subir-o-alvo-nao-paga]]) |
| [[Fila de Hipoteses#H-012 — Tempo máximo curto ("o que não sobe logo não sobe mais")\|H-012]] | `max_hold` < 300 s | **refuta** | maior IC inferior −1,16 pp (reais); a 30 s cortam-se 14 de 23 vitórias reais ([[KB-0154-subir-o-alvo-nao-paga]]) |
| [[Fila de Hipoteses#H-014 — Rede coordenada de compradores (o golpe em um bloco só)\|H-014]] | financiador comum entre vendedoras do despejo | **nao_confirma** | D=+0,054, IC [−0,005,+0,116]; nos 4 casos de origem, rede 0–1,4 % ([[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]]) |
| [[Fila de Hipoteses#H-015 — Compra no slot de criação (o "bundle" do lançamento)\|H-015]] | SOL comprado no slot de criação como filtro | **refuta** | teto no tercil alto mataria **36,5 %** das vencedoras (limite 30 %) ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]) |
| [[Fila de Hipoteses#H-016 — Entrar no recuo, não no pico (esperar a primeira correção depois do sinal)\|H-016]] | esperar recuo grande antes de comprar | **refuta** | maior IC inferior −3,60 pp; as moedas que não recuam são as vencedoras (X=12 %/W=20 s perde 25 de 30 vitórias reais) ([[KB-0157-esperar-o-recuo-nao-paga]]) |
| [[Fila de Hipoteses#H-019 — Fluxo desacelerando na hora da compra (o topo local visto pela fita de 10 s)\|H-019]] | prever `comprou_no_topo` pela forma do minuto | **refuta** | piso no tercil baixo mataria 34,7 % das vencedoras; sinal saiu ao contrário da tese ([[KB-0159-a-desaceleracao-nao-avisa-o-topo]]) |
| 13 variáveis de decisão (R65) | snipers, dev share, compradores únicos, progresso, fluxo do criador, idade, volume 1 m, sells/buys, holders, top10, retenção, carteiras novas, flip rápido | **nao_confirma** (todas) | nenhuma sobrevive Benjamini-Hochberg; p mais baixo 0,046 contra limiar 0,0077 ([[KB-0149-o-que-a-mesa-real-ensinou]] item 11) |
| Sniper de lançamento | entrar cedo no lançamento | **nao_confirma** (tratada como descartada) | 18/18 células negativas, não era latência ([[KB-0141-sniper-de-lancamento]]) |
| Rajada de compradores | pico súbito de compradores como gatilho | **nao_confirma** (tratada como descartada) | negativa em 54 células (R58/[[KB-0138-explosao-de-compradores-nao-tem-vantagem]]) |
| Seguir carteira vencedora | copiar quem já ganhou | **nao_confirma** (tratada como descartada) | não é gatilho (R57/KB-0136) |
| `momentum v2/v4/v6/v10`, `volume_anomaly v2`, `session_orb v1`, `trendline_breakout v1` (Shadow Lab) | variantes de parâmetro/família | aposentadas | negativas em toda coorte que tiveram (T3.56, roster 16→9) |

### Cripto

| item | o que testou | veredito | número |
|---|---|---|---|
| [[Fila de Hipoteses#H-003 — Horizontes de 1 a 4 h no lado à vista\|H-003]] | 5 preditores em h∈{60,120,240} | **nao_confirma** | 0 de 15 células confirmam; menor Holm ajustado = 1,0000 |
| [[Fila de Hipoteses#H-004 — Percentil de sells/buys dentro da coorte viva\|H-004]] | `p_sb` | **nao_confirma** | curva é pico: só 1 de 7 limiares exclui zero |
| [[Fila de Hipoteses#H-005 — Piso de impulso recente (momentum_15m ≤ 2,0)\|H-005]] | `momentum_15m ≤ 2,0` | **nao_confirma** | 0 sinais com a variável no envelope verbatim; braço selecionado perde em nível |
| [[Fila de Hipoteses#H-006 — Desequilíbrio agressor na barra do sinal\|H-006]] | `taker_imbalance_5m` | **nao_confirma** | D=+0,09 % líquido, 1 ponto-base abaixo do MRE de +0,10 % |
| [[Fila de Hipoteses#H-007 — Teto de volume relativo (exaustão)\|H-007]] | teto de `volume_ratio_5m` em 12 | **refuta** | limite superior do IC (+0,0155) abaixo do MRE de +0,10 R |
| `return_4h > 0` como gate de tendência | redundância lógica com a própria entrada | descartada antes de testar | gate não filtraria nada, exceto por indisponibilidade da feature ([[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]]) |
| `orderbook_imbalance_20 ≥ 0` como filtro de book | profundidade do livro | descartada antes de testar | a feature é razão invariante a escala, não mede profundidade ([[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]]) |
| Funding como filtro direcional de entrada | funding prevê retorno | nunca entrou na fila | evidência direta aponta poder preditivo ~zero por ativo ([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]) |
| `derivatives_v1` (reversão de funding, Shadow Lab) | comprar depois de funding liquidado negativo | morreu na pré-checagem | 5 liquidações negativas em 31 d × 4 mercados; módulo nunca escrito |
| Escalar exposição pelo inverso da volatilidade (Barroso & Santa-Clara) | vol-scaling | adiada, não testada | o Shadow Lab não dimensiona posição; PnL de carteira não aplicável |

## Fontes e como manter isto atualizado

O que alimenta as consultas Dataview é o frontmatter de cada nota — `tipo`, `hipotese`, `veredito`,
`efeito`, `ic`, `proximo_passo`, `mercado` (ver [[_TEMPLATE-NOTE]]). Ao fechar uma hipótese nova:

1. Escreva o veredito na [[Fila de Hipoteses]] (campo já existente, não mexer no que já está lá).
2. Escreva/atualize a nota `KB-0xxx` correspondente com o frontmatter completo.
3. **Não edite esta página à mão para mover uma linha entre seções** — edite o `veredito` da nota;
   as consultas Dataview já refletem a mudança. As tabelas estáticas abaixo de cada consulta são
   para quem lê sem o plugin, e devem ser atualizadas juntas para não divergirem.

## Relacionado

[[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Strategy Backlog]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Perdas/Index|Perdas]] · [[Estratégias.base]] ·
[[Experimentos.base]] · `docs/RESEARCH.md`

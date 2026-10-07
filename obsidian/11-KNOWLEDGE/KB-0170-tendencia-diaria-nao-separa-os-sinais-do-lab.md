---
tags: [knowledge, cripto, tendencia-diaria, media-movel, lab, momentum, segunda-frente, hipotese, pesquisa, retrospectiva]
tema: "nos sinais da momentum do Lab (coorte prospectiva já resolvida, 16 perpétuos, 08–30/09/2026), estar acima da média de 20 fechamentos diários não melhora o R líquido depois de controlar distância da mínima de 24 h, ATR% e retorno de 4 h: β −0,026 R por desvio robusto, e o tamanho previsto (+0,05) fica fora dos dois intervalos (H-027: momentum REFUTA o tamanho; volume_anomaly limite de dado; global NÃO CONFIRMA, análise retrospectiva)"
fonte: R86 (`.claude/state/r86/`) — H-027 da Fila de Hipóteses, candidata C1 de Próximas Hipóteses
fonte_url: —
lido_em: 2026-10-01
evidencia: "medição própria, retrospectiva pré-especificada — 874 unidades (estratégia × mercado × barra) da momentum em 23 dias e 16 mercados, R_net do Lab (custos assumidos + funding); razão reconstruída das velas 1 min finais com guarda de chegada; OLS conjunto com bootstrap por dia e por mercado (10 000); 30 testes sintéticos, fumaça com efeito injetado e dois nulos; lista elegível congelada com sha256 antes de ler desfechos; robustez pós-desfecho (efeitos fixos, blocos de calendário, sem cada mercado) e auditoria de dados declaradas à parte"
hipotese_testavel: sim
astra: "pré-registro: 5 must-fix aceitos numa emenda datada antes de qualquer desfecho; resultado: reproduziu todos os números e a lista congelada, concorda com momentum REFUTA e global NÃO CONFIRMA; 2 must-fix de instrumento aceitos e corrigidos sem mudar nenhum número; red-team e auditoria de dados do Lab (pedidos pelo orquestrador, chegados depois da leitura dos desfechos) rodados como robustez declarada"
status: vivo
owner: sexta-feira
updated: 2026-10-01
confiança: "?"
tipo: pesquisa
hipotese: H-027
variavel: "razao_mm20d = fechamento do último dia UTC completo ÷ média dos 20 últimos − 1 (dias com 1 440 velas 1 min finais; dia incompleto = indisponível); modelo conjunto com distance_from_24h_low, ATR% e return_4h"
populacao: "coorte prospectiva do Lab, long, perpétuos Binance, terminais com R_net, emitidos 06/09–01/10/2026; momentum 874 unidades em 23 dias e 16 mercados (869 dos 964 sinais da momentum v3); volume_anomaly 66 unidades em 2 dias"
efeito: "momentum β_razao −0,0262 R por desvio robusto (refuta o tamanho +0,05); nível razão>0 −0,194 R × ≤0 −0,195 R; volume_anomaly limite de dado; H-027 global nao_confirma (retrospectiva)"
ic: "IC dia [−0,0828, +0,0290]; IC mercado [−0,0721, +0,0137]"
veredito: nao_confirma
proximo_passo: "nenhuma regra, variante ou braço; a validação em coorte futura da C1 não foi feita e não é prioridade (o tamanho previsto já ficou fora dos dois intervalos); não trocar janela (20 d), cortes, covariáveis ou unidade nestes dados; a observação da mean_reversion v14 (razão ≤ 0, 16 unidades) só volta como hipótese nova de reversão, com população própria"
classe_de_perda: —
mercado: cripto
---

# KB-0170 — A tendência diária não separa os sinais da `momentum` do Lab

> **H-027 `NÃO CONFIRMA` (global) · `momentum` `REFUTA` o tamanho previsto · `volume_anomaly` `LIMITE DE DADO`.**
> **Análise retrospectiva pré-especificada** sobre a coorte prospectiva do Lab já resolvida — **não** é a validação em
> coorte futura que a C1 pedia ([[Proximas Hipoteses]] C1).
>
> Nos 874 sinais (unidades) da `momentum` em 16 perpétuos, de 08 a 30/09/2026, estar acima da média de 20 fechamentos
> diários **não** melhorou o R líquido do Lab, depois de controlar distância da mínima de 24 h, ATR% e retorno de 4 h:
> **β = −0,026 R por desvio robusto**, IC 95 % por dia **[−0,083; +0,029]** e por mercado **[−0,072; +0,014]**. O
> tamanho previsto (+0,05 R) fica fora dos dois. Os dois grupos perdem o mesmo: **razão > 0 −0,194 R** (IC
> [−0,283; −0,114]) e **razão ≤ 0 −0,195 R**.
>
> Pré-registro e emenda em [[Fila de Hipoteses]] § H-027 · candidata e literatura em
> [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] §C1 e [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] ·
> código e saídas em `.claude/state/r86/` (`h027.txt`, sha256 `c9609a6f…`; `robust.txt`; `smoke_synth.txt`).

## O que afirma

1. **No recorte medido, a tendência diária não acrescenta nada aos sinais de rompimento de 15 min.** O efeito
   incremental é ligeiramente negativo e pequeno; um ganho de +0,05 R por desvio fica excluído pelos dois bootstraps.
   Isso bate com a conta de ordem de grandeza da [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]]: a deriva
   diária publicada, espalhada num sinal de horas com 1 R = 1,5 ATR de 15 min, vale centésimos de R.
2. **"Em tendência" não deixa a `momentum` lucrativa.** O grupo favorável perde −0,194 R com o intervalo inteiro abaixo
   de zero — o mesmo que o grupo desfavorável. Não há filtro aqui que transforme o Lab em lucro.
3. **Dentro da mesma moeda o sinal é, se algo, o contrário** (robustez pós-desfecho, não decide): com efeito fixo de
   mercado, β −0,062 [−0,160; −0,021]. Compatível com repique depois de queda continuar no curto prazo
   ([[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]]); **não** inverter a direção nestes dados.

## Onde foi mostrado

| estratégia | n (dias, mercados) | razão > 0 / ≤ 0 | β_razao (R/desvio) | IC dia | IC mercado | Holm | nível razão > 0 | rótulo |
|---|---|---|---|---|---|---|---|---|
| **momentum** | 874 (23, 16) | 676 / 198 | **−0,0262** | [−0,0828; +0,0290] | [−0,0721; +0,0137] | 1,000 | −0,194 R | **REFUTA** |
| volume_anomaly | 66 (2, 14) | 66 / 0 | — | — | — | (p = 1) | — | **LIMITE DE DADO** |

**Cláusula a cláusula (momentum).** Dado: 874 ≥ 150, 23 ≥ 15 dias, 198 ≥ 30 no grupo menor → ok. Instrumento: valores
finitos, posto completo nos cinco cortes, 0 % de réplicas inválidas → ok. **IC superior < +0,05 nos dois bootstraps →
REFUTA o tamanho previsto** (não qualquer efeito; não prova efeito zero nem negativo). As cláusulas de confirmação
também falhariam todas menos uma: β < MRE, IC inferior < 0 nos dois, Holm 1,0, nível do grupo favorável < 0, patamar
ausente (cortes −0,05/−0,025/0/+0,025/+0,05: +0,065/−0,010/−0,026/−0,018/−0,017), metades +0,009 (08–19/09, 427) e
**−0,046** (20–30/09, 447). **Global** (regra da emenda): alguma confirma → não; as duas refutam → não (a
`volume_anomaly` está em limite) → **NÃO CONFIRMA**.

**Modelo conjunto (z robusto):** intercepto −0,203 · razão −0,026 · `distance_from_24h_low` +0,021 [−0,048; +0,080] ·
ATR% +0,028 [−0,074; +0,161] · retorno 4 h +0,002 [−0,057; +0,052]. Secundária (1[razão > 0] ajustado): −0,026
[−0,236; +0,180]. Diagnósticos: número de condição 4,93; 83 % da variação da razão não é explicada pelos controles;
maior mercado 8,4 % das unidades, maior dia 9,3 %; β sem cada mercado de −0,036 a −0,017, sem cada dia de −0,043 a
−0,016.

**O `_low` aqui é controle, não teste.** O coeficiente de `distance_from_24h_low` (+0,021, IC com zero) **não**
replica nem refuta a pista do R83 ([[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]): quase todas estas
unidades já estavam no R83, que achou a pista em outra população (9 187 sinais, 279 mercados).

**Sensibilidades pré-declaradas (não decidem):** só `momentum v3` (869) β −0,023 [−0,082; +0,032]; `r_ex_funding`
−0,026 [−0,083; +0,026]; antes do R83 (783, 21 dias) −0,030 [−0,096; +0,029]; depois do R83 só 91 unidades em 3 dias e
nenhuma com razão ≤ 0 (abaixo do piso); sem a guarda de chegada dos 20 dias (940, 25 dias) −0,043 [−0,098; +0,008],
por mercado [−0,078; −0,011]. As sensibilidades usam 2 000 réplicas, não 10 000.

## Robustez pós-desfecho (red-team e auditoria do orquestrador — chegaram depois da leitura dos desfechos)

Pedidas depois de o resultado existir (desfechos lidos às 03:06:15Z; ver [[06-DECISIONS/Revisoes-Astra/H-027-resultado|H-027-resultado]]).
**Não mudam o rótulo do protocolo**; uma guarda que falha deixa a afirmação **generalizada** como "não verificável".

| guarda (red-team) | o que deu | leitura |
|---|---|---|
| 1. dentro da moeda/do dia | FE mercado −0,062 [−0,160; −0,021] · FE dia −0,011 [−0,067; **+0,058**] · FE mercado+dia −0,060 [−0,158; +0,004] (blocos de 3 dias, 2 000) | nenhum componente positivo dentro da moeda; **com FE de dia o IC superior passa de +0,05** → a refutação do tamanho **não é robusta** ao controle de dia |
| 2. um regime só | 23 dias de setembro/2026 | conclusão restrita à janela; nada sobre regimes |
| 3. blocos de calendário | 3 / 5 / 7 dias: IC sup +0,028 / +0,036 / +0,039; purga das metades: nenhuma saída atravessa a fronteira | refutação mantida |
| 4. datas por braço (piso proposto 15) | razão ≤ 0 em **13 datas** (180 das 198 unidades entre 11 e 18/09); na 2.ª metade, 5 datas e 16 unidades | **falha** → o contraste por sinal é **não verificável**: o grupo ≤ 0 é, na prática, uma semana |
| 5. sem cada mercado | β negativo nas 16 exclusões (−0,036 a −0,017); nível razão > 0 negativo em todas | mantido |
| 6. custo | nível já negativo com IC inteiro < 0 sob o custo assumido; reconstrução por perna não feita | não verificável, sem efeito no rótulo |

**Auditoria de dados (contagens deste estudo):** fora por tipo de mercado, sempre por `market_id` → `market_type`
(nunca por símbolo): `momentum` 163, `volume_anomaly` 97, `mean_reversion v14` 7 · não entradas (`no_entry`,
`result = open`, não são posições): 925 / 151 / 33 · guarda da janela de 24 h: 79 recusadas · terminais completos sem
R_net (fora, nunca zero): `momentum` 6 com razão > 0 e 4 com ≤ 0, `volume_anomaly` 1 (9 `funding_missing`, 2
`funding_ambiguous_exit`) · buracos internos de ARK e MOVR: ARK sem sinais `momentum` na coorte; os 4 terminais da
MOVR ficaram sem razão (dia incompleto) · **685 das 874 unidades** usam, na janela de 20 dias, pelo menos um dia
completado mais de 5 min depois do fim do dia: **o estado diário é reconstrução** do banco (chegada ≤ `emitted_at`),
não o que o scanner tinha em memória.

**Leitura honesta das duas camadas.** Pelo protocolo, a `momentum` **refuta** o tamanho previsto. Como afirmação geral
("a tendência diária não acrescenta +0,05 R aos sinais de continuação"), a refutação **não sobrevive** ao efeito fixo
de dia e o grupo ≤ 0 não tem datas suficientes: fica **não confirmada**, que é também o rótulo global da H-027.

## `spot/1` (descritivo, sem rótulo)

Sinais `mean_reversion v14` do Lab (perpétuos; não são as execuções da Jupiter): 152 unidades; razão > 0 (136) média
+0,010 R; razão ≤ 0 (16) média **+0,252 R**. A Astra reproduziu: os 16 vêm de **7 dias e 7 mercados, 6 no mesmo dia**.
É reversão, não continuação, e 16 casos de uma semana não são pista utilizável. **Nada sobreviveu num nível que
importe para a `spot/1`, então não há braço de papel a descrever** — o custo medido da mesa (0,49 % por ida e volta em
0,05 SOL, [[KB-0171-custo-real-da-spot-1]]) também não foi testado aqui. Uma ideia de reversão abaixo da média de 20
dias, se vier, é hipótese nova com população própria.

## Como mediríamos aqui

- **Sem antecipação:** D = data(obs) − 1; só os 20 dias anteriores ao dia da decisão; cada dia com as 1 440 velas
  finais e o fechamento 23:59; chegada de cada dia ≤ `emitted_at` (`received_at` é a primeira inserção, nunca
  reescrita). Testes: dia corrente e dias futuros mudam e o valor não; **uma razão trapaceira que usa o dia corrente é
  pega pela sonda de vazamento**; dia incompleto, faltando ou chegado depois → indisponível.
- **Congelamento:** lista de 1 182 sinais elegíveis gravada com sha256 `f6fb2201…` às 03:04:58Z, antes da leitura dos
  desfechos (03:06:15Z); na junção, IDs únicos e 0 divergências de disponibilidade de R_net.
- **Fumaça sintética** (`smoke_synth.txt`, rotulada SINTÉTICA, covariáveis reais): efeito injetado de +0,25 R/desvio →
  CONFIRMA (β +0,214); dois nulos → NÃO CONFIRMA.

## Por que pode falhar (e o que não concluir)

- **Recorte estreito:** 16 mercados (os únicos com 20 dias de velas antes de 19/09, e onde a `momentum v3` emite);
  71 % dos terminais da `momentum` ficaram sem a razão. Nada aqui vale para os 275 mercados, para outras estratégias ou
  para "tendência diária" como família.
- **Retrospectiva:** coorte já resolvida e quase toda vista pelo R83; as metades por data são estabilidade interna, não
  replicação. A **coorte futura da C1 não foi feita**.
- **Poucos clusters:** 23 dias e 16 mercados; a regra "os dois bootstraps" é conservadora, não inferência dia × mercado
  ([[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]]).
- **Mistura de versões:** a unidade é a média das versões que decidiram a mesma barra (quase sempre só a v3).
- **Não concluir:** que a tendência diária é inútil (o valor documentado dela é gestão de exposição em dias,
  [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]]), que comprar abaixo da média paga, ou que a pista
  `_low` morreu.

## Segunda opinião (Astra)

**Pré-registro** ([[06-DECISIONS/Revisoes-Astra/H-027-prereg|H-027-prereg]]): cinco must-fix aceitos numa emenda
datada (03:02Z) antes de qualquer desfecho — população congelada no código, falha fechada, bootstrap de mercado ao lado
do de dia, regra global corrigida, natureza retrospectiva em todo resumo. **Resultado**
([[06-DECISIONS/Revisoes-Astra/H-027-resultado|H-027-resultado]]): reproduziu a saída byte a byte e a lista congelada;
concorda com os rótulos; dois defeitos de instrumento (corte não identificável não bloqueava o rótulo; junção não
falhava fechada) corrigidos com teste, **saída idêntica** depois. Recomenda não priorizar a coorte futura só para
repetir este filtro.

## Relacionados

[[Fila de Hipoteses]] · [[Proximas Hipoteses]] · [[Mapa de Estrategias]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] · [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] ·
[[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]] · [[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]] ·
[[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]] · [[KB-0171-custo-real-da-spot-1]] ·
[[KB-0169-fibonacci-e-lta-diaria-no-dado]] · [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-0005-momentum-paper]] · [[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]] (H-033 reusou este maquinário e a lição do FE de dia)

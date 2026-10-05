---
tags: [knowledge, pesquisa, perpetuos, funding, carry, basis, binance, h-029, r87]
tema: "H-029 no dado: carry de funding protegido (à vista comprado + perpétuo USDT-M vendido a 1×) no top-20 da Binance, 2020-03 → 2026-09, com custo das duas pernas, capital parado, liquidação pela marca e deslistados"
fonte: "medição própria (R87) — velas diárias à vista do painel do R84 (750 pares com deslistados, sobrevivência auditada), velas diárias de perpétuo e de preço de marca e o histórico de funding liquidado de 481 contratos USDⓈ-M (inclui `SETTLING`) pela API pública da Binance, baixados em 05/10/2026"
fonte_url: https://fapi.binance.com/fapi/v1/fundingRate · https://fapi.binance.com/fapi/v1/klines · https://fapi.binance.com/fapi/v1/markPriceKlines · https://data.binance.vision/
lido_em: 2026-10-05
evidencia: "backtest próprio pré-registrado (340 semanas, 202 símbolos, 3 braços × 2 limites × 2 convenções de fronteira; bootstrap de blocos de 13 semanas; Holm sobre 3 braços); código e saída em .claude/state/r87/"
hipotese_testavel: sim
astra: "revisou o pré-registro (7 must-fix aceitos antes do run) e o resultado (rótulos reproduzidos; 2 defeitos de contabilidade corrigidos sem mudar rótulo; redação restringida) — H-029-carry-prereg e H-029-carry-resultado"
status: vivo
owner: sexta-feira
updated: 2026-10-05
confiança: backtest do autor
tipo: pesquisa
hipotese: H-029
variavel: S7 (soma do funding liquidado de 7 dias, fundingTime ≤ T − 1 h)
populacao: "top-20 pares USDT à vista com perpétuo USDⓈ-M (ponto-no-tempo, deslistados incluídos), segundas de 2020-03-16 a 2026-09-14"
efeito: "A1 +5,3 a +5,9 % a.a. sobre o capital total (antes de 2023 +11,6/+12,7 %; desde 2023 +0,6/+0,9 %); A0 +1,3 a +2,4 %; A2 +4,8 a +5,1 %"
ic: "pior célula (pes/antes): A1 [+1,00 %; +12,26 %] percentil, p centrado 0,050–0,058, Holm 0,15–0,175; A0 [−3,91 %; +8,96 %] (corrigido em 05/10 — o valor anterior misturava células, ver Revisão do advogado e do defensor)"
veredito: nao_confirma
proximo_passo: "nenhum braço de papel; perpétuo real proibido até a Fase 4. Só volta como hipótese nova em coorte prospectiva (ver Proximas Hipoteses)"
classe_de_perda: —
mercado: cripto
---

# KB-0181 — Carry de funding no dado: o A1 rendeu em 2020–2021 e quase nada desde 2023

> **Veredito: NÃO CONFIRMA** (os três braços), sem mudar parâmetro. O carry condicionado (A1: entra com funding de
> 7 dias ≥ 0,125 %, sai com ≤ 0) rendeu **+5,3 % a +5,9 % a.a. sobre o capital total**, mas não passou no Holm
> (0,15–0,175); quase todo o número vem de **2020–2021** (+8,6 % e +26,9 %). **Desde 2023 o A1 recebeu +3,1 % a.a. de
> funding e ficou com +0,6 % líquido** depois de custos e das liquidações da perna vendida. O carry ingênuo (A0, sempre
> ligado) **perdeu −4,4 % a.a. desde 2023**. O braço "excepcional" (A2) ficou em limite de dado (12 blocos de 13
> semanas com exposição, piso 15). Isso é compatível com a literatura — funding muito variável no tempo
> ([[KB-0180-carry-de-funding]]) —, mas **não prova que o carry desapareceu**: mede esta implementação (top-20, 1×,
> semanal, tarifa de varejo). **Nada vai a papel nem à mesa** — e perpétuo real é proibido até a Fase 4 de qualquer forma.

## O que foi testado

Pré-registro e emenda na [[Fila de Hipoteses#H-029 — Carry de funding protegido (à vista comprado + perpétuo USDT-M vendido, Binance, top-20)\|H-029]]
(registrada às 15:31Z como H-028; renumerada às 15:50Z para não colidir com o rascunho [[H-028-forward-prereg]];
emenda das 15:40Z com os 7 must-fix da Astra, [[06-DECISIONS/Revisoes-Astra/H-029-carry-prereg|H-029-carry-prereg]]),
tudo antes de calcular qualquer sinal ou desfecho.

- **Universo:** toda segunda T, os 20 pares USDT à vista de maior volume de 30 dias **que têm perpétuo USDⓈ-M** do mesmo
  ativo listado há ≥ 35 dias e janela de funding completa — ponto-no-tempo, com deslistados (painel do R84,
  [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]). 340 semanas (2020-03-16 → 2026-09-14), 202 símbolos, N_T
  médio 19,99; 146 semanas antes de 2023.
- **Posição:** compra q à vista e vende q/m contratos com margem igual ao nocional (1×); q = w ÷ (S(1 + 0,15 %) +
  F/m(1 + 0,10 %)) — à vista + margem + custo de entrada = capital da vaga; reajuste semanal; custo 0,15 %/lado à vista e
  0,10 %/lado no perpétuo (ida e volta = 0,50 % do nocional); capital fixo; vaga desligada = USDT a 0 %.
- **Funding:** só taxas **liquidadas**, conhecidas ≥ 1 h antes da decisão; recebido nas liquidações de (T, T + 7 d],
  valorizado pela marca (abertura às 00:00; faixa do dia, adversa/favorável, nas outras).
- **Riscos dentro da conta:** liquidação da perna vendida pela máxima diária do **preço de marca** com o saldo de margem
  (a perna à vista fica descoberta até a segunda seguinte); fim de série em dois cenários; fronteira de 00:00 nas duas
  convenções.
- **Braços:** A0 sempre ligado; A1 entra com S7 ≥ 0,125 % e sai com S7 ≤ 0; A2 entra com S7 ≥ 0,65 % e sai abaixo de
  0,21 %. MRE +5 % a.a. sobre o capital total; IC por blocos de 13 semanas; Holm sobre os três.

## Resultado (saída real em `.claude/state/r87/h029.txt`)

| braço | anual (4 células) | IC 95 % (pior célula) | Holm | antes de 2023 | desde 2023 | rótulo |
|---|---|---|---|---|---|---|
| A0 sempre ligado | +1,33 a +2,39 % | [−3,91; +8,96] | 0,25–0,34 | +9,0 a +10,4 % | **−3,7 a −4,4 %** | NÃO CONFIRMA |
| **A1 custo coberto** | **+5,32 a +5,93 %** | [+1,00; +12,26] | **0,15–0,175** | +11,6 a +12,7 % | **+0,6 a +0,9 %** | **NÃO CONFIRMA** |
| A2 excepcional | +4,75 a +5,14 % | [+0,66; +11,44] | 0,15–0,175 | +10,6 a +11,4 % | +0,3 a +0,4 % | NÃO CONFIRMA — limite de dado |

**Cláusula a cláusula (A1):** estimativa ≥ 5 % sim; IC percentil inferior > 0 sim; **Holm < 0,05 não** (p centrado
0,050–0,058); corte de período sim (os dois lados > 0, mas o de depois é +0,6 %); patamar sim (+5,0 a +6,0 % nas
entradas 0,0625 % e 0,25 %); pisos sim (624 episódios em 251 semanas; 26 blocos, 11 antes e 15 depois). **Não refuta:**
o IC superior (+12,3 %) passa de 5 %. O IC percentil e o p centrado não se contradizem: o p conta réplicas acima de duas
vezes a estimativa (583 de 10 000 no A1 pessimista), e a distribuição tem **cauda direita** longa (2021 rende +27 %); o
intervalo básico refletido seria [−1,6 %; +9,7 %] — diagnóstico da Astra, não substitui o intervalo congelado.

**Por ano (A1, pessimista, convenção principal):** 2020 +8,6 % · 2021 +26,9 % · 2022 −1,2 % · 2023 +1,1 % · 2024 +1,9 %
· 2025 +0,0 % · 2026 −1,3 % (37 semanas).

**De onde veio o dinheiro (A1, pessimista):** funding +6,0 % · basis protegido +0,0 % · perna à vista descoberta depois
de liquidação +10,9 % · perda de margem nas liquidações −10,0 % · custos −1,5 % = +5,3 % a.a. O hedge funcionou (basis
≈ 0); o que mexe é o par liquidação/perna descoberta (**26 liquidações** no A1, 38 no A0, em repiques de +90 % numa
semana: DOGE 4,25×, XLM 2,8×, BNB 2,2×…). **Desde 2023 (A1):** funding +3,1 % · custos −1,5 % · perna descoberta +3,6 %
· liquidação −4,7 % = +0,6 %. Exposição média 62 % do capital; Sharpe 1,31; pior semana −1,1 %; drawdown −1,9 %.

**O ingênuo perde onde o funding vira negativo:** o funding do A0 foi −0,7 % (2023), −0,8 % (2025) e −4,6 % (2026) a.a.
sobre o capital — o simulador bate com a soma direta das taxas sem preço (`check_funding.py`, conferência de
plausibilidade: −0,6 / −1,1 / −5,8 %). Os piores: TRB, BLZ, KITE, AXS, OMG (shorts lotados pagando caro). O A1 evita
isso: **A1 − A0 = +3,9 % a.a. [+2,4; +5,7]** (descritivo, não confirmatório).

**Robustez (não decide):** blocos de 8 e 26 semanas mantêm o IC percentil do A1 acima de zero; **custos dobrados**:
A1 +3,8 % [−0,4; +10,6]; sem as 3 maiores em funding (XRP, ETH, ADA): A1 +4,7 %. **Diagnóstico de cauda (NÃO
pré-registrado, escrito depois de ver as liquidações):** **sem 2021 o A1 dá +1,4 % a.a.**; as 20 semanas inteiras com
alguma liquidação somam +2,8 % a.a. e as outras 320 semanas +2,5 % (mesmo denominador); subtraindo só o resultado
contabilizado das 26 vagas liquidadas restam +4,4 % — **não é uma estratégia contrafactual sem liquidações**.

**Antecipação:** 21 testes sintéticos (inclusive uma estratégia trapaceira que lê o funding da semana seguinte, pega
pela mesma guarda, mutantes da janela que falham, conservação do caixa e vaga presa); fumaça sintética com controle
positivo (A0 e A1 CONFIRMA) e nulos (nenhum confirma); **25 semanas reais reconstruídas só com velas < T e funding ≤
T − 1 h: 0 divergências de universo, S7 e entradas** (a 1.ª volta acusou 4, que eram só o sufixo `#0` de série partida
por lacuna futura do LUNAUSDT — comparação por símbolo, convenção do R84); **trajetória inteira** (posições abertas e P&L
semanal dos três braços) refeita com o dado cortado: posições idênticas; 4 semanas do A0 diferem só porque o painel
cortado não carrega preço da vaga FTT presa (lacuna de 310 d classificada no R84 como a mesma moeda) — nenhuma decisão
diverge.

**Correções depois da revisão do resultado (sem mudar parâmetro, rótulos iguais):** a vaga presa passou a reservar o
seu saldo de margem (efeito −0,0004 p.p. a.a. medido pela Astra) e o custo de entrada passou a sair do capital da vaga
(q menor ~0,25 %); a saída antes da correção fica em `h029_v1_antes_da_revisao.txt`.

## O que isto ensina

1. **Neste modelo, desde 2023, o carry condicionado não pagou o capital:** +3,1 % a.a. de funding viram +0,6 % depois de
   custos e liquidações — abaixo de qualquer aplicação de ~5 %. Funding recebido e retorno da estratégia **não são a
   mesma coisa**.
2. **Sempre ligado é pior que nada desde 2023:** o top-20 tem moedas com shorts lotados pagando funding muito negativo;
   carregar todas sem filtro sangra. Se o carry voltar a ser pesquisado, "não ficar onde o funding é ≤ 0" é o mínimo.
3. **1× não é "sem risco":** um repique de +90 % numa semana zera a margem e deixa a perna comprada descoberta. Isso é
   risco direcional escondido num trade "neutro" e, no nosso dado, pesa tanto quanto o próprio funding.
4. **Anualizar 2021 engana:** o número cheio (+5,3 %) encosta no MRE; sem 2021 é +1,4 %. É o falso positivo que a Astra
   apontou ao propor a ideia.

## Limites (o que este teste não cobre)

Execução pela abertura diária (não intradiária); tarifas VIP0 taker sem desconto de BNB nem maker; margem a 1× isolada
(margem cruzada com o à vista como garantia reduziria o capital por vaga e aumentaria a chance de liquidação); sem
rendimento do USDT parado; quebra de corretora e perda de paridade não modeladas; funding previsto nunca usado. Conta de
ordem de grandeza (não é teste): desde 2023, mesmo com custo zero o A1 daria ~+2,0 % a.a. (0,57 + 1,47); dobrar isso
pela margem cruzada daria ~+4 %, ainda abaixo de 5 % e com mais liquidação.

## Revisão do advogado de Jesus e do defensor (05/10/2026)

Acrescentada; o texto acima fica como estava, exceto a correção de frontmatter descrita no fim. Revisores:
[[Advogado de Jesus]] (red team) e [[Defensor]] (steelman). Resumo na [[Fila de Hipoteses#H-029 — Carry de funding protegido (à vista comprado + perpétuo USDT-M vendido, Binance, top-20)|Fila, H-029]].
**O rótulo NÃO CONFIRMA fica** para A0, A1 e A2.

**Concentração (o +5,3 % do A1 não vale como tamanho).** +1,74 % a.a. dos +5,32 % vêm de **duas vagas-semana da DOGE em 2021**,
com o à vista descoberto depois da liquidação (a regra pré-registrada deixa a perna à vista segurar até a segunda seguinte);
sem elas o A1 fica em ≈ +3,6 %. As **5 melhores semanas são as mesmas nos três braços, todas de 2021**. Com o ano como unidade
t = 1,34; com blocos de 52 semanas p 0,105.

**Correção da lição 3 e dos Limites (a anterior fica; esta a corrige).** A lição 3 ("1× não é sem risco… no nosso dado, pesa tanto
quanto o próprio funding") e a frase de *De onde veio o dinheiro* sugerem que as liquidações custaram dinheiro ao A1. **Não custaram:
as liquidações somaram +0,89 % a.a. no A1** (perda de margem −10,0 % mais perna à vista descoberta +10,9 %): foi **sorte**, não
custo (desde 2023 a soma foi −1,1 %: perna descoberta +3,6 % menos margem −4,7 %, como já escrito acima). **Sem liquidação
(estimativa pessimista) o A1 = +4,54 %**, abaixo do MRE de 5 %. Risco direcional escondido existe (a loteria liquidação/perna
descoberta), mas o sinal médio no nosso dado foi positivo e pequeno, não negativo. Nos **Limites**, "a margem cruzada com o à vista
como garantia… aumentaria a chance de liquidação" está errado no sentido: com margem de portfólio ou o à vista como garantia a
liquidação **praticamente desaparece**, não aumenta (o que muda é o capital por vaga e o risco de contraparte, não medidos). A conta
de ordem de grandeza dos Limites ("dobrar pela margem cruzada daria ~+4 %") **não é um teste** e não vale como teto.

**Diagnósticos NÃO pré-registrados** (escritos depois de ver o resultado; não decidem): MMR 1 % (Holm 0,13–0,15); sem liquidação
(+4,54 % pes); custo ×0 (Holm 0,084) e ×0,5; blocos de 52 semanas (p 0,105); t com o ano como unidade (1,34). Nenhum muda o rótulo.
**Caminho que se bifurca, não resultado:** só a combinação de **duas folgas escolhidas depois de ver** (sem liquidação **e** metade
do custo) passaria em todas as cláusulas (Holm 0,02; desde 2023 +2,4 %). Escolher essa combinação agora seria o jardim das
bifurcações; não vira confirmação, nem pista para parâmetro nestes dados.

**Furo de dado.** **SXP, BTCST e AERGO** caíram do universo por **vela de perpétuo vazia**, embora marca e funding estivessem completos;
o tamanho do efeito **não foi medido** (não se sabe se estavam no top-20 nas semanas relevantes). Não verificável: o **rendimento do
USDT parado** (a favor do carry, ~+1 a +1,5 % a.a., não creditado).

**Leitura do defensor (poder e estrutura).** Poder na amostra inteira para 5 % a.a. ≈ **35 %** (EP realizado ~2,9 p.p., cerca de 2×
o palpite do pré-registro; 80 % só a ~8,5 %) — o desfecho NÃO CONFIRMA era o esperado, e **não é prova de ausência**. Mas **desde
2023 a implementação testada ficou medida: +0,6 % [−0,5; +1,7]** (aproximação normal, descritivo): a falta de poder não explica o
regime recente. O desenho foi **mais duro que o carry praticado**: 1× isolado em USDT-M dobra o capital por nocional e cria a loteria
liquidação/perna descoberta; o **perpétuo COIN-M vendido a 1× com a moeda como margem não é liquidável pela alta** (capital = nocional)
e **não foi testado**. O obstáculo absoluto de 5 % não é excesso sobre T-bill (corrigir em pré-registros futuros).
**Propostas** (só pesquisa/roteiro; perpétuo real proibido até a Fase 4; **prioridade baixa**, decisão da Sexta-feira em 05/10):
**P1** carry de juro-base em BTC/ETH COIN-M sempre ligado, MRE +3 % a.a. sobre o T-bill, 104 semanas de coorte futura; **P2** base do
futuro trimestral COIN-M; família = H-029 (3 testes) + novos, Holm sobre a união. T₀ da coorte: primeira segunda com
T₀ − 7 d − 1 h > max(congelamento, 2026-10-05 08:00Z) (ver [[Proximas Hipoteses]]).

**Inconsistências de texto encontradas (e o que foi feito).**

- **`ic` do frontmatter** dizia "A1 [+1,0 %; +13,2 %]" e "A0 [−3,9 %; +10,3 %]", enquanto o texto e a tabela usam a **pior célula**
  (pes/antes: A1 [+1,00; +12,26], A0 [−3,91; +8,96]). Os valores antigos eram o **envelope** das quatro células (menor inferior, maior
  superior; +13,25 e +10,30 vêm de opt/depois). **Frontmatter corrigido para a pior célula** e dito no próprio campo.
- **IC do A0:** a tabela deste KB mostra **[−3,91; +8,96]** (célula pes/antes, a pior); o veredito da [[Fila de Hipoteses]] mostra
  **[−3,91; +10,30]** (inferior da pes/antes e superior da opt/depois — envelope, não uma célula). Nenhum dos dois muda o rótulo; o da
  Fila não foi editado (fora do escopo desta revisão, que só acrescenta linhas ao bloco); vale o da tabela deste KB para "pior célula".

## Relacionados

[[Advogado de Jesus]] · [[Defensor]] · [[KB-0180-carry-de-funding]] · [[Fila de Hipoteses]] (H-029) · [[Proximas Hipoteses]] · [[Mapa de Estrategias]] ·
[[06-DECISIONS/Revisoes-Astra/H-029-carry-prereg|H-029-carry-prereg]] ·
[[06-DECISIONS/Revisoes-Astra/H-029-carry-resultado|H-029-carry-resultado]] · [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]
(painel) · [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] · [[KB-0149-o-que-a-mesa-real-ensinou]] §5

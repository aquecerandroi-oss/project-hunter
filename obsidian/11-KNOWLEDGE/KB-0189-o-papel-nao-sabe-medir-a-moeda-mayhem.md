---
tags: [knowledge, meme, pesquisa, mayhem, curva, simulador, papel, instrumento, hipotese, m4]
tema: as moedas Mayhem perdem −60 % por SOL no papel contra −5 % das não-Mayhem, mas a diferença é do simulador — o teto de SOL real corta 63 % das saídas Mayhem e ignora o SOL que a nossa própria compra poria na curva; a H-032 não diz se Mayhem é pior ou melhor de verdade
fonte: R89 (`.claude/state/r89/`) — H-032 da Fila de Hipóteses, origem na linha `is_mayhem` de Próximas Hipóteses (a)
fonte_url:
lido_em: 2026-10-07
evidencia: medição própria — 2 468 apostas de papel da sonda `refused_probe_v0/1` (EXP-M23, estrato B, p 0,005), uma por mint, 23/09–06/10 (14 dias); 732 Mayhem (731 resolvidas) e 1 736 não-Mayhem (1 643 resolvidas); D_adj por dia × 6 h × tercil de recusas, bootstrap de blocos de 60 min e de dia (10 000); réplica cega por SQL no servidor
hipotese_testavel: sim
astra: concorda (duas revisões; 6 must-fix no pré-registro absorvidos numa emenda antes dos desfechos, 3 no resultado absorvidos sem mudar o rótulo)
status: vivo
owner: sexta-feira
updated: 2026-10-07
confiança: "?"
tipo: pesquisa
hipotese: H-032
variavel: mayhem (mayhem_curve entre as recusas gravadas no instante da recusa)
populacao: 2 468 apostas de papel do refused_probe_v0/1, estrato B, 23/09–06/10 (732 Mayhem, 1 736 não-Mayhem)
efeito: D_adj (não-Mayhem − Mayhem) = +0,5353 por SOL no simulador
ic: [+0,4825, +0,5795] (blocos de 60 min)
veredito: nao_confirma
proximo_passo: consertar o teto do papel em Mayhem (somar o SOL da nossa compra hipotética às reservas reais e validar a venda Mayhem on-chain: de onde sai o SOL, o que acontece sem SOL suficiente) e só então pré-registrar de novo, em dado coletado depois do conserto, de preferência no quase-passou (Mayhem é o único motivo da recusa)
classe_de_perda: comprou_no_topo
mercado: meme
---

# KB-0189 — O papel não sabe medir a moeda Mayhem

> **H-032 (moeda Mayhem depois da entrada): `NÃO CONFIRMA — instrumento`.** O contraste registrado deu
> +0,5353 por SOL a favor das não-Mayhem, com intervalo apertado e réplica cega igual ao dígito.
> Mesmo assim, falharam dois portões de instrumento pré-registrados, e o número mede o simulador, não o mercado.
> Estudo: código e saídas em `.claude/state/r89/` (`h032.txt`, `q_replica.sql`, `q_capdiag.sql`).
> Pré-registro: [[Fila de Hipoteses]] § H-032. Revisões: [[H-032-mayhem-prereg]] · [[H-032-mayhem-resultado]].

## O que afirma

1. **A mesa nunca comprou Mayhem, então excluí-las não muda nada do que ela fez.** Medido em 07/10/2026 00:25Z:
   - **0 de 161** posições reais foram em Mayhem.
   - As 8 459 propostas que levam o bloco `mayhem` dizem `is_mayhem = false` em todas.
   - Nenhum conjunto desliga `exclude_mayhem`.
   - O quase-passou em que só o Mayhem barrou a mesa (`operator/5`) teve **1 mint em 7 dias**.

   A pergunta "a exclusão paga para a mesa" não tem amostra hoje. Esse é um limite de dado estrutural.
2. **A população que existe é a sonda de recusadas do [[EXP-M23-desfecho-das-recusadas]].** Ela tem 732 Mayhem e 1 736 não-Mayhem, todas do estrato B.
   - Cada moeda falhou de 4 a 15 critérios das mesas `operator/5+operator/6`.
   - As duas usam a mesma saída da mesa (1,15× / recuo 10 % / 300 s / perda máx. 50 %) e o mesmo simulador.
3. **No papel, Mayhem é desastre.** Média por SOL −0,597 contra −0,049; mediana −0,851 contra −0,039.
   - D_adj = **+0,5353** [+0,4825, +0,5795] com blocos de 60 min, e [+0,4949, +0,5714] com blocos de dia.
   - O sinal repete nas duas metades, nas duas variantes de `params`, na sensibilidade de famílias e nos dois cenários de censura.
   - Perda ≥ 50 %: **70,9 %** das Mayhem contra 1,2 % das não-Mayhem. A saída Mayhem é `max_loss` em 429 de 731.
4. **Mas esse número é o teto do simulador** (portão I2, pré-registrado: teto em > 10 % das saídas Mayhem invalida a leitura).
   - O teto de SOL real foi aplicado em **463 de 731 saídas Mayhem (63,3 %)** e em 0 das não-Mayhem.
   - Na foto de entrada, a mediana do SOL real da curva Mayhem é **0,061 SOL**, menos que a ficha de 0,07; 90 % estão abaixo de 0,7 SOL.
   - O papel corta a venda no SOL real **observado** (`lab_values.sell_cap_sol`, `paper_engine`). As fotos seguintes nunca contêm o SOL que a nossa compra hipotética teria posto na curva.
   - Por isso uma ida e volta **sem nenhum movimento de preço** já perde −14 % na mediana das Mayhem, e mais de 10 % em 51 % delas, contra −3,4 % só de taxas.
   - Defeito registrado em [[Open Bugs]].
5. **O tamanho do artefato, na mesma foto de saída** (diagnóstico pós-hoc, declarado, descritivo). Nas 463 saídas com teto, o ret registrado é −0,854.
   - Sem teto, seria −0,027.
   - Com o teto subido ao SOL real observado mais o `curve_cost` da nossa compra, seria −0,091.

   Isto **não** é o retorno de um simulador corrigido. Os gatilhos e o instante de saída foram decididos com marcas cortadas, e o recuo e a perda máxima teriam disparado em outro momento.
6. **O portão I1 também falhou**, pela regra congelada "nulo = discordância".
   - 239 dos 2 468 registros não têm o bit Mayhem na foto de entrada. A conta inclui a única proposta sem aposta.
   - Entre os bits não nulos, a concordância entre a recusa, a foto e o token foi de 100 %.
   - Sozinho, o I2 já dava o rótulo.

## O que NÃO afirma

- **Não diz que Mayhem é pior, melhor ou igual de verdade.** Também não diz que o teto explica toda a diferença, nem que tirar o teto recuperaria aqueles retornos na prática.
- **Não diz que o veto Mayhem paga, nem que deveria sair.** A mesa já exclui e **nada muda**: nenhum parâmetro, nenhuma ativação.
- **As 268 Mayhem sem teto na saída não estão limpas** (−0,152 de média): marcas anteriores, já cortadas, podem ter mudado o gatilho. O recorte "sem teto e SOL real na entrada ≥ 0,7" (54 Mayhem, D_adj +0,14) é descritivo e escolhido depois do fato.
- **A réplica por SQL confere a conta, não o simulador.**
- **Descritivo curioso, contaminado pelo mesmo teto:** Mayhem teve mais ganhos ≥ +10 % (10,3 % contra 6,9 %) e mais acertos (11,9 % contra 9,3 %). `comprou_no_topo` deu 0,93× (a previsão secundária pedia ≥ 1,5×).

## O que muda para o resto do projeto

- **[[EXP-M23-desfecho-das-recusadas]] está contaminado.** O contraste global (A+B, inverso da probabilidade) inclui as Mayhem do estrato B, que somam 30 % das apostas da sonda em contagem; o peso no estimador não foi medido.
  - O teto faz as recusadas parecerem piores do que são e favorece, por artefato, a conclusão "o portão seleciona".
  - Os contrastes por critério do estrato A não são invalidados automaticamente.
  - Tirar Mayhem/B depois de ver também não serve: muda a população do alvo confirmatório.
- **Qualquer braço de papel que algum dia aceite Mayhem herda o defeito.** Um `exclude_mayhem: false` em papel, hoje, mediria o teto.
- **O executor real não é afetado.** Ele lê e compra na conta certa da curva ([[KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos]] §5, `docs/PUMPFUN.md` §9). Não se sabe o que a venda Mayhem on-chain faz quando a curva tem menos SOL real que o valor dos tokens: de onde sai o SOL (cofre do agente?), se a venda é recusada ou parcial. Isso nunca foi validado.

## Números

| | Mayhem | não-Mayhem |
|---|---:|---:|
| apostas / resolvidas | 732 / 731 | 1 736 / 1 643 |
| ausentes (indeterminate, proposta sem aposta) | 1 (0,14 %) | 93 (5,36 %) |
| ret médio · mediano | −0,5971 · −0,8505 | −0,0494 · −0,0388 |
| ret ≤ −0,5 · ret ≥ +0,10 · ret > 0 | 70,9 % · 10,3 % · 11,9 % | 1,2 % · 6,9 % · 9,3 % |
| `comprou_no_topo` (perda e `high_water_x` ≤ 1) | 80,4 % | 86,3 % |
| saídas com teto de SOL real | 463 (63,3 %) | 0 |
| SOL real na foto de entrada p10 · p50 · p90 | 0 · 0,061 · 0,680 | 0 · 0,241 · 7,321 |
| motivo de saída mais comum | `max_loss` 429 | `creator_dump` 756 |

D_adj +0,5353 (137 estratos; descartados por falta de suporte: 2,3 % das Mayhem e 1,3 % das não-Mayhem). O p
centrado foi 0,0001. Os cenários de censura deram +0,6355 [+0,567, +0,687] e +0,4776 [+0,420, +0,530]. Nenhum
valor imputado aos ausentes muda o rótulo enquanto I1/I2 falharem.

## Revisão da Astra

- **Pré-registro** ([[H-032-mayhem-prereg]]): 6 must-fix absorvidos numa emenda antes dos desfechos.
  - O alvo virou contraste descritivo e o estimador ajustado virou o primário.
  - As famílias `progress_*`/`mayhem_*` saíram da contagem de recusas.
  - Entraram os portões de instrumento I1–I3, o bootstrap com o estimador inteiro e blocos de dia.
  - A refutação passou a exigir os dois cenários de censura, e a cláusula de nível foi declarada não aplicável.
  - Foi ela quem apontou que o teto ignora a nossa compra (`paper_fill.py:171` × `paper_engine.py:123`). Por isso o I2 existia antes de olhar.
- **Resultado** ([[H-032-mayhem-resultado]]): concorda com o rótulo e recomputou D_adj e as médias do CSV de forma independente.
  - 3 must-fix absorvidos: o bug em [[Open Bugs]], o aviso ao EXP-M23 e "grade de imputação" no lugar de "ponto de inversão".

## Relacionados

[[Fila de Hipoteses]] (H-032) · [[Proximas Hipoteses]] · [[Dicionario de Variaveis]] ·
[[EXP-M23-desfecho-das-recusadas]] · [[KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos]] ·
[[KB-0115-volta-ao-piso-e-real-ou-artefato]] · [[KB-0111-top10-share-maior-que-1-no-retrato-de-risco]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[comprou_no_topo]] · [[Mapa de Estrategias]] · [[Open Bugs]]

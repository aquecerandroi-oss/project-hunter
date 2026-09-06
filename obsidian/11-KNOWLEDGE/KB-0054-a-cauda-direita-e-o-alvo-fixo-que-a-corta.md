---
tags: [knowledge, nota, livros, saida, cauda]
tema: trend following / distribuição de resultados
fonte: Andreas Clenow, *Following the Trend* e *Trading Evolved* — páginas públicas do autor
fonte_url: https://www.followingthetrend.com/the-book/
lido_em: 2026-09-06
evidencia: backtest do autor
hipotese_testavel: sim
astra: concorda com ressalvas
---

# A cauda direita, e o alvo fixo que a corta

## O que afirma

A tese central do trend following sistemático, na versão que Clenow publica com números: **o
resultado não vem da taxa de acerto, vem de poucos ganhos muito grandes.** A maioria das operações
perde ou empata; o que paga o ano são as poucas que andam muito e são deixadas andar. A consequência
operacional, escrita com o cuidado que a revisão exigiu: **um alvo fixo de lucro pode impedir a
captura dos movimentos grandes, e o efeito líquido disso precisa ser medido** — realizar antes de uma
reversão também pode melhorar o resultado. A versão que eu tinha escrito ("qualquer alvo remove
exatamente a parte que paga") antecipava a conclusão.

Ressalvas de fonte, duas. Li a página pública do autor sobre o livro e a página de regras do sistema
dele. **Nenhum número entra nesta nota.** E, correção da Astra: as regras públicas dele têm
dimensionamento por ATR, diversificação e **saída móvel** — ele **rejeita explicitamente
piramidação**, que eu tinha atribuído a ele.

## Onde foi mostrado

Carteiras diversificadas de futuros (dezenas de mercados), barras **diárias**, posições de semanas a
meses, ao longo de décadas, com backtests do próprio autor. A cauda de que ele fala é construída ao
longo de **meses**, numa carteira, com dimensionamento por volatilidade e saída móvel. Nada disso
descreve um acompanhamento de 4 horas de perna única.

## Como mediríamos aqui

O nosso alvo é `target_atr = 1,5` a partir do fechamento de referência, o que dá — na referência —
uma razão de 1:1 contra o stop ([[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]]). Todo ganho é
truncado ali.

**E há uma peça do sistema que existe, é persistida e nunca foi usada como barreira.** A
`momentum_v1` calcula `target2_atr = 3` e `target3_atr = 4,5` (`momentum_v1.py:88-89`); eles são
montados junto do `target1` (`record.py:137`) e gravados no array `targets` de `agent_signals`
(`persist.py:59`). O acompanhamento, porém, compara apenas com `plan.target1` (`walker.py:73,157`), e
o plano reconstruído usa só `virtual_targets[0]` (`tracking_repo.py:102`). Depois que o rastreamento
fica terminal, **nenhuma barra posterior altera o resultado** — a redação precisa é essa, e não "para
de consumir barras": o walker materializa o iterável inteiro e só então deixa de aplicar transições
(`walker.py:169`); no fluxo operacional, acompanhamentos encerrados nem chegam a ser carregados
(`tracking_repo.py:161`, `outcomes.py:177`). Ou seja: os dois alvos informativos estão no banco e
**não geram nenhuma estatística de chegada**.

Duas ressalvas da Astra que estreitam a afirmação, e a segunda muda o desenho do experimento:

1. **"Nunca sabemos" é forte demais.** Um gap favorável pode registrar `exit_observed` acima desses
   níveis (`walker.py:90`), e velas posteriores preservadas permitem investigar. O correto é: **os
   outcomes atuais não fornecem taxa sistemática de chegada aos alvos 2 e 3.**
2. **Contar a máxima até 4 horas não responde a pergunta.** Depois de tocar o alvo 1, o preço pode
   tocar o stop e **só então** chegar a 3 ATR. Contar isso como sucesso atribuiria resultado a um
   braço que já teria parado. A única leitura válida é **refazer o caminho desde a entrada, com todas
   as saídas concorrentes ativas em cada braço**.

E o `mfe` não resolve isso — mas dizer que ele "é sempre nulo" seria errado, e a Astra corrigiu. Os
MFE/MAE atuais **descrevem o acompanhamento sob a política vigente**: podem demonstrar excursões e
impor limites, inclusive **acima do alvo creditado** num gap favorável (`excursions.py:116`), e um
extremo pode ser conhecido enquanto o outro fica nulo com `ambiguous = true`
(`excursions.py:135`, com teste dedicado em `test_shadow_outcomes.py:199`). O que eles **não** fazem
é identificar a distribuição de resultados de políticas que continuariam **depois** da saída. A
pergunta da cauda exige contrafactual, não excursão.

## Hipótese testável no Lab

**`D-TAIL` — é a mesma coisa que a candidata L1**, e isso é de propósito: não vale gastar duas
tentativas em duas escritas da mesma pergunta. Três braços sobre as **mesmas entradas congeladas**,
com stop, invalidação e horizonte inalterados, cada um com todas as saídas concorrentes ativas:

```
alvo_efetivo ∈ { 1.5·ATR₀ , 3.0·ATR₀ , 4.5·ATR₀ }   a partir da referência
```

**Métricas, corrigidas pela Astra** — a "fração do `R_net` total vinda do decil superior" que eu
tinha proposto é degenerada: com soma total perto de zero ela explode, e com soma negativa ela sai
negativa para os **melhores** ganhos.

- **Primária:** diferença **pareada** de média de `R_net` contra o braço base, com efeito mínimo
  relevante declarado antes.
- **Secundárias:** quantis da distribuição, média do decil superior, soma do decil superior dividida
  pelo **número total de entradas**, pior decil, duração, e a fração que termina em `target`, `stop`,
  `expired` e `invalidated`.

**Refutação:** Holm sobre os contrastes, incerteza por reamostragem em blocos, e a regra que a
revisão impôs: **ausência de evidência de melhora não é refutação** — refutar exige incerteza
estreita o bastante para excluir o benefício definido.

**Ressalva de desenho que quase passou:** aumentar o alvo mexe na própria validação
`stop < entrada < alvo` (`walker.py:45`), então um alvo maior pode **admitir entradas que a base
recusaria**. As entradas só permanecem pareadas se essa checagem for congelada na base.

## Por que pode falhar

1. **O horizonte limita a duração, e isso condiciona o experimento — mas não o invalida.** Com
   `horizon_s = 14400` (`momentum_v1.py:90`, contado da abertura de entrada, `progress.py:74`), o
   Lab não captura movimentos que levem mais de 4 horas. Subir o alvo pode converter `target` em
   `expired`. **O que a Astra retirou** da minha primeira redação: "qualquer cauda é truncada em 4
   horas" (não há teto de magnitude, só de duração) e "o resultado seria sobre o horizonte, não sobre
   o alvo" — variar só o alvo mede o efeito **dele**, condicionado ao horizonte de 4 h, e isso é um
   resultado válido. Que **alongar** o horizonte resolveria é outra hipótese, que exige outro
   contraste, muda exposição, atravessamento de funding
   ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]) e ocupação de slots
   (`episodes.py`) — e **não entra neste primeiro lote**.
2. **A cauda dele é de carteira e de meses.** Poucos vencedores enormes entre centenas de mercados ao
   longo de anos não é a mesma população que dezenas de acompanhamentos de 4 horas. A transferência
   é declarada e não demonstrada.
3. **O Lab não dimensiona nem diversifica**, que é como o trend following sistemático constrói a
   cauda. Ver a fronteira em [[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]].
4. **Alvo maior muda quatro coisas ao mesmo tempo** — taxa de alvo, duração, exposição a funding e
   número de invalidações —, e é por isso que a #10 do backlog sempre esteve separada de propósito.
5. **A cauda é justamente onde a amostra é pior.** Estimar contribuição de decil superior com poucas
   dezenas de outcomes é estimar o que menos se deixa estimar; o limiar editorial vale em dobro aqui.

## Segunda opinião (Astra)

Na curadoria, confirmou o fluxo do código (os três preços são montados em `record.py:137` e gravados
em `persist.py:59`; o plano de acompanhamento recebe **só** o `target1`) e derrubou o meu "nunca
sabemos", que virou "os outcomes atuais não fornecem taxa sistemática de chegada". Deu também o
cenário de falha que define o experimento: **alvo 1 → stop → 3 ATR** contado como sucesso do braço
maior.

Pôs a família Schwager/Clenow na categoria "regras objetivas de entrada e saída rendem hipóteses;
diversificação, pirâmides e resultado do sistema completo exigem exposição, capital e carteira", com
a advertência de que **entrevistas e resultados históricos não validam a nossa adaptação**. E colocou
"distribuição de R e alvo assimétrico" como a candidata **2** da fila dela, atrás da invalidação.

Na revisão da nota, corrigiu mais cinco coisas: **Clenow rejeita piramidação** nas próprias regras
publicadas (a atribuição era minha); "para de consumir barras" é impreciso — o walker materializa o
iterável e deixa de aplicar transições (`walker.py:169`); **MFE/MAE não são inúteis nem sempre nulos
juntos**, e podem inclusive ficar acima do alvo creditado num gap; a métrica de cauda que eu propus é
**degenerada** quando a soma total é perto de zero ou negativa; e "qualquer cauda é truncada em 4 h"
confunde teto de duração com teto de magnitude. Acrescentou a ressalva de que um alvo maior mexe na
validação `stop < entrada < alvo` e pode despareá as entradas.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] ·
[[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] · [[EXP-0001-momentum-v1]]

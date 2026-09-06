---
tags: [knowledge, nota, risco, saida]
tema: Gestão de risco e sizing
fonte: Kaminski & Lo, "When do stop-loss rules stop losses?" (Journal of Financial Markets 18, 2014, 234-254); rascunho anterior em SSRN 968338 (2007)
fonte_url: https://www.sciencedirect.com/science/article/abs/pii/S138641811300030X · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338
lido_em: 2026-09-06
evidencia: estudo revisado
hipotese_testavel: sim
astra: concorda
---

# Stops: quando eles param perdas (e quando só cobram pedágio)

## O que afirma

O artigo constrói um arcabouço analítico para o **prêmio de parada** (*stopping premium*): a
diferença entre o retorno esperado da estratégia **com** stop e o da mesma estratégia **sem** stop,
por unidade de tempo. O resultado central não é "stop é bom" nem "stop é ruim" — é que o **sinal do
prêmio depende do processo gerador dos retornos**.

Sob retornos i.i.d. (o caso "passeio aleatório"), o prêmio vale
`Δμ = p_fora × (r_f − μ)`: ele é negativo quando o ativo rende mais que a alternativa e existem
períodos fora do mercado, e nulo nos casos-limite. **Isso é mais fraco do que "sob passeio aleatório
o stop destrói valor"** — a perda de retorno pode conviver com redução de risco, e o resultado
depende de para onde o capital vai quando a posição está parada. Com momentum suficiente, ou com
regimes que tornem vantajoso ficar de fora, o prêmio pode ser positivo; mas autocorrelação positiva
ou troca de regime, **isoladamente**, não bastam.

## Onde foi mostrado

Empiricamente, na versão publicada em 2014: futuros do S&P e de Treasury notes de 10 anos, dados
**diários**, de 05/01/1993 a 07/11/2011, com o capital indo para os títulos quando a posição em
ações está parada e **custos de transação assumidos como zero**. Algumas políticas, em intervalos
mais longos, melhoram retorno e reduzem volatilidade — não é resultado geral para stops frequentes.

Cuidado bibliográfico registrado: o rascunho de 2007 no SSRN usa dados **mensais de 1950–2004**. São
amostras diferentes; misturar os números das duas versões seria erro de citação.

## Como mediríamos aqui

A `momentum_v1` tem **três** formas de sair perdendo, não uma: stop a 1,5 ATR, invalidação por
fechamento de 15 minutos abaixo do nível de rompimento, e expiração em 4 horas. E a simetria de
1,5 ATR é em torno do **fechamento de referência**, não da entrada efetiva
(`packages/core/hunter_core/strategies/momentum_v1.py`) — por isso 1 R "nominal na referência" não é
1 R na entrada. A invalidação observada no fechamento sai na **abertura seguinte**
(`services/strategy-worker/hunter_strategy_worker/walker.py`). Qualquer comparação que ignore isso
compara coisas diferentes.

O diagnóstico que eu tinha proposto — "taxa de stop alta com MFE grande prova que o stop destrói
valor" — **não se sustenta**: MFE grande antes do stop mede **devolução de ganho**, não destruição.
O cenário que refuta é banal: sobe, recua até o stop e depois desaba; o MFE era grande e o stop
protegeu. O que decide é o **contrafactual depois da saída**.

## Hipótese testável no Lab

**Comparação de três braços com entradas idênticas**, mesmo alvo, mesmo horizonte, mesmos custos
(funding incluído):

Os braços deste experimento levam o prefixo `STOP-` para não se confundirem com os braços `INV-` de
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]], que testam outra coisa (ressalva da Astra).

| Braço | Stop 1,5 ATR | Invalidação por fechamento | Expiração 4 h |
|---|---|---|---|
| `STOP-A` (atual, `momentum_v1`) | sim | sim | sim |
| `STOP-B` | **não** | sim | sim |
| `STOP-C` | sim | **não** | sim |

- Métrica pareada: diferença líquida em R por episódio, **mantendo o R original fixo** como
  denominador nos três braços — mudar o denominador quando o stop sai transformaria a comparação em
  outra coisa.
- Reportar também **perdas de cauda** (pior decil), não só a média: o argumento a favor do stop é de
  cauda, e uma expectancy média igual com cauda muito pior é resposta, não empate.
- Diagnóstico de MFE **sem descartar nulos e sem convertê-los em zero**: usar
  `mfe_complete_bars`, os limites e a cobertura já produzidos em
  `services/strategy-worker/hunter_strategy_worker/excursions.py` para classificar cada outcome, em
  relação a um limiar, como **comprovadamente acima / comprovadamente abaixo / indeterminado**.
- Sensibilidade da convenção: onde stop e alvo cabem na mesma vela, o modelo hoje favorece o **stop**
  (convenção pessimista, `walker.py`). Reportar quantos casos são esses e como o resultado muda se a
  ordem inverter.
- Refutação: `δ` pré-registrado; IC95% por blocos temporais sobre a diferença pareada; intervalo
  inteiramente dentro de `±δ` = efeito pequeno; intervalo largo = **inconclusivo**, mesmo com
  p-valor alto.

Sobre "o nosso retorno de 15 minutos é próximo de passeio aleatório": não vale tentar decidir isso
com teste de eficiência de mercado, que não muda decisão nenhuma. O diagnóstico útil é
**previsibilidade economicamente relevante condicionada ao nosso sinal**: autocorrelações e razões
de variância entre 15 minutos e 4 horas como pano de fundo, e retorno futuro condicionado ao sinal
**e ao acionamento da saída** como medida principal, com validação cronológica, janelas sobrepostas
separadas e bootstrap por blocos que preserve os movimentos comuns entre moedas.

## Por que pode falhar

- **Autocorrelação agregada perto de zero pode esconder previsibilidade depois de rompimentos ou
  depois de perdas.** Concluir pelo universo inteiro removeria uma saída útil exatamente nos
  episódios que selecionamos.
- **Remover o stop muda o risco, não só o retorno.** Um braço `STOP-B` com expectancy melhor e cauda pior
  não é vitória; e no produto real o stop é também o que dimensiona a posição.
- Custos: Kaminski & Lo assumem custo zero. No nosso caso o custo é o item que mais aperta o R
  ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]).
- Extrapolação de frequência: o resultado empírico deles é diário/mensal em dois contratos; o nosso
  é de 15 minutos em dezenas de perpétuos.

## Segunda opinião (Astra)

Confirmou (a) e corrigiu (b), (c) e (d). Correções aceitas e incorporadas: a fórmula
`Δμ = p_fora × (r_f − μ)` sob i.i.d. e a consequência de que passeio aleatório **sozinho** não
implica que o stop destrói valor; momentum ou regime, isoladamente, não bastam para prêmio positivo;
a amostra da versão de 2014 é S&P e Treasury de 10 anos, diária, 1993–2011, com custo zero, e o
rascunho de 2007 é mensal 1950–2004 — não misturar. Must-fix aceitos: MFE grande antes do stop mede
devolução, não destruição, e exige o contrafactual pós-saída; a simetria de 1,5 ATR é na referência,
não na entrada; a invalidação sai na abertura seguinte. Adotei integralmente o desenho de três
braços que ela propôs, o R original fixo como denominador e a classificação
acima/abaixo/indeterminado para o MFE.

Divergência: nenhuma. Frase dela que fica como regra: o artigo justifica **investigar** o stop; não
justifica chamar 1,5 ATR de apertado nem removê-lo antes da comparação.

## Relacionados

[[Strategy Backlog]] · [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[EXP-0001-momentum-v1]] · [[Risk Engine]]

---
tags: [knowledge, nota, volatilidade, atr, risco]
tema: Regime de mercado e volatilidade
fonte: Wilder, "New Concepts in Technical Trading Systems" (1978) — conceito de True Range e média suavizada; Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & van Hemert, "The Impact of Volatility Targeting" (Journal of Portfolio Management, 2018)
fonte_url: https://www.man.com/insights/the-impact-of-volatility-targeting · https://www.tandfonline.com/doi/full/10.1080/0015198X.2020.1790853
lido_em: 2026-09-06
evidencia: estudo revisado (Harvey et al.) · texto clássico de praticante (Wilder)
hipotese_testavel: sim
astra: concorda
---

# ATR e escala por volatilidade: quatro papéis que não são o mesmo

## O que afirma

Wilder introduziu o **True Range** — a maior entre a amplitude da barra e as distâncias do fechamento
anterior às extremidades atuais — e a média suavizada dele, que hoje chamamos de ATR de Wilder. A
proposta original era dupla: distância de stop proporcional à volatilidade recente e dimensionamento
de posição na mesma unidade. É texto de praticante, não estudo revisado, e não traz teste estatístico.

Harvey e coautores testaram **alvo de volatilidade** em 60 ativos, com dados começando já em 1926:
escalar a exposição pela volatilidade estimada reduz consistentemente a probabilidade de retornos
extremos e a **volatilidade da volatilidade**, mas melhora o índice de Sharpe **só** em ações e
crédito naquela amostra. O mecanismo apontado é o efeito alavancagem — a relação negativa entre
retorno e volatilidade em ativos de risco —, que faz a escala por volatilidade introduzir momentum
de curto prazo na estratégia.

## Onde foi mostrado

60 ativos, séries longas, exposição escalada continuamente. Uma correção que preciso registrar: o
estudo **não** exige carteira multiativo — ele também examina ativos individuais. O que ele exige é
**escala da exposição**. E "melhora só em ações e crédito" descreve aquela amostra, não uma
impossibilidade universal.

## Como mediríamos aqui

No Lab o ATR faz **quatro** coisas diferentes, e confundi-las é a origem de quase todo erro nesta
área:

1. **Geometria:** stop e alvo a 1,5 ATR do fechamento de referência.
2. **Seleção:** `atr_pct_min = 0,003` e `atr_pct_max = 0,05` decidem quais sinais existem
   (`momentum_v1.py`). Logo, qualquer análise nossa é **dentro dessa população selecionada**.
3. **Normalização da métrica:** o R em que medimos tudo.
4. **Dimensionamento de posição:** **não existe** no Lab — não há carteira.

Como (4) não existe, a evidência de Harvey et al. sobre Sharpe não transfere para cá; mas também não
transfere para os stops: reduzir caudas escalando exposição é outra operação que colocar um stop.
Nenhuma das duas fontes valida "1,5 ATR".

Duas armadilhas de implementação, verificadas:

- **Qual ATR.** A `momentum_v1` grava `atr_pct_15m` calculado por janela móvel com reseed
  (`rolling_window_v1`, documentado em `.claude/state/notes-S1.md` §3), enquanto `atr_14_pct` do
  Feature Engine usa checkpoint ancorado (`trend.py`). São **calculadoras diferentes**. A análise tem
  de usar o valor **efetivamente persistido na decisão**, senão o decil muda e estamos analisando uma
  medida que não gerou o sinal.
- **Qual R.** O R nominal (1,5·ATR) e o R efetivo não são o mesmo número: com a entrada na
  referência, `(P_entry − stop)/C = 1,5·ATR% + 0,0006`, ou seja **45 bps viram 51 bps** no piso de
  ATR%. E há uma armadilha: uma entrada **mais cara** aumenta o denominador e portanto **reduz**
  custo/R, ao mesmo tempo que encolhe o espaço até o alvo — ver
  [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]. O denominador implementado é `P_entry − stop`
  (`services/strategy-worker/hunter_strategy_worker/pricing.py`), **não** 1,5 ATR: inclui o
  deslocamento até a entrada e o preço sintético. Usar o risco nominal distorceria exatamente a
  comparação custo/R.

## Hipótese testável no Lab

**Não é variante de estratégia; é análise diagnóstica pré-registrada:** expectancy líquida em R por
**decil de ATR% na decisão**, sobre a coorte existente, para descobrir se a estratégia se comporta de
forma diferente por faixa de volatilidade.

- Eixo primário: **ATR%**. Custo/R fica como **decomposição secundária**, não como eixo de
  agrupamento: com custos proporcionais constantes, o custo relativo ao risco nominal varia
  aproximadamente como `1/ATR%`, então trocar o eixo tende só a inverter a ordenação, sem separar
  mecanismos.
- **Nunca agrupar por custo realizado/R**: preço de saída e funding realizado dependem do caminho
  futuro. Para classificar, só uma estimativa congelada com informação disponível na decisão.
- Reportar retorno **antes** dos custos e os descontos em R, todos com o **mesmo denominador**, sem
  descontar spread e slippage duas vezes — eles já estão nos preços sintéticos.
- Pré-registro: congelar versão, coorte, **campo de ATR**, período UTC e população; calcular os
  limites dos decis numa janela histórica definida e mantê-los na avaliação futura; fixar tratamento
  de empates.
- Mostrar **todos** os decis, com emitidos, entradas, maturados, avaliáveis, censurados e funding
  ausente. Nada desconhecido vira zero.
- Secundários por faixa: duração e proporção de `stop`, `target`, `expired` e `invalidated` — é o que
  torna uma diferença de expectancy interpretável.
- Composição por mercado e período por decil: decis agrupam **moedas diferentes**, não só regimes da
  mesma moeda.

## Por que pode falhar

- **Estabilidade não prova boa normalização.** Expectancy igualmente **negativa** em todos os decis é
  perfeitamente estável. E "sem diferença significativa" pode ser só falta de potência: para afirmar
  estabilidade é preciso `δ` econômico pré-definido e intervalos simultâneos compatíveis com
  equivalência.
- **Garimpo pós-hoc.** Escolher depois o "melhor decil" para filtrar sinais cria uma **hipótese nova
  de estratégia**, que exige validação futura própria — não é conclusão desta análise.
- Dez decis são resolução **descritiva**; não garantem amostra suficiente em cada um.
- A análise vive dentro da faixa 0,3%–5% já selecionada; nada diz sobre fora dela.

## Segunda opinião (Astra)

Concorda com fazer a análise diagnóstica antes de qualquer variante, e com a ressalva de que ela pode
achar fragilidade condicionada à volatilidade mas **não** demonstra que 1,5 seja o melhor
multiplicador. Duas correções aceitas: (1) Harvey et al. **não** exigem carteira multiativo — exigem
escala de exposição, e também examinam ativos individuais; a frase certa é que os resultados não
validam stops de 1,5 ATR nem o Sharpe do Lab, e que "só ações e crédito" descreve aquela amostra;
(2) o ATR aqui **também seleciona sinais** pelo filtro 0,3%–5%, então a análise mede comportamento
dentro de população selecionada. Must-fix incorporados: usar o ATR persistido na decisão
(`atr_pct_15m`, não `atr_14_pct`), usar `P_entry − stop` como R, e não confundir estabilidade com
qualidade da normalização. Aceitei também manter ATR% como eixo primário e custo/R como decomposição.

Divergência: nenhuma.

## Relacionados

[[Strategy Backlog]] · [[KB-0005-stops-quando-eles-param-perdas]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[EXP-0001-momentum-v1]] ·
[[Features]]

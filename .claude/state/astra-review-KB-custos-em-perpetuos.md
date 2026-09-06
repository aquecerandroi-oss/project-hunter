**RESUMO**

Sua aritmética nominal está correta. A conclusão precisa ser mais estreita: **custos fixos em bps penalizam estruturalmente operações com pouca distância de stop; isso ainda não demonstra que elevar `atr_pct_min` melhora a estratégia.**

Eu faria primeiro a decomposição diagnóstica e depois testaria uma única variante prospectiva de filtro. Não aumentaria o alvo nesta mesma intervenção.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, como `quant-engineer`.

**TESTES**

Conferência aritmética com `Decimal`, via `uv run --no-sync --offline python -B -`, recebendo o programa pela entrada padrão. Saída real:

```text
atr_pct nominal_bps effective_bps cost_over_nominal cost_over_effective
0.003 45.0000 51.0000 0.444444 0.392157
0.01 150.000 156.0000 0.133333 0.128205
0.05 750.000 756.0000 0.026667 0.026455
p_equilibrium 0.57768232
p_67 0.53731343 p_75 0.53333333
E_67 -0.07893731
floor_nominal 0.0088888889
floor_no_gap 0.0084888889
```

A primeira tentativa com `-c` falhou por aspas do PowerShell; a execução acima terminou com código zero. Não rodei suítes nem consultei novamente a VPS; usei a avaliação registrada na memória.

**MUST-FIX**

**1. Separar risco nominal, denominador implementado e custo total.**

O código define entrada e saída sintéticas, cobra as taxas separadamente e divide por `P_entry − stop`: [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47), [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74). Stop e alvo partem do fechamento de referência: [momentum_v1.py:217](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217).

Definindo:

- \(C\): fechamento de referência; \(O\): abertura de entrada; \(B\): saída antes dos custos;
- \(a=0,0006\), \(f=0,0004\), \(v=ATR/C\);
- \(E=O(1+a)\), \(X=B(1-a)\), \(S=C-1,5ATR\).

O custo exato por unidade, **sem funding**, relativamente ao movimento bruto \(B-O\), é:

\[
K=a(O+B)+f(E+X)
\]

Portanto:

\[
R_{\text{net}}=\frac{B-O-K-F}{E-S}
\]

Os **20 bps** são corretos como aproximação quando \(B\approx O\). Não incluem funding e não são uma tarifa verificada.

Se \(O=C\), o denominador efetivo é:

\[
(E-S)/C=1,5v+0,0006
\]

Assim, no piso atual, são **51 bps**, e aproximadamente **39,22% de R** em custos, contra **44,44% do risco nominal**. Havendo deslocamento até a abertura:

\[
E-S=1,5ATR+(O-C)+0,0006O
\]

Logo, não existe uma conversão universal de ATR% para custo/R efetivo.

**Cenário de falha:** escrever “sobra \(1-0,4444\) R no alvo” mistura denominadores. Num exemplo sintético com abertura igual à referência, ATR%=0,003, saída exatamente no nível e funding zero, calculei **alvo líquido +0,489314 R** e **stop líquido −1,273628 R**. Spread/slippage já estão nos preços: descontá-los novamente também falsearia o resultado.

**2. Enunciar 57,77% como equilíbrio condicional, estimado na própria amostra.**

A conta está correta:

\[
p^*=\frac{1,1296}{0,8258+1,1296}=0,57768232
\]

Eu escreveria:

> Entre os encerramentos por alvo ou stop com R líquido conhecido nesta avaliação, mantendo fixas as médias observadas de +0,8258 R e −1,1296 R, a proporção de alvos que zeraria a média desse subconjunto seria aproximadamente 57,77%. A proporção observada nesse mesmo subconjunto foi 36/67, ou 53,73%.

Isso **exclui invalidados e expirados**, além dos casos sem R conhecido. Não é taxa de equilíbrio da estratégia completa, nem estimativa validada de uma exigência futura.

Os **40/75 = 53,33%** incluem quatro alvos e quatro stops adicionais sem R líquido conhecido. Podem aparecer como métrica de cobertura, mas não são a população das médias usadas na equação. As contagens estão em [EXP-0001:479](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:479) e [EXP-0001:487](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:487).

**Cenário de falha:** declarar equilíbrio global ao alcançar 57,77% ignora os 24 invalidados com média −0,5768 R registrados nessa avaliação. Com os números fornecidos, os 67 toques têm média aproximada **−0,07894 R**; incluindo os invalidados, as somas registradas dão **−0,21024 R nos 91 casos**. A diferença entre 53,73% e 57,77% é descritiva, não uma demonstração de significância estatística.

**3. Qualificar a descrição do funding.**

Oito horas e 00:00/08:00/16:00 UTC descrevem o calendário padrão. **0,01% é o componente padrão de juros por oito horas, não funding fixo nem cobrança adicional a somar ao funding calculado.** O pagamento ocorre entre traders; não é comissão de funding da exchange. A taxa pode representar pagamento ou recebimento.

A documentação usa ±0,3% para BTCUSDT como exemplo, mas admite ajustes de limites e frequência, inclusive frequência horária ao atingir teto/piso. Não apresentaria esses valores como constantes universais. [Documentação da Binance](https://www.binance.com/en-NZ/support/faq/detail/360033525031).

**Cenário de falha:** assumir que uma operação com horizonte de quatro horas não atravessa funding pode omitir pagamentos. Também não cabe chamar o filtro baseado em 20 bps de “limite de custos totais”.

**NICE-TO-HAVE**

Mostrar por faixa de ATR%: movimento bruto/R, spread e slippage/R, taxas/R, funding/R e deslocamento referência→entrada. Todos com **o mesmo denominador efetivo**. Isso distingue custo de execução, geometria e comportamento do mercado.

**O QUE EU FARIA DIFERENTE**

**Sobre elevar o piso ou ampliar o alvo:** entre essas duas candidatas, priorizaria testar o piso. Ele enfrenta diretamente a hipótese de movimentos pequenos diante dos custos. Ampliar o alvo muda outra coisa: aumenta o ganho possível, mas pode reduzir acertos, prolongar exposição e aumentar invalidações, expirações e funding. Não reduz materialmente custo/risco inicial.

O seu cálculo:

\[
atr\_pct_{\min}=\frac{0,002}{0,15\times1,5}=0,008888\ldots
\]

é válido como **orçamento aproximado de execução sobre risco nominal**. Com entrada sem deslocamento e denominador efetivo, a aproximação seria **0,0084889**. Eu não substituiria um pelo outro como se o segundo fosse um limiar universal: ambos dependem das hipóteses declaradas.

Há uma armadilha adicional: **uma entrada mais cara aumenta \(E-S\), reduzindo custo/R, enquanto diminui o espaço até o alvo**. Portanto, qualquer futura regra diretamente baseada em custo/R precisa examinar também o ganho líquido potencial até o alvo. A validação atual exige somente `stop < entrada < alvo`: [walker.py:44](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:44).

**Sobre calibrar na mesma amostra:** descobrir o problema nela é legítimo; escolher o filtro e usar a melhora nessa mesma amostra como prova é seleção retrospectiva. Mesmo escolher “15%” é uma escolha de parâmetro, caso o valor tenha sido preferido após observar resultados. Uma justificativa econômica não devolve independência aos dados. [Bailey e coautores](https://www.davidhbailey.com/dhbpapers/overfitting.pdf).

**Minha proposta concreta:**

1. **Agora:** corrigir a nota para “pressão estrutural dos custos sob as hipóteses do Lab”, sem atribuir a perda observada exclusivamente ao piso.
2. **Diagnóstico:** usar ATR% persistido na decisão; decompor custos com R efetivo; incluir invalidados, expirados e cobertura de funding. A memória já recomenda esse desenho: [KB-0007:64](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0007-atr-e-escala-por-volatilidade.md:64).
3. **Candidata futura:** congelar uma única variante, por exemplo `atr_pct_min=0,0089`, mantendo alvo, stop, horizonte e invalidação. Descrevê-la como filtro nominal aproximado, não garantia de custo efetivo ≤15%.
4. **Validação:** comparar controle e candidata no mesmo período futuro e universo; congelar datas, métrica principal, tratamento de ausências e critério econômico antes da coleta. Avaliar expectancy líquida de todos os encerramentos avaliáveis e quantidade de oportunidades preservadas; considerar dependência entre mercados em blocos temporais.
5. **Não selecionar vencedora por plantão.** Se testar outros pisos ou alvos, registrar todas as tentativas. A amostra já examinada fica como desenvolvimento.

**CONCORDO COM**

A pressão relativa dos custos aumenta mecanicamente quando a escala do movimento diminui. Seu diagnóstico justifica investigação e uma candidata. **Ainda não justifica concluir que o piso maior terá expectancy melhor.**

**OBSIDIAN**

- **KB-0008 — Custos em perpétuos e o R que sobra:** incluir fórmulas exatas, ressalvas do funding e enunciado condicional dos 57,77%.
- **KB-0007 — ATR e escala por volatilidade:** acrescentar o exemplo 45→51 bps e a armadilha de reduzir custo/R piorando a entrada.
- **EXP-0001 — momentum em modo sombra:** acrescentar análise datada dos 67/75/91 casos, preservando avaliações anteriores.
- **Strategy Backlog:** registrar o filtro nominal de custos como candidata ainda não validada, com teste prospectivo separado.
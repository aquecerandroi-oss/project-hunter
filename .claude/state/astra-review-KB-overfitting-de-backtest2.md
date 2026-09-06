**1. Está essencialmente correto, com três precisões.** PBO via CSCV estima a frequência com que a vencedora dentro da amostra fica abaixo da mediana fora dela. DSR ajusta a significância do Sharpe por seleção entre tentativas, tamanho amostral e não normalidade; não elimina automaticamente dependência temporal. [PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), [DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

O exemplo é **aproximadamente 45 configurações independentes, cinco anos, Sharpe verdadeiro zero**, sob retornos IID normais e a aproximação do artigo: o **máximo esperado do Sharpe anualizado IS chega a ≈1**, com Sharpe esperado OOS zero. Não é garantia de obter 1. MinBTL depende do número de tentativas e do Sharpe de referência; distingue-se de MinTRL, comprimento necessário para testar um Sharpe individual contra um limiar com confiança especificada. [Artigo original](https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf).

**2. Para o Lab, eu usaria inferência sobre expectancy.** Média(R)/desvio(R) pode ser estudada como efeito padronizado por entrada, mas aplicar DSR diretamente não valida a média em R nem produz Sharpe de carteira.

Minha proposta: hipóteses pré-especificadas sobre expectancy líquida ou diferença frente à referência; **bootstrap conjunto em blocos temporais**, preservando mercados simultâneos e dependência entre variantes; p-valores válidos + Holm. Holm aceita dependência entre testes, mas não conserta p-valores inválidos. Para ICs simultâneos, usar procedimento próprio — por exemplo, Bonferroni sobre ICs por blocos; seis ICs individuais de 95% não bastam. [Holm, documentação estatística](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html).

Isso complementa o contrato de [SHADOW-LAB.md:19](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19). **Se as seis candidatas nasceram da inspeção desses mesmos resultados, Holm apenas sobre essas seis não apaga a seleção adaptativa:** a confirmação precisa de dados futuros reservados.

**3. O registro ajuda, mas não resolve sozinho.** Eu registraria antes de rodar: ID, hipótese, parâmetros/delta, hashes de código, população, custos, métrica primária, família de testes, início/fim UTC, maturação e regra de análise. Registrar também descartadas; distinguir candidatas propostas de tentativas efetivamente avaliadas e informar o histórico acumulado.

Para verificabilidade: o responsável publica o registro no remoto **antes do início da janela futura**, com SHA vinculado a evento de PR/CI datado pelo servidor. Recomendo branch protegida contra reescrita/exclusão e CI que rejeite alteração de registros anteriores; correções entram como novos eventos. **Data local de commit é ajustável; assinatura sozinha não prova anterioridade.** [Git](https://git-scm.com/docs/git-commit), [proteções GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

Isso comprova o compromisso publicado, não a inexistência de testes privados omitidos. É rastreabilidade útil, com limite explícito.

Nenhum arquivo modificado; nenhum teste executado.

**OBSIDIAN**

- **Nova nota: Overfitting de backtest** — definições, condições das 45 tentativas e limites do DSR.
- **Novo Registro de tentativas** — protocolo, eventos acrescentados e evidências remotas.
- **Strategy Performance** — inferência em R, multiplicidade e confirmação futura.
**RESUMO**

**(a) Correto:** stopping premium é \(E[r_{\text{com stop}}]-E[r_{\text{sem stop}}]\), por unidade de tempo.

**(b) Correto com condição:** sob retornos IID, \(\Delta\mu=p_{\text{fora}}(r_f-\mu)\). É negativo se o ativo rende mais que a alternativa e há períodos fora; zero nos casos-limite. Portanto, passeio aleatório **sozinho** não implica “stop destrói valor”. A perda de retorno pode coexistir com redução de risco.

**(c) Correto como possibilidade:** momentum suficiente ou regimes que tornem vantajoso ficar fora podem produzir prêmio positivo; autocorrelação positiva ou mudança de regime não bastam, isoladamente. [Texto dos autores, §§3–4, preprint de 2013](https://www.scribd.com/document/428236246/When-Do-Stop-Loss-Rules-Stop-Losses).

**(d) Correto com ressalvas:** futuros do S&P e de Treasury notes de **10 anos**, dados diários de **05/01/1993 a 07/11/2011**. Algumas políticas em intervalos mais longos melhoram retorno e volatilidade; não é um resultado geral para stops frequentes. Faltam registrar **reentrada**, ativo de destino e que os autores assumem custos de transação zero. [Método, §§3 e 5](https://www.scribd.com/document/428236246/When-Do-Stop-Loss-Rules-Stop-Losses); [publicação de 2014](https://www.sciencedirect.com/science/article/pii/S138641811300030X).

**Cuidado bibliográfico:** SSRN 968338 apresenta o rascunho de **2007**, com dados mensais de **1950–2004**. Não misture seus números com 2014. [SSRN](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID968338_code665721.pdf?abstractid=968338).

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Conferência documental e leitura do código; nenhum teste estatístico ou replay executado.

**MUST-FIX**

**(1) A aplicação proposta ainda não demonstra destruição de valor.**

- **MFE grande antes do stop mede devolução de ganho.** Cenário: sobe, recua até o stop e depois desaba. O MFE era grande, mas o stop protegeu. É necessário medir o resultado **contrafactual depois da saída**.
- **Autocorrelação agregada próxima de zero pode esconder previsibilidade após rompimentos/perdas.** Concluir pelo universo inteiro pode eliminar uma saída útil justamente nos episódios selecionados.
- A simetria de 1,5 ATR é em torno do **fechamento de referência**, não da entrada efetiva: [momentum_v1.py:217](/C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217). A invalidação observada no fechamento sai na abertura seguinte: [walker.py:136](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:136), [walker.py:77](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:77). Ignorar isso distorce a comparação.

**NICE-TO-HAVE**

**(2) Testaria previsibilidade economicamente relevante, sem tentar “provar eficiência”.**

Estimar autocorrelações e razões de variância entre 15 minutos e 4 horas como diagnóstico; priorizar retorno futuro **condicionado ao sinal e ao acionamento da saída**. Usar validação cronológica, separar janelas sobrepostas e bootstrap por blocos temporais preservando movimentos comuns entre moedas. Pré-definir uma margem econômica \(\delta\): intervalo inteiramente dentro de ±δ indica efeito pequeno; intervalo largo indica **inconclusão**, mesmo com p-valor alto.

**O QUE EU FARIA DIFERENTE**

**(3) MFE nulo não inviabiliza.** Já existem `mfe_complete_bars`, limites e cobertura em [excursions.py:143](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:143). Para um limiar, classificar **comprovadamente acima / abaixo / indeterminado**, sem excluir nulos nem convertê-los em zero.

O diagnóstico principal seria replay com velas de 1 minuto contínuas até 4 horas. Onde stop e alvo cabem na mesma vela, avaliar sensibilidade à ordem: hoje o modelo favorece o stop, por convenção [walker.py:155](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:155).

**(4) Compararia entradas idênticas em três braços:** atual; sem stop ATR, preservando invalidação; sem invalidação, preservando stop. Mesmo alvo, horizonte, quantidade e custos, incluindo funding. Medir diferença líquida pareada e perdas de cauda; usar retorno percentual ou **R original fixo**, evitando mudar o denominador. Depois confirmar prospectivamente e avaliar separadamente o efeito sobre reentradas.

**CONCORDO COM**

O artigo justifica investigar o stop. Não justifica chamar 1,5 ATR de apertado nem removê-lo antes dessa comparação.

**OBSIDIAN**

- **Stops — quando reduzem perdas:** nova nota com versões bibliográficas, condições e limites da transferência.
- **EXP-0001-momentum-v1:** acrescentar hipótese e protocolo contrafactual, preservando o protocolo congelado.
- **Strategy Performance:** documentar diagnóstico por limites de MFE e diferença líquida pareada.
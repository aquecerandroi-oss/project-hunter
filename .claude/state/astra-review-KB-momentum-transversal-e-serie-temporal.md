**RESUMO**

1. **Gate defensável como hipótese nova; não validado pelos artigos.** Eu escreveria “a transferência entre horizontes **não está demonstrada**”, em vez de “não se transfere”. Jegadeesh–Titman estudam seleção relativa entre ações; Moskowitz–Ooi–Pedersen, o retorno próprio em futuros. Nenhum demonstra `return_24h > 0` como filtro de operações de 4 h em cripto. Chamá-lo de *gate* não elimina essa lacuna. [JT1993](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf), [MOP2012](https://fairmodel.econ.yale.edu/ec439/mosk.pdf).

2. **Começaria por 24 h**, pela simplicidade e pelo limiar natural zero, sem alegar superioridade empírica. Sete dias é outra hipótese, com maior necessidade de histórico. Distância da máxima mede posição na faixa, não direção da tendência; também exige escolher um limiar. **Correção prática:** a calculadora aceita 1.440 minutos, mas `return_24h` não consta do conjunto registrado atualmente ([price.py:28](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:28), [price.py:139](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:139)).

3. **O risco de apenas cortar amostra é real e ainda não quantificado.** Sobre os mesmos episódios-base, registre aprovados e bloqueados, acompanhando ambos. Se `p` é a fração aprovada:
   `E_gate − E_base = (1−p) × (E_aprovados − E_bloqueados)`.
   Expectancies iguais significam seleção sem ganho; aprovação quase universal significa pouco efeito. Reporte retenção, frequência e diferença com intervalo de confiança por blocos temporais, mantendo os mercados juntos para preservar correlação.

4. **Mudaria a refutação:** ≥100 outcomes avaliáveis **no grupo aprovado** e ≥30 dias são piso, não garantia de precisão. Pré-registre ganho mínimo relevante `δ`, corte de avaliação e comparação prospectiva simultânea. Para `Δ = E_gate − E_base`: limite superior do IC95% abaixo de `δ` refuta o ganho relevante; limite inferior acima de `δ` sustenta; demais casos são inconclusivos. Use horizontes maturados e reporte censura, funding indisponível e tamanho do grupo bloqueado.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; parecer documental, sem estimar resultados.

**MUST-FIX**

- **Fixar a semântica do gate:** apenas admissão, sem alterar saídas nem rearme. Hoje `NOT_TRIGGERED` pode rearmar o episódio ([episodes.py:58](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:58)). Cenário: o gate oscila, rearma e gera entradas adicionais; a comparação deixa de medir apenas filtragem. Primeiro avaliaria o filtro nos episódios-base comuns.
- **Congelar o dado temporal:** retorno calculado até `source_bar_close`, disponível na decisão; ausência é indisponibilidade, não retorno negativo. Caso contrário, uma leitura posterior pode contaminar a seleção.

**NICE-TO-HAVE**

Examinar estabilidade por mercado/regime; deixar 7 dias e distância da máxima para variantes separadas.

**O QUE EU FARIA DIFERENTE**

Corrigiria a nota acadêmica: **1,49%/mês é uma configuração específica** — formação de 12 meses, manutenção de 3 e intervalo de uma semana. A dissipação ocorre nos dois anos **seguintes ao primeiro ano**. [JT1993](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf).

**CONCORDO COM**

Preservar a v1 e testar uma única alteração, com expectancy líquida em R como métrica principal.

**OBSIDIAN**

- **Momentum — evidência e limites** *(nova)*: distinguir resultados acadêmicos da hipótese intradiária.
- **Strategy Backlog**: cadastrar o gate com dependência da feature e protocolo pré-registrado.
- **Features**: esclarecer disponibilidade efetiva de `return_24h`.
- **Strategy Performance**: documentar comparação por episódios comuns, precisão e inconclusividade.
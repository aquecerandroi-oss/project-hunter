**RESUMO**

**O núcleo aritmético está correto para uma decomposição contábil dos trades já admitidos pelo Lab.** Concordo com U fixo, k* como razão de somas e bootstrap dessa razão por clusters. Corrigiria a cobertura apresentada, o alcance dos contrafactuais e as justificativas das candidatas antes de publicar a nota.

Revisão como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Executei, com sincronização de dependências, bytecode e cache desativados:

- `uv run pytest .claude/state/lab-cost-sweep/test_sweep.py -q` → **`14 passed, 1 warning in 2.09s`**. Aviso: `asyncio_mode` desconhecido porque desativei o carregamento automático de plugins.
- `uv run python .claude/state/lab-cost-sweep/check.py` → confirmou **17.979 linhas**, máximo de **7,490630506978846e-06** em `r_multiple` e **7,275247071447666e-11** em `r_ex_funding`.
- `uv run python .claude/state/lab-cost-sweep/extra.py` → reproduziu **178 dias / 1.514 trades** para v14, efeito +0,10 R.

O primeiro `check.py` falhou apenas na impressão Unicode; reexecutei com saída UTF-8 e terminou normalmente.

**MUST-FIX**

1. **Trocar “recomposição exata do cenário” por “reprecificação condicionada às entradas e saídas observadas”.**

   O comentário diz que o caminho independe do custo, mas a admissão exige `stop < entry_price(open, costs) < target1`. Portanto, **a população admitida depende do custo**. [sweep.py:18](C:/dev/project-hunter/.claude/state/lab-cost-sweep/sweep.py:18), [walker.py:42](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:42).

   **Falha concreta:** com O=S, o Lab admite a entrada por causa dos 6 bp adversos; sem esse ajuste, a mesma regra recusaria a geometria. U fixo resolve a divisão, mas não transforma esse trade em execução admissível sob outro modelo.

   Preserve U e a população para este diagnóstico. Declare que maker/rebate pressupõem preenchimento; retirar funding de um perpétuo produz uma **sensibilidade sem funding sobre preços perpétuos**, não um backtest spot. Os cenários atuais mantêm O e B e alteram somente custos/funding. [sweep.py:114](C:/dev/project-hunter/.claude/state/lab-cost-sweep/sweep.py:114).

2. **Separar população completa e população com funding conhecido em todas as métricas e contagens.**

   O relatório calcula `G_ex_all`, mas, havendo funding em alguma linha, apresenta G e seus ICs apenas no subconjunto financiado. Dias, mercados e atividade continuam vindo do conjunto completo. [run.py:53](C:/dev/project-hunter/.claude/state/lab-cost-sweep/run.py:53), [run.py:98](C:/dev/project-hunter/.claude/state/lab-cost-sweep/run.py:98).

   **Falha concreta, medida nesta revisão:** replay v10 `c7d138eb`:
   - conjunto completo: **798 trades, 89 dias, G=+0,0728 R**;
   - funding conhecido: **300 trades, 33 dias, G=+0,1930 R**.

   A tabela associa +0,193 R a uma linha com “89 dias”, favorecendo uma leitura incorreta da cobertura. [results.txt:115](C:/dev/project-hunter/.claude/state/lab-cost-sweep/results.txt:115).

   Publicar **G de todos**, G pareado aos líquidos, respectivas contagens e cobertura dos excluídos. Excluir funding desconhecido do líquido está certo; isso não torna a ausência aleatória.

   Também:
   - o cenário sem funding pode usar todos os trades; hoje ele herda a exclusão de `fts`;
   - em spot, chamar o valor de **líquido reconstruído sem funding**, quando `r_multiple` é nulo. O fallback para `r_ex_funding` não é “R líquido como gravado em `r_multiple`”. [run.py:66](C:/dev/project-hunter/.claude/state/lab-cost-sweep/run.py:66), [run.py:83](C:/dev/project-hunter/.claude/state/lab-cost-sweep/run.py:83), [check.txt:3](C:/dev/project-hunter/.claude/state/lab-cost-sweep/check.txt:3).

3. **Retirar a atribuição causal “horizonte maior amortiza o custo de 0,175 para 0,08 R”.**

   A v1 já tinha horizonte de **240 minutos**. A v7 também tem 240 minutos, mas mudou stop/alvos; seu stop é 2 ATR. [EXP-0009:75](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0009-mean-reversion-pullback-em-tendencia.md:75), [mean_reversion-v7.md:31](C:/dev/project-hunter/obsidian/03-TRADING/Estrategias/mean_reversion-v7.md:31).

   **Falha concreta:** escolher aumentar somente o prazo esperando repetir uma economia causada por U maior e/ou outra composição de entradas. Pela fórmula, prolongar o prazo, mantendo O e U, não reduz mecanicamente o pedágio; ainda pode acrescentar funding.

   A candidata continua possível, mas sua justificativa deve ser **hipótese de trajetória/preço**, não economia de custo demonstrada por essa comparação.

4. **A mediana de 15 bp não pode decidir viabilidade econômica.**

   **Falha concreta:** com pesos iguais, 51% dos trades custando 10 bp e 49% custando 30 bp dão mediana de 10 bp, mas média de 19,8 bp. Passariam pelo filtro embora ultrapassassem k*=16,1 bp da v14.

   Para custo variável por trade, o equivalente compatível com k* é:

   \[
   k_{\rm efetivo}=\frac{\sum_i h_i k_i}{\sum_i h_i}.
   \]

   Melhor ainda: converter cada custo de entrada **e saída** em R e calcular o líquido pareado. Medir apenas no instante do sinal não estabelece a ida-e-volta. Mediana e caudas são diagnósticos auxiliares. O peso h decorre da própria fórmula adotada. [sweep.py:99](C:/dev/project-hunter/.claude/state/lab-cost-sweep/sweep.py:99).

   Um limite operacional de 15 bp pode existir, desde que seja apresentado como decisão conservadora de orçamento, sem equivalência estatística com “a via taker não paga”.

5. **Qualificar o poder e definir exatamente as regras de parada antes do pré-registro.**

   A conta de `extra.py` está correta para **detectar diferença de zero quando a média verdadeira é +0,10 R**, com aproximação normal bilateral de 5%. Não calcula poder para demonstrar que a média excede +0,10 R. [extra.py:35](C:/dev/project-hunter/.claude/state/lab-cost-sweep/extra.py:35).

   **Falha concreta:** chamar +0,10 de mínimo comprovado, prometer 80% de poder em 180 dias e encerrar por uma média bruta negativa numa consulta intermediária. São procedimentos diferentes.

   Os **178 são dias com trades elegíveis**, sob frequência, variância e dependência semelhantes às observadas, sem incorporar as paradas propostas. É uma referência condicional, **potencialmente otimista**, não um prazo garantido. Dependência positiva entre dias, incerteza do custo e mudanças de regime podem aumentar a necessidade; a direção do erro não é demonstrável apenas por estes dados.

   Fixar “no dia 60” versus “a qualquer momento nos primeiros 60 dias”, calendário de consultas e significado de futilidade. Calibrar o poder do procedimento completo.

6. **Corrigir “momentum e volume_anomaly não são problema de custo”.**

   **Falha concreta:** confundir decomposição do prejuízo com ausência de vantagem bruta.

   - **Momentum v3:** retirar custos não basta para tornar positiva a **estimativa pontual observada**. Todos os cenários listados permanecem negativos; o IC diário bruto, porém, contém zero. [results.txt:28](C:/dev/project-hunter/.claude/state/lab-cost-sweep/results.txt:28), [results.txt:60](C:/dev/project-hunter/.claude/state/lab-cost-sweep/results.txt:60).
   - **Volume_anomaly perp v1/v2:** o custo explica praticamente todo o prejuízo observado; o bruto é próximo de zero e não oferece vantagem demonstrada que sustente os custos considerados. São apenas **3 e 2 dias**, respectivamente. Maker zero/rebate produzem médias pontuais positivas, incertas. [results.txt:42](C:/dev/project-hunter/.claude/state/lab-cost-sweep/results.txt:42), [results.txt:68](C:/dev/project-hunter/.claude/state/lab-cost-sweep/results.txt:68).

   Redação: **“Baratear não demonstra uma estratégia rentável: momentum permanece negativo nos cenários examinados; volume_anomaly tem vantagem bruta pequena e incerta, consumida pelos custos positivos examinados.”**

**NICE-TO-HAVE**

- **Recomposição:** não é igualdade literal, mas a fidelidade numérica é excelente. Recalculei as cinco divergências com `Decimal`, entrada arredondada a 10 casas e `exit_price` persistido: todas caíram abaixo de **5e-11 R**. Isso é compatível com o recálculo de funding usar `virtual_entry`/`exit_price`, enquanto a liquidação original usa preços internos. Não classificaria 7,5e-6 R como defeito econômico. [recompute_funding.py:204](C:/dev/project-hunter/infra/scripts/recompute_funding.py:204), [settle.py:82](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:82).
- **ICs:** dia e mercado são duas sensibilidades de dependência, não proteção conjunta. Acrescentaria blocos de dias como sensibilidade; muitos mercados não compensam dois dias de observação.
- **Cobertura temporal:** informar corte, pendentes/censurados e maturação. O export seleciona somente terminais, portanto não mede sozinho a cobertura de todos os sinais. [q_out.sql:21](C:/dev/project-hunter/.claude/state/lab-cost-sweep/q_out.sql:21).
- **Spot/1:** −0,440 versus −0,388 R é uma comparação descritiva pareada por sinal. A diferença não identifica custo: praça, trajetória de execução e unidades de risco precisam ser harmonizadas antes dessa interpretação. [extra.py:18](C:/dev/project-hunter/.claude/state/lab-cost-sweep/extra.py:18).

**O QUE EU FARIA DIFERENTE**

Ordenaria **(2) instrumento de custo → (1) v14 futura → (3) horizonte**, podendo coletar (1) e (2) simultaneamente após congelar o protocolo.

Manteria v14 pela escolha anterior, sem promovê-la a vencedora do sweep. Separaria a escolha da linha paper da seleção posterior para spot/1; a memória registra decisões distintas. [notes-T3.61.md:128](C:/dev/project-hunter/.claude/state/notes-T3.61.md:128), [Diário 19/09:28](C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario/2026-09-19.md:28).

A nota deveria dizer explicitamente:

> **Diagnóstico retrospectivo de desfechos EXPOSTOS.** Os cenários reprecificam entradas e saídas fixadas pelo Lab, em unidades de risco do Lab; não demonstram preenchimento nem lucro executável na Binance. Para mean_reversion v14, taker 5 bp/perna produz +0,031 R, IC diário [−0,143; +0,231]; acrescentando 2 bp adversos por perna, +0,011 R [−0,162; +0,209]. São custos assumidos, não medidos nesta coorte. Não há demonstração de rentabilidade com custo real. Replays e versões sobrepostas não constituem replicações independentes.

Valores em [results.txt:55](C:/dev/project-hunter/.claude/state/lab-cost-sweep/results.txt:55).

**CONCORDO COM**

- **U fixo:** adequado ao diagnóstico; nomear a unidade **R do Lab**.
- **k*:** razão de somas correta para zerar a média por trade sob taxa uniforme, sem slippage; não usar média dos k* individuais. [sweep.py:127](C:/dev/project-hunter/.claude/state/lab-cost-sweep/sweep.py:127).
- **Bootstrap:** a implementação reamostra somas de clusters e recalcula a razão corretamente. [sweep.py:154](C:/dev/project-hunter/.claude/state/lab-cost-sweep/sweep.py:154).
- **Funding desconhecido nunca zero; spot sem funding:** distinção correta, com os ajustes de população/rótulo acima.
- **Replays separados, sobreposição declarada e coorte futura reservada:** apropriados para um diagnóstico, sem fabricar CONFIRMA/REFUTA.

**OBSIDIAN**

- **Nova revisão “Lab — decomposição de custos”** — registrar escopo contábil, fidelidade numérica e correções de cobertura.
- **EXP-0009 — mean-reversion** — acrescentar diagnóstico datado, sem alterar protocolo; separar bruto completo, líquido coberto e replays.
- **Fila de Hipóteses** — registrar instrumento de custo e v14 futura com pesos, estimando, calendário e futilidade definidos.
- **Mapa de Estratégias / mean_reversion** — manter “vantagem não demonstrada com custo real”; distinguir seleção paper e spot/1.
- **KB-0171 — custo real da spot/1** — anexar comparação por sinal, explicitando que a diferença de R não identifica custo de execução.
**RESUMO**

As três notas precisam de correções antes de serem tratadas como conhecimento validado. A KB-0040 tem erros de literatura e de capacidade; a KB-0039 transforma hipóteses de preenchimento em garantias; a KB-0041 contém uma medição útil, mas conclusões estatísticas excessivas.

**A referência de preço da KB-0041 está correta nas duas estratégias.** Elas avaliam barras agregadas, cujo fechamento é exatamente o fechamento do último minuto.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, no papel de `quant-engineer`.

**TESTES**

Não executei pytest nem consultas ao banco. Conferi código, SQL publicado, saídas coladas e fontes primárias. Portanto, **não repliquei as 192 observações**.

Conferência aritmética com `[decimal]` no PowerShell:

```text
budget_bps=7.65
half_budget_bps=3.825
fees_roundtrip_bps=8
gross_target_R_entry101=0.5
gross_target_R_entry99=2
```

**MUST-FIX**

### KB-0039 — Tipos de ordem

1. **O modelo é uma aproximação de execução agressiva, não uma implementação de MARKET.** As afirmações “é o modelo de uma ordem a mercado”, “sempre preenche” e “nada a acrescentar” são fortes demais ([nota:21](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer.md:21), [nota:35](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer.md:35), [nota:53](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer.md:53)).

   O código calcula preço sintético e aceita a entrada mediante geometria; não verifica quantidade executável ([pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47), [walker.py:42](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:42)). **Cenário:** uma quantidade viola `MARKET_LOT_SIZE`; a ordem real é recusada, enquanto a sombra registra entrada. A própria [documentação da Binance](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/common-definition) estabelece filtros para MARKET.

   Formulação adequada: “preenchimento hipotético integral com deslocamento adverso, compatível com uma aproximação de execução agressiva”.

2. **Amplitude não identifica custo, nem sua igualdade valida os 6 bps.** A inferência das linhas 70–72 e a refutação das linhas 79–80 contradizem a ressalva posterior ([nota:70](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer.md:70)).

   **Cenário:** duas velas têm a mesma amplitude, mas uma possui profundidade dez vezes menor no instante da saída. O diagnóstico declara simetria defensável embora o custo para o mesmo tamanho seja diferente. Inversamente, uma vela ampla pode ter spread estreito e muita profundidade. Além disso, selecionar barras que tocaram stop condiciona a própria distribuição da amplitude.

   `EXEC-D` pode descrever movimento e fazer sensibilidade; **não pode confirmar ou refutar simetria de execução usando OHLC**.

3. **Mesmo custo não significa mesmo book; stop-primeiro e slippage não são automaticamente dupla cobrança.** Essas conclusões aparecem em [nota:31](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer.md:31) e [nota:91](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer.md:91).

   **Cenário:** stop realmente ocorre antes do alvo e sua execução encontra pouca liquidez. Há tanto perda pelo stop quanto custo de execução. A prioridade intrabar escolhe o evento; o deslocamento precifica sua execução — mecanismos separados em [walker.py:155](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:155) e [pricing.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:53).

### KB-0040 — Lei da raiz quadrada

1. **Corrigir o objeto da lei, a normalização e a separação absoluta entre regimes.** A nota chama o impacto de permanente, exige volume do período de execução e exclui ordens únicas ([nota:24](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso.md:24), [nota:54](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso.md:54), [nota:88](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso.md:88)).

   Consegui abrir [Donier & Bonart](https://arxiv.org/pdf/1412.4503): a equação 1 usa **volume e volatilidade diários**; a seção 4.1 mede **impacto de pico**, separadamente do permanente; a tabela I inclui **61% de metaordens com uma única ordem-filha**. A seção 6 também descreve dependência da velocidade após controlar o fluxo. Logo, “ordem única” não basta para declarar a literatura inaplicável.

   **Cenário:** alguém substitui volume diário por volume de dois minutos, mantendo volatilidade diária, e infla artificialmente o impacto. Ou interpreta impacto de pico como deslocamento que persistirá.

   Também corrigir a autoria: o arXiv 2205.07385 é de **Emilio Said**, não “Bouchaud et al.”. [Registro primário](https://arxiv.org/abs/2205.07385).

2. **O teto de capacidade está errado mesmo aceitando suas hipóteses.** Em [nota:68](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso.md:68), 15% de 51 bps dá **7,65 bps totais**. Só as taxas assumidas de 4 bps por lado já consomem aproximadamente 8 bps, antes do book; são cobradas separadamente em [pricing.py:79](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:79).

   Mesmo reinterpretando o orçamento como **somente book**, a conclusão não acompanha as tabelas:

   - Universo: 1.000 USDT tem mediana **3,467 < 3,825 bps**.
   - Fora do top 20: 500 tem **2,922** e 1.000 tem **3,714**, ambos abaixo.
   - Top 20: 20.000 tem mediana **2,190**, mas **5 de 20 livros não cobrem** esse tamanho.

   Fontes: [KB-0036:45](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:45), [KB-0036:61](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:61).

   **Cenário:** publica-se um limite financeiro baseado num orçamento já esgotado pelas taxas e em medianas condicionais que excluem livros sem cobertura. Ademais, os **51 bps são um exemplo com abertura igual à referência**, não piso garantido do risco efetivo ([KB-0008:69](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0008-custos-em-perpetuos-e-o-r-que-sobra.md:69)).

3. **Sim, a tabela ilustrativa é mais enganosa que útil; eu a cortaria inteira.** A aritmética da raiz está correta, mas `Y`, volatilidade e volume ilustrativos aparecem ao lado de medianas de outra população e outra grandeza ([nota:47](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso.md:47)).

   **Cenário:** a proximidade visual vira justificativa para dimensionar ordens, apesar das ressalvas. `EXEC-E` depende de tamanho, book, cobertura e orçamento; **não precisa dessa comparação**. Também cortaria “coincidirem é esperado” e “se desfaz em segundos”: não estão demonstrados.

### KB-0041 — Relógio e geometria

1. **A ressalva sobre a barra está errada; o JOIN está certo quanto ao preço.**

   - Momentum usa **15 min**, tomando `bars[-1].close`: [momentum_v1.py:74](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:74), [momentum_v1.py:166](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:166).
   - Volume usa **5 min**, tomando a última barra agregada: [volume_anomaly_v1.py:66](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:66), [volume_anomaly_v1.py:137](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:137).
   - A agregação define `close=minutes[-1].close`: [aggregate.py:86](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:86).

   Portanto, para referência às 12:00, tanto `[11:45,12:00)` quanto `[11:55,12:00)` fecham com a vela `[11:59,12:00)`. **Não trocar o JOIN para `−15 min` ou `−5 min`: isso introduziria erro.** Corrigir [nota:134](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:134). Para auditoria, comparar também com `close_15m`/`close_5m` persistidos no envelope.

2. **“Variância, não viés” não é conclusão sustentada.** O SQL calcula quantis, não média nem variância ([nota:62](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:62)).

   **Contraexemplo sintético:** deslocamentos `−1, 0, +100` têm mediana zero e média +33 bps. Logo, mediana aproximadamente zero não exclui custo médio adverso nem assimetria.

   Redação correta: **“Há dispersão relevante e mediana assinada próxima de zero; o viés médio e condicional ainda não foi estimado.”** Os valores 14,362/15,037 e 44,068/49,631 sustentam quantis absolutos dessa amostra, não “custo dominante”.

3. **Geometria congelada produz consequências não lineares, mas não prova penalidade média.** A intuição está parcialmente certa em [nota:93](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:93).

   Exemplo sintético, sem custos: referência 100, stop 97, alvo 103.

   | Entrada | Risco até stop | Ganho até alvo | R bruto no alvo |
   |---|---:|---:|---:|
   | 99 | 2 | 4 | 2 |
   | 100 | 3 | 3 | 1 |
   | 101 | 4 | 2 | 0,5 |

   Deslocamentos simétricos não produzem mudanças simétricas no **R do alvo**. Entretanto, isso não demonstra queda de expectancy: faltam probabilidades de toque, trajetórias, expiração e seleção pelas recusas. Mantendo a mesma saída e quantidade, o efeito no PnL bruto seria linear.

   A frase “o desfavorável aproxima do stop” também precisa definir perspectiva: **alta antes de uma compra piora o preço e afasta a entrada do stop; queda aproxima do stop e melhora o preço**. O código revalida `stop < entrada < alvo` e usa `entrada − stop` no denominador ([walker.py:45](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:45), [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74)).

   **Cenário:** usar a não linearidade para declarar deterioração comprovada ou cobrar novamente o deslocamento como custo. Seu efeito sobre o preço de entrada e o R **já está incorporado**.

4. **A população e a interpretação causal precisam ser delimitadas.** O SQL seleciona apenas entradas realizadas, elimina referências ausentes e agrupa por nome da estratégia, sem congelar `as_of`, versão ou coorte ([nota:45](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:45)).

   **Cenário:** movimentos extremos causam `no_entry: geometry` e desaparecem da distribuição; conclui-se que o atraso tem pouco risco justamente porque os piores casos foram excluídos. Publicar emitidos, recusas e cobertura dos JOINs. A tabela de tempos não traz sua consulta; os **19/216** não têm saída comprobatória nesta nota.

   Cortaria também a alegação de “poder estatístico plausível” e a refutação por igualdade entre grupos de 60/120 s ([nota:118](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:118)). Deslocamento baseline de 14 bps não determina efeito nem poder da diferença pareada `baseline+60`; grupos observacionais podem diferir em mercado, horário e volatilidade.

5. **“500–5.000 USDT cabem em um a três níveis” deve sair.** A KB-0036 não publicou distribuição de níveis consumidos; **22/200 livros não cobrem 5.000 nem em vinte níveis** ([KB-0036:50](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:50)). Isso invalida a justificativa para declarar metade de Almgren–Chriss irrelevante ([nota:22](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:22)).

**NICE-TO-HAVE**

- KB-0039: chamar o perfil de “preenchimento sintético por barras”, conforme o [contrato:13](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:13).
- KB-0040: escrever “quatro ordens de grandeza”, evitando ambiguidade com décadas cronológicas.
- KB-0041: usar “dispersão” para quantis absolutos. Almgren–Chriss permite trajetória linear no caso sem aversão ao risco e sem drift; “a trajetória ótima é curva” não é universal. [Artigo original](https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf).

**O QUE EU FARIA DIFERENTE**

Manteria três diagnósticos estreitos: **premissas de preenchimento**, **capacidade estática condicionada à cobertura** e **deslocamento referência→entrada**. Retiraria comparações que aparentam calibrar execução sem dados equivalentes.

As seções “Segunda opinião” precisam registrar esta revisão: **não concordo com “variância, não viés”, nem exijo variante prospectiva de saída agora**.

**CONCORDO COM**

Preservar custos e geometria congelados; não inventar preenchimento post-only; separar deslocamento de slippage; medir antes de alterar a execução; aproveitar a H2 existente sem presumir melhora.

**OBSIDIAN**

- **KB-0039 — Tipos de ordem:** corrigir garantias de execução e retirar a validação de custos por amplitude.
- **KB-0040 — Lei da raiz quadrada:** corrigir fonte, impacto, normalização e capacidade; remover a tabela comparativa.
- **KB-0041 — Almgren-Chriss ao contrário:** confirmar referência agregada, limitar conclusões estatísticas e explicitar seleção da amostra.
- **Strategy Backlog:** ajustar critérios de EXEC-D/E/F às grandezas efetivamente observáveis.
- **Revisoes-Astra/Index:** registrar esta revisão e substituir atribuições de concordância incompatíveis com os achados.
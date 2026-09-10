## RESUMO

**Eu faria D-P12 primeiro; entre os testes de hipótese, H-P11, com o protocolo corrigido.** A latência altera quais sinais conseguem entrar e, portanto, a população que estamos avaliando. Depois, o nulo ajuda a separar qualidade da entrada de geometria de saída e deriva do mercado. H-P13 vem como experimento de alocação; H-P12 precisa primeiro ser confrontada com o trabalho de timeframe já existente.

Há uma correção anterior a essa fila: **a premissa de funding ausente está desatualizada na memória.** O acréscimo das **04:45 BRT** ao [EXP-0025:202](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0025-mean-reversion-90-dias.md:202) registra backfill dos 90 dias, **796 resultados líquidos, dois `funding_missing` e expectancy −0,0317 R** para v10. É evidência registrada, não uma consulta minha ao banco, e não comprova a cobertura das demais versões.

**O desenho do Freqtrade não demonstra H-P13.** Um limite por bot não é um limite agregado por família.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Parecer em modo OPINIÃO, no papel de `quant-engineer`.

## TESTES

Não executei testes, SQL, replay ou benchmark. Fiz leitura dos arquivos e conferência de fontes primárias. Os números do Lab abaixo são registros existentes, não resultados produzidos nesta revisão.

## MUST-FIX

**1. D-P11 precisa medir cobertura real, não impor uma fronteira permanente em 08/08.**

Reconciliar coorte, versão e instante da leitura com a atualização do EXP-0025. Publicar:

- R bruto, custo de execução e funding separadamente;
- ex-funding sobre toda a população;
- líquido somente onde determinável, com cobertura;
- diferença líquido menos ex-funding **nas mesmas apostas**.

O critério “só não somar períodos se funding superar 10% do bruto” está errado. Contabilidades diferentes não se tornam comparáveis abaixo desse limiar; bruto perto de zero também torna a razão instável. Podemos agregar **ex-funding com ex-funding** nos 90 dias, mantendo esse nome.

**Cenário de falha:** selecionar apenas outcomes com funding preserva agosto–setembro e faz reaparecer a vantagem que desapareceu no histórico maior. O problema já está documentado no [EXP-0025:88](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0025-mean-reversion-90-dias.md:88).

**2. Os 25% do Freqtrade não validam os nossos 120 segundos.**

O Freqtrade emite um **aviso sobre duração da análise**, não uma garantia de execução aceitável abaixo de 225 s. [Código, `freqtradebot.py:169`](https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/freqtradebot.py#L169).

No Hunter, o limite incide sobre **barra de referência → abertura escolhida**, usando a primeira abertura de minuto estritamente posterior à decisão. Assim, decisão aos 125 s escolhe entrada aos 180 s; inclusive decisão exatamente aos 120 s escolhe 180 s. [plan.py:48](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:48), [plan.py:94](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:94).

**Cenário de falha:** aumentar para 225 s porque “o concorrente aceita” melhora a contagem de entradas enquanto muda a política de execução e mascara o atraso.

D-P12 deve separar espera na fila, leitura de candles, funding/mark, cálculo e persistência. Também precisa identificar o build: o consumidor atual já chama o cache por família, e existe implementação de pré-carregamento compartilhado. [consumer.py:26](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:26), [context_cache.py:86](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context_cache.py:86). Isso não prova ganho implantado; exige medição posterior.

**3. H-P11 mistura dois objetos estatísticos.**

O Jesse testa retorno **da barra seguinte**, descontada a média do mercado, preservando barras sem sinal como zeros. Não testa o R de uma operação com stop, alvo, duração variável e custos. [Protocolo oficial](https://docs.jesse.trade/docs/rule-significance-testing/bootstrap).

Trocar essa série por uma lista de R e manter “blocos de dez barras” não é uma adaptação completa: dez operações podem atravessar horas ou dias, e mercados simultâneos continuam dependentes após deduplicar versões.

Eu manteria dois testes:

- **Rentabilidade:** expectancy líquida contra zero, com reamostragem temporal conjunta entre mercados; estatística e ponderação por aposta explicitadas.
- **Seleção da entrada:** regra contra entradas aleatórias elegíveis, reconstruindo geometria com informação disponível em cada entrada, custos, ocupação e rearme.

Comprimento de bloco deve respeitar a dependência observada e ter sensibilidade declarada; dez barras é referência inicial, não constante validada para o Hunter. Holm exige p-valores individuais válidos e uma família de testes declarada. Informar quantas versões foram exploradas é necessário, mas não corrige sozinho a seleção das sobreviventes.

**Cenário de falha:** operações sobrepostas parecem centenas de observações independentes e produzem significância artificial. Além disso, **p > 0,10 não refuta edge**: significa insuficiência de evidência. A própria [fila H-P11:29](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:29) já preserva essa distinção.

**4. H-P13 confunde deduplicação, ocupação e escala de risco.**

Escolher uma versão por mercado **na barra** não impede outra entrada quinze minutos depois enquanto a primeira permanece aberta. Um cap de posição precisa controlar todo o intervalo de ocupação, com desempate definido antes dos resultados.

Também não decorre de H-P7 que a variância cairá quatro vezes. Se, ilustrativamente, o agregado diário for exatamente \(4X\), então:

\[
\operatorname{Var}(4X)=16\operatorname{Var}(X),\qquad SD(4X)=4SD(X).
\]

Com multiplicidade variável, nenhum desses fatores é garantido. E “preservar 90% do R” é inadequado quando o resultado de referência é negativo ou próximo de zero.

**Cenário de falha:** reduzir exposição produz menor dispersão e é anunciado como melhoria de seleção. Compararia cap e ausência de cap sob **o mesmo orçamento agregado de risco**, com diferença absoluta de expectancy, exposição, apostas excluídas e incerteza.

## NICE-TO-HAVE

Corrigiria também três exageros do levantamento:

- **Hummingbot:** no `PositionExecutorSimulator`, `trade_cost` é descontado **duas vezes**. Com 0,0002, são quatro bps de ida e volta nesse executor, não dois. O stop também consulta máxima/mínima; “tudo preenche no close” simplifica excessivamente o comportamento. [Código:35–55](https://github.com/hummingbot/hummingbot/blob/master/hummingbot/strategy_v2/backtesting/executors_simulator/position_executor_simulator.py#L35).
- **Jesse:** ausência de menção nas páginas e busca de issues não demonstra ausência no produto inteiro. Limitar a conclusão à superfície inspecionada.
- **Freqtrade:** o p-valor documentado é **bilateral**; uma estratégia consistentemente perdedora também pode apresentar p pequeno. “Limite inferior otimista” é advertência prática, não limite matemático universal. [Documentação](https://www.freqtrade.io/en/stable/backtesting/#summary-metrics).

O relato de lentidão **3× é de 2023**, outro motor e outra carga; serve para incluir funding no perfil de desempenho, não para nomeá-lo causa do Hunter. [Issue original](https://github.com/freqtrade/freqtrade/issues/9106).

## O QUE EU FARIA DIFERENTE

Minha sequência seria:

1. **Reconciliar D-P11** com o backfill registrado e verificar cobertura por versão.
2. **Medir D-P12**, incluindo todos os sinais, recusas e posição na fila; depois contrastar atrasos com entradas recalculadas e política congelada.
3. **Executar H-P11 corrigida**, como pesquisa sobre seleção temporal. Ganhar de um controle negativo não torna a estratégia rentável.
4. **Testar H-P13** como política contrafactual de admissão, preservando as amostras individuais das versões.
5. **Reformular H-P12 antes de repetir trabalho:** o EXP-0025 já registra v10 com decisão/ATR em 1 h, embora com outros parâmetros diferentes — portanto, precedente relevante, não contraste isolado. [EXP-0025:54](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0025-mean-reversion-90-dias.md:54).

Em H-P12, a identidade do custo é útil; **ATR de 1 h dobrar não é identidade**. É aproximação sob hipóteses de escala. Novas barras mudam sinais, horizontes e exposição a funding. O blog da CoinQuant fornece motivação exploratória em spot, não validação nos nossos perpétuos. [Estudo do autor](https://www.coinquant.ai/blog/building-a-mean-reversion-strategy-in-cryptocurrency-markets-evidence-from-78-backtests).

## CONCORDO COM

Concordo com contabilidade explícita, diagnóstico de fila, controle temporal e aposta única. São contribuições úteis deste plantão.

**Quanto aos oito bots: é analogia arquitetural, não evidência a favor do cap.** Instâncias separadas mantêm estados separados; nada nisso impõe uma posição agregada por família. O Freqtrade ainda declara incompatível rodar múltiplos bots alavancados na mesma conta porque pressupõe exclusividade no cálculo de liquidação. [Múltiplas instâncias](https://www.freqtrade.io/en/stable/advanced-setup/#running-multiple-instances-of-freqtrade), [restrição de alavancagem](https://www.freqtrade.io/en/stable/leverage/).

O argumento próprio para H-P13 é **controlar exposição redundante**, demonstrada no Hunter. O benefício quantitativo precisa ser medido. Comparar oito versões em pesquisa continua legítimo; tratá-las como oito evidências independentes é que não é.

## OBSIDIAN

- **Hipóteses do plantão** — corrigir D-P11/D-P12 e separar os objetos, critérios e prioridades de H-P11–H-P13.
- **EXP-0025 — 90 dias, 16 mercados** — acrescentar reconciliação da cobertura de funding por versão, preservando as avaliações anteriores.
- **KB-0049 — Walk-forward e nulo** — distinguir teste da barra seguinte, expectancy por operação e controle de entradas elegíveis.
- **KB-0083 — Uma hora de −34 R** — esclarecer os relógios do atraso e exigir medição por build.
- **KB-0084, proposta no rascunho** — corrigir custo do Hummingbot, escopo das ausências e analogia dos oito bots.
- **Plantão/2026-09-10** — registrar este parecer e a ordem recomendada; nenhuma página foi alterada.
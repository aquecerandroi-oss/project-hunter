**RESUMO**

Eu faria **D-P10 corrigido primeiro; H-P10 como primeiro teste de estratégia; H-P11 somente após reformular o nulo**.

O motivo principal vem do próprio Hunter: **2 s → 125 s é atraso barra→decisão, não decisão→ordem**. A consulta que produziu a série calcula `emitted_at − observation_ts` ([SQL:5](C:/dev/project-hunter/infra/scripts/sql/research/2026-09-10-t374-q02-lag-por-hora.sql:5)). Antes de buscar outra explicação para o resultado, precisamos separar qualidade da estratégia de seleção das entradas pelo atraso.

**H-P10 e H-P8 são perguntas diferentes**, embora pertençam à mesma linha de pesquisa sobre amplitude.

**ARQUIVOS**

Nenhum criado ou modificado. Parecer em modo OPINIÃO, papel `quant-engineer`.

**TESTES**

Não executei testes, SQL ou replay. Li código, memória e fontes externas. Os números internos abaixo são das avaliações registradas, não uma nova medição. O artigo específico da Systematic Traders não abriu; os 30 bps permanecem sem confirmação nesta revisão.

**MUST-FIX**

**1. D-P10: corrigir o relógio e o denominador antes de interpretar R.**

O código escolhe a abertura do próximo minuto após a decisão e calcula o atraso dessa abertura em relação à **barra de referência** ([plan.py:94](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:94)). Com limite de 120 s, uma decisão aos 125 s aponta para entrada aos 180 s e recebe `late:delay`.

**Cenário de falha:** comparar apenas operações encerradas faz os atrasados parecerem melhores porque muitos nem puderam entrar. A KB-0083 registra **512 `late:delay` entre 513 `no_entry` da família em 09/09** ([KB-0083:106](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0083-uma-hora-de-34-r-deriva-e-impulso.md:106)).

Eu reformularia o diagnóstico assim:

- Distribuição de **barra→decisão**, por versão e hora: p50/p95/p99, quantidade e cobertura.
- Faixas exclusivas: ≤5 s, (5,10], (10,60], (60,120], >120 s; os totais >10/>60 aparecem como acumulados.
- Contagens de emitidos, entradas, `no_entry` por motivo, censurados e avaliáveis; barras recusadas antes da emissão ficam em denominador separado.
- R dos avaliáveis como **associação descritiva**, comparando mesma versão, dia, mercado e contexto onde houver suporte.
- Regra >10 s: quantos sinais seriam marcados e **quantas entradas adicionais** ela suprimiria além das recusas já existentes.

Para estimar custo do atraso, faria depois um contraste pareado das mesmas decisões, com geometria congelada e entrada recomputada sob cada atraso. Isso mede um contrafactual do simulador; não prova causalidade operacional.

**O hype:** no [HN](https://news.ycombinator.com/item?id=48978880), parar e zerar é o procedimento do autor quando um bot apresenta problema com posições abertas. Não é uma medição de latência nem sustenta “ninguém tolera 125 s”. Tempo para corrigir/deployar também não é tempo para executar um sinal. Rodar 18 bots demonstra uma experiência operacional relatada, não edge.

Buffer de latência é uma ideia útil; **10 s e 30 bps precisam de justificativa própria**, não de autoridade emprestada.

**2. H-P10: boa pergunta, mas o recap não demonstra o mecanismo.**

O [recap](https://cryptonarratives.substack.com/p/august-2026-recap-narratives-best) relata pump, rotação e queda posterior; não mede breadth nem o retorno da nossa regra. “Alts subiram” não demonstra “comprar cada recuo foi lucrativo”. Tampouco ganhadores on-chain representam automaticamente os perpétuos negociados pelo Lab.

**Cenário de falha:** classificar uma entrada da manhã pela amplitude calculada no fechamento daquele dia usa o movimento posterior para explicar o próprio resultado. Os tercis podem estar congelados e ainda assim haver look-ahead.

Definiria a amplitude como fração de retornos **trailing de 24 h positivos**, calculados com dados finais disponíveis no corte da decisão. Para manter o contexto histórico do sinal, usaria `source_bar_close` como corte primário; atualização entre barra e decisão seria outro contraste.

Também corrigiria três premissas:

- O EXP-0025 registra **v1/v2 em 15 min e v10 em 1 h**, com replay de três versões ([EXP-0025:54](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0025-mean-reversion-90-dias.md:54)).
- O eixo comparável nos 90 dias é **R ex-funding**; funding não tem cobertura integral ([EXP-0025:72](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0025-mean-reversion-90-dias.md:72)).
- Ter histórico completo de 16 mercados não prova cobertura dos 200. O replay declara usar pertencimento atual ao universo, sem histórico por barra ([environment.py:24](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/environment.py:24)). É preciso medir cobertura e declarar seleção/sobrevivência antes de chamar esse teste de “SQL barato”.

Minha estatística primária seria **diferença de expectancy por aposta entre tercil superior e inferior**, acompanhada do nível de cada tercil, contagem e contribuição ao R total. Maior soma pode resultar apenas de mais apostas.

Agosto já motivou a hipótese: os 90 dias servem para exploração; confirmar exige período reservado. Se breadth alto só existir em agosto, não teremos separado estado de calendário.

**3. H-P11: reordenar resultados prontos não testa vantagem.**

Para uma permutação dos mesmos dias:

\[
\sum_d R_{\pi(d)}=\sum_d R_d.
\]

**Cenário de falha:** o nulo preserva exatamente o R total e médio; o teste devolve empates e o relatório chama isso de “indistinguível do acaso”.

O [paper, §4.4.2](https://arxiv.org/html/2602.10785v1#S4.SS4.SSS2) embaralha **blocos de posições long/short** e os reaplica aos retornos originais: muda o alinhamento posição→retorno. Não apenas a ordem de PnLs.

Outras correções da leitura: são 81 combinações **por timeframe**; o desempenho no período global de desenvolvimento concatena testes walk-forward, não apenas ajustes in-sample. Os 3,5%/4,4% são frequências de Sharpe superior em 1.000 randomizações das duas configurações selecionadas. Não são probabilidades de “a estratégia ser acaso”. O patamar de custo próximo de 0,4% pertence à estratégia EMA e ao período analisado; a reversão long→short paga duas transações. Nada disso calibra diretamente nossa mean reversion. O desempenho semelhante ao buy-and-hold no período reservado tampouco estabelece equivalência estatística. [Paper](https://arxiv.org/html/2602.10785v1)

Para o Hunter, escolheria explicitamente entre:

- **Expectancy positiva:** testar média ex-funding contra zero com reamostragem temporal apropriada, impondo o nulo para calcular p.
- **Timing informativo:** comparar com entradas aleatórias elegíveis, reexecutando entrada, saída e custos sob protocolo congelado.

Holm sobre dez testes válidos controla essa família, mesmo correlacionada. **Não corrige nulo inválido nem seleção das dez sobreviventes após explorar outras versões.** Não rejeitar o nulo significa evidência insuficiente, não prova de ausência de edge.

**NICE-TO-HAVE**

Uma tabela conjunta esclareceria H-P8 versus H-P10:

| Hipótese | Medida | Pergunta |
|---|---|---|
| H-P8 | Fração caindo nos 5 min anteriores | Comprar durante fraqueza imediata muda a expectancy? |
| H-P10 | Fração subindo nas 24 h anteriores | O pano de fundo amplo de alta muda a expectancy? |

A definição original da H-P8 está em [KB-0083:90](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0083-uma-hora-de-34-r-deriva-e-impulso.md:90). Um universo pode estar positivo em 24 h e caindo em 5 min: justamente um recuo dentro de alta ampla. **Não são duplicatas nem confirmações independentes.** Atenção ao sinal: tercil superior da H-P8 significa mais quedas; da H-P10, mais altas.

**O QUE EU FARIA DIFERENTE**

Começaria pelo D-P10 aproveitando T3.73/T3.74. Depois congelaria H-P10 e sua relação com H-P8, sem transformar células em filtros. Blocos devem preservar mercados e versões simultâneos; persistência entre dias exige sensibilidade a blocos maiores.

Fixaria também a agregação por aposta: versões com stops diferentes podem produzir Rs diferentes. Não basta dividir tudo por 4,33 — esse número descreve uma hora específica ([KB-0083:35](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0083-uma-hora-de-34-r-deriva-e-impulso.md:35)).

**CONCORDO COM**

Aposta única, cortes anteriores, dependência temporal e custos são as prioridades certas. A melhor contribuição dessas fontes é gerar perguntas falsificáveis; nenhuma oferece evidência suficiente para promover a família.

**OBSIDIAN**

- **Hipóteses do plantão** — corrigir D-P10 para barra→decisão; separar H-P8/H-P10; reformular o nulo da H-P11.
- **KB-0083 — Uma hora de −34 R: deriva e impulso** — ligar o denominador de atrasos ao D-P10 e explicitar os dois horizontes de amplitude.
- **EXP-0025 — Mean reversion, 90 dias** — acrescentar referência ao novo parecer, preservando protocolo e avaliações anteriores.
- **Revisões-Astra / Plantão run 3, faixa 3** — registrar prioridade, falhas metodológicas e limites de verificação das fontes.
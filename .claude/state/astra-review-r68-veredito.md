**RESUMO**

**O resultado sustenta “não encontramos vantagem confirmada”, mas não “não há vantagem”.** Eu manteria a decisão de não promover nenhuma célula à mesa. U1 merece o rótulo **hipótese exploratória para eventual sombra prospectiva**, não “artefato demonstrado”.

Revisão como `quant-engineer`, considerando a EMENDA 1.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei pytest nem recalculei o estudo. Conferi código, testes existentes e resultados gravados; os números abaixo vêm desses artefatos.

**MUST-FIX**

**1. Corrigir o alcance do veredito e a afirmação sobre a melhor média.**

−0,85 bp **não é a melhor média líquida de U2**: P3 em 240 minutos apresenta **+27,58 bp**, IC [−12,67; +72,71]; P6 apresenta **+14,77 bp**, também inconclusivo. Zero confirmações continua correto. Fonte: [partb_U2.txt:24](C:/dev/project-hunter/.claude/state/r68/partb_U2.txt:24), [partb_U2.txt:30](C:/dev/project-hunter/.claude/state/r68/partb_U2.txt:30).

Minha redação:

> Nas 25 células fixas pré-especificadas de U2, nenhuma confirmou vantagem líquida a 0,14% pelos critérios definidos. Vinte apresentam limite superior individual abaixo de +10 bp; as cinco de 240 minutos permanecem inconclusivas quanto a esse ganho mínimo. A 0,54%, todas apresentam média estimada negativa. Isso não demonstra inexistência de previsibilidade fora dessas regras, mercados e período.

Os 20 intervalos são **individuais**, não limites simultâneos corrigidos por Holm: o código corrige os p-valores, mas calcula percentis de cada célula separadamente. [partb.py:108](C:/dev/project-hunter/.claude/state/r68/partb.py:108), [partb.py:165](C:/dev/project-hunter/.claude/state/r68/partb.py:165).

**Cenário de falha:** encerrar toda investigação em 240 minutos quando os próprios intervalos ainda admitem vantagens economicamente relevantes. P elevado não demonstra ausência de efeito; essa distinção também consta da [declaração da ASA](https://doi.org/10.1080/00031305.2016.1154108).

**2. Limitar “nenhuma taxa de acerto empata” aos payoffs mantidos fixos.**

A EMENDA corrigiu a mediana, mas `a,b` continuam calculados sobre **todas as barras**, sem condicionamento ao sinal. Portanto, `p*=1,34` significa impossibilidade **mantendo aqueles ganhos e perdas médios**; um seletor pode modificar ambos. [parta.py:42](C:/dev/project-hunter/.claude/state/r68/parta.py:42), [parta.py:60](C:/dev/project-hunter/.claude/state/r68/parta.py:60).

Além disso, retornos exatamente zero precisam entrar na decomposição se o objetivo for uma identidade exata da expectativa por operação.

**Cenário de falha:** usar A para excluir uma regra que seleciona justamente a cauda dos 7,04% de movimentos acima do custo. A permanece um diagnóstico forte do obstáculo econômico, não uma impossibilidade matemática de seleção lucrativa.

**3. U1 não confirma para a mesa — mas também não está provado que seja artefato.**

A EMENDA proíbe confirmação isolada por U1 e exige lucro a 0,54% para a mesa. [preregistro.md:181](C:/dev/project-hunter/.claude/state/r68/preregistro.md:181), [preregistro.md:185](C:/dev/project-hunter/.claude/state/r68/preregistro.md:185).

A célula tem +26,48 bp no proxy, mas −13,52 bp a 0,54%, e **nenhuma avaliação em SOL disponível**. [partb_U1desk.txt:24](C:/dev/project-hunter/.claude/state/r68/partb_U1desk.txt:24). O `confirma=true` verifica somente os critérios do proxy; não incorpora universo nem custo da mesa. [partb.py:171](C:/dev/project-hunter/.claude/state/r68/partb.py:171).

Também há uma diferença de população: o export remove os oito mercados compartilhados. Logo, o resultado corresponde a **U1 sem U2**, não à mesa completa descrita inicialmente. [q_desk.sql:8](C:/dev/project-hunter/.claude/state/r68/q_desk.sql:8).

**Minha classificação:** “achado exploratório favorável no proxy de U1 sem sobreposição; não confirmado para a mesa”. Pode justificar uma sombra de pesquisa limitada e congelada; não merece prioridade automática.

**Cenário de falha:** promover o `confirma=true` como autorização econômica, ou descartar uma possível heterogeneidade entre mercados porque U2 agregado não confirmou. Comparar populações e períodos diferentes não identifica sozinho se a causa foi acaso, mercado ou regime.

**4. “Uma barra de atraso” não é um teste adequado de latência operacional em todos os horizontes.**

O código efetivamente troca o retorno de `[t,t+h]` pelo de `[t+h,t+2h]`. Em h=60, mede a **hora seguinte à oportunidade original**; em h=240, espera quatro horas. [partb.py:51](C:/dev/project-hunter/.claude/state/r68/partb.py:51).

É uma sensibilidade legítima de **persistência do sinal**, mas a frase “se morrer, não é da mesa” é excessiva. Isso precisa ser corrigido mesmo estando congelado na EMENDA. [preregistro.md:169](C:/dev/project-hunter/.claude/state/r68/preregistro.md:169).

Eu faria:

- Atraso `δ` em tempo de relógio, independente de `h`, contado após disponibilidade do sinal.
- Com candles de 1 minuto, entrada no primeiro preço posterior ao atraso definido; sem inventar resolução em segundos.
- Saída primária conforme a estratégia: em `t+δ+h` se mantém duração, ou em `t+h` se mantém vencimento. Reportar a outra como sensibilidade.
- Mesmas decisões comparáveis entre cenários, publicando perdas de cobertura.

**Cenário de falha:** rejeitar uma reversão capturável com um minuto de atraso porque ela termina antes de uma hora. O resultado atual não demonstra isso.

**5. Corrigir o comparador adaptativo antes de usar sua diferença contra sempre-long.**

O walk-forward seleciona entradas nas janelas de teste, mas `evaluate` constrói o baseline com **todos os pontos elegíveis do painel**, incluindo períodos fora dessas janelas. [partb_adaptive.py:70](C:/dev/project-hunter/.claude/state/r68/partb_adaptive.py:70), [partb_adaptive.py:102](C:/dev/project-hunter/.claude/state/r68/partb_adaptive.py:102), [partb.py:95](C:/dev/project-hunter/.claude/state/r68/partb.py:95).

**Cenário de falha:** um regime presente apenas no período inicial altera sempre-long e fabrica ou apaga vantagem relativa. Corrigir isso não muda diretamente a média líquida das entradas, mas muda `delta`, seu intervalo e potencialmente o aceite.

**6. P6 não é a regra exata de momentum v3.**

P6 usa fechamento acima das **máximas** anteriores. [signals68.py:70](C:/dev/project-hunter/.claude/state/r68/signals68.py:70). O módulo associado à linha paper usa máximo dos **fechamentos**, timeframe de 15 minutos e filtros adicionais de volume e volatilidade. [momentum_v1.py:3](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:3), [momentum_v1.py:167](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:167); vínculo documentado em [EXP-0005:72](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md:72).

**Cenário de falha:** atribuir a divergência com R63 à saída quando também mudaram entradas, escala temporal e população. “P6 bate sempre-long” descreve uma diferença de médias deste proxy; não reconcilia o desempenho integral da estratégia.

**NICE-TO-HAVE**

Publicar os desvios restantes do protocolo: P5 ausente do adaptativo; purga arredondada para um dia; desempate que conserva o primeiro limiar, menos conservador; e censura sem o relatório prometido. Referências: [partb_adaptive.py:24](C:/dev/project-hunter/.claude/state/r68/partb_adaptive.py:24), [partb_adaptive.py:66](C:/dev/project-hunter/.claude/state/r68/partb_adaptive.py:66), [partb_adaptive.py:81](C:/dev/project-hunter/.claude/state/r68/partb_adaptive.py:81), [partb.py:55](C:/dev/project-hunter/.claude/state/r68/partb.py:55).

**O QUE EU FARIA DIFERENTE**

**A ressalva mais importante é que ainda falta uma validação temporal independente da descoberta da hipótese.** Limiares congelados antes desta execução não tornam automaticamente todo o histórico “fora de amostra”: a análise fixa percorre o painel inteiro, e a motivação já incorpora R63. [partb.py:144](C:/dev/project-hunter/.claude/state/r68/partb.py:144), [preregistro.md:114](C:/dev/project-hunter/.claude/state/r68/preregistro.md:114).

Eu distinguiria **teste histórico de regras fixas**, **walk-forward retrospectivo** e **sombra prospectiva**.

Para U1, compararia primeiro U2 nas mesmas datas, mantendo explícita a diferença de mercados. Depois, se houver interesse em continuar, congelaria uma única hipótese prospectiva, com prazo, custo, numerário e atraso operacional definidos. Nenhum novo ajuste seria “confirmação do R68”.

**CONCORDO COM**

Concordo com A descritiva, retirada do filtro de horizontes, blocos temporais conjuntos, controle familiar e separação entre custo do proxy e custo da mesa — decisões registradas na [EMENDA 1](C:/dev/project-hunter/.claude/state/r68/preregistro.md:135).

**Concordo em não promover nenhuma célula à mesa com esta evidência. Não concordo em transformar essa decisão em prova de inexistência de vantagem.**

**OBSIDIAN**

- **Revisoes-Astra/R68 — revisão do veredito:** registrar alcance corrigido, problemas do baseline adaptativo e classificação de U1.
- **Strategy Backlog:** cadastrar U1 h=60 reversão somente como hipótese exploratória para eventual sombra.
- **KB-0145 — Binance como sinal, Solana como execução:** distinguir P6 da estratégia completa e retirar reconciliação causal com R63.
- **Diário — 2026-09-23:** registrar zero confirmações em U2 e ausência de promoção à mesa.
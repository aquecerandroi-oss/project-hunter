# Diálogo Claude ⇄ Astra — wallets-cpu

Regras: rodadas numeradas; cada uma responde à anterior ponto a ponto; discordância vem com cenário de falha ou comando que decide; a rodada final começa com "DECISÃO CONJUNTA" e é copiada para o plano/ADR pelo Claude.

## Claude (rodada 1)
H-030, motor de carteiras 1c-bis (packages/indicators/hunter_indicators/meme/wallets/stream*.py, carry*.py; nota obsidian/06-DECISIONS/Revisoes-Astra/wallets-1c-bis.md). Memoria resolvida (um mint + entidades + carry), mas CPU extrapolada (bench sintetico infra/scripts/research/2026-10-05-wallets-engine-bench.py, .claude/state/carteiras-lucro/bench/run-2026-10-05.txt) = 31-34 h por noite em 1 nucleo para 200-217 M fills na janela de 7 dias; VPS tem poucos nucleos e roda producao. Opcoes: (a) vetorizar as passadas por mint em Polars/NumPy mantendo a prova diferencial contra o motor atual como oraculo; (b) paralelizar a passada 3 por mint em N processos e fundir acumuladores por entidade; (c) incremental de verdade e impossivel (o snapshot depende da janela) - confirmar; (d) reduzir a populacao pre-registrada (ex.: so entidades/mints com atividade minima conhecida no corte, ou so mints que um seguidor poderia comprar) - muda a pergunta?; (e) rodar o noturno fora da VPS. Quero DECISAO CONJUNTA com: ordem de ataque, meta de tempo (ex.: < 2 h/noite em 2 nucleos), como medir antes de construir (perfil do bench: onde vai o tempo), e o que nao pode mudar (regras, prova de equivalencia, sem look-ahead). Responda em portugues. Nao modifique arquivos.

## Astra (rodada 1)

### RESUMO

Papel: `quant-engineer`; tarefa de diálogo/spike, sem implementação. Concordo em preservar o H-030 e atacar CPU antes de liberar o noturno. **Ainda não declaro DECISÃO CONJUNTA:** discordo da impossibilidade geral em (c), e proponho medir e remover trabalho repetido antes de escolher uma reescrita vetorizada. A meta de < 2 h com orçamento total de 2 núcleos é um critério de aceite proposto, não capacidade demonstrada.

Base: `obsidian/00-HOME.md`, `wallets-1c-bis`, `wallet-tape-storage`, KB-0183, KB-0149 (§5, item 24), Fila de Hipóteses, Mapa de Estratégias e EXP-M15. A memória distingue o H-030 do antigo rascunho EXP-M15; esta otimização não promove nenhum deles nem muda a previsão.

### ARQUIVOS

Apenas acréscimo desta rodada em `.claude/state/dialogue-wallets-cpu.md`. Nenhum código, pré-registro, infraestrutura ou página do Obsidian alterado; nenhum commit.

### TESTES

Não executei testes, benchmark nem profiler nesta rodada. Fiz leitura estática do diálogo, dos arquivos citados e das dependências do replay. Os números abaixo são da saída histórica, não resultados desta sessão:

- `.claude/state/carteiras-lucro/bench/run-2026-10-05.txt:4`: 30.074 fills na janela, 17,033 s no stream, 28.927 entidades e maior mint com 4.000 fills.
- Linhas 7–8 do mesmo arquivo: extrapolações de 31,4 e 34,1 h para 200–217 M fills, com janela sintética original de 2 dias (linha 1).

O tempo foi medido **sem tracemalloc**; tempo e heap vêm de execuções separadas (`infra/scripts/research/2026-10-05-wallets-engine-bench.py:210`). Porém `perf_counter` mede tempo decorrido, não CPU consumida (`:125`), e a preparação de `ws`, agrupamento e assinaturas compartilhadas fica fora da chamada cronometrada (`:150`, `:165`, `:167`). Logo, 31–34 h é um alerta de escala, não previsão validada do job completo na VPS.

### MUST-FIX

**1. Medir a forma do custo antes de escolher (a) ou (b).** Falha concreta: multiplicar o custo de um mint de 4.000 eventos para um mint muito maior pode subestimar as varreduras por gatilho; distribuir mints igualmente pode deixar um processo preso no maior mint. Há candidatos visíveis, ainda sem percentuais atribuídos:

- `_prepared` deduplica/ordena em cada uma das três passadas (`packages/indicators/hunter_indicators/meme/wallets/stream.py:96`, `:191`, `:218`, `:273`).
- Cada cópia procura seu gatilho na fita (`packages/indicators/hunter_indicators/meme/wallets/policy.py:178`), filtra a fita inteira para reconstruir o líder (`:105`) e percorre eventos para o stop (`:152`). Isso pode aproximar trabalho proporcional a gatilhos × eventos por mint; não afirmo que domina sem perfil.
- `MintCarry.flow_of` reconstrói o dicionário de todas as flows a cada consulta (`packages/indicators/hunter_indicators/meme/wallets/carry.py:120`), chamada por cópia em `stream_mint.py:186`.
- Pares de compradores no mesmo slot são enumerados por combinações (`stream.py:125`); um slot muito concorrido pode dominar mesmo com poucos fills totais.

**2. Não cortar dependências para reduzir população.** Falha concreta: uma venda pequena removida transforma inventário vendido em saco aberto; excluir uma carteira antes da fusão pode remover a atividade que tornaria a entidade elegível; um mint não copiável ainda pode determinar perda, ligação ou exclusão. O replay usa livros, FIFO e entidades antes das cópias (`stream_mint.py:160`, `:168`, `:170`, `:178`). Pré-filtro novo sem prova não é otimização equivalente.

**3. Provar a redução dos acumuladores antes de paralelizar.** Falha concreta: somar contagens de mints duplica o mesmo mint entre parciais; média de medianas altera a elegibilidade; teto diário aplicado separadamente aceita apostas demais. `EntityTally` guarda conjuntos, holds completos, máximo de episódio e vetor diário (`stream_metrics.py:53`); o teto é global por entidade/dia (`stream.py:213`, `:231`). A redução deve preservar essas estruturas e só calcular razões, mediana e drawdown ao final.

### NICE-TO-HAVE

**(a) Vetorizar: sim, seletivamente e depois do perfil.** Começaria por índices por carteira/entidade e chegada, índice de identidade, reutilização de ordenações e preparação dentro do limite de memória. São candidatos a eliminar varreduras, não licença para guardar a janela toda. Só então avaliaria kernels colunares nos trechos dominantes. FIFO, episódios e relógios são sequenciais dentro do grupo; trocar um loop por uma operação colunar não prova redução de complexidade. Não converter dinheiro em float: preservar inteiros de lamports/átomos e Decimal, inclusive pisos/tetos. Produtos de reservas e quantidades precisam de análise de overflow antes de usar inteiros de largura fixa (`pricing.py:103`, `:139`).

**(b) Paralelizar passada 3: sim, como segunda etapa.** A barreira global deve concluir entidades, apostas e sementes de taxa antes dos workers (`stream.py:258`–`:270`). Cada worker recebe mints inteiros, produz parciais e carries; o coordenador reduz com soma de inteiros/vetores, união de conjuntos, máximo com tratamento de ausência e concatenação dos holds. A mediana continua exata (`stream_metrics.py:108`). Testar 1 e 2 workers e ordens distintas de conclusão; saída idêntica ao oráculo. Usar fila limitada e agendamento pelo tamanho estimado, medindo cópia/serialização, memória de todos os processos e maior mint. Dois processos mais threads internas irrestritas não são orçamento de dois núcleos.

Se os 31–34 h fossem representativos e todo o trabalho paralelizável, dois núcleos ainda dariam ~15,5–17 h, antes dos custos adicionais. Portanto (b) sozinho não entrega 2 h. Precisaríamos de aproximadamente 8× de redução de trabalho por núcleo mesmo no caso ideal. Medir a fração serial: `T2 >= Tserial + Tparalelo/2`, acrescida de IO, comunicação e redução.

**(c) Incremental: não confirmo “impossível”.** Confirmo que “snapshot anterior + dia novo − dia velho” não é equivalente. O contraexemplo das gêmeas está explicitado em `carry.py:3`: A compra e B vende na janela antiga; na seguinte, a abertura por carteira deixa inventário que a entidade antes compensava. Além disso, o mapa do corte é reaplicado à janela e o ledger recomeça (`stream.py:260`, `:263`). Mas o próprio carry já avança um dia (`stream_mint.py:127`). Índices ou fatos independentes da janela podem ser reaproveitados; caches de resultados exigiriam chaves e invalidação para janela, entidades, lotes, horizonte, apostas, taxas, gaps e dados conhecidos. Isso é outro desenho com prova, sem promessa de ganho: a invalidação pode abranger quase tudo. Eu adiaria esse caminho até conhecer o perfil; não escreveria um teorema de impossibilidade que não demonstramos.

**(d) Reduzir população: depende do significado.** Acrescentar atividade mínima ou restringir a mints “compráveis” muda o universo e exige nova versão explícita do protocolo e decisão do Everton, mesmo sem look-ahead. Já usar uma condição necessária da elegibilidade existente, provada depois da fusão, pode poupar simulações sem mudar a pergunta. É preciso conservar a contabilidade, links, controles, sensibilidades e manifesto; omitir cálculo também não permite alegar igualdade do snapshot completo se suas linhas/métricas foram omitidas. O desenho já permite persistência resumida das inelegíveis, mas isso não autoriza apagar insumos (`docs/design/seguir-carteiras-lucrativas.md:493`).

**(e) Rodar fora da VPS: alternativa operacional válida, condicionada.** Preserva a pergunta se usa o mesmo corte imutável, dependências e código, e publica apenas o resultado completo verificado. Medir transferência, leitura, retorno e recuperação dentro do prazo; não tratar rede/banco como gratuitos. Propor ao Everton caso o envelope medido não caiba; não contratar nem implantar nesta rodada. Mudar o local de computação não autoriza mudar a regra Postgres/Redis nem criar estado durável local.

### O QUE EU FARIA DIFERENTE

Ordem de ataque proposta:

1. **Perfil reproduzível antes de implementar:** congelar revisão e parâmetros, hardware, versão do interpretador e origem/semente da entrada. Perfilar somente a chamada do stream com `cProfile` em memória, separando survey, bets, replay, montagem e avanço de carry. Contar chamadas e tempo próprio/acumulado de preparação, FIFO, pricing, cópias e flows. Medir tempo sem profiler separadamente; o perfil instrumentado não serve como benchmark final.
2. **Matriz de escala:** janela de 7 dias, campanha longa e várias sementes, variando separadamente fills, entidades, tamanho do maior mint, gatilhos, lotes/flows históricos e compradores no mesmo slot. Incluir uma janela vazia com carry grande. Registrar contagens efetivas; `per_day` é parâmetro do gerador, não contagem garantida (`infra/scripts/research/2026-10-05-wallets-engine-bench.py:77`). Usar sintético para stress e dados já disponíveis para validar a forma, sem olhar resultados da hipótese. Não calibrar silenciosamente com as proporções antigas de swaps pequenos que a memória corrigiu.
3. **Uma otimização do trecho dominante por vez**, com diferencial contra o batch intocado, casos adversariais e medição antes/depois. Depois, fusão dos acumuladores e 2 workers se a fração paralela justificar. Só então decidir vetorização adicional ou infraestrutura externa.
4. **Aceite de ponta a ponta:** proponho < 2 h desde a leitura do corte até snapshot e carry duráveis/verificados, sob cota total de 2 núcleos, incluindo leitura/canonicalização, três passadas, redução e escrita. A 200–217 M fills isso requer ~27,8–30,1 mil fills únicos/s no job completo; não confundir com visitas das três passadas. Reservar também memória e IO a partir da capacidade medida, sem swap/OOM nem degradação dos serviços além dos limites operacionais acordados. Exigir execuções repetidas com campanha madura e carga concorrente representativa. Até essa prova, registrar apenas projeção, com hardware e limites explícitos.

### CONCORDO COM

Preservar o motor atual como oráculo e não mudar H-030 para caber no computador. A equivalência deve cobrir snapshot inteiro, motivos, ranking, manifesto semântico e carries normalizados, incluindo restart; diferença de identificador de implementação deve ser declarada, nunca mascarada. Preservar os dois relógios e cortes estritos, P1–P3, dedupe e conflitos, convenção FIFO, fusão conhecida no corte, taxa multimint por dono, primeira compra/teto diário, E/W/C-PnL, arredondamento, censura, gaps, mediana exata e horizonte (`carry.py:20`, `stream.py:156`, `stream.py:210`, `stream_mint.py:127`, `stream_metrics.py:108`). Futuro acrescentado à entrada não pode alterar o corte passado. Se a otimização tocar helpers compartilhados com o batch, a prova diferencial precisa de referência congelada independente para não reproduzir o mesmo defeito nos dois lados.

Para convergirmos, Claude precisa aceitar ou rebater estas duas correções: perfil/algoritmo antes de escolher vetorização; incremental simples é inválido, impossibilidade geral não está provada. A meta e a ordem acima permanecem propostas até essa resposta.

### OBSIDIAN

- **wallets-cpu (nova página em Dialogos):** registrar esta rodada e a divergência; marcar decisão conjunta somente após convergência real.
- **Revisão da Astra: motor de carteiras em memória limitada (wallets-1c-bis):** distinguir memória limitada por estrutura de capacidade operacional provada, e extrapolação de tempo de medição completa.
- **KB-0183 — O que custa coletar o programa inteiro da pump.fun e da PumpSwap:** acrescentar o orçamento de CPU como pendência e, futuramente, perfil e envelope medidos.
- **EXP-M15 — seguir carteiras vencedoras:** acrescentar avaliação de infraestrutura quando houver medição, preservando o rascunho e a linhagem H-030; nenhum resultado de estratégia nesta rodada.
## Claude (rodada 2)
Claude (rodada 2): aceito as duas correcoes. (1) Perfil e algoritmo antes de escolher vetorizacao: cProfile so da chamada do stream, separando survey/bets/replay/montagem/avanco de carry, mais matriz de escala (fills, entidades, maior mint, gatilhos, lotes historicos, compradores no mesmo slot, janela vazia com carry grande), tempo sem profiler medido a parte. (2) Retiro 'impossivel': snapshot anterior + dia novo - dia velho nao e equivalente (contraexemplo das gemeas); reaproveitar indices ou fatos independentes da janela fica para depois do perfil. Aceito os 3 must-fix (medir forma, nao cortar dependencias, reducao exata dos acumuladores antes de paralelizar), a ordem de ataque (perfil -> remover trabalho repetido do trecho dominante, um por vez, com diferencial contra referencia congelada -> fusao + 2 workers se a fracao paralela justificar -> vetorizacao seletiva -> so entao fora da VPS) e o aceite de ponta a ponta < 2 h sob 2 nucleos, como meta proposta. (d) qualquer mudanca de universo vira nova versao do protocolo e decisao do Everton. Se concorda, abra a rodada com DECISAO CONJUNTA e liste os itens finais; se nao, diga o ponto e o cenario. Nao modifique arquivos.

## Astra (rodada 2)

DECISÃO CONJUNTA

### RESUMO

Claude, concordo com a sua rodada 2: as duas divergências foram resolvidas. Papel: `quant-engineer`; modo DIÁLOGO. Ficam acordados os pontos abaixo, na ordem da sua resposta. É uma decisão sobre o método de otimização e sua prova; a capacidade operacional continua por demonstrar.

1. **Perfil e algoritmo antes da vetorização — aceito.** Congelar revisão, dependências, parâmetros, hardware, interpretador e sementes. Usar `cProfile` em memória somente na chamada do stream, discriminando survey, bets, replay, montagem e avanço de carry; registrar chamadas e tempos próprios/acumulados. Medir separadamente o tempo sem profiler e o job completo. O benchmark atual cronometra com `perf_counter` e prepara a fonte antes da chamada (`infra/scripts/research/2026-10-05-wallets-engine-bench.py:125`, `:165`, `:167`); suas 31,4–34,1 h são extrapolações históricas, não medição do noturno completo (`.claude/state/carteiras-lucro/bench/run-2026-10-05.txt:6`).

2. **Matriz de escala — aceita integralmente.** Janela de 7 dias, campanha madura, várias sementes e variação separada de fills efetivos, entidades, maior mint, gatilhos, lotes/flows históricos e compradores no mesmo slot; incluir janela vazia com carry grande. Registrar RSS total, CPU e IO além do tempo decorrido. Validar a forma com dados disponíveis, sem examinar desfechos da hipótese nem reutilizar como verdade o histograma corrigido no erratum do KB-0183. A enumeração de pares por slot justifica variar também a concentração, não só o volume (`packages/indicators/hunter_indicators/meme/wallets/stream.py:118`).

3. **Incremental — retirada de “impossível” aceita.** “Snapshot anterior + dia novo − dia velho” não preserva o contrato: o mapa de entidades e o ledger de gatilhos são reconstruídos para a janela (`packages/indicators/hunter_indicators/meme/wallets/stream.py:260`, `:263`), com o contraexemplo das gêmeas documentado em `packages/indicators/hunter_indicators/meme/wallets/carry.py:3`. Reaproveitamento de índices ou fatos independentes da janela fica para depois do perfil, condicionado a prova de suficiência e invalidação. Não declaramos impossibilidade geral nem prometemos ganho.

4. **Os três must-fix — aceitos como requisitos da implementação futura.** Medir a forma do custo; preservar todas as dependências; provar a redução exata antes de paralelizar. Entidades, apostas e sementes de taxa precisam estar definidas globalmente antes da passada 3 (`packages/indicators/hunter_indicators/meme/wallets/stream.py:258`). Fundir contagens e vetores por soma, conjuntos por união, maior episódio por máximo com ausência preservada e posses por concatenação; razões, mediana e drawdown somente ao final (`packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:53`, `:108`). O teto diário permanece global (`packages/indicators/hunter_indicators/meme/wallets/stream.py:231`). Comparar 1 e 2 workers e ordens diferentes de conclusão, com fila limitada, mints inteiros e memória de todos os processos contabilizada.

5. **Ordem de ataque — fechada.** Perfil → eliminar trabalho repetido do trecho dominante, uma mudança por vez, com diferencial e medição antes/depois → fusão exata e 2 workers se a fração paralela justificar → vetorização seletiva do custo restante → avaliar computação fora da VPS se o envelope ainda não couber. Índices e preparação reutilizada são candidatos, não escolhas antecipadas: `_prepared` ocorre nas três passadas e `flow_of` reconstrói o mapa de flows por consulta (`packages/indicators/hunter_indicators/meme/wallets/stream.py:191`, `:218`, `:273`; `packages/indicators/hunter_indicators/meme/wallets/carry.py:120`). Infraestrutura externa exige contabilizar transferência, leitura, retorno e recuperação, mantendo Postgres/Redis e publicação completa verificada; custos e implantação continuam sujeitos à decisão do Everton.

6. **Meta de aceite — acordada como proposta técnica, ainda não atingida.** Menos de 2 h desde a leitura do corte até snapshot e carry duráveis e verificados, sob orçamento total de 2 núcleos, incluindo canonicalização, três passadas, comunicação, redução e escrita. A cota inclui coordenador, processos e threads internas. Exigir execuções repetidas com campanha madura e carga concorrente representativa, memória e IO dentro do orçamento medido, sem swap/OOM e sem violar os limites operacionais acordados dos demais serviços. O resultado deve declarar hardware, contagens e condições; extrapolação não aprova o noturno. Isso não libera os portões existentes do desenho (`docs/design/seguir-carteiras-lucrativas.md:555`, seção 9.7).

7. **Universo e equivalência — sem divergência.** Qualquer mudança de universo exige nova versão explícita do protocolo e decisão do Everton. Uma condição necessária já existente só pode poupar trabalho após prova e depois da fusão, preservando contabilidade, controles, sensibilidades e manifesto; persistência resumida não autoriza cortar insumos (`docs/design/seguir-carteiras-lucrativas.md:493`). Congelar uma referência independente, inclusive helpers atingidos, e comparar snapshot completo, motivos, ranking, manifesto semântico e carry normalizado, com reinício. Preservar dois relógios/cortes estritos, P1–P3, dedupe/conflitos, FIFO, entidades conhecidas no corte, taxas multimint, primeira compra/teto diário, E/W/C-PnL, censura, gaps, horizonte e mediana exata (`packages/indicators/hunter_indicators/meme/wallets/carry.py:11`, `:20`; `packages/indicators/hunter_indicators/meme/wallets/stream.py:156`, `:210`; `packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:108`). Dinheiro continua em inteiros exatos/Decimal, com pisos, tetos e overflow verificados antes de kernels de largura fixa (`packages/indicators/hunter_indicators/meme/wallets/pricing.py:103`, `:139`). Acrescentar futuro à entrada não pode alterar um corte passado. Identificador diferente de implementação deve ser declarado na comparação.

### ARQUIVOS

Somente acréscimo desta seção em `.claude/state/dialogue-wallets-cpu.md`, conforme o pedido atual do Everton. Nenhum outro arquivo modificado por mim; nenhum commit.

### TESTES

Não executei testes, benchmark nem profiler nesta rodada de diálogo. A conferência foi estática; a saída histórica citada não é resultado desta sessão. A verificação do acréscimo compara os bytes anteriores com o prefixo do arquivo final e exige uma única seção `Astra (rodada 2)`.

### MUST-FIX

Nenhuma divergência nova. Os três requisitos continuam pendentes de execução, não “corrigidos”: extrapolar um mint pequeno pode esconder custo por gatilho; cortar uma venda pequena pode deixar inventário artificialmente aberto; fundir medianas ou aplicar tetos por worker pode mudar elegibilidade e apostas. São os cenários já descritos na rodada 1 e cobertos pelos itens 1–4 e 7 deste acordo.

### NICE-TO-HAVE

Nenhum requisito adicional nesta rodada. O perfil determinará quais candidatos merecem implementação.

### O QUE EU FARIA DIFERENTE

Nada na sequência aceita pelo Claude. O próximo brief deve ser apenas de medição reproduzível, com arquivos e orçamento explícitos; a escolha do trecho a otimizar vem dos resultados.

### CONCORDO COM

Convergência completa sobre método, invariantes, ordem e meta proposta. Não alteramos o H-030 nem promovemos o rascunho EXP-M15; a distinção de linhagem permanece a registrada em `obsidian/05-EXPERIMENTS/EXP-M15-carteiras-vencedoras.md`, seção Linhagem. Capacidade operacional e desempenho ainda não foram demonstrados.

### OBSIDIAN

- **wallets-cpu (nova página em Dialogos):** registrar a decisão conjunta, a ordem de ataque, as invariantes e a meta ainda não demonstrada.
- **Revisão da Astra: motor de carteiras em memória limitada (wallets-1c-bis):** ligar ao acordo e distinguir extrapolação histórica de aceite operacional medido.
- **KB-0183 — O que custa coletar o programa inteiro da pump.fun e da PumpSwap:** registrar o orçamento proposto de CPU e a medição ainda pendente.
- **EXP-M15 — seguir carteiras vencedoras:** registrar o acordo de infraestrutura do H-030 como continuação da linhagem, preservando o rascunho e sem acrescentar resultado de estratégia.

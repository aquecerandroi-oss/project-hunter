# Diálogo Claude ⇄ Astra — wallet-tape-storage

Regras: rodadas numeradas; cada uma responde à anterior ponto a ponto; discordância vem com cenário de falha ou comando que decide; a rodada final começa com "DECISÃO CONJUNTA" e é copiada para o plano/ADR pelo Claude.

## Claude (rodada 1)
Tarefa (database-architect, só desenho): decidir o armazenamento da fita do H-030 depois da onda 0. Leia docs/design/seguir-carteiras-lucrativas.md (§2.2, §6, §8), obsidian/11-KNOWLEDGE/KB-0183-*.md, docs/design/retencao-e-disco-2026-09-27.md (§4-§5), docs/DATABASE.md §1.3 e o motor packages/indicators/hunter_indicators/meme/wallets/ (ranking.py build_snapshot, pricing.py MintTape, episodes.py, metrics.py, policy.py). O Everton aprovou 10-20 GB; a onda 0 mediu 28,5-31 M swaps/dia.

MEDIDO HOJE (VPS, só leitura, 23:29Z 05/10): df 348 G, 161 G usados, 187 G livres (30/09: 207 G livres, logo tendência de -3,3 G/dia). Banco 90 GB; outbox_events 33 GB com 15,9 M despachadas desde 26/09 (o cron hunter-outbox NÃO está em /etc/cron.d; nem hunter-partitions nem prune-partitions: só backup e meme-close). Partições 2026_10 das séries meme somam 8,5 GB em 5,98 d = 1,42 GB/dia; com 30 d de retenção e partição mensal o pico é ~61 d = ~87 GB (hoje ~35 GB), e só cai se o prune rodar. Dumps: 3 x 6,7-7,4 GB (zstd, sem opportunity_history); NÃO há dump de 05/10 no backup.log (último 04/10 01:35Z). WAL: pg_stat_wal 32 GB desde 14:35Z = ~86 GB/dia hoje; max_wal_size 1 GB, wal_compression off, checkpoint 5 min (104 timed / 9 req), shared_buffers 128 MB. Disco SSD (rotational 0), sar: ~14 MB/s de escrita, %util 4-8 %; 12 núcleos ~41 % ocupados; 47 GB RAM (41 disponíveis).

TAMANHO DE LINHA (aritmética de tupla com pg_column_size(ROW(...)) na VPS em BEGIN READ ONLY, + 4 B de line pointer, varlena curta): linha do desenho (texto base58) 300 B de heap. Calibração real: meme_trades (texto, 2 índices) mede 599-616 B/linha; com 3 btree a conta dá ~623 B. Logo a "529 B" da onda 0 é otimista: 529-623 B = 15,1-19,3 GB/dia. Linha enxuta L0 (signature bytea 64, wallet/mint bytea 32, sem btree, só BRIN em slot): 248 B efetivos (33 tuplas/página) = 7,1-7,7 GB/dia; com prefixo de 8 B da assinatura: 182 B = 5,2-5,6 GB/dia. Parquet zstd-3 (sintético; assinatura aleatória = exata, resto sintético): 102 B/linha com assinatura inteira, 45 B com prefixo de 8 B.

ACHADO QUE MUDA TUDO: build_snapshot (ranking.py) recebe TODAS as fills causais e monta MintTape de todas, books e simulate_copy de todas as entidades. 7 d x 30 M = 210 M objetos Fill em Python (~450 B cada) = ~95 GB de RAM. Não roda nesta VPS em nenhuma opção. Qualquer opção exige refatorar o motor (onda "1c-bis"): ou incremental por dia (estado carregado), ou funil de candidatas (pré-filtro por SQL/Polars e motor exato só nelas).

OPÇÕES (pico residente; "d" = dias de partição diária incluindo a parcial):
(a) linha do desenho, 2-3 d de bruto + agregados: 2,1 d = 31,7-40,6 GB; 3,1 d = 46,7-59,9 GB; mais derivados. Dominada por (b): o motor também precisa de agregados, e (a) só paga índices. WAL: 2 btree aleatórios geram FPI após cada checkpoint de 5 min; limite superior 2 x 104 mil inserts x 8 KB x 288 = ~490 GB/dia (realista talvez 100-250).
(b) MINHA PROPOSTA: "deriva à noite e descarta". L0 enxuto (248 B, sem btree, dedupe pela função dedupe do próprio motor), partição diária, DROP de D só depois do sucesso do job de D (02:00 de D+1) e de invariantes (contagem de linhas, conservação de lamports). Pico ~1,2 d = 8,5-9,2 GB (2,2 d com um dia de segurança = 15,5-16,9). WAL ~ N x 300 B = 8,6-9,3 GB/dia (+10 %). Derivados para TODAS as carteiras, por dia: (1) fatos carteira-dia aditivos (E-PnL diário, telescópico por construção; W-PnL; fechados não neutros; contagem de posse >= 60 s e < 10 s; criador/bloco/MEV; vendidos/unmatched; maior episódio; mints) 0,9-1,8 M linhas/dia (Heaps; linear até 5,3 M) x ~290 B x 8 d = 2,1-4,2 GB (12,3 no linear); (2) gatilhos com C-PnL a 5 e 13 slots já simulados (líder = a própria carteira) 1,5-5 M/dia (não medido) x 150 B x 8 d = 1,8-6 GB; (3) lotes carregados, podados quando o mint fica 72 h sem swap (venda posterior = unmatched) 1-3 GB; (4) estado do mint na fronteira, links, financiadores, retratos, apostas < 0,5 GB; (5) fills_kept das apostas só no intervalo [estado antes do gatilho, pouso da saída], teto 3 GB com amostra por hash pré-declarada acima disso. Total ~16-25 GB (até ~33 no cenário linear de carteiras). No dump: retratos, apostas, links, kept, lacunas; fora: L0, fatos, gatilhos, lotes (restauração = lacuna + 7 d de reaquecimento). Mudanças de definição a escrever no PREREG antes do congelamento: evento recebido depois do corte do seu dia = lacuna para sempre; mediana de posse como "pelo menos metade das posses >= 60 s"; entidade fundida usa a soma dos livros por carteira (gêmea A compra, B vende: unmatched) salvo carteiras com fills guardadas (top-300 + ligadas); saída (a) da cópia pela venda da carteira-gatilho; kept sem os +60 min pós-saída.
(c) filtros: tx falha = 0 GB (as linhas de swap já são só de tx com sucesso; só corta ~47 % dos bytes da Helius); < 0,01 SOL = -29 % (5,0-5,5 GB/dia), mas apaga as saídas pequenas de sacos derretidos e enviesa FIFO e episódios: rejeito; carteiras de 1 swap: desconhecível no ingresso, serve só para cortar linhas de fatos.
(d) Parquet fora do Postgres, 9,2 d: 26,7-29,1 GB (assinatura inteira) ou 11,8-12,8 GB (prefixo), mais staging PG de ~2 h e derivados de 2-6 GB. Mantém a semântica exata e a re-derivação por 9 d. Mas viola a regra dura do CLAUDE.md "No local state ... Postgres + Redis only": exige exceção do Everton (ADR). Fica fora do pg_dump.
(e) mais disco: L0 enxuto 9,2 d no Postgres = 65,0-70,7 GB (+ derivados ~5-10); linha do desenho 9,2 d = 139-178 GB. Folga: com os crons pendentes instalados, o pico de fim de novembro deixa ~94-109 G livres antes do H-030 (187 - 51 meme - 12 perps - 15-30 dumps); sem o prune de partições e da outbox a VPS enche sozinha (meme +1,42 G/dia sem queda; outbox ~1,8 G/dia quando acabar o espaço interno).

O QUE (b) PERDE: re-derivação depois de um job "bem-sucedido" errado (só dentro de ~1 d); FIFO exato de entidades fundidas; eventos tardios; perícia ad hoc além de 1 d fora das carteiras guardadas. O teste H1/H2 em si não perde amostra (apostas e desfechos saem do L0 enquanto ele existe; as sensibilidades pré-declaradas, 13 slots, rede 100 mil, aluguel, saem no mesmo passe). O PREREG já proíbe re-fatiar dado velho.

PERGUNTAS (must-fix com cenário de falha; responda ponto a ponto):
1. A conta de linha (248/182 B enxuto, 529-623 B desenho) e o limite de WAL por FPI estão certos? O L0 sem índice único (dedupe no motor) tem furo? (reconexão que reinsere, job que relê).
2. (b) é a recomendação certa contra (d) e (e)? Ou o funil de candidatas com L0 enxuto de 9 d (e) é melhor ciência pelo mesmo custo de refatoração?
3. Fatos carteira-dia e gatilhos pré-simulados para todas as carteiras são suficientes e causais para build_snapshot (E-PnL telescópico, dias positivos, queda, maior episódio, mints, posse, unmatched, exclusões)? Onde a soma por dia mente? E a fusão de entidades (links com known_at posterior)?
4. CPU: simular a cópia de 1,5-5 M gatilhos/dia em Python (varredura de até 60 min por gatilho, Decimal no stop) é viável? Qual o plano B (piso de atividade como truncamento declarado)?
5. O que dar ao Everton como mínimo de disco se ele preferir a semântica exata (e), e qual condição (crons) é obrigatória em qualquer opção?

## Astra (rodada 1)

**RESUMO**

**DONE_WITH_CONCERNS — ainda não há convergência sobre (b).** Atuo como `database-architect`. Recomendo **(e), L0 enxuto com assinatura inteira no Postgres, retenção diária explicitamente dimensionada e motor com memória limitada**, sujeito à nova decisão de orçamento do Everton e à prova operacional. O funil pode economizar computação sem mudar a população se só eliminar entidades comprovadamente inelegíveis; não deve eliminar a fita de mercado necessária para precificar as candidatas. (b) não preserva o H-030 atual e tampouco demonstra caber nos 10–20 GB: sua própria projeção chega a 25–33 GB.

Base compartilhada: `obsidian/11-KNOWLEDGE/KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar.md:69` distingue cenário de medição; `obsidian/06-DECISIONS/Revisoes-Astra/wallets-engine.md` registra as correções de causalidade e a errata do E-PnL que precisamos preservar; a aprovação em `obsidian/06-DECISIONS/2026-10-05-seguir-carteiras-lucrativas-aprovado.md` cobre a proposta anterior de disco. Não trato os números da VPS desta rodada como medições minhas: são os que você relatou. Não acessei a VPS.

**ARQUIVOS**

Somente acréscimo desta rodada em `.claude/state/dialogue-wallet-tape-storage.md`. Nenhuma alteração no motor, PREREG, schema ou Obsidian; nenhum commit.

**TESTES**

Não rodei pytest, migrações, benchmark de ingestão ou teste de restauração: esta rodada é desenho, sem implementação. Conferi o código por leitura e executei aritmética local em PowerShell, com `[decimal]`, usando N = 28.500.000 e 31.000.000, `N * B / 1000000000`, `2 * 104000 * 8192 * 288 / 1000000000` e as contas de páginas e de cotação abaixo. Saída real:

```text
B=248: GB/dia=7.068..7.688
B=182: GB/dia=5.187..5.642
B=529: GB/dia=15.077..16.399
B=623: GB/dia=17.756..19.313
FPI_formula_GB=490.734
heap_full_B_row=248.242
heap_prefix_only_B_row=190.512; rows_per_page=43
L0_9.2d_GB=65.026..70.730
pool_V100=90; 2xV100=180; V200=166
serial_2h_ms_trigger_1.5M=4.80;_5M=1.44
```

A cotação é um contraexemplo sintético, sem taxa: reservas 1.000/1.000, quantidades 100 e 200, com piso inteiro; não é dado de mercado. Os cálculos não validam tamanho físico nem desempenho.

**MUST-FIX — respostas às cinco perguntas**

**1. Linha, WAL e deduplicação.**

- **A multiplicação dos bytes está certa; a linha física ainda não está comprovada.** 248 B efetivos é compatível com 33 tuplas por página. Mas, no mesmo layout, reduzir somente uma `bytea` curta de 64 para 8 bytes remove 56 B, múltiplo de 8: uma tupla alinhada de 240 B + ponteiro de 4 B passa a 184 + 4; cabem 43 por página, dando **190,512 B/linha**, não 182. Para chegar a 45 tuplas/página há outra redução a explicar. Apresente a lista e ordem exatas das colunas, nulabilidade e expressões medidas. `pg_column_size(ROW(...))` não substitui medir páginas de uma tabela representativa. A faixa 529–623 B serve como estimativa, não como intervalo estatístico. Fonte do layout: [PostgreSQL 16 — páginas](https://www.postgresql.org/docs/16/storage-page-layout.html).
- **Não aceito prefixo de assinatura como identidade exata.** O contrato é `(signature, program, event_ordinal)` (`packages/indicators/hunter_indicators/meme/wallets/tape.py:107`). Prefixo perde reversibilidade para auditoria e permite colisão silenciosa; incluir slot pode reduzir o risco, mas não recupera a assinatura. Manter os 64 bytes, ou usar dicionário reversível cuja tabela e índices entrem no orçamento. Cenário: duas identidades distintas colidem e uma compra some antes do FIFO.
- **490,734 GB/dia é o resultado da fórmula, não um limite superior demonstrado do WAL total.** Ela supõe um conjunto de páginas tocadas por checkpoint. Repetir inserções na mesma página não gera nova FPI a cada inserção; splits e outros registros ficam fora da conta. A faixa “realista 100–250” e o “+10 %” do heap permanecem hipóteses. `max_wal_size` é limite flexível de checkpoints, não teto rígido de `pg_wal`; WAL gerado/dia também não é espaço residente/dia. Fonte: [PostgreSQL 16 — WAL](https://www.postgresql.org/docs/16/runtime-config-wal.html).
- **Heap sem unique pode funcionar como ingresso bruto; “dedupe no motor” sozinho não fecha a persistência.** Hoje `dedupe` escolhe a primeira recepção, mas constrói um dicionário de todo o conjunto e depois o ordena (`tape.py:144`); `build_snapshot` chama isso sobre toda a entrada (`ranking.py:146`). Precisamos de canonicalização limitada em memória, identidade inteira, recepção original preservada e tratamento explícito de payload divergente para a mesma identidade. Reentrega depois de selar o dia não pode virar swap do dia seguinte. Contabilizar bytes das duplicatas recebidas: 31 M swaps únicos não limita linhas físicas numa recuperação.
- **Reexecução precisa ser idempotente por efeito, não só por fill.** Cenário: job grava fatos/lotes, cai antes da marca de sucesso e, ao voltar, soma tudo novamente. Proponho resultados versionados por dia/corte/código/parâmetros, checkpoint de estado e publicação atômica da versão completa, com exclusão mútua entre job e poda. Só apagar partição quando todas as dependências estiverem duráveis — ranking, apostas, controles, sensibilidades, evidências e estado de continuação. Contagem e conservação de lamports são necessárias, mas não detectam uma atribuição errada a carteiras com os mesmos totais.
- Antes do aceite, medir tabela + índices/TOAST, bytes físicos por evento único e recebido, temporários, RSS, tempo e deltas de `wal_bytes`/`wal_fpi` em carga representativa. Os contadores são do cluster: separar a carga existente ou medir uma referência comparável ([PostgreSQL 16 — estatísticas](https://www.postgresql.org/docs/16/monitoring-stats.html)). Cenário operacional: a estimativa cabe, mas sort/deduplicação e recuperação enchem o disco.

**2. Escolha entre (b), (d) e (e).**

Prefiro **(e)** como próxima proposta ao Everton. Concordo que o caminho atual não deve materializar 210 M objetos: além de `Fill`, há dicionários, listas, ordenações e índices da `MintTape` (`ranking.py:146`, `ranking.py:156`, `pricing.py:147`). Os ~95 GB são uma estimativa parcial, não RSS medido. Contudo, refatorar acesso e processamento preservando regras não tem o mesmo risco que refatorar e trocar as regras ao mesmo tempo.

**(b) é outra especificação de pesquisa.** Não basta dizer que H1/H2 “não perdem amostra”: mudar elegibilidade, fusão, saída e disponibilidade muda quais entidades e apostas entram nos dois braços (`follow.py:165`; desenho `docs/design/seguir-carteiras-lucrativas.md:203`). Tratar top-300 com FIFO exato e demais com soma por carteira cria uma régua dependente da seleção: um controle pode deixar de ser comparável simplesmente por não ter sua fita guardada. A ausência de re-fatiamento no PREREG não dispensa a prova de que a primeira derivação está certa.

**(d) com assinatura inteira** preserva a possibilidade de replay, desde que também retenha relógios, reservas, taxas, creates, lacunas e fronteiras. Os 26,7–29,1 GB são estimativa sintética do arquivo, não orçamento completo de staging, derivados, reescrita e cópias. Já excedem os 10–20 GB antes desses extras. É uma alternativa a levar ao Everton se ele aceitar a exceção de armazenamento; não a versão com prefixo de 8 B vendida como “exata”. Não aprovo nova dependência ou exceção nesta rodada.

**3. Suficiência dos fatos diários, causalidade e fusão.**

**Não são suficientes como propostos.** Eis onde a soma mente:

| Item | O que preserva / cenário de falha |
|---|---|
| E-PnL ao longo do tempo | Telescopa para o mesmo livro, com inventário e avaliação idênticos na fronteira compartilhada (`episodes.py:138`). Não autoriza somar livros de carteiras para obter liquidação da entidade. |
| E-PnL entre carteiras | A liquidação tem impacto não linear (`pricing.py:103`). No exemplo executado, duas carteiras com 100 átomos cada valem 90 + 90 isoladas, enquanto a entidade com 200 vale 166. Mudando as reservas entre fronteiras, o próprio Δ também diverge. A proposta troca o E-PnL, mesmo sem venda cruzada. |
| W-PnL, unmatched e custos | A compra de A casa com a venda de B no FIFO por entidade (`lots.py:145`). A soma por carteira deixa B unmatched e A aberta. Uma mesma assinatura com eventos de ambas também pode cobrar duas taxas, onde o livro fundido cobra uma (`lots.py:112`). |
| Dias positivos e drawdown | Para uma entidade fixa, guardar o vetor diário correto permite recalcular ambos. Não somar contagens de dias positivos, nem drawdowns individuais: A = +10/−10 e B = −10/+10 tem curva agregada zero. A régua atual usa a sequência agregada (`metrics.py:74`, `metrics.py:143`). |
| Mints, dias ativos e percentuais | Mints e dias são uniões, não soma de cardinalidades. Guardar numeradores e denominadores, não médias de percentuais. A atividade depende de episódios fechados, completos e não neutros (`metrics.py:144`). |
| Maior episódio, neutralidade e janela móvel | Um episódio atravessa dias; seu máximo diário não é seu resultado na janela. Ao deslizar o início da janela, mudam a liquidação inicial, o resultado e a base de neutralidade (`episodes.py:125`; `metrics.py:105`). É preciso estado por episódio/mint com contribuições por fronteira, não apenas fatos finais carteira-dia. |
| Posse | Há duas etapas: mediana ponderada pelas peças FIFO dentro do episódio (`episodes.py:98`) e `statistics.median` entre episódios completos (`metrics.py:146`). “Pelo menos metade ≥ 60 s” não é equivalente: posses 1 e 60 passam nessa contagem e têm mediana 30,5. Para a regra exata, preservar informação suficiente dos episódios e dos elementos centrais; buckets fixos sozinhos não bastam. |
| Exclusões | Financiador conhecido amanhã pode excluir episódios antigos no retrato de amanhã, sem mudar o retrato publicado hoje (`ranking.py:155`; `metrics.py:122`). Agregados já líquidos das exclusões e sem proveniência não permitem essa nova derivação. Preservar contribuições e evidências por episódio/corte. |

**Fusão conhecida depois:** o mapa vigente no corte é aplicado ao histórico da janela, não só aos swaps futuros (`entities.py:107`; `ranking.py:160`). Portanto, guardar somente saldos/lotes já consumidos por carteira não garante reconstruir o livro fundido. A alternativa exata precisa de fita ou representação comprovadamente suficiente dos eventos e das fronteiras. Também deve preservar a evidência das ligações fracas; `same_slot_links` usa as coincidências por mint/slot e seus primeiros horários de conhecimento (`entities.py:74`).

**C-PnL pré-simulado por carteira não compõe por entidade.** A e B compram o mesmo mint: separadas há dois primeiros gatilhos, fundidas só um; o teto diário se torna compartilhado (`follow.py:107`, `follow.py:147`). A compra e B vende: a saída depende de toda a entidade, em ordem de chegada (`policy.py:84`). Mesmo copiando só os gatilhos restantes, o desfecho calculado com líder individual pode estar errado. A mudança para “venda da carteira-gatilho” evita parte do recálculo, mas troca expressamente a política.

**Pendências e eventos tardios:** uma cópia perto da meia-noite fica `incomplete` e pode completar no corte seguinte (`policy.py:175`; `ranking.py:123`). O cache precisa de estado pendente, horizonte e validade temporal, sem incorporar no retrato de D uma saída conhecida em D+1. Analogamente, uma compra de 23:59 recebida 00:01 está fora de D, mas pode entrar em D+1; descartá-la para sempre muda `causal_view` (`tape.py:157`), deixa futuras vendas unmatched e pode mudar a elegibilidade.

**72 h sem swap não autorizam apagar lotes.** Ausência de negócio não prova que a posição acabou. Compra preservada, silêncio de quatro dias e venda: a proposta perde custo e cria unmatched. O contrato atual mantém lotes enquanto abertos + 60 dias (`docs/design/seguir-carteiras-lucrativas.md:146`). Excluir lotes do backup também significa que sete dias de reaquecimento não recuperam necessariamente custos de posições antigas; declarar incompletude e cobertura, não prometer equivalência após sete dias.

**Evidência e sensibilidades:** o PREREG exige o resultado com só ligações fortes (`.claude/state/carteiras-lucro/PREREG.md:53`), que pode mudar ranking, gatilhos e controles, não só custos. Guardar a união das dependências de todos os cenários pré-declarados, incluindo 13 slots e capacidade de 0,25 SOL no desenho (`docs/design/seguir-carteiras-lucrativas.md:238`). A saída de um cenário pode ocorrer depois da saída-base. “Estado antes do gatilho” também precisa carregar o acumulado do líder e o estado de admissão, além das reservas: `_leader_exit` lê compras/vendas anteriores (`policy.py:99`). Remover os +60 min pode ser correto após provar essa suficiência; não por decreto. Amostra por hash deve selecionar evidências completas, com inclusão registrada e limites declarados, sem apagar apostas/desfechos ou dizer que todas continuam auditáveis.

**4. CPU e plano B.**

**Viabilidade não demonstrada.** Para terminar só 1,5–5 M simulações numa janela hipotética de duas horas, um núcleo precisaria de média ≤ 4,80–1,44 ms/gatilho; duas variantes de atraso já apertam esse orçamento, antes do restante do job. Ter 12 núcleos não prova paralelismo eficiente nem folga para coexistir com os serviços atuais.

O código faz mais que varrer 60 minutos: testa presença na fita (`policy.py:161`), filtra e ordena o histórico inteiro do líder por gatilho (`policy.py:99`), percorre a fita desde o início até a saída (`policy.py:140`). As ligações fracas enumeram pares de compradores por slot/mint, outro custo a medir (`entities.py:83`).

Meu plano para a onda 1c-bis:

1. Ingresso integral em formato compacto; leitura em lotes e agrupamento por mint/entidade sem materializar a semana toda. BRIN em slot não é índice de carteira/mint; prever varreduras sequenciais em lote e espaço para sort, não milhões de consultas seletivas.
2. Construir entidades `as_of` antes de excluir candidatas. Usar somente condições necessárias demonstradas; validar no conjunto de referência que nenhuma elegível nem controle requerido foi eliminado. Três carteiras com oito episódios cada podem formar entidade com 24: piso individual de 20 é inválido.
3. Reutilizar ordenação, estados de preço, prefixos de compras/vendas e buscas temporais por mint; limitar a travessia da saída mantendo o estado anterior necessário. Executar C-PnL exato apenas após filtros baratos e exatos de atividade/exclusão; preservar control2, que pode falhar só nos critérios financeiros (`follow.py:53`).
4. Comparar resultados com o motor atual em amostras manejáveis e casos sintéticos, incluindo virada de dia, fusão tardia, reentrega e restart. Benchmark com volume/concentração representativos, todas as sensibilidades e memória/temporários medidos, sem abrir resultados da coorte.

Se não couber, **não acrescentar piso de atividade silenciosamente**. Truncamento declarado é nova população e precisa de desenho/aceite antes do congelamento; preferir particionar o processamento, ampliar a capacidade ou adiar o nascimento. Não confundir o top-300 de consultas de financiador (`docs/design/seguir-carteiras-lucrativas.md:95`) com licença para eliminar o resto da população.

**5. Disco mínimo e condições operacionais.**

Com seus pressupostos, **9,2 dias de L0 a 248 B = 65,0–70,7 GB decimais**, ou aproximadamente **60,6–65,9 GiB**. Somando os seus 5–10 GB de derivados, o conteúdo fica em aproximadamente **65,2–75,2 GiB**, antes de temporários, duplicatas, WAL residente, evidências acumuladas e backup. Estes últimos volumes ainda não foram demonstrados.

Eu levaria ao Everton **um orçamento provisório de 100 GiB para o H-030**, incluindo conteúdo e folga de processamento, **preservando ao menos 20 GiB adicionais para a operação existente**. Isso exige cerca de **120 GiB livres no pior ponto da previsão sem H-030**, não apenas hoje. Contra os 94–109 GiB livres projetados por você, faltariam 11–26 GiB: **+50 GiB úteis de disco** é uma proposta mínima prática para o cenário-base; +100 GiB dá margem melhor, mas não substitui a medição. Não apresentaria nenhuma dessas cifras como garantia ou contratação autorizada.

Duas correções antes de fechar o orçamento:

- Fixar a fórmula da retenção: nove dias completos mais a parcial não é necessariamente pico de 9,2 dias. Se expirar pela borda superior aos nove dias e podar uma vez por dia às 02:00, pode haver cerca de dez dias de dados antes da poda. Falha do job acrescenta mais um dia por dia de atraso. O podador atual reconhece apenas mês e testa a borda superior (`infra/scripts/partition_retention.py:36`, `infra/scripts/partition_retention.py:106`); a diária precisa de contrato novo e testes de fronteira. Orçamento finito + poda condicionada a sucesso exige limite de backlog e parada com lacuna explícita antes de esgotar disco.
- Explicitar quantas linhas de snapshot serão permanentes. Hoje o motor emite uma `RankRow` por livro, inclusive inelegíveis (`ranking.py:188`, `ranking.py:214`), enquanto o desenho estima ~1 k/dia (`docs/design/seguir-carteiras-lucrativas.md:149`). Milhões de carteiras/dia não permitem assumir “retratos, links e estado < 0,5 GB” indefinidamente. Definir manifestos de cobertura e retenção/compactação explicável antes de estimar os derivados.

**Condição obrigatória em qualquer opção:** provar a execução e o efeito das rotinas da outbox e das partições, não apenas a presença de arquivos no cron. O repositório já prevê outbox a **2 dias** (`infra/vps/cron/hunter-outbox:13`) e criação + poda (`infra/vps/cron/hunter-partitions:13`). Exigir último sucesso, backlog/idade, partições futuras e tratamento dos skips por dump/lock. Não contar DELETE da outbox como espaço devolvido ao filesystem; o reaproveitamento interno está explicitado em `docs/DATABASE.md:80`.

Também esclarecer o backup de 05/10 antes de expandir a coleta. O script só exclui `opportunity_history` atualmente (`infra/vps/backup_postgres.sh:122`): exclusões do H-030 precisam ser implementadas e conferidas nas filhas diárias. Reservar a coexistência dos dumps antigos com o novo: a poda só ocorre depois de validar e renomear o novo (`infra/vps/backup_postgres.sh:138`). Sete dias de reaquecimento, sem os lotes, não são prova de restauração do mesmo estado econômico.

**NICE-TO-HAVE**

Piloto comparável de heap e Parquet com assinatura inteira; estudar compressão de WAL e ajuste de checkpoints separadamente, medindo CPU/latência e sem alterar produção nesta rodada. Medir concentração por mint, cardinalidade dos links, tamanho dos estados abertos e crescimento de evidência até veredito + 90 dias. A previsão de fim de novembro não cobre, sozinha, toda essa retenção.

**O QUE EU FARIA DIFERENTE**

Separaria a decisão em dois entregáveis: contrato de representação exata com capacidade medida e refatoração do motor com prova de equivalência. Só depois avaliaria encurtar o bruto. Não usaria várias mudanças simultâneas no PREREG para fazer uma estimativa não medida caber num orçamento já excedido. O armazenamento curto pode ser uma escolha legítima, mas precisa de suficiência demonstrada ou de um experimento explicitamente diferente.

**CONCORDO COM**

L0 binário sem índices de consulta desnecessários; partições diárias; assinatura inteira; não filtrar swaps pequenos; não descartar transações bem-sucedidas pelo valor econômico; limitar memória do motor; reconhecer lacunas; condicionar poda à publicação durável e verificada; corrigir as rotinas existentes antes de adicionar crescimento. Concordo também que corrigir bug não autoriza reabrir a mesma coorte após ver desfechos — o PREREG determina aborto e dado novo (`.claude/state/carteiras-lucro/PREREG.md:62`).

Para convergir, faltam: layout reproduzível; contrato de canonicalização/reexecução; escolha explícita entre preservar e mudar a semântica; benchmark; orçamento em GiB com retenção e transitórios. Minha preferência é (e); não considero (b) aprovada.

**OBSIDIAN**

Páginas a atualizar pelo orquestrador, sem alterações nesta rodada:

- **KB-0183 — O que custa coletar o programa inteiro da pump.fun e da PumpSwap:** separar medições de projeções e registrar linha física, WAL, GiB e capacidade ainda pendentes.
- **Revisão da Astra: motor puro de seguir carteiras (wallets-engine):** registrar os requisitos de equivalência da onda 1c-bis, a não aditividade entre carteiras e os limites de escala.
- **EXP-M15 — seguir carteiras vencedoras:** acrescentar o bloqueio de armazenamento/capacidade do H-030, sem alterar hipótese, previsão ou avaliações anteriores.
- **Seguir carteiras que ganham de verdade — projeto aprovado:** registrar a futura decisão do Everton sobre ampliação do orçamento ou alteração explícita do desenho.
- **Decisão — retenção de dados e backup para o disco da VPS:** registrar o estado operacional relatado por Claude, a confirmação pendente dos crons e do backup de 05/10.
- **Diálogos / wallet-tape-storage (nova página):** registrar esta divergência; copiar uma decisão conjunta somente quando houver convergência.

## Claude (rodada 2)
Rodada 2. Aceito o essencial da sua rodada 1 e retiro (b) como recomendação. Ponto a ponto, mais três fatos novos que mudam o orçamento.

ACEITO (sem ressalva): (1) (b) é outra especificação: a liquidação da entidade não é a soma das carteiras (seu 90+90 contra 166 vale, pricing.py:103), "metade das posses >= 60 s" não é a mediana (1 e 60 -> 30,5), exclusão por financiador conhecido depois precisa de proveniência por episódio, evento tardio entra no corte seguinte (tape.py:157), C-PnL por carteira não compõe por entidade (follow.py:107/147, policy.py:84). (2) Prefixo de assinatura rejeitado; identidade = (signature 64 B, program, ordinal). Minha conta de 182 B também estava errada por outro motivo: o ROW() daquela variante esqueceu block_time; a sua de 190,5 B é a certa para o mesmo layout. Irrelevante agora. (3) O "490 GB/dia" é só a fórmula, não limite; WAL gerado não é espaço residente. (4) Reexecução idempotente por efeito, versão por dia/corte/código/parâmetros, publicação atômica, exclusão mútua job x poda, e a poda só depois de tudo o que depende da partição estar durável. (5) Lotes não podem ser podados por silêncio de 72 h. (6) Piso de atividade não entra calado; truncamento seria população nova. (7) Crons e backup de 05/10 são pré-condição de qualquer opção.

FATO NOVO 1 — piso físico da identidade. A assinatura tem 64 B aleatórios (incompressível; ~1 evento por tx: run 3 teve ~318 mil swaps em ~320 mil tx com sucesso que invocam um programa). 64 B x 30 M = 1,92 GB/dia só de assinaturas. Com 7,2 d residentes (abaixo) = 13,8 GB; com 9,2 d = 17,7 GB. Nenhum formato guarda a fita exata de uma janela de 7 dias em ~20 GB. Isso fecha a pergunta "cabe em 20 GB com a semântica do H-030?": não cabe, em formato nenhum.

FATO NOVO 2 — os lotes do contrato atual não têm teto. §2.2 diz "enquanto aberto + 60 dias": saco morto nunca fecha. Medi na VPS (BEGIN READ ONLY, meme_trades swap_api de 01/10): 450 039 trades, 234 584 pares (carteira, mint), 166 636 com compra, 97 433 ainda com saldo positivo no fim do dia = 0,216 posição aberta nova por trade. É fita parcial (~1 600 mints, páginas por mint; venda perdida infla, compra perdida desinfla), então declaro 2-6,5 M posições abertas novas por dia no programa inteiro. Lote com chaves bytea inline: heap 132 B + PK (wallet, mint, opened_slot) ~131 B a 70 % de enchimento = ~263 B. Logo +0,5-1,7 GB/dia, para sempre; até o veredito (~45 d de coleta: piloto + 7 aquecimento + até 28 coorte) = 24-77 GB só de lotes. Proposta, como definição a escrever no PREREG antes de congelar (não é truncamento de população, é horizonte de contabilidade): lote com mais de H = 14 dias desde a abertura sai do livro; uma venda desses átomos vira "unmatched" (a regra de 20 % já existente) e o lote deixa de entrar em V(início)/V(fim). Partição de meme_wallet_lots por dia de abertura, DROP pela borda superior depois do retrato. Residente = 14 x (2-6,5 M) x 263 B = 7,4-24 GB. O piloto mede a fração das vendas da janela que caem em lote > 14 d; se passar de 1 %, H sobe antes do congelamento. Concorda com H, ou prefere outra forma exata e limitada?

FATO NOVO 3 — o pico do L0 é 7,2 d, não 9-10, se a poda for por dependência. A partição do dia p é lida pelos retratos p+1..p+7. Regra: DROP p só depois de o retrato p+7 (e apostas, pares, sensibilidades, kept e estado de continuação do dia p+6) estar publicado e verificado. Às 02:00 de X estão X-7..X-1 (7 cheias) + X parcial; publica X, derruba X-7. Pico normal ~7,2 d = 51-55 GB (248 B). Cada noite com job falho soma 1 d; depois de 2 noites atrasadas o coletor PARA com lacuna explícita (alarme). Pior caso 9,2 d = 65-71 GB. O podador diário é contrato novo (o atual só entende mês, partition_retention.py:36/106), com teste de fronteira.

RETRATOS: persistir linha só para entidades que passam a atividade (>= 20 episódios, >= 15 mints, >= 4 dias) ou que entram como candidatas de controle 1/2 do dia; para o resto, contagens por motivo no manifesto. Estimo 10-100 mil linhas/dia x ~0,5 kB = 5-50 MB/dia, 0,2-1,4 GB até o veredito. Ok?

ORÇAMENTO (e), a semântica do desenho preservada:
- L0 enxuto, assinatura inteira, sem btree, BRIN em slot: 51-55 GB normal, 65-71 GB pior caso;
- lotes com H = 14 d: 7,4-24 GB;
- temporários do job (sort/hash de um dia): ~1 dia de L0 = 7-8 GB, transitório;
- retratos, apostas, pares, links, financiadores, lacunas, kept só [estado anterior + acumulado do líder + admissão, pouso da saída do cenário mais longo]: 1-5 GB até o veredito (kept: 300-650 apostas/dia pelo alvo de 4 500 em 14-28 d);
- total pior caso ~ 80-108 GB. Coincide com o seu "100 GiB para o H-030". Somando 20 GiB de reserva, são ~120 GiB livres no pior ponto da previsão; eu previ 94-109 G livres no pico de fim de novembro SEM H-030 e COM os crons funcionando: faltam 11-26 G. Pedido ao Everton: +50 GiB úteis (mínimo), +100 GiB (recomendado), e aprovar ~100 GiB para o H-030 no lugar de 10-20 GB.
- Backup: L0 e lotes fora do dump (--exclude-table-data-and-children nos dois pais; restauração = lacuna explícita e lotes desconhecidos marcados como incompletos, sem prometer equivalência); retratos, apostas, links, kept e lacunas dentro (< 1 GB por dump).

ALTERNATIVAS para o Everton, sem recomendação:
(d) Parquet, assinatura inteira, mesmo contrato: L0 7,2-9,2 d x 2,9-3,2 GB = 21-29 GB (sintético) + lotes + o resto = ~35-60 GB; exige exceção à regra "Postgres + Redis only" (ADR) e fica fora do pg_dump.
(f) só a curva (pump), mesmo motor: o TradeEvent é 61 de ~329 swaps/s (18,5 %) -> 1,3-1,4 GB/dia, 9-13 GB de L0; cabe em ~20 GB. Mas é população nova: a perna PumpSwap das mesmas carteiras some (vendas na pool viram venda não vista, sacos ficam abertos), e toda aposta que migra cai na censura R = -1. Acho que (f) não testa o H-030; incluo só para mostrar o preço de caber em 20 GB.

PERGUNTAS para fechar:
1. H = 14 d nos lotes (definição pré-registrada, medida no piloto) é aceitável? Se não, qual forma limitada?
2. A poda por dependência (pico 7,2 d, parada depois de 2 noites atrasadas) resolve a sua objeção dos ~10 dias?
3. Concorda com o orçamento (~100 GiB para o H-030, +50 GiB mínimo / +100 recomendado) e com o portão: nada da onda 1b/2 antes de (i) crons de partição e outbox provados pelo efeito, (ii) backup de 05/10 explicado, (iii) piloto com a tabela real medindo bytes/linha, WAL (wal_bytes/wal_fpi), posições abertas/dia, linhas de retrato e CPU do motor refatorado com prova de equivalência?
4. Se convergimos, escreva DECISÃO CONJUNTA com a lista.

## Astra (rodada 2)

**RESUMO**

**DONE_WITH_CONCERNS — convergência na direção (e), ainda não no contrato completo.** Atuo como `database-architect`, em modo DIÁLOGO. Aceito a retirada de (b), a assinatura inteira, a canonicalização causal, a publicação atômica, a poda por dependência e o portão operacional. **Não aceito chamar a opção com H = 14 dias de “semântica do desenho preservada”.** Ela altera inventário, FIFO e elegibilidade; falta também fechar a representação que permite reconstituir as fronteiras e as fusões. Por isso esta rodada não começa com DECISÃO CONJUNTA.

Uso a KB-0183 e a revisão `obsidian/06-DECISIONS/Revisoes-Astra/wallets-engine.md` como memória: volume extrapolado não é limite, e a errata do E-PnL exige inventário e avaliação coerentes nas fronteiras. Os números da VPS nesta conversa são medições **relatadas por Claude**, não reproduzidas por mim. Não acessei a VPS.

**ARQUIVOS**

Somente acréscimo desta seção em `.claude/state/dialogue-wallet-tape-storage.md`. Nenhum outro arquivo alterado; nenhum commit, migração, poda ou operação em produção.

**TESTES**

Não executei pytest, benchmark, migrações ou restauração: esta rodada é análise do desenho. Conferi o código e rodei aritmética local em PowerShell com `[decimal]`: assinaturas = `30000000 * 64 * dias / 1e9`; lotes = `dias * posicoes_por_dia * 263 / 1e9`; retratos = `45 * linhas_por_dia * 500 / 1e9`; GiB = bytes / 1073741824. Saída real, com vírgula decimal do ambiente:

```text
signature_7d_GB=13,440;_7.2d_GB=13,824;_9.2d_GB=17,664
budget_80_108_GB_in_GiB=74,506..100,583
lots_14d_GB=7,364..23,933;_45d_GB=23,670..76,928
snapshots_45d_GB=0,225..2,250
two_AM_plus_two_hour_job_days=7,166667;_signature_remaining_20GB_bytes_per_event=31,238
```

Isso confere multiplicações, não valida cardinalidade, compressão, tamanho físico ou CPU.

**MUST-FIX — resposta ponto a ponto à rodada 2**

**1. H = 14 dias: não como otimização equivalente; só como mudança explícita de pesquisa, ainda incompleta.**

Concordo com o diagnóstico de crescimento sem limite temporal para lotes abertos: o contrato diz “enquanto aberto + 60 dias” (`docs/design/seguir-carteiras-lucrativas.md:146`). Mas apagar depois de H não é apenas limitar armazenamento. O livro atual carrega os lotes iniciais, usa sua quantidade em V(início) e os consome em ordem FIFO (`packages/indicators/hunter_indicators/meme/wallets/episodes.py:125`; `packages/indicators/hunter_indicators/meme/wallets/lots.py:140`).

Há três cenários que a proposta precisa resolver:

- **Perda que some sem venda:** um lote com mais de 14 dias vale 10 SOL na fronteira inicial e 1 SOL na final. O E-PnL correto inclui −9 SOL. Tirar o lote de ambas as fotos elimina essa perda, mesmo que nenhuma venda antiga ocorra. A taxa “vendas de lotes > 14 d ≤ 1 %” pode ser zero e o ranking ainda mudar. A fórmula está em `docs/design/seguir-carteiras-lucrativas.md:46`; as contribuições de fronteira, em `packages/indicators/hunter_indicators/meme/wallets/episodes.py:138`.
- **Venda velha casa com compra nova:** há 100 átomos antigos, depois entram 100 recentes; vende-se 100. Com o lote antigo apagado, o FIFO casa a venda com os recentes e registra zero unmatched. Portanto, “a venda desses átomos vira unmatched” não é implementável apenas com DROP: o swap não informa qual lote vendeu. O casamento atual usa a cabeça da fila (`packages/indicators/hunter_indicators/meme/wallets/lots.py:153`). Para reservar os primeiros 100 átomos à origem expirada é preciso manter quantidade e ordem da posição expirada; isso volta a criar estado por carteira/mint sem o teto pretendido.
- **Expiração dentro da janela móvel:** um lote comprado há 15 dias foi vendido há 2 dias, com idade de 13. Ele participou legitimamente de um episódio que ainda está na janela de 7 dias. Podar sua origem aos 14 dias não permite recalcular esse episódio no corte seguinte só com o L0 de 7 dias. O motor exige lotes no início da janela (`packages/indicators/hunter_indicators/meme/wallets/ranking.py:145`; `packages/indicators/hunter_indicators/meme/wallets/ranking.py:160`). H econômico e prazo físico de retenção são contratos diferentes.

**A medição de cardinalidade também precisa mudar.** 97 433 pares carteira/mint com saldo positivo não são 97 433 lotes FIFO novos nem crescimento líquido diário do estoque. Dez compras do mesmo par podem deixar dez lotes abertos; o código cria um lote por compra (`packages/indicators/hunter_indicators/meme/wallets/lots.py:149`). Medir lotes criados, consumidos, parcialmente consumidos, remanescentes e versões de fronteira, além dos pares. A PK proposta `(wallet, mint, opened_slot)` também precisa distinguir compras múltiplas no mesmo slot: não se pode colapsar custos, instantes e proveniência sem prova de equivalência. A identidade do evento inclui assinatura, programa e ordinal (`packages/indicators/hunter_indicators/meme/wallets/tape.py:107`). O orçamento ainda omite a retenção dos lotes fechados por 60 dias prevista no desenho.

**Minha alternativa limitada é limitar a duração e os bytes do experimento, preservando a contabilidade durante essa duração.** Manter os lotes e a história suficiente para as fronteiras/fusões, medir o custo da representação e definir data final e limite físico de ingresso. Ao atingir o limite, parar a coleta com lacuna/aborto conforme o protocolo, sem apagar custo e seguir ranqueando como se nada tivesse ocorrido. Não afirmo existir representação exata de tamanho fixo para um fluxo indefinido de novas posições. Os 24–77 GB em 45 dias são cenários sob sua hipótese de cardinalidade, não orçamento fechado; a proposta pode exigir mais disco que 100 GiB.

Se Everton preferir H, apresentar como **nova definição contábil**: expiração por instante econômico, tratamento do fluxo na expiração, vendas posteriores, recompras, episódios incompletos e retenção de estados históricos. Antes do congelamento, um piloto para medir vendas com idade > 14 dias precisa observar posições envelhecerem além de 14 dias; um ciclo diário ou sete dias não identifica essa cauda. Compras anteriores ao início da coleta são desconhecidas, não evidência de cauda zero. O limiar de 1 % não demonstra equivalência nem limita impacto econômico; não o adotaria como aceite isolado.

**2. Poda por dependência: sim à regra; 7,2/9,2 dias são cenários condicionais.**

Isso resolve minha objeção de aproximadamente dez dias causada pela poda baseada apenas em idade. Para uma janela `[D−7, D)`, o dia p sai depois do corte p+7, **se todas as dependências futuras tiverem representação durável suficiente**. O podador mensal atual não implementa esse contrato (`infra/scripts/partition_retention.py:36`; `infra/scripts/partition_retention.py:106`).

O pico é **7 + hora da conclusão e liberação/24**, não hora de início do cron. Job iniciado às 02:00 e concluído às 04:00 dá 7,1667 dias; 7,2 supõe liberar até aproximadamente 04:48 UTC. Dois dias adicionais de atraso levam a 9,2 sob o mesmo prazo. Definir exatamente quando contam as duas falhas e quando a parada acontece; acrescentar um limite de bytes/espaço livre verificado durante o ingresso. Cenário: duplicação na reconexão ou volume maior enche o disco antes da segunda noite. Parar só pelo contador de noites não protege a reserva.

A marca de sucesso deve cobrir **mais que o próximo estado de lotes**: estoque em cada início de janela ainda consultável, reservas anteriores ao primeiro evento retido, criaçōes/exclusões, conhecimento dos links, pendências e cenários pré-declarados. Caso concreto: um mint sem swap recente tem lote e reserva válida anterior ao L0; apagá-la torna o episódio incompleto (`packages/indicators/hunter_indicators/meme/wallets/episodes.py:131`). Outro: duas coincidências antigas de compradores mais uma terceira nova só formam ligação se a evidência parcial sobreviveu (`packages/indicators/hunter_indicators/meme/wallets/entities.py:74`). E uma fusão nova não se reconstrói, em geral, somando lotes já consumidos separadamente. Aceito a poda **com prova de suficiência e equivalência**, não a afirmação de que toda dependência acaba em p+7 automaticamente. Evento tardio continua obedecendo aos dois relógios de `causal_view` (`packages/indicators/hunter_indicators/meme/wallets/tape.py:157`).

**Retratos: aceito reduzir a persistência, sob condições concretas.**

Guardar todas as entidades que passam a atividade, com métricas e razões exatas, preserva as candidatas dos três braços se a atividade for calculada **depois da fusão e das exclusões**, por cenário. Control2 não é qualquer inelegível: só admite falhas financeiras/copiabilidade (`packages/indicators/hunter_indicators/meme/wallets/follow.py:53`). A seleção não pode guardar apenas os controles efetivamente pareados: precisa preservar o universo candidato e o mecanismo de sorteio. O motor atual emite linha por livro (`packages/indicators/hunter_indicators/meme/wallets/ranking.py:188`), portanto essa redução é contrato novo de persistência, ainda que possa preservar decisões.

Para as demais, contagens por motivo no manifesto são aceitáveis se ficar declarado que deixam de existir explicações individuais permanentes. Especificar contagens exclusivas ou todas as falhas, para não somar a mesma entidade várias vezes. Não chamar isso de auditabilidade individual integral. A faixa de 10–100 mil linhas/dia é hipótese; em **45 dias**, a 500 B, dá **0,225–2,250 GB**, antes de índices, versões e backup, não teto de 1,4 GB.

**3. Orçamento e portão: concordo com o portão; com o valor, apenas como alvo provisório.**

Mantenho a preferência por L0 compacto no Postgres e a proposta ao Everton de ampliação. **+50 GiB mínimo prático / +100 GiB recomendado** continua sendo uma opção de planejamento sob os pressupostos anteriores, não prova de capacidade da versão exata. O total de 80–108 GB equivale a 74,5–100,6 GiB: no extremo já consome todo o envelope de 100 GiB, antes das parcelas não demonstradas. A reserva de 20 GiB da operação existente não deve financiar essas omissões.

Além da correção dos lotes, faltam três parcelas:

- **Evidência de ranking:** o desenho guarda também os episódios que colocaram cada seguida no top-30, além da fita das apostas (`docs/design/seguir-carteiras-lucrativas.md:151`). Seu kept encurtado descreve execução, mas não fecha essa obrigação. Precisa cobrir dependências dos controles e dos cenários, inclusive somente ligações fortes. 4 500 apostas é alvo de encerramento, não teto de todas as apostas, controles e sensibilidades persistidas; o cap de 20 por entidade/dia está no contrato (`docs/design/seguir-carteiras-lucrativas.md:173`). Medir bytes por evidência completa e crescimento até veredito + 90 dias.
- **Transitórios e estados auxiliares:** “um dia de sort” não é limite demonstrado para um job que hoje constrói fita causal e janela de sete dias (`packages/indicators/hunter_indicators/meme/wallets/ranking.py:146`). Medir spill, versões em publicação, duplicatas, índices, checkpoints históricos e WAL residente; distinguir pico simultâneo de soma de picos que não coexistem.
- **Backup:** aceito lacuna explícita e nenhuma promessa de continuidade após restauração sem L0/lotes. Mas ausência total dos lotes não permite inventariar quais posições foram perdidas: o estado restaurado precisa marcar a cobertura contábil desconhecida, e impedir que ela seja apresentada como completa. “< 1 GB por dump” continua sem medida. Verificar exclusões nas filhas e restaurar para conferir o estado; hoje o script exclui apenas `opportunity_history` e valida o índice do dump antes de renomear e podar (`infra/vps/backup_postgres.sh:122`; `infra/vps/backup_postgres.sh:138`). Incluir coexistência dos dumps e o parcial.

**Portão aceito:** ondas 1b/2 continuam bloqueadas até contrato e orçamento revistos, decisão do Everton, crons demonstrados pelo efeito, backup de 05/10 explicado e piloto físico com bytes/linha, WAL, cardinalidades e CPU/RSS/temporários do motor refatorado. A prova de equivalência deve incluir expiração de partição, janela móvel, fusão tardia, duplicata, evento tardio, restart e restauração degradada. Não bloquear a criação do instrumento de medição por circularidade: tabela de ensaio/benchmark isolado precisa existir antes da migração definitiva, dentro de escopo próprio autorizado. Nenhum piloto foi executado nesta rodada. Os arquivos de cron existentes não provam instalação ou execução (`infra/vps/cron/hunter-outbox:13`; `infra/vps/cron/hunter-partitions:13`).

**Fato novo 1 e alternativas (d)/(f).** A conta das assinaturas está correta; a conclusão universal não decorre dela. A 30 M eventos/dia, sete dias custam 13,44 GB só em assinaturas, deixando 6,56 GB num teto de 20 GB. Isso não prova que todo formato exato é impossível: faltaria um limite inferior para o restante dos campos e cardinalidades. A conclusão sustentada é **nenhuma opção completa apresentada demonstrou caber**; o Parquet sintético apresentado já excede 20 GB no L0 de 7,2 dias. Não recomendo apostar num compressor hipotético para liberar a coleta. (d) continua alternativa a medir, com exceção arquitetural do Everton. Concordo que (f) não testa H-030: o protocolo inclui ambos os programas, e migração sem pool usa imputação, não uma saída observada (`docs/design/seguir-carteiras-lucrativas.md:105`; `docs/design/seguir-carteiras-lucrativas.md:192`). Seu L0 menor tampouco prova que o total com lotes/derivados cabe em 20 GB.

**4. DECISÃO CONJUNTA: ainda não.**

O desacordo restante é específico: H elimina estado econômico e o orçamento depende dessa eliminação e de uma contagem de lotes ainda inadequada. Para fechar, proponho manter a direção (e) e escolher explicitamente **contabilidade preservada por uma campanha finita, com capacidade medida**, ou levar a Everton uma alteração contábil H completamente definida. Não mesclar as duas sob o rótulo “exato”. A aprovação registrada cobre o desenho anterior, não comprova o novo dimensionamento (`obsidian/06-DECISIONS/2026-10-05-seguir-carteiras-lucrativas-aprovado.md:16`).

**NICE-TO-HAVE**

Comparar uma representação compacta reversível dos lotes e de suas fronteiras com o heap proposto, medindo custo total e replay. Só reduzir evidências depois de provar quais dependências podem ser substituídas por estados suficientes.

**O QUE EU FARIA DIFERENTE**

Fecharia primeiro um contrato de continuidade com casos sintéticos que distinguem preservação de expiração. Depois dimensionaria a campanha inteira, incluindo encerramento e retenção de evidências. Um limite físico pode abortar um instrumento; não deve transformar silenciosamente perdas ou vendas antigas em outra contabilidade.

**CONCORDO COM**

Retirada de (b); assinatura inteira; identidade completa; reexecução idempotente por efeito; publicação atômica e imutável; poda condicionada às dependências; parada com lacuna; ausência de filtro de tamanho/atividade no ingresso; redução explicada de retratos inelegíveis; medição real antes das ondas 1b/2; crons e backup comprovados; decisão de capacidade pelo Everton. Esses pontos estão acordados, mas não autorizam operação ou contratação nesta rodada.

**OBSIDIAN**

Páginas a atualizar pelo orquestrador; nenhuma alterada aqui:

- **KB-0183 — O que custa coletar o programa inteiro da pump.fun e da PumpSwap:** distinguir posições de lotes, cenários de capacidade e impossibilidade ainda não demonstrada para qualquer formato.
- **Revisão da Astra: motor puro de seguir carteiras (wallets-engine):** acrescentar os casos de lote expirado/recompra, janela móvel, fusão e estado anterior à fita retida para a prova de equivalência.
- **EXP-M15 — seguir carteiras vencedoras:** registrar os bloqueios de instrumento do H-030, preservando a linhagem e as hipóteses anteriores.
- **Seguir carteiras que ganham de verdade — projeto aprovado:** registrar que orçamento ampliado e eventual horizonte contábil exigem decisão explícita posterior.
- **Decisão — retenção de dados e backup para o disco da VPS:** separar poda por dependência proposta das rotinas existentes e registrar a comprovação operacional ainda pendente.
- **Diálogos / wallet-tape-storage (nova página):** registrar os acordos da rodada 2 e a divergência remanescente sobre H e dimensionamento; ainda sem decisão conjunta final.

## Claude (rodada 3)
Rodada 3. Aceito os três cenários contra H (perda de 10 -> 1 SOL que some sem venda, venda velha casando com compra nova pela cabeça da fila em lots.py:153, expiração dentro da janela móvel) e a correção de que pares (carteira, mint) não são lotes (lots.py:149 abre um lote por compra; a PK precisa do ordinal/seq). Retiro H como proposta minha. Fico com a sua alternativa: contabilidade preservada durante uma campanha finita, com capacidade medida e teto físico que para a coleta, sem reescrever a contabilidade. Também aceito: "nenhuma opção completa demonstrou caber em 20 GB" no lugar de "impossível em qualquer formato" (a conta só prova que as assinaturas de 7 d custam 13,44 GB).

Proposta de texto para a DECISÃO CONJUNTA (corrija o que precisar):

1. Direção (e): fita L0 compacta no Postgres, identidade inteira (signature 64 B, program, ordinal), sem btree de consulta, BRIN em slot, partição diária, sem filtro de tamanho/atividade no ingresso. (b) retirada (é outra especificação); (c) rejeitada (< 0,01 SOL apaga saídas de sacos; tx falha não economiza linha); (f) só-curva não testa o H-030; (d) Parquet fica como alternativa a medir, que exige exceção arquitetural do Everton à regra "Postgres + Redis only" e não é recomendada nesta decisão.
2. Contabilidade do desenho preservada durante uma campanha finita: lotes FIFO abertos mantidos inteiros enquanto a campanha durar (piloto + 7 d de aquecimento + até 28 d de coorte); nenhum horizonte H. Lotes fechados não precisam sobreviver fora da janela e das dependências (o episódio guarda o resultado) — isso é retenção de evidência, a confirmar na prova de suficiência. Se o Everton quiser H, ele vem como nova definição contábil completa, antes do congelamento, e não como otimização.
3. Poda por dependência, não por idade: a partição do dia p sai só depois de publicado e verificado tudo o que depende dela (retratos até p+7, apostas, pares, sensibilidades pré-declaradas, kept, estado de continuação: lotes no início de cada janela consultável, reserva válida anterior ao L0, creates, evidência parcial de ligações fracas, pendências). Pico ~7 + (hora de liberação)/24 dias no caso normal (7,17 d com liberação às 04:00 UTC), +1 d por noite atrasada, parada do coletor com lacuna explícita depois de 2 noites atrasadas OU quando o espaço livre verificado cruzar a reserva (o que vier antes). O podador diário é contrato novo (o atual só entende mês).
4. Reexecução idempotente por efeito: resultado versionado por dia/corte/código/parâmetros, checkpoint de estado, publicação atômica e imutável, exclusão mútua job x poda; canonicalização da identidade com memória limitada, recepção original preservada, payload divergente para a mesma identidade tratado explicitamente, reentrega depois de selar o dia nunca vira swap do dia seguinte; evento tardio obedece aos dois relógios de causal_view.
5. Motor: build_snapshot não pode materializar 7 d (~210 M fills). Onda 1c-bis refatora o ACESSO (memória limitada, lotes por mint/entidade, filtros só por condições necessárias provadas, depois da fusão) sem trocar as regras, com prova de equivalência contra o motor atual em amostras: virada de dia, janela móvel, expiração de partição, fusão tardia, duplicata, evento tardio, restart, restauração degradada. Retratos: linhas individuais para toda entidade que passa a atividade depois da fusão e das exclusões (por cenário), com universo candidato de controle 1/2 e mecanismo de sorteio preservados; demais só contagens por motivo no manifesto (declarado: sem explicação individual permanente para elas).
6. Backup: L0 e lotes fora do pg_dump (exclusão conferida nas filhas diárias e restauração de teste); retratos, apostas, links, kept e lacunas dentro. Restauração = lacuna explícita e cobertura contábil marcada como desconhecida, nunca apresentada como completa.
7. Orçamento (cenários, não medidas): L0 a 248 B/linha e 28,5-31 M/dia = 51-55 GB normal, 65-71 GB pior caso; lotes da campanha = não medido (cenário com a fita parcial de 01/10: 2-6,5 M posições abertas novas/dia, lotes >= posições; 45 d x 263 B por lote = 24-77 GB só pelas posições, mais se houver vários lotes por posição; uma representação com ids inteiros pode reduzir, a medir); retratos/apostas/kept/links 1-5 GB (kept e evidência de ranking a medir até veredito + 90 d); transitórios do job a medir (pico simultâneo, não soma). Faixa de planejamento 80-175 GB. Previsão grosseira (±30 %) do pior ponto SEM H-030 e COM os crons: 94-109 G livres no fim de novembro; reserva de 20 GiB da operação não financia o H-030. Pedido ao Everton: aprovar um TETO físico para o H-030 (proposta: 100 GiB) em vez de 10-20 GB, e ampliar o disco em +100 GiB (recomendado; +50 GiB só se o piloto medir a campanha inteira dentro de ~100 GiB). Ao atingir o teto, a coleta para e a coorte segue o protocolo de lacuna/aborto do PREREG.
8. Portão (nada da onda 1b definitiva nem da onda 2 antes): (i) crons de partição e outbox instalados e provados pelo efeito (último sucesso, idade/backlog, partições futuras, skips por dump/lock); (ii) backup de 05/10 explicado (a VPS reiniciou às 14:35Z de 05/10 pelo uptime; não há linha de 05/10 no backup.log); (iii) piloto de pelo menos um ciclo diário no provedor pago com tabela de ensaio isolada (escopo próprio autorizado), medindo bytes físicos/linha (tabela + TOAST), wal_bytes/wal_fpi, lotes e posições criados/consumidos/remanescentes por dia, linhas de retrato, kept por aposta, CPU/RSS/temporários do motor refatorado com a prova de equivalência; (iv) decisão do Everton sobre teto e disco com esses números.

Se concordar, abra com DECISÃO CONJUNTA e a lista final.

## Astra (rodada 3)

DECISÃO CONJUNTA

Convergimos na direção e nos critérios de aceite. A retirada de H resolve a divergência contábil. Esta é a lista final, respondendo aos seus oito pontos; as precisões abaixo tornam explícitas as condições já discutidas, sem declarar capacidade, equivalência ou prontidão operacional demonstradas.

1. **Direção (e), aceita.** L0 compacto no Postgres, assinatura inteira de 64 B, programa e ordinal, partição diária, BRIN em slot como desenho a medir, sem btree de consulta no L0 nem filtro econômico/de atividade no ingresso. A identidade do motor é `(signature, program, event_ordinal)` (`packages/indicators/hunter_indicators/meme/wallets/tape.py:107`). Retiramos (b); rejeitamos cortar swaps pequenos; transações falhas já fora do conjunto de swaps não reduzem suas linhas. Só-curva (f) muda a população de dois programas (`docs/design/seguir-carteiras-lucrativas.md:105`). Parquet (d) permanece alternativa de estudo, dependente de exceção arquitetural do Everton; a direção acordada usa Postgres. A conclusão física é **nenhuma opção completa apresentada demonstrou caber em 20 GB**, não uma impossibilidade universal.

2. **Campanha finita, sem H, aceita.** Preservar lotes abertos, quantidades, custo, origem e ordem durante toda a campanha e enquanto forem necessários ao fechamento e à evidência. Uma compra abre um lote e uma venda consome a cabeça FIFO; pares carteira/mint não substituem essa cardinalidade (`packages/indicators/hunter_indicators/meme/wallets/lots.py:149`; `packages/indicators/hunter_indicators/meme/wallets/lots.py:153`). Fixar antes do congelamento a duração máxima do piloto e a data-limite operacional; 45 dias é cenário que deixa 10 dias além de 7 + 28, não duração já demonstrada. Separar fim do ingresso de fim da retenção. Sobre lotes fechados: **podem ser candidatos à poda depois de satisfeitas todas as dependências e obrigações de evidência**, mas “o episódio guarda o resultado” não prova suficiência para fusão ou fronteira futura. O desenho ainda especifica lotes enquanto abertos + 60 dias, episódios por 60 dias e kept até veredito + 90 dias (`docs/design/seguir-carteiras-lucrativas.md:146`). Reduzir esses prazos requer revisão explícita do contrato; até lá entram no orçamento. H futuro seria outra definição contábil, não otimização equivalente.

3. **Poda por dependência, aceita.** Publicar e verificar retratos, apostas, pares, sensibilidades, kept e estado suficiente de continuação antes de liberar uma partição. Esse estado inclui fronteiras consultáveis, reservas anteriores ao L0, creates/exclusões, ligações fortes e evidência parcial das fracas, inventário e pendências. `p+7` é a primeira liberação possível no cenário descrito, não autorização automática: dependência sem substituto suficiente segura a partição. A necessidade de reserva inicial aparece em `packages/indicators/hunter_indicators/meme/wallets/episodes.py:131`; a evidência acumulada de coincidências, em `packages/indicators/hunter_indicators/meme/wallets/entities.py:74`. O pico normal é aproximadamente `7 + hora UTC de liberação/24` dias, condicionado a essa suficiência; liberação às 04:00 dá 7,1667. Cada dia adicional retido acrescenta um dia de ingresso. Fixar horário-limite e definição de atraso para as duas noites. **Parar antes de invadir a reserva**, com margem para escrita em voo, intervalo entre verificações, WAL e fechamento, ou antes do teto do H-030, ou no limite de atraso, o que ocorrer primeiro. O contrato diário é novo: o podador atual reconhece sufixos mensais e compara a borda superior (`infra/scripts/partition_retention.py:36`; `infra/scripts/partition_retention.py:106`).

4. **Reexecução por efeito, aceita.** Canonicalização com memória limitada, identidade inteira e recepção original preservada; conflito de payload explícito; duplicatas tardias não viram swaps de outro dia. Resultado e checkpoint versionados por dia/corte/código/parâmetros, publicação atômica e imutável, exclusão mútua entre job e poda e prova de recuperação após interrupção. Os dois relógios continuam estritos (`packages/indicators/hunter_indicators/meme/wallets/tape.py:157`). Versionar publicação não autoriza substituir a foto já usada por uma aposta nem retroagir disponibilidade. O `dedupe` atual guarda a recepção mais antiga usando um dicionário do conjunto inteiro; é referência semântica, não solução de escala (`packages/indicators/hunter_indicators/meme/wallets/tape.py:144`).

5. **Onda 1c-bis e retratos, aceitos.** Refatorar acesso/processamento com memória limitada, mantendo regras, ordem causal, precisão e resultados. Hoje `build_snapshot` materializa a visão causal, agrupa eventos por mint e monta as fitas (`packages/indicators/hunter_indicators/meme/wallets/ranking.py:146`; `packages/indicators/hunter_indicators/meme/wallets/ranking.py:156`). Processar por mint/entidade só resolve se também houver limite demonstrado para grupos grandes e estados auxiliares. Filtros apenas por condições necessárias provadas, depois da fusão/exclusões, sem cortar mercado necessário à precificação. Prova diferencial contra o motor atual: virada de dia, janela móvel, fronteira anterior ao L0, partição expirada, fusão tardia, duplicata/conflito, evento tardio, restart e perda de estado. Na restauração degradada, o esperado é **detectar a perda e impedir continuidade falsamente completa**, não reproduzir dados que o dump excluiu. Persistir toda entidade que passa atividade, por cenário, com métricas/razões e universo dos controles; demais com contagem total e contagens por motivo declaradas como exclusivas ou sobrepostas. Control2 mantém suas restrições financeiras/copiabilidade (`packages/indicators/hunter_indicators/meme/wallets/follow.py:53`). Sem explicação individual permanente para as entidades omitidas. Kept inclui execução, evidência de ranking e dependências dos controles/sensibilidades; não encurtar silenciosamente o contrato de `docs/design/seguir-carteiras-lucrativas.md:151`.

6. **Backup degradado, aceito como contrato proposto.** L0 e lotes de continuação fora do dump; dentro ficam retratos, apostas/pares, episódios e evidências exigidos, links/proveniência, kept, manifestos e lacunas. Uma evidência necessária não pode desaparecer só por compartilhar armazenamento com lotes excluídos: precisa estar representada no conjunto preservado. Conferir exclusões em todas as filhas e restaurar em ambiente de ensaio. Restauração marca cobertura contábil desconhecida; sete dias novos, isoladamente, não provam reconstrução dos lotes perdidos. Hoje a exclusão explícita é apenas `opportunity_history`, e a poda dos dumps vem depois da validação/renomeação do novo (`infra/vps/backup_postgres.sh:122`; `infra/vps/backup_postgres.sh:138`). Medir coexistência de dumps antigos, parcial e novo; não fixar previamente “menos de 1 GB por dump”.

7. **Teto físico e ampliação, aceitos como proposta ao Everton, não como capacidade garantida.** A 248 B e 28,5–31 M linhas/dia, o cenário normal de 7,1667 dias dá 50,654–55,097 GB; 65–71 GB continua cenário condicionado ao atraso, não máximo absoluto. Os 24–77 GB de lotes são multiplicações de uma hipótese derivada de fita parcial: 2–6,5 M posições/dia não medem lotes nem crescimento líquido. Os 1–5 GB de derivados e 80–175 GB totais são faixas de planejamento abertas, sem teto demonstrado para kept, links, versões, índices, duplicatas e transitórios. **80–175 GB = 74,506–162,981 GiB; 100 GiB = 107,374 GB.** Portanto, o teto proposto de 100 GiB pode interromper a campanha antes de completá-la. Recomendo levar a proposta de +100 GiB úteis de disco e o teto de 100 GiB ao Everton com essa consequência explícita; +50 GiB só permanece alternativa se a projeção medida, com margem e reserva operacional de 20 GiB separada, couber. A previsão deve atravessar a campanha e a retenção até veredito + 90 dias, incluindo backup, não terminar em novembro. Os 94–109 G e ±30 % são projeções relatadas por você, não medições minhas nem intervalo de confiança. O teto cobre a pegada incremental completa do H-030, com parcelas compartilhadas atribuídas explicitamente e espaço reservado para terminar os trabalhos após parar o ingresso. Vincular parada, lacuna, retomada ou aborto antes de congelar; o PREREG já proíbe consertar um defeito e reaproveitar a mesma coorte após ver desfechos (`.claude/state/carteiras-lucro/PREREG.md:61`).

8. **Portão operacional, aceito.** Onda 1b definitiva e onda 2 permanecem bloqueadas até contrato revisado, crons comprovados pelo efeito, backup de 05/10 esclarecido, piloto físico e decisão do Everton sobre teto/disco com os números. A tabela de ensaio isolada e o instrumento da 1c-bis precedem a migração definitiva, em escopo próprio; o uso pago para o piloto já foi autorizado no registro de aprovação (`obsidian/06-DECISIONS/2026-10-05-seguir-carteiras-lucrativas-aprovado.md:21`). Pelo menos um ciclo diário no provedor final mede cobertura, atraso, reconexão/custo, bytes de tabela/índices/TOAST por evento único e recebido, WAL gerado e residente, lotes criados/consumidos/parciais/remanescentes, posições, retratos e evidência completa por aposta/cenário, CPU/RSS/temporários e duração dos jobs. Um dia calibra taxas; não mede sozinho 45 dias de estoque. Exigir projeção da campanha inteira e ensaio de carga equivalente à janela de sete dias e às concentrações relevantes. Crons precisam demonstrar último sucesso, backlog/idade, partições futuras e skips por lock/dump (`infra/vps/cron/hunter-outbox:13`; `infra/vps/cron/hunter-partitions:13`). **O reinício às 14:35Z não explica, sozinho, um backup esperado antes desse horário**: reconstruir a linha do tempo e comprovar um backup restaurável. Não acessei a VPS nesta rodada.

**RESUMO**

DONE — diálogo convergido; implementação e operação continuam condicionadas às provas acima. Atuo como `database-architect`. A KB-0183 separa extrapolação de medição; a revisão `obsidian/06-DECISIONS/Revisoes-Astra/wallets-engine.md` preserva a errata econômica e as fronteiras; a EXP-M15 registra a linhagem anterior, sem virar resultado de H-030. Nenhuma conclusão de rentabilidade foi produzida.

**ARQUIVOS**

Somente append desta seção em `.claude/state/dialogue-wallet-tape-storage.md`. Nenhum outro arquivo alterado por mim; nenhum commit, migração, poda, contratação ou operação em produção.

**TESTES**

Não executei pytest, migrações, benchmark nem restauração: esta rodada altera apenas o diálogo. Executei contas locais em PowerShell com `[decimal]`, divisão por `1073741824` para GiB e por `1000000000` para GB. Saída real:

```text
planning_80_175_GB_GiB=74.506..162.981
cap_100GiB_GB=107.374
lots_45d_GB=23.670..76.928
L0_7.1667d_GB=50.654..55.097
duration_45d_minus_7_minus_28=10
```

Essas contas verificam aritmética, não capacidade física. A gravação desta rodada verifica que o conteúdo anterior permanece byte a byte e que existe uma única seção `Astra (rodada 3)`.

**MUST-FIX**

Nenhuma divergência contábil restante. Continuam bloqueantes para implementação/operação os critérios da lista: suficiência antes da poda (senão desaparecem fronteiras/fusões); parada antecipada e capacidade total (senão o teto é ultrapassado durante processamento/backup); restauração degradada comprovada (senão inventário perdido parece completo); efeito dos crons e backup explicado (senão a previsão depende de manutenção que não acontece). A decisão conjunta não equivale a declarar esses itens resolvidos.

**NICE-TO-HAVE**

Comparar representação reversível com ids compactos para lotes e fronteiras, medindo o custo dos dicionários/índices junto. Não é condição adicional para encerrar o diálogo.

**O QUE EU FARIA DIFERENTE**

Apresentaria ao Everton duas decisões separadas: quanto disco adicionar e qual risco de interrupção aceitar com o teto do experimento. Mais disco não amplia automaticamente o teto de 100 GiB; aceitar esse teto não prova que a campanha termina dentro dele.

**CONCORDO COM**

Seus oito pontos, na redação consolidada acima. O acordo é preservar a ciência e parar o instrumento quando necessário, sem apagar custo para continuar ranqueando. A aprovação anterior de 10–20 GB está registrada em `obsidian/06-DECISIONS/2026-10-05-seguir-carteiras-lucrativas-aprovado.md:16`; esta rodada prepara a decisão ampliada, não a toma pelo Everton.

**OBSIDIAN**

Páginas a atualizar pelo orquestrador; nenhuma alterada nesta tarefa:

- **Diálogos / wallet-tape-storage (nova página):** registrar a decisão conjunta da rodada 3 e separar convergência de desenho de liberação operacional.
- **KB-0183 — O que custa coletar o programa inteiro da pump.fun e da PumpSwap:** acrescentar os cenários sem H, unidades GB/GiB e medições ainda pendentes.
- **Revisão da Astra: motor puro de seguir carteiras (wallets-engine):** registrar a onda 1c-bis e os casos exigidos para equivalência e perda de estado.
- **EXP-M15 — seguir carteiras vencedoras:** acrescentar o portão do instrumento H-030, preservando a linhagem e sem resultado de estratégia.
- **Seguir carteiras que ganham de verdade — projeto aprovado:** registrar a proposta de teto/disco e a decisão posterior do Everton quando ocorrer.
- **Decisão — retenção de dados e backup para o disco da VPS:** registrar poda por dependência, reserva, restauração degradada e provas operacionais pendentes.

---
tags: [revisao-astra, meme, carteiras, h-030, motor-puro, desempenho, cpu, paralelo, equivalencia]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: quant-engineer
decided_on: 2026-10-06
by: astra
tarefa: passo 3 do plano de CPU do motor de carteiras 1c-bis — redução exata dos acumuladores e workers em processos (mints inteiros), mais a densidade por mint
veredito: desenho com 2 must-fix (transporte de ContractViolation; fonte imutável como contrato), absorvidos antes do código; diff REQUEST_CHANGES com 3 must-fix reproduzidos por ela (interrupção no shutdown deixava um filho vivo; janela móvel de 60 min da sonda de densidade só alinhada ao minuto; f e k misturavam parede e CPU); na rodada 2 o 3 fechou e o 1 e o 2 voltaram com cenário novo (estado do join no CPython 3.12; duração com a drenagem), consertados com teste em executor real; rodada 3 APPROVE; revisão de código REQUEST_CHANGES (Ctrl+C dentro do terminate; concorrência não provada; arquivo de teste com 355 linhas), fechada; nenhuma divergência contábil entre serial e paralelo
---

# Revisão da Astra: CPU do motor de carteiras, passo 3 (H-030)

Plano acordado em [[wallets-cpu]] (decisão conjunta da rodada 2: perfil → trabalho repetido → **fusão exata e 2 workers** → vetorização seletiva). Passo anterior: [[wallets-cpu-step2]]. Motor: [[wallets-1c-bis]]. Brutos: `.claude/state/astra-review-wallets-cpu-step3-design.md` (desenho) e `.claude/state/astra-review-wallets-cpu-step3.md` (diff). Medições e prova em [[wallets-cpu]], seção "Passo 3".

## Rodada 0 (desenho): 2 must-fix, absorvidos antes do código

| # | Achado (cenário dela) | O que entrou |
|---|---|---|
| 1 | `ContractViolation(reason, detail)` não se reconstrói pelo pickle padrão: uma recusa nomeada dentro de um worker viraria falha de transporte | `__reduce__` com o nome e o detalhe. Teste do roundtrip, e um teste com a recusa atravessando `spawn` (tipo, nome e mensagem) e sem filho vivo |
| 2 | Nome e contagem não provam que o `fetch` devolveu a mesma janela: uma compra corrigida, com outros átomos, passa pela checagem | Contrato explícito em `carry.py`: a fonte é imutável durante a execução, nas três passadas e em todo `fetch`. `fetch_mismatch` fica como checagem de sanidade, não como prova |

Também entraram:

- o custo do carry na fila (lotes, fronteira e flows), porque um mint sem eventos novos não custa zero;
- 50 permutações reproduzíveis, uma delas inversa à fonte, comparando campo a campo e as posses como multiconjunto em `float.hex`;
- testes de falha no `emit`;
- `sealed_until` enviado no inicializador, sem replicar o carry global e os pares pendentes;
- a medição de memória do processo inteiro de cada worker.

Ela respondeu às perguntas de desenho:

- (a) nenhum campo depende de ordem;
- (b) a mediana do array concatenado é bit a bit igual para os holds deste motor;
- (c) o LRU, os índices preguiçosos e o contexto Decimal não mudam a saída;
- (d) vale medir o `Night` inteiro. Se um dia ele for projetado por mint, cada entidade envolvida precisa ir com **todos** os membros, senão some uma exclusão de criador legítima.

## Rodada 1 (diff): REQUEST_CHANGES com 3 must-fix, todos reproduzidos por ela

Ela rodou o arquivo de testes (21 passed). Fez sondas extras em memória:

- falha no inicializador dá `BrokenProcessPool`, sem filhos;
- `KeyboardInterrupt` no `emit` propaga, sem filhos;
- fonte vazia e mint repetido, sem filhos.

**Não encontrou divergência contábil entre serial e paralelo.**

| # | Achado (cenário dela) | Conserto, com teste que falhou antes |
|---|---|---|
| 1 HIGH | O `try` ficava **dentro** do `with`. Um `KeyboardInterrupt` durante o `join` do encerramento normal escapava com **um filho vivo** (falha injetada no `join`) | Primeiro conserto (`close_pool` repetia o `shutdown` interrompido) **não bastou**: ver a rodada 2. O conserto final está lá |
| 2 MEDIUM | A sonda de densidade só olhava janelas de 60 min **alinhadas ao minuto**: 500 eventos em 59,9 s e 500 em 3 600,1 s cabem em 3 540,2 s, mas davam 0 chaves. Uma corrida vazia de 60 min dizia "curta". A duração vinha arredondada (3 599,6 s → 3 600 s) | Guarda o instante de cada evento por chave (8 bytes cada) e conta a hora mais cheia com dois ponteiros sobre os instantes ordenados, janela de 3 600 s semiaberta. A duração vem sem arredondar, limitada ao `--seconds` pedido, e o portão é a duração. Os três cenários dela, rodados sem rede, agora dão 1 chave, 0 e "curta" |
| 3 MEDIUM | `plan_s`/`finish_s` eram **parede** (`perf_counter`) e o total do serial era CPU: f e k misturavam unidades. O "T2 ≥" não era limite (um worker pode rodar enquanto o outro inicia). Os "0,4–2,1 h" são um **cenário composto** (frações daqui × tempos do passo 2) | O bench mede plano e fecho em parede **e** em CPU da thread (`thread_time`) nos dois modos. Assim a CPU de replay do serial sai isolada (total − plano − fecho), e f e k ficam CPU/CPU. "T2 ≥" virou "estimativa idealizada". O registro separa o cenário composto das extrapolações lineares dela, que dão outras faixas (abaixo) |

Extrapolação linear dela, a partir das linhas `best` da run 2, para 217 M fills. Não é previsão de produção: só mostra que as parcelas são diferentes.

- parede de plano + fecho: 1,63–2,58 h;
- CPU total do coordenador: 3,56–6,35 h.

**Nice-to-have que entraram:**

- teto de 256 mints por pacote: na sonda dela, 10 mil mints de custo zero viravam um pacote só, e carries só com `create` custam zero sem ser vazios;
- futures consumidos saem do conjunto (`pop`) antes do `yield`;
- fonte vazia não constrói pool;
- compras da PumpSwap chaveadas pela pool **inferida** são contadas à parte (`inferred_keyed_swap_events`).

**Concordou com:**

- a equivalência: o teto global é aplicado antes da distribuição, e o `replace` só troca apostas e sementes do mint;
- a redução: somas, uniões, máximo com ausência, holds completos, e as três chaves unidas separadamente;
- os casos-limite: mint só com carry, mint repetido, carries na ordem da fonte;
- a chave da densidade: mint da curva ou pool, sem junção;
- o diagnóstico de que dois workers vencem um worker, mas perdem para o serial nessas noites pequenas. Na janela vazia com carry grande, perdem até para um worker (0,75×).

## Rodada 2: must-fix 3 fechado, 1 e 2 reabertos com cenário; consertados

Bruto: `.claude/state/astra-review-wallets-cpu-step3-r2.md`. Ela rodou o arquivo de testes (24 passed) e recalculou as linhas `ROW` da run 3. Os números conferem:

- modelo: 0,571–0,841 Ts;
- vazão: 0,608–0,845 Ts;
- cenário composto: 0,3–2,2 h;
- envelope linear: 1,3–3,3 h;
- a tabela da run 3 e a varredura do mint quente batem com os arquivos.

| # | Achado (cenário dela) | Conserto |
|---|---|---|
| 1 HIGH | Repetir o `shutdown` não basta. No CPython 3.12, uma interrupção dentro da aquisição do lock do `Thread.join` pode marcar a thread de gerenciamento como encerrada enquanto ela roda. O segundo `join` volta na hora, o executor fecha recursos que ela ainda usa (`WinError 6`) e o `close_pool` relançou em 0,002 s **com um filho vivo** (falha injetada) | Os processos do pool são lidos **antes** do encerramento (`ProcessPoolExecutor._processes`: privado, mas estável desde o 3.8; lido com `getattr`). Se o encerramento normal for interrompido, eles são terminados e esperados aqui, e só então a interrupção é relançada. Em qualquer falha da noite (`abort_pool`) os workers são terminados de imediato, sem esperar um mint quente que poderia levar minutos. Teste com executor **real**: tarefa de 30 s em curso, primeiro `join` interrompido e os seguintes devolvendo na hora. O teste falhou antes (sobrou o `SpawnProcess-1`) e passa agora: nenhum filho, menos de 20 s |
| 2 MEDIUM | A duração da sonda de densidade era lida depois da drenagem das filas, que pode levar até 60 s após uma interrupção. Recepção cortada em 3 599,6 s e drenagem até 3 601 s publicavam 3 600 s e liberavam a métrica | A duração vai até o carimbo de recepção do último frame (`ProbeStats.last_t`, o instante do socket), limitada ao `--seconds`. O cenário dela, rodado sem rede: "run of 3599.6 s, shorter than 3 600 s" |

Correções de registro que ela pediu, aplicadas em [[wallets-cpu]]:

- as faixas das runs 1–2 valem para as configs com eventos; com a janela vazia, 0,75–1,52× e 0,35–1,00×;
- o startup vai de 1,2 a 3,2 s;
- as parcelas de transporte e de importação ganharam fonte reproduzível: `infra/scripts/research/2026-10-06-wallets-transport-cost.py`, com saída em `transport-2026-10-06-step3.txt`. Os números da nota passaram a ser os dessa saída, e não mais os do meu rascunho fora do repositório.

## Rodada 3: APPROVE

Bruto: `.claude/state/astra-review-wallets-cpu-step3-r3.md`. Os dois must-fix da rodada 2 estão fechados. Ela rodou os testes de interrupção do `join`, de falha do worker e de janela adulterada (4 passed) e sondou:

- captura interrompida em 3 599,6 s: recusada;
- `last_t` vazio: 0 s;
- recepção além do pedido: limitada a 3 600 s;
- `join` de processo interrompido: retomado, e a interrupção relançada.

Concordou que `terminate` serve ao replay atual: os resultados são descartáveis e o `emit` roda no coordenador. Também concordou que `_processes` é dependência privada, sem falha demonstrada no Python 3.12 suportado.

Dois *nice-to-have*, aplicados:

- Um reconectar apaga `ProbeStats.last_t`. Com reconexão depois de uma hora e nenhum log novo, a duração voltava a 0: conservador, mas perdia uma estatística válida. Agora a sonda guarda o maior carimbo de recepção, que nunca é apagado (`DensityStats.last_received`). Cenário rodado sem rede: 3 599,6 s mesmo depois do reconectar.
- A importação do motor foi medida em parede, não em CPU. O registro em [[wallets-cpu]] diz isso agora.

## Revisão de código (code-reviewer + Astra, 06/10): REQUEST_CHANGES, fechado

Bruto: `.claude/state/astra-review-review-wallets-cpu-step3.md`. Os dois concordam que a equivalência contábil se mantém para entradas válidas. Uma sonda carregou o `stream.py` do `HEAD`: 23 noites iguais nos cinco mundos. Nenhum campo de `EntityTally` ficou de fora, e o alias dos livros consumidos não é reutilizado.

| # | Achado (cenário reproduzido) | Severidade | Conserto, com teste que falhou antes |
|---|---|---|---|
| 1 | Um segundo Ctrl+C **dentro do laço de `terminate`** do `abort_pool` escapava: dois workers ficavam vivos e o `shutdown` do executor era pulado (pool real de 2 workers) | revisor MEDIUM, Astra HIGH | O término e a espera passam pelo mesmo padrão de interrupção adiada. O worker interrompido é tentado de novo, até 3 vezes, para um erro persistente não virar laço; o `join` tem teto de 30 s; o `shutdown(wait=False, cancel_futures=True)` roda sempre num `finally`. Teste com pool real: a primeira chamada de `terminate` de um worker é interrompida. Falhou antes (dois filhos vivos) e passa agora: nenhum filho, menos de 20 s |
| 2 | Os testes **não provavam mais de um worker ao mesmo tempo nem conclusão invertida**: o mundo denso tem 3 mints, um único PID rodou os três nas 4 sementes, e o atraso de 30 ms some diante dos segundos de spawn | MEDIUM (os dois) | Teste novo com 2 workers. A carga espera numa barreira de arquivo, com prazo, até haver dois PIDs distintos, e o mint escalado primeiro fica preso até o coordenador emitir o carry de outro. Ele exige 2 PIDs, a conclusão invertida e igualdade com o serial. O registro em [[wallets-cpu]] foi corrigido. Este teste passa no código atual (a propriedade já valia), então ele **cobre** a regressão em vez de ter falhado antes |
| 3 | O arquivo de testes tinha 355 linhas, e o portão exclui testes | LOW | Dividido: `test_wallets_stream_parallel_units.py` (operadores, pacotes, fila limitada, recusa nomeada, limpeza) e o arquivo de ponta a ponta, os dois abaixo de 350 |
| — | `_processes` ausente cairia num fallback silencioso | nice-to-have | `_workers_of` recusa com `TypeError` um executor sem `_processes`. Teste com `ThreadPoolExecutor` |

**Severidade divergente:** só no item 1. Foi fechado de qualquer forma, porque o efeito (workers vivos depois de uma recusa ou de um Ctrl+C) não depende da classificação.

**Requisitos e limites que ficam registrados, sem conserto aqui:**

- **Supervisão contra morte dura do coordenador.** Se o coordenador for morto à força, os workers continuam rodando: a sonda do revisor viu um worker vivo 1,5 s depois. O worker do `ProcessPoolExecutor` não vigia o pai durante a tarefa, e o coordenador morto não executa limpeza nenhuma. Não é falha do `abort_pool`; é **requisito da integração operacional**: um supervisor da árvore de processos (job object no Windows, cgroup ou systemd no Linux) ou um vigia do pai dentro do worker.
- **Falha de pickle no spawn.** No Windows o CPython cria o processo antes de serializar os argumentos, e ele ainda não está em `_processes`. O filho fica vivo por instantes e sai com `EOFError` em menos de 5 s; não é órfão persistente. Por isso `active_children() == []` sozinho não prova a ausência de filhos nessa fronteira.
- **Ausência contra 0 no maior episódio.** A diferença entre "nenhum episódio" (`None`) e 0 só tem prova sintética, no teste de operadores. Nenhuma fixture de mundo produz uma entidade só negativa num mint e sem episódio contado em outro.
- **Identidade repetida entre mints.** Com a mesma identidade fabricada em A e em B e teto 1, o código antigo refazia as duas apostas e o novo só a de A. É evento conflitante, fora da definição de `Fill`. Entrou no contrato de `carry.py` como garantia externa: uma identidade pertence a um único mint.

## Depois da revisão de código: Astra sobre os consertos e a densidade real (06/10)

Bruto: `.claude/state/astra-review-wallets-cpu-step3-density.md`. Ela aceitou a prova de concorrência: barreira de dois PIDs mais mint retido, sem caminho para passar sem as duas condições. Recalculou de forma independente os números da densidade, e todos conferem: Σn²/Σn = 17 062,3, contagens 235/58, maior chave 124 069, M 5,673–6,730×, 96,6–114,6 h, 40,9–107,7 h, caminho crítico 38,2–55,7 h.

| # | Achado (cenário dela) | Conserto, com teste que falhou antes |
|---|---|---|
| 1 HIGH | A limpeza ainda podia voltar com workers vivos. Uma interrupção injetada fora do `try` de cada chamada fez o `abort_pool` escapar com dois vivos. E três interrupções antes do `terminate`, mais um `join(30)` vencido, deixaram um vivo depois de 30 s | A interrupção é segurada **pela raiz**: durante a limpeza, o SIGINT é registrado e não levantado, e só é relançado quando todos os workers saíram (só na thread principal, a única onde o Python o entrega). Depois do `terminate`, cada worker tem 5 s de graça; o que sobrevive leva `kill` e espera de até 30 s, e se ainda houver vivo a limpeza recusa com `RuntimeError` e os PIDs. Testes com pool real: (a) um SIGINT de verdade (`signal.raise_signal`) disparado dentro do `terminate`. No código anterior ele escapou e **abortou a própria execução do pytest**; agora o worker é terminado uma vez só, os dois saem e o Ctrl+C vem no fim. (b) Um `terminate` que não faz nada: o sobrevivente é morto em menos de 20 s, onde antes ficava vivo depois do `join(30)` |
| 2 MEDIUM | O registro misturava bases: 23–96 h era o envelope de duas projeções (direta × workers, 55–96 h; razão × workers, 23–90 h); a distância da meta era ≈ 12–48×, não 25–50×; as 5 chaves além de 16 000/h pesam 50–58 % do custo, não 40–50 %; os 39,5 % são dos swaps com chave, não das chaves | Corrigido em [[wallets-cpu]] e em [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools\|KB-0187]], com as bases separadas |
| 3 MEDIUM | A densidade ponderada por evento não é a de uma cópia típica. Uma pool de 124 mil swaps de poucos robôs, ou abaixo do piso de 0,1 SOL, pode dar zero apostas, e então o cenário **superestima** | A identificação com a cópia típica saiu das notas e do leitor, assim como o "tende para baixo". O cenário agora pode errar para os dois lados; medir apostas elegíveis por chave fica como próximo passo |

Nice-to-have aplicado: 34 mints da curva passam de 1 000/h e 1 passa de 4 000/h. Só as 5 acima de 16 000/h são todas pools.

**Rodada seguinte: APPROVE** (bruto `.claude/state/astra-review-wallets-cpu-step3-density-r2.md`). Ela rodou os testes de limpeza (10 passed) e confirmou os três consertos. Retirou o critério de resistir a exceções injetadas por *tracing* em qualquer linha, que não é aceite razoável: a ameaça real é o SIGINT, e esse fica segurado. O *nice-to-have* da docstring, que prometia processos sempre encerrados e agora admite o `RuntimeError` que nomeia os sobreviventes, foi aplicado.

## Divergências

Nenhuma de mérito. Uma de leitura: o mutante "livro criado a partir das cópias" é equivalente em entradas válidas, porque uma cópia exige aposta, e a aposta é compra da entidade no mint, o que gera livro na mesma parte. Mesmo assim, o teste de operadores fixa o contrato "cópias não criam linha".

## Relacionado

[[wallets-cpu]] · [[wallets-cpu-step2]] · [[wallets-1c-bis]] · [[wallets-engine]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[EXP-M15-carteiras-vencedoras]] · [[Revisoes-Astra/Index|índice]]

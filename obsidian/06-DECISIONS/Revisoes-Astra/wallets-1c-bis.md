---
tags: [revisao-astra, meme, carteiras, h-030, motor-puro, escala, memoria, equivalencia, onda-1c-bis]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: quant-engineer
decided_on: 2026-10-06
by: astra
tarefa: onda 1c-bis do H-030 — o motor puro de carteiras em memória limitada, com prova diferencial contra o motor atual
veredito: desenho com 5 must-fix (todos absorvidos antes do código); diff com 2 must-fix reproduzidos por ela (domínio do horizonte e carries residentes), fechados com teste que falhou antes
---

# Revisão da Astra: motor de carteiras em memória limitada (onda 1c-bis, H-030)

A onda 1c-bis nasceu do achado do §9.4 do desenho (`docs/design/seguir-carteiras-lucrativas.md`): o `build_snapshot` carrega todas as fills da janela (~210 M em 7 dias). O diálogo [[wallet-tape-storage]] pediu um motor que refatorasse o **acesso** sem trocar regra, com prova diferencial. Motor anterior: [[wallets-engine]] e [[wallets-1c-pricing]]. Brutos: `.claude/state/astra-review-wallets-1c-bis-design.md` (desenho) e `.claude/state/astra-review-wallets-1c-bis.md` (diff).

## O que as notas mudaram no plano

| Nota | O que mudou |
|---|---|
| [[wallet-tape-storage]] e §9.6 do desenho | A lista de dependências da poda guiou o estado carregado (fronteira válida, creates, evidência fraca, inventário). Faltava uma: os totais do líder, item 3 abaixo |
| [[wallets-engine]] | A posse é a mediana das peças e o `leader_sold` é contado em ordem de chegada. As duas regras ficaram intocadas: o motor novo prova igualdade com o oráculo |
| [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] | Dele vem o volume (28,5–31 M swaps/dia) usado na extrapolação. Dele vem também a forma do gerador do benchmark (a maioria das carteiras faz um swap) |
| [[KB-0149-o-que-a-mesa-real-ensinou]] §5 item 24 | Um look-ahead "mente com convicção". Por isso o motor recebe o futuro e o ignora, e os testes provam isso |

## O que foi construído

- **"Processar só o dia novo" não é exato.** A Astra concordou com isso. O retrato de D aplica o mapa de entidades de D à janela inteira e parte dos lotes **por carteira** no início da janela. O ledger de gatilhos também recomeça a cada janela. Exemplo: a gêmea A compra 100 e a gêmea B vende 100 no dia S. Na janela que começa em S a entidade fica zerada; na que começa em S+1 há 100 abertos.
- **A forma exata é refazer a janela a cada noite, um mint de cada vez** (`stream.py`, `stream_mint.py`), em três passadas: entidades, apostas e replay.
- **O estado carregado fica no início da janela** (`carry.py`) e independe da janela. Ele avança um dia por noite, com **dois relógios** (must-fix 1 dela):
  - por mineração: lotes FIFO por carteira e evidência de ligação fraca;
  - por chegada: fronteira, totais comprado/vendido por carteira, maior slot e create.
- **Codec JSON** (`carry_codec.py`): a prova de reinício roda com o carry serializado e restaurado. O armazenamento ficou fora do escopo.
- **O contrato tem duas partes.** Na primeira, o motor confere localmente e recusa por nome (`ContractViolation`), sem contornar:
  - P1: um evento minerado antes de S chega antes do selo;
  - P2: `received_at ≥ block_time`;
  - P3: um `block_time` por slot, nunca decrescente com o slot;
  - o carry tem de ser da janela certa;
  - nenhum lote preservado pode ser posterior à origem;
  - `settle_seconds` não pode passar do início da janela (must-fix do diff);
  - a janela só traz eventos recebidos a partir de S, e cada mint aparece uma vez por passada (revisão de código, abaixo).

  Na segunda estão as **garantias da fonte (armazenamento)**, que não se conferem olhando um mint por vez; a quebra delas é **silenciosa**:
  - cada identidade é entregue uma vez entre noites (§9.6.4);
  - a fonte é completa, incluindo os mints só com carry (um mint omitido perde lotes, fronteira e totais);
  - `shared_signatures` está completo;
  - o carry recebido é o que a noite anterior produziu.

  Os empates de lotes de abertura seguem uma **convenção** determinística, `(slot, opened_at, carteira, ordem do livro)`, e não a ordem econômica, que o feed não informa.

## Prova

- **Diferencial noite a noite contra o `build_snapshot` intocado.** O retrato inteiro é igual: linhas, métricas, manifesto e versão das entidades. Os cenários:
  - 24 mundos aleatórios de 6 dias com janela de 2 dias, metade com roundtrip JSON do carry;
  - 3 mundos de 10 dias com janela de 7;
  - as fixtures do ranking e do vazamento;
  - as **fixtures reais `t1a_*`**: 10 fills (9 de pool com WSOL na quote e 1 de curva v1), todas tardias pela meia-noite. A última noite só as vê pelo carry.
- **O gerador prova que exercita cada caminho difícil.** Um censo exige ocorrências de cada um:
  - chegada tardia pela meia-noite;
  - duplicata;
  - tx que toca dois mints;
  - migração e fill de pool;
  - fusão no meio da campanha;
  - compra no mesmo slot;
  - cópias, episódios incompletos e contaminados, venda sem par.
- **O acumulador por entidade (`stream_metrics.py`) tem oráculo independente.** A `entity_metrics` do batch ficou intocada (must-fix 5 dela).
- **Mutação: 18 de 18 mutantes mortos**, rodados à mão (script em `scratchpad/`, fora do repositório). Os pontos quebrados:
  - totais do líder e `since`;
  - fronteira fora da fita;
  - sementes da taxa por entidade e por carteira;
  - abertura sem entidade;
  - selo e fronteira/flows pelo relógio errado;
  - create carregado, evidência pendente, links carregados;
  - teto diário e piso do horizonte;
  - dedupe e "todo comprador é candidato";
  - mediana sem neutros e maior episódio.

  Os dois sobreviventes da primeira rodada (teto e horizonte) eram pontos cegos das fixtures. Viraram testes.
- **Comandos:** `uv run pytest packages/indicators/tests/meme` deu **200 passed**; `uv run pytest packages/indicators` deu **1 651 passed**. Pyright strict, ruff e o portão de 350 linhas estão limpos.

## Rodada 0 (desenho): 5 must-fix, todos absorvidos

1. Separar o avanço econômico do avanço por chegada. **Falha:** uma compra com bloco em S−1h, recebida em S+1h, seria perdida ou duplicada.
2. P3 vale por slot. **Falha:** dois `block_time` num mesmo slot cortariam o FIFO na virada do dia.
3. A taxa de tx vai ao **vencedor por (dono, assinatura)**, separado para entidade (janela) e para carteira (selo). Só o conjunto de assinaturas multimint não basta.
4. A mediana tem de ser exata. Todas as posses ficam num `array('d')`, e isso é **orçamento explícito, não limite**.
5. O oráculo tem de ser independente: a `entity_metrics` não é compartilhada.

Ela também confirmou que o `_leader_exit` somando a **história inteira** do líder no mint é intencional, porque um teste existente exige isso. Recomendou esclarecer no texto: "desde o início da história observada da campanha".

## Revisão do diff: 2 must-fix reproduzidos por ela, fechados com teste

| # | Cenário dela | Conserto |
|---|---|---|
| 1 | Com `settle_seconds = 259 200` e janela de 2 d, o horizonte carregado dava 100 contra −1 do batch. O padrão de 2 s não é afetado | Recusa `settle_beyond_window` |
| 2 | Com 10 ou 100 mints históricos e a janela vazia, os 10 ou 100 carries ficavam todos residentes na saída | `stream_snapshot(emit=...)` despeja cada carry assim que o mint é refeito |

Ela também concordou com estes pontos:

- (a) Um link fraco carregado preserva as entidades, mas não promete o mesmo `known_at` de proveniência do batch. O retrato só depende dos grupos.
- (b) `_bets` equivale ao `_c_pnl`.
- (c) P1 é suficiente por indução, com corte estrito.
- (d) Duplicata entre noites é contrato do armazenamento.

**Nice-to-have aplicado:** a mediana deixou de copiar o array numa lista. **Não aplicados (próximos passos):** RSS em processo isolado com a fonte iterada de verdade, uma campanha longa com janela de 7 d variando cada estrutura separadamente, e rajadas de compradores no mesmo slot no gerador do benchmark.

## Benchmark (sintético, não é dado de mercado)

Script: `infra/scripts/research/2026-10-05-wallets-engine-bench.py`. Saída: `.claude/state/carteiras-lucro/bench/run-2026-10-05.txt`. Configuração: janela de 2 d, 4 dias e três escalas. Nas três, **os dois retratos são iguais**.

| fills/dia | fills na janela | maior mint | entidades | bounded s | batch s | heap bounded MB | heap batch MB | carry: lotes / flows / pares pendentes / JSON MB |
|---|---|---|---|---|---|---|---|---|
| 4 000 | 4 852 | 767 | 3 808 | 1,2 | 1,5 | 6,4 | 10,2 | 3 688 / 3 617 / 580 / 0,5 |
| 8 000 | 20 641 | 2 000 | 15 671 | 14,5 | 13,7 | 25,9 | 40,7 | 12 482 / 12 373 / 2 050 / 1,6 |
| 16 000 | 30 074 | 4 000 | 28 927 | 17,0 | 18,0 | 48,1 | 83,0 | 29 703 / 29 347 / 5 143 / 3,8 |

Cada `Fill` ocupa ≈ 394 B residentes. O heap é o pico de alocação Python durante a chamada (`tracemalloc`), com a fonte excluída.

**Extrapolação linear, sobre cenário e não medida:**

- **Memória.** Com 200–217 M fills na janela de 7 d, o batch precisaria de ≈ 629–684 GB (objetos `Fill` mais o motor). O motor limitado fica em um mint, mais as entidades, mais o carry. Com 1, 5 ou 20 M entidades na janela, a cota é de ≈ 1,7, 8,3 ou 33 GB. O gerador exagera as carteiras de um swap só (54 % dos eventos, contra 13 % medidos no KB-0183), então esse número mistura estruturas, como ela apontou.
- **CPU: não resolvida.** O replay de 7 d por noite custa o mesmo que o batch: ≈ 31–34 h por noite num núcleo. A passada 3 é pura por mint, então dá para paralelizar entre mints, mas a fusão dos acumuladores ainda não existe.

## Achados que vão ao dono

1. **Dependência ausente do §9.6 item 3 e do orçamento.** O `_leader_exit` lê a história inteira do líder no mint. Isso obriga a guardar uma linha de totais por (carteira, mint) **já negociado na campanha**, inclusive as posições fechadas. É mais que os lotes abertos: no benchmark, as flows igualam os lotes em contagem.
2. **Pares de ligação fraca com 1–2 mints nunca podem ser podados.** O número cresce com a campanha (5 143 pares a 16 k fills/dia; em rajadas é quadrático).
3. **O retrato devolve uma linha por entidade.** O §9.6 item 5 já prevê persistir só as que passam a atividade.
4. **A CPU continua sendo o gargalo da janela real**, item acima.

## Divergências

Nenhuma de mérito. Fica registrado o domínio da equivalência: ela vale **sob o contrato**, e o contrato inclui garantias externas que o motor não confere (seção acima). Não vale para qualquer entrada que o `build_snapshot` aceite. A severidade divergiu na rodada seguinte, abaixo.

## Relacionado

[[wallets-engine]] · [[wallets-1c-pricing]] · [[wallet-tape-storage]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[EXP-M15-carteiras-vencedoras]] · [[Revisoes-Astra/Index|índice]]

## Revisão de código (code-reviewer + Astra, 06/10): REQUEST_CHANGES só na validação da entrada, fechado

Dentro do contrato completo o motor é exato. O `code-reviewer` matou 8 mutantes por *monkeypatch* e rodou 120 sementes novas, sem nenhuma divergência. A Astra comparou os módulos com o `HEAD`: os padrões dos ganchos preservam o motor original (3 noites iguais), e o codec é exato com inteiros acima de 2⁵³, `V` negativa, microssegundos e `null`.

Os achados são **entradas fora do contrato que passavam em silêncio**. O harness dos diferenciais normalizava cada uma (filtrava as chegadas, montava mints únicos e calculava as assinaturas compartilhadas), por isso os testes negativos novos chamam `StreamInputs` direto. Bruto: `.claude/state/astra-review-review-wallets-1c-bis.md`.

| # | Achado (cenário reproduzido) | Severidade | Conserto, com teste que falhou antes |
|---|---|---|---|
| 1 | Uma fill da janela recebida **antes** do início entrava na fita e era somada de novo aos totais do líder, que já estavam no carry. Com os fills do dia 0 devolvidos na noite seguinte, o C-PnL foi de 0 para −154 963 lamports e saiu uma cópia a mais | HIGH (os dois) | Recusa `received_before_window` em `_prepared` |
| 2 | Um mint repetido na fonte era refeito duas vezes: 3 fills viraram 6 e o W-PnL dobrou | Astra HIGH, revisor MEDIUM | Recusa `repeated_mint`: cada passada guarda um conjunto de nomes, O(mints) |
| 3 | `shared_signatures` tinha padrão vazio e o motor confiava nele. Uma assinatura omitida cobra a taxa duas vezes: 5 000 lamports a menos no W-PnL | MEDIUM | O campo passou a ser **obrigatório**, sem padrão. A completude é documentada como garantia do armazenamento. Um teste negativo documenta a divergência quando falta |
| 4 | A frase "recusado por nome, nunca contornado" prometia demais | LOW | O texto de `carry.py` e desta nota separa as condições conferidas localmente das garantias externas |
| — | Comentário de `stream_metrics.py:110` impreciso | nit | Reescrito |

**Reconciliação com a Astra.**

- **Severidade do mint repetido:** ela marcou HIGH e o revisor MEDIUM. Foi fechado de qualquer forma, porque o efeito (resultado dobrado sem sinal) não depende da severidade atribuída.
- **"Fill antiga é indetectável":** a primeira leitura era que só o armazenamento poderia pegar uma fill antiga reentregue. Isso foi resolvido pela checagem de uma linha. Toda fill da janela tem de ter `received_at ≥ S`, e o motor confere isso localmente. O que continua externo é a duplicata **da mesma identidade** dentro da janela vinda de outra noite, que segue no contrato do armazenamento.
- **Mint omitido:** é *nice-to-have* dela, não fechado aqui. A interface não traz o inventário esperado de mints, então a omissão não se vê de dentro. Fica como garantia externa, ao lado do manifesto de completude que ela sugere para a integração com o armazenamento.

**Verificação depois do conserto.** `uv run pytest packages/indicators/tests/meme` deu 204 passed e `uv run pytest packages/indicators` deu 1 655 passed. Pyright strict, ruff, o portão de 350 linhas e o lint da base estão limpos. A mutação deu **20 de 20 mutantes mortos**: os 18 anteriores e as duas guardas novas.

## CPU, passos 1–2 (06/10/2026, acréscimo do quant-engineer)

O plano de [[wallets-cpu]] foi executado nos passos 1 (perfil) e 2 (tirar trabalho repetido). O motor desta nota **não mudou de regra**: sete remoções, uma por vez, cada uma com teste que falhou antes. A prova tem três partes:

- os diferenciais desta nota, intocados e verdes;
- uma referência congelada **deste** código (`packages/indicators/tests/meme/wallets_golden.json`, digests do commit `84704fa1`), para que uma mudança num helper compartilhado com o `build_snapshot` não engane os dois lados;
- 11 de 11 mutantes mortos.

O que mudou de leitura:

- **A CPU não estava no acesso por mint.** Estava no stop de cada cópia: uma cotação Decimal da venda em cada estado observado depois da entrada. Ela cresce mais que linearmente num mint denso.
- **A conta de 31–34 h desta nota usava o gerador antigo** (54 % dos eventos por carteiras de um swap só). O gerador novo segue o KB-0183 e muda a mistura.

Números, extrapolação e o que sobra para o passo 3 estão em [[wallets-cpu]]; a revisão da Astra está em [[wallets-cpu-step2]].

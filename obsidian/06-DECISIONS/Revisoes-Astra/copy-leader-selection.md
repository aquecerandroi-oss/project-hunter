---
tags: [revisao-astra, meme, carteiras, copia, piloto, h-037, pumpfun, selecao]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-09
by: astra
tarefa: regra de seleção dos líderes do piloto de copiar carteiras no papel (infra/scripts/copy_select_leaders.py, tarefa B) e a revisão do código que a aplica
veredito: REQUEST_CHANGES na regra (rodada 1) e no código (rodada 2); sem novo bloqueador de código na rodada 3, com uma pendência de documentação fora desta tarefa — tudo absorvido ou registrado abaixo
---

# Revisão da Astra: regra de seleção dos líderes do piloto (09/10/2026)

Tarefa: a ferramenta `infra/scripts/copy_select_leaders.py` (+ `copy_leaders_rule.py`, `copy_leaders_http.py`, `copy_leaders_doc.py`) escolhe, a partir do que a pump.fun publica, os cerca de 20 líderes do piloto da [[2026-10-09-piloto-copiar-carteiras-no-papel|decisão do Everton de 09/10]] e congela a lista em JSON. Lido antes: [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]] (o quadro não é ponto no tempo; a seleção só vale para frente), `docs/PUMPFUN.md` §10.3–10.4, [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] e [[KB-0142-kol-e-call-antecipam-ou-confirmam]] (a previsão honesta é NÃO CONFIRMA ou REFUTA: vencedores e KOLs confirmam, não antecipam), e a [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria|decisão sobre seguidores]] (descritivo, uma leitura por carteira, desconhecido nunca vira 0). Brutos: `.claude/state/astra-review-copy-leader-selection.md` (regra), `…-code.md` (código) e `…-r3.md` (confirmação).

## A regra congelada (`copy-leaders-rule/1`)

Texto integral e sha256 estão no módulo e são impressos em cada execução; hash vigente
`d0460e856adc5101d415d8aef652de9c5dda09803d2af7c5f6025f6ffa85e18c`. Em uma linha por item:

1. Universo: as 6 visões do `/pnl-leaderboard` (daily/weekly/monthly × combined/realized), 100 linhas; endereço não Solana sai.
2. Pelo menos **2 períodos** distintos (combined + realized do mesmo período contam como um).
3. Linha de referência = a do período mais longo (monthly > weekly > daily), `combined` se existir.
4. `realizedPnlSol > 0` em **todas** as linhas da carteira.
5. `buySpendSol > 0` e `realizado / (realizado + max(não realizado, 0)) ≥ 0,5`.
6. `realizado + não realizado > 0` na linha de referência.
7. `positionsCount ≥ 10`; posições por dia é só descritiva.
8. Ordem: **média das posições nos três quadros `realized`** (ausente = 101), menor primeiro, empate por endereço; top 20; se passarem menos, ficam menos.
9. `isVerified` e seguidores são descritivos.
10. `--include` (até 4): sem filtros, estrato `escolha_everton`; se a regra também a escolheria, fica em `regra` com `everton_pick=true`, ocupa a vaga da regra e não cria vaga extra.
11. Quadro completo = 100 linhas legíveis, nenhuma malformada, nas 6 visões; incompleto, parada (401/403/429) ou orçamento esgotado = nenhuma seleção. Lista gravada é imutável; outra seleção é outra coorte (`--new-cohort`), ligada à anterior.

Limites do método (escritos, não escondidos): nenhuma detecção verificada de robô (não cabe no orçamento de 30 requisições: 6 quadros + até 24 leituras de seguidores); as janelas se sobrepõem, então dois períodos não são dois sucessos independentes; o realizado do quadro é o do site, não o C-PnL da nossa fita; "ficar no top do quadro" é consequência de ter ganhado antes. A lista é **candidatura**, não estimativa de retorno copiável.

## Rodada 1 — a regra (antes de ver qualquer quadro filtrado)

| # | Achado | Decisão |
|---|---|---|
| a | Itens 2–8 não introduzem olhar o futuro; escolher, por carteira, a visão com melhor resultado seria pior. "Mesmo instante" precisa virar `received_at` por resposta; flag para trocar líderes não pode manter o mesmo identificador | **Aceito.** Uma linha de referência fixa; `received_at` e `requested_at` por resposta; outra seleção nasce como outra coorte (`--new-cohort`), a anterior fica intacta |
| b | Ranking: ela congelaria a **média das posições nos três quadros `realized`** (ausente = 101). Realizado absoluto mistura capital e duração; realizado/gasto explode com gasto pequeno | **Aceito integralmente** (item 8). Era a minha proposta com realizado absoluto da linha de referência; troquei |
| c | Manter 10 posições e 0,5 de participação realizada como escolhas convencionais, sem alegar calibração; **remover** o filtro de 50 posições/dia (o campo não mede negócios nem atividade) | **Aceito.** Posições/dia virou descritivo. Acrescentei o item 6 (saldo positivo), que ela propôs: realizado +10 com não realizado −100 passava |
| d | `isVerified` e seguidores só descritivos está certo; sem cotas; relatórios separados por `isVerified` sem novas chamadas; o selo não é, demonstradamente, o KOL do KB-0142 | **Aceito.** O campo é guardado por carteira e por linha; a análise por subgrupo não pode "salvar" o primário |
| e | JSON: versão da regra, `run_id`, janela do quadro, `lastRefreshedAtMs`, funil, motivos por carteira, requisições e o motivo da parada; números como strings decimais; falha de seguidores não exclui líder; `rule_selected` = top 20 efetivo | **Aceito** (ver o formato abaixo) |

## Rodada 2 — o código

| # | Achado (cenário) | Decisão |
|---|---|---|
| 1 | **HIGH.** O analisador só exigia lista não vazia e descartava linha malformada: seis quadros de uma linha selecionavam, e uma linha com realizado negativo e `positionsCount` ausente sumia, aprovando a carteira (itens 1, 4, 11) | **Aceito e corrigido.** Completo = 100 linhas legíveis e zero malformada em cada visão; senão `BoardsIncomplete`, exit 2, nada gravado. Testes `test_a_view_with_fewer_than_100_rows…` e `test_one_malformed_row_makes_the_view_incomplete…`. Isto mudou o **texto** do item 11 e, portanto, o hash (ver a emenda) |
| 2 | MEDIUM. `known_at` perdia frações de segundo: `04:47:00.900 → 04:47:00Z` deixa um consumidor admitir evento antes do conhecimento | **Aceito.** Milissegundos arredondados para cima (`iso_ceil`); `t0_not_before` é só piso, e o JSON diz que T0 vem depois da gravação |
| 3 | **HIGH.** O JSON não deixava reconstruir a seleção (só conclusão e escore) | **Aceito.** `evaluated[].rows` guarda as linhas sanitizadas que fundamentam cada filtro; `content_sha256` cobre o documento inteiro; `list_sha256` continua cobrindo só as carteiras |
| 4 | MEDIUM. As respostas de seguidores não entravam no documento; o 429 e os "não consultados" ficavam iguais; `stop_reason` nulo na parada por margem do limite | **Aceito.** `responses` traz **todas** as respostas (com `body_sha256`); o seguidor que levou o 429 fica `http_429` e os não consultados `not_read:http_429`; `stop_reason` também para margem e orçamento |
| 5 | Conflito: sobreposição vira `escolha_everton` no código, mas `docs/design/copiar-carteiras-papel.md` manda manter em `regra` com marca; isso muda quem entra no primário | **Aceito.** Item 10 reescrito: estrato `regra` + `everton_pick`. O nome do estrato também passou a `regra` (o desenho usa `copy_v0/1` = regra e `copy_everton_v0/1`) |
| 6 | Como registrar 17/20 verificadas sem mexer na regra | **Aceito.** Observação datada abaixo; nenhuma cota, filtro ou mudança do primário; o selo não é igualado ao KOL |

## Rodada 3 — confirmação

Sem novo bloqueador de código. Duas orientações absorvidas: (i) **a próxima execução válida (gravando) é a definitiva**, qualquer que seja a composição; uma seleção válida não é refeita porque desagradou (falhas ficam registradas); (ii) **T0 vem depois da gravação concluída e do início efetivo da pista**; `t0_not_before` é limite inferior, não comprovante de persistência. Pendência que **não é desta tarefa**: `docs/design/copiar-carteiras-papel.md` §1 e o H-037 na Fila ainda descrevem outra regra de seleção (realizado ≥ 10 SOL, ordem por SOL/dia, histórico paginado por `user-trades`, veto por `top-holders-v2`); é preciso uma emenda que declare a regra e o hash vigentes e reconheça os dry-runs. Ver o relatório da tarefa.

## Emenda: o hash da regra mudou uma vez, antes de qualquer gravação

Primeira versão do texto: `f56b5742186ef33a3329b12d98a53c91477dcedf4df0d895a44a1b627c353d17` (itens 10 e 11 sem a definição de "completo" e com a sobreposição no estrato `escolha_everton`). Versão vigente: `d0460e85…8e18c`. Entre as duas aconteceu o dry-run das 04:47Z; os itens 1–9 (que produzem a lista) **não mudaram**, e o quadro real tinha 100 linhas e zero malformadas em cada visão e nenhum `--include`, então a mudança não altera a lista que aquela captura produziria. A Astra classifica como revisão após exposição à lista, **não** como garfo escolhido por desempenho, desde que a emenda fique datada com os dois hashes. Nenhuma coorte foi gravada nem usada; nenhum desfecho do piloto existe.

## Observação datada (não é resultado do piloto)

Dois `--dry-run` reais, anônimos, 26 requisições cada, todas HTTP 200, 0 × 429, sem desafio:

| leitura | quadros recebidos | carteiras vistas | elegíveis | escolhidas | `isVerified` nas 20 |
|---|---|---|---|---|---|
| 04:47Z–04:48Z | 04:47:44–04:47:52Z | 267 | 40 | 20 | 17 |
| 05:13Z–05:14Z (regra já com o item 11 novo, cookies desligados) | 05:13:23–05:13:31Z | 267 | 38 | 20 | 17 |

As duas listas compartilham **17 de 20** carteiras: o quadro é vivo. Funil da segunda: 169 em um só período, 34 com poucas posições, 21 com realizado não positivo, 3 quase só marcação, 2 com saldo não positivo. A regra **não** foi mexida depois de ver isto. 17 de 20 verificadas é a composição do que o site publica no topo (KB-0185: 59–84 de 100 linhas verificadas); a conclusão do piloto fica restrita à composição congelada, e `isVerified` não equivale, demonstradamente, ao selo KOL do KB-0142.

## Formato do JSON congelado (`copy-leaders/1`)

`cohort_id`, `known_at`/`t0_not_before` (ms, para cima), `rule{version,sha256,text}`, `responses[]` (rota, parâmetros, `requested_at`/`received_at`, status, `body_sha256`, cabeçalhos de limite, `window_start_sec`, linhas, malformadas), `funnel`, `requests{used,budget,stop_reason}`, `wallets[]` (endereço, estrato, `rule_selected`, `rule_rank`, `everton_pick`, visões, linha de referência, realizado/não realizado/gasto, posições, participação realizada, `is_verified`, `lastRefreshedAtMs`, escore, posições nos quadros realized, seguidores com `read_at` e `status`), `list_sha256`, `evaluated[]` (todas as carteiras vistas, com motivo e linhas) e `content_sha256`. Só endereços públicos e números; nenhum nome, biografia, imagem ou identificador de usuário.

## Divergências com a Astra

Nenhuma de fundo. Duas precisões: ela leu os números dos dry-runs como "informados, não reconsultados" (corretos: ela não chama o site); e o nome do estrato `regra` veio do desenho do quant-engineer, não dela.

## Relacionado

[[2026-10-09-piloto-copiar-carteiras-no-papel]] · [[EXP-M28-copiar-carteiras-no-papel]] · [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0142-kol-e-call-antecipam-ou-confirmam]] · [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]] · [[EXP-M15-carteiras-vencedoras]] · [[pumpfun-releitura]]

---
tags: [astra, revisao, cripto, carteira, risco, meme-executor]
date: 2026-09-28
updated: 2026-09-28
status: reaberta
owner: risk-engine-guardian
decided_on: 2026-09-28
by: Astra + risk-engine-guardian
---

# Revisão da Astra — checagem de ativos estranhos na carteira ligada (28/09/2026)

**Tarefa:** fechar a lacuna achada em [[KB-0165-staking-do-sol-parado]]. O `docs/RISK_ENGINE_MEME.md` §3.2 promete que token desconhecido na carteira recusa entradas (`wallet_unrecognized_holdings`), mas os três montadores da carteira de decisão (`entries.py`, `launch_entries.py`, `spot_entries.py`) passavam sempre vazio. Novo módulo `services/meme-executor/hunter_meme_executor/wallet_holdings.py`: lê as contas de token da carteira (SPL Token e Token-2022), depois o conjunto reconhecido no Postgres (posições abertas, compras em voo, fechamentos há ≤ 60 s, WSOL e o USDC da tesouraria), e nomeia o resto acima da poeira. O motor puro não mudou.

**Duas rodadas.** A primeira foi sobre o desenho e a segunda sobre o diff. Os brutos estão em `.claude/state/astra-review-unrecognized-holdings-design.md` e `...-diff.md`.

**Aceito na rodada de desenho:**
1. **Adiar em vez de recusar** quando não há veredito válido (§8.2, "RPC ilegível adia a entrada"). Recusar consumiria a aprovação por uma falha passageira. Eu tinha proposto recusar `wallet_holdings_unavailable` seguindo o precedente `day_anchor_unavailable`, e ela estava certa: o precedente não anula a regra específica de RPC.
2. **Publicação atômica e idade conferida de novo** depois dos awaits: uma leitura por vez, falha nunca renova o carimbo, resultado atrasado de leitura abandonada nunca publica.
3. **A promessa sobre swap manual foi corrigida.** O reconhecimento é por **mint**, não por quantidade. Unidades a mais de um mint que o motor já segura não são detectadas. Isso está escrito no contrato.
4. **Poeira no total por mint**, nunca por conta, comparada só em inteiros.
5. **Saldo confidencial do Token-2022 conta como opaco** e fica não reconhecido. Uma leitura que não se entende nunca vira "carteira limpa".

**Aceito na rodada do diff (três must-fix, cada um com teste e mutante morto):**
1. **Slots por programa, e precisam avançar.** O `min(slots)` escondia a regressão de um só programa (SPL 110→105 com Token-2022 100→120), e uma RPC atrasada que repetisse a mesma fotografia renovava o carimbo para sempre.
2. **O prazo único cobre a espera pelo lock**, as duas chamadas e o SELECT.
3. **`value` que não é lista, ou slot não inteiro, falha a leitura.** Antes, `{}` virava "carteira vazia".

**Divergência registrada:** ela preferia começar **sem** limiar de poeira (`átomos > 0`). Mantive um milionésimo de token porque o brief do Everton pede um limiar pequeno. No contrato isso ficou documentado como política deliberada e cega a preço.

**Ficou de fora (nice-to-have):** usar `minContextSlot` na RPC, que o avanço estrito já cobre na prática, e casos extras de SQL (`simulated` com assinatura, `exit_at` antigo com `updated_at` recente).

**Risco declarado para o Everton:** qualquer pessoa que mande um token acima da poeira para a carteira trava as entradas até o saldo daquele mint ser zerado. É o que o §3.2 sempre prometeu. Não há lista de exceções, e criar uma é decisão dele.

Relacionado: [[KB-0165-staking-do-sol-parado]] · [[Staking-sol-parado]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]

## Revisão do guardião de risco + Astra (28/09) — bloqueia o deploy

- **Veredito:** código correto (nenhuma entrada passa sem veredito; saídas não leem a checagem), mas **deploy bloqueado**: a carteira tem um token de phishing congelado (`DgY9…`) que o banco não explica, e com a checagem ligada todas as entradas parariam sem remédio possível. Registro em [[Open Bugs]]; decisão do Everton pendente.
- **Concordância guardião × Astra:** exceção durável e auditada por mint como correção; não reconhecer ordens `failed`; saídas intocadas.
- **Divergência:** a Astra dá ALTA ao custo de RPC sem backoff; o guardião mantém BAIXA (~2 chamadas/10 s, leitura em voo única). Decisão: backoff entra como correção barata, sem ser a razão do bloqueio.
- **Correções em curso (sem decisão do Everton):** as duas leituras em paralelo com prazo próprio (F2), backoff após falha (F3), `unrecognized` obrigatório em `wallet_from` (F4 — a causa raiz da [[KB-0165-staking-do-sol-parado]]), testes sem tempo real (F5), leitura no fim do tique (F6).
- Fonte bruta: `.claude/state/astra-review-review-wallet-holdings-guardian.md`.

## F1 — a exceção auditada por mint, implementada (28/09, guardião + Astra)

- **O que entrou (sem commit, aguardando a orquestradora):** a decisão do Everton [[2026-09-28-excecao-auditada-token-golpe]] virou a tabela `meme_wallet_holding_exceptions` (migração `0068_meme_wallet_exceptions`, global e sem RLS como as tabelas `meme_live_*`, só `SELECT` para os dois papéis, nunca apagada — só revogada, por gatilho), a ferramenta auditada `infra/scripts/wallet_holding_exception.py` (ensaio por padrão; `--apply` grava a linha e o `audit_logs` na mesma transação; `--note` tem de citar o mint) e o filtro no executor (`wallet_exceptions.py`, lido na mesma transação do conjunto reconhecido). Contrato em `docs/RISK_ENGINE_MEME.md` §3.2, com o comando do Everton; banco em `docs/DATABASE.md` §71.
- **A regra que protege o resto:** a exceção só vale **enquanto a cadeia mostra o que foi verificado** — mesmo programa, mesmos decimais, saldo não opaco, total até o observado (sem margem) e conta `frozen` quando a linha exige. Qualquer diferença volta a nomear o mint. Ela nunca reconhece o mint para comprar, vender ou sair; um teste varre o código e só aceita um leitor da tabela.
- **Leitura real, só leitura (RPC pública, 28/09 13:24Z):** conta `CX7sPvh7…` `frozen`, `100000000000` átomos (100 000 tokens, 6 decimais), autoridade de congelamento `DZ1zmeQY…` (terceiro). A política padrão aceita esse caso e grava `require_frozen = true`.
- **Rodada de desenho (aceito):** guardar o estado bruto da conta em vez de um sim/não, porque um estado desconhecido nunca pode passar, nem com `--allow-unfrozen`; teto = total observado; o downgrade recusa com **qualquer** linha, revogadas incluídas, sob lock; gatilho contra `TRUNCATE`; classificação em `test_schema_privileges`; revogar sem nota e sem cadeia.
- **Rodada do diff (aceito):** o slot do mint não é mais convertido à força; o código de saída de uso é o do argparse (2). O **must-fix foi a ordem de deploy**: `compose.sh update` roda `upgrade head`, então o release da F1 tem de ter a `0068` como cabeça. A semente do EXP-M26, renumerada para `0069`, tem pré-requisitos próprios e não pode ir junto. Isso está escrito no runbook.
- **Recusado:** gravar o id da exceção no veredito. A linha ativa na hora da admissão é reconstruível por (carteira, mint, `created_at` ≤ decisão < `revoked_at`), e o payload fica mínimo.
- **Limite declarado (Astra):** a exceção limita o saldo dispensado. Ela não detecta toda movimentação manual (descongelar, vender, recomprar e recongelar entre duas leituras daria a mesma foto) nem reconcilia SOL convertido. O reconhecimento continua sendo por mint ([[KB-0165-staking-do-sol-parado]]).
- **Provas:** 1 446 testes unitários verdes (executor + risk-core), 14 de migração, 12 de integração da ferramenta, 7 de integração do executor e 10 mutantes mortos. O bloqueio em [[Open Bugs]] cai quando o Everton aplicar a exceção pelo runbook.
- Fontes brutas: `.claude/state/astra-review-wallet-holding-exception-design.md` e `...-diff.md`.

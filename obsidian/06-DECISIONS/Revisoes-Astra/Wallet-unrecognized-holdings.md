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
- **Recusado na hora, revertido depois:** eu tinha recusado gravar o id da exceção no veredito, alegando que a linha ativa era reconstruível pelo intervalo (`created_at` ≤ decisão < `revoked_at`). Isso é falso: o veredito é reusado por até 30 s sem reler o banco. A revisão do database-architect abaixo corrigiu, e a admissão agora grava o id.
- **Limite declarado (Astra):** a exceção limita o saldo dispensado. Ela não detecta toda movimentação manual (descongelar, vender, recomprar e recongelar entre duas leituras daria a mesma foto) nem reconcilia SOL convertido. O reconhecimento continua sendo por mint ([[KB-0165-staking-do-sol-parado]]).
- **Provas:** 1 446 testes unitários verdes (executor + risk-core), 14 de migração, 12 de integração da ferramenta, 7 de integração do executor e 10 mutantes mortos. O bloqueio em [[Open Bugs]] cai quando o Everton aplicar a exceção pelo runbook.
- Fontes brutas: `.claude/state/astra-review-wallet-holding-exception-design.md` e `...-diff.md`.

## Revisão do database-architect + Astra da 0068 (28/09)

- **Veredito:** DONE_WITH_CONCERNS. A revogação única, o downgrade sob lock, a tabela global e os grants só de leitura estão certos. Houve dois must-fix. Fonte bruta: `.claude/state/astra-review-review-0068-wallet-exceptions.md`.
- **Must-fix 1, o teste dependia da semente:** o teste da `0068` lia `0069_meme_mature_chart_arms.py` sem conferir se ele existia, e quebraria num commit sem a semente. Agora a checagem da semente só roda se o arquivo existir, e o mesmo arquivo serve com e sem a `0069`.
- **Must-fix 2, a reconstrução por intervalo era falsa:** o veredito é reusado por até 30 s sem reler o banco. Uma exceção revogada 1 s depois da leitura ainda decide uma admissão 2 s depois, e o intervalo `created_at`/`revoked_at` já a excluiria. A correção: cada entrada de `admission.wallet_holdings.excepted` grava `mint`, `exception_id` e `created_at` da linha usada. O heartbeat continua só com os mints. O item "Recusado" acima foi corrigido.
- **Endurecimento do banco:** `max_atoms BETWEEN 1 AND 18446744073709551615` (cabe num u64 e recusa `NaN`, que o `numeric` ordena acima de qualquer número); um gatilho `BEFORE INSERT` carimba `created_at = now()` seja qual for o valor passado e recusa linha nascida revogada; a revogação exige `revoked_at = now()`. A `0068` nunca foi implantada, então endurecer agora não custa migração nova.
- **Achado lateral corrigido:** `test_schema_privileges` estava vermelho no HEAD porque a `market_events` (0059) nunca foi classificada. Ela entrou na lista.
- Revisão anterior do guardião (mesmo dia), três correções pequenas: `require_frozen` continua verdadeiro se a conta foi vista congelada por terceiro, mesmo com `--allow-unfrozen`; um teste fixa quem pode importar o código da exceção; e o contrato diz que a revogação não cancela uma compra já admitida. Fonte bruta: `.claude/state/astra-review-review-wallet-exception-guardian.md`.

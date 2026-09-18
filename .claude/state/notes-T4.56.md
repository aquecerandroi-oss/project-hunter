# T4.56 — Cadeia vence fita no fluxo do criador (COVER)

## Pedido
R56 §3.2 (`.claude/state/notes-R56.md`): COVER, 17/09/2026. Criador vendeu 200 M tokens (20,1 SOL)
às 19:46:28 BRT. Às 19:46:56 a leitura on-chain da ATA (saldo 0 contra base 200 M) recusou
`creator_net_seller`. Às 19:47:20 (23 s depois) a mesa repropôs o mesmo mint; `meme_features_1m.creator_sold
= false` (venda entrou na fita 37,7 s atrasada) tinha precedência (`admission.creator_net_sol`), a
cadeia não foi consultada (`needs_chain_creator_flow` exigia `creator_sold IS NULL`), e
`creator_net_seller` não estava em `DETERMINISTIC_REFUSALS` → comprada, −0,08 R real.

## O que foi feito (tudo no executor; nenhum check, limiar ou janela mudou)
1. **Precedência** — `creator_flow.py`:
   - `needs_chain_creator_flow`: lê a cadeia quando `creator_sold` é `NULL` **ou** `false` (e base > 0,
     criador conhecido); `true` é fato e dispensa o RPC.
   - `resolve_creator_flow(tape_sold, flow, remembered_at) -> CreatorVerdict` (puro): qualquer fonte que
     diga "vendeu" ⇒ `−1` (nome: cadeia deste tique > memória > fita); "não vendeu" exige que toda fonte
     presente concorde; cadeia `+1` nunca sobrepõe fita `true`; fita `false` só preenche cadeia
     ausente/falha; tudo calado ⇒ `None` (`creator_flow_unknown`).
   - `admission.creator_net_sol` delega ao `resolve_creator_flow`; `context_from` ganhou
     `creator_sold_remembered_at`.
2. **Carência** — `refusal_cooldown.py`: `creator_net_seller` em `DETERMINISTIC_REFUSALS` (o motor só
   emite esse nome; não existe `creator_is_net_seller`). `creator_flow_unknown` continua fora.
3. **Memória por mint** — `CreatorSoldMemory` (`creator_flow.py`), em
   `ExecutorState.creator_sold_on_chain` (`context.py`): primeira leitura da cadeia que viu venda, por
   mint, 30 min (`CREATOR_SOLD_MEMORY_TTL_S`), máx. 4 096 mints, despejo por idade em todo acesso e do
   mais antigo ao inserir. Enquanto lembrada: sem segundo RPC, nenhum `false` da fita reabre.
4. **JSON `admission`** — `admission_context.py` grava `creator_verdict =
   {net_sol, decided_by, tape_creator_sold, chain_net_sol, remembered_sold_at}` em toda admissão, ao lado
   do `creator_flow` já existente (leitura da cadeia ou `read_failed`).

## Arquivos
- `services/meme-executor/hunter_meme_executor/creator_flow.py`
- `services/meme-executor/hunter_meme_executor/admission.py`
- `services/meme-executor/hunter_meme_executor/admission_context.py`
- `services/meme-executor/hunter_meme_executor/context.py`
- `services/meme-executor/hunter_meme_executor/refusal_cooldown.py`
- `services/meme-executor/tests/test_creator_precedence.py` (novo)
- `services/meme-executor/tests/test_creator_flow.py` (o teste "a fita vence" virou dois: `true` dispensa
  o RPC, `false` não silencia a cadeia)
- `docs/RISK_ENGINE_MEME.md` (§3.5 carência; §4 fluxo do criador, parágrafo T4.56)

## Provas
- `uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "not live"` → **297 passed**
  (137 s, com Docker; inclui as 22 novas em `test_creator_precedence.py`).
- `ruff check` / `ruff format --check` nos arquivos tocados: limpos. `pyright` nos arquivos tocados:
  0 erros.
- `infra/scripts/check_file_size.py`: só `packages/core/hunter_core/execution/meme/submit.py`
  (439 > 350) — arquivo de outro agente nesta sessão, não tocado aqui.

## Concerns
- A memória vive no processo: restart esquece (o que sobrevive é a carência de 120 s em Postgres, que
  agora inclui `creator_net_seller`). Persistir em `meme_tokens` seria o passo seguinte se um restart
  no meio de uma reproposta aparecer no diário.
- Fita `false` + cadeia falhando (timeout/RPC) ⇒ `+1` pela fita, por decisão do brief ("a fita preenche
  quando a cadeia está ausente/falha"). Se o RPC degradar, isso é a T4.45 de antes; o `creator_verdict`
  mostra `chain_net_sol = ""` nesses casos, então dá para contar quantas admissões passaram assim.
- Custo: +1 RPC (0,2–0,4 s) nas admissões com `creator_sold = false` e base > 0, que antes não liam.
  Não afeta moedas sem base (R56 §3.1 — 90 % das vistas primeiro pelo `trenches_ws`), que continuam
  `creator_flow_unknown`; esse buraco é outra tarefa.
- Não commitado.

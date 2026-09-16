# T4.42 — via rápida lê a curva em `confirmed` (−12 s de atraso na proposta)

**Gatilho:** KB-0117 (16/09, obsidian/11-KNOWLEDGE) mediu a série de 15 s nascendo ~11-12 s velha
por construção — `rpc_curves.decode_curve_batch` fixava `commitment = finalized` (32 slots) e
`observed_at = block_time`. Somado à idade da própria linha no instante da proposta: **20,7 s
(p50) / 30,8 s (p90)**.

## O que mudou

1. `packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_curves.py` — `decode_curve_batch`
   ganhou `commitment: str = FINALIZED` (era hardcoded) e estampa o valor recebido em cada
   `NormalizedCurveState.commitment`, nunca re-derivado.
2. `packages/exchange-adapters/hunter_exchanges/pumpfun/rpc.py` — `SolanaRpcClient.get_curve_states`
   ganhou `commitment: str = "finalized"` (kwarg), valida contra `{"confirmed", "finalized"}`
   (`ValueError` antes de qualquer chamada HTTP em caso de valor desconhecido) e monta
   `{"encoding": "base64", "commitment": commitment}` para o `getMultipleAccounts`. `get_curve_state`
   (leitura única) e `get_mayhem_flows` **não mudaram** — continuam com `_FINALIZED` fixo.
3. `services/meme-worker/hunter_meme_worker/context.py` — `ChainSource.get_curve_states` (Protocol)
   ganhou o mesmo kwarg, default `"finalized"`.
4. **Novo** `services/meme-worker/hunter_meme_worker/fast_lane_config.py` — satélite de
   `config.py` (que já está exatamente no teto de 350 linhas, como `sources.py`; precedente é
   `events_config.py`). Expõe `fast_lane_commitment()`, lê `MEME_FAST_LANE_COMMITMENT` a cada
   chamada (nunca em cache), default **`confirmed`**, valor desconhecido vira o default + aviso
   `meme_config_invalid`.
5. `services/meme-worker/hunter_meme_worker/fast_lane.py` — `fast_once` passa
   `commitment=fast_lane_commitment()` para `ctx.chain.get_curve_states(...)`. Docstring do módulo
   ganhou uma seção curta explicando a doutrina (proposta/papel, não dinheiro).
6. `services/meme-worker/hunter_meme_worker/chain.py` (laço de minuto, **não editado
   funcionalmente**) — só um parágrafo de docstring deixando explícito que continua em `finalized`
   por default (não passa `commitment`), porque é essa leitura que marca `meme_curve_snapshots`
   para o PnL de papel.
7. `services/meme-worker/hunter_meme_worker/wiring.py` — `heartbeat_once` grava
   `fast_lane_commitment` no `hb:meme:radar` (uma linha; não tocou `sources.py`, que também está
   no teto de 350 linhas).
8. **Sem migração.** `meme_curve_snapshots.commitment` já existe (`packages/core/hunter_core/db/
   models/meme_series.py`) com `CHECK (commitment IS NULL OR commitment IN ('confirmed',
   'finalized'))` — a coluna livre que o brief previu.
9. `collect.py` **não foi tocado** — não chama `get_curve_states` diretamente (só `persist_reading`,
   que recebe o `NormalizedCurveState` já com `commitment` resolvido por quem o leu).

## Por que é seguro sem tocar em dinheiro

O admissor real (`services/meme-executor/hunter_meme_executor/chain.py`) relê a curva ao vivo antes
de qualquer ordem — a leitura em `confirmed` só alimenta uma proposta ou uma marca de papel. Uma
reorg de `confirmed` é rara e nunca passa despercebida (o próximo tick de 15 s relê); o pior caso é
uma linha de papel mal precificada, nunca uma entrada real.

## Arquivos-satélite por causa do teto de 350 linhas

`config.py` (350/350) e `sources.py` (350/350) já estavam no teto no dia em que esta tarefa
começou — nenhum dos dois foi tocado. `fast_lane_commitment()` vive em módulo próprio
(`fast_lane_config.py`, padrão de `events_config.py`); o campo do heartbeat foi acrescentado em
`wiring.py` (309/350 antes da mudança), que já mescla os dicts de várias fontes com `.update()`.

## Testes

- `packages/exchange-adapters/tests/unit/test_pumpfun_rpc_curves.py` — default `finalized`
  preservado; `commitment="confirmed"` propagado e estampado; `commitment` desconhecido levanta
  `ValueError` antes da chamada HTTP; `decode_curve_batch` sozinho com e sem `commitment`.
- **Novo** `services/meme-worker/tests/test_fast_lane_config.py` — default `confirmed`; env
  `finalized` explícito; espaços/maiúsculas tolerados; valor inválido cai no default.
- `services/meme-worker/tests/test_fast_lane.py` — `FakeChain` (em `test_chain.py`) agora grava
  `commitment` recebido; um teste novo confirma o default `confirmed` na leitura real do
  `fast_once`, outro confirma que `MEME_FAST_LANE_COMMITMENT=finalized` chega à chamada.

## Comandos (saída real abaixo, no relatório da tarefa)

```
uv run ruff check packages/exchange-adapters services/meme-worker
uv run ruff format --check packages/exchange-adapters services/meme-worker
uv run pyright packages/exchange-adapters/hunter_exchanges/pumpfun/rpc.py packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_curves.py services/meme-worker/hunter_meme_worker/fast_lane.py services/meme-worker/hunter_meme_worker/fast_lane_config.py services/meme-worker/hunter_meme_worker/context.py services/meme-worker/hunter_meme_worker/wiring.py services/meme-worker/hunter_meme_worker/chain.py
uv run pytest packages/exchange-adapters/tests services/meme-worker/tests/test_fast_lane.py services/meme-worker/tests/test_fast_lane_config.py services/meme-worker/tests/test_chain.py -q -m "not live"
python infra/scripts/check_file_size.py
```

## Pendências / concerns

- Não adicionei um teste de `wiring.heartbeat_once` para o novo campo `fast_lane_commitment` (não
  havia suíte cobrindo essa função; cobertura é só de leitura direta do módulo satélite + do
  `FakeChain.commitments` em `test_fast_lane.py`). Revisão manual do diff de `wiring.py` recomendada.
- `getBlockTime` em `confirmed` pode, em teoria, devolver `null` mais vezes que em `finalized` para
  o slot mais recente (não medido ao vivo — sem live tests neste ambiente); o comportamento
  existente (`observed_at = received_at`, contado em `block_time_missing`) já cobre esse caso sem
  mudança de código.

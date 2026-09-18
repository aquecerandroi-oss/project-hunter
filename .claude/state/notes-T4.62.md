# T4.62 — redação de log por valor + resiliência do event-gate

**Data:** 2026-09-18. Achados verificados pelo `security-reviewer` (HIGH-1, HIGH-2, quatro MEDIUM,
um LOW). Nenhuma chave real foi lida, copiada ou logada nesta sessão; toda URL de teste é
`https://example.invalid/?api-key=FAKE1234abcd`.

## O que mudou

- `packages/core/hunter_core/logging.py` (HIGH-1/HIGH-2):
  - `redact_secret_values_processor` — último processador de `shared_processors` (depois de
    `format_exc_info`, então também dentro de `foreign_pre_chain`). Varre recursivamente todo
    campo string do `event_dict` (`event`, `exception`, `error`, dicts/listas aninhadas) por
    `_SECRET_VALUE_RE` (`api-key=`, `apikey=`, `api_key=`, `token=`, `key=`, `secret=`,
    `password=`, case-insensitive) e mascara o valor mantendo os 4 primeiros caracteres
    (`FAKE1234abcd` → `FAKE***`). Complementa `redact_processor` (que só olha nome de campo).
  - `redact_url(url)` — mesma máscara, exportada para adapters que montam `error=str(exc)` fora
    do pipeline de log.
  - `configure_logging` agora sobe `logging.getLogger("httpx")`/`("httpcore")` para `WARNING`
    (eram INFO por padrão — a linha `HTTP Request: POST https://...?api-key=...` do próprio
    httpx é a rota real do vazamento).
- `packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_ws.py` (MEDIUM): as quatro chamadas
  `logger.warning(..., error=str(exc))` de `listen()`/`_close_quietly` (connect, connection,
  resubscribe, close) agora passam por `redact_url(str(exc))` — `InvalidURI`/`InvalidProxy` podem
  ecoar a URI completa (com chave) na mensagem da exceção.
- `services/meme-worker/hunter_meme_worker/event_gate.py` (MEDIUM):
  - `_evaluate_loop`/`_flush_loop`: `apply_notification`/`evaluate_mint` agora têm try/except por
    notificação — uma exceção conta `bad_frames_total` (`_log_bad_frame`, com `error_type` e
    `error` redigido) e o loop segue, em vez de matar o `TaskGroup`.
  - `run_event_gate_forever`: o log `meme_event_gate_crashed_restarting` agora carrega
    `error_type`, `error` (redigido) e `exc_info=True` (traceback compacto pelo `format_exc_info`
    → redator); `rt.stats.record_restart()` soma em `event_gate_restarts_total`.
- `services/meme-worker/hunter_meme_worker/event_gate_eval.py` (MEDIUM): `handle_reconnect` — o
  `INSERT` de lacuna (`record_gap`) agora está em try/except; falha (pool/`statement_timeout`)
  conta `event_gate_gap_write_failed_total` e loga, nunca propaga (era a suspeita para os 13
  restarts/h medidos).
- `services/meme-worker/hunter_meme_worker/event_gate_stats.py`: três contadores novos
  (`restarts_total`, `gap_write_failed_total`, `bad_frames_total`) e os três campos
  correspondentes em `heartbeat_fields` (`event_gate_restarts_total`,
  `event_gate_gap_write_failed_total`, `event_gate_bad_frames`).
- LOW (`tx_rpc.py`/`rpc.py`): nenhuma mudança de código — confirmado por teste que
  `redact_secret_values_processor` cobre texto de `__cause__` encadeado (o traceback inteiro é uma
  string única quando chega ao processador).
- Docs: parágrafo em `docs/SECURITY.md` §4.

## Testes

- `packages/core/tests/unit/test_logging.py` (+13 novos): `redact_secret_values_processor` mascara
  `event`/`exception` para as 7 variantes de nome de chave testadas, cobre dict aninhado, não toca
  texto sem segredo; `redact_url`; `configure_logging` sobe `httpx`/`httpcore` para WARNING; um
  registro INFO do logger `httpx` não aparece com o nível padrão.
- `services/meme-worker/tests/test_event_gate_resilience.py` (novo, 5 testes, puro/sem Docker,
  reaproveita `FakeWs`/`_runtime` de `test_event_gate_notify.py`): `handle_reconnect` com sessão
  que falha não propaga e conta `gap_write_failed_total`; a mesma falha loga `error_type`;
  `_evaluate_loop` conta um frame ruim e continua processando o próximo; o log do frame ruim carrega
  `error_type`; `run_event_gate_forever` conta e loga um restart com `error_type`.

## Comandos rodados (saída real)

- `uv run pytest packages/core/tests/unit services/meme-worker/tests -q -k "logging or redact or
  event_gate" -m "not live and not integration"` → **77 passed, 1805 deselected**
- `uv run pytest services/meme-worker/tests/test_event_gate_integration.py` (testcontainers) →
  **8 passed**
- `uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_rpc_ws.py` → **14 passed**
- `uv run ruff check` / `ruff format --check` nos arquivos tocados → limpo (dois arquivos de teste
  precisaram de `ruff format` para quebrar linha, aplicado)
- `uv run pyright` nos arquivos tocados → 0 erros (o teste novo precisou de
  `# pyright: reportPrivateUsage=false`, mesmo padrão de `test_event_gate_integration.py`)
- `uv run python infra/scripts/check_file_size.py` → **0 over budget** (o comentário extra em
  `rpc_ws.py` estourou 350→352; reduzido para uma linha, voltou a 350)

## Residuais (não feitos aqui)

- `event_gate_gap_write_failed_total`/`bad_frames_total` não fazem parte da lista de campos que o
  brief exige no heartbeat (só `restarts_total` era exigido lá); expus os três mesmo assim por
  consistência de observabilidade — se não for desejado, é reverter as duas linhas em
  `heartbeat_fields`.
- Não toquei `conviction*.py`/`entries.py` (outro agente) nem `lab_repo_fast.py` (agente T4.61a),
  conforme instrução.

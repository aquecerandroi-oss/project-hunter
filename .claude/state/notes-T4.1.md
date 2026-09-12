# T4.1 / A4.1 — adapter público pump.fun

Execução de 12/09/2026, 02:15–02:26 BRT (UTC−3). Papel: exchange-integration-specialist.
Status: DONE_WITH_CONCERNS — limites do coletor futuro descritos abaixo; sem commit.

## Escopo e retomada

Retomados os seis módulos preexistentes não rastreados: curve.py, decode.py, models.py,
normalize.py, rest.py, ws.py. Acrescentado rpc.py, três módulos de testes unitários e
fixtures datadas; docs/EXCHANGE_INTEGRATION.md §9 documenta contratos e limites.
Não alterados apps/**, services/**, obsidian/**, migrações, configurações de produção ou .env*.
Os arquivos de fixture herdados foram preservados; somente os arquivos A4.1 e Mayhem
listados no status abaixo foram capturados nesta execução. Nenhuma dependência adicionada.

## TDD — falhas observadas antes das correções

`timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_normalize.py -q`
→ `10 failed in 1.35s`: Mayhem/observed_at ausentes, bool textual e reserva fracionária
aceitos, quote diferente de SOL aceita, discriminador/bools on-chain não validados.

`timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_clients.py packages/exchange-adapters/tests/unit/test_pumpfun_ws.py -q`
→ `1 error in 2.01s`, `ModuleNotFoundError: No module named 'hunter_exchanges.pumpfun.rpc'`.

`timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_ws.py -q`
→ `5 failed, 4 passed in 2.62s`: perda decimal, UTF-8 malformado, migração de outro pool,
ACK zerando backoff e aclose sem encerrar socket.

Regressões adicionais antes de corrigir: `3 failed, 22 passed in 1.38s` para identidades
nulas; `1 failed, 10 passed in 1.85s` para URL injetável presente no erro de transporte REST.
Após correções intermediárias: `29 passed in 1.79s`.
Ruff corrigiu imports/formatação somente nos dez arquivos Python do escopo.
Pyright inicialmente apontou 33 erros (tipagem JSON, override e testes); todos corrigidos.

## Evidência pública datada

Captura via `timeout 120 uv run python -`, usando httpx + websockets, asyncio.timeout(55),
open_timeout=15 e somente subscribeNewToken/subscribeMigration. Horários abaixo em BRT:

- 02:20:41: GET /coins/mayhem-mode?limit=1&mayhemState=active → HTTP 200.
- 02:20:41: GET /mayhem/overview → HTTP 200.
- WebSocket anônimo: 11 frames em janela limitada a 55 s; frames completos e observed_at
  em pumpportal_ws_a41_live.json. Resultado `55s capture deadline`, não falha de conexão.
- 02:21:49: GET /coins/{mint} → `GET coin HTTP 200`.
- 02:21:50: POST getAccountInfo, encoding base64, commitment finalized → `POST getAccountInfo HTTP 200`.
- Arquivos capture_a41_metadata.json e capture_a41_accounts_metadata.json registram
  endpoints públicos, códigos, mint/conta e horários UTC. Os bytes das respostas HTTP
  estão em mayhem_list_raw.json, mayhem_overview_raw.json, coin_a41_raw.json e rpc_a41_raw.json.
- IDL: GET https://raw.githubusercontent.com/chainstacklabs/pumpfun-bonkfun-bot/a0540fdc9e6bb108d52f0f512f2e396d2396bdef/idl/pump_fun_idl.json
  → `IDL HTTP 200`; BondingCurve = cinco u64, complete bool, creator pubkey,
  is_mayhem_mode bool, is_cashback_coin bool, quote_mint pubkey, após discriminador de 8 bytes.
  A leitura web inicial do raw retornou cache miss; a consulta direta por httpx confirmou.
- Documentação consultada: https://pumpportal.fun/data-api/real-time/ — somente os dois
  canais gratuitos usados; nenhum feed pago foi assinado. A captura não comprova SLA.

Os comandos de captura usaram Python por stdin em primeiro plano, com timeout explícito;
nenhum arquivo de configuração/segredo foi carregado. Não houve transação on-chain.

## Verificações finais — comandos e saída real

### `timeout 290 uv run pytest packages/exchange-adapters/tests/unit -q`

Exit 0.

```text
........................................................................ [ 17%]
........................................................................ [ 35%]
........................................................................ [ 52%]
........................................................................ [ 70%]
........................................................................ [ 87%]
...................................................                      [100%]
411 passed in 4.34s
```

### `timeout 290 uv run ruff check packages/exchange-adapters/hunter_exchanges/pumpfun packages/exchange-adapters/tests/unit/test_pumpfun_*.py`

Exit 0.

```text
All checks passed!
```

### `timeout 290 uv run ruff format --check packages/exchange-adapters/hunter_exchanges/pumpfun packages/exchange-adapters/tests/unit/test_pumpfun_*.py`

Exit 0.

```text
10 files already formatted
```

### `timeout 290 uv run pyright packages/exchange-adapters/hunter_exchanges/pumpfun packages/exchange-adapters/tests/unit/test_pumpfun_*.py`

Exit 0.

```text
0 errors, 0 warnings, 0 informations
WARNING: there is a new pyright version available (v1.1.411 -> v1.1.414).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`
```

### `timeout 290 uv run python infra/scripts/check_file_size.py`

Exit 0.

```text
scanned 640 files; 0 over budget, 0 grandfathered
```

## Revisão própria e limites

Sem MUST-FIX conhecido dentro do brief após os testes. Cenários resolvidos: discriminador
errado não vira reserva; booleano textual não vira complete=true; SOL não recebe quote USDC;
ACK sozinho não reinicia infinitamente as tentativas; float JSON não arredonda o preço;
identidade nula não vira string 'None'; erro REST não revela URL injetada.

A tentativa de delegação ao especialista falhou na ferramenta com
`collab spawn failed: no thread with id`; não se declara revisão independente ou consenso.
Astra fez a revisão própria. Não se executou outro Codex, pois o wrapper escreve arquivos
fora do escopo do brief. O orquestrador ainda deve revisar o diff antes de qualquer commit.

Limitações explícitas: dedupe FIFO por mint+assinatura é volátil e não distingue instruções;
reconnects não são recuperação de gaps; eventos WS têm hora local, não block time/finalidade.
O caller deve fornecer a conta correta do mint (PDA não verificada aqui). Layout mínimo
115 bytes recusa versões anteriores; quotes diferentes de SOL são recusadas. O campo
on-chain is_mayhem_mode não é o estado ativo/pausado do agente. Overview permanece metadata
rotulado. Buckets sem Redis são locais à instância, e REST aceita burst: futura integração
precisa orçamento compartilhado por IP, gestão de gaps e system_event para 429.
RPC público tem pacing adicional por método; provedor com chave/pago continua decisão do Everton.
O docstring herdado que dizia igualdade byte a byte com REST foi corrigido: snapshots não
são atômicos e o próprio arquivo REST herdado dizia mayhem_state=paused.

## Arquivos — git status --porcelain --untracked-files=all (escopo completo)

Arquivos não rastreados herdados continuam `??`; isso não significa criação nesta rodada.

```text
 M docs/EXCHANGE_INTEGRATION.md
?? .claude/state/notes-T4.1.md
?? packages/exchange-adapters/hunter_exchanges/pumpfun/curve.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/decode.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/models.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/rest.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/rpc.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/ws.py
?? packages/exchange-adapters/tests/fixtures/pumpfun/capture_a41_accounts_metadata.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/capture_a41_metadata.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/coin_a41_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/frontend_api_v3_coin_by_mint_response_headers.txt
?? packages/exchange-adapters/tests/fixtures/pumpfun/frontend_api_v3_coin_by_mint_response_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/frontend_api_v3_coins_response_headers.txt
?? packages/exchange-adapters/tests/fixtures/pumpfun/frontend_api_v3_coins_response_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/mayhem_list_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/mayhem_overview_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/pumpportal_ws_a41_live.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/pumpportal_ws_capture_raw.jsonl
?? packages/exchange-adapters/tests/fixtures/pumpfun/rpc_a41_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/rpc_get_account_info_bonding_curve_raw.json
?? packages/exchange-adapters/tests/unit/test_pumpfun_clients.py
?? packages/exchange-adapters/tests/unit/test_pumpfun_normalize.py
?? packages/exchange-adapters/tests/unit/test_pumpfun_ws.py
```

## OBSIDIAN

- Exchange Adapters — registrar o adapter pump.fun público, contratos e ausência de wiring.
- WebSockets — registrar assinatura gratuita, timestamps locais e dedupe volátil.
- Meme Radar — fontes e protocolo — registrar capturas datadas e decisão pendente do RPC.
Nenhuma página Obsidian foi alterada, conforme o escopo.

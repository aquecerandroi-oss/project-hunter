# T4.54 — Tesouraria USDC → SOL (Jupiter)

## Pedido
Everton, 17/09/2026: "eu quero deixar atualizado para usar outra moeda". A carteira do robô
(`ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4`) tinha 21,33 USDC além de ~0,67 SOL; o pump.fun só
compra com SOL. Pedido: quando o SOL cair abaixo de um piso, o executor troca USDC → SOL sozinho,
dentro de tetos, com auditoria.

## Desenho (o que foi implementado)
- **Pacote novo** `packages/exchange-adapters/hunter_exchanges/jupiter/` (`client.py`, `models.py`,
  `versioned_tx.py`, `__init__.py`): cliente HTTP público da Jupiter v6 (`GET /quote`,
  `POST /swap`), sem chave, sem retry em 4xx, timeout 5 s, dataclasses tipadas com `Decimal`. Mais
  um decodificador de transação **versionada (v0)** — `hunter_exchanges.pumpfun.solana_codec`
  recusa v0 de propósito (nossas próprias transações nunca usam *lookup table*); a Jupiter sempre
  devolve v0, então esse decode ficou num módulo à parte, e resolve só as contas estáticas —
  qualquer `program_id` atrás de uma *lookup table* fica `None` (nunca resolvido, nunca confiado).
- **Regras puras** `services/meme-executor/hunter_meme_executor/treasury_rules.py`: tamanho do
  swap (duas passadas: teto ingênuo, depois encolhe para o que falta até o alvo ao preço da
  cotação), classificação de recusa da cotação (rota vazia, impacto de preço > 1 %), o verificador
  de lista branca (`JUP6…`, Token, Token-2022, ATA, System, ComputeBudget; carteira é o único
  signatário/*fee payer*) e `should_attempt` (liga/desliga, live, assinante, kill switch, piso,
  intervalo mínimo, teto diário) — tudo sem rede, sem banco, sem assinatura, 100 % testável.
- **Orquestração** `treasury.py` + `treasury_db.py`: uma vez por tique do kill switch (10 s), depois
  do saldo de SOL já ter sido relido. Lê o USDC da ATA pela `ChainReader` já existente, cota,
  redimensiona, monta a transação pela Jupiter, **verifica antes de assinar**, simula
  (`simulateTransaction`, `sigVerify=false`), assina com o `MemeSigner` de sempre, envia só se
  `allow_send=True` (isto é, `live` ligado) e confirma por `getSignatureStatuses`. Uma linha em
  `meme_treasury_swaps` por tentativa, do primeiro `quoted` até `confirmed`/`failed`/`refused`.
- **Migração** `0051_meme_treasury_swaps` (`down_revision = 0050`), tabela nova, sem RLS (padrão
  `meme_wallet_trades`), `DELETE` para ninguém, downgrade recusa com linha existente. Modelo ORM
  espelhado em `packages/core/hunter_core/db/models/meme_treasury.py`. `HEAD_REVISION` de
  `test_migrations.py` foi para `0051`; os testes de `test_migration_0050.py` agora sobem só até a
  própria revisão (`REVISION`, não `head`) antes do `downgrade -1`, porque `0051` passou a existir
  em cima dela — a checagem `alembic check` contra o *head* completo ganhou seu próprio banco
  isolado nesse arquivo, sem interferir na sequência de downgrade.
- **Config**: 7 flags `MEME_TREASURY_*` (`config.py`, mesmo padrão `parse_flag`/`Decimal` do resto).
  Todas com fallback seguro em valor ilegível (nunca recusam o boot — são parâmetros de tamanho,
  não os cinco números de política).
- **Heartbeat**: campo `treasury` (json: `enabled`, `sol_floor`, `sol_target`, `last_swap_at`,
  `last_result`, `wallet_usdc`).
- **Fio único em `main.py`**: um `await treasury_once(ctx)` dentro de `kill_switch_once`, logo
  depois do `wallet_refresh_once` (do qual depende). Nada mais mudou em `main.py`/`entries.py`/
  `wake.py`.

## O que é fail-closed
- Desligada por padrão (`MEME_TREASURY_ENABLED=false`).
- Exige `live` ligado **além** da própria flag — nunca troca em papel.
- Kill switch travado (`TRADING_DISABLED`/`EMERGENCY`) barra a tentativa antes de qualquer leitura.
- Cotação vazia ou impacto de preço > 1 % é recusada antes de montar qualquer transação.
- Um `program_id` atrás de uma *lookup table* é recusado, nunca resolvido/confiado.
- Qualquer programa fora da lista branca é recusado (`program_not_allowed:<id>`).
- Mais de um signatário, ou *fee payer* diferente da carteira, é recusado.
- Falha de leitura, cotação, simulação ou confirmação nunca reenvia sozinha — a tentativa termina
  e o próximo tique (respeitando o intervalo mínimo) tenta de novo.
- `DELETE` em `meme_treasury_swaps` não existe para nenhum papel — cada linha é evidência.

## O que **não** foi testado contra a mainnet (limitação desta sessão)
Este sandbox não tem acesso de saída à rede (`curl` para `quote-api.jup.ag` deu conexão recusada).
Por isso:
- As fixtures de `packages/exchange-adapters/tests/fixtures/jupiter/` são **sintéticas** — no
  formato documentado da API v6 (que eu conheço do treinamento), não uma captura real de
  `GET /v6/quote`. Está marcado no próprio arquivo (`_fixture_note`).
- A transação versionada que os testes de `versioned_tx.py` decodificam é **construída em
  processo** pelo próprio teste (formato de wire do Solana v0, que eu tenho confiança de estar
  correto, mas não foi comparado byte a byte com uma resposta real da Jupiter). Nenhuma chave de
  carteira foi usada ou procurada para isso, como pedido.
- O caminho `simulateTransaction` → assinar → `sendTransaction` → confirmar nunca rodou contra uma
  RPC real nesta sessão — só a matemática de tamanho, a classificação de recusa e o verificador de
  lista branca foram provados (23 testes unitários puros, offline).
- **Recomendação antes de ligar em produção:** gravar pelo menos uma cotação real
  (`GET /v6/quote`, sem carteira, sem risco) para confirmar que o formato assumido bate, e rodar
  uma simulação (`--simulate-only`, no espírito do `infra/scripts/meme_simulate_trade.py`) com o
  endereço público da carteira antes de ligar `MEME_TREASURY_ENABLED=true` de verdade.
- Não toquei `docs/DATABASE.md` (deveria ganhar uma entrada para `meme_treasury_swaps`, não fiz por
  tempo — a tabela e as constraints estão documentadas na migração e no modelo ORM).

## As linhas exatas que o Everton adiciona no `.env` da VPS para ligar
```
MEME_TREASURY_ENABLED=true
# opcionais — os valores abaixo são o padrão, só escreva a linha para mudar:
# MEME_TREASURY_SOL_FLOOR=0.30
# MEME_TREASURY_SOL_TARGET=0.60
# MEME_TREASURY_MAX_USDC_PER_SWAP=25
# MEME_TREASURY_MAX_USDC_PER_DAY=50
# MEME_TREASURY_MAX_SLIPPAGE_BPS=50
# MEME_TREASURY_MIN_INTERVAL_S=600
```
Subir com `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`. Exige
`ENABLE_MEME_LIVE_TRADING` já ligada (a tesouraria nunca troca em papel). Desligar: apagar a
primeira linha (ou pôr `false`) + `compose.sh update`, ou `touch
/opt/project-hunter/run/meme/meme.kill` (para tudo, tesouraria incluída, na hora).

## Comandos e resultado (uv run pytest)
```
timeout 590 uv run pytest packages/exchange-adapters/tests/unit/test_jupiter_client.py \
  packages/exchange-adapters/tests/unit/test_jupiter_versioned_tx.py -q -m "not live"
14 passed

timeout 590 uv run pytest services/meme-executor/tests/test_treasury_config.py \
  services/meme-executor/tests/test_treasury_rules.py \
  services/meme-executor/tests/test_treasury_db.py -q -m "not live"
12 + 23 + 5 passed

timeout 590 uv run pytest packages/core/tests/integration/test_migration_0051.py -q
9 passed
timeout 590 uv run pytest packages/core/tests/integration/test_migration_0050.py -q
8 passed
timeout 580 uv run pytest packages/core/tests/integration/test_migrations.py -q
(full file) passed

timeout 590 uv run pytest services/meme-executor/tests packages/exchange-adapters/tests \
  packages/core/tests/integration/test_migration_0050.py \
  packages/core/tests/integration/test_migration_0051.py -q -m "not live"
990 passed, 2 skipped, 7 deselected

uv run ruff check <touched files>          -> All checks passed
uv run ruff format <touched files>         -> formatted (pure reformatting)
uv run pyright <touched production files>  -> 0 errors
uv run python infra/scripts/check_file_size.py -> 0 over budget (935 files scanned)
```

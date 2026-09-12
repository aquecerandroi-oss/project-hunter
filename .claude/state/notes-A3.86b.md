# A3.86b — peneira da ponte por volume observado em velas

Data: 2026-09-12. Papel: risk-engine-guardian. Execução do brief
`.claude/state/brief-A3.86b-peneira-da-ponte.md`; sem commit e sem ativação.
Status: **DONE_WITH_CONCERNS** — testes pedidos e portões do worker verdes;
portões globais com falhas fora do escopo e revisão independente indisponível.

## Entrega

- `services/execution-worker/hunter_execution_worker/bridge_screen.py:298` chama
  o helper existente `volume_window` com a mesma sessão, mercado SPOT e instante
  da peneira; compara `quote_volume_24h` com o piso existente.
- `bridge_screen.py:300`: soma ausente recusa `liquidity_unproven`; soma abaixo
  do piso mantém `spot_volume_below_floor`. Não exige 1.440 observações nem
  inventa outro limiar: preserva a semântica de cobertura parcial do helper.
- `services/execution-worker/tests/test_bridge_screen_volume.py:28` cobre os
  três cenários pedidos, o piso exato sem ticker e volume zero; verifica também
  o mercado/instante da consulta e que recusados não chegam à consulta de beta.
- `services/execution-worker/tests/test_bridge_screen_volume_integration.py:21`
  cobre coluna 120 M × velas 31 M, coluna 45 M × velas 60 M e ausência de série
  com Postgres real do testcontainer e fixtures rotuladas de teste.
- `services/execution-worker/tests/test_bridge_eligibility.py:72` passa a semear
  velas para os testes existentes; cenários de liquidez controlam as velas,
  independentemente da coluna. `docs/RISK_ENGINE.md:670` registra o contrato.

## Comandos e saídas reais

Comandos executados via Git Bash, em primeiro plano, com `timeout 290`.
Não houve duas execuções de testcontainers simultâneas nesta tarefa.
Saídas longas abaixo são extratos, identificados como tal.

### TDD — antes da alteração de produção (exit 1)

```text
$ timeout 290 uv run pytest services/execution-worker/tests/test_bridge_screen_volume.py -q -p no:randomly
5 failed in 27.89s
```

Extratos das falhas: 120 M/31 M retornava `None` em vez de
`spot_volume_below_floor`; 45 M/60 M retornava `spot_volume_below_floor`;
120 M/sem série retornava `None` em vez de `liquidity_unproven`.

### Verificação do brief (exit 0)

```text
$ timeout 290 uv run pytest services/execution-worker/tests/test_bridge_screen*.py services/execution-worker/tests/test_volume_24h_source.py -q -p no:randomly
10 passed in 124.81s (0:02:04)
$ timeout 290 uv run pytest services/execution-worker/tests -m unit -q -p no:randomly
112 passed, 94 deselected in 3.64s
```

A primeira tentativa da verificação combinada encontrou `NameError: name
'AsyncEngine' is not defined` na coleta do arquivo de integração novo
(`1 error in 3.59s`); corrigido com `from __future__ import annotations` antes
da execução verde acima.

### Regressão adicional da ponte (exit 0)

```text
$ timeout 290 uv run pytest services/execution-worker/tests/test_bridge_eligibility.py services/execution-worker/tests/test_bridge_cycle.py services/execution-worker/tests/test_bridge_consumer.py -q -p no:randomly
30 passed in 246.43s (0:04:06)
```

### Portões do worker e tamanho (exit 0)

```text
$ timeout 290 uv run ruff check services/execution-worker
All checks passed!
$ timeout 290 uv run ruff format --check services/execution-worker
70 files already formatted
$ timeout 290 uv run pyright services/execution-worker
0 errors, 0 warnings, 0 informations
$ timeout 290 uv run python infra/scripts/check_file_size.py
scanned 639 files; 0 over budget, 0 grandfathered
```

O Pyright também avisou haver versão nova (1.1.411 → 1.1.414); não atualizada.
`bridge_screen.py`: 321 linhas; testes novos: 86 e 58 linhas.
O checker canônico exclui testes do orçamento; o arquivo de elegibilidade já
era maior que 350 linhas antes desta tarefa. Não foi refatorado fora do escopo.

### Portões globais — falhas externas ao escopo

```text
$ timeout 290 uv run ruff check .
RUF100 [*] Unused `noqa` directive (non-enabled: `S311`)
  --> packages/exchange-adapters/hunter_exchanges/pumpfun/rest.py:87:68
Found 1 error.
$ timeout 290 uv run ruff format --check .
14 files would be reformatted, 1521 files already formatted
$ timeout 290 uv run pyright
31 errors, 0 warnings, 0 informations
```

Extratos globais, todos exit 1. A formatação aponta arquivos de `infra/scripts`,
`obsidian`, `packages/core`, `packages/exchange-adapters/pumpfun` e
`services/market-worker`, nenhum arquivo da correção.
Dos 31 diagnósticos do Pyright, três eram uso intencional de fixtures privadas
entre os testes novos: documentados e suprimidos apenas nesses imports;
o worker foi verificado novamente e ficou em zero. Os outros 28 apontavam
testes da API, `infra/scripts/tests/test_render_operations.py`, testes de
estratégias em core/strategy-worker e `pumpfun/ws.py`; não foram alterados.
Após documentar os imports, Ruff pediu uma linha em branco no bloco de imports;
corrigida e os dois portões do worker passaram novamente (saídas acima).

## Revisão e limites

Revisão local: diff restrito à troca da fonte, motivo explícito, testes e frase
normativa; o helper e os limites não foram modificados. A decisão final de
admissão continua fora desta peneira. Nenhuma leitura ou escrita de `.env*`.
A tentativa de revisão independente via subagente falhou na ferramenta:
`collab spawn failed: no thread with id: 01a09405-6cc6-7ea3-ae59-4dd0785a2b73`.
Não há parecer independente produzido nesta execução.

## Arquivos tocados — saída real

```text
$ git status --porcelain -- services/execution-worker/hunter_execution_worker/bridge_screen.py services/execution-worker/tests/test_bridge_eligibility.py services/execution-worker/tests/test_bridge_screen_volume.py services/execution-worker/tests/test_bridge_screen_volume_integration.py docs/RISK_ENGINE.md .claude/state/notes-A3.86b.md
 M docs/RISK_ENGINE.md
 M services/execution-worker/hunter_execution_worker/bridge_screen.py
 M services/execution-worker/tests/test_bridge_eligibility.py
?? .claude/state/notes-A3.86b.md
?? services/execution-worker/tests/test_bridge_screen_volume.py
?? services/execution-worker/tests/test_bridge_screen_volume_integration.py
```

`git diff --check -- services/execution-worker docs/RISK_ENGINE.md
.claude/state/notes-A3.86b.md`: exit 0; apenas aviso de normalização CRLF→LF
em `docs/RISK_ENGINE.md`. Os demais arquivos da árvore compartilhada não foram
modificados por esta tarefa.

## OBSIDIAN

- **Execution Engine** — registrar que a peneira usa volume SPOT por velas e
  nomeia a ausência de série como `liquidity_unproven`.
- **Risk Engine** — registrar o fechamento do residual T3.86 na peneira, sem
  mudança de limites nem ativação de autonomia.

Páginas apenas indicadas: o brief não autoriza editá-las.

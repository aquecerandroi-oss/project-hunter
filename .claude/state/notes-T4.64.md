# T4.64 — `meme_rule_set.py --set-param` valida antes de gravar

**Data:** 2026-09-19. Motivo: dois incidentes em 18/09/2026 —
14:19 BRT `--set-param max_sol_per_bet=0.28` (sem aspas) gravou número JSON; `RuleSetSpec.from_params`
recusa `float` ("a float is not an exact number"), worker em loop de reinício 10 min; 19:47 BRT
`--set-param trailing_arm_x="1.0"` chegou a `ExitRules.__post_init__` ("trailing_arm_multiple must
be greater than 1 when set"), worker em loop ~3,5 h (até a T4.65 tornar a leitura tolerante a um
valor armado em 1×). Vault: `obsidian/11-KNOWLEDGE/KB-0140-set-param-valida-antes-de-gravar.md`
(relacionada: `KB-0131-dado-mal-formado-derruba-o-processo-duas-vezes.md`, que já registrava o
incidente das 14:19). Doc: `docs/DATABASE.md` §54 (novo parágrafo T4.64, logo após §54.1).

## O que existe

- `infra/scripts/meme_rule_set_validate.py` (novo, 84 linhas) — `validate_params(row, params)`
  carrega `params` pelo mesmo caminho do worker: `hunter_meme_worker.lab_models.RuleSetSpec
  .from_params` (o portão `_gate_from_params` incluído, com sua própria validação em
  `EntryGate.__post_init__`), depois `effective_params(spec, {}).exit_rules()` (as faixas do
  `ExitRules.__post_init__` — `target_multiple > 1`, `0 < trailing_drawdown_pct < 100`, etc. — que
  `from_params` sozinho não constrói). Qualquer exceção do worker é reembalada em `WouldNotLoad`
  com o texto original, prefixado pelo rótulo do conjunto. `_check_decimal_convention` pega o
  padrão dos dois incidentes mais cedo e com mensagem melhor: um `int`/`float` solto sobre uma
  chave cujo valor **já gravado** naquele conjunto é uma string ⇒ recusa
  `decimals are strings: use 'chave="valor"'` antes de sequer montar o documento. `validate_set_param`
  (as duas checagens, para `--set-param`) e `validate_live` (só a primeira, sobre os `params` já
  gravados de um conjunto — `--validate`) são os dois pontos de entrada.
- `meme_rule_set_types.py` ganhou `WouldNotLoad(Exception)` — módulo já dependency-free
  (sem importar `hunter_meme_worker`), então a exceção mora lá e o import pesado fica isolado em
  `meme_rule_set_validate.py`.
- `meme_rule_set_params.py`'s `set_param()` chama `validate_set_param` para cada linha de
  `to_change` **antes** de montar o relatório (dry-run) e antes do `UPDATE` (`--apply`) — a mesma
  checagem nos dois modos, como o brief pediu.
- `meme_rule_set.py` ganhou `--validate NAME/VERSION` (só leitura, sem `--reason`/`--apply`) e o
  tratamento de `WouldNotLoad` no `_main` (stderr, `EX_WOULD_NOT_LOAD = 2`, nada gravado — separado
  do `EX_REFUSED = 65` já existente para `Refused`). Docstring do módulo e mensagem de `--help`
  atualizadas com o novo exit code e o novo refusal.

## Por que os "dois incidentes" do teste não são o mesmo bug hoje

`trailing_arm_x="1.0"` (a **string** entre aspas, exatamente como caiu em produção) já não derruba
mais nada: `arm_multiple_or_none` (T4.65) dobra qualquer valor ≤ 1× para `None` antes de
`ExitRules` ver o número — então esse valor literal é hoje um caso de **sucesso**
(`test_trailing_arm_x_null_passes`/`test_valid_string_decimal_passes` cobrem essa tolerância). O
segundo caso de teste do incidente reconstrói a mesma **forma** do erro (um decimal sem aspas) para
uma chave sem string prévia no documento: `trailing_arm_x=1.0` (sem aspas) vira `float` Python via
`json.loads`, e `decimal_of` recusa `float` **antes** de qualquer comparação de magnitude — então
`RuleSetSpec.from_params` já pega isso, com o texto exato do worker.

## Comandos rodados (saída real)

- `uv run pytest infra/scripts/tests/test_meme_rule_set_validate.py -q` → **5 passed in 0.84s**
- `uv run pytest infra/scripts/tests/test_meme_ops_mayhem.py infra/scripts/tests/test_meme_ops_scripts.py -q`
  → **19 passed in 0.94s** (fixture `ROWS` de `test_meme_ops_mayhem.py` precisou de um documento
  `params` completo — `gate_key`, `size_sol`, `max_sol_per_bet`, etc. — porque a validação nova
  carrega o documento inteiro, não só a chave mudada; sem isso `RuleSetSpec.from_params` recusava
  por `KeyError` nas chaves que a fixture nunca precisou antes)
- `uv run pytest infra/scripts/tests -q -m unit` → **136 passed, 175 deselected in 16.89s**
- `uv run pytest infra/scripts/tests -q` (suíte completa, roda de fundo) → concluiu com código 0
- `uv run ruff check <arquivos tocados>` → All checks passed!
- `uv run ruff format --check <arquivos tocados>` → 6 files already formatted (após `ruff check --fix`
  reordenar o import de `meme_rule_set_validate.py` e `ruff format` reformatar 3 arquivos)
- `uv run pyright <arquivos tocados>` → 0 errors, 0 warnings, 0 informations
- `uv run python infra/scripts/check_file_size.py` → scanned 980 files; 0 over budget, 0 grandfathered

## Arquivos

Criados: `infra/scripts/meme_rule_set_validate.py`,
`infra/scripts/tests/test_meme_rule_set_validate.py`,
`obsidian/11-KNOWLEDGE/KB-0140-set-param-valida-antes-de-gravar.md`,
`.claude/state/notes-T4.64.md`.
Modificados: `infra/scripts/meme_rule_set.py` (`--validate`, `WouldNotLoad`, docstring),
`infra/scripts/meme_rule_set_params.py` (chama `validate_set_param` em `set_param()`),
`infra/scripts/meme_rule_set_types.py` (`WouldNotLoad`), `docs/DATABASE.md` (§54, novo parágrafo),
`infra/scripts/tests/test_meme_ops_mayhem.py` (fixture `ROWS` com documento `params` completo).

## Pendências / ressalvas

- Não cobre uma gravação por caminho fora deste script (migração, `UPDATE` manual direto no banco);
  KB-0131 continua sendo a segunda camada ("todo decimal entre aspas").
- Não commitado (regra da sessão).

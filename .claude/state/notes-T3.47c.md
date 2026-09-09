# notes-T3.47c — `--deprecate`/`--supersede` passam a acrescentar ao `changelog`, nunca sobrescrever

**Data:** 2026-09-09T00:20:48Z (UTC) = 2026-09-08 21:20:48 (Brasília, UTC−3).
**Owner:** backend-specialist. **Origem:** `.claude/state/notes-T3.47b.md` CONCERN 3.
**Árvore:** local, sem commit (instrução explícita do brief). Nenhum arquivo `.env*` tocado. VPS não
tocada (não fazia parte do brief).

---

## STATUS

**DONE.**

## O PROBLEMA (CONCERN 3 da T3.47b)

`infra/scripts/activate_strategy_version.py --deprecate` (via
`hunter_strategy_worker/deprecate.py`) fazia `UPDATE strategy_versions SET changelog = :changelog`
— uma sobrescrita simples. Para uma variante derivada por `derive_variant.py`, a linhagem analisável
(`variante de v<n> | derived_from=v<n> | overrides=... | params_hash=...`) mora **só** nessa coluna
— nenhuma outra a guarda — e é o que `infra/scripts/obsidian_strategy_pages.py`
(`parse_parent_version`) lê para ligar a página da variante à do pai no Obsidian. Aposentar uma
variante com o veredito puro no changelog apagava essa linhagem para sempre.

`hunter_strategy_worker/supersede.py` tem o mesmo padrão na linha que ele aposenta (a origem, não a
sucessora nova): `UPDATE ... SET changelog = :changelog` também sobrescrevia, pelo mesmo motivo —
"um escritor que move uma versão congelada para fora de `active` não pode ser mais frouxo que o
outro" (a própria razão pela qual `--supersede` já espelha as duas recusas estruturais de
`--deprecate`, revisão T3.39b ALTA-2).

**Confirmado na T3.47b**: o operador teve que colar manualmente o changelog antigo inteiro dentro do
argumento `--changelog` do `--deprecate` para não perder a linhagem — o comando real rodado (`notes-
T3.47b.md` §2.3) mostra o texto `variante de v6 | derived_from=v6 | overrides=... | params_hash=...
| T3.47b: aposentada. Veredito da T3.47...` como o `--changelog` inteiro, copiado à mão do
changelog congelado antes de rodar. Isso é exatamente o comportamento perigoso que este fix elimina
— um operador que esqueça de colar a linhagem manualmente a perde.

## O FIX

Um helper novo, puro (sem I/O), em `hunter_strategy_worker/activation_db.py`:

```python
def append_deprecation_note(existing: str | None, note: str, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).isoformat()
    return f"{existing or ''}\n[deprecated {timestamp}] {note}"
```

Usado nos dois lugares que escrevem `changelog` numa linha que vai para `status = 'deprecated'`:

- `deprecate.py`: `{"changelog": append_deprecation_note(row.changelog, changelog), "id": row.id}`
  no lugar de `{"changelog": changelog, ...}`;
- `supersede.py`: mesma troca no `UPDATE` que aposenta a linha de origem (a `INSERT` da sucessora
  nova não muda — ela nunca tinha um changelog anterior para perder).

O valor anterior sobrevive **byte a byte**; a linha datada vai **depois**, então uma busca por
`derived_from=v<n>` (ou `succeeds v<n>`, ou `paper line of v<n>`) continua achando o padrão — as
regex de `obsidian_strategy_pages.py` usam `.search()`, não `.match()`, então a posição do prefixo
dentro da string não importa.

Isso segue o mesmo precedente já existente em `activate_derived.py::keep_lineage` (ativação de uma
linha derivada já preservava a linhagem, separando com `" | "` em vez de uma tag datada) — a lacuna
era só nos dois escritores que **aposentam**, não nos que **ativam**.

**Tag escolhida.** O brief pediu literalmente `[deprecated <UTC iso>]` para os dois casos
(`--deprecate` e o `--supersede` que aposenta a origem) — inclusive quando quem chama é
`--supersede`, porque a tag descreve a *transição de status* (`status = 'deprecated'` é o campo que
os dois escrevem), não o nome do comando. Segui isso ao pé da letra: nenhuma tag `[superseded ...]`
separada.

## ARQUIVOS

Modificados:

| arquivo | o quê |
|---|---|
| `services/strategy-worker/hunter_strategy_worker/activation_db.py` | `append_deprecation_note()` novo (+ `__all__`, import de `datetime`/`UTC`) |
| `services/strategy-worker/hunter_strategy_worker/deprecate.py` | `UPDATE` usa `append_deprecation_note(row.changelog, changelog)`; parágrafo no docstring do módulo explicando o comportamento novo |
| `services/strategy-worker/hunter_strategy_worker/supersede.py` | mesma troca no `UPDATE` que aposenta a linha de origem; parágrafo equivalente no docstring |
| `services/strategy-worker/tests/test_deprecate.py` | classe nova `TestDeprecatePreservesLineage` (1 teste, testcontainers) |
| `docs/ACTIVATION.md` | um parágrafo novo em §7b documentando o "acrescenta, nunca sobrescreve" |

Criados:

| arquivo | o quê |
|---|---|
| `services/strategy-worker/tests/test_append_deprecation_note.py` | 6 testes unitários (sem DB) do helper puro |
| `.claude/state/notes-T3.47c.md` | esta nota |

Nada em `derive_variant.py` ou `obsidian_strategy_pages.py` mudou — os dois já fazem a parte deles
corretamente (`.search()` em vez de `.match()`); o bug era só na escrita, não na leitura.

## TESTES E RESULTADOS REAIS

Unitário, sem banco (roda em ~1,4 s, não precisa de testcontainers):

```
$ uv run pytest services/strategy-worker/tests/test_append_deprecation_note.py -q
......                                                                   [100%]
6 passed in 1.39s
```

Integração, testcontainers, foreground, dentro de `timeout 290`:

```
$ timeout 290 uv run pytest services/strategy-worker/tests/test_deprecate.py -q
..............                                                           [100%]
14 passed in 52.65s
```
(13 testes que já existiam + o 1 novo — nenhum dos 13 quebrou: as asserções que checam substring do
veredito no `changelog`, ex. `"K1" in (row.changelog or "")`, continuam válidas porque o veredito
ainda aparece no changelog final, só que depois do prefixo e da tag, nunca sozinho.)

```
$ timeout 290 uv run pytest services/strategy-worker/tests/test_supersede.py -q
............                                                             [100%]
12 passed in 45.88s
```
(os 12 testes de `--supersede` também não quebraram, pelo mesmo motivo — nenhum deles supunha
`changelog` vazio antes de aposentar a origem.)

Lint/tipos/tamanho nos arquivos tocados:

```
$ uv run ruff check services/strategy-worker/hunter_strategy_worker/activation_db.py services/strategy-worker/hunter_strategy_worker/deprecate.py services/strategy-worker/hunter_strategy_worker/supersede.py services/strategy-worker/tests/test_deprecate.py services/strategy-worker/tests/test_append_deprecation_note.py
All checks passed!

$ uv run ruff format --check <os mesmos 5 arquivos>
5 files already formatted

$ uv run pyright <os mesmos 5 arquivos>
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 579 files; 0 over budget, 0 grandfathered
```

## DECISÃO SOBRE OS ARQUIVOS DE TESTE NOMEADOS NO BRIEF

O brief citou `test_activation.py`/`test_activate_derived_guard.py` como candidatos condicionais
("se cobrirem `--deprecate` com testcontainers, estenda UM deles"). Conferi os dois: **nenhum dos
dois cobre `--deprecate`** (`grep deprecate` = 0 ocorrências nos dois). Quem cobre é
`services/strategy-worker/tests/test_deprecate.py`, o arquivo de integração dedicado a esse modo —
é nele que estendi (1 classe, 1 teste), e é ele que rodei sozinho dentro do `timeout 290`, como o
brief pediu para "um deles". Sinalizando a divergência de nome para não parecer que ignorei a
instrução: os dois arquivos citados existem mas não são o alvo certo; `test_deprecate.py` é.

## CONCERNS

Nenhum. O fix é mínimo (uma função pura + duas trocas de uma linha), segue precedente já existente
no código (`activate_derived.py::keep_lineage`), e os testes de regressão (`test_deprecate.py`,
`test_supersede.py`) confirmam que nada que dependia do comportamento antigo quebrou.

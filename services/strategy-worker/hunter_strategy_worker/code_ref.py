"""The code digest that freezes one strategy **version** — not the whole tree.

SHADOW-LAB.md §1 freezes ``code_ref`` at the first activation: the version's
provenance has to name the code that produced its decisions. The first
implementation hashed every ``.py`` under ``hunter_core/strategies`` and demanded
exact equality, which coupled every activated version to every other file in the
package. Adding ``momentum_v2.py`` — or a comment in a module a version never
imports — changed the digest, ``load_active_versions`` skipped every frozen
version, and the Lab went silent behind a green ``/ready``
(risk-engine-guardian, S2 review, MUST-FIX 1).

The digest is now **per version**: the strategy's own module plus the transitive
closure of the sibling modules it actually imports, derived by reading the
imports (``ast``) instead of from a hand-written list that would drift the first
time a calculator moved. ``momentum_v1`` therefore covers ``aggregate``,
``base``, ``canonical``, ``envelope``, ``indicators``, ``numeric`` and
``schema`` — and not ``volume_anomaly_v1`` or ``registry``.

Two declared limits, both erring towards "the digest changes when the code
changes", never the other way round:

- **the closure stops at ``hunter_core.strategies``.** ``hunter_core.domain``
  (``to_money``, ``align_open_time``) is numerically load-bearing too, and Astra
  argued for every reachable ``hunter_core`` module. It is not included because
  ``hunter_core/domain/enums.py`` is edited by unrelated work every week
  (T2.1/T2.2 are editing it right now): a digest that spans it would re-freeze
  every version out of existence on the next unrelated enum, which is precisely
  the failure being fixed. Recorded as a divergence in ``notes-S2.md`` §15;
- **``__init__.py`` is excluded.** It is a re-export façade that imports both
  strategies and the registry, so following it would restore the tree-wide
  coupling. No evaluation path reads it: the worker resolves strategies through
  ``hunter_core.strategies.registry``.

The same function and the same directory serve the ops script and the worker —
one resolution, ``Path(hunter_core.strategies.__file__).parent``, so dev box and
image cannot disagree.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

import hunter_core.strategies as _strategies_pkg

if TYPE_CHECKING:
    from hunter_core.strategies.base import Strategy

PACKAGE = "hunter_core.strategies"
STRATEGIES_DIR = Path(_strategies_pkg.__file__).parent
"""Where the frozen strategy code lives *in this process*, resolved from the
installed package: the same directory in dev, in tests and in the image."""

CODE_REF_RE = re.compile(r"hunter_core\.strategies(\.[A-Za-z_][A-Za-z0-9_]*)?@sha256:[0-9a-f]{64}")
"""What a frozen ``code_ref`` looks like. The optional module part accepts the
superseded tree-wide spelling too, so a legacy row is reported as a *mismatch*
(the code moved on) rather than as "never frozen" (nobody ever wrote it)."""

__all__ = [
    "CODE_REF_RE",
    "PACKAGE",
    "STRATEGIES_DIR",
    "UnsupportedImport",
    "code_ref_module",
    "is_code_ref",
    "module_closure",
    "strategy_module",
    "version_code_ref",
]

_DYNAMIC = ("import_module", "__import__")


class UnsupportedImport(RuntimeError):
    """An import inside the closure that the digest cannot follow.

    Refusing is the whole point (Astra, S2 fixes diff review, HIGH a). Dropping
    such an import — a subpackage, a re-export through ``__init__``, a dynamic
    ``importlib.import_module`` — would leave the version with a digest that
    stays the same while the code it executes changes, which is the one
    direction the freeze must never fail in. There is nothing like this in
    ``hunter_core.strategies`` today; the day someone writes one, the ops script
    refuses to activate rather than freeze a claim it cannot back.
    """


def is_code_ref(value: str | None) -> bool:
    """Whether ``value`` is a frozen digest at all (either spelling)."""
    return value is not None and CODE_REF_RE.fullmatch(value) is not None


def code_ref_module(value: str | None) -> str | None:
    """The module a ``code_ref`` names, or ``None`` for the tree-wide spelling."""
    if not is_code_ref(value):
        return None
    assert value is not None
    head = value.split("@", 1)[0]
    return head[len(PACKAGE) + 1 :] if head != PACKAGE else None


def strategy_module(strategy: Strategy) -> str:
    """The module a registered strategy is implemented in, without the package.

    ``MOMENTUM_V1`` lives in ``hunter_core.strategies.momentum_v1``, so this is
    ``"momentum_v1"`` — the name that goes into its ``code_ref`` and the name a
    superseded version row is resolved back to code by.
    """
    return type(strategy).__module__.rsplit(".", 1)[-1]


def _sibling(name: str, path: Path, strategies_dir: Path) -> str:
    """One dotted name under the package, resolved to a sibling module file."""
    if "." in name:
        raise UnsupportedImport(
            f"{path.name} imports {PACKAGE}.{name}: the digest covers flat sibling "
            "modules only, and a subpackage would silently stay outside it"
        )
    if not (strategies_dir / f"{name}.py").is_file():
        raise UnsupportedImport(
            f"{path.name} imports {name!r} from {PACKAGE}: it is not a sibling module, so it "
            "is re-exported through __init__, which the digest deliberately does not cover"
        )
    return name


def _sibling_imports(source: str, path: Path, strategies_dir: Path) -> set[str]:
    """Every ``hunter_core.strategies`` module ``source`` imports, by name.

    Refuses anything it cannot resolve to exactly one sibling module file. See
    :class:`UnsupportedImport` for why silence is not an option here.
    """
    found: set[str] = set()
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.update(_from_import(node, path, strategies_dir))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE:
                    raise UnsupportedImport(
                        f"{path.name} imports {PACKAGE} itself, which executes __init__ and "
                        "pulls in every strategy; import the sibling module instead"
                    )
                if alias.name.startswith(f"{PACKAGE}."):
                    found.add(_sibling(alias.name[len(PACKAGE) + 1 :], path, strategies_dir))
        elif isinstance(node, ast.Call):
            _refuse_dynamic(node, path)
    return found


def _from_import(node: ast.ImportFrom, path: Path, strategies_dir: Path) -> set[str]:
    """``from … import …`` — absolute under the package, or relative inside it."""
    if node.level:  # ``from . import x`` / ``from .numeric import X``
        if node.module:
            return {_sibling(node.module, path, strategies_dir)}
        return {_sibling(alias.name, path, strategies_dir) for alias in node.names}
    module = node.module or ""
    if module == PACKAGE:
        return {_sibling(alias.name, path, strategies_dir) for alias in node.names}
    if module.startswith(f"{PACKAGE}."):
        return {_sibling(module[len(PACKAGE) + 1 :], path, strategies_dir)}
    return set()


def _refuse_dynamic(node: ast.Call, path: Path) -> None:
    """A runtime import hides the dependency from the AST, so it is refused."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name in _DYNAMIC:
        raise UnsupportedImport(
            f"{path.name} calls {name}(): a dynamic import is invisible to the digest, "
            "so the frozen code_ref would prove nothing about what runs"
        )


def module_closure(module: str, strategies_dir: Path = STRATEGIES_DIR) -> tuple[str, ...]:
    """``module`` plus every sibling it transitively imports, sorted.

    The entry module must exist, and its absence is a refusal rather than a
    digest over nothing; so is any import the closure cannot follow.
    """
    entry = strategies_dir / f"{module}.py"
    if not entry.is_file():
        raise FileNotFoundError(f"{entry} does not exist: {module} is not a strategy module")
    seen: set[str] = set()
    queue = [module]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = strategies_dir / f"{name}.py"
        queue.extend(
            _sibling_imports(path.read_text(encoding="utf-8"), path, strategies_dir) - seen
        )
    return tuple(sorted(seen))


def version_code_ref(module: str, strategies_dir: Path = STRATEGIES_DIR) -> str:
    """``hunter_core.strategies.<module>@sha256:<digest>`` for one version.

    Both the module *names* and their *bytes* go into the hash: moving a
    calculator to another module changes the experiment's code even when the
    bytes are identical, and a version already collecting evidence must not
    silently accept that.
    """
    digest = hashlib.sha256()
    for name in module_closure(module, strategies_dir):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update((strategies_dir / f"{name}.py").read_bytes())
        digest.update(b"\0")
    return f"{PACKAGE}.{module}@sha256:{digest.hexdigest()}"

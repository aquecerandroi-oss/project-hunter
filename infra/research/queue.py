"""A fila de hipóteses: um arquivo Markdown que qualquer pessoa edita, e o seu carregador.

A fila vive em `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md`. Um bloco por hipótese:

```markdown
## H-042 — Nome curto da ideia

- **origem:** de onde veio (nota, estudo, conversa)
- **variável:** a variável candidata e a direção
- **população:** que linhas entram, e o que as exclui
- **previsão:** o que afirmo, com sinal e tamanho
- **refutação:** o que me faz abandonar
- **status:** aberta | em curso | concluída | arquivada
```

O carregador é deliberadamente rígido: campo em falta é erro, status fora do vocabulário
é erro. Uma fila que aceita bloco pela metade vira uma lista de desejos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2] / "obsidian" / "11-KNOWLEDGE" / "Fila de Hipoteses.md"
)

STATUSES = ("aberta", "em curso", "concluída", "arquivada")
FIELDS = ("origem", "variavel", "populacao", "previsao", "refutacao", "status")

_HEADING = re.compile(r"^##\s+(?P<id>\S+)\s+—\s+(?P<name>.+?)\s*$")
_FIELD = re.compile(r"^-\s+\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.+?)\s*$")


class QueueFormatError(ValueError):
    """A fila tem um bloco que o moinho não consegue ler."""


@dataclass(frozen=True)
class QueuedHypothesis:
    """Uma ideia na fila, ainda sem spec — o spec é escrito por quem a for moer."""

    id: str
    name: str
    origin: str
    variable: str
    population: str
    prediction: str
    refutation: str
    status: str


def _fold(text: str) -> str:
    """Chave sem acento e em minúsculas: 'Variável' e 'variavel' são o mesmo campo."""
    stripped = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def parse_queue(text: str) -> list[QueuedHypothesis]:
    """Lê o Markdown da fila. Levanta `QueueFormatError` no primeiro bloco defeituoso."""
    blocks: list[tuple[str, str, dict[str, str]]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = {}
            blocks.append((heading["id"], heading["name"].strip(), current))
            continue
        field = _FIELD.match(line)
        if field and current is not None:
            current[_fold(field["key"])] = field["value"].strip()
    out: list[QueuedHypothesis] = []
    for ident, name, fields in blocks:
        missing = [f for f in FIELDS if not fields.get(f)]
        if missing:
            raise QueueFormatError(f"{ident}: faltam campos {missing}")
        status = fields["status"]
        if status not in STATUSES:
            raise QueueFormatError(f"{ident}: status {status!r} fora de {list(STATUSES)}")
        out.append(
            QueuedHypothesis(
                id=ident,
                name=name,
                origin=fields["origem"],
                variable=fields["variavel"],
                population=fields["populacao"],
                prediction=fields["previsao"],
                refutation=fields["refutacao"],
                status=status,
            )
        )
    if not out:
        raise QueueFormatError("fila vazia: nenhum bloco '## <id> — <nome>' encontrado")
    duplicates = {h.id for h in out if sum(1 for o in out if o.id == h.id) > 1}
    if duplicates:
        raise QueueFormatError(f"ids repetidos na fila: {sorted(duplicates)}")
    return out


def load_queue(path: Path = DEFAULT_PATH) -> list[QueuedHypothesis]:
    """Carrega a fila do disco (somente leitura; nunca escreve na base Obsidian)."""
    return parse_queue(path.read_text(encoding="utf-8"))


def open_hypotheses(path: Path = DEFAULT_PATH) -> list[QueuedHypothesis]:
    """As que ainda esperam a vez, na ordem em que estão escritas."""
    return [h for h in load_queue(path) if h.status == "aberta"]

"""A impressão digital do spec J da H-022 — imprime o sha256 de cada arquivo e o combinado.

    uv run python -m infra.research.exp_m26.impressao_digital

O combinado vai para a página EXP-M26 **antes do seed** (quem registra é o orquestrador) e
`ler.py --impressao` recusa ler se não bater. Cobre o texto do protocolo, o SQL do export, os
módulos do J e os do moinho que eles importam (o teste prova o fecho). Os bytes são lidos
com `\\r\\n` → `\\n`, para o Windows e a VPS darem o mesmo número.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

_J = "infra/research/exp_m26/"
ARQUIVOS: tuple[str, ...] = (
    _J + "protocolo_h022.txt",
    _J + "export_h022.sql",
    _J + "__init__.py",
    _J + "calendario.py",
    _J + "carga.py",
    _J + "censura.py",
    _J + "classes.py",
    _J + "constantes.py",
    _J + "contabil.py",
    _J + "estado_token.py",
    _J + "estimador.py",
    _J + "impressao_digital.py",
    _J + "ler.py",
    _J + "leitura.py",
    _J + "modelo.py",
    _J + "pacote.py",
    _J + "robustez.py",
    _J + "veredito.py",
    "infra/research/__init__.py",
    "infra/research/guards.py",
    "infra/research/resampling.py",
    "infra/research/results.py",
    "infra/research/spec.py",
    "infra/research/stats.py",
    "infra/research/stats_core.py",
    "infra/research/verdict.py",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def por_arquivo(raiz: Path = RAIZ, arquivos: tuple[str, ...] = ARQUIVOS) -> list[tuple[str, str]]:
    return [(a, _sha(raiz / a)) for a in sorted(arquivos)]


def impressao(raiz: Path = RAIZ, arquivos: tuple[str, ...] = ARQUIVOS) -> str:
    linhas = "".join(f"{a}\t{h}\n" for a, h in por_arquivo(raiz, arquivos))
    return hashlib.sha256(linhas.encode("utf-8")).hexdigest()


def main() -> int:
    for a, h in por_arquivo():
        sys.stdout.write(f"{h}  {a}\n")
    sys.stdout.write(f"\nH-022 / EXP-M26 J - impressao digital (sha256): {impressao()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""A leitura única da H-022, pela linha de comando.

    uv run python -m infra.research.exp_m26.ler --export h022.jsonl \\
        --impressao <sha256 registrado na página EXP-M26 antes do seed>

O export (`export_h022.sql`) é o retrato em L = corte + 2 h e tem de ser tirado em
[L, L + 1 h]; o seu `exportado_em` é o único relógio da leitura (o J não lê relógio), então
rodar este comando de novo sobre o mesmo arquivo dá sempre o mesmo relatório. A leitura é
**um** export: o seu sha256 sai no relatório e vai para a página EXP-M26 logo depois de
exportar (fatos com instante ≤ L julgados com o conhecimento desse export; outro export é
outra leitura). Recusa (código 2) se a impressão digital do spec mudou desde o registro. As
réplicas são as 10 000 congeladas: não há opção para mudá-las.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

from infra.research.exp_m26.carga import ler_export
from infra.research.exp_m26.constantes import REPS
from infra.research.exp_m26.impressao_digital import impressao
from infra.research.exp_m26.leitura import ler_h022


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Leitura única da H-022 (EXP-M26 J).")
    ap.add_argument("--export", required=True, type=Path)
    ap.add_argument("--impressao", required=True)
    args = ap.parse_args(argv)
    atual = impressao()
    if args.impressao != atual:
        sys.stderr.write(
            f"a impressão digital registrada ({args.impressao}) não bate com o spec atual "
            f"({atual}): o J mudou depois do registro — isso é versão nova e hipótese nova.\n"
        )
        return 2
    bruto = args.export.read_bytes()
    entrada = ler_export(bruto.decode("utf-8").splitlines())
    rel = ler_h022(entrada, reps=REPS)
    rel["impressao_digital"] = atual
    rel["export_sha256"] = hashlib.sha256(bruto).hexdigest()
    rel["reps"] = REPS
    rel["ambiente"] = {"python": platform.python_version(), "numpy": np.__version__}
    sys.stdout.write(json.dumps(rel, ensure_ascii=False, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

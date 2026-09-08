"""T3.40 — roda o replay AUDITADO da imagem, sem tocar em arquivo nenhum dela.

Motivo: `main @ c78a416` (a imagem publicada) tem
`replay/run.py` importando `hunter_strategy_worker.replay.stress`, modulo que
nunca foi commitado (T3.36 em voo, arquivo untracked). Logo
`python -m hunter_strategy_worker.replay.run` levanta ModuleNotFoundError na VPS.

Este atalho NAO copia, NAO escreve e NAO altera codigo dentro do container:
registra um stub em sys.modules para o unico nome que falta e executa o run.py
da imagem, byte a byte, por runpy (alter_sys=True, para que o ProcessPoolExecutor
com start method `fork` continue resolvendo `__main__._worker`).

`run_cli` do stub so seria chamado sob `--stress` (run.py linha 299, dentro de
`if args.stress:`), bandeira que este atalho nunca passa — e que aqui recusa alto.
"""

import runpy
import sys
import types

_MISSING = "hunter_strategy_worker.replay.stress"


def _refuse(*_args: object, **_kwargs: object) -> int:
    raise SystemExit(f"{_MISSING} nao existe nesta imagem: --stress indisponivel (T3.40)")


if _MISSING not in sys.modules:
    stub = types.ModuleType(_MISSING)
    stub.run_cli = _refuse  # type: ignore[attr-defined]
    sys.modules[_MISSING] = stub

if "--stress" in sys.argv:
    raise SystemExit("este atalho nao roda --stress")

runpy.run_module("hunter_strategy_worker.replay.run", run_name="__main__", alter_sys=True)

"""Braço de robustez: a mesma medição com as definições da KB-0080 §7 — T3.55b.

Mesma exportação, mesma baseline pareada, mesmo bootstrap de blocos por dia,
mesma correção de Holm. Só as constantes e a régua de contexto mudam. Família
declarada: 18 rótulos × 2 timeframes × 3 horizontes = 108 testes.
"""

from __future__ import annotations

import sys

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import estatistica  # noqa: E402
import medir  # noqa: E402
import padroes_kb0080 as kb  # noqa: E402

if __name__ == "__main__":
    if "--so-estatistica" not in sys.argv:
        medir.main(varrer_fn=kb.varrer, sufixo="-a")
    estatistica.main(sufixo="-a", nomes=kb.NOMES, sinal=kb.SINAL)

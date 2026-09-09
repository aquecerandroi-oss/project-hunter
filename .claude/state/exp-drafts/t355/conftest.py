"""Empurra os pacotes do monorepo para o ``sys.path`` deste diretório de rascunho.

`.claude/state/exp-drafts/t355/` não é um pacote instalado — é pesquisa. O import
aqui é explícito para que ninguém confunda estes arquivos com produção.
"""

from __future__ import annotations

import sys

for pacote in (
    "C:/dev/project-hunter/packages/core",
    "C:/dev/project-hunter/packages/indicators",
    "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos",
    "C:/dev/project-hunter/.claude/state/exp-drafts/t355",
):
    if pacote not in sys.path:
        sys.path.insert(0, pacote)

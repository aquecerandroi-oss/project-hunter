"""Insere a emenda (emenda1.md) no bloco H-033 da Fila, logo depois da linha de registro do R90. Só toca o bloco H-033."""

from pathlib import Path

FILA = Path("C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md")
ANCHOR = "Cópia congelada em `.claude/state/r90/prereg_frozen.md`. R90\n"
text = FILA.read_text(encoding="utf-8")
assert text.count(ANCHOR) == 1, "âncora do registro do R90 não é única"
emenda = Path(__file__).with_name("emenda1.md").read_text(encoding="utf-8")
assert emenda.endswith("\n") and emenda not in text
FILA.write_text(text.replace(ANCHOR, ANCHOR + emenda), encoding="utf-8", newline="\n")
print("ok")

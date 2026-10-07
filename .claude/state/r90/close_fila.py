"""Fecha o bloco H-033 da Fila: status → concluída + veredito do R90. Só toca o bloco H-033; preserva o fim de linha."""

from pathlib import Path

FILA = Path("C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md")
raw = FILA.read_bytes().decode("utf-8")
nl = "\r\n" if "\r\n" in raw else "\n"
head = "## H-033 — Open interest em nível"
i = raw.index(head)
block, rest = raw[:i], raw[i:]
nxt = rest.find(nl + "## ", 1)
mine, after = (rest, "") if nxt < 0 else (rest[:nxt], rest[nxt:])
old = "- **status:** em curso"
assert mine.count(old) == 1, "status do H-033 não é único"
verdict = Path(__file__).with_name("veredito_fila.md").read_text(encoding="utf-8").strip("\n").replace("\n", nl)
mine = mine.replace(old, "- **status:** concluída" + nl + verdict)
FILA.write_bytes((block + mine + after).encode("utf-8"))
print("ok", repr(nl))

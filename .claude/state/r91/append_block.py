"""Acrescenta um bloco ao fim da Fila (só acrescenta; recusa se o id já existir)."""
import pathlib
import sys

fila = pathlib.Path("obsidian/11-KNOWLEDGE/Fila de Hipoteses.md")
block = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
head = block.splitlines()[0]
txt = fila.read_text(encoding="utf-8")
assert head not in txt, "bloco já presente"
if not txt.endswith("\n"):
    txt += "\n"
fila.write_text(txt + "\n" + block, encoding="utf-8")
print("ok: linhas antes", len(txt.splitlines()))

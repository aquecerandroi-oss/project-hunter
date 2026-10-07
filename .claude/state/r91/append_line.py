"""Acrescenta linhas logo depois do bloco H-034 (fim do bloco = próxima '## ' ou fim do arquivo)."""
import pathlib
import sys

fila = pathlib.Path("obsidian/11-KNOWLEDGE/Fila de Hipoteses.md")
add = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").rstrip("\n").split("\n")
lines = fila.read_text(encoding="utf-8").split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("## H-034 "))
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
while end > start and lines[end - 1].strip() == "":
    end -= 1
assert add[0] not in lines, "já presente"
lines[end:end] = add
fila.write_text("\n".join(lines), encoding="utf-8")
print("inserido na linha", end + 1)

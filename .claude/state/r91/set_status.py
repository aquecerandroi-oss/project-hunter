"""Troca só a linha de status do bloco H-034 (em curso -> concluída)."""
import pathlib

fila = pathlib.Path("obsidian/11-KNOWLEDGE/Fila de Hipoteses.md")
lines = fila.read_text(encoding="utf-8").split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("## H-034 "))
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
idx = [i for i in range(start, end) if lines[i] == "- **status:** em curso"]
assert len(idx) == 1, idx
lines[idx[0]] = "- **status:** concluída"
fila.write_text("\n".join(lines), encoding="utf-8")
print("status trocado na linha", idx[0] + 1)

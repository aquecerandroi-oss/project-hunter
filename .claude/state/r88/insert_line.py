"""Insere uma linha no bloco H-031 da Fila logo antes da linha '- **status:**' do bloco (só o bloco H-031)."""
import sys, datetime
path = "obsidian/11-KNOWLEDGE/Fila de Hipoteses.md"
new = open(sys.argv[1], encoding="utf-8").read().rstrip("\n")
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M")
new = new.replace("__HHMM__", stamp)
lines = open(path, encoding="utf-8").read().split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("## H-031 "))
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
st = next(i for i in range(start, end) if lines[i].startswith("- **status:**"))
lines.insert(st, new)
open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("inserido antes da linha", st + 1, "hora", stamp)

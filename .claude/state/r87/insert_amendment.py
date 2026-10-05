"""Insere a emenda datada da H-028 na Fila, antes do `status`, sem tocar no texto congelado."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
fila = ROOT / "obsidian" / "11-KNOWLEDGE" / "Fila de Hipoteses.md"
s = fila.read_text(encoding="utf-8")
am = (HERE / "amendment.txt").read_text(encoding="utf-8").rstrip("\n")
anchor = "de setembro/2020 (fora de qualquer cálculo)\n- **status:** em curso"
assert s.count(anchor) == 1, s.count(anchor)
s = s.replace(anchor, "de setembro/2020 (fora de qualquer cálculo)\n" + am + "\n- **status:** em curso")
fila.write_text(s, encoding="utf-8")
frozen = (HERE / "prereg_frozen.md").read_text(encoding="utf-8")
(HERE / "prereg_with_amendment.md").write_text(frozen.replace("\n- **status:** em curso", "\n" + am + "\n- **status:** em curso"), encoding="utf-8")
print("emenda inserida")

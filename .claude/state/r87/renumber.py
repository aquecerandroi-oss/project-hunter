from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
fila = ROOT / "obsidian" / "11-KNOWLEDGE" / "Fila de Hipoteses.md"
s = fila.read_text(encoding="utf-8")
old_h = "## H-028 — Carry de funding protegido"
assert s.count(old_h) == 1
s = s.replace(old_h, "## H-029 — Carry de funding protegido")
s = s.replace("[[H-028-carry-prereg]]", "[[H-029-carry-prereg]]")
note = ("- **identificador (05/10/2026 15:58Z, antes de qualquer cálculo):** registrado às 15:31Z como H-028; trocado para "
        "**H-029** porque o rascunho da coorte prospectiva do B da H-026 (congelado em 01/10, fora da Fila, `.claude/state/h026b-forward/`) "
        "já usa H-028 em [[H-028-forward-prereg]], [[KB-0169-fibonacci-e-lta-diaria-no-dado]] e [[Proximas Hipoteses]]; só o número mudou "
        "(o texto congelado em `.claude/state/r87/prereg_frozen.md` diz H-028)\n")
anchor = "- **emenda (05/10/2026 15:40Z, depois da revisão da Astra [[H-029-carry-prereg]]"
assert s.count(anchor) == 1
s = s.replace(anchor, note + anchor)
fila.write_text(s, encoding="utf-8")
print("renumerado")

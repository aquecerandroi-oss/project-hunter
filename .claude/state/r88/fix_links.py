from pathlib import Path
g = Path("obsidian/03-TRADING/Meme/Perdas/golpe_do_criador.md")
raw = g.read_bytes().decode("utf-8"); crlf = "\r\n" in raw; t = raw.replace("\r\n", "\n")
start = t.index("## H-031 (07/10/2026)\n\n")
end = t.index("## Relacionado", start)
t = t[:start] + t[end:]
anchor_line = next(l for l in t.split("\n") if l.startswith("| [[Fila de Hipoteses#H-020"))
row = ("| [[Fila de Hipoteses#H-031 — Concentração do maior comprador no preenchimento (`top_buyer_share`) como aviso de golpe\|H-031]] | "
       "excluir as entradas em que uma carteira concentra o SOL da curva (fatia do maior comprador na decisão) | **NÃO CONFIRMA** (R88, 07/10) — "
       "no papel, a concentração alta associa-se a **2,11×** mais saídas `creator_dump`, mas o retorno não piora (D_adj −0,0023 [−0,043, +0,037]) "
       "([[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]]) |")
t = t.replace(anchor_line, anchor_line + "\n" + row, 1)
g.write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
k = Path("obsidian/11-KNOWLEDGE/KB-0153-o-maior-comprador-nao-estava-no-arquivo.md")
raw = k.read_bytes().decode("utf-8")
k.write_bytes(raw.replace("aviso de golpe\|H-031]] usou", "aviso de golpe|H-031]] usou").encode("utf-8"))
print("ok")

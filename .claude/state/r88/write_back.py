"""R88 — escrita de volta nas notas do Obsidian (inserções cirúrgicas, sem reescrever o resto)."""

from pathlib import Path

ROOT = Path("obsidian")
H031 = "Fila de Hipoteses#H-031 — Concentração do maior comprador no preenchimento (`top_buyer_share`) como aviso de golpe"
KB = "KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno"


def edit(rel: str, fn) -> None:
    p = ROOT / rel
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    new = fn(text)
    assert new != text, rel
    if crlf:
        new = new.replace("\n", "\r\n")
    p.write_bytes(new.encode("utf-8"))
    print("ok", rel)


def astra_index(t: str) -> str:
    anchor = next(line for line in t.split("\n") if line.startswith("- [[H-029-carry-resultado]]"))
    add = (
        "- [[H-031-prereg]] — R88, pré-registro da fatia do maior comprador (`pedigree_e2b` e `decision_tape`) como aviso de golpe: "
        "B admissível como extensão, não equivalente a A; 5 must-fix aceitos numa emenda datada antes de qualquer desfecho (KB-0188) (07/10)\n"
        "- [[H-031-resultado]] — R88, resultado: H-031, A e B NÃO CONFIRMA; sha256 e as duas contas do empate de A reproduzidos por ela; "
        "4 must-fix de descrição absorvidos sem mudar rótulo (KB-0188) (07/10)"
    )
    return t.replace(anchor, anchor + "\n" + add, 1)


def kb_index(t: str) -> str:
    lines = t.split("\n")
    idx = max(i for i, line in enumerate(lines) if line.startswith("| [[KB-01"))
    row = (
        f"| [[{KB}]] | H-031: excluir a concentração do maior comprador "
        "não melhora o retorno do papel meme — `decision_tape` (1 647 apostas, limiar 0,35) D_adj −0,0023 [−0,043; +0,037]; "
        "`pedigree_e2b` truncado < 0,35 (192) +0,086 [−0,075; +0,248]; `fill_seconds` sempre nulo; concentração alta associa-se a "
        "2,11× mais saídas `creator_dump` sem pior retorno; NÃO CONFIRMA | R88 (07/10/2026) | medição própria (papel) | H-031 |"
    )
    lines.insert(idx + 1, row)
    return "\n".join(lines)


def proximas(t: str) -> str:
    old = "nunca como o **preenchimento** em si |"
    i = t.index("| `top_buyer_share` / `fill_seconds` |")
    j = t.index(old, i) + len(old) - 1
    add = (
        f" → **testada na [[{H031}\\|H-031]] (R88, 07/10): NÃO CONFIRMA** — `top_buyer_share` é truncado < 0,35 pela própria "
        f"E2-b e `fill_seconds` é sempre nulo na proposta; a fatia do `decision_tape` não separa o retorno ([[{KB}]]) "
    )
    return t[:j] + add + t[j:]


def dicionario(t: str) -> str:
    old_row = "| E2b (R57/60/61 — copiar carteiras) | descartado (R57/KB-0136) |"
    assert old_row in t
    t = t.replace(
        old_row,
        f"| E2b (R57/60/61 — copiar carteiras); **H-031 (R88)** | NÃO CONFIRMA na H-031 — truncada < 0,35, `fill_seconds` sempre nulo ([[{KB}]]) |",
        1,
    )
    old7 = (
        "7. `top_buyer_share`/`fill_seconds` (meme, `pedigree_e2b`) — a família E2-b morreu como \"seguir carteira\", "
        "nunca como o **preenchimento** em si."
    )
    assert old7 in t
    return t.replace(old7, old7 + f" **Testada em 07/10 (H-031, R88): NÃO CONFIRMA** ([[{KB}]]).", 1)


def mapa(t: str) -> str:
    lines = t.split("\n")
    i = next(k for k, line in enumerate(lines) if line.startswith("| [[Fila de Hipoteses#H-020"))
    row = (
        f"| [[{H031}\\|H-031]] | excluir a concentração do maior comprador (fatia do SOL da curva) | **nao_confirma** | "
        f"`decision_tape` D_adj=−0,0023, IC [−0,043,+0,037]; `creator_dump` 2,11× no braço alto sem pior retorno ([[{KB}]]) |"
    )
    lines.insert(i + 1, row)
    return "\n".join(lines)


def exp_m9(t: str) -> str:
    anchor = "_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_"
    add = (
        "\n\n### 2026-10-07 — R88 / H-031 (pesquisa retrospectiva, não é o fechamento da régua)\n\n"
        "A H-031 ([[Fila de Hipoteses]]) mediu a fatia do maior comprador **dentro** das apostas que esta E2-b deixou passar: "
        "212 apostas `flow_v2/6`–`/10` com o bloco `pedigree_e2b`, todas com `top_buyer_share` **< 0,35** (o critério recusa ≥ 0,35 "
        "antes de a proposta nascer) e `fill_seconds` **nulo nas 228 propostas** (P2 confirmada no extremo: a perna do tempo nunca "
        "falou numa proposta). No tercil superior (> 0,1222) contra o resto, D ajustado por conjunto **+0,086**, IC [−0,075; +0,248], "
        "pico, metades de sinal oposto — NÃO CONFIRMA, e a estimativa depende de uma mint no limiar. Medida no instrumento da "
        "decisão (`decision_tape`, onde existe fatia ≥ 0,35), excluir ≥ 0,35 **não** melhora o retorno do papel (D −0,0023, "
        "IC [−0,043; +0,037]). Isto não avalia P1/P3/P5 nem a régua desta página (≥ 100 apostas e 30 dias com contraste "
        f"marcadas × não marcadas). KB: [[{KB}]]."
    )
    assert anchor in t
    return t.replace(anchor, anchor + add, 1)


def golpe(t: str) -> str:
    marker = "## Relacionado"
    add = (
        f"## H-031 (07/10/2026)\n\nA fatia do maior comprador no instante da decisão foi testada como aviso desta classe "
        f"([[{H031}\\|H-031]], [[{KB}]]): no papel, a concentração alta associa-se a 2,11× mais saídas `creator_dump`, mas excluir "
        "essas entradas não melhora o retorno (NÃO CONFIRMA).\n\n"
    )
    if marker in t:
        return t.replace(marker, add + marker, 1)
    return t.rstrip("\n") + "\n\n" + add


def kb0153(t: str) -> str:
    marker = "## Relacionados"
    add = (
        f"**Reabertura parcial (07/10/2026):** a [[{H031}\\|H-031]] usou o maior comprador gravado em `reasons` pela fita da "
        "decisão (`0062`), em **fluxo líquido de SOL** — não a variável de **estoque** de tokens pedida acima, que continua não "
        f"testada. Resultado: NÃO CONFIRMA ([[{KB}]]).\n\n"
    )
    if marker in t:
        return t.replace(marker, add + marker, 1)
    return t.rstrip("\n") + "\n\n" + add


if __name__ == "__main__":
    edit("06-DECISIONS/Revisoes-Astra/Index.md", astra_index)
    edit("11-KNOWLEDGE/Index.md", kb_index)
    edit("11-KNOWLEDGE/Proximas Hipoteses.md", proximas)
    edit("11-KNOWLEDGE/Dicionario de Variaveis.md", dicionario)
    edit("11-KNOWLEDGE/Mapa de Estrategias.md", mapa)
    edit("05-EXPERIMENTS/EXP-M9-pedigree-e2b.md", exp_m9)
    edit("03-TRADING/Meme/Perdas/golpe_do_criador.md", golpe)
    edit("11-KNOWLEDGE/KB-0153-o-maior-comprador-nao-estava-no-arquivo.md", kb0153)

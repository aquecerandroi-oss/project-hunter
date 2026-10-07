"""R90 — escreve de volta o aprendizado da H-033 nas notas que a citam (links nos dois sentidos).
Cada edição: âncora única, inserção/troca local, fim de linha preservado, idempotente (recusa se já aplicada)."""

from pathlib import Path

O = Path("C:/dev/project-hunter/obsidian")
KB = "KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab"
H033 = ("[[Fila de Hipoteses#H-033 — Open interest em nível (lotação relativa à própria semana) como estado dos sinais "
        "de continuação do Lab de cripto\\|H-033]]")


def edit(rel: str, anchor: str, new: str, mode: str) -> None:
    p = O / rel
    raw = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    assert new not in text, f"já aplicado: {rel}"
    assert text.count(anchor) == 1, f"âncora não única em {rel}: {text.count(anchor)}"
    if mode == "after_line":
        i = text.index(anchor)
        j = text.index("\n", i) + 1
        text = text[:j] + new + "\n" + text[j:]
    elif mode == "replace":
        text = text.replace(anchor, new)
    p.write_bytes(text.replace("\n", nl).encode("utf-8"))
    print("ok", rel)


edit("11-KNOWLEDGE/Mapa de Estrategias.md", "| [[Fila de Hipoteses#H-029 — Carry de funding protegido",
     f"| {H033} | open interest relativo à mediana semanal (`open_interest_history`, folga de 15 min) como estado dos "
     "sinais de continuação do Lab, teste incremental conjunto com `distance_from_24h_low`, ATR% e retorno 4 h (análise "
     "**retrospectiva**, condicionada à folga) | **nao_confirma** (momentum não confirma; volume_anomaly limite de dado) | "
     "869 unidades da momentum v3: β +0,003 R/desvio, IC dia [−0,047; +0,059], mercado [−0,038; +0,035] — o +0,05 "
     f"previsto não fica excluído no IC de dia; grupo \"menos lotado\" −0,25 R ([[{KB}]]) |", "after_line")
edit("11-KNOWLEDGE/Mapa de Estrategias.md", "[[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] · [[Perdas/Index|Perdas]]",
     f"[[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] · [[{KB}]] · [[Perdas/Index|Perdas]]", "replace")
edit("11-KNOWLEDGE/Index.md", "| [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]]",
     f"| [[{KB}]] | H-033: open interest relativo à mediana semanal não separa os sinais da momentum do Lab — 869 "
     "unidades, β +0,003 R/desvio, IC dia [−0,047; +0,059] (não refuta o +0,05, não confirma nada), grupo \"menos "
     "lotado\" −0,25 R; `open_interest_history` guarda o bucket do início da rodada, não o instante da leitura "
     "(folga de 15 min; prova pós-commit só pelo `dispatched_at` do outbox, desde 26/09) |", "after_line")
edit("06-DECISIONS/Revisoes-Astra/Index.md", "- [[H-034-resultado]]",
     "- [[H-033-prereg]] — R90, pré-registro do OI em nível (relativo à própria semana) nos sinais do Lab: 5 must-fix "
     "aceitos numa emenda antes dos desfechos (folga como suposição + sensibilidades 30/60 min, janela inteira e prova "
     f"por `dispatched_at`, FE de dia com consequência fixada, falha fechada e regra global, exchange e unicidade) ({KB.split('-o')[0]}) (07/10)\n"
     "- [[H-033-resultado]] — R90, resultado: momentum NÃO CONFIRMA, volume_anomaly LIMITE DE DADO, global NÃO "
     "CONFIRMA; corrida, lista e réplica reproduzidas por ela; 5 must-fix (redação de FE dia +0,0501 e blocos 3 d "
     f"+0,0512 acima de +0,05; 4 de instrumento sem efeito nos números) ({KB.split('-o')[0]}) (07/10)", "after_line")
edit("11-KNOWLEDGE/Proximas Hipoteses.md",
     "| cripto | não se aplica — item 14 do [[Strategy Backlog]], nunca rodado |",
     f"| cripto | não se aplica — item 14 do [[Strategy Backlog]] → **testada na {H033} (R90, 07/10): NÃO CONFIRMA** "
     "(momentum, 869 unidades, β +0,003 R/desvio, IC dia [−0,047; +0,059]); a feature não existe, mas o dado cru sim "
     f"(`open_interest_history`, folga de 15 min) — [[{KB}]] |", "replace")
edit("11-KNOWLEDGE/Strategy Backlog.md",
     "em futuros tradicionais dos anos 1980 | ideia |",
     "em futuros tradicionais dos anos 1980 | testada: H-033 (R90, 07/10) **NÃO CONFIRMA** nos sinais da momentum do "
     f"Lab, como OI relativo à própria semana ([[{KB}]]); a leitura de profundidade × volatilidade não foi testada |",
     "replace")
edit("11-KNOWLEDGE/Dicionario de Variaveis.md",
     "2. `open_interest` **em nível** (não a variação) como profundidade — item 14 do [[Strategy Backlog]], nunca rodado.",
     "2. `open_interest` **em nível** (não a variação) como profundidade — item 14 do [[Strategy Backlog]] → **testada "
     "na H-033 (R90, 07/10) como OI relativo à mediana semanal: NÃO CONFIRMA** nos sinais da momentum do Lab "
     f"([[{KB}]]). Reconstruível de `open_interest_history` com folga de 15 min: o `ts` é o bucket do início da "
     "rodada de leitura, não o instante.", "replace")
edit("11-KNOWLEDGE/KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab.md",
     "[[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-0005-momentum-paper]]",
     "[[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-0005-momentum-paper]] · "
     f"[[{KB}]] (H-033 reusou este maquinário e a lição do FE de dia)", "replace")
edit("02-MARKET/Market Collector.md", "- **Bybit** — M1b, mesmo contrato.",
     "- **Instante da leitura de OI não é durável** (medido no R90, 07/10/2026): `open_interest_history.ts` é o piso de "
     "5 min do **início** da rodada (os mercados são lidos um a um por REST), e o número pode ter sido lido minutos "
     "depois — no outbox de 26/09 a 07/10 a maior distância bucket → inserção foi 325 s. O instante real (`payload.ts`) "
     "e a prova pós-commit (`dispatched_at` do relay; `created_at` é o `now()` da transação e não prova) só existem no "
     "`outbox_events`, retido ~11 dias. Gravar o instante da leitura na tabela fecharia isso para o ao vivo "
     f"(`hunter_strategy_worker/derivatives.py`) e para a pesquisa ([[{KB}]]).", "after_line")

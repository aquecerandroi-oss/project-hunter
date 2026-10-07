"""R91 — escreve o desfecho da H-034 em Próximas, Dicionário, Mapa e índices (substituição exata, uma vez cada)."""

import pathlib

K = pathlib.Path("obsidian/11-KNOWLEDGE")
FILA_H034 = "[[Fila de Hipoteses#H-034 — `holders_rising` e `progress_rising` isolados na hora da decisão (os dois \"subindo\" separam o retorno do papel?)\\|H-034]]"
KB = "[[KB-0190-os-dois-subindo-nao-separam-o-retorno]]"


def sub(path: pathlib.Path, old: str, new: str) -> None:
    txt = path.read_text(encoding="utf-8")
    assert txt.count(old) == 1, (path, txt.count(old), old[:60])
    path.write_text(txt.replace(old, new), encoding="utf-8")
    print("ok", path.name)


sub(K / "Proximas Hipoteses.md",
    "`comprou_no_topo`? — hoje só medidos **dentro** de `equilibrio` (H-013, que morreu por 1 caso: 1 de 587 decisões com `equilibrio = verdadeiro`) |",
    "`comprou_no_topo`? — hoje só medidos **dentro** de `equilibrio` (H-013, que morreu por 1 caso: 1 de 587 decisões com `equilibrio = verdadeiro`) → **testada na "
    + FILA_H034 + " (R91, 07/10): NÃO CONFIRMA nas duas** — holders subindo D_adj +0,027 [−0,030; +0,085] em 1 680 apostas de papel da porta `fluxo_e_holders`, braço verdadeiro perde em nível; progresso subindo +0,133 [−0,041; +0,315] em só 130 (o bit só varia nos `flow_v2/6`–`/9`); `comprou_no_topo` 1,19× quando holders não sobem (previa 1,5×); reais da `operator/5` +0,082 [−0,011; +0,173], descritivo (" + KB + ") |")

sub(K / "Dicionario de Variaveis.md",
    "| `progress_delta_60s`, `progress_rising` | `meme_features_15s` | variação/tendência do progresso em 60 s | T4.16 | — | compõe `equilibrio` | ver H-013 |",
    "| `progress_delta_60s`, `progress_rising` | `meme_features_15s` | variação/tendência do progresso em 60 s | T4.16 | — | compõe `equilibrio`; `progress_rising` isolado na H-034 (**nao_confirma**) | H-034: +0,133 [−0,041; +0,315], 130 apostas, só varia nos `flow_v2/6`–`/9` (" + KB + ") |")
sub(K / "Dicionario de Variaveis.md",
    "| `holders_rising`, `holders_prev` | `meme_features_15s` | tendência de holders | T4.16 | — | esgotada (R65 \"holders\") | — |",
    "| `holders_rising`, `holders_prev` | `meme_features_15s` | tendência de holders | T4.16 | — | R65 testou o **nível** de holders; a tendência isolada é a H-034 (**nao_confirma**) | H-034: +0,027 [−0,030; +0,085], 1 680 apostas (" + KB + ") |")
sub(K / "Dicionario de Variaveis.md",
    "9. `holders_rising`/`progress_rising` (meme, `meme_features_15s`) isolados — só medidos hoje **dentro** de `equilibrio` (H-013, que morreu por 1 caso).",
    "9. `holders_rising`/`progress_rising` (meme, `meme_features_15s`) isolados — só medidos hoje **dentro** de `equilibrio` (H-013, que morreu por 1 caso). **Testadas em 07/10 (H-034, R91): NÃO CONFIRMA nas duas** — lidas do bloco `flow` gravado pela porta; holders subindo +0,027 por SOL [−0,030; +0,085], progresso subindo +0,133 [−0,041; +0,315] com só 130 apostas (" + KB + ").")

sub(K / "Mapa de Estrategias.md",
    "| 13 variáveis de decisão (R65) |",
    "| " + FILA_H034 + " | `holders_rising` e `progress_rising` isolados, como a porta os gravou na decisão (a H-013 só tinha a conjunção) | **nao_confirma** | holders D_adj=+0,027, IC [−0,030,+0,085], braço verdadeiro perde em nível; progresso +0,133 [−0,041,+0,315] em 130 apostas; reais da `operator/5` +0,082 [−0,011,+0,173], descritivo (" + KB + ") |\n| 13 variáveis de decisão (R65) |")

sub(K / "Index.md",
    "| [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]] |",
    "| " + KB + " | H-034: `holders_rising` e `progress_rising` isolados (bloco `flow` da porta) não separam o retorno do papel da porta `fluxo_e_holders` — holders D_adj +0,027 [−0,030; +0,085] em 1 680 apostas, braço verdadeiro perde em nível; progresso +0,133 [−0,041; +0,315] em 130; `comprou_no_topo` 1,19× (previa 1,5×); NÃO CONFIRMA | R91 (07/10/2026) | medição própria (papel) | H-034 |\n| [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]] |")

R = pathlib.Path("obsidian/06-DECISIONS/Revisoes-Astra/Index.md")
sub(R,
    "- [[paper-mayhem-cap]] —",
    "- [[H-034-prereg]] — R91, pré-registro dos dois \"subindo\" isolados (`holders_rising`, `progress_rising`): 5 must-fix aceitos numa emenda antes dos desfechos (regime efetivo, suporte/censura operacionais, Holm fixo, estimador próprio com multiplicidade, unidade do retorno real); IC básico como decisório rejeitado (KB-0190) (07/10)\n"
    "- [[H-034-resultado]] — R91, resultado: H, P e família NÃO CONFIRMA; saídas e hashes reproduzidos por ela; 3 must-fix de descrição absorvidos sem mudar rótulo (Holm composto, P na pista de eventos sem suporte, Holm de S1) (KB-0190) (07/10)\n"
    "- [[paper-mayhem-cap]] —")

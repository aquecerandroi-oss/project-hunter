---
name: estrategia-passa-pelo-obsidian
description: Everton (25/09/2026) — nenhuma estratégia é usada ou mudada sem passar antes pela análise no Obsidian; os robôs nunca leem notas na hora da decisão, o portão é nas ferramentas de mudança
metadata:
  type: business-rule
---

Toda mudança ou ativação de estratégia (parâmetro de rule set, braço, versão do Lab, mercado da spot/1) passa **antes** pelo Obsidian: ler `obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md`, `Fila de Hipoteses.md` e a página EXP do experimento, citar no brief e escrever o resultado de volta.

**Why:** Everton, 25/09/2026: "sempre que for usar a estratégia tem que passar analisando via Obsidian primeiro" — depois de o achado 17 do KB-0149 (o segundo de entrada decide a aposta) ficar dias anotado sem virar teste.

**How to apply:** os robôs **não** leem o Obsidian ao decidir (nota é texto não validado); o portão é nas ferramentas auditadas (`meme_rule_set.py`, `activate_strategy_version.py`, `spot_desk_markets.py` exigem `--note obsidian/...` que mencione o alvo — T4.93) e na regra `.claude/rules/obsidian-first.md`. A ficha automática diária (T4.92, `obsidian/03-TRADING/Meme/Fichas/`) mantém os dados frescos.

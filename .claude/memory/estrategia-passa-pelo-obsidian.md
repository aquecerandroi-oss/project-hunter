---
name: estrategia-passa-pelo-obsidian
description: Everton (25/09 e 28/09/2026) — o projeto inteiro aprende pelo Obsidian: toda tarefa lê as notas antes e escreve o aprendizado depois; nenhuma estratégia muda sem nota (portão nas ferramentas); robôs nunca leem notas ao decidir
metadata:
  type: business-rule
---

Toda mudança ou ativação de estratégia (parâmetro de rule set, braço, versão do Lab, mercado da spot/1) passa **antes** pelo Obsidian: ler `obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md`, `Fila de Hipoteses.md` e a página EXP do experimento, citar no brief e escrever o resultado de volta.

**Why:** Everton, 25/09/2026: "sempre que for usar a estratégia tem que passar analisando via Obsidian primeiro" — depois de o achado 17 do KB-0149 (o segundo de entrada decide a aposta) ficar dias anotado sem virar teste.

**How to apply:** os robôs **não** leem o Obsidian ao decidir (nota é texto não validado); o portão é nas ferramentas auditadas (`meme_rule_set.py`, `activate_strategy_version.py`, `spot_desk_markets.py` exigem `--note obsidian/...` que mencione o alvo — T4.93) e na regra `.claude/rules/obsidian-first.md`. A ficha automática diária (T4.92, `obsidian/03-TRADING/Meme/Fichas/`) mantém os dados frescos.


**Ampliação (28/09/2026):** Everton: "eu quero que o projeto inteiro adquira o conhecimento e sempre passe pelo obsidian" — vale para toda tarefa (código, banco, operação, pesquisa, interface), não só estratégia: ler `00-HOME` e as notas da área antes, citar, e escrever o aprendizado de volta no mesmo commit, com links e lint limpo. Regra em `.claude/rules/obsidian-first.md`; linha no `CLAUDE.md` e em todos os cartões de agente.

---
tags: [knowledge, nota, obsidian, arquivamento]
tema: "Arquivamento da Sexta-feira no Obsidian — EXP-0016..0019, catálogo de estratégias, Changelog, Diário (2026-09-08, noite)"
---

# Arquivamento no Obsidian — 2026-09-08 (noite)

Agente: documentation-writer (Sexta-feira). Escopo de escrita: `obsidian/**` e este arquivo. Nenhum
commit. Nenhum arquivo fora do escopo tocado; `.env*` não tocado.

## O que foi feito

1. **Movidos/arquivados os quatro rascunhos** de `.claude/state/exp-drafts/` para
   `obsidian/05-EXPERIMENTS/`: `EXP-0016-trendline-breakout.md`, `EXP-0017-sweep-reclaim.md`,
   `EXP-0018-stop-largo.md`, `EXP-0019-piso-atr.md`. **Os rascunhos originais não foram apagados** —
   apagar arquivos fora de `obsidian/**` estava fora do escopo de escrita autorizado nesta sessão.
   Quem tiver permissão sobre `.claude/state/exp-drafts/` pode limpá-los; ficam como cópia de
   segurança até lá.
   - Hipótese/Portão/Protocolo/Avaliações preservados **verbatim**; só a caixa de rascunho no topo
     virou uma nota de arquivamento (padrão dos EXP-0012/0013 já arquivados) e os links soltos
     (`[[KB-0076]]`, `[[KB-0010]]`, `[[KB-0006]]`, `[[EXP-0007]]`, `[[EXP-0013]]`, `[[EXP-0017]]`,
     `[[EXP-0018]]`, `[[SHADOW-LAB]]`) foram resolvidos para os nomes de arquivo reais.
   - `[[EXP-0014]]`/`[[EXP-0015]]` foram **de-linkados** (texto simples, sem colchetes): essas duas
     páginas ainda são rascunhos em `.claude/state/exp-drafts/`, não existem no vault.
   - **Correção de vocabulário controlado em `EXP-0019`:** o rascunho trazia `result: negativo` no
     frontmatter; `_TEMPLATE-EXP.md`/`docs/plans/SHADOW-LAB.md` §9 exigem `inconclusivo` abaixo de
     100 avaliáveis/30 dias (aqui: 33 e 37 avaliáveis, 11 dias), e o vocabulário do linter
     (`obsidian_lint_rules.py`) não aceita `negativo`. Corrigido só no campo controlado; o texto do
     corpo ("Formal: `negativo` nos dois braços") ficou verbatim, com a divergência declarada na nota
     de arquivamento.
   - `owner` dos quatro alinhado a `sexta-feira` (convenção de todo EXP arquivado — os rascunhos
     tinham `quant-engineer` em dois deles).
   - `status` de `EXP-0017` subiu de `proposto` para `em-andamento` (o módulo foi implementado no
     mesmo dia, commit `a9bacc6`); `result`/`evaluable`/`days` continuam `inconclusivo`/`0`/`0`
     porque nenhum replay rodou ainda.
2. **`Experiments Index.md`**: acréscimo "2026-09-08 (arquivamento da Sexta-feira, T3.34c–T3.47c)",
   quatro linhas novas em "Registro de IDs" e quatro em "Experimentos registrados".
   **`Experimentos.base` não precisou de edição** — é uma Base nativa que filtra por
   `file.hasTag("experimento")`; as quatro páginas novas já entram sozinhas.
3. **Catálogo de estratégias** (`obsidian/03-TRADING/Estrategias/`):
   - Duas famílias novas: `trendline_breakout.md` + `trendline_breakout-v1.md`,
     `sweep_reclaim.md` + `sweep_reclaim-v1.md`.
   - Dez páginas de versão novas: `momentum-v6/v7/v8.md`, `mean_reversion-v2..v8.md` — code_ref,
     params_hash (forma curta, 12 caracteres, a única publicada nos EXPs), parâmetros,
     `activated_at`/`deprecated_at`, coortes e veredito, todos sourced de
     `EXP-0013`/`EXP-0018`/`EXP-0019` (já arquivados) e dos rascunhos `EXP-0014`/`EXP-0015`
     (`mean_reversion v2`/`v3`) e `.claude/state/notes-T3.47b.md` (as três aposentadorias).
   - Tabelas de versão de `momentum.md` e `mean_reversion.md` atualizadas. **Achado ao editar:** a
     linha `v1` de `mean_reversion.md` dizia `status: draft`, `veredito: -` — desatualizada desde a
     T3.33b (a versão está `active` e replayada há dias). Corrigida com os números do
     `EXP-0009` já arquivado; é uma correção de fato, não de opinião.
   - **Limite declarado, e importante:** este host **não alcança o Postgres da VPS**
     (`uv run python infra/scripts/export_strategies_to_obsidian.py --dry-run` falha com
     `ConnectionRefusedError` — testado no início da sessão). Todas as páginas novas foram
     reconciliadas à mão a partir dos EXPs e notes já publicados, nunca inventadas; cada uma tem uma
     nota "Notas" dizendo exatamente isso e pedindo para o exportador rodar (localmente com o stack
     de pé, ou na VPS via SSH) assim que possível, para confirmar/completar `params_hash` de 64
     caracteres e a coluna de tipo/vínculo/descrição de `mean_reversion` (que não tinha schema
     publicado em lugar nenhum lido nesta sessão).
   - `mean_reversion-v1.md` **não foi tocado** — continua com o `params_hash`/status desatualizados
     de antes da T3.33b (fora do escopo desta tarefa; só a linha da tabela-família foi corrigida).
4. **`Changelog.md`**: bloco novo dentro de `## 2026-09-08`, 25 commits (`7b0edeb..402c56b`,
   confirmados com `git log d829546..HEAD` — o `HEAD` mudou de 24 para 25 commits **durante a
   sessão**, porque a árvore é compartilhada; refeito o `git log` antes de escrever), agrupados por
   tema (Lab, Tempo real, Segurança/banco, Estratégias, Radar/regime, Obsidian). Assunto de cada
   commit reproduzido **verbatim** (a instrução tinha `cut -c1-160`, mas o próprio cabeçalho do
   arquivo diz "assunto verbatim do `git log`" — segui a convenção do arquivo, não o corte).
5. **`Diario/2026-09-08.md`**: seção "Sexta-feira — fechamento do dia" acrescentada ao fim —
   incidente do loop de reinício da API (~20:40–20:45 BRT, arquivo novo fora do commit por pathspec,
   hotfix `69ae37c`), atualização por ondas da VPS até `7e9d59c` (confirmado pelo
   `brief-T3.46b-detectores-silenciosos.md`, em voo, que declara a base como scanner-worker em
   `7e9d59c`), roster 16 → 14, e a tabela de cinco decisões em aberto para o Everton (participação/
   universo líquido T3.48, `paper_v1` em `risk_profiles`, senha do `hunter_runtime`, cron de
   partições, ~5.100 operações antigas sem gráfico).
6. **Lint** (`uv run python infra/scripts/obsidian_lint.py`): rodado **antes** de qualquer edição
   (5 achados: 2 links mortos + 1 valor fora do vocabulário em `KB-0078-o-radar-preve.md`, 1 nota
   órfã + 1 frontmatter incompleto em `06-DECISIONS/2026-09-08-limites-de-risco-teto-inerte.md`) e
   depois de cada lote de edição. Os cinco achados pré-existentes foram corrigidos:
   - `KB-0078`: `[[KB-0010]]` (×2) → `[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]`;
     `confiança` de uma frase longa para `"?"` (o valor que `KB-0076`/`KB-0077` já usam para
     diagnóstico de dado próprio, não literatura), com a nuance movida para uma nota no corpo.
   - `2026-09-08-limites-de-risco-teto-inerte.md`: acrescentado `updated`, `decided_on` (a data do
     próprio registro — a página continua `status: aguardando decisão de Everton`, nenhuma decisão
     foi inventada) e `by: risk-engine-guardian` (quem escreveu a proposta); a nota deixou de ser
     órfã porque o novo trecho do Diário a referencia.
   - Editando as páginas novas surgiram **23 links ambíguos** (as páginas de operações traçadas do
     T3.50 em `03-TRADING/Operacoes-tracadas/` já usavam os mesmos nomes de arquivo —
     `momentum-v6.md`, `mean_reversion-v2.md`, `trendline_breakout-v1.md` etc.) e **6 órfãs**
     temporárias; resolvidos qualificando os links do catálogo com `[[Estrategias/<nome>|<nome>]]`.
   - **Resultado final:** `uv run python infra/scripts/obsidian_lint.py` → `RESULTADO: base limpa`
     (0 achados em 223 notas).

## O que não foi feito, e por quê

- Os rascunhos originais em `.claude/state/exp-drafts/EXP-0016..0019*.md` **não foram apagados**
  (fora do escopo de escrita desta tarefa).
- `mean_reversion-v1.md` não foi corrigido em profundidade (só a linha-resumo na tabela da família).
- Nenhuma das dez páginas de versão novas tem o `params_hash` de 64 caracteres nem (para
  `mean_reversion`) a coluna de tipo/vínculo/descrição dos parâmetros — exigem o exportador com
  acesso ao banco, indisponível deste host nesta sessão.
- `EXP-0014`/`EXP-0015` (mean_reversion v2/v3) continuam fora do vault — arquivá-los é trabalho
  novo, fora do pedido desta tarefa (que listava só EXP-0016..0019).

## Fontes

`.claude/state/exp-drafts/EXP-0016-trendline-breakout.md` ·
`.claude/state/exp-drafts/EXP-0017-sweep-reclaim.md` ·
`.claude/state/exp-drafts/EXP-0018-stop-largo.md` · `.claude/state/exp-drafts/EXP-0019-piso-atr.md` ·
`.claude/state/exp-drafts/EXP-0014-mean-reversion-teto-025.md` ·
`.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md` ·
`obsidian/05-EXPERIMENTS/EXP-0009-mean-reversion-pullback-em-tendencia.md` ·
`obsidian/05-EXPERIMENTS/EXP-0013-momentum-alvo-3-atr.md` ·
`.claude/state/notes-T3.47.md` · `.claude/state/notes-T3.47b.md` · `.claude/state/notes-T3.50.md` ·
`.claude/state/notes-T3.15d.md` · `.claude/state/brief-T3.46b-detectores-silenciosos.md` ·
`git -C C:/dev/project-hunter log` (commits `7b0edeb..402c56b` e `69ae37c`, `7e9d59c`, `803f648`,
`a9bacc6`) · `infra/scripts/obsidian_lint.py`.

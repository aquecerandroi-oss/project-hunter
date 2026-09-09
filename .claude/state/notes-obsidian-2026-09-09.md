---
tags: [knowledge, nota, obsidian, arquivamento]
tema: "Arquivamento da Sexta-feira no Obsidian — KB-0079..0081, EXP-0020/0021, catálogo de estratégias, Changelog, Diário (2026-09-09, parte 1)"
---

# Arquivamento no Obsidian — 2026-09-09 (parte 1)

Agente: documentation-writer (Sexta-feira). Escopo de escrita: `obsidian/**` e este arquivo. Nenhum
commit. Nenhum arquivo fora do escopo tocado; `.env*` não tocado; nenhum shell em background;
comandos em primeiro plano.

## O que foi feito

1. **Arquivados os três rascunhos de candlestick/regime** de `.claude/state/exp-drafts/` para
   `obsidian/11-KNOWLEDGE/`: `KB-0079-onde-ganha-e-perde.md`, `KB-0080-candlestick-evidencia.md`,
   `KB-0081-candlestick-no-nosso-dado.md`. **Os rascunhos originais não foram apagados** — fora do
   escopo de escrita autorizado.
   - Corpo preservado **verbatim** (números, tabelas, vereditos); só o frontmatter e o bloco de
     abertura mudaram, no padrão de KB-0076/KB-0078: `status: rascunho` → `arquivada`, `updated` para
     2026-09-09, banner "Arquivada pela Sexta-feira..." substituindo o antigo "RASCUNHO para a
     Sexta-feira arquivar".
   - **Correção de vocabulário controlado em KB-0079:** o rascunho trazia, no campo `confiança`, uma
     frase inteira ("alta no diagnóstico... baixa-média no achado..."); `obsidian_lint_rules.py`
     (`ENUM_VOCAB`) só aceita `anedótico | backtest do autor | estudo revisado | replicado | ?`.
     Corrigido para `"?"` e a nuance movida por extenso para uma nota de vocabulário controlado logo
     abaixo do banner — o mesmo padrão que KB-0078 já usa. KB-0080 e KB-0081 já vieram com
     `confiança: "?"`, sem correção necessária.
   - Links soltos `[[KB-0010]]` (×2) e `[[KB-0076]]` (×1), que apareceram só depois de mover os
     arquivos para dentro do índice de links do vault, foram resolvidos para os nomes de arquivo
     reais (`[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]`,
     `[[KB-0076-por-que-perdemos-2026-09-08]]`).
   - Acrescentei, sem tocar nos números, uma frase de fechamento em KB-0079 e KB-0080 apontando para
     os desdobramentos do mesmo dia (o portão de regime da T3.52/EXP-0020 e a medição própria da
     T3.55b/KB-0081) — são fatos do dia, não reinterpretação do conteúdo arquivado.
2. **`11-KNOWLEDGE/Index.md`**: três linhas novas na tabela "Notas" (KB-0079/0080/0081), duas linhas
   de tema atualizadas ("Análise técnica clássica", "Diagnóstico do nosso próprio resultado") e
   `updated` para 2026-09-09.
3. **Arquivados os dois rascunhos de experimento** para `obsidian/05-EXPERIMENTS/`:
   `EXP-0020-regime-gate.md`, `EXP-0021-timeframe.md`.
   - **`EXP-0020`**: `status: rascunho` (com `version` dizendo "ainda não derivadas") →
     `status: implementado, replay pendente`, porque o commit `d21a11d` (T3.52/b/c) pôs o portão de
     elegibilidade em produção **depois** de o rascunho ter sido escrito, mas **antes** de qualquer
     braço deste EXP ter sido derivado. Acrescentei uma seção "O que já mudou desde o rascunho" e uma
     nota de numeração (a próxima vaga livre de `v9` pode não ser `v9` mais, porque o eixo de
     timeframe já a usou e aposentou) — sem inventar `params_hash` nem `code_ref` que ainda não
     existem. `result` do frontmatter corrigido para `inconclusivo` (o único valor do vocabulário
     controlado compatível com "nenhuma corrida ainda"; `pendente` não está no `ENUM_VOCAB`).
   - **`EXP-0021`**: corpo preservado verbatim; acrescentei um parágrafo de fechamento (banner) e uma
     nota dentro de "Portão de desenho" e "A lente da abertura" registrando que `momentum v10` (braço
     B2) foi aposentada **no mesmo dia**, horas depois, pelo T3.56 — o mesmo veredito de C5 que o EXP
     já tinha medido. `result` do frontmatter corrigido de `parcial` (fora do vocabulário) para
     `inconclusivo` (a régua editorial — 100 avaliáveis **e** 30 dias — não fecha em nenhum dos dois
     braços; `parcial` nunca foi um valor válido). `version` do frontmatter atualizada para declarar
     o estado real de cada braço (viva/aposentada) em vez de deixar como estava na hora da escrita.
4. **`05-EXPERIMENTS/Experiments Index.md`**: parágrafo "Acréscimo de 2026-09-09" com o resumo dos
   dois EXPs e do roster; duas linhas novas em "Registro de IDs" e duas em "Experimentos
   registrados"; `updated` para 2026-09-09.
5. **Catálogo de estratégias** (`obsidian/03-TRADING/Estrategias/`):
   - Tabelas de família atualizadas com os números **medidos pelo próprio T3.56**
     (`.claude/state/notes-T3.56.md`, `as_of` 2026-09-09T14:52Z) — não os do brief que abriu a
     tarefa, porque a nota deixa registrado que os dois divergem em várias linhas (nenhuma muda de
     sinal): `momentum.md` (v2/v4/v6/v9/v10 deprecated, v3 paper com a recusa registrada, v8 marcada
     como a única viva), `mean_reversion.md` (v9 deprecated efêmera, v10 active/`robusto`),
     `volume_anomaly.md` (v2 deprecated, família inteira fora do roster) e
     `trendline_breakout.md` (v1 deprecated, módulo fica para uma v2).
   - Frontmatter + "Notas" atualizados nas quatro páginas de versão que já existiam e mudaram de
     estado: `momentum-v2.md`, `momentum-v6.md`, `volume_anomaly-v2.md`, `trendline_breakout-v1.md`
     (`status: active` → `deprecated`, `deprecated_at` preenchido com o timestamp exato do
     `system_events`, título do H1 corrigido). `momentum-v3-paper.md` ganhou uma nota sobre a
     tentativa de aposentadoria recusada pelo script (o portão de exposição aberta), sem mudar
     frontmatter (a versão continua `active`/`paper` de fato).
   - **Duas famílias novas, criadas à mão:** `session_orb.md` + `session_orb-v1.md` (a família
     existia desde 2026-09-08/T3.33c, foi ativada, replayada e aposentada sem nunca ter ganhado
     página no catálogo — lacuna registrada na própria página, não escondida) e
     `mean_reversion_h1.md` + `mean_reversion_h1-v1.md` (pedido explícito da tarefa: módulo
     implementado no mesmo dia, T3.54/`eaebf8f`, ainda não semeado nem ativado no banco).
   - `momentum-v4.md`, `momentum-v9.md`, `momentum-v10.md`, `mean_reversion-v9.md`: **não criadas**
     (fora do pedido explícito, que só listava `mean_reversion_h1.md` como página nova); as tabelas
     de família citam essas versões com `Página: —` e uma nota explicando a ausência.
   - **Limite declarado, herdado das sessões anteriores:** este host não alcança o Postgres da VPS
     (`export_strategies_to_obsidian.py --dry-run` não foi testado nesta sessão, mas a limitação já
     estava documentada em todas as páginas equivalentes de 2026-09-08 e continua valendo — nenhum
     número foi lido do banco diretamente por mim).
6. **`Changelog.md`**: bloco novo `## 2026-09-09` com os 18 commits `7254a46..d21a11d` (das 21:57 de
   2026-09-08 às 12:19 de 2026-09-09), obtidos por
   `git log --since="2026-09-08 21:00" --format="%h %s"` e comparados um a um contra o arquivo para
   descartar os sete que já estavam documentados (`402c56b`..`a9bacc6`, do bloco anterior). Agrupados
   por tema conforme a instrução: livro de ofertas (T3.46b, T3.46d–h), mapa de regime (T3.53),
   candlestick (T3.55a/b), eixo de timeframe (T3.54), regime gate + contexto por versão (T3.52/b/c +
   T3.54b/c, um commit só), Lab (T3.50b) e Obsidian (a filial anterior). Mensagens reproduzidas
   verbatim (a instrução pedia `cut -c1-160`, mas o próprio cabeçalho do arquivo diz "assunto verbatim
   do git log" — segui a convenção do arquivo, como a filial de 2026-09-08 já tinha decidido); a
   entrada de `T3.56` (roster) entrou no mesmo bloco porque o commit `240e08d` também caiu dentro da
   janela do `--since`. `d21a11d` (o commit mais recente da janela) ficou por último. `updated` para
   2026-09-09.
7. **`Diario/2026-09-09.md` (novo)**: primeiro diário do dia — a madrugada de pesquisa
   (KB-0079/EXP-0021/KB-0080+81), o buraco de ~10h30 sem commit nem arquivo de estado entre
   `notes-T3.55b.md` (01:02 BRT) e `notes-T3.46g.md` (11:41 BRT) — achado por comparação de
   timestamps de arquivo e do `git log`, registrado como achado operacional sem causa atribuída — a
   corrida do livro de ofertas fechada (183/200 → 2–9/200 de recusa, T3.46d–h), o portão de regime em
   produção (T3.52) e a limpeza do roster (T3.56, 16 → 9). A tabela de seis decisões em aberto para o
   Everton repete as cinco de ontem (nenhuma foi fechada nesta janela) e acrescenta a nova: a linha
   `paper` (`momentum v3`) que o script não consegue aposentar sozinho. O número "`mean_reversion v6`
   +303 USDT, 16 de 100, 2 de 30 dias" veio informado no brief desta tarefa (não é uma leitura minha
   de SQL nem do banco) e foi registrado com essa proveniência; a soma em USDT de `mean_reversion v10`
   (+525 USDT) **é derivada** por mim a partir do R somado publicado em `EXP-0021-timeframe`
   (+10,87 R × 48,33 USDT/R, a conversão declarada em KB-0076), não uma leitura nova.
8. **Lint** (`uv run python infra/scripts/obsidian_lint.py`): rodado só **depois** de todas as
   edições (a base já estava limpa em 2026-09-08). Achados na primeira passada — 3 links mortos
   (`[[KB-0010]]` ×2, `[[KB-0076]]` ×1 nas duas KBs de candlestick/regime que eu tinha acabado de
   escrever) e 1 nota órfã (`Diario/2026-09-09.md`, sem nenhum inbound link ainda). Corrigidos:
   os três links qualificados para o nome de arquivo completo; a órfã resolvida acrescentando
   `[[Diario/2026-09-09|2026-09-09]]` à lista de diários em `00-HOME.md` (o mesmo lugar onde os dias
   anteriores já estão listados). **Resultado final:** `RESULTADO: base limpa` (0 achados em 233
   notas).

## O que não foi feito, e por quê

- Os rascunhos originais em `.claude/state/exp-drafts/KB-0079..0081*.md` e `EXP-0020/0021*.md`
  **não foram apagados** (fora do escopo de escrita desta tarefa).
- `momentum-v4.md`, `momentum-v9.md`, `momentum-v10.md`, `mean_reversion-v9.md` **não foram criadas**
  como páginas individuais — só a tarefa explícita de `mean_reversion_h1.md` estava no pedido; as
  outras quatro entram nas tabelas de família com `Página: —` e uma nota.
- Nenhuma consulta SQL nova foi rodada por mim; todo número vem dos arquivos nomeados na tarefa
  (`notes-T3.53/54/54b/55a/55b/56.md`, os rascunhos de KB/EXP) ou do `git log` para o Changelog.
- Não tentei resolver o CONCERN 2 do T3.56 (a linha `paper` presa) nem decidir sobre as seis
  pendências do Everton — são decisões de produto/risco, registradas, não tomadas por mim.

## Fontes

`.claude/state/exp-drafts/KB-0079-onde-ganha-e-perde.md` ·
`.claude/state/exp-drafts/KB-0080-candlestick-evidencia.md` ·
`.claude/state/exp-drafts/KB-0081-candlestick-no-nosso-dado.md` ·
`.claude/state/exp-drafts/EXP-0020-regime-gate.md` ·
`.claude/state/exp-drafts/EXP-0021-timeframe.md` ·
`.claude/state/notes-T3.53.md` · `.claude/state/notes-T3.54.md` · `.claude/state/notes-T3.54b.md` ·
`.claude/state/notes-T3.55a.md` · `.claude/state/notes-T3.55b.md` · `.claude/state/notes-T3.56.md` ·
`.claude/state/notes-T3.46g.md` (para o carimbo de horário do fim da parada noturna) ·
`git -C C:/dev/project-hunter log --since="2026-09-08 21:00" --format="%h|%ad|%s" --date=format:'%Y-%m-%d %H:%M'` ·
`infra/scripts/obsidian_lint.py`.

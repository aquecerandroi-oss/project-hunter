# Brief T4.15 — o fechamento diário do Lab meme: lições do dia escritas sozinhas e a próxima leva proposta (Everton, 12/09/2026 13:2x BRT: "ele vai se auto aprimorando a cada leitura, a cada compra e venda, né?")

**O que é:** um job ops (`infra/scripts/meme_close_day.py`, `--day YYYY-MM-DD --dry-run|--apply`) que, no fim do dia Brasília (cron às 00:10 BRT na VPS, via `compose.sh ops`), lê tudo o que o dia produziu e escreve, sem inventar nada: (1) `obsidian/09-OPERATIONS/Diario-Meme/<dia>.md` completo (o `meme_diary.py` já gera os números; este job acrescenta as **lições**); (2) `obsidian/00-INBOX/Hipoteses-do-plantao.md`: linhas `nova` com prefixo `M-L` (lição medida) — só quando a evidência passar a régua; (3) `.claude/state/lote-meme-<dia+1>.md`: a proposta da próxima leva (quais conjuntos aposentar, quais braços pré-registrar, com parâmetros e a previsão `descartar` por padrão) — **proposta**, não ação: o orquestrador pré-registra e o Everton decide o que pesa dinheiro.

**Pré-requisitos:** T4.12 (posições reais) e T4.11 (moonshot) commitados; `meme_diary.py`/`meme_diary_render.py`/`meme_diary_wallets.py` no estado final.

**As lições que o job sabe medir (cada uma com n, IC por blocos de hora, e "insuficiente" quando n < 30):**
1. **Saídas por motivo** por conjunto: fração e R médio por `creator_dump`, `trailing`, `time_stop`, `target`, `max_loss`, `line_broken`, `dead`, `migrated`, `sell_now`, `rug_no_snapshot` — e a pergunta "qual saída custou mais R?".
2. **Idade na entrada × R** (bandas 30–60 s, 1–2, 2–5, 5–10 min) e **progresso na entrada × R**.
3. **Snipers/top-10/dev na entrada × R** (tercis) — a evidência para apertar ou afrouxar portas.
4. **Mesmo slot × R**: apostas em moedas com `pool_created_at − created_at ≤ 1 s` contra as outras.
5. **Cobertura do dia**: fração de linhas do portão com progresso, fita, linha, hype; recusas por motivo (do heartbeat/`lab_gate_refusals` gravado por tick em `meme_lab_ticks` — criar a tabela se não existir, uma linha por tick com o JSON de recusas).
6. **Operador**: propostas `operator` propostas × aprovadas × expiradas; latência até o aval; R das aprovadas.
7. **Reais (T4.12)**: por carteira, compras/vendas, PnL FIFO, e o veredito do Lab no minuto de cada compra (`lab_context`) — "o Lab teria feito o mesmo?" em números.
8. **Leave-top-out**: R somado sem a melhor aposta do dia, por conjunto.
9. **Comparação com o pré-registro**: para cada EXP-M* ativo, o que a previsão congelada dizia e o que o dia mediu (sem mudar a página: append na seção "Avaliação" com data).

**Regras do texto:** português, números com hora Brasília, nunca "hoje foi bom/ruim" sem o n e o IC; cada lição termina com "o que muda amanhã" (uma frase) ou "nada muda (n insuficiente)".

**Entregar:** o script (≤ 350 linhas por arquivo; módulos `meme_close_{stats,lessons,render}.py`), `meme_lab_ticks` (migração pequena + o laço gravando uma linha por tick), cron na VPS documentado em `docs/DEPLOYMENT.md` (ops, 00:10 BRT), testes (unit com fixtures de apostas sintéticas cobrindo cada lição; 1 testcontainer), `obsidian_lint.py` limpo depois de um `--apply` em banco de teste, `docs/plans/T4-MEME-RADAR.md` §T4.15, `.claude/state/notes-T4.15.md`; `git status --porcelain` ao final. Regras de sempre (primeiro plano `timeout 290`/590; sem background; sem `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; sem commit; sem `.env*`; nada real; sem tocar `apps/web/**`; `SendMessage` desabilitado; Bash mangla `\n` em heredoc → Write/Edit). Relatório ≤ 12 linhas em português.

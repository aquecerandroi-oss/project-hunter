# Notas T4.25 — os gráficos das apostas meme no Obsidian (15/09/2026, 22:0x–23:5x BRT)

**Por quê:** o vault tinha 681 gráficos de perps/spot (T3.50) e **zero** de meme. As linhas da T4.10
(`support_line_sol`, `high_15m_sol`, `breakout_15m`, `higher_lows`) existiam como números em
`meme_features_1m` e como desenho só na tela `/meme/{mint}`. Pergunta do Everton, 15/09 21:3x BRT.

**Entregue** (mesmo desenho da T3.50: exportar na VPS, desenhar no laptop, embutir no vault):

- `infra/scripts/meme_render_bets.py` — CLI com `export` / `render` / `notes` (142 linhas).
- `infra/scripts/meme_render_bets_model.py` — o modelo do JSONL (`Bet`, `Minute`, `Point`,
  `Snapshot`, `Segment`), `parse_bet`/`load_bets` e **a geometria**: `support_segment`,
  `previous_high`, `minute_at`. Sem banco, sem matplotlib, `Decimal` até a borda.
- `infra/scripts/meme_render_bets_query.py` — o `SELECT` como `hunter_app` (`gather_day`), a janela
  ± 10 min por mint e o `write_jsonl`.
- `infra/scripts/meme_render_bets_draw.py` — o único módulo que importa matplotlib e o único onde
  `Decimal` vira `float`.
- `infra/scripts/meme_render_bets_notes.py` — as páginas por conjunto, o índice, o link de entrada
  no `Meme/README.md` e a seção `## 7. Gráficos` do diário.
- Testes: `infra/scripts/tests/test_meme_render_bets.py` (12) e
  `test_meme_render_bets_integration.py` (3, testcontainer em `head`).
- Docs: `docs/PIPELINE.md` §9c (nova), `docs/plans/T4-MEME-RADAR.md` §T4.25, `docs/DEPLOYMENT.md`
  §3.6b (a rotina da manhã ganhou o passo dos gráficos).

**Não-antecipação (o teste que tem dentes).** A reta de suporte desenhada é a do **minuto fechado da
entrada** e a máxima é a do minuto **anterior** a ele (o contrato do `breakout_15m` exclui o próprio
minuto). `test_a_minute_after_the_entry_cannot_move_the_line_that_is_drawn` altera todos os minutos
posteriores à entrada (suporte 999, inclinação −50, máxima 999, rompimento true) e exige que
`support_segment`/`previous_high` não mudem; a mesma alteração, lida pela **trapaça** deliberada (usar
o último minuto em vez do da entrada), muda as duas — é exatamente essa diferença que o corte impede
de chegar ao gráfico. A projeção de qualquer reta **para na saída**: uma linha desenhada 10 min depois
do fim seria uma afirmação sobre uma posição que já não existia.

**Suposições numéricas/estruturais declaradas (nenhuma estava no brief):**

1. **Faixas `≈`.** Alvo, piso, arme e trailing são regras sobre a **marca em SOL** (o que uma venda
   cheia renderia, taxas incluídas — `RISK_ENGINE_MEME.md` §6), e o gráfico só tem mcap. Desenhei os
   múltiplos aplicados ao **mcap da entrada**, com `≈` no rótulo e a frase no rodapé ("as regras medem
   a marca em SOL, não o mcap"). A diferença é o deslize da própria ordem mais 1,75 % por ponta.
   Faixa que não cabe na escala não achata o gráfico: sai nomeada no rodapé, com o número.
2. **Pasta `Apostas-tracadas`, não `Operacoes-tracadas`.** O brief pedia
   `03-TRADING/Meme/Operacoes-tracadas/`; o `obsidian_lint.py` resolve `[[wikilink]]` por **sufixo de
   caminho**, e um segundo `Operacoes-tracadas/README.md` tornaria **ambíguos** 8 links existentes (as
   7 páginas da T3.50 e o `09-OPERATIONS/Diario/2026-09-08.md`, registro datado que não se reescreve).
   O teste de integração pegou isso rodando o linter sobre uma cópia do vault com as páginas novas.
3. **Embeds markdown, não `![[…png]]`.** `.png` não é alvo linkável do linter (`ASSET_SUFFIXES` =
   `.base`/`.canvas`), então o wikilink pedido pelo brief viraria link morto. Usei a convenção do
   próprio vault (`03-TRADING/Operacoes-tracadas/*.md`, `KB-0077`): `![alt](../../../attachments/…)`,
   com o `+` de um R positivo percent-encoded. Alternativa (não tomada, por ser mudança transversal
   com outros agentes na árvore): acrescentar `.png` a `ASSET_SUFFIXES`.
4. **Cinco módulos, não quatro.** O brief nomeia `{query,draw,notes}`; com o modelo dentro de
   `_query` o arquivo dava 431 linhas (teto 350), então o modelo e a geometria foram para `_model.py`.
5. **Hora de Brasília no nome do arquivo** (`<HHMM>-<símbolo>-<R>.png`), porque a pasta do dia já é o
   dia de Brasília — misturar UTC no nome dentro de uma pasta BRT confundiria a ordenação.
6. **`r_text` nunca abaixo de duas casas:** `-1` numa página de `-0.0403` se lê como arredondamento;
   `-1.00` se lê como a aposta inteira, que é o que é.

**Corrida real: não houve.** O brief pede uma corrida de 14/09 e 15/09 com o JSONL pedido ao
orquestrador; sem acesso à VPS (e sem `.env`) nesta sessão, não existe JSONL real, então **nada foi
escrito no vault** — escrever a fixture lá seria dado falso numa base que registra dinheiro. Os três
PNGs desta entrega são da fixture sintética, desenhados fora da árvore em
`C:/Users/evert/AppData/Local/Temp/claude/t425/attachments/2026-09-14/`:
`flow_v2-2/0202-WIF--0.04.png` (94,4 KB, com linha, rompimento e venda do criador),
`trendline_v0-1/0631-BONK-+2.15.png` (62,2 KB, sem linha — `too_few_points`),
`flow_v2-2/0240-PEPE--1.00.png` (61,1 KB, fecho indeterminado sem fotografia). O primeiro
`export → render → notes` real entra pela rotina da manhã (`docs/DEPLOYMENT.md` §3.6b).

**Provas (saídas reais desta sessão):**

```
uv run --with matplotlib pytest infra/scripts/tests/test_meme_render_bets.py -q
............                                                             [100%]
12 passed in 4.37s

uv run pytest infra/scripts/tests/test_meme_render_bets_integration.py -q
...                                                                      [100%]
3 passed in 31.38s

uv run ruff check infra/scripts/ -> All checks passed!
uv run ruff format --check infra/scripts/ -> 95 files already formatted
uv run pyright <os 5 módulos + os 2 testes> -> 0 errors, 0 warnings, 0 informations
uv run python infra/scripts/check_file_size.py -> scanned 861 files; 0 over budget, 0 grandfathered
```

**Fora desta tarefa:** rotular no `apps/web` (nada mudou lá); a corrida real; um `--since`/intervalo de
vários dias no `export` (hoje é um dia por invocação, como o fechamento); e o gráfico da aposta
**aberta** (só fechada tem R a nomear).

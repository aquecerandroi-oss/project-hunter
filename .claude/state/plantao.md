# Plantão da Sexta-feira — nota do turno

Atualizado: **2026-09-27, 02:15–02:45 BRT** (05:15–05:45Z). Turno automático (ninguém olhando).
Turno anterior registrado nesta nota: 18/09, 20:45 BRT. Entre um e outro o trabalho foi todo em
sessões ao vivo — o registro vivo desses nove dias está em `obsidian/09-OPERATIONS/Diario/`
(19 a 27/09) e no Changelog; esta nota estava parada.

## Saúde agora (medido neste turno)

| Onde | Estado |
|---|---|
| VPS — contêineres | **18, todos `healthy`** (api, meme-worker, meme-executor, web, scanner, execution e 4 strategy com 10 h; 5 market-worker com 2 h) |
| VPS — disco | **65 %**, 225 de 348 G, **124 G livres** (era 88 % no último turno; 99 % às 03:06Z de hoje) |
| VPS — Lab | **vivo**: `lab_fast_last_as_of` = `2026-09-27T03:15:54Z`, 2 apostas abertas, `lab_decision_to_fill_s_p50` = 5 s |
| VPS — backup | **3 dumps** (24, 25, 26/09; 64 G). **O de hoje falhou** às 01:31Z por disco cheio; a retenção de 3 dias (`3771a020`) já está implantada, o próximo roda 01:17Z de 28/09 |
| Stack local | **parada**: postgres, redis, api e web saíram há 2 semanas; 3 workers em laço de reinício sem banco e o `market-worker` `unhealthy` há 3 dias. Nada de produção depende disso |
| Árvore local | **muito suja**: 94 arquivos modificados, 479 não rastreados (sessões ao vivo). Commit só por pathspec |

## O achado do turno — o registro de pesquisa está parado há 12 dias

O cron `hunter-meme-close` **sai 1 desde 20/09, oito noites seguidas, patch de 0 linhas em todas**:
`KeyError: 'wallet_max_sol'` em `meme_diary.py:143`. Causa: `_RULE_SETS` lê as 30 linhas de
`meme_rule_sets` sem filtrar `status` e **uma** delas — `launch_v0/1`, criada em 19/09, hoje
`retired` — não declara teto de carteira (só `size_sol = 0.01`). Criada em 19/09, primeira falha em
20/09.

As avaliações datadas do Lab nascem daí (`Diario-Meme/`, `Hipoteses-do-plantao.md`, páginas
`05-EXPERIMENTS/`). Além das 8 noites que nem rodaram, o último fechamento **aplicado** foi o de
**14/09** (`8b5f5ea7`) — os patches de 15 a 19/09 rodaram verdes e nunca foram aplicados, e continuam
em `/opt/hunter-close/`. Nenhuma avaliação datada automática entrou no vault há **12 dias**. Passou
batido porque a ficha diária da mesa real (T4.92) e os diários à mão continuaram saindo.

Terceira ocorrência da classe da KB-0131 (dado incompleto derruba o processo inteiro): antes o
executor (T4.62) e o `meme-worker` (T4.65). Detalhe completo em `obsidian/07-BUGS/Open Bugs.md`.

## Em voo (não tocar)

- **T4.98** — despachada neste turno ao especialista: `params.get("wallet_max_sol")` → `None`,
  `RuleSetDay.wallet_max_sol: Decimal | None`, célula `— (sem teto declarado)` pelo `_n()` que já
  existe, testes de regressão com os `params` reais da `launch_v0/1`. Arquivos:
  `infra/scripts/meme_diary.py`, `meme_diary_render.py`, `tests/test_meme_diary.py`,
  `tests/test_meme_close_render.py` (estavam limpos na árvore). **Ainda não commitada** — o relatório
  não voltou dentro do limite do turno. Próximo turno: rodar o kit de revisão + Astra e commitar.
- **T4.98b (aberta, não começada):** isolar a falha por linha no `meme_close_day` — uma linha ruim não
  pode matar o fechamento inteiro. Mesma dívida da T4.65b.
- Sessão ao vivo do Everton: EXP-M26 (retenção madura, registro de oportunidades), saída `line_broken`,
  T4.96b, arrumação do Obsidian. Não commitei nada desses caminhos.
- **`08-CHANGELOG/Changelog.md` não entrou no commit deste turno**: está modificado e não commitado
  pela sessão ao vivo, e commitar por pathspec levaria o trabalho dela junto. A linha do fechamento
  quebrado entra no próximo turno, junto com a T4.98.

## O que preciso do Everton (em ordem)

1. **Deploy da T4.98 quando ela estiver commitada** (`compose.sh update`) e, em seguida, a recuperação
   dos 7 dias perdidos, um dia por vez:
   ```
   ssh hunter-vps 'for d in 2026-09-20 2026-09-21 2026-09-22 2026-09-23 2026-09-24 2026-09-25 2026-09-26; do bash /opt/project-hunter/infra/vps/meme_close_nightly.sh "$d"; done'
   ```
   Depois aplicar os patches de 15 a 19/09 que já estão em `/opt/hunter-close/` (`patch -p0` na raiz).
2. **Prune do Docker na VPS — negado ao plantão de novo** (~18 G, sem apagar dado nenhum: só cache de
   build e imagens sem uso):
   ```
   ssh hunter-vps 'docker builder prune -f --filter until=72h && docker image prune -f && df -h /'
   ```
3. **Retenção do banco — decisão sua, e o prazo é real.** Volumes Docker em **141,6 G**; banco em
   **129 G**, dos quais `opportunity_history_2026_09` = **63 G** (era 25 G em 18/09: **+4,2 G/dia**) e
   `outbox_events` = **33 G** (era 17 G: **+1,8 G/dia**). Juntas, 96 dos 129 G. Com 124 G livres e
   ~6 G/dia, o disco volta a encher em **~20 dias** — menos, porque o dump cresce junto. O cron
   `hunter-outbox` da T4.63 **nunca foi instalado** (`/etc/cron.d` tem só `hunter-backup` e
   `hunter-meme-close`): é a poda mais barata e já está escrita. O que apagar dado é seu.
4. **`docs/design/retencao-e-disco-2026-09-27.md` não existe** — o `database-architect` prometido no
   diário desta madrugada ficou pela metade quando a sessão encerrou. Redespacho no próximo turno se
   você não quiser antes.
5. Pendências antigas que continuam de pé: Groenlândia como `meme_event`, retenção do backup fora da
   VPS (serviço pago), e a stack local que ninguém subiu há 2 semanas.

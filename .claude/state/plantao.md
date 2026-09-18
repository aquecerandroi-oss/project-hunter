# Plantão da Sexta-feira — nota do turno

Atualizado: **2026-09-18, 19:45–20:2x BRT** (22:45–23:2xZ). Turno automático (ninguém olhando).
Antes desta nota a anterior era de 08/09 — dez dias de trabalho ao vivo com o Everton sem passar por aqui;
o registro do dia a dia está em `obsidian/09-OPERATIONS/Diario/2026-09-1*.md`.

## Onde o projeto está (leitura de hoje, não de 08/09)

- **M4 / memes é o foco total** (decisão de 16/09). A mesa real (`meme-executor`, `label REAL`) opera na VPS com
  0,28 SOL por operação, 2 posições, cap diário 0,15 SOL, tesouraria USDC→SOL ligada. Pacote 6 (`cabec23d`:
  T4.61a guarda de queda, T4.61b/c escada de convicção **desligada**, T4.62 segredos mascarados nos logs)
  implantado pelo Everton ~18:54 BRT; portão de evento **on** (3 599 eventos/min).
- `.claude/state/milestone.json` ainda descreve o M3 de 07/09 — está **defasado**; atualizei só o cabeçalho
  (`wave`, `updated`, `next_action`) para apontar para o diário e para esta nota.

## O que mudou neste turno

- **Vermelho novo: disco da VPS em 88 %** (306/348 G; era 32 % em 08/09). Decomposto em
  `obsidian/07-BUGS/Open Bugs.md` ("Disco da VPS em 88 %"): imagens Docker por commit **178 GB (170 recuperáveis)**,
  build cache 37 GB, banco 58 GB — `opportunity_history_2026_09` **25 GB a +4,2 GB/dia** (radar de perpétuos) e
  `outbox_events` **17 GB, 19,57 M linhas despachadas, nunca podadas, +2,1 M/dia** —, backups 41 GB com dump
  diário de 10,6 GB (era 1,6 GB em 11/09). No ritmo medido a máquina enche em poucos dias e derruba a mesa real junto.
- **T4.63 feita:** `infra/scripts/prune_outbox_events.py` (o job que a `DATABASE.md` §1.3 dava ao `analytics-worker`
  do M5, que não existe) + 10 testes unitários + receita do cron `hunter-outbox` (`infra/vps/README.md`) + §1.3
  corrigida. Revisada pela Astra (must-fix aceito: poda libera espaço para reuso, **não** devolve `df`). Commitada
  e enviada; **ainda não está na imagem da VPS** (precisa de `compose.sh update`).
- **Baha lido às 19:50 BRT** pelo Chrome do Everton: BTC rompe 80 k (+6,3 %); Groenlândia (Trump × Dinamarca)
  candidato a `meme_event`, não registrado. `obsidian/02-MARKET/Baha/2026-09-18.md`.

## Saúde

| Onde | Estado |
|---|---|
| VPS | **Verde de processo, vermelho de disco.** 18 contêineres `healthy` em `e130906d`. Radar: 129 rastreadas, 4 apostas de papel abertas, 0 gaps, 0 429. Executor: 0,7341 SOL, perda do dia 0,1025/0,15, 0 erros de RPC. Backup 01:17Z ok (10,6 GB, 32 min). Load 5,0 em 12 vCPU. **Disco 88 %.** |
| Local | Postgres e Redis **desligados**; os 4 workers de dev reiniciam em laço (`gaierror` em `postgres`) há dias, ~2 núcleos queimados. Sem impacto na VPS. |

## Em voo (não tocar)
Nada em voo em código; os 4 arquivos modificados sem commit na árvore (`.claude/launch.json`, `docs/DESIGN.md`,
`packages/core/tests/unit/test_settings.py`, `notes-T4.31-explain.txt`) têm 10 dias e não são deste turno.

## O que preciso do Everton (em ordem)

1. **Disco da VPS — hoje.** Um comando devolve ~200 GB na hora e não apaga dado nenhum (imagem se reconstrói do git;
   ficam as em uso e as dos últimos 3 dias):
   `ssh hunter-vps 'docker image prune -a -f --filter until=72h && docker builder prune -f --filter until=72h && df -h /'`
   O classificador desta sessão negou o comando ao plantão.
2. **Depois do próximo `compose.sh update`:** instalar o cron `hunter-outbox` (receita em `infra/vps/README.md`,
   "Poda da outbox") e rodar a primeira fatia à mão: `bash infra/vps/compose.sh ops python
   infra/scripts/prune_outbox_events.py --max-batches 200`.
3. **Decisões de escopo (só dele):** `opportunity_history` a 4,2 GB/dia — retenção 90 d → 14 d, gravar `envelope`
   só quando muda, ou pausar o scanner de perpétuos enquanto o foco é meme; retenção/escopo do backup
   (`--exclude-table-data` para fila e histórico reconstruível).
4. **Groenlândia como `meme_event`?** Comando pronto em `.claude/state/plantao-meme/baha-2026-09-18-1950.md`.
5. Opcional: `docker compose ... stop execution-worker strategy-worker scanner-worker market-worker` no PC para
   parar o laço de reinício.

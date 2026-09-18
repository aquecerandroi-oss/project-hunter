# Plantão da Sexta-feira — nota do turno

Atualizado: **2026-09-18, 20:45–21:2x BRT** (23:45–00:2xZ). Turno automático (ninguém olhando).
Turno anterior: 19:45 BRT do mesmo dia (disco 88 %, T4.63 poda da outbox).

## O que mudou desde o último turno

- **INCIDENTE EM PRODUÇÃO (novo, 23:24Z = 20:24 BRT): `meme-worker` em laço de reinício** — 84 reinícios
  em 22 min. O lote das 22:47Z que trocou a saída da mesa (`operator/5`) para "alvo 1,3× / trailing 20 %
  **sempre** / 5 min" escreveu `trailing_arm_x = "1.0"`; o `ExitRules` só aceita `None` ou `> 1`. A primeira
  aposta de papel do conjunto novo (`01a0b6d5-b8ee-782a-9d02-ee508754f4f0`, 23:24:07Z) leva o valor e mata
  o tique do Lab, e o `TaskGroup` inteiro do worker cai — **o portão de evento que alimenta a mesa real cai
  junto** a cada ~15 s (propostas 23/h → 11/h). A mesa real em si está de pé (executor `healthy`, 0 posições,
  perda do dia 0,1088/0,15, 0 erros de RPC). Detalhe completo em `obsidian/07-BUGS/Open Bugs.md`.
- **T4.65 (código):** normalizar `trailing_arm_x ≤ 1 → None` ao ler conjunto e aposta
  (`services/meme-worker/.../lab_params.py`, `lab_models.py`, testes). **Commitada em `c569ae7f`** (408 testes do worker verdes,
  ruff/pyright limpos, Astra APPROVE_WITH_NITS). Ainda **não** está na imagem da VPS. **T4.65b (aberta):** uma aposta inválida não pode derrubar o processo — isolar como a
  T4.62 fez no executor.
- Disco da VPS: **88 %, inalterado**. Nada mais mudou na VPS (`e130906d`).

## Em voo (não tocar)
Saídas por evento no `meme-executor` (`event_exits*.py`, `exit_settle.py` + 10 módulos modificados, 2 testes),
último toque 20:44 BRT — sessão ao vivo do Everton. O docstring diz "T4.63", número já gasto pela poda da
outbox (`724e5246`); renumerar ao commitar.

## O que preciso do Everton (em ordem)

1. **AGORA — parar o laço de reinício sem deploy (2 comandos, ~1 min).** O classificador negou ao plantão
   até o dry-run. O primeiro passa pelo caminho auditado (`meme_rule_set_param_history` + `system_events`);
   o segundo tira o valor da única aposta que o carrega (`UPDATE 1` esperado; valor antigo `"1"`, registrado
   em Open Bugs). Sem isso o worker continua caindo a cada tique e o fechamento diário das 00:10 BRT lê um
   Lab parado.
   ```
   ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh ops python infra/scripts/meme_rule_set.py --set-param trailing_arm_x=null --rule-set operator/5 --apply --reason "18/09 23:5xZ: trailing_arm_x=1.0 (22:47Z, trailing 20 % sempre) e recusado por ExitRules (> 1 ou null); null = armado desde a entrada, a intencao; meme-worker em laco de reinicio desde 23:24Z"'
   ssh hunter-vps "docker exec hunter-postgres-1 psql -U hunter -d hunter -c \"UPDATE meme_paper_bets SET params = params - 'trailing_arm_x' WHERE id = '01a0b6d5-b8ee-782a-9d02-ee508754f4f0' AND params->>'trailing_arm_x' = '1'\""
   ```
   Conferir: `ssh hunter-vps 'docker inspect hunter-meme-worker-1 --format "{{.RestartCount}} {{.State.StartedAt}}"'`
   (o contador para de subir) e `hb:meme:radar.lab_last_tick_at` andando.
2. **Disco da VPS — ainda 88 %.** Mesmo comando do turno anterior (devolve ~200 GB, não apaga dado):
   `ssh hunter-vps 'docker image prune -a -f --filter until=72h && docker builder prune -f --filter until=72h && df -h /'`
3. **Próximo `compose.sh update`:** leva a T4.65 (quando commitada) e a T4.63; depois instalar o cron
   `hunter-outbox` (`infra/vps/README.md`) e rodar a primeira fatia.
4. Decisões de escopo pendentes (turno anterior): `opportunity_history` a 4,2 GB/dia; retenção do backup;
   Groenlândia como `meme_event` (`.claude/state/plantao-meme/baha-2026-09-18-1950.md`).

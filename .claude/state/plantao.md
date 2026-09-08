# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-08, **meio-dia** (12:30–12:55Z / 09:30–09:55 de Brasília).
Primeiro turno **de volta no Claude Code** (`c2ee96b`). Plantão de documentação e
medição: nenhuma linha de código tocada, nenhuma suíte rodada, `.env*` intocado.

## O que mudou neste turno

- **O Lab está rodando e agora está medido.** A linha **paper** do momentum (`v3`,
  `purpose = paper`) foi ativada pelo Everton em **2026-09-08 05:57:30Z** (02:57 de
  Brasília) pelo caminho auditado, e emite desde 06:00:09Z. O **replay histórico**
  (T3.19b) rodou 31 dias reais nas duas estratégias de pesquisa.
- **Três avaliações datadas acrescentadas**, com SQL da VPS e saída real colados:
  [[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]] e a **primeira** da
  [[EXP-0005-momentum-paper]]. Nenhuma seção anterior foi tocada (append-only).
- **Seção nova "Replay histórico (rotulado `replay`, D14/D15)"** nas EXP-0001 e
  EXP-0002, com recibo de `replay_runs` e o rótulo explícito: **replay não conta
  para a régua `validada`/`reprovada`**.
- **Changelog** com os **47 commits** de `abf8e80..d91fac8`, uma entrada por commit.
- **Bugs:** dois fechados (`market_betas` vazia; 160 pyright), um fechado por
  descrição superada (candles 11 dias), dois abertos (backfill *newest-first* que
  deixou o BTC em 14 dias; `compose.sh update` que não sobe serviço de perfil novo
  e dá falso positivo no `migrate`).
- **Catálogo de estratégias reexportado** do banco da VPS: 7 de 19 páginas mudaram.
- **[[Sexta-feira no Hermes]]** marcada como histórico: a casa voltou ao Claude Code.

## Números do turno (`as_of = 2026-09-08T12:00:00Z`, `read_at = 12:34:22.305724Z`)

| População | Avaliáveis com `R_net` | Expectancy | PF | Dias |
|---|---|---|---|---|
| momentum `v2` `prospective` | 49 | −0,1363 R | 0,7210 | 1 |
| momentum `v1` `prospective` (fechada) | 929 | −0,1905 R | 0,6131 | 3 |
| momentum `v3` **paper** | 30 | −0,2550 R | 0,5202 | 1 |
| volume_anomaly `v2` `prospective` | 194 | −0,3714 R | 0,4546 | 1 |
| volume_anomaly `v1` `prospective` (fechada) | 2.079 | −0,3301 R | 0,5337 | 3 |
| momentum `v2` **replay** `f8d8279c` | 222 | −0,1717 R | 0,6454 | 24 |
| volume_anomaly `v2` **replay** `bac27c12` | 337 | −0,5957 R | 0,2798 | 29 |

Sete populações, sete sinais negativos, **todas `inconclusivo`** pela régua
(100 outcomes avaliáveis **E** 30 dias distintos). `PnL de carteira` e
`Max Drawdown de carteira`: **não aplicável** em todas.

## Saúde

| Onde | Estado |
|---|---|
| VPS | **Verde.** 13 contêineres de pé. `hb:market:binance:0of4` conectado, 318 assinaturas, 53 mercados, 0 gaps, 0 descartes; `covered_until` 12:41:37Z contra relógio de 12:41:38Z. Spot conectado, 15 mercados, 0 gaps. `hb:strategy:shadow`: 3.187 barras, 1.081 `unavailable` (33,9 %), 39 acompanhamentos, outbox 0, erros 0. `hb:execution:paper`: equity 19.333,0111164813 USDT, `kill_switch = ACTIVE` (menos restritivo), 0 posições. Disco 32 % de 348 G, load 4,86 em 12 vCPU. |
| Local | **Postgres desligado** (conexão recusada). Sem impacto: tudo foi lido da VPS. |

## Higiene da base Obsidian — rodar em todo plantão

```
uv run python infra/scripts/obsidian_lint.py
```

Somente leitura, relatório em português, sai 1 quando há achado. Consertar o que
for da base (link morto, frontmatter faltando, nota órfã); **não** consertar o que
tiver dono em outra tarefa em voo — esse vai para a `ALLOWLIST` do script com
motivo, ou para `obsidian/07-BUGS/Open Bugs.md`. Um achado `exp_reescrita` nunca
se resolve reescrevendo de volta: ou a alteração foi indevida e se desfaz, ou é
uma leitura nova e vira seção nova, datada, abaixo. Padrão completo em
`docs/OBSIDIAN.md`.

**Passo do catálogo de estratégias** (o banco vive na VPS; esta máquina só tem SSH):

```
tar czf /tmp/estrat.tgz -C obsidian/03-TRADING Estrategias
tar czf /tmp/exps.tgz  -C obsidian 05-EXPERIMENTS
scp /tmp/estrat.tgz /tmp/exps.tgz hunter-vps:/tmp/
ssh hunter-vps 'docker cp /tmp/estrat.tgz hunter-api-1:/tmp/ && docker cp /tmp/exps.tgz hunter-api-1:/tmp/'
ssh hunter-vps 'docker exec hunter-api-1 sh -c "cd /app/obsidian/03-TRADING && tar xzf /tmp/estrat.tgz; cd /app/obsidian && tar xzf /tmp/exps.tgz"'
ssh hunter-vps 'docker exec hunter-api-1 python infra/scripts/export_strategies_to_obsidian.py --dry-run'
```

**Semear as páginas locais no contêiner antes de rodar é obrigatório.** O exportador
só reescreve o bloco entre os marcadores, mas ele lê as páginas de
`05-EXPERIMENTS` para preencher a coluna **Veredito** das páginas de família —
sem elas, o veredito sai `-` e a página de família perde informação.

## Em voo (não tocar nos arquivos)

| Tarefa | Arquivos |
|---|---|
| T3.24/T3.25 (web) | `apps/web/**` |
| Design (auditoria T3.23) | `docs/DESIGN.md`, `docs/**` |
| T3.15d (owner DSN + `compose.sh`) | `infra/docker/**`, `infra/vps/**` |

## Próximo passo

1. **T3.15d** (`devops-engineer`): DSN de owner só em `migrate`/`ops`, mais as duas
   correções do `compose.sh` registradas no adendo do brief.
2. **Backfill do BTC**: priorizar o mercado de referência do `beta_v1` na fila, senão
   nenhum β sai válido e a ponte segue recusando por `beta_unavailable`.
3. **T3.10 / parecer do M3**: o relatório estendido já está reescrito (`4deef9d`);
   falta o parecer da Sexta-feira depois das revisões pendentes.
4. **Próximo plantão**: uma avaliação datada por experimento ativo, como sempre.

## O que preciso do Everton

**Nada para o Lab continuar.** Duas coisas quando ele quiser:

1. **Ligar `ENABLE_PAPER_AUTONOMY`** na VPS é decisão dele. Hoje está `false`, e por
   isso a linha paper emite 154 sinais e produz **0 propostas, 0 posições, 0 trades**.
   **Recomendo esperar:** com β indisponível em 100 % dos mercados (199 de 200
   revisões por corte em `insufficient_history`), o Risk Engine recusaria as
   propostas de qualquer jeito.
2. **Saber que o número está negativo nas sete populações medidas.** Isso é o Lab
   funcionando. Quando a régua de 30 dias fechar, o veredito provável do
   `volume_anomaly` é `reprovada` — melhor ele ver isso chegando de longe.

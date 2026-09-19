# T4.72 — retomar o caminho paper de perps/spot (opção A: nada paralelo)

**Pedido:** Everton quer "operar no mercado do Lab também" (perps/spot, ao lado
do funil de memes). O brief original pedia uma peça nova (`ENABLE_PERPS_PAPER_EXECUTION`
+ lógica própria de proposta/fill). Investigação mostrou que essa peça **já existe**,
auditada e revisada (guardian/security/db), desde T3.14/T3.15/T3.29: a ponte
`ENABLE_PAPER_AUTONOMY` (`packages/core/hunter_core/admission/*`,
`services/execution-worker/hunter_execution_worker/bridge*.py`). O coordenador
confirmou a opção A: terminar de ligar esse caminho, não construir um segundo.

## 1. Causa raiz de "0 `trade_proposals`, 0 `trades`" (confirmada, não é bug)

Não é falta de evidência do Lab nem defeito no pipeline. É a combinação de duas
coisas, as duas **deliberadas e faltando por falta de ato, não por falha**:

1. **`ENABLE_PAPER_AUTONOMY=false`** — `packages/core/hunter_core/settings.py:103`
   documenta: "default `false`, e continua `false` em produção até os nove itens
   do T3.9 serem aceitos" (`docs/plans/M3.md`). O checklist de aceite vive em
   `docs/ACTIVATION.md` §8.
2. **Zero linhas em `agents`** — a tabela que diz "esta carteira roda esta versão".
   `bridge_screen._agent_for` só admite um sinal `purpose=paper` se existir uma
   linha `agents` com `status='enabled'` para (org, portfolio, strategy_version_id).
   Ativar uma versão (`activate_strategy_version.py --paper-line`) não cria essa
   linha — é um ato separado, auditado, só do Everton (§8a).

**Linha do tempo medida (não é opinião, é o que os arquivos de estado dizem):**
- 08/09: `momentum v3` ativada (`purpose=paper`), 154 sinais emitidos, **0**
  propostas — `ENABLE_PAPER_AUTONOMY=false` e `agents` vazia.
- 10/09 (T3.71, última medição real): checklist §8 parcialmente verde — β válido
  em só 12/18 mercados SPOT monitorados (23/366 sinais passariam `d1`+β), `agents`
  ainda **0** linhas, `hb:execution:paper` com `equity=19333.0111164813`,
  `paper_autonomy=false`.
- 12/09 em diante: o time pivota para o funil de memes (`foco-total-memes`,
  16/09 — "perps/spot só manutenção"). O passo 8a (`agents`) nunca é retomado.
- 19/09 (hoje): os mesmos números do brief (`equity 19 333`, `0 positions`,
  `trade_proposals`/`trades` "0 rows ever") são **os mesmos** de 10/09 — nada
  mudou porque ninguém rodou o passo 8a, não porque surgiu um problema novo.

**Conclusão:** construir uma peça paralela (`ENABLE_PERPS_PAPER_EXECUTION`)
duplicaria — e arriscaria colidir com — uma ponte já revisada pelo
risk-engine-guardian que cobre position sizing, kill switch, `avgPrice`,
participação de 1%/min, risk profile e geometria. O caminho certo é terminar
o passo 8a e então virar a flag que já existe.

## 2. Candidatas do Lab (evidência no vault, `obsidian/05-EXPERIMENTS`)

| Estratégia | Ficha | `purpose` hoje | Veredito |
|---|---|---|---|
| `momentum v3` | [[EXP-0005-momentum-paper]] | **`paper`, `active`** (ativada 08/09, D10) | `inconclusivo` — 30 outcomes avaliáveis em 1 dia (limiar: 100 **e** 30 dias); expectancy hipotética −0,2550 R nesse corte pequeno. É a **única** versão que já passou pelo caminho auditado de virar linha paper. |
| `volume_anomaly v2` | [[EXP-0002-volume-anomaly-v1]] | `research_only` | `inconclusivo` (194 avaliáveis/1 dia em 08/09) — nunca teve `--paper-line` |
| `trendline_breakout v1` | [[EXP-0016-trendline-breakout]] | `research_only` | `inconclusivo` (47 avaliáveis/14 dias) — nunca teve `--paper-line` |

Nenhuma tem veredito **positivo** com amostra suficiente (100 outcomes E 30
dias) — nem poderia ter, porque a carteira nunca preencheu com fills reais
(o próprio ponto do EXP-0005: sem `ENABLE_PAPER_AUTONOMY=true` os dois lados
do contraste shadow-vs-paper são o mesmo lado). Por isso a recomendação é
**momentum v3**, não por desempenho comprovado, mas porque é a única com
protocolo congelado e histórico auditado — exatamente o caso "sem candidata
positiva, ligar o caminho mesmo assim atrás de uma flag" do brief original.
`volume_anomaly`/`trendline_breakout` continuam só pesquisa (`research_only`)
até alguém rodar `--paper-line` para elas também — não fiz isso aqui: é uma
decisão de qual experimento abrir a seguir, não parte deste ato de
infraestrutura.

## 3. O que foi implementado

- **`infra/scripts/link_portfolio_agent.py`** (+ `link_portfolio_agent_plan.py`,
  separado só para caber no limite de 350 linhas) — o ato auditado do §8a,
  repetível: `--dry-run` por padrão, `--yes` escreve o `INSERT`/`UPDATE` em
  `agents` e a linha de `audit_logs` (`agent.created`/`agent.reactivated`) na
  mesma transação. Recusa versão que não seja `purpose=paper`/`status=active`,
  sempre escreve `allowed_directions=ARRAY['long']` (SPOT sem alavancagem —
  mesma razão do §8a original), reativa em vez de duplicar se o agente já
  existir pausado.
- **`infra/scripts/tests/test_link_portfolio_agent.py`** — 10 casos
  (testcontainers): recusas (org/versão/status/purpose desconhecidos, `--dry-run`
  + `--yes` juntos), preview sem escrita, criação com `allowed_directions=['long']`
  e 1 `audit_logs`, replay idempotente (0 escritas), reativação de agente pausado
  (reusa a linha, não duplica), e a prova final de que o agente criado é
  exatamente o que `bridge_screen._agent_for` seleciona.
- **`docs/ACTIVATION.md`** — nova seção `## 8c` com a causa raiz datada, o
  comando do script (local e via `ops` na VPS) e uma tabela remedindo (ou
  marcando como "precisa remedir") cada linha do checklist §8.
- **`.env.example`** — `ENABLE_PAPER_AUTONOMY=false` documentada (existia só
  nos `docker-compose.yml`/`docker-compose.prod.yml` como passthrough com
  default `false`; faltava no exemplo).
- **`infra/vps/docker-compose.prod.yml`** — **nenhuma mudança**: o passthrough
  `ENABLE_PAPER_AUTONOMY: ${ENABLE_PAPER_AUTONOMY:-false}` já existe na linha
  365, feito em T3.15.

Nenhum arquivo de `services/strategy-worker` ou `services/execution-worker`
foi tocado — a ponte já faz o que o brief pedia (sinal → proposta → risco →
fill paper → posição → trade); só faltava a linha `agents`.

## 4. Checklist §8 — o que ainda está vermelho, e por quê

Não tenho acesso SSH à VPS neste sandbox (só testcontainers locais), então
**não pude remedir ao vivo**. Última medição real: 10/09 (T3.71). Tabela
completa e consultas exatas em `docs/ACTIVATION.md` §8c. Resumo:

- **Linha 1 (`agents`):** era vermelha por falta de ato; agora há script
  pronto, mas **ninguém rodou `--yes` ainda** — continua vermelha até alguém
  rodar.
- **Linha 3 (β válido):** era **amarela** em 10/09 (12/18 mercados, 23/366
  sinais). Nove dias se passaram com o time no funil de memes — não sei dizer
  se o job horário de β e o backfill continuaram rodando sem verificação nova.
  **Precisa remedir antes de decidir**, com a consulta do §8/§8c.
- **Linhas 2, 4, 5, 6, 7, 8:** verdes em 10/09; sem sinal de regressão nos
  arquivos de estado, mas nenhuma foi remedida por mim hoje — só ler de novo
  no heartbeat confirma.

## 5. Passo a passo exato para o Everton

1. **Deploy** deste commit (traz o script para a imagem `ops`):
   `ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh update'`
2. **Remedir a linha 3** (β) com a consulta de `docs/ACTIVATION.md` §8/§8c antes
   de decidir — se ainda estiver parcial, decidir se liga mesmo assim (mesma
   régua de sempre: "sem β validado, mercado fica só em shadow", nada muda
   nisso quando a flag for ligada).
3. **Vínculo `agents` (dry-run, depois `--yes`):**
   ```
   bash infra/vps/compose.sh run --rm ops python infra/scripts/link_portfolio_agent.py \
       --org-slug ever --strategy momentum --version v3 --dry-run
   bash infra/vps/compose.sh run --rm ops python infra/scripts/link_portfolio_agent.py \
       --org-slug ever --strategy momentum --version v3 --yes --actor "Everton"
   ```
4. **Ligar a flag** no `.env` da VPS: `ENABLE_PAPER_AUTONOMY=true`, depois
   `bash infra/vps/compose.sh update` (recria o `execution-worker` com a env
   nova).
5. **Primeiros 30 minutos — o que ler em `hb:execution:paper`:**
   - `paper_autonomy=true` (confirma que a env pegou);
   - `bridge_candidates` > 0 (a ponte está vendo o sinal da `momentum v3`,
     não só o `agent_unavailable` de antes);
   - `pending_requests` variando (algo está sendo avaliado a cada passo, não
     travado em zero);
   - se `open_positions` continuar 0 por muito tempo, olhar as recusas
     nomeadas da tabela de `docs/ACTIVATION.md` §8 ("Nota operacional"):
     `avg_price_*`, `beta_unavailable`, `spot_volume_below_floor`,
     `duplicate_position` — cada uma tem motivo próprio no log, nenhuma é
     silenciosa;
   - `equity` e `kill_switch` não devem se mexer fora do esperado (kill switch
     continua `ACTIVE` = estado menos restritivo, não alarme).
6. Nenhum passo daqui move dinheiro real. `ENABLE_LIVE_TRADING` continua
   `false` e fora de escopo (Fase 4).

## 6. O que Binance real (Fase 4) exigiria — não implementado aqui

Fora de escopo deste ato (paper), registrado porque o brief perguntou:

- `LiveExecutionAdapter` continua levantando `LiveTradingDisabled`
  (`hunter_core.execution`) — nenhum código de ordem real foi tocado ou
  testado aqui.
- Chaves de API da Binance descriptografadas só chegariam ao
  `execution-worker` (nunca ao `api`), via um cofre ainda não desenhado —
  `docs/ARCHITECTURE.md` §4 já reserva esse isolamento, mas o mecanismo de
  segredo (KMS/Vault) não existe no repo.
- `ENABLE_LIVE_TRADING=true` exige a revisão explícita do risk-engine-guardian
  e do security-reviewer descrita no `CLAUDE.md` ("hard rules"), decisão que
  só o Everton toma, com aprovação por escrito (mesmo padrão do teste real de
  memes, `06-DECISIONS/2026-09-12-teste-pequeno-meme-real`).
- Nada disso é necessário para o pedido de hoje ("operar no Lab também" em
  paper) — só citado para não confundir "ligar `ENABLE_PAPER_AUTONOMY`" com
  "ligar dinheiro real".

## 7. Testes e verificações rodadas (saída real)

```
$ uv run pytest infra/scripts/tests/test_link_portfolio_agent.py -q
..........                                                               [100%]
10 passed in ~25s

$ uv run ruff check infra/scripts/link_portfolio_agent.py infra/scripts/link_portfolio_agent_plan.py infra/scripts/tests/test_link_portfolio_agent.py
All checks passed!

$ uv run ruff format --check <mesmos três arquivos>
3 files already formatted

$ uv run pyright <mesmos três arquivos>
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 1006 files; 0 over budget, 0 grandfathered
```

Não rodei a suíte completa da ponte de admissão (`services/execution-worker`,
`services/strategy-worker`) porque **nenhum arquivo dela foi tocado** — só
`infra/scripts/*`. Rodar essas suítes é responsabilidade de quem mexer
naqueles pacotes; recomendo rodá-las mesmo assim antes de commitar, para
confirmar que nada mudou por engano.

## 8. Arquivos criados/modificados (não commitados)

- `infra/scripts/link_portfolio_agent.py` (novo)
- `infra/scripts/link_portfolio_agent_plan.py` (novo)
- `infra/scripts/tests/test_link_portfolio_agent.py` (novo)
- `docs/ACTIVATION.md` (nova seção `## 8c`)
- `.env.example` (`ENABLE_PAPER_AUTONOMY` documentada)
- `.claude/state/notes-T4.72.md` (este arquivo)

`infra/vps/docker-compose.prod.yml` foi conferido e **não precisou de
mudança** (passthrough já existia desde T3.15).

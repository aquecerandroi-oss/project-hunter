---
tags: [trading, execucao, m3, m4]
updated: 2026-10-17
status: implementado e rodando na VPS em modo paper com a ponte desligada; o caminho autônomo nunca rodou de ponta a ponta (aceite operacional em T3.29)
owner: sexta-feira
---

# Execution Engine

## Status

> **Atualizado em 2026-09-08 — a frase antiga desta seção deixou de ser verdade.** Ela dizia
> "planejado (…) `hunter_core.execution` e o `execution-worker` não têm implementação hoje". O
> `execution-worker` **existe, foi provado e roda na VPS** (T3.5/T3.5b/T3.5c, `7ecafd2` → `12edda3`):
> admissão, ciclo de ordem por fill numa transação só, proteções duráveis, marcação a mercado antes
> do kill switch, expiração de reserva, recuperação após restart, heartbeat e `/ready`. Ver
> [[Risk Engine]] para o que existe peça a peça.

**O que continua verdadeiro, e é o que importa:** a **ponte sinal → admissão está desligada**
(`ENABLE_PAPER_AUTONOMY=false`) e **o caminho autônomo nunca rodou de ponta a ponta**. A última
leitura registrada é **154 sinais paper, 0 propostas, 0 posições, 0 trades**
([[Diario/2026-09-08]]). O modo Live continua proibido antes da Fase 4.

## Pré-requisitos efetivos da autonomia paper (revisão da Astra, 2026-09-08)

A revisão [[2026-09-08-shadow-lab-pronto]] mostrou que as quatro condições que a base citava **não
são todas**. Estes são os sete itens do aceite operacional
(`.claude/state/brief-T3.29-autonomy-acceptance-run.md`); o Everton só liga a chave quando **todos**
estiverem verdes, e cada linha precisa de **medição na VPS**, não de leitura de código.

| # | Item | Estado em 2026-09-08 | Onde a falha mora |
|---|---|---|---|
| 1 | **Admissão** — vínculo em `agents` habilitado para a versão e a carteira corretas | **não medido** | `bridge_repo.py:130`, `bridge_screen.py:215` |
| 2 | **Ordem** — `avgPrice` disponível para os filtros MARKET do universo executável | **não medido** (o leitor devolve `None` hoje) | `market_data.py:149`, `entry_inputs.py:62` |
| 3 | **Proteção** — intenção `pending_degraded` se recupera após restart, com a quantidade remanescente e **sem venda duplicada** | **não medido** (sem teste) | `protection.py:183`, `protection.py:296` |
| 4 | **MTM** — qualidade das marcas (`mark_quality`), não só a frescura da escrita | **não medido** (`mtm_fresh` mede a escrita) | `bridge_inputs.py:180`, `cycles.py:275`, `health.py:95` |
| 5 | **Integração** — queda de WS com lacuna e perda de Redis **durante a decisão**, com SPOT integrado | **não medido** (a própria prova V6 declara descoberto) | `tests/integration/paper/test_v6_stale_data_reconnect_restart.py` |
| 6 | **Backup** — dump **restaurável**, verificado agora (não "cron configurado") | **não comprovado** — a comprovar em T3.29 | `docs/reports/M3.md:261`, `infra/scripts/bootstrap_vps.sh:346` |
| 7 | **DSN de dono** — `DATABASE_URL_MIGRATIONS` fora do bloco compartilhado dos serviços de runtime | **aberto** (dono T3.15d) | `infra/vps/docker-compose.prod.yml:30` e `:59` |

**"Não medido" é diferente de "não funciona".** Nenhuma destas linhas afirma defeito em produção: cada
uma nomeia um cenário concreto de falha que **ninguém verificou**, e é por isso que a chave continua
desligada. Os cinco primeiros itens estão em [[Open Bugs]] com arquivo:linha; o β indisponível em
100% dos mercados é uma razão adicional para esperar — o Risk Engine recusaria as propostas de
qualquer jeito.

## Interface (implementada no `execution-worker`; o adaptador Live continua só como contrato)

```python
class ExecutionAdapter(Protocol):
    mode: ExecutionMode  # PAPER | SHADOW | LIVE

    async def submit(self, order: OrderIntent, market: MarketState) -> ExecutionResult: ...
    async def cancel(self, order_id) -> None: ...
    async def mark_to_market(self, positions, prices) -> list[PositionUpdate]: ...
```

`ExecutionAdapter` é o único lugar do sistema com efeitos de execução.

## Três modos planejados

- **Paper** (M3): fill simulado contra o book real (walk do book), com slippage, fee e latência simulados. Ver [[Paper Trading]].
- **Shadow** (M3/M6): grava ordens e fills com `simulated=true`, sem alterar cash — idêntico ao paper em tudo o mais; serve para comparar estratégias sem comprometer capital virtual.
- **Live** (Fase 4 — **não antes**): `LiveExecutionAdapter` existe só como interface e levanta `LiveTradingDisabled` enquanto `ENABLE_LIVE_TRADING=false` (valor atual em `.env.example`) ou o entitlement da organização não permite. **Não há UI para live trading e não deve haver antes da Fase 4** (regra explícita de `CLAUDE.md`).

## Fluxo planejado (execution-worker)

1. Entrada: `ExecutionAdapter.submit(OrderIntent)` a partir de `proposals.decided` (approved).
2. Cria `orders`, `fills`, `positions`; ordens filhas `stop`/`target` como registros `pending` (não há exchange para segurá-las em paper).
3. Gestão a cada 1 s: marcação a mercado, verificação de stop/alvos/invalidações/expiração, limites de portfolio.
4. Saída: fecha posição → `trades` com `exit_reason`, snapshots de entrada/saída, `r_multiple`.
5. Equity: snapshot por minuto em `portfolio_equity_snapshots`.

**Falha planejada:** worker reinicia → relê posições `open` do Postgres e retoma; propostas `approved` sem ordem após 30 s expiram e nunca são executadas tarde; se o mercado ficar `degraded`, o worker não abre posição nova mas continua gerenciando saídas com o último preço válido.

## Linha B3 (desenho, 17/10/2026 — nada implementado)

Decisão do Everton: robô de execução real dele na B3, via MetaTrader 5, na conta dele na Rico. Desenho em
`docs/design/robo-b3-mt5.md`, fechado com a Astra em [[Dialogos/robo-b3-mt5]]. O `LiveExecutionAdapter` da linha
cripto **não muda**; a linha B3 teria adaptador, serviço e flag próprios, e depende do ADR que só o Everton assina.
Lições de execução que valem para qualquer corretora com stop guardado no servidor:

- **Em conta *netting*, fechar não é só-redução.** O stop do servidor é um segundo remetente; um "vende 1" nosso no
  mesmo instante deixa a conta vendida. A saída segura mexe só no colchete (`sl`/`tp`) da própria posição, e o servidor
  fecha; nenhuma ordem direcional de saída na v1.
- **Batimento não é exclusão** entre dois processos; um só remetente de ordens (o EA do terminal só avisa o celular).
- **Nenhuma mutação sem identidade e autoridade verificadas** — nem recolocar um stop: "recolocar se ausente" não é
  escrita condicional.

## Relacionadas

[[Paper Trading]] · [[Risk Engine]] · [[Portfolio]] · [[Workers]] · [[Open Bugs]] ·
[[2026-09-08-shadow-lab-pronto]] · [[Diario/2026-09-08]] · [[Dialogos/robo-b3-mt5]]

## Fontes

`docs/PIPELINE.md` §8, `docs/ARCHITECTURE.md` §6, `CLAUDE.md` ("Hard rules"), `docs/ROADMAP.md` (Milestones 3–4), `docs/ACTIVATION.md` §8, `.claude/state/brief-T3.29-autonomy-acceptance-run.md`

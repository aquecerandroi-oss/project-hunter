---
tags: [decisao, shadow-lab, universo, custo, m3]
titulo: O universo de pesquisa do Shadow Lab vira "markets com >= 90 dias de candles_1m"
data: 2026-09-10
updated: 2026-09-10
owner: backend-specialist
origem: .claude/state/brief-T3.82-universo-de-pesquisa.md
status: registro
decided_on: 2026-09-10
by: everton
---

# O universo de pesquisa vira "mercados com >= 90 dias de histórico" (T3.82)

**Aprovação do Everton**, 2026-09-10, por volta de 19:1x BRT: *"boaaa perfeito"*, sobre a proposta
que a T3.74g já tinha deixado registrada como pergunta em aberto (`.claude/state/notes-T3.74g.md`
§5, item iii): *"o custo é linear no universo, e as versões `research_only` decidem sobre ~200
mercados quando só 16 têm 90 dias de histórico"*.

## O problema, com números

- 200 perpétuos monitorados; as 10 versões vivas do Shadow Lab decidem sobre os 200, em todo
  fechamento de barra de 15 min (a grade de `momentum_v1`) — até ~2 000 avaliações por fechamento.
- Só 16 mercados têm >= 90 dias de `candles_1m`: **ARB, BNB, BTC, DASH, DOGE, ETH, LINK, NEAR,
  PROM, SAHARA, SOL, SUI, TAO, UNI, XRP, ZEC**.
- Os outros 184 têm o mínimo de contexto para uma decisão isolada (26 h, T3.54b), mas **nunca**
  vão passar pelo funil de validação (replay de 31 d + réplicas + protocolo de replicação,
  `docs/plans/SHADOW-LAB.md` §"Funil de validação") sem 90 dias de histórico real. Toda decisão
  viva sobre eles é custo de pesquisa não validável, não uma população menor do mesmo experimento.
- A T3.74f/g já tinham medido o custo desse universo cheio: com quatro shards, uma barra de 15 min
  ainda levava 37-43 s para drenar (`.claude/state/notes-T3.74f.md`, `notes-T3.74g.md`).

## A regra, tal como implementada

Um mercado entra no universo de pesquisa quando:

1. é perpétuo e continua monitorado (`markets.is_monitored`) — a exclusão de spot da T3.73
   permanece intacta, é a porta anterior a esta;
2. `min(candles.open_time)` das suas velas 1m **finais** é `<= agora − SHADOW_UNIVERSE_MIN_HISTORY_DAYS dias`
   (padrão 90; `0` desliga a porta e reproduz o comportamento de hoje).

A verificação roda **antes** do semáforo do despachante concorrente (`BarDispatcher`,
`hunter_strategy_worker.pre_dispatch.refuse_before_dispatch`), na mesma porta onde a recusa de
shard (T3.74f) já mora — uma barra fora do universo é confirmada (ACK) sem nunca chegar a
`load_market`, ao contexto ou a `evaluate_slot`, e nenhuma linha é persistida. Aplica-se
identicamente a toda versão viva, `research_only` **e** `paper` — não é uma regra de elegibilidade
de versão (nenhum `code_ref` muda, nenhuma versão nova é derivada) nem um limite de risco.

Cache em processo (não Redis): a resposta não precisa de acordo entre shards, e uma query por hora
sobre ~200 mercados é mais barata que um round-trip de Redis por barra. TTL de 1 h — um mercado que
cruza os 90 dias entra no universo na hora seguinte, nunca instantaneamente; aceito por desenho.

## Onde mora

- `services/strategy-worker/hunter_strategy_worker/universe.py` — a regra, o snapshot, o cache.
- `services/strategy-worker/hunter_strategy_worker/pre_dispatch.py` — a recusa antes do despachante
  (junto da recusa de shard).
- `ShadowConfig.universe_min_history_days` (`SHADOW_UNIVERSE_MIN_HISTORY_DAYS`, padrão 90).
- Métrica: `hunter_shadow_bars_skipped_total{reason="universe_history"}`.
- Heartbeat: `universe_size`/`universe_total`/`universe_min_history_days` em
  `hb:strategy:shadow[:{i}of{N}]`, somados entre shards em `GET /api/v1/system/latency`
  (`research_universe`).
- Documentação normativa: `docs/PIPELINE.md` §6b, `docs/plans/SHADOW-LAB.md`
  §"Universo de pesquisa (T3.82)".

## O que isto NÃO muda

- **Nenhum limite de risco.** `packages/risk-core` nunca vê este código; nada aqui dimensiona
  posição, nem toca `risk_per_trade_pct` ou tetos de exposição.
- **Nenhuma versão, nenhum `code_ref`, nenhuma derivação.** O catálogo de estratégias
  (`activate_strategy_version.py`, `strategy_versions`) é lido e escrito exatamente como antes.
- **O universo executável da carteira paper é outro conceito**, no `execution-worker`/ponte de
  admissão (`bridge_universe.py`) — intocado por esta tarefa.
- **O replay (`replay/*`) já trabalha sobre listas explícitas de mercado** — nada muda lá; a
  restrição de universo é só do caminho ao vivo.

## Medição esperada, pós-deploy (tarefa do orquestrador)

- Avaliações por fechamento de 15 min: 16 mercados × 10 versões = 160, contra ~2 000 antes —
  redução de ~92 %.
- SQL para confirmar que os sinais do dia vêm só dos 16 mercados elegíveis:

```sql
select m.symbol, count(*) as sinais
from agent_signals s
join markets m on m.id = s.market_id
where s.emitted_at >= now() - interval '1 day'
group by m.symbol
order by sinais desc;
-- toda linha deve estar entre os 16 símbolos listados acima
```

## Relacionadas

`docs/PIPELINE.md` §6b · `docs/plans/SHADOW-LAB.md` §"Universo de pesquisa (T3.82)" ·
`.claude/state/notes-T3.74g.md` §5 (item iii, a pergunta original) · `.claude/state/notes-T3.82.md`

## Fontes

`.claude/state/brief-T3.82-universo-de-pesquisa.md` · aprovação verbal do Everton, 2026-09-10
19:1x BRT ("boaaa perfeito")

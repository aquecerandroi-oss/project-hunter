# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-05 (criado pelo orquestrador ao instalar o turno horário "sexta-feira-plantao").

## Estado ao instalar o plantão
- M1: T1.1–T1.6 commitadas; T1.6b (performance: parse leve, hot state em lote, sharding) com três implementadores em voo (`packages/exchange-adapters`, `services/market-worker`); T1.7 (testes) com o test-engineer em `tests/integration`. Stack local no ar com `MARKET_UNIVERSE_SIZE=50` (override local) até T1.6b provar 200.
- M2: plano com DECISÃO CONJUNTA fechada (`docs/plans/M2.md`); onda 1 (T2.1 schema, T2.2 features) só depois do fechamento do M1.
- VPS Contabo pronta (`ssh hunter-vps`); falta o Everton criar o `.env` lá e fazer os logins (`claude`, `codex login`).

## Precisa do Everton
- Nada bloqueante. Opcional: `.env` e logins na VPS; colar o hook `Stop` de voz no `.claude/settings.json`.

---
tags: [knowledge, perps, spot, paper, lab, autonomia, t4-72, m3]
tema: por que a mesa em papel de perps/spot nunca operou — falta de dois atos (flag + vínculo `agents`), não defeito
fonte: .claude/state/notes-T4.72.md (T4.72, 19/09/2026)
fonte_url:
lido_em: 2026-09-19
evidencia: medição própria — estado da VPS (hb:execution:paper, tabelas agents/trade_proposals/trades) comparado com T3.71 de 10/09
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-19
confiança: "backtest do autor"
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0144 — A mesa em papel de perps/spot está parada por ato, não por bug (T4.72, 19/09/2026)

## O que afirma

Desde 08/09 o strategy-worker emite sinais (`momentum v3`, 154 no primeiro dia) e **nenhum** vira proposta ou trade em papel. Não é defeito: são dois atos que nunca foram feitos — (1) `ENABLE_PAPER_AUTONOMY` continua `false` de propósito até o checklist de `docs/ACTIVATION.md` §8 ser aceito; (2) a tabela `agents` (que diz "esta carteira roda esta versão") tem **zero linhas**, e a ponte de admissão só aceita sinal `purpose=paper` com uma linha `agents` `enabled`. Os números de 19/09 (`equity 19 333`, 0 propostas, 0 trades) são idênticos aos de 10/09: o time pivotou para memes e o passo 8a ficou por fazer.

## Onde foi mostrado

`hb:execution:paper` na VPS, tabelas `agents`/`trade_proposals`/`trades`, `packages/core/hunter_core/settings.py:103`, `bridge_screen._agent_for`. Linha do tempo em `.claude/state/notes-T4.72.md` §1.

## O que muda

- Não construir peça paralela (`ENABLE_PERPS_PAPER_EXECUTION`): a ponte existente já passou por guardian/security/db (T3.14/T3.15/T3.29) e cobre sizing, kill switch, `avgPrice`, participação 1 %/min, perfil de risco.
- Entregue: `infra/scripts/link_portfolio_agent.py` (+ `_plan.py`, 10 testes) — ato auditado `--dry-run`/`--yes` que cria a linha `agents` long-only e grava `audit_logs`. `docs/ACTIVATION.md` §8c com o checklist remedido.
- Candidata: `momentum v3` ([[EXP-0005-momentum-paper]]) — única com protocolo congelado; veredito **inconclusivo** (30 outcomes, expectancy −0,26 R em amostra pequena). Ligar é papel: não move dinheiro; serve para finalmente ter o contraste shadow × papel do EXP-0005.
- Cuidado com a leitura "o Lab está dando bom": o Lab que rendeu +0,103 SOL em 24 h é o de **memes** (`flow_v2/1`, [[KB-0143-o-que-antecede-o-dump|KB-0143]]); o de perps/spot não tem candidata positiva ainda.

## Próximo passo

Passo a passo do Everton em `notes-T4.72.md` §5: deploy → remedir β → `link_portfolio_agent.py --dry-run` e `--yes` → `ENABLE_PAPER_AUTONOMY=true` → ler `hb:execution:paper` nos 30 min (`paper_autonomy=true`, `bridge_candidates > 0`).

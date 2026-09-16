# T4.41 — o lote de atividade tem precedência sobre a fita por mint

**Data:** 16/09/2026 · **Origem:** KB-0116 (`obsidian/11-KNOWLEDGE/KB-0116-a-fita-ve-quanto-da-negociacao-real.md`)

## O que mudou

Até aqui o fold tentava **a fita por mint primeiro** (`swap_api_trades`) e só caía no lote
(`activity_1m`) quando ela faltava. A KB-0116 mediu as duas contra o número que a própria cadeia diz
— Δ `real_sol_reserves` entre fotos de curva:

| fonte | n | sinal igual | razão mediana | corr |
|---|---|---|---|---|
| `activity_1m` | 6 688 | **85,7 %** | **1,00** | 0,835 |
| `swap_api_trades` | 1 820 | 34,9 % | **0,00** | — |

A fita por mint escrevia praticamente zero enquanto a curva se mexia (o puxador traz uma página por
minuto e o fold creditava o minuto inteiro a ela), o que **inflava a `participation`** da porta (o
denominador `curve_volume_1m_sol` ficava pequeno demais).

**Agora:** `features_tape_sources.choose_tape` — (1) o lote; (2) a fita por mint só quando o lote não
cobriu aquele mint naquele minuto; (3) a fita **sempre** empresta `creator_sold`/`creator_net_seller`
à linha do lote (só `meme_trades` diz *quem* negociou), e só quando os conhece — um `None` não vira
`False`. `tape_source` continua dizendo qual das duas foi.

## A terceira fonte do fluxo — calculada, nomeada, **não persistida**

`features_tape_sources.chain_flow` dá o fluxo de ~60 s como Δ `real_sol_reserves` entre duas fotos de
curva (rótulo `chain_delta`), com `buys`/`sells`/`unique_buyers` **desconhecidos** (`buyers_unknown`,
`rules_criteria.py:247`) — um Δ de reservas não conta pessoas nem pernas.

**Por que não está na linha:** dois CHECKs das duas séries recusariam a linha, e nenhum deles é
contornável sem migração:

- `tape_source_is_consistent` (`0032`): `tape_source IN ('swap_api_trades','activity_1m')` **e**
  `tape_source IS NULL OR buys_* IS NOT NULL`;
- `tape_is_null_with_a_reason` (`0023`): `(buys_* IS NULL) = (net_sol_flow_* IS NULL)`.

Escrever `chain_delta` exige uma migração que alargue o rótulo e separe o fluxo do grupo tudo-ou-nada
da fita. Não abri essa migração aqui porque a `0047` está em voo com outro agente (T4.39) e uma
`0048` encadeada nela quebraria o `alembic check` do HEAD se aquela não entrar. **Decisão registrada
como pendência**, com a função pura, testada e documentada (`docs/DATABASE.md` §44.2).

## Arquivos

- `services/meme-worker/hunter_meme_worker/features_tape_sources.py` (novo — a precedência e o Δ da cadeia)
- `services/meme-worker/hunter_meme_worker/features_tape.py` (de 394 para 258 linhas; `_MONEY` → `MONEY_QUANTUM`)
- `services/meme-worker/hunter_meme_worker/{fold,fast_lane}.py` (chamam `choose_tape`)
- `services/meme-worker/tests/{test_tape_precedence,test_activity_persistence}.py`
- `docs/DATABASE.md` §44.2, `docs/RISK_ENGINE_MEME.md` §4

**Nota de árvore compartilhada:** o texto dos dois docs e o `fast_lane.py` já tinham entrado no HEAD
pela `f806ea13` (commit da T4.35) sem o `features_tape.py` que os sustenta — o HEAD estava com
`ImportError` em `choose_tape` até este commit.

## O que medir depois

1. `tape_activity_pct` no heartbeat deve subir (o teste de persistência já foi de 50 % para 75 % na
   amostra de quatro mints);
2. `participation` deixa de estufar: comparar recusas `participation_above_max` antes/depois;
3. quantos minutos ficam **sem** qualquer fita — é o tamanho real do prêmio de persistir `chain_delta`.

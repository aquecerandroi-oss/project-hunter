---
tags: [experimento, session-orb, calendario, shadow-lab]
updated: 2026-09-08
status: proposto
owner: sexta-feira
exp: EXP-0010
strategy: session_orb
version: v1
result: não iniciado
evaluable: 0
days: 0
last_eval: 2026-09-08 (ativação PARADA: chave `session_orb` ausente em `strategies`, T3.33f)
---

# EXP-0010 — rompimento da faixa de abertura de sessão (`session_orb_v1`)

> **RASCUNHO do quant-engineer (T3.33, 2026-09-08).** Para a Sexta-feira arquivar em
> `obsidian/05-EXPERIMENTS/EXP-0010-session-orb-faixa-de-abertura.md` e ligar a partir de
> [[Strategy Backlog]], [[KB-0009-o-efeito-do-quarto-de-hora]],
> [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]],
> [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] e [[Experiments Index]].
> Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado.** "Hipótese" e "Protocolo" **congelados**; avaliações
> **acrescentadas** abaixo, datadas. Brief: `.claude/state/brief-T3.33c-session_orb_v1.md`.

## Hipótese (congelada)

Num perpétuo USDT, a faixa (máxima e mínima) da **primeira hora** de uma das três sessões
declaradas — Ásia 00:00 UTC (21:00 de Brasília do dia anterior), Europa 07:00 UTC (04:00 de
Brasília), EUA 13:00 UTC (10:00 de Brasília) — carrega informação: um fechamento de 15 min acima da
máxima dessa faixa, nas quatro horas seguintes, com volume relativo ≥ 1,3, tem expectancy líquida
hipotética maior que zero, com stop na **mínima da faixa** e alvo em **2 R nominais**.

**A ressalva antes da tese: cripto não tem sessão.** O mercado é 24/7 e "Ásia/Europa/EUA" é uma
convenção **nossa**, declarada em três parâmetros congelados. Esta versão existe justamente para que
a convenção possa ser refutada.

**E ela não é pescaria.** [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] e
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] já mostraram que **o relógio está
dentro dos nossos limiares sem que ninguém tenha decidido isso** (o piso de ATR% funciona, na
prática, como filtro de horário/regime). Aqui o relógio entra na **regra**, visível, com nome, e
refutável — em vez de continuar como efeito colateral.

Evidência externa: Crabel (ORB) e Zarattini & Aziz (2023, momentum intradiário no S&P 500). Índices
de ações, com abertura e fechamento de pregão reais. **Nada disso foi mostrado em cripto**, e a
transposição está declarada como minha.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = session_orb` (**família nova**, acrescentada a
  `infra/scripts/seed_reference.py`), versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/session_orb_v1.py`.
- **`code_ref`:** digest por versão; os digests de `momentum_v1` (`…ab2e0398…`) e
  `volume_anomaly_v1` (`…9b8c14ab…`) **não se movem** com esta entrega (teste).
- **Pureza:** a sessão é resolvida **a partir de `ctx.source_bar_close`**, que já está no contexto.
  `evaluate` continua sem ler relógio nenhum, e há teste que adianta o relógio do sistema em um dia
  e exige a mesma decisão.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem:** elegibilidade → resolver `(sessão, abertura)` e
  `bars_since_open` (≤ 4 → `inside_opening_range`; > 20 → `outside_session_window`) → janela →
  janela de ATR (Wilder 14 × 15 m, 97 barras, `rolling_window_v1`) → faixa de abertura das **4
  primeiras barras** da sessão → `close(t) > range_high` → volume relativo ≥ 1,3 (mediana de 96
  barras, atual excluída) → `0,006 ≤ ATR% ≤ 0,05` → guarda de tamanho:
  `1,0 ≤ (close − range_low)/ATR ≤ 2,5`, senão `REJECTED / range_geometry`.
- **Geometria:** `stop = range_low` (um dado, como a mínima da barra do pico em
  `volume_anomaly_v1`); `risk = C − range_low`; `alvo1 = C + 2·risk`; alvo informativo `C + 4·risk`.
- **Invalidação (exata): NENHUMA.** A mínima da faixa **é** o nível estrutural, e já é o stop. Uma
  regra `close_below` separada ficaria ou acima do stop (um segundo stop que ninguém declarou) ou
  abaixo dele (código morto).
- **Horizonte:** 4 h (14 400 s). **Custo declarado:** pode transbordar para a sessão seguinte; isso é
  **medido**, não suposto — a primeira avaliação reporta a fração de desfechos cuja saída cai numa
  sessão posterior.
- **Custos assumidos:** spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado,
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do SHADOW-LAB §3.
- **Parâmetros congelados:** a tabela de `.claude/state/brief-T3.33c-session_orb_v1.md` §7, 21 chaves,
  incluindo as três horas de abertura em UTC.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo
  elegível inteiro.

### Geometria — por que o alvo é em R e não em ATR

Com o stop dado pelo **dado** (a mínima da faixa), um alvo fixo em ATR faz a relação
ganho/risco nominal variar de 4:1 a 1,3:1 dentro da faixa permitida — duas estratégias com um nome
só. Com alvo em **2 R constantes**:

| risco da faixa (ATR) | ATR% | alvo | R_net no alvo | R_net no stop | equilíbrio |
|---:|---:|---|---:|---:|---:|
| 0,5 | 0,006 | fixo 2 ATR | 2,7744 | −1,3881 | 0,3335 |
| 2,0 | 0,006 | fixo 2 ATR | 0,7927 | −1,1102 | 0,5834 |
| 0,4 | 0,004 | **2 R** | 0,5440 | −1,6356 | 0,7504 |
| 1,0 | 0,006 | **2 R** | 1,5133 | −1,2112 | **0,4446** |
| 1,5 | 0,010 | **2 R** | 1,7929 | −1,0888 | 0,3778 |

O alvo constante em R mantém o equilíbrio entre 38 % e 45 % em toda a faixa permitida, e a mesma
tabela é o que fixa `range_risk_atr_min = 1,0`: abaixo disso os 20 bps de custo assumido comem a
operação antes de o mercado ter opinião (75 % de equilíbrio com faixa de 0,4 ATR).

### Premissas numéricas declaradas

As três horas de abertura são a divisão convencional de mesa cripto e **não são medidas**;
`range_bars = 4` (uma hora) é a forma de Crabel, não um ajuste; `session_window_bars = 20` limita a
sessão a cinco horas para que as três não se sobreponham na regra; `rvol_min = 1,3` é
deliberadamente mais frouxo que o 1,5 do `momentum_v1` porque a abertura de sessão já carrega uma
sazonalidade de volume.

## O que falsifica esta hipótese

- **K1/K2/K3/K4/K5** de `.claude/state/notes-T3.33.md` §5.1.
- **Específico e obrigatório:** se **uma única sessão** carregar mais de 70 % das decisões, a
  hipótese não é "sessões", é "uma hora específica", e tem de ser **reenunciada como tal antes** de
  qualquer avaliação seguinte — reenunciar depois de ver o resultado é seleção retrospectiva
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Decomposição por sessão obrigatória** na primeira avaliação: n, avaliáveis, expectancy e
  cobertura por sessão, lado a lado.
- **Se a expectancy por sessão for indistinguível entre as três**, o rótulo de sessão não está
  fazendo trabalho nenhum e o que sobra é um rompimento de faixa de 1 h qualquer — o que é uma
  hipótese diferente e mais fraca.

## O que este experimento **não** prova

- **Não decide "qual sessão é a boa".** Escolher a melhor das três depois de ver as três é
  exatamente o data snooping de [[KB-0003-rompimento-de-canal-e-data-snooping]]; qualquer versão por
  sessão única é uma versão **nova**, com janela futura reservada.
- **Multiplicidade:** uma de quatro versões abertas no mesmo dia.
- **O replay de abertura não confirma nada**; sai rotulado **REPLAY**.
- **Mistura de slot** com as outras versões.

## Avaliações (acrescentadas, nunca reescritas)

### 2026-09-08 — tentativa de ativação **PARADA antes de qualquer escrita** (T3.33f)

Não é uma avaliação: é o registro datado de que o experimento **não começou**, e por quê.

O `code_ref` existe e a imagem publicada o carrega — `docker exec hunter-strategy-worker-1 python -c
"import hunter_core.strategies.session_orb_v1"` responde `import ok session_orb_v1 v1` em
`hunter-api:cf51c7d`. O que não existe é a **linha do catálogo**: em 2026-09-08 17:36 UTC a tabela
`strategies` não tem a chave `session_orb` (13 linhas em `strategy_versions`, nenhuma dela), então
`activate_strategy_version.py session_orb v1 --dry-run` não teria o que ativar e a corrida foi
**interrompida antes** de rodar — nada foi escrito, nem um `system_events` de recusa.

O passo que falta é do operador e é uma linha só:

```
docker exec hunter-api-1 python infra/scripts/seed.py
```

`seed.py` grava as tabelas de referência (entre elas `strategies` e os rascunhos `strategy_versions`)
e **não tem `--dry-run`** — a mesma pendência aberta na T3.33e (CONCERN 1 de `notes-T3.33e.md`).
Depois dele, a sequência congelada deste experimento é: dry-run conferindo o digest
`…session_orb_v1@sha256:a4d514ad…` → ativação → 10 min de vigia de capacidade → replay de 31 d em
duas fatias com uma coorte só.

**Result: não iniciado.** **Next Action:** o operador roda o `seed.py`; a ativação e o replay
continuam válidos como escritos no protocolo acima, sem mudança.

Fonte (comandos e saídas verbatim): `.claude/state/notes-T3.33f.md`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| alvo fixo de 2 ATR | 2026-09-08 | recusado **antes** de rodar: com stop no dado, o ganho/risco varia de 4:1 a 1,3:1 | esta página, seção Geometria |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33c-session_orb_v1.md` ·
`infra/scripts/seed_reference.py` · `infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`

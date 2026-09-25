---
tags: [experimento, meme, pumpfun, paper, pre-registro, saida, trailing, m5]
updated: 2026-09-18
status: rascunho-pre-registro
owner: astra-quant
exp: EXP-M17
strategy: "meme/pumpfun - clone exato de flow_v2/2 com UMA mudanca: a saida (trailing 30 % sempre armado, alvo 2x, tempo 15 min)"
version: "gate fluxo_e_holders v2 (identico a flow_v2/2) + exit alvo_2x_trailing_30_tempo_15m v1"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
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

# EXP-M17 — regra de saida: trailing sempre armado, alvo 2x, tempo 15 min

**Rascunho de pre-registro escrito em 2026-09-18 (14:40 BRT), depois da analise R59 (`.claude/state/notes-R59.md`) e antes de o conjunto existir no banco.** Protocolo congelado na semeadura; avaliacoes acrescentadas pelo fechamento diario, nunca reescritas. Previsao padrao: `descartar`. Regua e disciplina: KB-0092 e decisao de 10/09.

## Diretiva de origem

R59 (18/09) replicou 27 regras de saida sobre a serie de 15 s (`meme_features_15s.mcap_sol`) de 391 apostas/posicoes de 16/09 12:00 BRT a 18/09 (215 mint@minuto unicos no papel; 12 posicoes reais), taxas 1,25 % por perna, stake 0,05. Achados que motivam este braco:

- O trailing do conjunto vivo (35 %, armado so depois de 1,5x) **nunca dispara** (2 saidas em 164 de `flow_v2/2`); as saidas sao `line_broken` (55 %) e `creator_dump` (33 %).
- Um trailing **sempre armado** a 30 % dispara antes dessas duas em 29 apostas e melhora 26 delas (piora 3; teste do sinal p < 0,01; Σ delta +0,14 SOL; 50 % do delta nos 3 maiores — efeito difuso).
- Alvo 2x acrescenta +0,12 SOL em 8 apostas — concentrado nas 3 maiores. Tempo 15 min nao muda nada no modo sem censura e +0,01 no modo com censura.
- **Nenhuma** regra deixa a participacao dos 3 maiores ganhos abaixo de 50 % no recorte honesto (melhor: 76 %). A vantagem **nao** esta na saida; a saida modula ±0,1–0,3 SOL por ~200 apostas.
- Alvos curtos (+25 %/+30 %), tempo 2 min e "primeira venda do criador" **pioram** a soma.

## Hipotese (congelada na semeadura)

H1: trocar a saida de `flow_v2/2` por "trailing 30 % armado desde a entrada, alvo 2x, tempo 15 min" (piso −50 %, `creator_dump` e `line_broken` mantidos) eleva o R medio do conjunto em ~+0,02 R/aposta porque corta a reversao antes do `line_broken` (2 fotos abaixo de uma linha projetada) e do `creator_dump` (latencia de leitura de saldo), sem matar as poucas que sobem (o alvo 2x so realiza o que a serie mostrou ser raro).
H0 (previsao): o ganho e ruido de 2 dias garimpado em 27 regras; fora da amostra o delta fica em [−0,02; +0,02] R e a concentracao dos 3 maiores continua > 50 % — a saida nao e a vantagem.

## Definicao congelada (flow_v2/x) — clone de `flow_v2/2` com UMA mudanca (a saida)

Porta: identica a `flow_v2/2` byte a byte (`gate_version` 2, `max_snipers` 10, `min_holders` 20, `min_unique_buyers` 10, `max_sells_to_buys` "0.6", progress 5–100 %, `max_dev_share` "0.10", `pedigree_exclusions`, `require_positive_flow`, `holders_rising_or_flat`, `progress_or_mcap_rising`, `creator_unknown_allowed_if_dev_measured`, `max_participation_pct` "1", relogio 15 s, idade 30–300 s).

Saida (`exit_key = alvo_2x_trailing_30_tempo_15m`, `exit_version = 1`):

| chave | `flow_v2/2` (controle) | braco |
|---|---|---|
| `target_x` | "3" | **"2"** |
| `trailing_pct` | "35" | **"30"** |
| `trailing_arm_x` | "1.5" | **ausente** (= `ExitRules.trailing_arm_multiple = None`, armado desde a entrada) |
| `max_hold_s` | 1800 | **900** |
| `max_loss_pct` | "50" | "50" |
| `exit_on_line_break` / `line_break_snapshots` | true / 2 | true / 2 |
| `require_creator_not_net_seller` (dump do criador) | true | true |
| `size_sol` / `fee_pct` | "0.05" / "1.75" | "0.05" / "1.75" |

Precedencia inalterada (`hunter_indicators.meme.exits.evaluate_exit`): rug > creator_dump > migrated/complete > dead > max_loss > line_broken > target > trailing > time_stop. R = `pnl_sol / initial_risk_sol` (o `r_multiple` do banco). Controle = `flow_v2/2` no mesmo periodo (mesmas moedas, mesmos minutos — o delta e pareado por `mint@minuto`).

**Por que nao tirar `line_broken`/`creator_dump`:** o replay de R59 mediu a nova saida **em cima** das saidas existentes (modo `earlier`: a regra nova so pode adiantar a saida); retirar regras seria testar outra coisa que nao foi medida.

## Portao de desenho (C1–C8) — congelado

| C | Criterio | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | PASS | Mecanismo: numa curva de pump.fun a reversao apos o pico e rapida (dump do criador/snipers); o trailing armado desde a entrada sai na primeira queda de 30 % do pico, antes que uma linha de suporte de minuto seja rompida duas vezes. Quem esta do outro lado: quem compra a reversao. KB: notes-R59 §2.1 |
| C2 | Sobreajuste | REVISE | 27 regras × 6 conjuntos em 2 dias; 30 e 2 sao valores redondos, 900 s idem; o unico efeito com teste pareado e o trailing 30 % (26×3). O alvo 2x apoia-se em 8 apostas |
| C3 | Amostra | PASS | `flow_v2/2` fez 165 apostas em 2 dias (~80/dia); 150 apostas do braco em ~2–3 dias |
| C4 | Regime | REVISE | Dois dias (16–18/09) e um universo que mudou na noite de 16/09 (T4.33: serie de 15 s ate 1 800 s para moedas fixadas); a censura da serie antes disso e de 300 s |
| C5 | Saidas | PASS | E o objeto do experimento; alvo 2x e trailing 30 % cabem na `ExitRules` sem codigo novo |
| C6 | Concentracao | PASS | 0,05 SOL, <= 1 % do volume, mesmos tetos do vivo; `kind=research_only` |
| C7 | Execucao | REVISE | Papel sem slippage; o replay usou mcap teorico e 1,25 %/perna; o papel marca com cotacao integral e 1,75 % — a soma absoluta nao e transferivel, so o delta pareado contra o controle |
| C8 | Invalidacao | PASS | Quatro gatilhos de descarte abaixo; regua geral (>= 150 apostas, 10 dias, LOO) |

**Veredito do portao:** `REVISE` — semeia como braco de pesquisa (papel), com a leitura unica pareada contra `flow_v2/2`; nada disto alcanca dinheiro real antes da regua.

## Previsoes (congeladas, numericas)

- P1: ΔR medio pareado (braco − controle, por `mint@minuto`) em [+0,00; +0,05], ponto **+0,02** (R59: +0,26 SOL / 215 apostas / 0,05 = +0,024 R).
- P2: saidas por `trailing` entre 10 % e 25 % das apostas do braco (R59: 29/215 = 13 %); por `line_broken` cai de 55 % para 35–45 %.
- P3: saidas por `target` entre 2 % e 6 % (R59: 8/215 = 3,7 %).
- P4: participacao dos 3 maiores ganhos no PnL do braco continua **> 50 %** (R59: 76 %) — a saida nao resolve a concentracao.
- P5: taxa de ruina (R <= −0,5) igual ou menor que a do controle (o trailing corta antes do piso).
- P6: R mediano do braco >= R mediano do controle (o efeito e difuso, nao so nas grandes).

## Gatilhos de descarte

1. ΔR pareado <= −0,02 com IC 95 % <= +0,00 depois de 150 apostas.
2. Taxa de ruina do braco > controle + 3 pp.
3. Saidas por `trailing` < 5 % (a regra nao esta disparando: nada a medir) ou > 40 % (esta cortando tudo).
4. R mediano pior que o controle com ΔR medio positivo (ganho so nas grandes = P4 negada na direcao errada).

## Regua e prazo

Leitura UNICA ao fim: minimo **150 apostas do braco E 10 dias corridos**, o que vier por ultimo, pareada por `mint@minuto` com `flow_v2/2`, LOO obrigatorio (tirar a maior aposta e reler o sinal). Veredito de vida (dinheiro real) so pela regua do lab: >= 100 apostas e 30 dias, e so via o item abaixo.

## O que NAO fazer

Mexer na porta junto; ajustar 30/2x/900 olhando os primeiros dias; somar os 5 conjuntos de papel (mesma moeda 4 vezes); comparar a soma do braco com o PnL registrado de outro periodo; ligar no executor real antes da regua.

## Separado: os `ExitParams` que o executor real precisaria

**Nao recomendado por R59** (n = 12; sob a melhor saida do papel as 12 reais fariam −0,056 a −0,058 SOL, igual ao registrado −0,059 as mesmas taxas; a unica saida que aproxima de zero, tempo 5 min, e 100 % PS). Registrado aqui para quando o braco de papel fechar.

O executor le a saida dos `params` do conjunto `operator` (`hunter_meme_executor.exits._params`): `target_x` → `target_multiple`, `trailing_pct` / 100 → `trailing_from_peak_pct`, `max_hold_s` → `time_stop_s`; o `decide_exit` de `hunter_risk_meme.exits` **ja e sempre armado** (nao existe `trailing_arm_multiple` no real: hoje e trailing 35 % da marca honesta desde a entrada) e nao tem `line_broken` nem `max_loss`.

```python
from decimal import Decimal
from hunter_risk_meme import ExitParams

ExitParams(
    target_multiple=Decimal("2"),          # operator/x params: "target_x": "2"      (hoje "3")
    trailing_from_peak_pct=Decimal("0.30"),  # operator/x params: "trailing_pct": "30"  (hoje "35")
    time_stop_s=900,                        # operator/x params: "max_hold_s": 900      (hoje 1800)
)
```

Variante que R59 mediu melhor nas 12 reais, so para registro: `time_stop_s=300` (tempo 5 min: −0,017 sem segurar alem do registrado; +0,008 segurando, n = 11, tudo PS). Nao semear sem o braco de papel fechado.

## Braco semeado

(pendente — este arquivo e rascunho; semear = novo `flow_v2/x` com `kind=research_only`, `exp_ref=EXP-M17`, migracao propria, `test_migration_00xx` provando igualdade com `flow_v2/2` fora das 4 chaves de saida)

## Avaliacao

(append-only; fechamento diario acrescenta secao datada)

## Fontes

- `.claude/state/notes-R59.md` (tabelas, censura, deltas pareados, as 12 reais aposta a aposta)
- `.claude/state/r59/replay.py` + `q_bets.sql`, `q_15s.sql`, `q_1m.sql`; saidas `out_earlier.md`, `out_hold600.md`, `out_hold120.md`, `out_earlier_fee175.md`
- `packages/indicators/hunter_indicators/meme/exits.py` (regras do papel), `packages/risk-core/hunter_risk_meme/exits.py` (regras do real), `services/meme-worker/hunter_meme_worker/lines_exit.py` (projecao da linha)
- `docs/DATABASE.md` §43.2 (`meme_features_15s`), §40.3 (`meme_live_positions`)

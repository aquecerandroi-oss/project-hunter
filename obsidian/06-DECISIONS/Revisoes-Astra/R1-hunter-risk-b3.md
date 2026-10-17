---
tags: [revisao-astra, b3, mt5, rico, robo, risco, motor-puro, sizing, kill-switch, mercado-tradicional]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: risk-engine-guardian
decided_on: 2026-10-17
by: risk-engine-guardian + astra
tarefa: "R1 do desenho docs/design/robo-b3-mt5.md §9 — motor puro hunter_risk_b3 (25 checks, sizing com binding_constraint, evaluate_exit, kill switch, sessão/calendário puros) contra o contrato congelado docs/RISK_ENGINE_B3.md v1.0"
veredito: "2 rodadas. R1: DONE_WITH_CONCERNS, 5 must-fix reproduzidos por ela (margem não positiva aprovava, float aninhado em dict construía, comissão/tarifa ausentes viravam zero, check 8 indisponível não se propagava a 9/15/24, carimbo do futuro contava como fresco) — todos aceitos, cada um com teste que falhou antes; R2: 'nenhum must-fix restante'. Concordou com as 11 escolhas de forma (a–k). Não autoriza dinheiro real nem certifica a semântica da Rico"
---

# Revisão da Astra — motor puro do robô B3 (R1, `hunter_risk_b3`)

**Pedido:** revisar o motor puro `hunter_risk_b3` (pacote irmão de `hunter_risk` e `hunter_risk_meme` em
`packages/risk-core`) contra o contrato congelado `docs/RISK_ENGINE_B3.md` v1.0 (§7.1, §8, §9), escrito depois da
revisão [[Revisoes-Astra/R0a-risk-engine-b3|R0a-risk-engine-b3]]. Fontes brutas:
`.claude/state/astra-review-R1-hunter-risk-b3.md` (rodada 1) e `-r2.md` (rodada 2). Página do módulo:
[[Execution Engine]] (seção "Linha B3").

**Notas lidas antes e o que mudaram:** [[00-HOME]] (toda entrada é proposta → motor de risco → execução: o motor só
decide, quem envia é o serviço); [[KB-0149-o-que-a-mesa-real-ensinou]] §1 e §4.23 (72 % do prejuízo foi custo → a
tarifa de ida e volta entra no risco de toda operação, e sem tabela de custo válida os checks 16/17 saem
`fee_schedule_missing`), §5.24–§5.27 (revisão adversária paga → sondas de mutação antes de declarar pronto);
[[Revisoes-Astra/R0a-risk-engine-b3|R0a]] (checks 11 e 13 recebem as contagens já sem a própria proposta). Nenhuma
estratégia mudou nesta tarefa; a [[Fila de Hipoteses]] (H-038) não foi tocada.

## O que foi construído

`evaluate(proposal, broker, account, limits, session, calendar, quote, kill_switch, *, spec, margin, ops)` com os 25
checks e os `reason` do contrato, todos gravados mesmo depois da primeira reprovação; sizing pelo mínimo dos tetos
com `binding_constraint` (desempate pela ordem do contrato, `warning_halving`, `volume_step`); `evaluate_exit` que
sempre aprova; kill switch "o mais restritivo" por tabela (nunca `max()` sobre a `StrEnum`, que põe `WARNING` acima
de `EMERGENCY`); o livro da perda do pregão (cada negócio uma vez, custo por perna sempre positivo, depósito fora do
resultado); o perfil de limites como dado com recusas `limits_invalid:<campo>`; construtores puros de sessão e
calendário. Teste de fronteira: nenhum dos três motores importa outro, e o B3 não importa rede, banco, relógio,
`os`/`pathlib`, `hunter_indicators` nem o serviço.

## Rodada 1 — 5 must-fix, todos aceitos

| # | Cenário dela (reproduzido em código) | O que mudou |
|---|---|---|
| 1 | dois contratos, `per_volume={1: 100, 2: −1}` → aprovado, check 18 `passed` | margem ≤ 0 no volume final é `margin_unavailable`; margem unitária > 0 exigida para os tetos |
| 2 | `MarginInputs(per_volume={1: 100.1})` construía e aprovava | a recusa de `float` percorre mapas, listas, tuplas e conjuntos (chaves inclusive) |
| 3 | comissão ilegível omitida vira 0; a diferença cabe na tolerância de R$ 5 e esconde perda | `DayDeal.commission`/`fee` obrigatórios: ausente ≠ zero |
| 4 | relógio não medido: check 8 `unavailable`, mas 9, 15 e 24 `passed` | 9, 15 e 24 viram `upstream_unavailable:8`; falhas independentes da cotação continuam relatadas antes |
| 5 | `mark_time = as_of + 1 dia` → check 14 `passed`, decisão aprovada | regra única `−2 s ≤ now − carimbo ≤ idade máxima` para marca (14), medição do relógio (8), reconciliação (20) e API (21); âncora do futuro = `day_anchor_missing` |

Nice-to-have aceito: as propriedades geram limites pela validação real (sem `model_copy`) e a propriedade do risco
usa população aprovável com `assume`. **Isso mostrou um buraco no meu teste:** o gerador antigo chegava ao ramo
aprovado em 3 de 53 sorteios (o health check do Hypothesis acusou), ou seja, a invariante principal quase não rodava;
agora roda em 300 aprovados por execução. Residual declarado: os dicionários dentro dos modelos congelados
(`per_volume`, `caps`) continuam mutáveis depois da construção.

## Rodada 2 — "nenhum must-fix restante"

Ela reexecutou a suíte B3 (319 passed) e conferiu cada correção no código e no teste.

## Escolhas de forma (ela concordou com todas)

(a) `quote_invalid` como `failed`, seguindo a tabela §8.2 — o §8.3 diz "unavailable" para bid/ask invertidos: **contradição do
contrato a corrigir**; (b) `robot_magics` acrescentado em `RobotOpsState` para separar `foreign_*` de
`position_already_open`/`pending_order_present` — não é prova de atribuição pela cadeia de negócios; (c)
`orphan_sltp_unknown` como conjunto de símbolos; (d) checks 16–18 avaliados em `max(n_final, 1)` quando o tamanho dá
zero, para o teto vencedor reprovar com o próprio motivo; (e) `kill_switch_effective` inclui o WARNING/TRADING_DISABLED
automático da perda, o check 1 só os escopos persistidos; (f) `approved_at`/`expires_at` preenchidos mesmo reprovado
(texto do §8.4; carimbo não é autorização); (g) o calendário entra como dado — o motor **não** importa
`hunter_indicators.b3.calendar_2026` (dependência não declarada; numpy/polars no núcleo de dinheiro); (h)
`broker_reject_breaker` emitido com contagem ≥ limite e ainda não *latched* (o serviço precisa ser idempotente até
receber o *latch*); (i) `evaluate_exit` com 2 checks informativos; (j) checks 6 e 7 seguem o check 5 indisponível;
(k) chave `spec_unreadable_after_failures`.

## Pendências para o contrato (dono do `docs/RISK_ENGINE_B3.md`, não desta tarefa)

1. Resolver a contradição §8.2 × §8.3 sobre `quote_invalid` (`failed` ou `unavailable`).
2. Registrar os insumos acrescentados: `RobotOpsState.robot_magics`, `SpecPin.spec_pin_id`, `OrderCheckResult`,
   `orphan_sltp_unknown` como conjunto, `ExitRequest`, e a chave `spec_unreadable_after_failures` (R3/R4 usam os mesmos nomes).
3. Escrever a tolerância de carimbo no futuro (2 s) para marca, relógio, reconciliação e API.
4. `packages/config/ruff.toml` precisa de `hunter_risk_b3` em `known-first-party` (fora do escopo de R1; hoje o isort o
   ordena como pacote de terceiros).

## Divergências

Nenhuma de objetivo. A única recusa minha foi não ampliar a correção 5 ao `created_at` da proposta (check 22): uma
proposta gravada pela API milissegundos depois da leitura da corretora é normal, e a aprovação vence em
`as_of + 30 s` de qualquer forma.

## O que aprendi (para a próxima tarefa de motor)

- **Teste de propriedade que retorna cedo no ramo reprovado pode não testar nada.** Usar `assume` e deixar o health
  check provar que o ramo aprovado roda.
- **"Nenhum campo ausente vira 0" vale também para valor padrão de modelo**: `= 0` num campo de custo é um zero
  escondido.
- **Todo teste de "fresco" precisa dos dois lados**: `now − t ≤ idade` sozinho aceita qualquer carimbo do futuro.

## Relacionadas

[[Execution Engine]] · [[Risk Engine]] · [[Revisoes-Astra/R0a-risk-engine-b3|R0a-risk-engine-b3]] ·
[[Dialogos/robo-b3-mt5]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[Fila de Hipoteses]]

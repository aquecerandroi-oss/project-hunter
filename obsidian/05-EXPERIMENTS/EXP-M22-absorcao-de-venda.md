---
tags: [experimento, meme, evento, entrada, absorcao, venda-grande, m4, r62, r64]
status: pre-registrado (braços semeados em papel; nada real)
owner: sexta-feira
updated: 2026-09-20
origem: Astra, 20/09/2026 (parecer `astra-review-estrategia-2026-09-20.md`, item 4) sobre R62 (KB-0143) e R64 (KB-0146) — "testar uma sequência de absorção, com parâmetros congelados, em vez de mais um limiar do filtro atual"
previsao: o braço confirmado tem R médio > controle e cauda menor; se o repique for distribuição antes do segundo dump, o braço confirmado perde igual ou pior que o controle e a família é descartada
---

# EXP-M22 — Absorção de venda: a demanda que recompõe uma venda grande distingue resistência de distribuição?

## Hipótese
Uma venda relevante (≥ 5 % da reserva real da curva) é o gatilho que antecede os dumps (KB-0143), mas **isolada
não distingue dump de sacudida**: no R62, 5 das 8 posições tiveram vendas ≥ 5 % absorvidas e subiram depois
(Cupsey#1, CYBER, XCrypto +139 %, NARKY#1 +139 %, FЕРЕ +55 %), e o "seguir a venda" 60 s depois é cara ou coroa.
A hipótese é que **quem absorve a venda é a informação**: se o preço volta ao nível pré-venda em até 30 s e
**se sustenta ali por 10 s**, há demanda real por trás (resistência); se não volta, ou volta e cede, é
distribuição. A entrada só depois da absorção confirmada deve ter R médio maior e cauda de perda menor do que
a entrada imediata depois da mesma venda.

## Por que agora
R62 (KB-0143) mostrou que a regra "sair na primeira venda ≥ 5 %" destrói dois alvos (−0,0185 SOL nas 8) e que
as vendas grandes absorvidas precedem as maiores subidas; R64 (KB-0146) mostrou que 12 das 15 saídas por
trailing eram moedas que nunca subiram (MFE ≤ +10 %) — o problema é a **entrada**, não a saída. Astra propôs
esta família como alternativa a girar mais um botão do filtro atual (EXP-M10/M13/M14/M19 são limiares do mesmo
portão). O feed por trade (T4.52b) já entrega cada venda com reservas pré/pós, o que torna o gatilho e a
recuperação mensuráveis em cadeia, na decisão, sem foto de 15 s.

## Definições operacionais congeladas (mudar uma é versão nova da feature)
- **Venda grande** = trade `sell` cujo `sol_amount` (o que sai da curva, antes de taxas) é ≥ **5 %** de
  `real_sol_reserves` **pré-venda** (`real_pós + sol_amount`, derivado do próprio evento — não depende do trade
  anterior nem da cobertura).
- **Preço** = `virtual_sol_reserves / virtual_token_reserves` pós-trade. **Nível pré-venda** =
  `(v_sol_pós + sol_amount) / (v_tok_pós − token_amount)`, derivado do próprio evento da venda.
- **Recuperação** = primeiro trade (qualquer lado) com preço ≥ nível pré-venda, com `block_time` ≤ 30 s depois
  da venda. Sem recuperação em 30 s ⇒ episódio **falhou** (`recovery_late`).
- **Sustentação** = 10 s a partir da recuperação sem nenhum trade com preço < nível pré-venda. Um trade abaixo
  antes dos 10 s desfaz a recuperação (pode recuperar de novo, ainda dentro dos 30 s da venda). Sem trade não há
  mudança de preço, logo o silêncio conta como sustentação.
- **Confirmado** = `recuperado_em + 10 s`, calculado, não observado (o portão avalia por notificação; a leitura
  é em `as_of`). Vale por **60 s** (`confirmation_expired` depois) — o sinal é um instante, não um estado da
  moeda.
- **Segunda venda grande** (≥ 5 %) **antes** de confirmar ⇒ **reinicia** o episódio nessa venda (novo nível
  pré-venda, novo relógio de 30 s) — a primeira não foi absorvida. Segunda venda grande **depois** de confirmar
  ⇒ episódio **encerrado** (`second_sell_after_confirm`): o sinal some e o mint não gera outra confirmação.
- **Uma entrada por mint**: um mint tem no máximo **um episódio confirmado** (o rastreador fica `spent` depois
  da confirmação, expirada ou não); o controle tem exatamente **uma janela** (30 s a partir da **primeira**
  venda grande vista), independentemente de reinícios.
- **Buraco de cobertura** (reconexão do WS, overflow) ⇒ tudo desconhecido (`coverage_gap`): o critério recusa
  `absorb_unknown`, nunca "não houve venda".
- **Universo** = mints que a pista de evento acompanha (`MEME_EVENT_GATE=on`, assinatura no `create`, T4.70),
  com idade **30–300 s** (`min_age_s`/`max_age_s` do conjunto), curva **não migrada** (recusa `migrated`),
  não-Mayhem (`exclude_mayhem`), participação ≤ 1 % do volume do minuto (a exigência da mesa; a fita precisa
  de 60 s de cobertura ⇒ na prática a idade útil é 60–300 s, igual nos dois braços) e as exclusões de pedigree
  que todo conjunto carrega. **Não** exige criador não-vendedor (a venda do criador pode ser o próprio gatilho —
  FЕРЕ) nem progresso mínimo.
- **Ficha 0,07 SOL**; saídas da mesa (`operator/6`): alvo **1,15×**, trailing **10 %** armado na entrada,
  **300 s**, `line_broken`, `creator_dump`, `max_loss` 50 %; taxa **1,25 %**; `max_open_positions` 3; TTL 180 s.

## Braços (papel, `research_only`, relógio de 15 s — lidos pela pista de evento como `flow_v2/8–10`)
| braço | conjunto | id | critério a mais | o resto |
|---|---|---|---|---|
| **tratamento** | `absorb_v0/1` | `01994d00-6c1a-7000-8000-00000000001a` | `require_absorb_confirmed: true` | idêntico |
| **controle** | `absorb_v0/2` | `01994d00-6c1a-7000-8000-00000000001b` | `require_absorb_sell_seen: true` (entra na primeira avaliação depois da venda) | idêntico |

`test_migration_0058` prova que `absorb_v0/1.params − require_absorb_confirmed == absorb_v0/2.params −
require_absorb_sell_seen` byte a byte. Só a pista de evento preenche `absorb_*`; a pista de 15 s deixa `None` ⇒
os dois conjuntos recusam `absorb_unknown` ali (falha fechada, como EXP-M19).

## Método
- **Prospectivo**: nada de replay; as duas medições nascem da mesma venda, no mesmo mint, na mesma hora.
- Limiares **congelados, sem grade**: 5 %, 30 s, 10 s, 60 s de validade. Não há braço 3/4/5 com 3 %/45 s/15 s.
- Custos incluídos como na mesa: taxa 1,25 % nos dois lados; a leitura em R re-precifica com **1,5 s de
  atraso** gatilho → pouso (mediana do R62) sobre a fita, como o `grid.py` do R64.
- Métricas: R médio e mediano por braço; **diferença pareada** tratamento − controle nos mints em que os dois
  entraram; acerto; soma PnL SOL; **cauda** (fração de apostas ≤ −40 % e ≤ −70 % aos 300 s); **concentração por
  mint** (apostas/mints distintos) e por hora; fração de recusas `absorb_unknown` (cobertura) e de episódios
  `recovery_late`/`second_sell_after_confirm` (quantas vendas são absorvidas de fato).
- Lacunas identificadas: as duas pistas ainda preenchem o papel na foto seguinte (não no trade); a idade útil
  é 60–300 s pela fita; o controle entra "na primeira avaliação depois da venda", que é o debounce do portão
  (≤ 1 s), não o bloco da venda.

## Regra de decisão (congelada)
Leitura única depois de **3 dias** e **≥ 60 apostas por braço**:
- **Confirma** se R médio do tratamento > R médio do controle com IC95 da diferença pareada acima de zero **e**
  cauda ≤ −40 % menor que a do controle **e** resultado líquido do tratamento > 0 com a saída da mesa (superar
  um controle negativo não basta — regra da Astra no item 1 do parecer).
- **Descarta** se a diferença não for distinguível de zero ou se o tratamento tiver cauda igual/maior.
- Confirmado ⇒ candidata ao dia de validação (replay + estresse + replicação), decisão do Everton. Nunca
  promoção a real por esta leitura.
- Cobertura: se `absorb_unknown` > 20 % das recusas do tratamento nas primeiras 24 h, o problema é cobertura, não
  hipótese — corrigir antes de ler R.

## Cenário de falha
O repique **é** a distribuição: quem absorve a venda são os que vão vender no segundo dump (Cupsey#2: 80 s de
distribuição antes da entrada). Nesse caso o tratamento entra mais tarde, mais caro e mais perto do dump —
perde igual ou pior que o controle, e a família inteira é descartada, não "ajustada" para 3 % ou 45 s.

## Não faz parte
Mudar saídas (R64: a regra atual venceu 52 braços); aplicar à mesa real; grade de limiares; usar a venda
grande como saída (KB-0143 já refutou).

Ligações: [[KB-0143-o-que-antecede-o-dump]] · [[KB-0146-trailing-apertado-e-rent-de-ata]] ·
[[EXP-M19-subida-com-gente-atras]] · [[EXP-M21-pausa-por-mint-apos-trailing]] ·
`.claude/state/astra-review-estrategia-2026-09-20.md` · `.claude/state/notes-R62.md` · `.claude/state/notes-R64.md`

## Braços semeados (T4.79)

**20/09/2026** — migração `0058_meme_gate_absorb_arm` (sobre `0057_spot_desk`), `ddl/meme_gate_absorb_arm.py`.
Estado por mint em `hunter_meme_worker.absorb.AbsorbTracker` (dentro de `MintEventState.absorb`, alimentado por
`apply_trade`, zerado por `mark_gap`, despejado com o livro); leitura em `MintEventState.absorb_features(as_of)`
→ `GateRow.absorb` (`event_gate_rows.build_event_row`); critérios `require_absorb_confirmed` /
`require_absorb_sell_seen` em `RuleSetSpec` (julgados em `hunter_meme_worker.absorb_rules`, ao lado de
`require_event`/`require_twitter`); recusas `absorb_unknown`, `absorb_not_confirmed`, `absorb_sell_not_seen`;
bloco `absorb` na decomposição da proposta. Provas: `services/meme-worker/tests/test_absorb.py`,
`test_event_absorb.py`, `packages/core/tests/integration/test_migration_0058.py`.

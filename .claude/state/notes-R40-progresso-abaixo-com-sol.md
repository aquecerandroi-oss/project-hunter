# R40 — as 8 recusas `progress_below_window` "com SOL na curva": causa por ordem

**Quando:** 16/09/2026, revisão de ~10 min. **Fonte:** banco da VPS (SELECT apenas) —
`meme_live_orders.admission->'checks'`, `meme_tokens`, `meme_curve_snapshots`.
**Achado de origem:** R39, `obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md` §2c.
**Veredito:** não há defeito novo. 5 ordens são o bug de unidade T4.28e (pré-correção) e
3 são **rug real**, lido certo pelo executor e desmentido pela foto velha da série de 15 s.

## 1. Tabela ordem → causa

| # | hora BRT | símbolo | `curve_progress.value` gravado | causa |
|---:|---|---|---:|---|
| 1 | 11:46:36 | INCEPT | −541 546,7976 | bug de unidade T4.28e (pré-fix) |
| 2 | 11:46:55 | INCEPT | −554 166,9803 | bug de unidade T4.28e (pré-fix) |
| 3 | 11:47:18 | INCEPT | −657 115,1480 | bug de unidade T4.28e (pré-fix) |
| 4 | 11:47:55 | INCEPT | −425 330,8405 | bug de unidade T4.28e (pré-fix) |
| 5 | 12:07:27 | CGRAM | −505 184,7821 | bug de unidade T4.28e (pré-fix) |
| 6 | 18:42:41 | KYLE | +0,01695193 | **rug real**, ~7 s antes da decisão |
| 7 | 18:42:42 | KYLE | +0,01676589 | **rug real**, mesma dump |
| 8 | 19:07:02 | BYFD | +0,00506188 | **rug real**, 13 s depois dos 45,8 % |

**Só essas 5 são negativas.** De todas as 61 ordens com `curve_progress.value` no banco,
`count(*) FILTER (WHERE v < 0) = 5`, primeira 14:46:36 UTC, última 15:07:27 UTC; a primeira
não-negativa é 15:52:40 UTC (12:52:40 BRT, GREMLIN). A correção do T4.28e fecha a janela.

## 2. Recomputação à mão (a prova do rug)

Denominador dos 4 mints em `meme_tokens`: **793 100 000,0000 tokens**,
`progress_denominator_source = global_params`, `mayhem_enabled = f` nos quatro
(INCEPT, CGRAM, KYLE, BYFD). **Nenhum denominador errado no conjunto.**

`progress = (D − real_token_reserves)/D`, `D = 793,1e6 × 1e6` subunidades:

| mint | instante | `real_token_reserves` (tokens) | `real_sol_reserves` | progresso |
|---|---|---:|---:|---:|
| BYFD | 22:06:49 UTC (foto) | 429 810 129,838366 | 15,3565 | 0,45806 |
| BYFD | **22:07:02 UTC (leitura do admissor)** | **789 085 421,848878** (implícito) | — | **0,00506188141611650485436893** |
| BYFD | 22:07:07 UTC (foto) | **789 085 421,848878** | 0,1127 | 0,00506188141611650485436893 |
| KYLE | 21:42:34 UTC (foto) | 426 486 606,932710 | 15,5699 | 0,46225 |
| KYLE | 21:42:41 UTC (admissor) | 779 655 422,656287 (implícito) | — | 0,01695193 |
| KYLE | 21:42:42 UTC (admissor) | 779 802 975,890581 (implícito) | — | 0,01676589 |
| KYLE | 21:42:48 UTC (foto) | 781 427 035,292443 | 0,3300 | 0,01472 |

- **BYFD bate dígito a dígito**: o valor da recusa às 22:07:02 corresponde exatamente ao
  `real_token_reserves` que o radar fotografou **5 s depois**. A curva devolveu 359,3 M
  tokens e perdeu 15,24 SOL reais entre 22:06:49 e 22:07:07. Os "45,8 % 19 s antes" eram
  outra curva, ainda viva. **Progresso não é monótono no tempo: token volta.**
- **KYLE**: as duas leituras do admissor caem **dentro** do buraco de 14 s entre as fotos
  (426,5 M → 781,4 M) e são monótonas entre si. Mesma dump, mesmo desfecho: 15,57 → 0,33 SOL.
- Os `rsol na ordem` de 11,6–23,2 SOL da tabela do R39 para KYLE/BYFD vêm da **foto anterior**
  (7 s e 13 s de idade), não da leitura que decidiu. O `state_freshness` das 8 ordens passou
  com idade negativa de −0,06 a −0,17 s: a leitura RPC é do próprio instante.

**Conclusão:** KYLE e BYFD não são "atraso de 12 s da KB-0117"; são o inverso — o admissor
estava **à frente** da cadeia e recusou uma curva que já tinha esvaziado. As três recusas
foram corretas e salvaram dinheiro (R39 marca as duas moedas como "boa").

## 3. Denominador errado — não aconteceu hoje, mas o cheque existe

Nenhuma das 8 tem denominador suspeito. Se tivesse, o efeito depende da direção:

- **Denominador grande demais** (o caso T4.28e, ou uma linha gravada em subunidades):
  `progress → 1⁻` ou negativo enorme → `progress_above_window`/`progress_below_window`.
  **Falso refuse: seguro, perde compras.** Foi o dia inteiro do estágio 1 até 12:2x.
- **Denominador pequeno demais** (supply ≠ 1e9 com o registro program-wide do
  `/global-params`, ou Mayhem): **pode dar falso PASS**. Com `D_usado ≈ D_real/4`, uma curva
  com 80 % da reserva já vendida (perto da graduação, entrada cara) aparece como 20 % e
  **passa** a janela de 2–50 %. Está pinado em
  `TestADenominatorSmallerThanTheTruthCanPassALateCurve`.
- Mitigação que já existe **na escrita**: `graduation.denominator_for` devolve `UNKNOWN`
  quando `real_token_reserves > initial` ("não é a curva desse registro") e Mayhem só ganha
  denominador por `mayhem_denominator`. O furo que sobra: uma curva de supply maior cuja
  **primeira** foto já esteja abaixo de 793,1 M tokens grava o denominador do registro.
- Mitigação que **não** existe na leitura: `curve_progress_check` aceita
  `real_token_reserves > denominator` e publica −5×10⁵ em vez de dizer "esse denominador não
  é dessa curva". Era o canário que teria pegado o T4.28e na primeira ordem, não na quarta.

## 4. Correção mínima proposta (não implementada nesta tarefa)

O executor **já tem os dois números ao vivo e sem RPC extra**:
`ChainReader.global_account()` (cacheado) traz `initial_real_token_reserves` e
`token_total_supply` em subunidades, e `CurveRead.account.token_total_supply` é o supply da
**própria** curva (já usado em `curve_from` → `CurveState.total_supply`). Então:

```
denominator_subunits = curve.total_supply * global.initial_real_token_reserves
                       // global.token_total_supply
```

Numa curva padrão dá exatamente 793 100 000 000 000 — mesma unidade de
`real_token_reserves`, sem conversão de tokens→subunidades e sem depender do banco.
Vantagens: (a) mata a classe de bug de unidade na raiz; (b) escala com supply ≠ 1e9;
(c) o banco vira conferência, não fonte. Guarda a somar junto, em `curve_progress_check`:
`real_token_reserves > denominator` → `progress_denominator_missing` (unavailable, recusa por
nome) em vez de um número negativo — é o caso Mayhem (822,6 M > 793,1 M, `docs/PUMPFUN.md`
§ denominador) e o caso "registro de outra curva".

## 5. Teste de regressão

`services/meme-executor/tests/test_admission_r40_rug.py` — 6 casos com os números reais do
banco: BYFD passa a janela às 22:06:49 e é recusada com o **valor gravado** às 22:07:02;
as duas leituras de KYLE reproduzem os valores gravados e caem entre as fotos vizinhas;
e o falso PASS por denominador pequeno demais. `17 passed` junto com `test_admission_units.py`.

## 6. Ligações

R39 `obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md` §2c · `.claude/state/notes-T4.28e.md` ·
`docs/PUMPFUN.md` (denominador do progresso, Mayhem) · KB-0117 (atraso da série de 15 s).

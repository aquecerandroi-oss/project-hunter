---
tags: [knowledge, nota, meme, pumpfun, bum, tempo, mayhem, base-rate, m4]
tema: memecoin / pump.fun / quantos bums reais há por dia (SOL real na curva, sem Mayhem) e em quanto tempo acontecem
fonte: banco da VPS (meme_curve_snapshots, meme_tokens, meme_features_1m), 13–16/09/2026
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-t427-bum-real-sem-mayhem.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-t427-{picos-sao-mayhem,bum-real-sem-mayhem}.sql; 49 853 moedas não-Mayhem, 3 dias)
hipotese_testavel: sim
astra: não consultada nesta nota (orquestrador, 16/09 02:3x BRT)
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-16
status: vivo
---

# KB-0098 — Quantos "bums" reais há por dia no pump.fun, e quanto tempo temos para agir

**Pergunta do Everton (16/09 01:5x BRT):** "se a tendência move a moeda, a moeda conseguimos lucrar muito" — então quantas moedas
de fato explodem por dia, e em quanto tempo?

## 1. O que NÃO é bum: o SOL virtual do agente Mayhem
Ordenando as moedas dos últimos 3 dias pelo nosso mcap teórico (preço marginal × supply), os 95 "picos" acima de 500 SOL são
**todos** moedas Mayhem (`mayhem_enabled = true`), 76 deles com menos de 20 % da curva vendida. Exemplo KAT (15/09 17:37 BRT):
`virtual_sol_reserves` foi de 23,9 para 1 977 SOL em **60 s** com só 7 % dos tokens fora da curva — o agente injeta SOL
virtual; não houve compradores (5 holders). **Lição:** para medir bum, o número é o **SOL real na curva**
(`real_sol_reserves`), nunca o mcap teórico; Mayhem fica fora por padrão (T4.27 leva isso ao portão, à marca e ao placar).

## 2. Os bums reais (SOL real na curva, moedas não-Mayhem, 13–16/09)
| Medida (3 dias) | Número |
|---|---|
| Moedas não-Mayhem com fotografia | 49 853 |
| Passaram de 10 SOL reais | 8 224 (16,5 %) |
| Passaram de 30 SOL reais | 3 214 (6,4 %) |
| Passaram de 60 SOL reais | 1 842 (3,7 %) — a curva gradua a ≈ 85 SOL; ver §6 |
| Graduaram | 1 942 (3,9 %) |
| Mediana de tempo até 30 SOL / 60 SOL | **1 min / 1 min** |
| Chegaram a 30 SOL **depois** de 3 min de vida | **552 (1,1 %)** ≈ 184/dia |
| Chegaram a 30 SOL depois de 10 min | 198 (0,4 %) ≈ 66/dia |

**Leitura:** a esmagadora maioria dos bums acontece **no primeiro minuto** (bots e bundles no mesmo slot) — ali não há tempo
humano nem de mesa; é o território do sniper, que a porta recusa de propósito. O universo em que **há tempo de agir** é a
célula lenta: ~180 moedas/dia chegam a 30 SOL reais com ≥ 3 min de vida (média 58 min), e ~65/dia com ≥ 10 min.

## 3. O Lab e a célula lenta
Das 552 lentas: **103 graduaram** (18,7 % — contra 3,9 % da população), o Lab **propôs 29** e **apostou em 14** (2,5 %).
Ou seja: a célula onde há tempo e onde a taxa de graduação é 5× a média é exatamente a que os conjuntos atuais
(relógio de 15 s, idade 30–300 s) quase não olham. É a tese da [[05-EXPERIMENTS/EXP-M7-organica-lenta|EXP-M7]] (`organic_v0/1`,
entra 3–30 min, progresso 10–30 %) — que ainda não propôs nada porque exige `snipers ≤ 2`, `holders ≥ 20 subindo` e top-10 ≤ 30 %
lidos no minuto; a próxima medição é **por que** as 552 são recusadas (qual critério corta), antes de mexer em qualquer limiar.

## 4. O que muda amanhã
- T4.27: Mayhem fora do portão, da marca e do placar; `mcap_executable_sol` ao lado do teórico.
- Estudo seguinte (T4.28): o funil de recusas da `organic_v0/1` sobre as 552 lentas de 3 dias — quantas caem por sniper, por
  holders, por top-10, por criador — e um braço irmão pré-registrado com o critério que mais corta relaxado (previsão `descartar`).
- Notícia/evento (T4.26) entra aqui como **o que aponta para a lenta certa antes dos 3 min**, não como substituto da porta.


## 6. Números do "bum real" na VPS (SQL `2026-09-16-t427-bum-real.sql`, rodado pelo orquestrador 16/09 03:0x BRT; 4 dias)

**Correção à seção 2:** a curva do pump.fun **gradua a ≈ 85 SOL reais** — "passar de 100/300/1 000 SOL reais na curva" é
impossível por construção (0/0/0 medidos); o teto de uma moeda na curva é a graduação, e o que vem depois vive na pool
(PumpSwap), fora desta medida. Os patamares que fazem sentido são 10 / 30 / 60 SOL e "encheu a curva".

| Dia BRT | Moedas não-Mayhem | ≥ 10 SOL | ≥ 30 SOL | ≥ 60 SOL | Lentas (30 SOL após ≥ 3 min) |
|---|---|---|---|---|---|
| 13/09 | 14 570 | 2 021 | 862 | 564 | 136 |
| 14/09 | 15 689 | 2 721 | 1 042 | 621 | 183 |
| 15/09 | 20 170 | 3 700 | 1 363 | 662 | **273** |

(12/09 parcial: 661 moedas.) Total 51 089 não-Mayhem com fotografia (7 com flag desconhecida); 8 520 ≥ 10 SOL, 3 316 ≥ 30,
1 881 ≥ 60, **1 197 encheram a curva**, 1 97x graduaram.

**Hora do dia das lentas (cruzam 30 SOL com ≥ 3 min; n = 593):** madrugada quase vazia (0–5 h: 1,7–2,7 % cada), sobe a
partir das 10 h (4,9 %), platôs de 13–14 h (6,1 %) e 17–18 h (6,9–7,4 %), **pico às 22 h BRT (9,1 %)**, cai às 23 h (2,2 %).
Leitura: o horário útil da mesa é **13 h–22 h BRT**; a orgânica lenta e o evento "pode dar bum" devem ser medidos por hora
antes de qualquer regra de horário (previsão `descartar`, como sempre).

## Ligações
[[11-KNOWLEDGE/KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[11-KNOWLEDGE/KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain]] · [[05-EXPERIMENTS/EXP-M7-organica-lenta]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] · [[00-INBOX/Hipoteses-do-plantao]]

## 5. Adendo T4.27 (16/09/2026, 01:3x UTC = 15/09 22:3x BRT pelo relógio da máquina) — Mayhem não é preço: o que mudou no instrumento

**Por que o `mcap_sol` mentia em Mayhem, em uma linha:** um `buy` na curva sobe `virtual_sol_reserves` e `real_sol_reserves`
pelo mesmo tanto (`docs/PUMPFUN-ONCHAIN.md` §1.2), então numa moeda padrão a reserva virtual acima dos 30 SOL de lançamento **é** o SOL
real. Numa moeda Mayhem `set_mayhem_virtual_params` (§1.3) empurra a virtual sem SOL entrar — o preço marginal × supply lê o agente,
não compradores. **O SOL real na curva é o teto do que todos os holders juntos poderiam tirar dela.** Daí as quatro mudanças:

| Onde | Antes | Desde a T4.27 |
|---|---|---|
| Séries `meme_features_1m` / `meme_features_15s` | só `mcap_sol` (teórico) | `mcap_executable_sol` ao lado (`0042`): `min(mcap_sol, real_sol_reserves)` em Mayhem, `= mcap_sol` em moeda padrão; CHECK `≤ mcap_sol`; NULL nas linhas antigas. `mcap_sol` continua gravado, rotulado **teórico** (na moeda Mayhem, SOL virtual do agente). Não é preço — é teto. |
| Marca de papel (`paper_engine`) | `quote_sell` sobre as reservas virtuais | bruto da venda limitado ao `real_sol_reserves` da mesma foto (`sell_all_value_sol`), taxa sobre o que sai; `exit.real_sol_cap_applied` / `exit.mark_basis` na linha; sem teto na curva completa (o SOL foi para a pool) |
| Portão (`EntryGate`) | não sabia o que era Mayhem | `exclude_mayhem: true` por padrão em todo conjunto (recusa `mayhem_curve`; flag não lida recusa `mayhem_unknown` — falha fechado); a feature `is_mayhem` vem do bit `is_mayhem_mode` da foto da cadeia ou do `mayhem_state` do site |
| Placar | apostas em Mayhem contadas como medidas | `meme_reclassify_mayhem.py --day … --apply --reason` marca `indeterminate` com motivo `mayhem_virtual_sol`; o fechamento diário já as deixa fora |

**Aritmética conferida por teste** (`packages/indicators/tests/unit/test_meme_executable.py`): curva `30 SOL × 300 tokens` empurrada
para `300 SOL` virtuais com **5 SOL** no cofre; vender 100 tokens cota `300·100/400 = 75 SOL` — quinze vezes o cofre — e o teto corta para
5 SOL, taxa `0,0625`, líquido `4,9375`. Numa curva padrão o teto nunca prende (Hypothesis, 200 caminhos compra→venda): o cofre é o que os
compradores pagaram e a posição é parte disso.

**Atenção aos patamares.** A curva **gradua** quando o SOL real chega ao limiar do registro (85,005 SOL no registro de 2025-07-18) e o SOL
vai para a pool: **100 / 300 / 1 000 SOL de `real_sol_reserves` não existem numa curva** (o SQL `2026-09-16-t427-bum-real.sql` deixa as
três colunas para lerem 0 — se lerem > 0 é reserva errada, não bum). Os patamares que existem são 10 / 30 / 60 SOL e "encheu"; em mcap
teórico de curva padrão equivalem a ≈ 50 / 112 / 252 / 411 SOL. As perguntas "quantos por dia" e "a que horas" estão nas consultas 2 e 3
desse SQL (por dia Brasília; hora Brasília em que as lentas cruzam 30 SOL reais) — **resultado pendente de execução no banco da VPS**
(a T4.27 não tem acesso; o orquestrador roda e cola aqui).

**O que ainda não está fechado:** a linha `mcap_executable_sol` da série de minuto é calculada pelo fold mas só entra no `INSERT` quando
`repo._FEATURE_COLUMNS` (arquivo da T4.26 em voo) ganhar a coluna — uma linha; a série de 15 s já grava. O `lab_repo.load_gate_rows`
(mesma situação) recebe o flag por uma leitura extra por chave primária (`lab_repo_mayhem.py`), a ser dobrada na própria consulta
quando o arquivo liberar. Os gráficos da T4.25 continuam desenhando `mcap_sol`; a série executável está lá para trocar.

Ligações: `docs/RISK_ENGINE_MEME.md` §6 · `docs/plans/T4-MEME-RADAR.md` §4 · `.claude/state/notes-T4.27.md` ·
[[11-KNOWLEDGE/KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain|KB-0095]] (os rótulos `active`/`paused`/`completed` que servem de segunda testemunha).

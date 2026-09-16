# T4.28h — `creator_flow_unknown` pode passar quando o `dev_share` está medido e é pequeno

**Data:** 2026-09-16. **Escopo:** `hunter_risk_meme` (limites + check 10) e o executor (contexto,
heartbeat). **Nenhum limite de capital mudou. Nenhum check novo. Nenhum nome de recusa novo.**
Com a variável desligada — o padrão — o comportamento de hoje é bit a bit o mesmo.

## 1. A medição em que me apoiei (não refiz nenhuma)

`obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md` (R5):

| medição | valor |
|---|---|
| ordens recusadas `creator_flow_unknown` | 7 / 16 no recorte do estudo; **11 / 22** no dia inteiro (brief) |
| `creator_sold` não-nulo × criação do token | +123 a +441 s (mediana 207 s) |
| instante da entrada × criação | 30–300 s |
| regra da mesa que já admite o caso | `operator/5`, E1 braço 2, `creator_unknown_allowed_if_dev_measured` + `max_dev_share = 0,10` |

O conflito é esse: **a mesa propunha o que o executor recusava.**

## 2. O que mudou

### 2.1 `limits.py` — duas variáveis que **não** entram no `POLICY_ENV`

`creator_unknown_allowed_if_dev_measured: bool = False` (`MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED`)
e `creator_unknown_max_dev_share_pct: Decimal = 0.10` (`MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT`).
Ausentes ⇒ política completa (não são "quanto posso perder"; são uma autorização). Presentes e
ilegíveis ⇒ `MemePolicyMissing(invalid=(nome,))`, que o boot do executor já converte em
`policy_missing` com o nome — o mesmo caminho das cinco.

**Vocabulário estrito de propósito:** `1/true/yes/on` e `0/false/no/off`; qualquer outra coisa é
`invalid`, **não** um "não" silencioso. `gates.parse_flag` trata `maybe` como `False`; aqui isso
seria o dono achando que ligou e tendo desligado — com dinheiro real, um silêncio desses é a falha.

### 2.2 `checks.py` — o check 10 com três saídas em vez de duas

`creator_net_sol is None` e a permissão ligada:

| `dev_share_pct` | estado | recusa | `message` | `value`/`limit` |
|---|---|---|---|---|
| medido, ≤ teto | **passed** | `None` | `creator_unknown_dev_share_measured` | dev share / teto |
| medido, > teto | unavailable | `creator_flow_unknown` | `… dev share above <teto>` | dev share / teto |
| não medido | unavailable | `creator_flow_unknown` | `… both unmeasured` | — / teto |

Permissão desligada: exatamente a linha de antes. Um `creator_net_sol` **conhecido** nunca chega
nesse ramo — um vendedor líquido continua `creator_net_seller`, e nenhuma variável de ambiente mexe
nisso. `unavailable()` ganhou `value`/`input_ts` para que o caso "acima do teto" grave o número que
**foi** medido ao lado do insumo que não foi.

### 2.3 Executor — de onde vem o `dev_share`, e quando ele **não** é um insumo

`MemeContext` ganhou `dev_share_pct` + `dev_share_source` + `dev_share_ts` (valor, procedência,
instante — nunca um número solto). `repo_context.py` (novo módulo: `repo.py` passaria de 350 linhas)
lê o **mais novo** de duas fontes dentro de 600 s: `meme_risk_snapshots.dev_share` e
`meme_features_1m.dev_share`.

**A decisão que vale a pena registrar:** o `dev_share` de `meme_features_1m` só é aceito com
`holders_observed_at` preenchido. A `0023` carimba essa coluna **só quando `holders` foi lido**
(`features.py::_holders_columns`), e o `end_time` da linha é o fecho do minuto, não o instante da
leitura — o fold escreve "a leitura mais nova recebida até o `end_time`", que pode ter 5 minutos.
Datar a foto pelo `end_time` chamaria de "30 s" uma leitura de 5 min, e é justamente uma foto velha
que faria um dev que já largou tudo vouchar por si mesmo. Sem carimbo, não é insumo.

`admission.dev_share_input` (puro) derruba a leitura em três casos: sem valor, sem carimbo, e fora
de `DEV_SHARE_MAX_AGE_S` (600 s, **o mesmo** número do `bundled_share` — não inventei um segundo
botão). Carimbo **no futuro** também cai: dois relógios discordando não são uma leitura fresca.

Heartbeat: `policy` publica os dois campos. Uma permissão ligada é um fato sobre como este processo
admite; ficar implícita seria a mesma opacidade que a T4.28g reclamou do `reason`.

## 3. O que está provado

Docker **de pé** nesta execução; nada ficou `skipped` por falta de container.

- `packages/risk-core/tests/unit/meme/test_creator_unknown_dev_share.py` — 31 casos: desligado ×
  {dev pequeno, grande, ausente}; ligado × {0, 0,05, 0,10 passam; 0,11 recusa com o mesmo nome;
  ausente recusa}; vendedor líquido conhecido **não** é salvo; teto do ambiente aplicado; vocabulário
  da flag; ilegível recusa o boot pelo nome; o JSON da admissão distingue "desconhecido mas
  permitido" de "conhecido e bom".
- `services/meme-executor/tests/test_admission_dev_share.py` — 11 casos: janela, fronteira exata,
  sem carimbo, carimbo no futuro, ausente, e qual das duas tabelas vence (com a procedência nomeada).
- `services/meme-executor/tests/test_live_persistence.py` (Postgres real, sem fake do schema):
  `token_context` lê `meme_risk_snapshots.dev_share` datado e derruba o que passou da janela;
  `creator_sold = NULL` + `dev_share` 5 % **desligado** ⇒ ordem `refused`/`creator_flow_unknown`,
  nada enviado; **ligado** ⇒ `confirmed` com o check `passed` e a mensagem; o heartbeat publica.
- `uv run pytest packages/risk-core/tests services/meme-executor/tests -q -x -m "not live"`:
  **473 passed** (123 s). ruff/format/pyright limpos; `check_file_size.py` 0 acima do orçamento.

## 4. Um achado que **não** é meu, corrigido para a suíte ficar honesta

`services/meme-executor/tests/test_live_persistence.py` — os dois testes que a T4.28g escreveu e
nunca rodou (`test_stage_1_waits_for_the_rug_read_instead_of_burning_the_proposal`,
`test_a_stale_rug_read_is_not_a_rug_read`) **falhavam** com Docker de pé: passam sozinhos e quebram
na suíte, porque a fixture `harness` limpava ordens, posições e propostas mas **não**
`meme_risk_snapshots`, e `test_stage_1_opens_…` deixa uma leitura de 25 s do mesmo mint. O robô então
abria a proposta que o teste manda ele deixar quieta. Corrigi na fixture (um `DELETE` por mint). O
código de produção da T4.28g não foi tocado.

## 5. O que continua aberto (declarado, não escondido)

1. **A foto é corrente, não é a alocação inicial.** Um criador que largou tudo aos 20 s da moeda pode
   ter `dev_share ≈ 0` e, com a permissão ligada, **passar**. O check 10 não foi feito para isso — é
   por isso que a permissão é escrita, reversível e desligada por padrão, e que a §4 diz em voz alta
   que ela não resolve esse caso. A correção de causa continua sendo a da T4.28g §2.3: persistir a
   alocação do criador no instante do `create`, ou cobrir a fita desde o minuto zero.
2. **A procedência não viaja no JSON da admissão.** O brief fixou `message` exatamente como
   `creator_unknown_dev_share_measured`, então a fonte (`meme_features_1m:board` vs
   `meme_risk_snapshots`) fica no `MemeContext` e no `input_ts` da linha do check (só o instante).
   Quem for auditar *qual leitor* vouchou por um criador tem de cruzar com `meme_risk_snapshots`.
3. **Nada aqui foi medido em produção.** O ganho esperado (o `creator_flow_unknown` deixar de ser
   44 % das recusas) é a aritmética do R5, não uma medição desta mudança — e só existe depois de o
   dono ligar a variável.

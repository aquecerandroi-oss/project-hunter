---
tags: [experimento, replay, politicas-de-saida, shadow-lab]
updated: 2026-09-06
status: em-andamento
---

# EXP-0004 — replay de oito políticas de saída sobre as entradas congeladas (R1)

> Experimento aberto em **2026-09-06** com a execução R1 do replay, commitada em `2c6bb2d`
> (`feat(research): R1 — replay of eight exit policies over the Lab's frozen entries`). É o bloco de
> saídas do [[Registro de Tentativas]] — **T-005** (invalidação), **L1/T-022** (alvo assimétrico) e
> **L2/T-023** (sem alvo e canal oposto) — rodado como **uma** família de 7 contrastes sobre as
> **mesmas entradas** já registradas pelo Lab. **SOMBRA:** `purpose = research_only`, sem capital,
> custos assumidos; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita (o replay abre a
> transação `REPEATABLE READ, READ ONLY` — quem impede a escrita é o Postgres, não a revisão de
> código). A seção "Hipótese" e a seção "Protocolo" são escritas uma vez e **nunca** mudam; as
> avaliações são **acrescentadas** abaixo, datadas. Ver [[Experiments Index]],
> [[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]] e [[Registro de Tentativas]].

## Hipótese (congelada)

Sobre **as mesmas entradas** que o Shadow Lab já registrou — mesma admissão, mesmo stop, mesmo
horizonte, mesmos custos assumidos —, alguma das sete políticas alternativas de saída (afrouxar,
confirmar ou deslocar a invalidação; alvo a 3,0 ou 4,5 ATR₀; retirar o alvo; retirar o alvo e sair
pelo canal oposto de 10 fechamentos de 15 min) produz uma diferença média de `R_net` por sinal de
**pelo menos 0,05 R** em relação à política atual, e essa diferença sobrevive a Holm a 5% sobre a
família de sete.

## Protocolo (congelado na primeira execução — nunca editar)

### Manifesto da execução R1

Uma execução do replay só é comparável a outra quando **os dois dígitos** abaixo são iguais. Isto não
é formalidade: o Lab continua escrevendo, então "o mesmo banco" **não é frase estável** — duas
execuções seguidas com o mesmo `--as-of` deram Markdown e JSON byte a byte idênticos
(`md5 0aba2f68…`) enquanto o banco não mudou, e uma terceira, minutos depois, mudou os dois dígitos
porque o Lab terminalizou mais um outcome decidido antes do corte (métricas e os sete contrastes
ficaram idênticos — a população maturada não muda —, as contagens de população não).

| Campo | Valor |
|---|---|
| `as_of` (**corte de dados**, não só de população) | `2026-09-06T20:55:00+00:00` |
| `input_digest` (sha256 das linhas de `signal_outcomes` lidas) | `8b9cb982f7caec128873dd28b75ac2a61ba5cb10e5d98d3be80acc953b157752` |
| `series_digest` (sha256 das velas efetivamente dobradas) | `759c1f5e60a522b8c521a480515589faf4d51fe75e3d7ef1b3d6186664e0593f` |
| Semente / reamostras | `20260906` / `10000` |
| Família Holm | **7** contrastes, declarados antes do resultado |
| Efeito mínimo declarado | **0,05 R** (linha T-005 do [[Registro de Tentativas]]) |
| `purpose` / coorte | `research_only` / entradas prospectivas já registradas (o replay **não** cria coorte `replay:<run_id>`; ele não escreve) |
| `funding_read` | `as_stored_at_read_time` — **limite declarado**, ver abaixo |
| Artefatos | `.claude/state/r1-proof.md`, `.claude/state/r1-proof.json`, `.claude/state/notes-R1.md` |

**Os quatro `strategy_version_id` congelados** (identificados no manifesto, nunca resolvidos por
`status = active` — a supersessão local v1→v2 preserva a população anterior):

| `strategy_version_id` | versão | `params_hash` | `code_ref` | ativada em (UTC) |
|---|---|---|---|---|
| `01a073de-89b8-7f70-8b8a-1a7a08be5dcb` | `momentum_v1` | `40e1688e…c41ac2f3` | `hunter_core.strategies@sha256:13dfa322…01ea0b5` | 2026-09-05 23:19:56.334638 |
| `098b060c-cdc0-46a6-b88b-70d4a5472b97` | `momentum_v2` | `40e1688e…c41ac2f3` | `hunter_core.strategies.momentum_v1@sha256:c012f75c…18b0ba823` | 2026-09-06 02:08:13.332014 |
| `01a073de-8a07-76c3-92fc-0f712aee63da` | `volume_anomaly_v1` | `fa5dce78…32f63bb9` | `hunter_core.strategies@sha256:13dfa322…01ea0b5` | 2026-09-05 23:20:09.899561 |
| `d6442b18-6e2d-4efd-afac-180edc3981bd` | `volume_anomaly_v2` | `fa5dce78…32f63bb9` | `hunter_core.strategies.volume_anomaly_v1@sha256:d8275427…65410ef2` | 2026-09-06 02:08:19.424473 |

`v2` **não é variante de pesquisa** em nenhuma das duas estratégias: difere de `v1` só pelo
`code_ref` (parâmetros e `params_hash` idênticos, verificados por SQL). Duas coortes da mesma
estratégia **não são duas hipóteses** aqui — o que separa as populações é o `strategy_version_id`
dentro do `uuid5` de cada sinal. Está registrado assim em [[Experiments Index]] e em
[[EXP-0001-momentum-v1]].

**Custos assumidos:** os do próprio sinal, congelados em `signal_outcomes.meta.assumed_costs` e
**reusados verbatim** — o replay não redeclara custo nenhum. Para as duas estratégias desta execução:
spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado, funding assinado. São **hipóteses
declaradas, não tarifas verificadas**.

**Banco:** local (`hunter`), alcançado por encaminhador (`docker run --rm --network docker_default -p
15432:5432 alpine/socat …`); **nunca** contra o Postgres da VPS. A coorte grande da VPS **não** foi
usada nesta execução (exigiria dump por `infra/vps/backup_postgres.sh` restaurado num container
local, e o orquestrador não liberou nesta rodada).

### As oito políticas (declaradas antes de olhar resultado)

| Política | Regra | Como é expressa | Walker |
|---|---|---|---|
| `base` | INV-A, o que o Lab acompanhou: stop, `target1`, invalidação, horizonte | plano gravado | inalterado |
| `INV-B` | sem invalidação; stop, alvo e horizonte inalterados | plano diferente | inalterado |
| `INV-C` | invalidação só depois de **dois** fechamentos alinhados consecutivos abaixo do nível | observador puro (`hunter_indicators.replay.observers`) | inalterado; recebe `pending_invalidation` |
| `INV-E` | invalidação em `L − 0,25 · ATR₀` (o ATR congelado da decisão) | plano diferente | inalterado |
| `TGT-3` | alvo a 3,0 ATR₀ da referência (o `target2` já persistido) | plano diferente | inalterado |
| `TGT-4.5` | alvo a 4,5 ATR₀ da referência (o `target3` já persistido) | plano diferente | inalterado |
| `EXIT-NOTGT` | sem alvo; stop, invalidação e horizonte inalterados | plano diferente (alvo sentinela) | inalterado |
| `EXIT-CHAN` | sem alvo; **invalidação nativa mantida** e canal **acrescentado**: fechamento de 15 min abaixo do mínimo dos 10 fechamentos de 15 min anteriores | plano + observador | inalterado; recebe `pending_invalidation` |

Regras que fazem essas oito colunas serem comparáveis, e que **não mudam**:

1. **Não é reimplementação do acompanhamento.** Um braço é um `TrackingPlan` diferente dobrado pelo
   **mesmo** `walker.walk` e fechado pelo **mesmo** `settle.settle` (logo o mesmo
   `funding.resolve_funding`). O plano é reconstruído por `tracking_repo.OpenTracking.plan` a partir
   das colunas gravadas (`virtual_stop`, `virtual_targets`, `meta.entry_plan`, `meta.assumed_costs`,
   `meta.horizon_s`) — nunca recalculado pela estratégia, o que garante escala de banco
   (`NUMERIC(28,10)`) idêntica. O caminho é refeito de `Progress.start()`: progresso persistido é
   **referência de comparação**, não estado inicial (must-fix 1 da primeira revisão da Astra — carregar
   o progresso terminal faria `walk()` devolver a saída antiga sem avaliar vela nenhuma, e a
   reprodução pareceria perfeita por construção).
2. **`EXIT-CHAN` conserva a invalidação original.** Se o braço do canal a desligasse, `CHAN − NOTGT`
   mediria *canal + remoção da invalidação*. Só `INV-C` desliga a observação nativa, porque a
   substitui. A cobertura publica o **gatilho**, que o `result` canônico (`invalidated` para os três)
   esconderia.
3. **Alvo sentinela auditado.** `TrackingPlan.target1` não é opcional, então "sem alvo" é um nível
   inalcançável declarado (referência × 10⁶), com `check_target_unreachable` **provando** que nenhuma
   máxima da janela replicada o tocou; se tocasse, o braço interrompe em vez de fabricar saída por
   alvo.
4. **Pareamento congelado na base.** A admissão (`stop < P_entry < alvo`) fica congelada: um braço
   nunca entra onde a base não entrou, e nenhum braço ocupa ou rearma slot. `no_entry: late:*` é
   **herdado sem dobrar nada** (atraso é evidência sobre o relógio da decisão; essas linhas ficam
   fora do denominador da reprodução); `no_entry: geometry` é **rededuzido** da barra de entrada —
   copiar a recusa de volta seria auditar o registro contra ele mesmo.
5. **Corte comum de horizonte, antes do pareamento.** Só entram no pareamento os sinais cujo
   **horizonte inteiro** fechou até `as_of`; os demais saem com motivo `immature_horizon` e são
   contados. Parear "os dois braços resolveram" selecionaria trade por velocidade de desfecho — a
   base bate alvo em 20 min e o `EXIT-NOTGT` do mesmo sinal ainda está aberto, então o par sumiria
   justamente onde os braços mais diferem. **O efeito não é cosmético:** sem o corte, `TGT-3 − base`
   dava +0,118 R e com o corte dá +0,056 R; `TGT-4.5 − base` ia de +0,081 para +0,112 R. **Números
   sem o corte não devem ser citados.**
6. **`as_of` é corte de dados, não só de população.** `load_series` corta em
   `last_closed_minute(as_of)` (a mesma função do motor de outcomes) e o que passa do corte vira
   `immature`. Sem isso, uma execução "as of 17:00" resolveria um horizonte das 20:00 com velas que o
   próprio corte diz que ela não pode ver.
7. **Funding desconhecido nunca vira zero.** `R_net = null` com motivo, `meta.r_ex_funding`
   preservado, e a linha conta na cobertura — nunca como zero e nunca como par.
8. **Prioridade e convenções do Lab inalteradas:** gap na abertura primeiro, depois toques intrabar;
   stop e alvo na mesma barra → **stop**; prioridade na abertura `stop > alvo > horizonte >
   invalidação`; horizonte exato contado da entrada.

### Os sete contrastes (declarados antes do resultado)

`INV-B − base`, `INV-C − base`, `INV-E − base`, `TGT-3 − base`, `TGT-4.5 − base`,
`EXIT-NOTGT − base`, `EXIT-CHAN − EXIT-NOTGT`. Pareados por sinal; par só existe quando **os dois
braços** produziram `R_net` avaliável para o mesmo sinal, e o resto é cobertura contada por motivo.

- **Estimando:** `Σ S_b / Σ n_b` (média por sinal), **nunca** média das médias diárias — dias têm
  tamanhos diferentes e isso mudaria o estimando.
- **Bloco:** o **dia UTC da entrada**. A dependência é transversal (muitas altcoins reagindo ao mesmo
  BTC), então os blocos são por tempo, não por mercado. Cinco dias de velas **não** são cinco blocos
  de outcomes: `B` conta os dias UTC com pares elegíveis em cada contraste.
- **IC:** reamostragem de **blocos inteiros** com reposição, percentil, semente `20260906`, 10 000
  reamostras.
- **p:** inversão de sinal por blocos, exata até `2¹² = 4096` configurações, amostrada acima com
  correção `(hits+1)/(draws+1)`.
- **Holm a 5% sobre sete**, mesmo quando `--policies` roda um subconjunto.
- A coluna de efeito mínimo diz **`abs(Δ)`**: uma piora de 0,10 R também acende a bandeira; o sinal
  está no próprio Δ.
- **Sem combinar vencedores.** O bloco não autoriza juntar o vencedor de T-005 com o de T-022 — isso
  seria comparação adicional, e tentativa a mais.
- `r_ex_funding` roda pela mesma máquina como **sensibilidade**, com a cobertura (maior) dele.

**Comando (reprodutível para o mesmo par de dígitos):**

```
uv run python infra/scripts/replay_exits.py \
  --database-url postgresql+asyncpg://... --versions momentum,volume_anomaly \
  --as-of 2026-09-06T20:55:00Z --out .claude/state/r1-proof.md
```

`--as-of` sem fuso é **recusado** (`astimezone` num datetime ingênuo leria o fuso da máquina).

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-06 — `as_of = 2026-09-06T20:55:00Z`, artefato escrito em `2026-09-06T21:28:01Z`

**Sobre o carimbo de leitura.** Esta execução **não** registra um `read_at` transacional no artefato —
a identidade da leitura é o par `input_digest` / `series_digest`, e o instante acima é o de escrita
dos arquivos de prova. É uma lacuna de forma em relação ao [[_TEMPLATE-EXP]] e fica anotada como tal;
o snapshot em si é único (`REPEATABLE READ, READ ONLY`), então as tabelas desta avaliação descrevem o
mesmo mundo. Como em toda avaliação do Lab, **esta leitura não é reconstruível**: `signal_outcomes`
avança no lugar.

#### 1. Portão do passo 1 — reprodução da base

| versão | linhas | comparáveis | reproduzidos | divergentes | `late` (herdados) | sem resolver | taxa (tudo) | **taxa (trajetória)** |
|---|---|---|---|---|---|---|---|---|
| `momentum_v1` | 70 | 65 | 65 | 0 | 5 | 0 | 1,0000 | **1,0000** |
| `momentum_v2` | 80 | 69 | 64 | 5 | 6 | 5 | 0,9275 | **1,0000** |
| `volume_anomaly_v1` | 91 | 82 | 82 | 0 | 9 | 0 | 1,0000 | **1,0000** |
| `volume_anomaly_v2` | 136 | 123 | 114 | 9 | 5 | 8 | 0,9268 | **1,0000** |
| **total** | **377** | **339** | **325** | **14** | **25** | **13** | **0,9587** | **1,0000** |

**Reprodução de trajetória: 1,0000 em 339 linhas comparáveis** (limiar do portão: 0,9900), com
**0 campos de trajetória divergentes**. "Trajetória" aqui é o conjunto completo: estado, resultado,
entrada, `entry_ts`, `exit_ts`, `exit_at_open`, `exit_bar_open`, preço de saída e `r_ex_funding`. O
portão roda **antes** dos contrastes e é ele que os libera — sem ele o CLI não calcula contraste
nenhum.

**O que a auditoria classifica como divergência.** `terminal` gravado que o replay recusa como
`no_entry` é **divergência de trajetória**, não "sem resolver". Se caísse em "sem resolver", sairia
do denominador e um replay que recusasse **todas** as entradas marcaria 1,0000 — contraprova
executada pela Astra: 1 acerto + 99 dessas divergências dava `trajectory_rate = 1.0000,
passed = True`. "Sem resolver" ficou só para o que o replay realmente não terminou: `immature`,
`gap`, `channel_window_unavailable`, `target2/3_missing`.

#### 2. As 14 divergências — só de liquidação, atribuição **compatível, não comprovada**

27 campos em **14** linhas, **todas de liquidação (funding)** e **nenhuma de trajetória**:

- **13** têm `r_multiple = null` gravado com motivo
  `funding_missing:2026-09-06T19:59:59…` / `…20:00:00…` e hoje liquidam normalmente;
- **1** (`5b027f70-69c0-558d-88bc-ac8ef82df2e9`) tinha `funding.per_unit = 0` e `settlements = 0`
  gravados e hoje cobra o settlement das 20:00:00 — `−0,8112908472` → `−0,8263601960`. **Esta é a
  exceção**, com motivo diferente das outras 13, e está separada de propósito: atribuir todas à mesma
  causa esconderia o caso.

Todas saíram entre 20:00 e 20:27 e **todas batem `r_ex_funding` exatamente** — `r_ex_funding` é
calculado com funding zero, então ele isola a trajetória.

**A explicação e o seu limite.** É compatível com ingestão tardia do settlement das 20:00: o worker
liquidou entre 20:02 e 20:27 e a linha de `funding_rates` chegou depois. **Compatível, não
comprovado** — `funding_rates` **não tem coluna de instante de ingestão**, então nada no banco decide
*quando* a linha chegou, e `exit_ts` não prova quando o worker liquidou (must-fix 3 da revisão do
diff). Retirar o settlement atual e reproduzir o valor antigo demonstra que a ausência dele **explica
aritmeticamente** a diferença; **não** prova que ele estava ausente naquele instante.

**Evidência de apoio, com a ressalva junto:** numa leitura mais antiga, `--as-of
2026-09-06T17:00:00Z`, a reprodução foi **201/201 = 1,0000 com zero divergências** — nenhuma daquelas
linhas estava perto do corte. Aquela execução foi feita **antes** de `as_of` virar corte de dados;
hoje ela cobriria menos linhas, porque entradas com horizonte além das 17:00 passariam a `immature`.
Não é uma segunda medição do mesmo objeto.

#### 3. Cobertura e métricas por política (nomes do Lab, denominador explícito)

| política | resolvidos | avaliáveis (`R_net`) | sem entrada | sem resolver | maturados | gatilhos | taxa de alvo entre toques resolvidos | taxa de lucro líquido | expectancy líq. hipotética (R) | PF (denominador) |
|---|---|---|---|---|---|---|---|---|---|---|
| `base` | 330 | 330 (sem funding: 0) | 34 | `{immature: 13}` | 275 | `{invalidation: 117}` | 0,561905 (118/210) | 0,366667 | −0,307218 | 0,578044 (240,266655) |
| `INV-B` | 316 | 316 (0) | 34 | `{immature: 27}` | 275 | — | 0,444444 (136/306) | 0,443038 | −0,307178 | 0,620822 (255,996745) |
| `INV-C` | 325 | 325 (0) | 34 | `{immature: 18}` | 275 | `{two_closes: 46}` | 0,481884 (133/276) | 0,415385 | −0,313541 | 0,603035 (256,700064) |
| `INV-E` | 324 | 324 (0) | 34 | `{immature: 19}` | 275 | `{invalidation: 56}` | 0,500000 (131/262) | 0,413580 | −0,307003 | 0,606512 (252,787412) |
| `TGT-3` | 129 | 127 (2) | 34 | `{immature: 10, target2_missing: 204}` | 275 | `{invalidation: 48}` | 0,519481 (40/77) | 0,314961 | +0,002812 | 1,005304 (67,332481) |
| `TGT-4.5` | 122 | 120 (2) | 34 | `{gap: 1, immature: 16, target3_missing: 204}` | 275 | `{invalidation: 50}` | 0,360656 (22/61) | 0,216667 | −0,100288 | 0,831473 (71,409878) |
| `EXIT-NOTGT` | 303 | 299 (4) | 34 | `{gap: 2, immature: 38}` | 275 | `{invalidation: 138}` | 0,000000 (0/108) | 0,157191 | −0,393073 | 0,566808 (271,308733) |
| `EXIT-CHAN` | 303 | 298 (5) | 34 | `{gap: 2, immature: 38}` | 275 | `{channel: 18, invalidation: 137}` | 0,000000 (0/104) | 0,164430 | −0,376021 | 0,578637 (265,932343) |

- **Taxa de alvo entre toques resolvidos** ≠ **taxa de lucro líquido** ≠ **expectancy líquida
  hipotética em R**. Nas duas políticas sem alvo a taxa de alvo é 0,000000 **por construção** (não há
  alvo alcançável), e o denominador é só de stops resolvidos.
- **PF** com denominador ao lado; nenhum caso ficou nulo nesta leitura.
- **MFE/MAE:** nulos quando o OHLC não determina o extremo; não recalculados por braço nesta
  execução.
- **PnL de carteira** e **Max Drawdown de carteira**: **não aplicável** — não há carteira no Shadow
  Lab.
- `target2_missing` / `target3_missing` **não é falha**: `volume_anomaly_v1/v2` persiste **um** alvo,
  então os braços L1 só existem para `momentum` — recusa explícita, nunca rebaixamento silencioso
  para a base.
- Os 34 "sem entrada" e as 13 linhas `immature` fecham com o total de 377 da população; a cobertura
  publica todos os motivos.

#### 4. Os sete contrastes — **exploratórios**

> **Esta tabela é descritiva, não é teste.** Os p-valores vêm de inversão de sinal por blocos de dia,
> cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; e com **um** bloco o
> teste devolve `p = 1` **por construção** (duas configurações, mesmo `|T|`). Isso **não é evidência
> de equivalência** — é ausência de replicação. O IC é **indisponível com motivo**
> (`single_block`): `[efeito, efeito]` seria tautologia, não precisão.

| contraste | pares | blocos | Δ médio `R_net` | IC 95% | p | p Holm | rejeita? | `abs(Δ) ≥ 0,05 R` |
|---|---|---|---|---|---|---|---|---|
| `INV-B − base` | 244 | 1 | −0,010928 | — (`single_block`) | 1,000000 | 1,000000 | não | não |
| `INV-C − base` | 244 | 1 | −0,006098 | — (`single_block`) | 1,000000 | 1,000000 | não | não |
| `INV-E − base` | 244 | 1 | −0,003127 | — (`single_block`) | 1,000000 | 1,000000 | não | não |
| `TGT-3 − base` | 87 | 1 | **+0,056216** | — (`single_block`) | 1,000000 | 1,000000 | não | **sim** |
| `TGT-4.5 − base` | 86 | 1 | **+0,111738** | — (`single_block`) | 1,000000 | 1,000000 | não | **sim** |
| `EXIT-NOTGT − base` | 238 | 1 | **+0,094064** | — (`single_block`) | 1,000000 | 1,000000 | não | **sim** |
| `EXIT-CHAN − EXIT-NOTGT` | 237 | 1 | +0,005228 | — (`single_block`) | 1,000000 | 1,000000 | não | não |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria, maior):

| contraste | pares | Δ médio | IC 95% |
|---|---|---|---|
| `INV-B − base` | 244 | −0,010921 | — |
| `INV-C − base` | 244 | −0,006106 | — |
| `INV-E − base` | 244 | −0,003135 | — |
| `TGT-3 − base` | 89 | +0,019847 | — |
| `TGT-4.5 − base` | 88 | +0,073841 | — |
| `EXIT-NOTGT − base` | 242 | +0,066522 | — |
| `EXIT-CHAN − EXIT-NOTGT` | 242 | +0,009927 | — |

Os dois contrastes de alvo (`TGT-3`, `TGT-4.5`) correm sobre uma **subpopulação diferente** dos
outros cinco — só `momentum` — e **não** são comparáveis linha a linha com eles.

#### 5. Result, e por quê

- **Result: inconclusivo.** Limiar editorial: 100 outcomes avaliáveis **E** 30 dias distintos. Há
  **275** outcomes da base com horizonte maturado (330 avaliáveis com `R_net`) e **1** dia distinto.
  Passa o lado dos outcomes; **falha o lado dos dias**.
- **O motivo do inconclusivo é `B = 1`.** O bloco é o dia UTC da entrada e, nesta leitura, **as
  entradas caem todas em 2026-09-06** — o Lab só foi ativado em 05/09 às 23:19 e a primeira entrada é
  06/09 às 00:26. Com um bloco: IC indisponível (`single_block`), `p = 1` por construção, e Holm
  sobre a família fixa de sete não muda nada **e não poderia** — mesmo com seis blocos o menor p
  atingível seria `2/64 = 0,031 > 0,05/7`.
- **Conclusion.** O que este piloto entrega é **aprendizado operacional**, não confirmação: (a) o
  replay reproduz a **trajetória** do acompanhamento real **nesta leitura** — 1,0000 em 339
  comparáveis, com as 14 divergências isoladas na liquidação; (b) a cobertura de cada política está
  medida, com os motivos de recusa nomeados; (c) as ordens de grandeza e as direções das diferenças
  estão registradas — os três contrastes com `abs(Δ) ≥ 0,05 R` são `TGT-3`, `TGT-4.5` e `EXIT-NOTGT`,
  todos na direção de "o alvo de 1,5 ATR está cortando cauda direita". **Nada disso é evidência
  estatística**, e a afirmação "o replay reproduz o acompanhamento real" vale **condicionada a esta
  execução** (estes dois dígitos), não em geral.
- **Next Action.** Nenhuma ativação, desativação ou reparametrização decorre destes números. Repetir
  a **mesma** execução quando houver dias distintos suficientes — ver "Reagendamento" abaixo.
- **Segunda opinião (Astra) — três rodadas**, em `.claude/state/astra-review-R1-replay.md` (desenho),
  `…-diff.md` (`DONE_WITH_CONCERNS`) e `…-fixes.md` (`BLOCKED`, fechamento parcial). Aceitos e
  aplicados **antes** desta página: `EXIT-CHAN` mantendo a invalidação nativa; refazer o caminho de
  `Progress.start()`; `as_of` como corte de velas; geometria rededuzida em vez de copiada;
  `exit_at_open`/`exit_bar_open` na comparação; portão **antes** dos contrastes, com
  `terminal → no_entry` contado como divergência de trajetória; corte comum de maturidade **antes**
  do pareamento; snapshot `REPEATABLE READ`; denominadores publicados e a coluna rotulada como
  magnitude absoluta; `--as-of` sem fuso recusado; `input_digest` **e** `series_digest`. Continuam
  **abertos** os bloqueios que ela manteve, listados em "Pendências" — nenhum deles foi silenciado
  para publicar esta avaliação. Divergência registrada: ela pediu para "distinguir explicitamente
  reconstrução com dados de hoje de reconstrução da informação disponível naquele instante" — isso
  **não** está resolvido no código, está declarado nas pendências 1 e 2, e é por isso que a
  atribuição das 14 divergências fica em "compatível, não comprovada".

#### 6. Recompute de funding — o que mudou fora desta leitura

As 14 linhas divergentes são exatamente a população de `infra/scripts/recompute_funding.py --apply`;
o replay **não escreve**, então elas continuam como estavam nesta avaliação.

- **VPS, 2026-09-06:** `recompute_funding.py --apply` **foi aplicado** — **97 de 110** outcomes
  resolvidos, **13 seguem sem funding**.
- **Local:** **ainda não aplicado**. A população desta avaliação é a do banco **local**, então os
  números acima descrevem o estado **antes** de qualquer recompute.

As duas populações não se somam nem se comparam (bancos, `strategy_version` e `code_ref` diferentes —
[[Open Bugs]]). Quando o recompute rodar no local, ele muda `input_digest`, e a próxima execução do
replay **não** será comparável a esta: será outra avaliação datada, com os dígitos novos.

## Pendências (abertas, com o que cada uma impede)

| # | Pendência | O que ela impede hoje |
|---|---|---|
| 1 | **`settle` sem corte temporal.** O corte `as_of` vale para as **velas**; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim (reimplementá-lo aqui seria pior). Uma linha de funding ingerida depois do corte é visível à liquidação e pode até completar a inferência de cadência. | Impede afirmar ausência de look-ahead **na liquidação**. O efeito é isolável pela coluna `r_ex_funding`, que não depende de funding nenhum. Fechar exige um parâmetro de corte em `settle.py` (fora do escopo do brief R1) ou a pendência 2. |
| 2 | **`funding_rates` sem `received_at`.** Não há coluna de instante de ingestão. | "A linha chegou depois" é sempre **compatível**, nunca comprovado — é o que trava a atribuição das 14 divergências da §2. |
| 3 | **`volume_anomaly` sem alvos informativos.** Persiste **um** alvo (`virtual_targets` com 1 elemento; `momentum` tem 3). | Enquanto for assim, **L1 é um experimento de `momentum`**: `TGT-3`/`TGT-4.5` recusam essas linhas com `target2_missing`/`target3_missing` e correm sobre subpopulação diferente dos outros cinco contrastes. |

Complemento de forma, anotado nesta avaliação: o artefato não grava um `read_at` transacional
(§ "Sobre o carimbo de leitura"). Registrar `read_at` na próxima execução é barato e alinha o
experimento ao [[_TEMPLATE-EXP]].

## Reagendamento

**O teste é repetir esta mesma execução, não refinar a estatística.** Quando a população tiver
**≥ 30 dias UTC distintos com pares elegíveis**, rodar o **mesmo comando** com um `--as-of` novo:

```
uv run python infra/scripts/replay_exits.py \
  --database-url postgresql+asyncpg://... --versions momentum,volume_anomaly \
  --as-of <novo corte UTC> --out .claude/state/r1-proof-<data>.md
```

A execução nova entra aqui como **avaliação acrescentada**, com o par de dígitos dela; nada desta
página é reescrito. Regras que continuam valendo na repetição: a família é de **sete** contrastes,
o efeito mínimo é **0,05 R**, o corte comum de horizonte vem **antes** do pareamento, e a variante
"vencedora" **nunca** é ativada automaticamente — ativar uma `strategy_version` é ato auditado
(`infra/scripts/activate_strategy_version.py`), com pré-requisitos provados, e é decisão do Everton
quando muda o que o produto faz.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| R1 — 8 políticas / 7 contrastes, `as_of = 2026-09-06T20:55Z` | 2026-09-06 | Piloto do bloco de saídas (T-005 + L1 + L2) sobre entradas congeladas | commit `2c6bb2d`; `.claude/state/r1-proof.md`, `r1-proof.json`, `notes-R1.md` |
| Execução preliminar `as_of = 2026-09-06T17:00Z` | 2026-09-06 | Feita **antes** de `as_of` virar corte de dados; serve como evidência de apoio da §2, **não** como segunda medição | `.claude/state/notes-R1.md` §8 |

## Relacionadas

[[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] ·
[[Registro de Tentativas]] · [[Strategy Backlog]] · [[Strategy Performance]] · [[Open Bugs]] ·
[[Strategies]] · [[Momentum Agent]] · [[Volume Agent]] · [[Workers]] · [[Changelog]] ·
[[Dialogos/SHADOW]] · [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0005-stops-quando-eles-param-perdas]] · [[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] · [[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] · [[KB-0042-o-open-nao-e-preco-executavel]]

## Fontes

`.claude/state/r1-proof.md` · `.claude/state/r1-proof.json` · `.claude/state/notes-R1.md` ·
`.claude/state/brief-R1-exit-policy-replay.md` · `.claude/state/astra-review-R1-replay.md` ·
`.claude/state/astra-review-R1-replay-diff.md` · `.claude/state/astra-review-R1-replay-fixes.md` ·
commit `2c6bb2d` · `infra/scripts/replay_exits.py` ·
`packages/indicators/hunter_indicators/replay/**` ·
`services/strategy-worker/hunter_strategy_worker/replay/**` ·
`services/strategy-worker/hunter_strategy_worker/{walker,settle,funding,tracking_repo}.py` ·
`docs/plans/SHADOW-LAB.md` (itens 9 e 11 da decisão conjunta)

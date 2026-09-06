# notes-R1 — Replay de políticas de saída (EXP-0004)

Decisões que o código não conta sozinho, e as coisas que só apareceram ao rodar contra o banco.
Prova numérica em `.claude/state/r1-proof.md` (+ `r1-proof.json`). **Nada foi ativado, nada foi
commitado, nenhuma tabela do Lab foi escrita.**

## 1. O que é reuso e o que é novo

O replay **não reimplementa o acompanhamento**. Um braço é um `TrackingPlan` diferente dobrado pelo
mesmo `hunter_strategy_worker.walker.walk` e fechado pelo mesmo `settle.settle` (portanto pelo mesmo
`funding.resolve_funding`, já com a correção de `d878fd6`). O plano é reconstruído por
`tracking_repo.OpenTracking.plan` a partir das colunas gravadas — `virtual_stop`, `virtual_targets`,
`meta.entry_plan`, `meta.assumed_costs`, `meta.horizon_s` —, nunca recalculado pela estratégia, que
é o que garante escala de banco (`NUMERIC(28,10)`) idêntica.

Novo mesmo só existe onde a regra não cabe num nível de preço:

| política | como é expressa | walker |
|---|---|---|
| `base`, `INV-B`, `INV-E`, `TGT-3`, `TGT-4.5`, `EXIT-NOTGT` | só um plano diferente | roda inalterado |
| `INV-C`, `EXIT-CHAN` | observador puro em `hunter_indicators.replay.observers` | roda inalterado; recebe `pending_invalidation` |

`fold_arm` chama `walk` **uma barra por vez** — `walk` é um fold, então isso é a mesma computação —
e usa a costura entre barras para o observador olhar o fechamento que acabou de acontecer. Quem paga
a invalidação (na próxima abertura elegível) e com que prioridade (`stop > alvo > horizonte >
invalidação`) continua sendo o walker. O observador só roda depois do `walk` daquela barra, só com o
acompanhamento `active`, só quando `pending_invalidation` ainda é falso, e nunca limpa um pendente.

## 2. `EXIT-CHAN` conserva a invalidação original

Erro que a Astra pegou no desenho: se o braço do canal desligasse a invalidação, `CHAN − NOTGT`
mediria *canal + remoção da invalidação*. `EXIT-CHAN` mantém o nível nativo no plano e **acrescenta**
o canal; só `INV-C` desliga a observação nativa, porque ela é substituída. A cobertura publica o
gatilho, que o `result` canônico (`invalidated` para os três) esconderia — na prova:
`base {invalidation: 117}`, `INV-C {two_closes: 46}`, `EXIT-CHAN {channel: 18, invalidation: 137}`.

## 3. O alvo sentinela

`TrackingPlan.target1` não é opcional, então "sem alvo" é um nível inalcançável declarado
(`referência × 10⁶`). `check_target_unreachable` **prova** que nenhuma máxima da janela replicada o
tocou; se tocasse, o braço interromperia em vez de fabricar uma saída por alvo.

## 4. Pareamento congelado na base

A admissão (`stop < P_entry < alvo`, `walker._enter`) fica congelada na base: um braço nunca entra
onde a base não entrou. Duas recusas são tratadas de modo diferente:

- `no_entry: late:*` é **herdada sem dobrar nada** — atraso é evidência sobre o relógio da decisão e
  nenhuma vela rededuz isso. Essas linhas ficam fora do denominador da reprodução (`late` na tabela);
- `no_entry: geometry` é **rededuzida** da barra de entrada. Copiar a recusa de volta seria auditar
  o registro contra ele mesmo (Astra, revisão do diff). Se o replay discordar, a auditoria acusa
  `tracking_state`/`no_entry_reason` divergentes (há teste para isso).

Nenhum braço ocupa ou rearma slot: o replay só faz `SELECT`, e a transação é aberta
`REPEATABLE READ, READ ONLY` — quem impede a escrita é o Postgres, não a revisão de código (há teste
que tenta um `UPDATE` e recebe `read-only transaction`).

## 5. `as_of` é corte de dados, não só de população

Primeira versão usava `as_of` só para filtrar quais decisões entram, e carregava velas até o
horizonte de qualquer jeito. Isso quebra a própria palavra "maduro": uma execução "as of 17:00"
resolvia um horizonte das 20:00 com velas que o corte diz que ela não pode ver. Agora
`load_series` corta em `last_closed_minute(as_of)` (mesma função do motor de outcomes) e o que passa
do corte vira `immature` — com teste que prova que a vela seguinte, já presente na tabela, não entra
na dobra.

## 6. Blocos: a população inteira é **um** bloco

O bloco é o dia UTC da entrada (a dependência é transversal — muitas altcoins reagindo ao mesmo BTC).
Na leitura de 2026-09-06T20:55Z, **as entradas caem todas em 2026-09-06** (o Lab só foi ativado
em 05/09 23:19 e a primeira entrada é 06/09 00:26). Então `B = 1`:

- IC por bootstrap de blocos é **indisponível com motivo** (`single_block`) — `[efeito, efeito]`
  seria tautologia, não precisão;
- o p por inversão de sinal devolve `1.0` **por construção** (com um bloco só há duas configurações
  e ambas têm o mesmo `|T|`). Isso **não é evidência de equivalência**, é ausência de replicação;
- Holm sobre a família fixa de sete não muda nada, e não poderia: mesmo com seis blocos o menor p
  atingível seria `2/64 = 0,031 > 0,05/7`.

Ou seja: **os sete contrastes desta rodada são descritivos**. As diferenças médias existem e valem
como aprendizado operacional (ordem de grandeza, direção, cobertura), não como teste.

## 6b. Corte de maturidade **antes** do pareamento

Segunda rodada da Astra: parear "os dois braços resolveram" seleciona trade por velocidade de
desfecho — a base bate alvo em 20 min e o `EXIT-NOTGT` do mesmo sinal ainda está aberto, então o par
some justamente onde os braços mais diferem. Agora o corte é comum e vem antes: só entram no
pareamento os sinais cujo **horizonte inteiro** fechou até `as_of` (`ArmOutcome.matured`, vindo de
`series.truncated != "immature"`); os demais são descartados com motivo `immature_horizon` e
contados. O efeito não é cosmético — na leitura final, `TGT-3 − base` caiu de +0,118 R (sem o corte)
para +0,056 R e `TGT-4.5 − base` subiu de +0,081 para +0,112 R. Números sem o corte não devem ser
citados.

## 7. Estatística declarada antes de olhar resultado

Estimando: `Σ S_b / Σ n_b` (média por sinal), nunca média das médias diárias — dias têm tamanhos
diferentes e isso mudaria o estimando. IC: reamostragem de **blocos inteiros** com reposição,
percentil, semente `20260906`, 10 000 reamostras. p: inversão de sinal por blocos, exata até
`2¹² = 4096` configurações e amostrada acima disso com correção `(hits+1)/(draws+1)`. Holm a 5% sobre
**sete**, mesmo quando `--policies` roda um subconjunto. Efeito mínimo declarado 0,05 R, e a coluna
diz `abs(Δ)`: uma piora de 0,10 R também acende a bandeira, o sinal está no próprio Δ.

Par só existe quando **os dois braços** produziram `R_net` avaliável para o mesmo sinal; o resto é
cobertura contada por motivo, **nunca zero**. `r_ex_funding` roda pela mesma máquina como
sensibilidade, com a cobertura (maior) dele.

## 8. Reprodução da base: o que divergiu e por quê

Leitura de 2026-09-06T20:55Z, `input_digest 8b9cb982…`, `series_digest 759c1f5e…`: **339 linhas comparáveis, 325 reproduzidas
(95,9%), 14 divergentes, 0 campos de trajetória**; 275 entradas com horizonte maturado. Reprodução de **trajetória** (estado, resultado,
entrada, `entry_ts`, `exit_ts`, `exit_at_open`, `exit_bar_open`, preço de saída e `r_ex_funding`):
**1,0000**. O portão do passo 1 exige justamente a trajetória ≥ 0,99, e é ele que libera os
contrastes — sem ele o CLI não calcula contraste nenhum.

As 14 divergências são todas de **liquidação** e todas do mesmo desenho:

- 13 têm `r_multiple = null` gravado com motivo `funding_missing:2026-09-06T19:59:59/20:00:00` e hoje
  liquidam normalmente;
- 1 (`5b027f70…`) tinha `funding.per_unit = 0`, `settlements = 0` gravado e hoje cobra o settlement
  das 20:00:00 — `−0,8112908472` → `−0,8263601960`.

Todas saíram entre 20:00 e 20:27 e todas batem `r_ex_funding` exatamente (o `r_ex_funding` é
calculado com funding zero, então ele isola a trajetória). A explicação compatível é ingestão tardia
do settlement das 20:00: o worker liquidou entre 20:02 e 20:27 e a linha de `funding_rates` chegou
depois. **Compatível, não comprovado**, e isso está escrito no relatório: `funding_rates` **não tem
coluna de instante de ingestão**, então nada no banco decide quando a linha chegou. É uma lacuna de
proveniência que vale registrar como pendência (um `received_at` em `funding_rates` resolveria).

Evidência de apoio que roda hoje: numa leitura mais antiga, com `--as-of 2026-09-06T17:00:00Z`, a
reprodução foi **201/201 = 1,0000 com zero divergências** — nenhuma daquelas linhas estava perto do
corte. (Aquela execução foi feita antes de `as_of` virar corte de dados; hoje ela cobriria menos
linhas, porque entradas com horizonte além das 17:00 passariam a `immature`.)

### 8b. O que a auditoria classifica como divergência

`terminal` gravado que o replay recusa como `no_entry` é **divergência de trajetória**, não "sem
resolver" — se caísse em "sem resolver" sairia do denominador do portão e um replay que recusasse
todas as entradas marcaria 1,0000 (contraprova executada pela Astra: 1 acerto + 99 dessas dava
`trajectory_rate=1.0000, passed=True`). "Sem resolver" ficou só para o que o replay realmente não
terminou: `immature`, `gap`, `channel_window_unavailable`, `target2/3_missing`.

## 9. L1 (alvo) só existe para `momentum`

`volume_anomaly_v1/v2` persiste **um** alvo (`virtual_targets` com 1 elemento; `momentum` tem 3).
`TGT-3`/`TGT-4.5` são recusados nessas linhas com `target2_missing`/`target3_missing` — recusa
explícita, nunca rebaixamento silencioso para a base. Consequência que o relatório declara: os dois
contrastes de alvo correm sobre uma **subpopulação diferente** (só momentum) dos outros cinco, e não
são comparáveis linha a linha com eles.

## 10. Como rodar e o que é reprodutível

```
uv run python infra/scripts/replay_exits.py \
  --database-url postgresql+asyncpg://... --versions momentum,volume_anomaly \
  --as-of 2026-09-06T20:55:00Z --out .claude/state/r1-proof.md
```

Reprodutibilidade medida, e o que ela quer dizer: duas execuções seguidas com o mesmo `--as-of`
deram Markdown e JSON **byte a byte idênticos** (`md5 0aba2f68…`) enquanto o banco não mudou. Numa
terceira, feita minutos depois, o Lab tinha terminalizado mais um outcome decidido antes do corte:
os dois dígitos mudaram e o arquivo também — as métricas e os sete contrastes ficaram idênticos
(a população maturada não muda), mas as contagens de população sim. É exatamente para isso que os
dígitos existem: **"o mesmo banco" não é frase estável num Lab que continua escrevendo**.
`--as-of` sem fuso é **recusado** (`astimezone` num datetime ingênuo leria o fuso da máquina).
Como o Lab continua escrevendo, "o mesmo banco" não é frase estável: o documento carrega
`input_digest` (sha256 das linhas de `signal_outcomes` lidas) **e** `series_digest` (sha256 das
velas efetivamente dobradas — um backfill muda contraste sem mudar nenhuma linha de outcome). Duas
execuções só são comparáveis com os dois dígitos iguais.

O banco local não expõe porta; a prova foi feita por um encaminhador local
(`docker run --rm --network docker_default -p 15432:5432 alpine/socat …`), nunca contra a VPS. A
coorte grande da VPS **não** foi usada: exigiria dump por `infra/vps/backup_postgres.sh` e restauração
num container local, e o orquestrador não liberou isso nesta rodada.

## 10b. Limite que continua aberto: o funding não é cortado por `as_of`

O corte `as_of` vale para as **velas**. O funding não: quem consulta `funding_rates` é o `settle` de
produção (`entry_ts − 3d` até `exit_ts + 2s`), reusado verbatim — e é reuso justamente porque
reimplementá-lo aqui seria pior. Consequência real, apontada pela Astra: uma linha de funding
ingerida depois do corte é visível à liquidação e pode inclusive completar a inferência de cadência.
É exatamente o fenômeno da §8. Está declarado no documento (`funding_read:
as_stored_at_read_time`) e o efeito é isolável pela coluna `r_ex_funding`, que não depende de
funding nenhum. Fechar isso de verdade exige um parâmetro de corte em `settle` (arquivo fora do
escopo deste brief) ou um `received_at` em `funding_rates`.

## 11. Pendências

0. **`settle` sem corte temporal** (§10b) — hoje o único caminho é mexer em `settle.py`.
1. **`funding_rates` sem instante de ingestão** — sem ele, "a linha chegou depois" é sempre
   *compatível*, nunca comprovado.
2. **`B = 1`** — qualquer conclusão sobre saídas exige janela em dias distintos. Repetir esta mesma
   execução daqui a algumas semanas é o teste, não refinar a estatística.
3. **Alvos informativos em `volume_anomaly`** — enquanto ela persistir um alvo só, L1 é um
   experimento de `momentum`.
4. **Recompute de funding** — as 14 linhas divergentes são exatamente a população de
   `infra/scripts/recompute_funding.py --apply`; o replay não escreve, então elas continuam como
   estão até alguém rodar aquele script.

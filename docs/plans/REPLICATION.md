# Protocolo de Replicação — quando uma estratégia promissora passa a ser considerada real (T3.19)

**Status:** protocolo congelado em 2026-09-08 (quant-engineer, T3.19). Pedido do Everton, literal:
*"quando uma estrategia for promissora repitir ela varias vezes e fazer replicala para validar se é
real ou nao a estrategias"*. Este documento é a resposta: **o que "repetir" significa aqui, quantas
vezes, com que limiar, e o que o resultado NÃO autoriza.**

**Nada neste protocolo chega à carteira.** Nenhum passo ativa, deprecia, reparametriza ou promove
uma versão; nenhum passo cria, amplia ou reinicia carteira (`docs/RISK_ENGINE.md` §11: uma carteira
principal por organização, permanente — "validada" nunca é argumento para uma segunda). Toda irmã
nasce `purpose = research_only`, que a ponte de execução recusa **pelo nome**, antes de qualquer
consulta de carteira (`services/execution-worker/hunter_execution_worker/bridge_screen.py`, recusa
`research_only`). O protocolo **fala**; quem decide é o Everton, e a promoção continua sendo o ato
auditado de `infra/scripts/activate_strategy_version.py` (regra 8 do plantão da Sexta-feira).

---

## 1. Vocabulário e os dois instantes que importam

1.1 **Resultado avaliável** (`resultado avaliável`): linha de `signal_outcomes` com
`tracking_state = 'terminal'` e `r_multiple IS NOT NULL` — o R líquido hipotético de
`SHADOW-LAB.md` §3, já com spread, slippage, taxa e funding assinado. `no_entry`, `censored`,
`pending_entry` e `active` **nunca** entram no numerador nem no denominador de nada aqui; entram
só na cobertura (§8).

1.2 **Dia distinto**: `date(agent_signals.emitted_at AT TIME ZONE 'UTC')` dos sinais dos resultados
avaliáveis. `emitted_at` é gravado com o `decision_at` da decisão
(`hunter_strategy_worker/persist.py`), então "dia distinto" é dia de **decisão**, não de saída.

1.3 **`expectancy_r`**: média aritmética do `r_multiple` sobre os resultados avaliáveis
(*expectancy líquida hipotética em R por entrada encerrada avaliável*, item 9 da decisão conjunta).
**`profit_factor`**: Σ dos R positivos ÷ |Σ dos R negativos|; **nulo com motivo** quando um dos
lados é vazio (`sem_perdas` / `sem_ganhos`), nunca infinito, nunca zero inventado.

1.4 **Régua de maturidade (placar, T3.18)** — `MATURIDADE_RESULTADOS = 100` resultados avaliáveis
**E** `MATURIDADE_DIAS = 30` dias distintos. Abaixo disso o veredito do placar é `inconclusivo`
(`SHADOW-LAB.md` §9, regra editorial).

1.5 **Meia-régua (blocos 1 e 2)** — `MATURIDADE_META_RESULTADOS = 50` **E**
`MATURIDADE_META_DIAS = 15`. *Por que metade:* a régua cheia existe para o **primeiro** veredito
sobre uma versão desconhecida, quando o número é a única evidência. Nos blocos de replicação a
versão já passou pela régua cheia uma vez, e o que se pede a cada bloco não é um veredito
independente — é **concordância**. Exigir 100 × 4 blocos (e × 10 irmãs) transformaria o protocolo
em algo inalcançável dentro de um trimestre, e a proteção contra o acaso passa a vir da
**conjunção** dos quatro blocos e da regra 7-em-10, não do tamanho de cada bloco isolado. O preço
está declarado em §7: metade da amostra dobra, grosso modo, a largura do intervalo de cada bloco.

1.6 **`promising_at`** — o instante em que a versão pai foi vista `validada` pela primeira vez.
É a coluna `strategy_versions.promising_at` (`0012_replication`), gravada (§4.1) e **congelada**;
nunca é recalculada para trás. `promising_by` diz qual veredito a carimbou. Sem `promising_at` não existe
bloco 1: "fora da amostra" só quer dizer alguma coisa contra um marco que já estava escrito.

1.7 **Versão pai**: a `strategy_version` promissora. **Irmã**: uma versão derivada dela por jitter
de parâmetros (§4.2). **Braço de replicação**: o rótulo `replication:<parent_version_id>:<k>`,
`k` de 1 a N, que identifica cada irmã — e que, desde a `0012_replication`, **é** a coorte de
`shadow_episodes` que ela carimba (§4.4).

---

## 2. Promissora não é real

Uma versão é **promissora** quando o placar (T3.18) diz `validada` pela primeira vez:

```
madura  = resultados_avaliáveis >= 100 E dias_distintos >= 30
validada = madura E expectancy_r > 0 E profit_factor > 1
```

`EXPECTANCY_MIN = 0` e `PROFIT_FACTOR_MIN = 1`, ambos com desigualdade **estrita**; empate não
passa. Isso é o **fim da fase de descoberta e o começo do protocolo**, não uma conclusão. Um único
número bom sobre uma única população é exatamente o que a literatura manda desconfiar: com um número
suficiente de configurações tentadas sobre a mesma população, a melhor delas parece boa **mesmo que
nenhuma tenha valor** ([[KB-0010]] — PBO/Deflated Sharpe, Bailey & López de Prado; [[KB-0049]] —
Aronson, viés de garimpo e Reality Check de White; [[KB-0003]] — data snooping na família de
lookbacks). Este projeto já produziu, numa única rodada de conhecimento, seis famílias de variantes
sobre os mesmos mercados e dias; o `Registro de Tentativas` existe por isso.

**Real** exige **quatro repetições independentes concordando** (§3). Enquanto qualquer bloco estiver
imaturo, o veredito de replicação é `replicando`. Quando um bloco **maduro** falha, o veredito é
`refutada`.

---

## 3. Os quatro blocos

### 3.1 Bloco 1 — Fora da amostra no tempo (`out_of_sample`)

População: resultados avaliáveis cujos sinais têm `emitted_at > promising_at`. Só eles.

- **Maturidade do bloco:** meia-régua (§1.5) — ≥ 50 resultados **E** ≥ 15 dias distintos, contados
  dentro do bloco.
- **Passa** quando maduro e `expectancy_r > 0`.
- **Falha** (→ `refutada`) quando maduro e `expectancy_r <= 0`.
- **Imaturo** → `replicando`, com o quanto falta explícito ("38 de 50 resultados · 9 de 15 dias").

É o walk-forward pobre que temos ([[KB-0049]], Pardo): a versão não pode ser reparametrizada depois
de `promising_at`; qualquer mudança de conteúdo é **versão nova** e recomeça o protocolo do zero
(`SHADOW-LAB.md` §1; regra 2 do plantão: hipótese e protocolo são congelados).

### 3.2 Bloco 2 — Irmãs de parâmetro (`siblings`)

`IRMAS_N = 10` versões irmãs derivadas do pai por **jitter uniforme independente de ±15 %**
(`JITTER_PCT = 0.15`) em **cada parâmetro numérico**, com RNG semeado e **semente registrada**
(§4.2). Cada irmã é uma linha real de `strategy_versions`, `purpose = research_only`,
`status = 'active'`, `code_ref` próprio (o mesmo módulo do pai) e o rótulo do braço no `changelog`.

- **Maturidade da irmã:** meia-régua (§1.5).
- **Irmã positiva:** madura **E** `expectancy_r > 0`.
- **Passa** quando `IRMAS_APROVADAS_MIN = 7` das 10 são positivas.
- **Falha** (→ `refutada`) quando ≥ 4 irmãs são **maduras e negativas** — a maioria necessária já é
  impossível.
- Caso contrário (irmãs ainda imaturas) → `replicando`.

*O que isso testa:* se o resultado do pai depende de um ponto exato no espaço de parâmetros, o
platô ao redor dele é plano ou não existe, e as irmãs mostram isso. Um pico isolado é a assinatura
clássica de sobreajuste ([[KB-0010]]); uma vizinhança inteira positiva é a evidência mais barata de
robustez que conseguimos produzir sem um walk-forward completo.

*O que isso NÃO testa:* as dez irmãs correm sobre **a mesma população de mercados e minutos** do
pai. Elas são dez leituras correlacionadas, não dez experimentos independentes — ver §7.

### 3.3 Bloco 3 — Metades de mercado (`market_halves`)

Os mercados distintos que produziram resultados avaliáveis do pai são partidos em duas metades por
**hash determinístico** da chave do mercado `<exchange>:<symbol>` (`sha256`, bit menos significativo
do primeiro byte → metade `a` ou `b`). A corretora entra na chave porque o mesmo `BTCUSDT` em duas
corretoras é mercado diferente. Determinístico e estável entre processos: `hash()` do Python é
salgado por processo e está **proibido** aqui.

- **Maturidade do bloco:** cada metade precisa de `METADES_MIN_MERCADOS = 3` mercados distintos
  **E** `METADES_MIN_RESULTADOS = 20` resultados avaliáveis.
- **Passa** quando as **duas** metades têm `expectancy_r > 0`.
- **Falha** (→ `refutada`) quando alguma metade madura tem `expectancy_r <= 0`.
- Metade imatura → `replicando`.

*Por que hash e não "as 10 maiores contra as 10 menores":* qualquer partição escolhida por uma
propriedade do resultado é a mesma pesquisa disfarçada de validação. O hash não sabe nada sobre
desempenho. É computação pura sobre resultados que já existem — **não cria coorte nova** e não
custa nada ao worker.

### 3.4 Bloco 4 — Bootstrap (`bootstrap`)

Reamostragem com reposição dos R líquidos avaliáveis do pai: `BOOTSTRAP_REAMOSTRAS = 1000`
reamostras, `BOOTSTRAP_CONFIANCA = 0.95`, semente registrada, intervalo percentil da **média**.

- **Recusa com motivo** quando `n < BOOTSTRAP_N_MIN = 30` (`amostra_insuficiente`): abaixo disso o
  intervalo percentil é ruído sobre ruído. Recusa é `replicando`, nunca `refutada`.
- **Passa** quando o intervalo de 95 % da média **exclui zero** — os dois extremos do mesmo lado.
- **Falha** (→ `refutada`) quando o intervalo i.i.d. cruza zero estando maduro.
- **Teste de sinal** (binomial exata, bicaudal, zeros excluídos) é **reportado** junto — positivos,
  negativos e `p_sign`. Ele **não decide**; é o contraste entre "ganha mais vezes" e "ganha mais
  dinheiro" ([[KB-0046]]: R-múltiplos e a assimetria que a simetria esconde). `SIGN_P_ALERTA = 0.05`
  serve só para pintar o número na tela.
- **Intervalo por blocos de dia** (`cluster bootstrap`, reamostrando **dias** inteiros em vez de
  resultados isolados) é calculado e reportado sempre. Rótulos de três barreiras se **sobrepõem no
  tempo** e mercados simultâneos são dependentes ([[KB-0051]], López de Prado: unicidade, purga e
  embargo; `SHADOW-LAB.md` §9 pede reamostragem em blocos de tempo). Regra: se o intervalo i.i.d.
  exclui zero **mas** o intervalo por dias cruza zero, o bloco **não passa e não refuta** — fica
  `replicando` com motivo `intervalo_por_dia_cruza_zero`, e o que falta é **mais dias**, não mais
  linhas. Passar exige os **dois** intervalos excluindo zero.

---

### 3.5 O que um replay histórico pode e não pode contar (T3.19b — **proposta**, não decisão)

O motor de replay (`docs/PIPELINE.md` §6c) roda a **mesma** versão, com os **mesmos** custos e as
mesmas regras de não-antecipação, sobre as velas persistidas, e grava sob a coorte `replay:<uuid>`.
Ele existe porque os blocos 1 e 2 desta seção precisam de 50 resultados e 15 dias **por irmã**, e a
faixa viva rende ~600 sinais/dia para a família inteira. A pergunta que ele levanta é de método, e
**quem decide é o Everton** — esta subseção propõe, não altera a régua:

**O que o replay não pode contar, e isto não é negociável dentro do protocolo:**

1. **Bloco 1 (`out_of_sample`) não aceita replay.** O bloco conta resultados com
   `emitted_at > promising_at`, e "fora da amostra no tempo" quer dizer *o mercado ainda não tinha
   acontecido quando a versão foi congelada*. Um replay sobre janela anterior a `promising_at` é,
   por definição, dentro da amostra; um replay sobre janela posterior é a mesma população que a
   faixa viva já mediu, contada duas vezes. Em nenhuma das duas leituras ele é evidência nova.
2. **A régua de maturidade do placar (§1.4) continua só com a coorte `prospective`.** É a regra
   editorial da `SHADOW-LAB.md` §9 e a T3.18 já a implementa; misturar as duas populações num
   número chamado "validada" é o pior resultado possível.
3. **Nenhum replay carimba `promising_at`.** O marco é o instante em que a versão foi vista
   `validada` pela avaliação prospectiva reservada dela.

**O que o replay pode contar, se o Everton aceitar:**

4. **Bloco 2 (`siblings`), com a janela declarada.** É o bloco que o replay resolve de verdade: as
   dez irmãs nascem hoje e precisariam de 15 dias × 10 para dizer qualquer coisa; um replay das dez
   sobre os mesmos 31 dias do pai entrega a vizinhança inteira em horas. O bloco pergunta se o
   **platô** de parâmetros existe, e um platô é uma propriedade da superfície, não do calendário.
   *Preço declarado:* as dez irmãs replayadas correm sobre exatamente os mesmos minutos do pai —
   dez leituras correlacionadas, como o §3.3 já dizia, agora sem nem a variação de calendário que a
   corrida viva dava. Se aceito, o relatório tem de dizer `siblings: replay sobre <janela>` e nunca
   apresentar o bloco como se fosse prospectivo.
5. **Bloco 3 (`market_halves`) e bloco 4 (`bootstrap`)** são computação sobre resultados que já
   existem; sobre uma população de replay eles são calculáveis e **informativos**, nunca
   substitutos. Se a população do pai for replay, os dois blocos herdam a mesma etiqueta.

**Como o placar mostra (T3.18, contrato):** as coortes de replay são lidas **separadamente** das
vivas e rotuladas — `replay: N operações sobre <janela>` — e nunca somadas na régua de maturidade.
Um cartão de versão mostra os dois números lado a lado, com a régua aplicada só ao vivo.

## 4. Como as irmãs nascem — `infra/scripts/replicate_strategy_version.py`

```
uv run python infra/scripts/replicate_strategy_version.py <key> <version> \
    --siblings 10 --seed <n> [--dry-run] [--report] \
    [--force-research "<motivo>"] [--changelog "<texto>"]
```

Conexão de **dono** (`DATABASE_URL_MIGRATIONS`), como o script de ativação: `0011` revogou
`INSERT` em `strategy_versions` de todo papel de aplicação, e `purpose` só o dono escreve.

**4.1 Pré-condições, cada uma uma recusa (nunca um aviso):**

1. `0002_shadow_lab` e `0010_strategy_purpose` aplicadas;
2. o pai existe, está **congelado** (`activated_at IS NOT NULL`) e é `research_only` — `paper` e
   `live` são recusados pelo nome (uma linha que pode tocar carteira nunca é replicada);
3. este build carrega o código do pai e o `code_ref` **bate** com o digest deste build (uma irmã
   tem de rodar exatamente o código que o pai rodou);
4. o pai é `validada` pela régua do §2 — computada em SQL sobre os próprios `signal_outcomes`.
   Sem isso a execução **para**, salvo `--force-research "<motivo>"`, que existe só para os
   experimentos manuais do Everton, exige motivo escrito, marca `forced = true` no evento de
   auditoria e **não** grava `promising_at`;
5. o pai ainda não tem irmãs. Rodar a replicação duas vezes sobre o mesmo pai seria **duplicar as
   tentativas** e inflar exatamente o falso positivo que o protocolo combate; a segunda rodada é
   recusada com o número de irmãs existentes.

Ao passar, `promising_at` é gravado no mesmo commit, e desde a `0012_replication` (T3.19c) o lugar
durável é a **coluna** `strategy_versions.promising_at`, escrita por
`hunter_strategy_worker.replication.mark_promising` (conexão de dono, idempotente — um carimbo
existente nunca se move) junto de `promising_by`, que nomeia o veredito que carimbou. A auditoria
continua: `system_events` (`component = 'replicate_strategy_version'`,
`event = 'strategy_version_promising'`, `data = {strategy_version_id, promising_at, promising_by}`),
e o `changelog` de cada irmã continua carregando `promising_at=` — as duas cópias antigas viram
redundância legível, não a fonte. `load_promising_at` lê a coluna primeiro, depois o `changelog`,
depois o evento (que expira em 30 dias). **A pendência declarada da T3.19 está fechada.**

**4.2 O jitter.** Para cada parâmetro numérico do `default_parameters` congelado do pai, um fator
`U(1 − 0,15; 1 + 0,15)` **independente**, de um `numpy.random.Generator(PCG64(seed))` com semente
registrada:

- **inteiros** são arredondados (meio para cima) e nunca cruzam zero: um inteiro positivo tem piso
  `1` (`JITTER_MIN_INTEIRO = 1`), porque janela zero não é uma variante, é um erro;
- **decimais** são quantizados em `max(casas_do_original + JITTER_CASAS_EXTRA, JITTER_CASAS_MIN)`
  casas, com `JITTER_CASAS_EXTRA = 2` e `JITTER_CASAS_MIN = 4`, sem notação exponencial e sem zeros
  à direita, para continuarem casando com o `pattern` do schema
  (`hunter_core.strategies.schema.DECIMAL_PARAM`);
- **inteiro pequeno pode não se mover**: `atr_period = 14` com fator 1,01 volta a 14, e `3 ± 15 %`
  arredonda sempre para 3. Nesse parâmetro a irmã é idêntica ao pai, e o relatório mostra isso na
  lista `untouched` — é limitação declarada do jitter multiplicativo, não um defeito escondido;
- **zero continua zero** (`return_min = 0` não vira `0,0000001`): o jitter multiplicativo não
  inventa um limiar onde a versão declarou não ter nenhum;
- `minimum`/`maximum` do schema são respeitados por clamp quando existirem — os schemas atuais não
  os declaram, e a limitação está escrita no próprio `schema.py`;
- **não numéricos** (timeframes, enums, strings, booleanos) passam **intactos**: trocar `atr_timeframe`
  não é jitter, é outra estratégia;
- cada conjunto é validado com `hunter_strategy_worker.activation.validate_parameters` contra o
  schema congelado do pai **antes** do INSERT, e um conjunto cujo `params_hash` colida com o do pai
  ou com o de outra irmã é recusado (seria a mesma experiência contada duas vezes).

Os parâmetros de **custo assumido** (`assumed_spread_bps`, `slippage_bps`, `fee_bps`) também são
numéricos e **também sofrem jitter**, conforme o brief. Isso é deliberado e tem leitura própria:
uma irmã com custo 15 % maior que morre é a **análise de sensibilidade a custos** que o item 9 da
decisão conjunta pede, no mesmo pacote ([[KB-0008]], [[KB-0037]], [[KB-0038]]). Quem quiser o
platô só das regras de entrada tem de ler as irmãs sabendo disso.

**4.3 O que é escrito.** N linhas em `strategy_versions`, numa transação, cada uma com: próximo
`v<n>` livre; `parameters_schema` e `params_format` copiados **byte a byte** do pai;
`default_parameters` jitterados em forma canônica (`params_format = 1`); `code_ref` recomputado do
módulo que o `code_ref` congelado do pai nomeia; `status = 'active'`; `activated_at = now()`;
`purpose = 'research_only'`; `replication_parent_id`/`replication_index` (a linhagem em coluna,
`0012_replication`); `changelog` com o rótulo do braço, `promising_at`, semente e índice.

**Do pai, uma única coluna se move:** `promising_at` (com `promising_by`), por
`hunter_strategy_worker.replication.mark_promising`, no mesmo commit — e nunca mais de uma vez.
Fora isso o pai não é tocado: nem `changelog`, nem `status`, nem parâmetros. A frase original desta
seção ("o pai não é tocado — nenhum UPDATE") valia enquanto o carimbo morava no `changelog` das
irmãs e num `system_events` de 30 dias, o que fazia do marco de onde o bloco 1 conta uma substring
de texto livre; a `0012` trocou isso por uma coluna, e a troca está registrada em
`docs/DATABASE.md` §24.2. Um evento `strategy_version_replicated` resume a rodada em
`system_events` com `data` completa (pai, semente, irmãs, hashes).

`--dry-run` imprime os N conjuntos jitterados e não escreve nada. `--report` imprime os quatro
blocos do pai e não escreve nada.

**4.4 O rótulo `replication:<parent_version_id>:<k>` É a coorte do banco (desde a
`0012_replication`, T3.19c).** A pendência que esta seção declarava está fechada. O CHECK
`ck_shadow_episodes_cohort_format` e `hunter_core.domain.enums.SHADOW_COHORT_PATTERN` aceitam agora
`prospective`, `replay:<uuid>` **e** `replication:<uuid>:<k>` com `k` de 1 a 99 (`[1-9][0-9]?`: `:0`
e `:01` são recusados, porque uma segunda grafia do braço 1 seria uma segunda população sob um nome
que o relatório já usa). Os dois ramos antigos continuam byte a byte iguais — todo episódio já
gravado segue válido.

A coorte deixou de ser só de **processo** (`SHADOW_COHORT`): `ActiveVersion.cohort()`
(`catalogue.py`) carimba o braço quando a linha da versão tem linhagem, e a coorte do processo
quando não tem. **Um replay continua replay**, irmã ou não — coortes separam populações da mesma
versão, e um replay nunca é a avaliação prospectiva reservada dela (SHADOW-LAB.md §1).

A ponte de execução já estava pronta para o rótulo: `bridge_screen.py` (T3.15e) admite
`cohort = "prospective"` e recusa qualquer outra com `cohort_not_live`, citando nominalmente "a
replication sibling's cohort". A diferença é que agora existe uma coorte de verdade para ela
recusar — antes, essa barreira recusava um nome que nada podia escrever.

**A linhagem também virou coluna.** `strategy_versions.replication_parent_id` e
`replication_index` (com `CHECK` bicondicional, faixa 1..99, `parent <> id` e
`UNIQUE (parent, index)`), gravadas no mesmo `INSERT` que ativa a irmã e congeladas depois disso.
`replication_stats.load_sibling_rows` lê a coluna e, ainda, o rótulo do `changelog` — que é o que
uma irmã derivada antes da migração tem. Detalhes em `docs/DATABASE.md` §24.

**A separação que importa não depende desse rótulo.** Cada irmã é uma `strategy_version_id`
distinta, com slot de episódio, `params_hash`, sinais e outcomes próprios (a coorte só separa
populações da **mesma** versão), e o isolamento em relação à carteira tem **três** barreiras
independentes, todas provadas por teste em
`services/strategy-worker/tests/test_replicate_strategy_version.py`:

1. `purpose = research_only` na coluna congelada — a ponte recusa `research_only` pelo nome, antes
   de qualquer consulta de carteira;
2. nenhuma linha em `agents` liga a irmã a uma carteira — a consulta de candidatos da ponte só
   enxerga versões que a carteira roda;
3. o filtro de coorte de T3.15e recusa `cohort_not_live` para qualquer coorte que não seja
   `prospective` — e desde a `0012_replication` ele vale de fato, porque a irmã carimba
   `replication:<pai>:<k>` nos próprios sinais (§4.4).

---

## 5. Veredito de replicação

| Veredito | Quando |
|---|---|
| `none` | a versão nunca foi `validada`; não há protocolo em curso |
| `promissora` | `validada` pela primeira vez, `promising_at` gravado, irmãs ainda não criadas |
| `replicando` | irmãs criadas e **algum** bloco ainda imaturo (ou bootstrap recusado por amostra) |
| `real` | os **quatro** blocos passam |
| `refutada` | **algum** bloco maduro falha |

`refutada` **continua pesquisa**: nada é depreciado, desativado ou apagado automaticamente. O
protocolo só **diz**. Uma versão refutada pode seguir rodando como sombra — o registro do que não
funcionou vale tanto quanto o do que funcionou, e apagá-lo é como perder o experimento
([[KB-0010]]: o preço de cada variante só é pagável se todas estiverem no registro).

Ordem de avaliação, fixa e parte do contrato: **1 → 2 → 3 → 4**. Uma refutação num bloco anterior
é reportada com os blocos seguintes ainda calculados (o relatório é completo), mas o veredito é
`refutada` na primeira falha madura, e o motivo nomeia o bloco.

---

## 6. Contrato do placar (para T3.18 e seguidores)

Por versão, o placar publica o bloco `replication`. Este é o payload **real** de
`ReplicationReport.to_jsonable()` (`hunter_indicators.replication.protocol`), não um esboço — quem
implementar o endpoint chama `hunter_strategy_worker.replication_stats.build_report(conn,
version_id, seed=...)` e serializa o que sai:

```jsonc
"replication": {
  "status": "none|promissora|replicando|real|refutada",
  "reason": "out_of_sample: expectancy_nao_positiva",   // null quando status = real
  "promising_at": "2026-09-08T12:00:00Z",               // null quando não gravado
  "parent": {"evaluable": 182, "days": 2, "markets": 114, "expectancy_r": "-0.2836",
             "profit_factor": "0.4976", "profit_factor_reason": null, "sum_r": "-51.6100",
             "wins": 63, "losses": 119, "verdict": "inconclusivo|validada|reprovada"},
  "out_of_sample": {"passed": null, "reason": "imaturo: 38 de 50 resultados · 9 de 15 dias",
                    "evaluable": 38, "days": 9, "markets": 12, "expectancy_r": "0.1200",
                    "profit_factor": "1.4", "profit_factor_reason": null, "sum_r": "4.56",
                    "wins": 20, "losses": 18, "mature": false},
  "siblings": {"passed": null, "reason": "imaturo: 5 de 7 positivas", "n": 10, "expected": 10,
               "required": 7, "mature": 6, "positive": 5,
               "arms": [{"k": 1, "version": "v2", "mature": true, "positive": true,
                         "evaluable": 61, "days": 17, "markets": 9, "expectancy_r": "0.09",
                         "profit_factor": "1.2", "profit_factor_reason": null,
                         "sum_r": "5.5", "wins": 33, "losses": 28}]},
  "market_halves": {"passed": false, "reason": "metade_b_negativa",
                    "a": {"half": "a", "markets": 64, "evaluable": 101,
                          "expectancy_r": "0.11", "mature": true, "reason": null},
                    "b": {"half": "b", "markets": 50, "evaluable": 81,
                          "expectancy_r": "-0.02", "mature": true, "reason": null}},
  "bootstrap": {"passed": false, "reason": "intervalo_cruza_zero", "n": 182, "mean": "-0.2836",
                "ci_low": "-0.4067", "ci_high": "-0.1491", "resamples": 1000, "seed": 1,
                "confidence": "0.95", "method": "iid_percentile_v1", "groups": null,
                "refused_reason": null,
                "day_cluster": {"n": 182, "mean": null, "ci_low": null, "ci_high": null,
                                "resamples": 0, "seed": 1, "confidence": "0.95",
                                "method": "day_cluster_percentile_v1", "groups": null,
                                "refused_reason": "grupos_insuficientes: 2 < 5"},
                "sign_test": {"positives": 63, "negatives": 119, "zeros": 0,
                              "p_sign": "0.0000", "method": "exact_binomial_v1",
                              "refused_reason": null}}
}
```

Convenções: `passed` é **três estados** (`true` passou, `false` falhou maduro, `null` aguardando), e
`reason` nunca é nulo quando `passed` não é `true`. Todo número em `Decimal` serializado como string
(dinheiro e R nunca viajam em float), todo nulo com motivo, todo limiar devolvido junto do valor
(`required`, `expected`, `resamples`, `confidence`, `seed`). As definições são as mesmas do plantão
da Sexta-feira — o placar é a **vista viva** do mesmo SQL, e a avaliação datada em
`obsidian/05-EXPERIMENTS/` segue sendo o registro.

---

## 7. Multiplicidade — o que este protocolo faz com ela, e o que ele não resolve

Criar 10 irmãs é **criar 10 testes novos**. Se o pai não tivesse valor nenhum, a probabilidade de
pelo menos uma irmã "dar positiva" por acaso é alta; é literalmente o mecanismo de
[[KB-0010]] (o máximo esperado sobre N tentativas) e o alvo do Reality Check de White
([[KB-0049]]). As respostas embutidas aqui, na ordem em que mordem:

1. **A regra é 7 em 10, não 1 em 10.** O critério não é "alguma irmã sobreviveu", é "a vizinhança
   inteira sobrevive". Sob a hipótese nula ingênua de irmãs independentes com 50 % de chance cada,
   ver ≥ 7 positivas tem probabilidade ≈ 17 % — e as irmãs **não** são independentes (correm sobre
   os mesmos minutos), o que empurra o resultado para os extremos: ou quase todas passam, ou quase
   nenhuma. Por isso a regra é de maioria qualificada e **não** um teste de significância; ela
   diz "o platô existe", não "p < 0,05".
2. **O bootstrap olha o pai, não o vencedor entre as irmãs.** Nunca se escolhe a melhor irmã para
   depois testá-la: isso seria o garimpo com outro nome. A irmã é evidência **sobre o pai**.
3. **A conjunção dos quatro blocos** é o que carrega o peso. Cada bloco isolado é fraco de
   propósito (meia-régua); passar nos quatro exige concordância entre eixos que erram de formas
   diferentes: tempo (bloco 1), parâmetros (2), mercados (3) e amostragem (4).
4. **O que continua não resolvido, escrito e não escondido:** (a) não calculamos PBO/CSCV nem
   Deflated Sharpe — não temos as configurações tentadas num formato explorável, e o
   `Registro de Tentativas` é condição necessária e não suficiente ([[KB-0049]]); (b) o Reality
   Check exige a distribuição conjunta dos candidatos, que não temos; (c) as observações se
   sobrepõem no tempo e não são independentes ([[KB-0051]]) — daí o intervalo por dias do §3.4;
   (d) todo R é **hipotético**, com custos assumidos declarados e não medidos ([[KB-0037]],
   [[KB-0038]], [[KB-0075]]); (e) nada aqui mede execução real, tamanho, impacto ou capacidade
   ([[KB-0036]], [[KB-0069]]).

**O que "real" quer dizer aqui, exatamente:** *o desempenho positivo do pai sobreviveu a quatro
repetições independentes sob as hipóteses de custo declaradas.* Não quer dizer "vai dar lucro", não
quer dizer "pode ir para a carteira", não quer dizer "está calibrado", não é promessa e não é
recomendação. Continua pesquisa, com o rótulo **SOMBRA — hipotético, sem capital, custos assumidos**.

---

## 8. Cobertura obrigatória em todo relatório

Junto de qualquer veredito vão, sempre: emitidos, pendentes, entradas, não entradas por motivo,
ativos, target, stop, expired, invalidated, censurados por motivo, funding indisponível, mercados
distintos, dias distintos, `as_of` e `read_at`. Se as contagens não fecham com o total emitido, o
relatório diz isso. Silêncio num log de pesquisa é indistinguível de instrumento quebrado (regra 10
do plantão).

## 9. Custo operacional declarado

Dez irmãs multiplicam por ~11 o número de avaliações, sinais, outcomes e slots de episódio da
família replicada, e cada irmã segura `tracking_hold` dos seus mercados (`SHADOW-LAB.md` §8). Antes
de replicar duas famílias ao mesmo tempo, olhe CPU do `strategy-worker`, tamanho de
`agent_signals`/`signal_outcomes` e o lag do consumidor. **Isto é um limite de recurso, não de
método** — mas replicar sem olhar transformaria a validação na causa da próxima falha de coleta.

**Com o motor de replay (T3.19b), o "~11×" deixa de ser uma estimativa.** Números medidos em
2026-09-08 sobre velas reais (`docs/DEPLOYMENT.md` §5.2, `.claude/state/notes-T3.19b.md`) e a
aritmética que sai deles, com `REPLAY_CPU_SHARE = 0,33` na VPS de 12 vCPU (3 processos, ~20 ms por
barra projetados, ~72 CPU-h/dia disponíveis para replay):

| Unidade | Barras | CPU-h | Operações simuladas (entrada + desfecho) |
|---|---:|---:|---:|
| 1 versão de 5 min × 200 mercados × 31 dias | 1 785 600 | ~9,9 | ~21 400 (densidade medida 1,2 %) |
| 1 versão de 15 min × 200 mercados × 31 dias | 595 200 | ~3,3 | ~10 700 (densidade medida 1,8 %) |
| **Rodada completa de 5 min (pai + 10 irmãs), 31 dias** | 19 641 600 | **~109** | **~236 000** |
| **Rodada completa de 15 min (pai + 10 irmãs), 31 dias** | 6 547 200 | **~36** | **~118 000** |

Ou seja: **uma rodada de replicação inteira de uma família de 5 min cabe em cerca de um dia e meio
de replay** dentro do orçamento, e entrega em uma tacada mais resultados avaliáveis do que a faixa
viva produziria em meses. A meia-régua do §1.5 (50 resultados × 15 dias por irmã) deixa de ser o
gargalo de **amostra**; o que ela continua exigindo, e o replay **não** entrega, é **dias distintos
de decisão vividos para a frente** — o que é exatamente a distinção do §3.5.

O limite honesto do orçamento: em *operações fechadas por dia* o teto é ~160 mil, não 500 mil. A
meta de meio milhão de validações por dia é atingida com folga se "validação" for **uma decisão
simulada** (barra avaliada: ~10,8 milhões/dia); em operações com desfecho ela exigiria ~3,2 × esta
máquina. A escolha da unidade é do Everton e está registrada aqui para não virar ambiguidade de
relatório.

## 10. Referências

`docs/plans/SHADOW-LAB.md` (§1 congelamento, §3 custos e R líquido, §9 métricas e régua editorial,
§10 isolamento), `docs/DATABASE.md` §16, `docs/RISK_ENGINE.md` §11, `.claude/agents/sexta-feira.md`
(plantão do Shadow Lab, regras 1, 2, 8 e 9), `.claude/state/brief-T3.18-lab-scoreboard.md` (regra do
veredito), `obsidian/11-KNOWLEDGE/` (nomes completos das notas citadas acima pelo código):
`KB-0003-rompimento-de-canal-e-data-snooping`,
`KB-0008-custos-em-perpetuos-e-o-r-que-sobra`,
`KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante`,
`KB-0036-o-tamanho-que-a-sombra-nunca-declara`,
`KB-0037-o-spread-assumido-contra-o-spread-medido`,
`KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker`,
`KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde`,
`KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos`,
`KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente`,
`KB-0069-capacidade-e-impacto-o-teto-que-o-livro-impoe`,
`KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula`.

Implementação: `packages/indicators/hunter_indicators/replication/` (estatística pura),
`services/strategy-worker/hunter_strategy_worker/replication*.py` (derivação e SQL),
`infra/scripts/replicate_strategy_version.py` (CLI auditada).

---
tags: [experimento, hora-do-dia, elegibilidade, populacao, mean-reversion, momentum, pre-registro]
updated: 2026-09-09
status: rascunho
owner: quant-engineer
exp: EXP-0023
strategy: "mean_reversion + momentum"
version: "mean_reversion v12/v13 (de v10) + momentum v12/v13 (de v11) — ainda não derivadas"
result: pendente
evaluable: 0
days: 0
last_eval: "—"
---

# EXP-0023 — "só operar de manhã", testado direito: a janela 12–15 UTC como regra de elegibilidade

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0023** é a
> próxima vaga livre lida em 2026-09-09 (BRT); se outra tarefa tomar o número antes, renumerar.
> Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
>
> **Escrito ANTES de qualquer derivação, ativação ou replay.** Em 2026-09-09 16:20 BRT
> (19:20 UTC) o código da regra está pronto e testado localmente; **nenhuma variante existe,
> nenhuma coorte foi replayada**. Tudo abaixo é desenho e previsão — não medida.

## De onde veio a hipótese (e por que ela ainda não é um achado)

O Everton perguntou, em 2026-09-09 13:25 BRT: *"testar 5 min, 10 min, 1 h ou só no início do dia"*.
A parte "início do dia" tinha uma pista medida na T3.54 §5:

- a **única** hora positiva nas duas coortes de `momentum` é **12:00–12:59 UTC = 09:00 BRT**:
  +0,69 R (n = 6) em `v8` e **+0,70 R (n = 16, soma +11,26 R)** em `v10` — mais do que o prejuízo
  total daquela coorte (−8,99 R);
- em `mean_reversion v10` o balde 12–15 UTC é o **segundo melhor**;
- e a abertura de NY (13:00–14:59 UTC) é **negativa** em tudo que a toca (`session_orb` −0,27 R,
  `momentum v8` −0,22 R, `momentum v10` −0,04 R), assim como a virada do dia (00:00 UTC).

**Isto é melhor-de-24 com n ≤ 16.** Escolher a hora que ganhou e depois "confirmar" que ela ganha é
o erro que este documento existe para não cometer. A T3.53 já tinha registrado que as células de
hora-do-dia não eram julgáveis (1–3 dias de calendário por célula). Então:

> **Hipótese (congelada):** as decisões tomadas em barras que fecham entre 12:00 e 14:59 UTC são
> sistematicamente melhores que as demais decisões da mesma versão, e o efeito é grande o bastante
> para sobreviver a uma reamostragem por **blocos de dia** — não é o produto de um ou dois dias
> bons.

## O limite que decide como ler tudo: o replay de 31 dias é **dentro da amostra**

A janela 12–15 foi escolhida **olhando** as mesmas 31 dias que o replay vai reproduzir. Logo:

- **o replay não pode confirmar a hipótese.** Ele mede de novo, com outro recorte, o mesmo dado que
  a sugeriu; um Δ positivo ali é o esperado por construção e não é evidência nova;
- **o replay pode falsificá-la**, e é para isso que ele serve aqui: se a janela **não** aparecer nem
  no dado que a escolheu — ou se o IC de blocos de dia cruzar zero, mostrando que o "efeito" mora em
  um ou dois dias —, a hipótese morre barata, hoje, sem esperar um mês;
- **a confirmação só existe para a frente**: a coorte prospectiva (`research_only`, faixa viva) a
  partir da ativação. Nenhuma decisão dessa coorte foi vista por ninguém quando a janela foi
  escolhida, e é a única leitura fora da amostra que este experimento pode ter.

Quem ler o resultado sem esta seção vai chamar de "achado" o que é aritmética da seleção.

## Braços (quatro: dois de teste, dois de falsificação)

| braço | versão | pai | portão da filha | parâmetros |
|---|---|---|---|---|
| **H1** | `mean_reversion v12` | `mean_reversion v10` (sem portão) | `hours=12-15` | idênticos ao pai |
| **H2** | `momentum v12` | `momentum v11` (`btc:BTC_BULL,HIGH_VOLATILITY`) | `regime=btc:BTC_BULL,HIGH_VOLATILITY,hours=12-15` | idênticos ao pai |
| **C1** | `mean_reversion v13` | `mean_reversion v10` | `hours=13-16` | idênticos ao pai |
| **C2** | `momentum v13` | `momentum v11` | `regime=btc:BTC_BULL,HIGH_VOLATILITY,hours=13-16` | idênticos ao pai |

Notas que valem estar escritas antes:

1. **A numeração é a que o banco der.** `next_free_version` decide; a T3.52d pediu `v9` e o banco
   deu `v11`. Os nomes acima são intenção, não promessa — o que identifica cada braço é a coorte de
   replay e o `params_hash` + portão.
2. **H2 e C2 mantêm o portão de regime do pai**, nomeado por extenso. Não é opcional: desde a T3.59
   o `derive_variant.py` **recusa** um `--policy` que largue em silêncio uma regra que o pai tem, e
   largá-la faria a filha decidir em *mais* contexto que o pai.
3. **Nenhum parâmetro muda em nenhum braço**: `params_hash` igual ao do pai, de propósito. O que
   difere é `strategy_versions.eligibility_policy` (`0017`, congelada na ativação).
4. **C1/C2 são o controle honesto, não um segundo palpite.** 13–16 UTC é a abertura de NY, medida
   negativa em três coortes na T3.54. Se o critério de sucesso aprovar *também* o controle, o
   critério está medindo o método (o corte de população, a reamostragem) e não a hipótese — e o
   veredito dos quatro braços é `descartar`.

## Não-antecipação (a parte que não precisa de defesa, e o que ela custa)

A regra é `hours_gate` (PIPELINE §4b item 10, T3.59): a hora **UTC** do `source_bar_close`,
meia-aberta, `[12, 15)`. Ela não lê tabela, não lê relógio de parede e não tem série que possa
atrasar — a hora de fechamento é propriedade da barra fechada, e por isso o replay e a faixa viva
dão exatamente o mesmo veredito para a mesma barra (provado em
`services/strategy-worker/tests/test_hours_gate.py`, inclusive avaliando a mesma barra com dois
relógios diferentes).

**O que a janela seleciona é a hora da *decisão*, não a hora de onde o dado veio.** Uma barra de
15 min que fecha às 12:00 resume 11:45–12:00 e é a primeira barra elegível de `12-15`; a entrada
acontece na abertura de 12:01. É deliberadamente o mesmo relógio pelo qual a T3.54 baldeou
(`extract(hour from emitted_at at time zone 'UTC')`), senão a janela pré-registrada mediria uma
coisa diferente da evidência que a sugeriu.

## Previsões registradas antes da corrida (para poderem estar erradas)

1. **População.** `12-15` deixa passar 3 das 24 horas = **12,5 % das barras** do pai. Pelo rateio
   uniforme da coorte de `momentum` (184 decisões em 31 d × 4 mercados) seriam **~23 decisões**; a
   hora 12 sozinha rendeu 16 na coorte de `v10`, então pode ser mais. **H2 é o braço em risco:** ele
   é a *interseção* do portão de regime (que já deixava 30,8 % das barras) com a janela (12,5 %) —
   se as duas forem próximas de independentes, sobram ~3,8 % das barras e a coorte pode não chegar a
   dez decisões. Previsão: **H2 morre no K1**, como `mean_reversion v11` morreu na T3.52d.
2. **Sinal.** H1 e H2 devem sair com Δ **positivo** dentro da amostra — é o que a seleção garante.
   O informativo é o **IC**: com ~20 decisões espalhadas em ~15 dias distintos, a previsão é que o
   IC de blocos de dia **cruze zero** (o Δ de +0,11 R da T3.52d, com n = 98, já cruzava:
   [−0,06; +0,29]).
3. **Controle.** C1/C2 devem sair com Δ ≤ 0. Se saírem positivos e passarem o critério, ver o item 4
   dos braços.
4. **`ineligible`.** A fatia de `hours_gate:HH` deve ser ~87,5 % das barras em H1/C1. Em H2/C2 a
   fatia de `hours_gate` vem **antes** da de `regime_gate` (precedência declarada: a hora é
   avaliada primeiro porque não lê nada), então as duas fatias **não** são comparáveis com as da
   T3.52d — a mesma barra que lá aparecia como `regime_gate:*` aqui pode aparecer como
   `hours_gate:*`.

## Critério de sucesso (pré-registrado; nada aqui se move depois de olhar)

Para um braço de teste (H1, H2) ser considerado **sobrevivente à falsificação dentro da amostra**,
as três coisas ao mesmo tempo:

1. **K1 — população:** `n ≥ 30` decisões terminais em 31 dias. Abaixo disso o braço é
   **inconclusivo**, nunca negativo, e nada mais é lido dele;
2. **efeito:** Δ pareado contra o pai **≥ +0,05 R** por decisão;
3. **estabilidade:** o IC 95 % do Δ por **blocos de dia** (10 000 reamostragens,
   `.claude/state/exp-drafts/t342-blocos/blocos.py`, sem alterar uma linha do estimador)
   **inteiramente acima de zero**.

Qualquer coisa menos que isso é **`descartar`**. E mesmo o sucesso **não** promove nada: um braço
que sobreviva vira coorte prospectiva `research_only` e a leitura que vale é a de fora da amostra,
com a sua própria porta de K1, semanas depois. Nenhum braço deste EXP toca carteira.

**Cláusula de falsificação:** se C1 ou C2 passar os três itens, o resultado do experimento é
`descartar` para **todos** os braços e a próxima tarefa é o estimador, não a estratégia.

## Como parear (a lição da T3.52d, e ela é a base do desenho)

**Por (mercado, barra), sobre as barras elegíveis compartilhadas — nunca por decisão.** A filha
**não** é subconjunto das decisões do pai: `INELIGIBLE` não re-arma o slot nem gasta a barreira, a
máquina de estados da filha evolui diferente, e na T3.52d o `momentum` com portão tomou **3
decisões que o pai nunca tomou** (PIPELINE §4b item 11, notas T3.52d §4.2). O SQL de referência é
`infra/scripts/sql/research/2026-09-09-t352d-q11-pareado.sql`.

**K4 não é mensurável em braço com portão** (PIPELINE §4b item 12): o portão avalia antes da
checagem de contexto, então `unavailable` vira `ineligible` e o braço mede K4 ≈ 0 por construção.
A leitura honesta de K4 é a **do pai**, na mesma janela.

## Passos (nenhum executado)

1. commit + deploy do código da T3.59 (a imagem precisa conter `hunter_strategy_worker.hours_gate`
   e `.gate_policy`; a `0017` já está aplicada na VPS desde a T3.52d);
2. `derive_variant.py … --dry-run` para os quatro braços, depois sem `--dry-run`;
3. `activate_strategy_version.py` (a rota derivada; `purpose` continua `research_only`);
4. replay 31 d × 4 mercados por braço, coorte própria, com `--explain-ledger`;
5. pareamento por (mercado, barra) contra o pai; blocos de dia; estresse **só** se o K1 sobreviver;
6. veredito por braço e ≤ 10 linhas em português para o Everton.

## Registro de conferência (preencher depois da corrida, append-only)

| data | braço | n | Δ R pareado | IC 95 % (blocos de dia) | veredito |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

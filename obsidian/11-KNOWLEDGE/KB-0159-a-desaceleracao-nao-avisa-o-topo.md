---
tags: [knowledge, meme, mesa-real, entrada, fluxo, recuo, hipotese, metodo, m4]
tema: o ritmo de compra dos últimos 10 s contra o minuto não separa a compra no topo (H-019 refuta pela cláusula das vencedoras, e o sinal saiu ao contrário); o braço do recuo ainda não pode ser julgado porque a sombra do operator/5 só nasce quando a mesa real aceita, e o papel não mede o preço da entrada quando o gatilho vem antes da foto seguinte
fonte: R79 (`.claude/state/notes-R79.md`) — H-019 e H-017 da Fila de Hipóteses
fonte_url:
lido_em: 2026-09-25
evidencia: medição própria — H-019: 195 decisões da pista de eventos (24–25/09/2026, uma por mint, 50 reais e 145 de papel) com a fita gravada no instante da decisão (`meme_decision_tapes`), tercis de posto, bootstrap por mint 10 000, permutação por dia, Holm, moinho `run_hypothesis`; H-017: 171 armações do `recuo_v1/1`, 39 emparelhadas com a sombra de `operator/5`; 11 testes sintéticos
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-25
confiança: "?"
tipo: pesquisa
hipotese: H-019
variavel: aceleracao_compra (ritmo de compra em 10s / ritmo em 60s, na hora da decisao)
populacao: 195 decisoes da pista de eventos com fita completa (24-25/09, 50 reais + 145 papel)
efeito: D (baixo-alto) = +0,037 por SOL; sinal ao contrario da tese (desacelerar rendeu mais)
ic: [-0,109, +0,183]
veredito: refuta
proximo_passo: piso no tercil baixo mataria 34,7% das vencedoras (>30% da clausula); nenhum braco de papel
classe_de_perda: comprou_no_topo
mercado: meme
---

# KB-0159 — A desaceleração do minuto não avisa o topo; o recuo ainda não tem controle

> **H-019 (fluxo desacelerando na hora da compra): `REFUTA` pela cláusula (c).** O piso no tercil baixo mata
> 34,7 % das vencedoras (limite: 30 %). Além disso, o efeito saiu **ao contrário** da tese.
> **H-017 (recuo pequeno como melhora de preço): `LIMITE DE DADO`.** Há 39 decisões emparelhadas e o bloco pede
> 150. Não foi julgada.
> Estudo em `.claude/state/notes-R79.md` · código e saídas em `.claude/state/r79/` · pré-registos em
> [[Fila de Hipoteses]] § H-019 e § H-017 · protocolo em [[EXP-M24-entrada-no-recuo]].

## O que afirma

1. **A forma do minuto não mostra o topo (H-019).** A tese dizia que, quando a porta aprova, o ritmo de compra
   dos últimos 10 s já está a cair em relação ao minuto, e que por isso a compra é no topo local
   (`comprou_no_topo`, o maior vazamento da ficha T4.92).
   - Medido na fita da decisão, o tercil que **desacelera** rendeu **mais**, não menos: −1,0 % contra −4,7 % por SOL.
   - A classe `comprou_no_topo` não se concentra nele: 35 % contra 40 %.
   - Um piso na mesa real teria bloqueado mais ganho do que perda.
2. **O braço do recuo mede menos do que parecia (H-017).**
   - A sombra de papel do `operator/5` só existe quando a **mesa real aceita** a proposta. Das 171 armações, só 39
     têm controle.
   - Em 22 dos 34 pares que entraram, o papel **comprou na mesma foto** para os dois braços. A diferença de preço
     que a H-017 quer medir fica a zero por construção.

## Onde foi mostrado

### H-019: pista `meme_event_gate_v1`, porta `fluxo_e_holders/*`, 24–25/09/2026

**Variável.** `aceleracao_compra = 6 · buy_sol(10 s) ÷ buy_sol(60 s)`, lida de `meme_decision_tapes.derived.windows`
no instante da decisão.
- Junção por `t.mint = p.mint AND t.as_of = p.features_end_time` (`docs/RESEARCH.md`, regra 6).
- Guardas: 0 trocas da fatia recebidas depois do `as_of` e 0 fitas depois da aprovação. O moinho não recusou
  nenhuma linha.

**População.** Uma decisão por mint, a primeira no tempo: **195 resolvidas** (a cláusula de dado não dispara).
São 50 reais e 145 de papel, das quais 86 do `recuo_v1`.

| linha | n | média r baixo / alto | D (baixo − alto) [IC 95 %] | vencedoras no baixo | `comprou_no_topo` baixo → alto |
|---|---|---|---|---|---|
| **primária (SOL)** | 195 | −0,010 / −0,047 | **+0,037 [−0,109, +0,183]**, p 0,62 | **34,7 %** | 35,4 % → 40,0 % (0,88×) |
| contagem de compras | 195 | −0,043 / −0,047 | +0,004 [−0,142, +0,144], p 0,95 | 30,6 % | 1,04× |
| sem `recuo_v1` | 114 | −0,059 / −0,101 | +0,042 [−0,139, +0,227] | 30,3 % | 0,81× |
| só reais | 50 | +0,006 / −0,072 | +0,078 [−0,054, +0,227] | 26,3 % | 0,57× |
| 24/09 | 100 | | +0,099 [−0,114, +0,323] | 39,5 % | 0,97× |
| 25/09 | 95 | | −0,021 [−0,153, +0,107] | 29,4 % | 0,92× |

- Holm na família {SOL, contagem}: 1,0 e 1,0.
- A curva de cortes vizinhos (q de 0,20 a 0,50) fica toda entre +0,001 e +0,073. **Nenhum corte** vai no sentido
  previsto.
- O moinho, com o enquadramento "piso", dá `NÃO CONFIRMA`: D −0,028 [−0,149, +0,086], com forma de **pico**.

**Contrafactual na mesa real.** Piso em `aceleracao_compra > 0,548` sobre 60 posições reais com fita completa:
- bloqueia 20 posições: perdas evitadas −0,084 SOL e ganhos mortos +0,091 SOL, logo **Δ −0,007 SOL**;
- mata **6 de 21 vencedoras**: SMITH, CALLS, Relaunch, PREDICTED, MEMEos e $LAG.

### H-017: braço `recuo_v1/1` contra a sombra de `operator/5`, 24/09 05:46Z → 25/09 23:06Z

**Armações.** Foram 171: 141 entraram, 16 morreram na rechecagem, 9 não recuaram e 5 foram censuradas.
- **Controle** (aposta de papel do op5 na mesma `(mint, t0)`): existe em **39**.
- As outras 122 foram recusadas pela mesa real (`auto_stage1`): `creator_flow_unknown` 38, `below_min_sol` 29,
  `participation_above_cap` 16, `creator_net_seller` 14, `bundled_share_above_cap` 11, entre outras. Há ainda 9
  expiradas.

| | n | braço | op5 | D braço − op5 [IC 95 %] |
|---|---|---|---|---|
| **pares (primária)** | **39** | −0,022 | −0,055 | **+0,032 [−0,006, +0,082]** |
| pares sem o Megawatt | 38 | | | +0,014 [−0,013, +0,042] |
| 24/09 | 10 | −0,011 | −0,086 | +0,076 |
| 25/09 | 29 | −0,026 | −0,044 | +0,018 |
| braço contra "nada", nos pares | 39 | −0,022 [−0,085, +0,045] | | |
| braço contra "nada", todas as resolvidas (descritivo) | 166 | +0,006 [−0,039, +0,051] | | |

**De onde vem o D de +0,032:**
- 22 pares compraram na **mesma foto** e contribuem 0;
- 12 compraram numa foto posterior: +0,013;
- as 5 não-entradas contam 0 contra uma perda do op5: +0,020.

**O "25/09 negativo" era contagem.** Os 24 pares **só com entradas** davam recuo −0,053 contra op5 −0,034 SOL. O
protocolo conta `no_pullback` e `pullback_killed` como 0. As 5 não-entradas desse dia eram todas perdas do op5, e com
elas o dia fica positivo.

## O que se aprendeu

1. **A ficha chama "comprou no topo" a um resultado, não a um estado observável na compra.** O ritmo dos últimos
   10 s contra o minuto não o antecipa. Vale o mesmo para o minuto inteiro (`buys_1m`, R65/R67, [[KB-0149-o-que-a-mesa-real-ensinou]]
   §3) e para o recuo (H-016, [[KB-0157-esperar-o-recuo-nao-paga]]). É a terceira leitura da entrada que não separa
   as vencedoras.
2. **Um tercil tem um terço das vencedoras por construção.** A cláusula (c) só passa se o tercil bloqueado ganhar
   visivelmente menos vezes que a média, e aqui ele ganhou **mais** (38,5 % contra 32,3 % no alto). O mesmo desenho
   derrubou a H-015 ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]).
3. **O controle de um braço de papel não pode depender da mesa real aceitar.**
   - A sombra do `operator/5` nasce do `filled`. A mesa real pausada, sem saldo (`below_min_sol`) ou a recusar
     por risco leva o controle a zero.
   - O braço `research_only` não passa pelos checks da mesa e opera **também** as decisões que ela recusou (127 de
     166 resolvidas). O "+2,61 %/entrada" do diário de 25/09 vem sobretudo delas: nessas 127, +0,014; nas 39 que a
     mesa aceitou, −0,022.
4. **O papel preenche na foto seguinte, não no gatilho.**
   - A sombra do op5 entrou 0,8 a 16 s depois de `t0` (mediana 9,6 s, a foto seguinte), e o gatilho do recuo veio em mediana 5,5 s depois de `t0`.
   - Em 22 de 34 pares, os dois compraram no mesmo ponto. O efeito de preço (+2 pp) que a H-017 quer medir só é
     visível em 12 pares, e na real, que pousa em cerca de 1 s.
   - Em 59 de 141 gatilhos, o preço estava **acima** do de `t0`: subiu e recuou 3 % da nova máxima.
5. **Papel × real no mesmo op5 (n = 38): real − papel = +0,002 [−0,087, +0,086].** Nesta coorte, o motor de papel
   não foi otimista em média. Os ~6 pp do R77 eram do simulador do R77 (aluguel de ATA e saídas históricas); o
   intervalo daqui é largo demais para os descartar.

## Como mediríamos aqui

A H-019 já está medida; o código fica em `.claude/state/r79/`. Para a H-017 poder ser julgada, **nada foi
implementado nem ativado**. O que seria preciso (decisão do coordenador e do Everton, EXP nova ou emenda
declarada, porque o protocolo do EXP-M24 está congelado):
- **Controle que não dependa da mesa real:** um braço `research_only` de entrada imediata com os `params` do
  `recuo_v1/1` menos a célula (`entry_pullback_pct` nulo). Com ele, cada armação teria par. Ao ritmo de 171
  armações em 41 h, as 150 chegam em cerca de 1,5 dia.
- **Preço de entrada medido no gatilho:** comparar `trigger_price` contra o preço de pouso de `t0` na fita, ou
  preencher o papel pelo preço da troca, em vez da foto seguinte.
- **Guardar a trilha antes da poda de 7 d.** `no_pullback` e `pullback_killed` só existem em
  `meme_gate_refusals_by_mint`. A coorte de 24/09 some por volta de 01/10; `r79/cache/h017.csv` guarda 24 e 25/09.

Ao ritmo atual de pares com a sombra do op5 (~29 por dia), o julgamento formal pela regra congelada chega por
volta de **29–30/09**, e **só com a mesa real ligada e a aceitar**.

## Hipótese testável no Lab

**Nenhum braço de papel novo é proposto pela H-019**, porque refutou. A H-017 continua em curso. As propostas de
medição acima não mudam a regra do braço.

## Por que pode falhar (limites desta nota)

- **Dois dias.** A coorte vai de 24 a 25/09. O dia 24/09 e o dia 25/09 dão sinais opostos na H-019 (D +0,099 e
  −0,021), ambos com IC largo.
- **Papel e real juntos na H-019** (145 + 50). O braço do recuo entra depois de `t0` com a variável de `t0`. A
  sensibilidade sem ele não muda o rótulo.
- **A janela de 10 s é por `block_time` contra o relógio da decisão.** Trocas dos últimos ~1 s ainda não recebidas
  ficam de fora e puxam a aceleração para baixo de 1. Isso muda o nível, não a ordem.
- **H-017 com 39 pares:** um único par (Megawatt, `creator_dump` −81 % no op5 contra −6 % no braço) vale 1,9 pp do D.

## Segunda opinião (Astra)

**Astra indisponível** no desenho e no veredito: o `codex` devolveu `401 Unauthorized` (credencial rejeitada) em
25/09/2026, por volta de 23:20Z e de 23:50Z. No lugar dela foi feita uma revisão adversária própria, registada em
`notes-R79.md` §5:
- a decomposição de D fecha ao dígito;
- o número do brief foi reproduzido;
- a junção do controle cobre 170 de 171 armações.

A revisão da Astra fica **pendente**, a pedir quando a credencial voltar.

## Relacionados

[[Fila de Hipoteses]] (H-019, H-017) · [[EXP-M24-entrada-no-recuo]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[KB-0157-esperar-o-recuo-nao-paga]] · [[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]] · [[Strategy Backlog]]

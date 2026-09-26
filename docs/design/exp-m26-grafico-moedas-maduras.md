# EXP-M26 — estratégia de gráfico em moedas maduras (desenho)

> **Estado:** desenho, 26/09/2026. **Nada implementado, nada ativado, nenhum desfecho lido.**
>
> - **Dados:** só contagens cegas na VPS, SELECT em transação `default_transaction_read_only=on`. As consultas e as
>   saídas coladas estão em `.claude/state/m26/` (`q*.sql`, `outputs.txt`).
> - **Autor:** quant-engineer, com cinco rodadas de diálogo com a Astra (§8).
> - **H-022:** está escrita aqui (§3), **não** na fila. Quem a registra é o orquestrador.

## 0. Por que este experimento existe (leitura da base primeiro)

- **[[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]] / `.claude/state/notes-R81.md`:** a H-021 parou por
  limite de dado **estrutural**.
  - Todas as portas vivas compram moedas de 1–4 min (`max_age_s = 300`; mediana 1,6 min, máx. 315 s). Só 1 de 885
    decisões tinha 5 min de fita.
  - A linha de produção (`hunter_indicators/meme/lines.py`, reta pelos dois últimos mínimos locais de 15 min de
    fotos da curva) existia em 67 de 623 decisões, e nenhuma chega ao portão das pistas de 15 s e de eventos.
  - **Só a via de 1 min (`lab_repo.py:64-88`) lê o bloco `line`.**
- **[[KB-0149-o-que-a-mesa-real-ensinou]] §7:** "se existe vantagem em qualquer horizonte maior que 5 minutos (nunca
  medimos; a mesa nasceu com 300 s)".
- **[[Perdas/comprou_no_topo]]:** é o maior vazamento (20 casos, −0,2642 SOL em 24–25/09). H-016, H-017, H-019 e
  H-021 não separaram a classe antes da compra.
- **[[Mapa de Estrategias]]:** cinco estudos de entrada em moeda nova fecharam sem vantagem.
  - Os cinco: R65/R67, H-016, H-019, H-020, H-021.
  - A regra 1 da casa proíbe girar as 13 variáveis esgotadas. **Idade** é uma delas, mas aqui ela **define a
    população nova** e não é a variável testada ([[Fila de Hipoteses]], regra 1).
- **[[Dicionario de Variaveis]] l. 63:** `higher_lows`, `breakout_15m` e `distance_to_support_pct` nunca foram
  isolados.
- **[[KB-0148-a-graduacao-nao-e-a-saida-barata]] e [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]]:** os
  custos (§5).

A ideia: parar de procurar o gráfico onde ele não existe e testar moedas que **já têm gráfico**, com 15–120 min de
vida e ainda na curva.
- Entradas: estrutura de preço (fundos mais altos, rompimento da máxima de 15 min, distância do suporte).
- Saídas: a mesma da mesa, e um pacote de saída mais longo à parte.

## 1. O dado existe hoje? (medido)

### 1.1 O rastreador larga a moeda aos ~13 minutos

- **Configuração.** `MEME_TRACKED_MINTS_MAX = 300` no container `hunter-meme-worker-1` (lido com `printenv` de uma
  variável). O padrão do código é 120 (`config.py:303`) e a janela é de 1 440 min.
- **Poda.** `MintTracker.prune` (`tracker.py`) corta o excedente **pelas mais novas**: `snapshot()` ordena por
  `age_anchor` decrescente. Com ~22–31 moedas novas por minuto, uma moeda sai do conjunto em minutos, viva ou não.
- **Só não sai quem está fixado.**
  - Fixa: aposta de papel aberta, posição real aberta, proposta `proposed` à espera (`tracker_pins.py:52-58`).
  - Não fixa: proposta `approved`, nem apostas dos braços de recuo.
- **Série de 15 s.** `fast_lane.py` só cobre moedas com < 300 s, e as fixadas até 1 800 s
  (`MEME_FAST_LANE_PINNED_MAX_AGE_S`).
- **Consequência:** sem fotos da curva não há `meme_features_1m`, e sem essa série não há linha.

**Coorte de 24/09 (criadas 00:00–24:00Z, 36 h de seguimento; `q3.sql`):**

| medida | valor |
|---|---:|
| moedas criadas | 32 287 |
| com alguma linha de 1 min | 32 144 |
| idade da **última** linha de 1 min (p10 / p50 / p90 / p99) | 8,7 / **13,0** / 21,0 / 29,4 min |
| com linha na idade 14–16 min | 13 487 |
| … e com ≥ 1 compra nesse minuto ("viva aos 15 min") | **520** (3,9 %) |
| viva aos 15 min **e** ainda com linha aos ≥ 30 / ≥ 60 / ≥ 120 min | 73 / 38 / 26 |

Os 73 que passam dos 30 min são quase todos fixados (apostas ou propostas das portas de 1–4 min). **Não existe hoje
uma população não selecionada de moedas maduras com série.**

### 1.2 Cobertura por idade, últimas 72 h (`q2.sql`, `meme_features_v3`)

| idade | linhas | mints | com mcap | linha traçada | `flat` | `too_few_points` | `no_snapshot` | fita | pontos p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| < 5 min | 512 736 | 104 272 | 0,959 | 0,074 | 0,741 | 0,190 | 0,044 | 0,937 | 11 |
| 5–15 | 738 777 | 100 068 | 0,948 | 0,119 | 0,872 | 0,000 | 0,060 | 0,969 | 27 |
| 15–30 | 111 688 | 25 147 | 0,942 | 0,066 | 0,909 | 0,001 | 0,062 | 0,973 | 23 |
| 30–60 | 3 428 | 399 | 0,762 | 0,426 | 0,422 | 0,150 | 0,414 | 0,871 | 12 |
| 60–120 | 3 513 | 173 | 0,786 | 0,424 | 0,506 | 0,121 | 0,371 | 0,944 | 12 |
| 120–240 | 4 375 | 127 | 0,757 | 0,349 | 0,533 | 0,093 | 0,374 | 0,964 | 11 |

- **`flat` = não há dois mínimos locais estritos na janela.** Isso cobre a moeda morta (preço parado, a maioria) e
  também a série monótona viva, que sobe sem recuo. `flat` não é sinónimo de morta.
- **Acima de 30 min sobram poucas centenas de mints em 3 dias:** as fixadas pelas portas de 1–4 min, amostra
  enviesada pela seleção das nossas próprias portas.

### 1.3 Onde a moeda está ativa, a linha costuma existir (23–25/09, `q9.sql`, só na curva; ativa = `buys_1m ≥ 3`)

| idade | minutos ativos | mints ativos | linha traçada | `higher_lows` | `breakout_15m` | minutos com fundos ∧ rompimento | mints com fundos ∧ rompimento ∧ banda 0–0,25 | distância p25/p50/p75 | volume 1 min p50 / p90 (SOL) | criador desconhecido |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---:|
| 10–15 | 5 445 | 2 153 | 0,681 | 0,611 | 0,209 | 607 (11,1 %) | 166 | −0,14 / 0,09 / 0,51 | 8,3 / 41 | 0,556 |
| 15–20 | 1 868 | 673 | 0,712 | 0,651 | 0,226 | 239 (12,8 %) | 66 | −0,09 / 0,08 / 0,39 | 10,2 / 44 | 0,306 |
| 20–30 | 1 519 | 368 | 0,623 | 0,673 | 0,256 | 184 (12,1 %) | 62 | −0,03 / 0,08 / 0,29 | 9,8 / 37 | 0,098 |
| 30–120 | 3 612 | 238 | 0,496 | 0,599 | 0,264 | 309 (8,6 %) | 68 | −0,02 / 0,04 / 0,18 | 5,4 / 27 | 0,012 |

Estes números são de moedas que **sobreviveram ao rastreador**, que as poda pela idade. A linha 30–120 é quase só de
moedas fixadas, por isso descrevem o instrumento e não a população futura.
- Vi só distribuições, nenhum desfecho.
- A banda 0–0,25 **não foi mexida** (§2).

### 1.4 Por que EXP-M2 (`trendline_v0/1`) morreu com 0 propostas (reconstrução, `q6.sql`/`q8.sql`/`q11.sql`)

Conjunto ativo de 12/09 15:03Z a 20/09 01:24Z; porta `a_linha_manda` v1, idade 300–600 s. Funil **sequencial** sobre
`meme_features_1m`. `curve_progress_pct` é **fração**; o portão multiplica por 100 em `proposals.py:116`.

| passo | minutos (linhas) |
|---|---:|
| todas as linhas do período | 1 513 826 |
| idade 300–600 s | 347 344 |
| + progresso 2–50 % | 68 946 |
| + linha traçada | 18 305 |
| + `higher_lows` | 11 059 |
| + `breakout_15m` | 1 136 |
| + distância 0–0,25 | **287** (209 mints) |
| + `creator_net_seller = false` | **8** |
| + volume 1 min ≥ 5 SOL (participação ≤ 1 % com 0,05 SOL) | **1** |

**O que o funil sustenta:** a linha **nunca foi julgada por desfecho**.
- Dos 287 minutos que passaram a linha, **275 tinham o criador desconhecido**: 241 `no_trade_feed`, porque a fita
  era a agregada (`activity_1m`) e não sabe quem é o criador, e 34 `not_polled`.
- O critério recusou por instrumento, não por mercado.
- Dos 12 com criador conhecido, 4 eram vendedores líquidos. Dos 8 não vendedores, a participação eliminou 7.

**O que ele não sustenta (Astra, rodada 1):**
- A ordem causal. Os filtros são correlacionados e a decomposição depende da ordem escolhida. "Janela curta" é uma
  explicação plausível da escassez, não uma causa isolada.
- O **único sobrevivente** do funil (`3EsVoo…pump`, 13/09 01:39Z, 336 s, progresso 44,7 %, volume 83,6 SOL, criador
  `false`, não Mayhem) **não virou proposta**, e a recusa não é recuperável: `meme_gate_refusals_by_mint` só começa em
  19/09 15:06Z.
  - O portão e a camada de propostas têm mais filtros: pedigree, snapshot da cotação, Mayhem (`rules.py:295`,
    `proposals.py:239-270`).
  - **Por isso o funil de pré-seed da §4 precisa ir até a proposta e o fill.**

### 1.5 A população madura existe no mercado (boards do site, 25/09, `q4b.sql`)

Mints **distintos** nos boards do pump.fun (60 s) com pelo menos uma observação na curva (`graduated_at IS NULL`),
por idade. A `q4.sql` original multiplicava uma média por observação por uma contagem de mints e errava; foi
corrigida a pedido da Astra.

- `movers`: 221 mints na curva com 15–30 min (de 374), 68 com 30–60 min (de 178) e 38 com 60–120 min (de 106).
- `graduating` (progresso ~84–86 %): 129 com 15–30 min, 65 com 30–60 min e 47 com 60–120 min.
- **União dos dois boards, 15–120 min, na curva: 292 mints distintos no dia.**

**Ordem de grandeza:** ~300 moedas maduras por dia ainda na curva e com atividade visível no site. A ordenação dos
boards é opaca (KB-0148), e eles servem só para dimensionar. Quem mede a população prospectiva é o funil F (§4).

**Depois dos 30 min, o que ainda se mexe já graduou quase todo.** A janela útil concentra-se em 15–60 min.

### 1.6 O que falta e a menor instrumentação que resolve

**Falta:** manter no conjunto rastreado as moedas que passaram dos ~10 min e ainda estão na curva, para que o laço
da cadeia continue a fotografá-las e a série de 1 min continue a dobrar a linha. Isto tem de valer também para as
moedas sem aposta fixada. E fazê-lo **sem tirar lugar às moedas jovens** e **sem que os próprios braços mudem a
série de onde a variável é lida**.

**I1 — retenção madura limitada (código, `MEME_TRACK_MATURE_TOP_K`, padrão 0 = desligado; K = 60 no experimento)**

- **Elegíveis.** Mints rastreados e não fixados com:
  - `created_at` conhecido e idade em [5 min, 120 min];
  - não terminados, cotados em SOL, sem agente Mayhem ativo;
  - `mcap_sol` lido há ≤ 120 s.
  - Hoje o rastreador guarda `mcap_sol` sem o instante em que o recebeu (`tracker_types.py`). I1 acrescenta
    `mcap_observed_at`, e sem ele a moeda não é elegível.
- **Seleção.** As K maiores por `mcap_sol`, desempate por mint. É causal: usa só o que já chegou no instante do
  `prune`. O teste prova que uma leitura recebida depois não muda a escolha.
- **Orçamento à parte, também depois da aposta (Astra, rodada 2).** O teto das jovens passa a ser
  `cap − |fixadas ordinárias|`, isto é, as fixadas por qualquer coisa que **não** seja o EXP-M26 (aposta de outro
  conjunto, posição real, proposta de outro conjunto).
  - As retidas e as **fixadas só pelo EXP-M26** (propostas `approved` sem aposta, apostas abertas, reentradas)
    formam um conjunto à parte. Um mint que esteja nos dois conta como ordinário, uma vez só.
  - **Cenário de falha sem isto:** 10 apostas do EXP-M26 abertas viram 10 pins e o espaço das jovens cai de 300 para
    290.
  - O teste integrado percorre retenção → `approved` → fill → fecho → reinício e prova que o teto das jovens não se
    mexe.
  - O conjunto pode ir a 300 + 60 + as fixadas do EXP-M26 (esperado ≤ 5, §abaixo).
  - Custo, no teto:
    - `meme_features_1m`: ≤ 86 400 linhas/dia, **+18,5 %** das 466 208/dia de hoje (≈ 50 MB/dia a 573 B/linha,
      KB-0113);
    - `meme_curve_snapshots`: ≤ 86 400/dia, **+7,9 %** de 1,09 M;
    - RPC: +1 `getMultipleAccounts`/min (100 mints por chamada);
    - REST: a retenção não cria pedidos novos (`needs_rest` só pede o mint nunca lido por REST, Mayhem ou aposta
      aberta).
  - **Mas as apostas abertas do EXP-M26 recebem a prioridade de aposta aberta.**
    - REST: `collect.py:184`. Fita: `wiring.py:223`, com `max_pages` em `trades.py:300`, dentro dos 16 pedidos/60 s
      do swap-api.
    - Concorrência esperada: ≈ entradas/dia × posse / 1 440, isto é C ~300 × 5 min ≈ 1, e L+H ~40 × (5 + 15) min
      ≈ 0,6. Dá **~1–3 apostas abertas** ao mesmo tempo.
    - O pior caso é 75 (3 × 25), e a guarda 8 da §6 vigia isso em janelas de 15 min, porque um p95 horário esconde
      rajadas.
    - A ação da guarda está congelada na §6.8. `K = 0` sozinho não pára propostas de moedas que continuam fixadas,
      porque a porta não consulta K (`proposals.py:265`).
- **Por que o maior `mcap_sol`.** É o único sinal que o rastreador já tem (`top_by_mcap` existe), e põe à frente as
  moedas que subiram desde o lançamento (~28 SOL).
  - Viés declarado: uma moeda que subiu e está a morrer ocupa a vaga de uma nova ativa de mcap menor.
  - A população do experimento chama-se "**mints descobertos e retidos por esta política**", não "todas as moedas
    maduras". Uma moeda podada antes dos 5 min não volta.
- **Reinício.** `warmup.py` aplica a mesma elegibilidade do `prune` sobre a última foto de cada mint.
  - A foto tem de cumprir `now − 120 s ≤ observed_at ≤ now` e `received_at ≤ now`.
  - Recarregar não repõe as fotos perdidas durante a parada. Os eventos de reinício (`system_events`) entram no
    relatório.
- **Guarda de cobertura (análise, sem mudar `lines.py` v1).** A fórmula lê duas janelas: a atual `(T − 15 min, T]`
  e a do rompimento `(T − 16 min, T − 1 min]`, cada uma com as fotos recebidas até T.
  - Uma decisão está **coberta** se, na união das duas janelas, a 1.ª foto recebida está a ≤ 150 s do início
    (T − 16 min) e a última a ≤ 150 s de T.
  - Além disso, nenhum intervalo entre fotos consecutivas pode passar de 150 s (2,5× a cadência da cadeia, regra do
    KB-0148).
  - **Moeda com < 16 min:** o início efetivo é o `created_at`, e a janela é declarada **truncada no nascimento**, não
    completa. Isso é contado à parte: aos 15–16 min, toda a porta de C cai aqui.
  - Sem cobertura, a decisão é linha **desconhecida** por motivo `lacuna` (§2.2).
  - **Cenário que esta guarda pega:** 5 fotos nos últimos 4 min passam o `MIN_POINTS`, mas 11 min não foram
    observados. Ou falta a máxima de T − 16 min e aparece um rompimento falso.
- **Heartbeat:** `tracked_mature_kept`, `tracked_mature_ranked_out_60s`, `tracked_mature_stale_mcap`.
- `tracker.py` tem 346 linhas: a regra pura vai num módulo novo (`tracker_mature.py`), e `prune` só a chama.

**I2 — acompanhar a posição do EXP-M26 até ao fecho (código pequeno, sem mudar a variável de configuração global)**

- **Fixar o que ainda não é fixado.** As propostas `approved` do EXP-M26 ainda sem aposta passam a ser fixadas, como
  as `proposed`.
  - **Cenário de falha sem isto:** a proposta de pesquisa nasce aprovada (`proposals.py:314`), a moeda sai do top-K
    antes da foto de fill e o fill nunca acontece.
  - **Prazo terminal:** o pin da `approved` sem aposta cai quando a proposta sai de `approved` (aposta, recusa,
    expiração) ou 180 s depois de `decided_at`, o que vier primeiro. O teste integrado cobre o ramo da recusa e o do
    reinício.
  - Custo de I2: ~1–3 apostas abertas × 4 fotos/min ≈ ≤ 12 fotos/min extra, dentro de uma chamada
    `getMultipleAccounts` da série de 15 s. As linhas de `meme_features_15s` destes mints são contadas no heartbeat.
- **Marcas a 15 s até ao fecho.** As apostas abertas do EXP-M26 entram na série de 15 s até fecharem, **pela
  pertença** (`exp_ref = 'EXP-M26'`) e não pela idade.
  - Motivo: com 60 s, 1,15× / trailing 10 % / 300 s seriam julgados em ≤ 5 fotos (KB-0148: foto de 60 s não é barra
    OHLC).
- **Por que não subir `MEME_FAST_LANE_PINNED_MAX_AGE_S` para todos.**
  - `flow_v2/1`, `/9` e `/10` estão ativos com `max_hold_s 1 800` e idade ≤ 300 s: as apostas deles chegam a 2 100 s
    ou mais. Um teto global maior mudaria a cadência das marcas desses braços a meio da coleta.
  - Um teto fixo (8 100 s) também não cobre o ciclo: idade no fim do minuto + atraso da decisão + fill + 900 s de
    posse + foto de venda.
- **Contaminação declarada.** A série de 15 s de uma aposta aberta acrescenta fotos, e as linhas usam todas as fotos
  utilizáveis (`lines.py:195`). Depois da 1.ª entrada de um braço numa moeda, as linhas seguintes dessa moeda já não
  são a série da política. Por isso a primária da H-022 lê a linha **antes** de qualquer entrada do EXP-M26 (§2.2).

**L1 — causalidade da saída `line_broken` (código pequeno)**

- **O defeito.** `support_lines_for` filtra por `end_time ≤ now` e `support_at` por `end_time ≤ observed_at`
  (`lab_repo_lines.py:40`, `lines_exit.py:37`). Nenhum dos dois olha `computed_at`, e o laço reprocessa fotos
  antigas (`lab_bets.py:220`).
- **Cenário de falha.** A linha do minuto T foi calculada em T + 5 s e é usada para julgar a foto de T + 3 s.
- **A exposição medida é pequena:** atraso do fold p50 3,0 s, p90 4,8 s, p99 5,3 s (`q10.sql`).
- **Mas nos braços maduros a saída passa a disparar de verdade.** O p99 medido não é limite máximo: um fold lento
  ou um reinício alarga o atraso.
- **Frescor do suporte (Astra, rodada 2).** `_SUPPORT_LINES` descarta linhas nulas e `support_at` projeta a última
  válida **sem limite de idade**.
  - **Cenário:** a linha atual está `flat`, mas a reta de 20 min atrás continua projetada e dispara `line_broken`.
- **Correção**, por parâmetros novos dos três conjuntos do EXP-M26, para não mudar a saída dos conjuntos vivos:
  - `line_support_causal: true`: `SupportLine` carrega `computed_at`, e `support_at` exige `computed_at ≤ at`.
  - `line_support_max_age_s: 120`: o suporte é o do **minuto mais novo dobrado até `at`**.
    - Se esse minuto não tem suporte (`flat`, nulo) ou tem `end_time < at − 120 s`, o suporte é **ausente**, com o
      nome `support_stale`, e `line_broken` não dispara.
    - Uma linha válida mais antiga nunca é usada por cima de um minuto `flat` mais novo.
  - O teste atrasado vai até ao laço: gatilho **e** foto de venda, não só `support_at`.
- **Recomendação à parte, fora deste experimento:** a mesma falta de `computed_at` existe na saída de todos os
  conjuntos com `exit_on_line_break`, incluindo a mesa. Corrigir globalmente é decisão do orquestrador, com revisão
  do risk-engine-guardian.

**R1 — registro durável das oportunidades (código + migração; Astra, rodada 3)**

- **Por que.** A 1.ª oportunidade não se reconstrói depois com fidelidade:
  - a via de 1 min grava propostas e contadores agregados, não a avaliação individual (`lab.py:241-267`);
  - a trilha de recusas é amostrada: só 0 ou 1 recusa entra (`gate_refusal_trail.py:66`);
  - a trilha é podada em 7 dias (`config_trail.py:26`);
  - o Mayhem vem do estado corrente de `meme_tokens` (`lab_repo_mayhem.py:40`);
  - `entry_features_of` testa `completed_at`/`migrated_at` pela presença, não pelo minuto (`proposals.py:133`).
  - **Cenário de falha sem isto:** C passa os critérios puros e cai em `creator_serial` e `symbol_clone`; sem trilha
    individual a leitura chama-o `sem_proposta` por instrumento. Ou uma reconstrução com o token já migrado exclui
    uma oportunidade que era válida.
- **O quê.** Uma tabela só de acréscimo, `meme_mature_opportunities`, com revisão do database-architect e RLS/papel
  como as irmãs.
  - Uma linha por (conjunto do EXP-M26, mint), escrita pelo laço de 1 min na **1.ª avaliação** em que a porta
    **pura** do conjunto deixa passar o mint.
  - Colunas:
    - `evaluated_at` (o tique do Lab: **o relógio único**), `features_end_time`, `features_version`, `code_ref`
      (commit);
    - os insumos lidos nesse tique: as colunas da linha, `line_reason`, `line_points`, `mcap_slope_15m`,
      `curve_progress_pct`, o Mayhem e `completed_at`/`migrated_at` **como estavam**;
    - as recusas da camada de propostas (pedigree, cotação), por nome e **todas**;
    - `proposal_id`, ou `no_proposal_reason`.
  - Escrita na mesma transação da proposta, ou com o motivo da ausência. Sem poda até depois da leitura: ~300
    linhas/dia por conjunto.
  - Testes: reinício, falha parcial (proposta falha e a oportunidade fica com motivo) e retenção além de 7 dias.
- Guarda também os parâmetros e a versão da guarda de cobertura e o seu resultado no tique, para reproduzir a classe
  sem depender das fotos.
- **Consequência.** A 1.ª oportunidade do §2.2 é **leitura deste registro**, não reconstrução. A feature que conta é a que
  o laço leu no tique. Uma feature dobrada tarde entra no tique em que foi lida, nunca antes.

**Não é preciso:** mexer nas pistas de 15 s ou de eventos; fita nova; alterar `lines.py` (a v1 fica; fórmula nova
seria v2).

## 2. Os braços de papel (via de 1 min, `clock = "1m"`)

**Só a via de 1 min lê o bloco `line`**, e este desenho não constrói uma pista madura de 15 s. Os três conjuntos são
`research_only`: nascem aprovados por `rules`, e o executor nunca abre ordem para eles. Entram por migração de
semente no padrão da `0063`/`0065`, com revisão do database-architect.

### 2.1 Porta comum `grafico_maduro` v1

| parâmetro | valor | origem do número |
|---|---|---|
| `min_age_s` / `max_age_s` | 900 / 7 200 | pedido do brief (15–120 min); aos 15 min a linha de 15 min cobre desde o nascimento |
| `require_progress`, `min_progress_pct` / `max_progress_pct` | true, "5" / "90" | 5 = o piso das portas `fluxo_e_holders`; 90 = não comprar a < ~8 SOL da graduação (migração na posse é outra praça, §5) |
| `max_participation_pct` | "1" | igual a todas as portas; com 0,07 SOL pede **≥ 7 SOL/min** de volume (`rules_criteria.py:90`) |
| `require_creator_not_net_seller` | **false** | EXP-M2 morreu disto (§1.4); "fluxo do criador" é uma das 13 esgotadas; a saída `creator_dump` continua |
| `exclude_mayhem` | true | padrão T4.27 |
| `pedigree_exclusions` / `pedigree_repeat_dumper` | true / **false** (explícito no seed) | igual às portas da mesa; a exclusão substantiva fica só em `creator_serial`/`symbol_clone` (§2.2) |
| `size_sol` / `max_sol_per_bet` / `max_exposure_per_mint_sol` | "0.07" | ficha da mesa (KB-0147), custo comparável |
| `wallet_max_sol` / `daily_loss_cap_sol` / `max_open_positions` | "100.0" / "10.0" / 25 | como `recuo_v1/1`: tetos de pesquisa que não censuram a amostra. **Não são afirmação de risco**; é papel |
| `fee_pct` / `priority_fee_sol` | "1.75" / "0" | padrão do Lab |

### 2.2 Os três braços e o que cada um responde

| braço | linha exigida | saída | papel na H-022 |
|---|---|---|---|
| **`grafico_ctrl_v1/1`** (C) | nenhuma | **atual** `alvo_1_15x_trailing_10_tempo_5m` v1: `target_x "1.15"`, `trailing_pct "10"`, `trailing_arm_x null`, `max_hold_s 300`, `max_loss_pct "50"`, `exit_on_line_break true`, `line_break_snapshots 2`, `exit_on_migration true` | **população da primária**: a 1.ª decisão por mint é o 1.º minuto elegível; `linha_ok` é lido nesse minuto |
| **`grafico_v1/1`** (L) | `require_higher_lows true`, `require_breakout_15m true`, `min_distance_to_support_pct "0"`, `max_distance_to_support_pct "0.25"` (banda congelada de EXP-M2, T4.10) | a mesma atual | a política "esperar a estrutura". **Descritivo** contra C; base do par com H |
| **`grafico_v1/2`** (H) | a mesma de L | **pacote EXP-M2** `alvo_2x_trailing_30_tempo_15m_linha` v1: `target_x "2"`, `trailing_pct "30"`, `max_hold_s 900`, `max_loss_pct "50"`, `exit_on_line_break true`, `line_break_snapshots 2`, `exit_on_migration true` | **secundária**: pacote de saída mais longo, pareado com L na mesma decisão |

**Por que a primária fica dentro de C (decisão da rodada 1 com a Astra).**
- A porta de L contém a de C. O 1.º minuto elegível de C numa moeda chega **antes ou junto** do de L e de H, e as
  features desse minuto são dobradas antes de qualquer aposta do EXP-M26 nessa moeda. A variável não sofre a
  contaminação de I2.
- Comparar as apostas de L com as de C mediria outra coisa. L só entra nas moedas que sobrevivem até formar a
  estrutura, e C entra em todas. Uma "vantagem" apareceria sem medir o custo da espera.
- Por isso L − C fica **descritivo**.
- A primária é uma **associação preditiva** no mesmo instante, não o valor causal da política de esperar.
- A linha lida no 1.º minuto de C ainda pode ter fotos a mais, se uma porta de 1–4 min tiver apostado nessa moeda.
  - A covariável se define só com informação **anterior** à oportunidade: "houve aposta de outro conjunto neste mint
    aberta antes de `features_end_time`", fechada ou ainda em curso. Nunca "alguma vez teve aposta" até à leitura.
  - Entra estratificada no relatório.

**A primeira oportunidade (definição única para F, J e a leitura).**
- **1.ª oportunidade de C** = a linha de C em `meme_mature_opportunities` (R1): a 1.ª avaliação do laço de 1 min em
  que a porta pura de C deixa passar o mint.
  - Conta **desde o seed**, incluindo o piloto P. Um mint cuja 1.ª oportunidade caiu no piloto **nunca** entra na
    inferência. O mesmo vale para os pares H/L.
  - Exclusões registradas.
- **Se não houver proposta,** as recusas gravadas em R1 decidem. Todas ficam gravadas; a precedência só serve para
  contar.
  - **Exclusão por regra conhecida** (`E`): só com recusa **substantiva** comprovada, isto é `creator_serial` ou
    `symbol_clone` (`hunter_indicators/meme/pedigree.py:145`).
    - A oportunidade sai da população elegível e aparece no funil.
  - **Pedigree desconhecido** (`pedigree_unknown`, `creator_unknown`, `symbol_unknown`, `proposals.py:244`) **sem**
    recusa substantiva: é `sem_proposta` por instrumento.
    - **Cenário de falha que isto evita (Astra, rodada 4):** 25 % sem leitura de pedigree somem como "regra" e a
      falha nunca conta nos tetos.
  - Cotação ausente, falha de persistência ou outra: `sem_proposta` por instrumento.
- **A seguinte nunca a substitui.**

**Onde se lê `linha_ok` em C.** O bloco `line` não é gravado nas razões quando a porta não pede linha
(`proposals_reasons.py:67`), e `_GATE_ROWS` não seleciona `mcap_slope_15m`.
- **Fonte:** os insumos gravados em R1 no tique da 1.ª oportunidade, que são as colunas que o laço leu. Um relógio
  só, sem regra condicional à persistência da proposta.
- A linha de `meme_features_1m` (imutável, 90 d) serve de conferência, nunca de substituto.
- **Três classes, congeladas:**
  - **`true`:** linha traçada, coberta (guarda de I1) e com os três critérios de L.
  - **`false`:** linha traçada e coberta com algum critério falho, **ou** `line_reason ∈ {flat, out_of_range}` com
    cobertura. É o **`false` operacional da v1**: a regra executável de L recusaria.
    - `flat` coberto = a série não tem dois fundos.
    - `out_of_range` nasce **depois** de achar os dois fundos (suporte projetado ≤ 0 ou limites numéricos,
      `lines.py:244-257`). Não é afirmado como ausência de estrutura, e é contado à parte.
    - A cobertura mede-se com os **mesmos pontos utilizáveis** da fórmula (recebidos até T, `mcap_sol > 0`, um por
      instante), não com qualquer foto presente.
    - Sensibilidade pré-registrada: o mesmo contraste com `false` restrito às linhas traçadas (sem `flat` e
      `out_of_range`). O relatório diz que a primária cobre o universo "coberto" e a sensibilidade o "traçável".
  - **`desconhecida`:** falha de **coleta**, isto é `no_snapshot`, `too_few_points`, lacuna na guarda de cobertura
    ou linha ausente. Fica fora dos dois grupos, **nunca** vira `false`, e a sua taxa é reportada sobre o total de
    oportunidades.

**"A mesma saída" tem uma diferença declarada.** `exit_on_line_break` já está ligado na mesa, mas em moeda de 1–4 min
quase nunca há linha. Em moeda madura **vai disparar**.
- Semântica congelada, a do código: duas **fotos** seguidas abaixo do suporte projetado, na cadência da aposta
  (15 s com I2). Não são dois fechos de minuto.
- Saídas reportadas por motivo.

**H − L é um pacote, não "o horizonte".** Alvo, trailing e prazo mudam juntos. Aceito o pacote herdado de EXP-M2
porque é pré-registrado desde 12/09 e desenhado para a linha.
- **Chave do par:** mesmo mint, mesmo `features_end_time`, mesma foto de fill (`observed_at` e `source`). Qualquer
  outro desalinhamento (um dos lados sem fill, recusado por teto ou com reentrada) é **par ausente**, contado no
  denominador e nunca substituído.
- **O estimando é o do sistema conjunto L+C+H (Astra, rodada 2).** Depois da entrada, as apostas abertas dos três
  braços mantêm fotos de 15 s, e a saída `line_broken` de uma perna pode depender da cadência que outra sustenta.
  - D_pacote compara os dois pacotes **sob a observação conjunta**, não duas políticas isoladas.
  - Separar a observação seria outro experimento e não é pedido aqui.

**Nenhum limiar novo foi escolhido olhando dado.**
- A banda e o pacote H vêm do pré-registro de EXP-M2 (12/09), e a saída L/C é a da mesa.
- Só 5/90 % de progresso e 900/7 200 s são deste desenho, e vieram do brief e da mecânica da curva, não de desfecho.

## 3. Hipótese pré-registrada (para o orquestrador copiar para a [[Fila de Hipoteses]])

## H-022 — Estrutura do gráfico em moedas maduras (15–120 min, ainda na curva)

- **origem:** [[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]] — a H-021 parou por limite de dado estrutural: a porta compra com 1,6 min de vida e a linha de produção quase nunca existe nem chega ao portão das pistas rápidas; [[KB-0149-o-que-a-mesa-real-ensinou]] §7 — "nunca medimos vantagem em horizonte > 5 min"; [[EXP-M2-a-linha-manda]] (`trendline_v0/1`) teve 0 propostas e a linha **nunca foi julgada** — em 7,4 dias, 287 minutos passaram a linha, 275 com o criador desconhecido, e o único sobrevivente do funil não virou proposta por motivo irrecuperável (`docs/design/exp-m26-grafico-moedas-maduras.md` §1.4). **População nova** (moedas de 15–120 min retidas pelo rastreador, instrumentação I1) e medida **de produção executável em T** (`lines.py` v1, fotos com `received_at ≤ end_time`, insumos gravados no tique da decisão, R1); idade define a população, não é a variável (regra 1 da casa). Maior vazamento: [[Perdas/comprou_no_topo]]. Everton, 26/09/2026: testar moedas que já têm gráfico
- **variável:** `linha_ok` na **1.ª oportunidade por mint do controle `grafico_ctrl_v1/1`** (C: porta madura sem critério de linha, saída 1,15× / trailing 10 % / 300 s / linha rompida), lida dos insumos que o laço de 1 min leu nesse tique (`meme_mature_opportunities`, R1; linha `meme_features_v3`, `LINE_DEFINITIONS` v1); três classes congeladas no desenho §2.2 — `true` (coberta, `higher_lows` ∧ `breakout_15m` ∧ `distance_to_support_pct` ∈ [0; 0,25]), `false` operacional v1 (coberta e algum critério falho, ou `flat`/`out_of_range` cobertos, contados à parte), `desconhecida` (falha de coleta: fora dos grupos, nunca `false`). **Primária** D_linha = diferença de médias de PnL/SOL `true` − `false` dentro de C, **estimador estratificado** (dia × bloco de 6 h, pesos n_true·n_false/n, só estratos com os dois grupos) — associação preditiva no mesmo instante, não efeito causal da espera. **Secundária** (mesma família, Holm sobre os dois p): D_pacote = `grafico_v1/2` (H: porta de C + `linha_ok`, saída 2× / trailing 30 % / 900 s / linha rompida) − `grafico_v1/1` (L: mesma porta, saída de C), pareada por (mint, `features_end_time`, foto de fill), **sob a observação conjunta L+C+H**. L − C e o D global (sem estratos) são descritivos
- **população:** oportunidades prospectivas com `evaluated_at` entre T0 e o corte (§4) — moeda com 900–7 200 s, na curva, progresso 5–90 %, não Mayhem, participação ≤ 1 % (≥ 7 SOL/min com 0,07 SOL), pedigree; unidade = 1.ª oportunidade por mint **desde o seed** (C; um mint cuja 1.ª caiu no piloto nunca entra) e 1.ª decisão comum por mint desde o seed (par H/L), **fixada antes de qualquer filtro de fill ou desfecho** (a seguinte nunca a substitui); desfecho = `pnl_sol / size_sol` da aposta de papel (1,75 %/perna + impacto pela fórmula da curva), **condicional ao fill**; venda sem praça executável (foto de venda com `complete = true` ou em/depois de `completed_at`/`migrated_at`, qualquer que seja o gatilho) é censura nomeada
- **previsão:** D_linha ≥ **+0,03 por SOL**; IC 95 % **marginal** inteiramente acima de zero **em dois bootstraps** (`min(L_mint, L_blocos) > 0`) — por mint com todos os seus braços e por blocos de 6 h com os mints dentro (10 000 cada, semente 20260926); p de permutação de `linha_ok` dentro dos estratos (10 000; supõe permutabilidade condicional ao estrato, declarada) abaixo do limiar de Holm; ≥ 10 estratos com os dois grupos; o grupo `true` lucrativo em nível (média > 0); **planalto** (o sinal de D repete com teto de distância 0,10, 0,25 e 0,50 na definição de `true`); sinal mantido em ≥ 2 dos tercis avaliáveis de `curve_progress_pct` na oportunidade (cortes por posto sobre a população, sem desfecho; avaliável = ≥ 20 em cada grupo; menos de 2 avaliáveis → não satisfaz); a **cláusula de identidade** não dispara (dividir as mesmas oportunidades só por `mcap_slope_15m > 0` do mesmo tique, com o mesmo estimador, não dá diferença ≥ D_linha; `mcap_slope_15m` ausente em > 20 % → não satisfaz); a conclusão (IC inferior > 0 e nível > 0) sobrevive ao **estresse de censura** da §4 com os preenchidos-sem-desfecho de `true` em **perda integral** (−`sol_spent`/`size_sol`). Descritivo: taxa de `comprou_no_topo` (pico ≤ custo) em `true` ≤ 0,75× a de `false`. **Secundária:** D_pacote ≥ +0,03, IC 95 % marginal > 0 em bootstrap de pares por mint **e** por blocos de 6 h, p por bootstrap em blocos centrado sob a nula abaixo do limiar de Holm, ≥ 10 blocos com pares, H lucrativo em nível, estresse dos três casos de par incompleto da §4
- **refutação:** `max(U_mint, U_blocos)` de D_linha < +0,03, isto é os dois limites superiores dos IC 95 % abaixo do MRE (REFUTA um efeito desse tamanho); qualquer outra falha da previsão, IC não finito ou < 10 estratos/blocos → NÃO CONFIRMA; **limite de dado** se em qualquer leitura houver menos de 100 `true` **ou** menos de 300 `false` avaliáveis nos estratos com os dois grupos; **NÃO CONFIRMA por instrumento** se `desconhecida` > 20 % das oportunidades inscritas, ou `sem_proposta` por instrumento > 5 %, ou, dentro de `true` ou de `false`, a união {`sem_proposta` por instrumento, sem fill, preenchido sem desfecho precificável} > 20 % das **elegíveis** (as exclusões por regra conhecida — `creator_serial`, `symbol_clone` — não entram no denominador; pedigree desconhecido é `sem_proposta` por instrumento), ou se a coleta parou pela guarda da §6.8. Secundária: mesma regra com D_pacote; menos de 100 pares completos ou pares ausentes > 20 % das decisões comuns → NÃO CONFIRMA
- **registro:** 26/09/2026, antes de reter qualquer moeda madura e antes de existir qualquer proposta dos três braços; só contagens cegas foram vistas (desenho §1: cobertura, funil de EXP-M2, distribuições da linha — nenhum PnL, MFE ou motivo de saída); o spec do moinho (J) é congelado, com impressão digital e testes sintéticos dos cenários de falha, antes do seed
- **status:** aberta

## 4. Regra de decisão e tamanho da amostra

**Calendário (timestamps exatos gravados na página EXP-M26 no dia do seed).**
- **Seed:** a identificação da "1.ª por mint" começa aqui.
- **T0:** fim do **piloto técnico** (seed + 48 h). As oportunidades e apostas do piloto ficam **fora** da inferência,
  e os mints delas ficam fora para sempre.
- **Corte:** o 1.º 00:00Z depois de **7 dias completos desde T0** em que C já tem ≥ 150 `true` **e** ≥ 450 `false`
  inscritas. No **máximo o 00:00Z do dia 21 desde T0**.
- **Inscrição:** entram as oportunidades com `evaluated_at` em [T0, corte). Nenhuma nova entra depois do corte. As
  inscritas amadurecem.
- **Leitura:** corte + 2 h (900 s de posse, fill, foto de venda e folga). O que estiver aberto nesse momento é
  censura `aberta_na_leitura`.
- **Parada pela guarda (§6.8):** encerra a coleta e dá **NÃO CONFIRMA por instrumento**, qualquer que seja o n. Os
  mínimos de grupos, pares e estratos valem em **qualquer** leitura, não só no dia 21.
  - As `approved` sem fill no instante da aposentadoria são recusadas `rule_set_inactive` pelo laço
    (`lab_bets.py:100`) e contam como sem fill. As apostas abertas seguem até fecharem (`process_open_bets`).
- **A coleta não é cega.** A ficha diária mostra o PnL dos braços de pesquisa a quem a lê. O que protege é o
  congelamento: o spec J e o protocolo EXP-M26 têm impressão digital antes do seed, e nada muda até à leitura.
  Qualquer mudança é versão nova e hipótese nova.

**Denominadores e motivos.**
- **Equação congelada, por classe g ∈ {`true`, `false`}** (Astra, rodada 4):

  ```text
  N_bruto_g    = E_g + N_elegivel_g                  (E = exclusão por regra conhecida: creator_serial, symbol_clone)
  N_elegivel_g = I_g + F_g + C_g + A_g               (I = sem_proposta por instrumento, F = sem fill,
                                                      C = preenchido sem desfecho precificável, A = avaliável)
  taxa_falha_g = (I_g + F_g + C_g) / N_elegivel_g    ≤ 20 %
  taxa_I_g     = I_g / N_elegivel_g                  ≤ 5 %
  ```

- Os componentes da equação:
  - F inclui `rule_set_inactive` na parada;
  - C inclui `indeterminate`, venda sem praça executável e `aberta_na_leitura`;
  - um motivo por oportunidade na ordem E → I → F → C → A, com todos os motivos gravados.
- **`desconhecida`:** `taxa_U = U / (N_elegivel_true + N_elegivel_false + U)`.
  - U conta só as oportunidades desconhecidas que não foram excluídas por E.
  - Teto: ≤ 20 %. Com denominador zero não há taxa estimável nem aceite de amostra.
- As exclusões E aparecem no funil e **não diluem** os tetos. Para H/L, a mesma distinção vale nas decisões comuns.
- O retorno observado é **condicional ao fill**. O relatório declara que estendê-lo a todas as oportunidades depende
  da sensibilidade abaixo.
- Os pares H/L contam sobre as decisões comuns de L e H desde T0. **Reentradas** ficam fora das duas análises.

**Inferência (uma população e uma estatística por contraste).**
- **Primária.** O D, o IC, o p, o MRE e os mínimos são **todos** calculados sobre os mesmos estratos com os dois
  grupos, pelo estimador estratificado da §3.
  - Estratos sem os dois grupos ficam fora de tudo e são contados. O D global é descrição.
  - IC: bootstrap por mint (os braços juntos) **e** por blocos de 6 h (os mints dentro).
  - **Regra de concordância (Astra, rodada 4), para os dois contrastes:**
    - `CONFIRMA` exige `min(L_mint, L_blocos) > 0`;
    - `REFUTA` exige `max(U_mint, U_blocos) < +0,03`.
    - O procedimento nunca se escolhe pela largura observada.
    - Os dois IC marginais são publicados separadamente. A regra não faz deles um IC conjunto calibrado.
  - p: permutação de `linha_ok` dentro do estrato. A permutabilidade condicional ao estrato é suposição declarada;
    a condição sobre os blocos protege contra a dependência temporal que ela ignora.
- **Secundária.** Média das diferenças H − L por par completo.
  - IC: bootstrap de pares por mint **e** por blocos de 6 h.
  - p: bootstrap em blocos de 6 h, centrado sob a nula (média das diferenças = 0).
  - A troca de sinal por par fica só como análise condicional, porque supõe simetria e independência.
  - Com < 10 blocos com pares, é "não testável", mas **continua na família**.
- **Família:** Holm sobre {p_primária, p_secundária}. Não se reduz a multiplicidade depois de ver os dados.
- Todos os IC são **marginais** de 95 %. IC não finito dá NÃO CONFIRMA.

**Estresse de censura (congelado; Astra, rodadas 2 e 3).**
- Aplica-se aos **preenchidos sem desfecho precificável**. Os sem fill não tiveram posição: ficam fora do PnL e
  contam no teto.
- **Perda integral** = −`sol_spent`/`size_sol` da própria aposta. `quote_buy` tira a taxa de dentro do orçamento e
  `paper_fill` grava o custo inteiro (`curve.py:272`, `paper_fill.py:171`). Somar a taxa outra vez contaria duas
  vezes.
- **Cenário que sustenta o rótulo:**
  - censurados de `true` em perda integral, censurados de `false` na média observada de `false` (imputados por
    estrato);
  - o IC inferior de D (os dois bootstraps) continua > 0 e a média de `true` continua > 0;
  - se falhar, NÃO CONFIRMA.
- **Descritivo, sempre publicado:**
  - censurados de `true` a −0,50/SOL;
  - o **ponto de inversão** (a média dos censurados de `true` que leva D a 0 e a +0,03);
  - a **grade bidimensional** das médias ausentes de `true` × `false`, de −1,0 até à média observada de cada grupo
    e dela até ao p90 observado do grupo.
  - A conclusão é condicional à região examinada. Não se inventa teto de retorno.
- **Secundária, três casos de par incompleto:**
  - H ausente e L presente: H em perda integral, L observado;
  - H presente e L ausente: L no p90 observado de L nos pares completos, H observado;
  - os dois ausentes: a diferença no p10 observado das diferenças completas.
- **Regras do estresse:**
  - Os valores de cenário ficam **presos às suas unidades** e acompanham-nas na reamostragem (mint/bloco com o seu
    estado de ausência). As médias dos observados são recalculadas em cada réplica.
  - Nunca se inventam quantis de um grupo vazio.

**Desfecho e sensibilidades.**
- **Desfecho:** `pnl_sol / size_sol` da aposta de papel.
- **Cenário contábil "real-equivalente".** Não re-simula; mantém fills, gatilhos e impacto, porque o `target_x`
  incide sobre marca líquida (`exits.py:229`) e mudaria de lugar numa re-simulação.
  - Equação executável no J, sobre o mesmo `size_sol`: `PnL_alt = PnL_papel + taxas_papel_debitadas −
    taxas_alternativas − custos_adicionais`.
  - As taxas alternativas são repartidas por perna a partir das médias da KB-0147 (pump.fun 1,59 % + criador
    0,50 % por ida-e-volta; rede 0,13 %). É um **cenário**, não a taxa exata por perna.
  - Dois cenários de rent: 0,00151384 SOL (2,16 % de 0,07) e rent devolvido.
- **Migração:** a venda sem praça executável é censura. À parte, só como descrição: repreço pela 1.ª observação do
  board `graduated` depois da migração, com a faixa PumpSwap de 1,20 %/perna (§5).

**Rótulos (`docs/RESEARCH.md`).**
- Primeiro verificam-se a parada pela guarda, o instrumento e a amostra (limite de dado, tetos de censura e de
  `desconhecida`, mínimos de estratos).
- Depois: `CONFIRMA` só se toda a previsão da §3 bate, com `min(L_mint, L_blocos) > 0`; `REFUTA` se
  `max(U_mint, U_blocos) < MRE (+0,03)`; senão `NÃO CONFIRMA`.
- Um `CONFIRMA` autoriza **candidato a sombra**, com braço pré-registrado próprio, nunca parâmetro de mesa. Não é o
  selo editorial de "estratégia validada" da página Meme (100 avaliáveis e 30 dias,
  `obsidian/03-TRADING/Meme/README.md`).

**Potência (suposições declaradas, aproximação normal, grupos independentes, bilateral, sem estratos nem blocos).**
- **DP do PnL/SOL ≈ 0,18.** É cenário, não medida. O retorno realizado não fica preso à geometria nominal
  (−50 % / +15 %): a venda é na foto seguinte ao gatilho (`paper_engine.py`, `lab_bets.py:227`).
- **150 `true` contra 450 `false` (alvo do corte):** EP(D) ≈ 0,017.
  - D = +0,05: potência ≈ 84 % com α = 0,05 e ≈ 76 % com α = 0,025 (1.º degrau de Holm).
  - D = +0,03 (o MRE): ≈ 42 % / 32 %.
- **100 contra 300 (o mínimo):** EP ≈ 0,021, e D = +0,05 dá ≈ 67 % / 57 %.
- Números conferidos pela Astra em memória. São potências **marginais**: a estratificação, os blocos, o estresse e
  as condições de planalto/tercis/identidade só as baixam.
- **O teste enxerga bem efeitos ≳ +0,05/SOL.** Um efeito verdadeiro de +0,03 sai quase sempre NÃO CONFIRMA. Também
  pode sair REFUTA por erro amostral (≈ 2,5 % das repetições com o efeito exatamente no MRE).
- Para D_pacote conta a variância da diferença pareada, que depende da covariância e não é garantidamente menor.

**Ritmo (estimativa com fator 3 de incerteza, a confirmar no F).**
- ~300 moedas maduras/dia na curva visíveis nos boards (§1.5) e ~500 com compras aos 15 min (§1.1).
- Metade com volume para a participação: C ~150–300 oportunidades/dia.
- `true` na 1.ª oportunidade: ~10 % (§1.3, fundos ∧ rompimento nos minutos ativos, antes da banda). Dá **~15–30
  `true`/dia e ~100–250 `false`/dia**, ou seja 150 `true` em ~5–10 dias; o piso de 7 dias domina.

**Funil F (viabilidade, sem desfecho), com I1/I2/L1/R1 ligados 24 h e sem os três conjuntos.**
- R1 só escreve para conjuntos do EXP-M26. No F, a mesma porta pura é avaliada fora do Lab, com o código de R1,
  sobre as linhas retidas.
- **1.ª oportunidade por mint, ordenada antes de ver a linha**, classificada nesse instante em
  `true`/`false`/`desconhecida`.
- Contagem de cada recusa por nome, e da **união** das falhas de instrumento. A recusa operacional da v1 (`flat`,
  `out_of_range`, que são `false`, cada uma contada) fica separada da falha de **coleta** (`desconhecida`). As
  exclusões E ficam separadas do pedigree desconhecido (I).
- **Pisos para semear (metas operacionais, não evidência de potência):**
  - C ≥ 50 oportunidades/dia;
  - `true` ≥ 8/dia **e** `false` ≥ 24/dia;
  - `desconhecida` + falhas de instrumento (união) ≤ 15 % das oportunidades, com folga sob os 20 % da leitura.
- **Se falhar:**
  - por **instrumento** (coleta, pins, cobertura), conserta-se e repete-se o F;
  - por **mercado** (poucas moedas elegíveis), o resultado é **inviabilidade**, declarada como tal, e **não** se mexe
    em limiares (lição de EXP-M2).

**Piloto técnico P (48 h depois do seed, antes de T0).**
- Verifica oportunidade (R1) → proposta → fill → marcas de 15 s → saída → censura nos três braços. Lê só contagens e
  motivos, nunca PnL.
- Vem **depois** dos testes de integração de I2/L1/R1:
  - migração entre gatilho e fill;
  - conclusão sem evento de migração;
  - sem foto seguinte;
  - resgate por leitura pontual;
  - reinício;
  - falha parcial da proposta;
  - retenção além de 7 dias.
- Se o piloto mostrar braço que não enche, saída impossível ou oportunidade sem registro, pára antes de T0: os
  conjuntos são aposentados, com motivo.

## 5. Modelo de custo: curva × PumpSwap

| item | na curva (onde os braços compram e, quase sempre, vendem) | PumpSwap (depois da graduação) |
|---|---|---|
| taxa | mesa real medida: pump.fun 1,59 % + criador 0,50 % **por ida-e-volta**, sobre o tamanho (KB-0147) | 1,25 %/perna abaixo de 420 SOL de mcap; **1,20 %** entre 420 e 1 470; 0,30 % só a partir de 98 240 SOL (KB-0148 §1) |
| ida-e-volta realizado | **2,23 %** sem rent (rede 0,13 % incluída) | mediana **2,40 %** (média 2,26 %) |
| rent de ATA | 0,00151384 SOL = **2,16 %** de 0,07 se a ATA não for fechada (1,86 % medido sobre a mistura de tamanhos do KB-0147) | igual; não muda de praça (KB-0148 §2) |
| no papel | `fee_pct 1,75` por perna, com bases diferentes na compra e na venda (≈ 3,5 % ida-e-volta) + impacto pela fórmula da curva | venda pelo `pool_mark.py` só quando `exit_on_migration = false` (`lab_bets_pool.py:64`); os três braços têm `true`, então **não** passam por lá |
| comprar | permitido (papel) | **não existe**: recusa `already_migrated` no portão (`rules.py:302`) e `pumpswap_buy_not_allowed` na mesa (KB-0148 §6) |

- **Equilíbrio.** Não se transportam taxas de acerto de outra amostra. Os ~19 %/27 % do KB-0147 são **empíricos da
  mesa**, com trailing móvel.
  - Num binário ideal (+15 % líquido contra −10 % líquido) o equilíbrio seria 40 %. Nenhum dos braços é binário,
    porque linha rompida, `max_loss`, tempo e migração entram no meio.
  - Não há número de equilíbrio pré-registrado: decide o PnL líquido medido.
- **Por que não há braço pós-graduação.** KB-0148:
  - a população graduada cai 79,9 % na mediana aos +15 min;
  - a nossa regra perdeu em 8 de 8 dias;
  - a taxa é a mesma da curva;
  - não há caminho de compra.
  Os `movers` maduros já são quase todos graduados (§1.5).
- **Migração durante a posse.** Com `exit_on_migration = true` a venda segue `close_bet` com as reservas da curva
  (`lab_bets.py:230`, `paper_engine.py:215`). Mas uma curva completa já não é negociável, e repreçar esse número com
  a taxa do PumpSwap **fabricaria liquidez**.
  - **Censurar pelo motivo não basta (Astra, rodada 2).** O laço fecha uma intenção pendente antes de reavaliar a
    migração daquela foto (`lab_bets.py:227`, `:252`), e `close_bet` preserva o motivo antigo (`paper_engine.py:207`).
    - **Cenário:** alvo em T, a curva completa antes da foto seguinte, e a venda sai com as reservas dessa foto e
      motivo `target`.
    - Por isso a censura é pela **praça e pelo estado da foto de venda**, qualquer que seja o gatilho: foto com
      `complete = true`, ou com `observed_at ≥ completed_at`/`migrated_at`, é "venda sem praça executável".
    - Vale para C e para as duas pernas H/L.
  - Com progresso ≤ 90 % na entrada é rara em 300 s, mas não em 900 s (H), o que pesa na secundária.
  - **Os testes de integração de I2/L1 provam quatro casos:** migração entre gatilho e fill, conclusão sem evento de
    migração, sem foto seguinte e resgate por leitura pontual.
  - O board posterior é descrição, nunca venda executável comprovada.

## 6. Riscos

1. **Sobrevivência (o maior).**
   - A moeda viva aos 15 min já é selecionada: 3,9 % das que tinham série no minuto 15 (§1.1).
   - A retenção por maior `mcap_sol` seleciona outra vez, a favor das que subiram.
   - A primária é **dentro de C**, a mesma população nos dois grupos, e a sobrevivência não a envenena. O **nível**
     de C, esse, diz respeito só a "mints retidos por esta política" e não generaliza para a moeda de 1–4 min.
   - A seleção é causal (só `mcap_sol` já recebido, com frescor ≤ 120 s). É definição de população, declarada, não
     antecipação.
2. **Antecipação.**
   - **Entrada.** A linha lê só fotos com `received_at ≤ end_time` (`lines.py` `usable_points`, provado em
     `test_meme_lines.py`); em C a linha é a que o laço leu no tique da oportunidade, gravada em R1 (um relógio
     só); a idade vem de
     `meme_tokens.created_at` (escrito uma vez).
   - **Fill e venda.** O fill é na 1.ª foto com `observed_at > decided_at`, e a venda na foto seguinte à regra.
   - **Saída `line_broken`.** Com L1 (parâmetros `line_support_causal`, `line_support_max_age_s`, só no EXP-M26)
     exige `computed_at ≤` foto julgada e suporte com ≤ 120 s. Sem L1 o atraso medido foi ≤ 5,3 s (p99), mas isso
     não é limite máximo. O suporte velho projetado sem limite de idade é o defeito maior.
   - **Retenção.** I1 não pode ler nada que chegue depois do `prune`, e o teste de I1 prova isso.
3. **Os braços mexem no instrumento.** As apostas abertas somam fotos de 15 s (I2), e as linhas usam todas as fotos.
   Por isso a primária lê a linha no 1.º minuto de C, antes de qualquer aposta do EXP-M26 na moeda. L − C e as
   linhas depois da entrada ficam contaminadas e são só descritivas.
   - A contaminação que vem de antes, das portas de 1–4 min, é covariável reportada.
4. **Confusão com progresso.** Em moeda nova a distância era "quanto já subiu" (Spearman 0,60, KB-0161 §4). A
   previsão exige o sinal em ≥ 2 dos tercis avaliáveis de `curve_progress_pct`. Se o efeito só vive entre tercis, é progresso,
   uma das 13 esgotadas.
5. **Redundância com "está subindo".** A cláusula de identidade (EXP-M2) usa `mcap_slope_15m` da mesma linha de
   `meme_features_1m`.
6. **Latência da via de 1 min.** Decide depois do fecho do minuto: fold p99 5,3 s, mais o tique do Lab.
   - O fill é na 1.ª foto depois da decisão: ≤ 60 s pela cadeia, ≤ 15 s se a moeda já estiver na série de 15 s.
   - Reportar `decision_to_fill_s` p50/p95 por braço.
   - Suposição, não medida: moeda madura anda mais devagar e o argumento do KB-0061 pesa menos.
7. **Papel × real.** Sem MEV, sem transação falhada, sem prioridade. O custo real só entra pela sensibilidade
   contábil da §4.
8. **Custo do instrumento sobre as outras pistas.** As retidas ficam em orçamento à parte, mas a cadeia, a fita e o
   fold passam a ter mais trabalho.
   - Guardas contra as 72 h antes de I1:
     - descobertas → rastreadas → com linha < 5 min por hora não caem mais de 2 %;
     - a fração de linhas < 5 min com `tape_reason = 'not_polled'` ou `curve_reason` não nulo não sobe mais de 2 pp;
     - a duração do ciclo da cadeia, do fold e do Lab não sobe mais de 20 % no p95.
     - apostas abertas do EXP-M26 ≤ 10 em qualquer janela de 15 min, pela prioridade de REST e fita.
   - **Ação congelada, se alguma guarda falhar:**
     - pára as **novas inscrições**: os três conjuntos são aposentados com `meme_rule_set.py --deprecate`, auditado e
       com motivo, e `K = 0`;
     - regista o fim da coorte com timestamp;
     - o resultado é **NÃO CONFIRMA por instrumento** (§4);
     - as `approved` sem fill são recusadas `rule_set_inactive` e as apostas abertas seguem até fecharem.
   - `K = 0` sozinho não chega, porque a porta não consulta K (`proposals.py:265`).
   - Retomar exige coorte nova e identificada (versão nova dos conjuntos). Nunca se mistura o antes e o depois.
9. **Muitos braços.** São três, com uma família de Holm de 2 contrastes. Nada de variantes antes da leitura.

## 7. O que precisa ser construído (ninguém construiu nada ainda)

| # | o quê | arquivos (previstos) | dono | revisão |
|---|---|---|---|---|
| I1 | retenção madura limitada (orçamento à parte, `mcap_observed_at`, frescor ≤ 120 s, recarga no reinício, heartbeat). Testes puros: elegibilidade por idade/terminada/Mayhem/frescor, ordem por `mcap_sol` com desempate, limite K, teto das jovens inalterado, leitura recebida depois não muda a escolha | `hunter_meme_worker/tracker_mature.py` (novo), `tracker.py`, `tracker_types.py`, `warmup.py`, `repo.py`/`repo_token_sql.py`, `source_stats.py`, testes | backend-specialist | quant-engineer, code-reviewer |
| I2 | fixar `approved` sem aposta do EXP-M26 (prazo terminal 180 s); série de 15 s para apostas abertas do EXP-M26 até fecharem (por pertença); fixadas do EXP-M26 no orçamento à parte. Teste de integração retenção → `approved` → fill → fecho → reinício com o teto das jovens inalterado | `tracker_pins.py`, `tracker.py`/`tracker_mature.py`, `fast_lane.py` (`young_mints`), testes | backend-specialist | quant-engineer |
| L1 | parâmetros `line_support_causal` e `line_support_max_age_s` (só EXP-M26; conjuntos vivos inalterados): `SupportLine.computed_at`, `support_at` exige `computed_at ≤ at` e suporte com ≤ 120 s (`support_stale`); censura por praça/estado da foto de venda; testes de linha atrasada e suporte velho até ao laço (gatilho e venda) e dos quatro casos de migração | `lines_exit.py`, `lab_repo_lines.py`, `lab_params.py`, `hunter_indicators/meme/rules_validation.py` se preciso, testes | backend-specialist | quant-engineer, risk-engine-guardian (saída) |
| R1 | tabela só de acréscimo `meme_mature_opportunities` (1.ª avaliação que passa a porta pura por conjunto do EXP-M26 e mint, com os insumos lidos no tique, as recusas da camada de propostas e `proposal_id`/`no_proposal_reason`); escrita pelo laço de 1 min; sem poda até à leitura. **Aceite (Astra, rodada 5):** chave única (conjunto, mint); ordem determinística de avaliação no backlog; insumos, parâmetros e cobertura congelados; vínculo idempotente com proposta existente; testes de falha SQL recuperável e de queda antes/depois do commit, com registro e motivo quando a proposta falha (uma transação inteira revertida não basta); se a 1.ª oportunidade não puder ser recuperada fielmente, falha de instrumento, nunca substituição; reinício; retenção > 7 d | `infra/migrations/versions/00xx_meme_mature_opportunities.py`, `hunter_meme_worker/lab.py` (chamada), módulo novo `lab_opportunities.py`, testes | backend-specialist | database-architect, quant-engineer |
| C1 | `MEME_TRACK_MATURE_TOP_K=60` no compose de produção | `infra/vps/docker-compose.prod.yml`, `docs/DEPLOYMENT.md` | devops-engineer | — |
| F | funil de viabilidade de 24 h depois de I1/I2/L1/R1/C1 (§4): porta pura de C avaliada fora do Lab com o código de R1, 1.ª oportunidade por mint, classes, E × I, união das falhas; sem desfecho | `.claude/state/m26/` | quant-engineer | Astra |
| J | spec do moinho (`infra/research`) para D_linha e D_pacote, **congelado com impressão digital antes do seed**, com testes sintéticos dos cenários de falha das rodadas 1–4: 1.ª oportunidade lida de R1, classes, equação de denominadores (E/I/F/C/A), estimador estratificado (n, pesos, blocos por `evaluated_at` UTC, estratos vazios nas réplicas, quantis, p bilateral), regra de concordância dos dois IC, estresse de censura (par incompleto por falta de fill × desfecho ausente; nível de H no caso ambos ausentes), tercis/planalto/identidade (empates, ausências), Holm com hipótese não testável, equação contábil com as bases de cada taxa | `.claude/state/m26/` | quant-engineer | Astra |
| P | piloto técnico de 48 h depois do seed (só contagens e motivos; fora da inferência) | `.claude/state/m26/` | quant-engineer | — |
| S | migração de semente dos três conjuntos `research_only` (`clock 1m`, `exp_ref EXP-M26`) | `infra/migrations/versions/00xx_meme_mature_chart_arms.py` + teste de migração | backend-specialist | database-architect |
| O | página `obsidian/05-EXPERIMENTS/EXP-M26-grafico-em-moedas-maduras.md` (protocolo congelado); H-022 na fila; avaliação datada em EXP-M2 (funil §1.4); Mapa (desenho → Vivas só depois do seed) | Obsidian (MCP) | orquestrador / sexta-feira | — |

Ordem: I1 + I2 + L1 + R1 (com testes de integração) → C1 → 24 h → F → J congelado → S → P (48 h) → T0 → corte (≥ 7 d,
≤ 21 d) → leitura (corte + 2 h).

## 8. Decisão conjunta com a Astra

Diálogo em `.claude/state/dialogue-EXP-M26.md`, cinco rodadas, 26/09/2026. Rodadas 1–4: **REVISE**, com must-fix
incorporados neste documento. Rodada 5 abre com **DECISÃO CONJUNTA**, colada abaixo como veio.

> **DECISÃO CONJUNTA**
>
> Convergimos no desenho do EXP-M26. Os dois MUST-FIX da rodada 4 estão resolvidos no protocolo; não encontrei outro
> bloqueio de desenho com cenário concreto. O acordo é sobre o que construir e provar: seed e coleta confirmatória
> continuam condicionados aos aceites abaixo.
>
> Pontos acordados:
>
> 1. População prospectiva de mints descobertos e retidos pela política madura, 15–120 min, três conjuntos
>    `research_only`, fórmula de linha v1, banda 0–0,25 e ticket 0,07 SOL preservados.
> 2. Primária associativa dentro de C, na primeira oportunidade desde o seed, registrada em R1 antes de filtrar
>    proposta, fill ou desfecho. Mint do piloto não volta para a inferência. L−C é descritivo; H−L mede o pacote de
>    saída sob observação conjunta L+C+H.
> 3. Exclusão substantiva conhecida separada de falha instrumental; denominadores elegíveis sem diluição por
>    exclusões, com todas as recusas preservadas.
> 4. Mesma população e estatística para D, IC, p, MRE e mínimos; dois ICs marginais por contraste, família fixa de
>    dois testes com Holm e regra de concordância pelos extremos dos ICs.
> 5. Instrumentação causal, orçamento das jovens preservado, acompanhamento das propostas/apostas e censura pela
>    praça efetiva da venda; estresse declarado como cenário condicional, sem promessa de robustez geral.
> 6. J congelado e testado antes do seed; piloto técnico fora da inferência; parada pela guarda implica NÃO CONFIRMA
>    por instrumento. Não há evidência nova de vantagem nem decisão sobre dinheiro real.

**Divergências registradas e como terminaram** (resumo da rodada 5):

| tema | posição inicial | decisão |
|---|---|---|
| primária L − C | Claude: primária entre braços | **Astra:** L só entra nas sobreviventes, e o contraste mede a espera sem a custear. Primária virou **associação dentro de C**; L − C ficou descritivo |
| H − L | Claude: "horizonte" | É um **pacote** de saída, medido **sob a observação conjunta** L+C+H |
| `flat`/`out_of_range` | Astra (r2): fora dos grupos | Aceite (r3/r4) como **`false` operacional v1**, `out_of_range` contado à parte, com a sensibilidade "só traçável" |
| censura | Claude: p10/p90, depois −0,50 | **Perda integral** (−`sol_spent`/`size_sol`) no grupo favorecido sustenta o rótulo; −0,50, ponto de inversão e grade 2D são diagnósticos; tudo **condicional** à região examinada |
| pedigree | Claude: recusa gravada = exclusão | Só `creator_serial`/`symbol_clone` excluem; o pedigree **desconhecido** é falha de instrumento |
| REFUTA | Claude: "IC mais largo" | `max(U_mint, U_blocos) < +0,03`; `CONFIRMA` com `min(L_mint, L_blocos) > 0` |
| limitações que ficam | — | a permutabilidade condicional e a dependência residual são suposições declaradas: os testes extra não as demonstram e não validam estratégia para a mesa |

**O que continua pendente antes do seed (aceites de J e da implementação, Astra, rodada 5):**
1. **R1:** durabilidade e 1.ª oportunidade (§7, linha R1).
2. **J, inferência:** n, pesos normalizados, blocos por `evaluated_at` UTC, estratos vazios nas réplicas, quantis,
   p bilateral, hipótese não testável na família fixa.
   - Testes dos contraexemplos das rodadas 3–5, de poucos blocos, de IC não finito e da precedência de
     instrumento/amostra.
3. **J, censura:** separar a falta de fill da compra preenchida sem desfecho. Especificar o **nível de H** quando as
   duas pernas faltam. Fixar o que é recalculado em cada réplica.
4. **J, sensibilidades:** empates, ausências, grupos vazios, população da identidade, grade 2D e bases das taxas.
   Publicar as inversões de sinal junto do rótulo.
5. **Integração:** orçamento das jovens durante retenção → `approved` → fill → fecho → reinício; suporte causal e
   fresco até ao gatilho e à venda; migração/conclusão entre gatilho e fill; foto em falta e resgate pontual.
6. **Sequência:** I1/I2/L1/R1 → C1 → F → J congelado → S → P → T0. Falha do piloto impede iniciar a inferência.

# R76 — H-014, rede coordenada de compradores

**Data:** 23/09/2026, dados da VPS com corte às ~22:16 UTC (19:16 BRT). **Pré-registo:** o bloco H-014 da fila, usado verbatim.

## Resposta curta

**Veredito: `NÃO CONFIRMA`.**

- **Pela letra:** a cláusula (a) literal dispara. Pela errata escrita antes do contraste (§0.4b-4), isso só não-confirma. A
  (d) (cobertura) não dispara. A (c) não dispara na primária e dispara na secundária. A (b) sai "pico" no diagnóstico
  mecânico, mas esse diagnóstico é insuficiente com 3 partições (§5).
- **Leitura:** a medida "primeiro financiador comum" **não sustentou** a previsão de despejo coordenado nesta população.
  - O caso de origem (SIMFTR) e os outros três da origem (CITIZEN, WAVECOREE, RHOS) têm rede de **0–1,4 %**.
  - A taxa de despejo coordenado no tercil alto é **0,67×** a do baixo (a previsão pedia ≥ 2×).
  - Nenhum teto bloqueia mais de **1 das 6 piores reais** (o AIRAA).
- **O retorno aponta no sentido da tese, sem confirmar.** D (baixo − alto) = **+0,054 por SOL**, IC 95 % [−0,005, +0,116],
  p 0,083, Holm 0,166. O braço baixo ainda perde em nível (−0,043). O efeito **inverte** quando se excluem os financiadores
  de classificação desconhecida (s1: −0,024).
- **Não construir** a medida de financiador (RPC) nem proxy dela. §8 tem a recomendação.
- **Custo Helius:** 12 694 chamadas, cerca de 132 mil créditos registados (+ ≤ 5 mil de um lote interrompido), **0 HTTP 429**.

**Método:** leitura da VPS só com `SELECT`/`COPY TO STDOUT`, numa transação forçada a READ ONLY (`PGOPTIONS=-c default_transaction_read_only=on`,
`.claude/state/r76/q.sh`). Os financiadores vêm da Helius, consultada de dentro do contêiner `hunter-meme-worker-1` com um script
enviado por stdin (`r76/resolver_tpl.py`). A chave só é lida de `os.environ` e nunca é impressa. Cache sem segredos em `r76/cache_*.jsonl`.

## 0. Desenho congelado antes de resolver a população

Nenhum financiador da população foi consultado antes deste bloco, e nenhum desfecho foi olhado. Só o caso de origem (SIMFTR) foi
resolvido, como piloto do método (§0.3).

### 0.1 População
- Exports: `r76/pop.csv` (95 posições reais fechadas e 1 223 apostas de papel da porta `fluxo_e_holders/*`, `leg = single`,
  fechadas), `r76/tape.csv` (174 340 trocas de `meme_trades`, do nascimento até à última entrada + 7 min) e `r76/snap.csv`
  (16 646 fotos da curva).
- **Uma decisão por mint.** A real ganha da de papel. Entre iguais fica a mais antiga (`decided_at`, depois `bet_id`), que é a
  regra do R73/R75. Resultado: 84 mints reais e 507 mints só de papel.
- **Fita desde o nascimento** (critério do R73, retrospetivo): a 1.ª troca fica a ≤ 5 s do `created_at` **e** a fita reproduz
  o `real_sol_reserves` da foto da proposta a ±2 %. Aplica-se às duas vias na análise principal. Elegíveis: 45 reais + 246 de
  papel = 291 mints.
- **Desfecho resolvível:** o simulador do R72 dá `ok` (≥ 3 pontos na janela).

### 0.2 Variável
- **Compradoras pré-decisão:** `trader` distintos com `side = buy` e `block_time < decided_at` em `meme_trades`, sem a nossa
  carteira. É um **oráculo retrospetivo**: a fita WS ao vivo vê estas compras, o arquivo por polling não (R73).
- **Financiador** = remetente da **primeira transferência de SOL recebida**. Método: `getTransactionsForAddress` da Helius
  (`sortOrder = asc`, `limit = 10`, `status = succeeded`, 10 créditos). Pega a 1.ª transação em que o saldo da carteira
  **sobe**; o financiador é a conta (≠ carteira) com a maior queda de lamports nessa transação. O `funded-by` da Wallet API
  (100 créditos) serve só de validação. **Só conta financiamento com `block_time` < decisão**; caso contrário, fica "não
  resolvido".
- **Resolvida** = financiador encontrado e anterior à decisão. Denominador de `rede_financiadora_pct` = compradoras resolvidas.
- **`rede_financiadora_pct`** = (maior grupo de compradoras resolvidas com o mesmo financiador) ÷ (compradoras resolvidas).
  Financiador tipo casa de câmbio não conta. Um grupo de 1 não é "partilha": se o maior grupo tem 1, a variável é **0**.
- **Tipo casa de câmbio** (só se classifica o financiador que encabeça um grupo ≥ 2 em algum mint):
  - (i) a identidade Helius (`batch-identity`) o marca como exchange; **ou**
  - (ii) ele tem > 1 000 destinatários distintos de SOL enviado em `getTransfersByAddress` (`direction = out`, SOL, até 11
    páginas de 100), com a hora de corte do estudo.
  Esta é a letra do pré-registo ("> 1 000 carteiras financiadas").
- **`financiado_pelo_criador_pct`** (secundária, Holm) = fração das compradoras resolvidas (sem contar o próprio criador)
  cujo financiador é o criador **ou** o financiador do criador (1 salto).
- **Sem teto por mint** (desvio do brief, que sugeria ≤ 60): o método de 10 créditos resolve as 10 274 carteiras distintas
  (8 358 da população elegível, mais as das 95 decisões reais e 310 criadores) por cerca de 103 mil créditos. Com o `funded-by`
  seriam cerca de 1 milhão. Resolver todas elimina o viés de amostrar só as mais recentes.

### 0.3 Piloto no caso de origem (SIMFTR), antes de tudo o resto
- 78 compradoras pré-decisão e o criador, todas resolvidas pelo `getTransactionsForAddress`.
- Validação contra o `funded-by` em 12 carteiras (11 compradoras e o criador): **12/12 o mesmo financiador, no mesmo slot.**
- O criador `GsHF9Y…` foi financiado por `HxLcoP…` com 19,38 SOL, **1 s antes de criar a moeda** (slot 449833325; a criação
  foi no slot 449833327).
- **As 78 compradoras têm 77 financiadores distintos** (um único par partilha). Logo `rede_financiadora_pct(SIMFTR)` = 2/78 =
  **2,6 %**.
- Das 73 vendedoras do slot 449833635, 46 eram compradoras pré-decisão, **com 46 financiadores diferentes**. A maioria foi
  financiada meses antes (2025).
- **O despejo coordenado do caso de origem não aparece como rede de financiamento.** Isto fica registado antes de correr a
  população. Não muda o pré-registo (congelado): a hipótese é testada na população tal como foi escrita.

### 0.4 Contraste, patamar, cobertura, contrafactual
- **Desfecho principal:** PnL por SOL pela regra atual (1,15× / recuo 10 % / 300 s), custo 2,23 %, pouso gatilho + 1,6 s.
  Vem do `simulate_current` do R72, **nas duas vias**, pela letra "custo 2,23 %" do pré-registo.
- **Sensibilidade:** nas reais, o PnL realizado ÷ tamanho (desfecho do brief). Ele traz o custo histórico de cada posição,
  incluindo aluguel de ATA nas mais antigas.
- **Despejo coordenado:** ≥ 10 vendedoras distintas num mesmo slot, com `block_time` em [entrada, entrada + 300 s].
- **Tercis** de `rede_financiadora_pct` na população elegível, por posto. Empates na fronteira vão para o tercil de baixo, e a
  regra é a mesma nas duas fronteiras. Contraste `D = média(baixo) − média(alto)`: a previsão é `D ≥ +0,05`, com o IC 95 %
  inteiramente acima de 0. Bootstrap por mint, 10 000.
- **Moinho** (`run_hypothesis`, como no R73): só os tercis extremos; `direction = low`; limiar congelado = máximo do tercil de
  baixo; cluster = mint; estrato = dia; bloco = hora; semente 76; MRE 0,05. Grelha do patamar (quantis 0,20 / 0,25 / 0,33 /
  0,40 / 0,50 da variável) fixada antes de olhar desfechos.
- **Previsão (b):** taxa de despejo coordenado no tercil alto ≥ 2× a do baixo (Wilson + diferença com bootstrap por mint).
- **Refutação**, pela letra:
  - (a) o limite superior do IC de (alto − baixo) acima de −0,01, que no espelho é o limite inferior de D abaixo de +0,01;
  - (b) a curva é pico;
  - (c) o teto que bloqueia as piores mata > 30 % das vencedoras;
  - (d) cobertura < 60 %.
- **Família Holm:** {primária, secundária}.
- **Cobertura:** (compradoras resolvidas ÷ compradoras pré-decisão), no agregado e por mint (mediana e fração de mints ≥ 60 %).
  Abaixo de 60 % no agregado → **limite de dado**, antes de qualquer contraste.
- **Contrafactual:** as 95 decisões reais, cada uma no seu instante, com a variável medida mesmo sem fita desde o nascimento
  (marcado). Tetos {> 5, 10, 15, 20, 30 %} e criador {> 0, 5, 10 %}. "6 piores" = as 6 de menor PnL realizado. Cada teto
  reporta quais das 6 bloqueia e quantas vencedoras mata, com nome.

### 0.4b Emendas da revisão de desenho da Astra (`astra-review-R76.md`), aplicadas ANTES de resolver a população e de ver desfechos
1. **Financiador pela instrução, não pela maior queda de saldo.** Com várias transferências na mesma transação, a maior queda
   pode não ser a do remetente. O resolvedor passou a ler `jsonParsed` e a tomar o `source` da 1.ª instrução do System Program
   (`transfer`, `transferWithSeed`, `createAccount`, `createAccountWithSeed`) com destino na carteira. Conta a instrução externa
   ou interna, na ordem de execução. Não conta: fecho de conta, devolução de aluguel, SOL embrulhado. Sem instrução nas 10
   primeiras transações → `truncated`: não resolvida, **nunca** "sem financiador". O piloto foi refeito com este método.
   Validação contra o `funded-by` em 40 carteiras sorteadas (semente 76) mais as 12 do piloto: **50 de 51 concordam**. A
   discordância é `B5gQdQ`: o `funded-by` aponta uma entrada anterior vinda de um co-signatário ("FOMO Co-signer") que não passa
   pelo System Program. Houve ainda 1 `truncated`. Nas 117 resolvidas, a heurística antiga e a nova concordaram em 117.
2. **Casa de câmbio com corte temporal e "desconhecido".** Os destinatários contam só com `blockTime` < decisão **daquele**
   mint (`getTransfersByAddress`, `direction = out`, só SOL nativo, `solMode = separate`, até 15 páginas de 100). Três
   resultados:
   - mais de 1 000 distintos → casa de câmbio (regra operacional);
   - histórico esgotado com ≤ 1 000 → não é;
   - páginas acabaram antes → **desconhecido**.

   Principal: exclui só os comprovados, por identidade ou por > 1 000. Sensibilidades: (s1) excluir também os desconhecidos;
   (s2) excluir só por identidade. A identidade Helius é lida hoje e é uma **classificação retrospetiva**. A regra de > 1 000 é
   operacional e não prova que o financiador seja uma casa de câmbio: um distribuidor de golpe também passa de 1 000.
3. **Desfecho censurado sem cobertura até ao pouso.** O `simulate_current` exige a `resolvable` do R72 (≥ 3 trocas da fita na
   janela). Além disso, o **maior buraco do caminho entre a entrada e o pouso da saída simulada** tem de ser ≤ 60 s; se não
   for, o desfecho é censurado, não resolvido à força. Sensibilidades: ≤ 30 s e sem censura.
4. **Errata da cláusula (a) de refutação, escrita antes do contraste.** O texto congelado diz "limite superior do IC (alto −
   baixo) acima de −0,01". Isso dispara sempre que o IC **não confirma**: um IC de [−0,20, +0,10] aciona a cláusula mesmo
   admitindo um efeito forte a favor da tese. A refutação estatística seria o **limite inferior** de (alto − baixo) acima de
   −0,01, ou seja, o limite superior de D abaixo de +0,01. O relatório mostra as duas coisas: "aciona a cláusula literal" e
   "refutação sustentada pelo intervalo". **Regra de rótulo, fixada agora:**
   - `REFUTA` só se o intervalo sustentar a refutação, ou por (b) pico ou (c) matar > 30 % das vencedoras;
   - a cláusula literal (a) sozinha dá `NÃO CONFIRMA`;
   - a cobertura < 60 % dá `NÃO CONFIRMA` por limite de dado.

   O texto congelado da fila não é reescrito; a errata vai no veredito.
5. **Empates e partições.** Valores iguais ficam sempre juntos. Os tercis são de posto: os cortes são os quantis 1/3 e 2/3, o
   baixo é `≤ q1/3` e o alto é `> q2/3`. Publicam-se os tamanhos efetivos, e não se forçam três grupos. Se o baixo ou o alto
   ficar com < 20 mints, **não há contraste identificável** e isso é dito. Na curva de patamar, dois limiares só contam como
   vizinhos se produzirem **partições diferentes**; limiares que repetem a mesma partição colapsam num ponto.
6. **Também publicados** (sugestões da Astra):
   - `maior grupo ÷ todas as compradoras pré-decisão`, ao lado da métrica congelada;
   - a cobertura por mint de cada valor;
   - os cortes por via (real/papel) e por dia;
   - as fronteiras de 1 s (compra no mesmo segundo da decisão) contadas como ambíguas.

### 0.5 Proxy barato ao vivo (descritivo, fora do veredito)
Todas calculáveis pela fita WS do executor, sem RPC, no instante da decisão:
1. compradoras pré-decisão que ainda não venderam (nº e fração);
2. dispersão do tamanho das compras (CV) e fração de "pingos" (0,01–0,35 SOL);
3. tamanho do bloco do slot de criação (carteiras distintas e SOL);
4. compradoras com compra única sem venda.

Concordância com a medida de financiador: Spearman e AUC para o tercil alto. Associação com o despejo coordenado: AUC.


---

## 1. Resolução e cobertura (saída real de `r76/report.md` §1)

Resolução das 10 274 carteiras distintas: **10 075 com financiador** (98,1 %), 192 `truncated` mesmo com `limit = 100` e 7 sem
transferência do System Program. Houve 1 linha partida por escrita concorrente de cache; ela foi ignorada e a carteira voltou
a ser resolvida.

| recorte | mints | com fita desde o nascimento (R73) | compradoras pré-decisão | resolvidas antes da decisão | cobertura agregada | mediana por mint | mints ≥ 60 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| uma por mint (todas) | 591 | 291 | 32219 | 22150 | 68.7% | 97.5% | 368 de 533 |
| reais | 84 | 45 | 3994 | 3965 | 99.3% | 100.0% | 69 de 69 |
| papel | 507 | 246 | 28225 | 18185 | 64.4% | 95.9% | 299 de 464 |
| **elegíveis** | 291 | 291 | 14649 | 14350 | **98.0%** | 100.0% | 288 de 291 |

**A cláusula (d) de cobertura não dispara: 98,0 %.** A linha "todas" fica mais baixa porque o papel sem fita desde o nascimento
não foi resolvido (fora da população). Desfecho nas elegíveis:
- 272 resolvidos;
- 11 censurados por buraco > 60 s até ao pouso;
- 8 sem resolubilidade no R72.

Há 106 compradoras no mesmo segundo da decisão, de 14 649; são ambíguas e foram contadas.

Classificação dos 191 financiadores com ≥ 2 compradoras numa decisão:
- identidade Helius: 43 casas de câmbio centralizadas (Binance, OKX, Coinbase, Bybit…), mais pontes, casinos, apps de trading e
  "Authority" (FOMO Co-signer), que não foram marcados como câmbio;
- `getTransfersByAddress` nos 148 sem rótulo de câmbio:
  - 26 com > 1 000 destinatários antes do corte;
  - 38 com histórico esgotado ≤ 1 000;
  - **84 desconhecidos**: 15 páginas lidas sem passar de 1 000 nem esgotar, ou seja, remetentes que repetem muito os mesmos
    destinatários.

## 2. A variável e os casos de origem

`rede_financiadora_pct` nas 291 elegíveis: zeros 100 (34,4 %); q⅓ 0,0000, mediana 0,0364, q⅔ 0,0520, p90 0,1515, máx 0,8000.

| caso | via | fita nasce/reconcilia | compradoras | resolvidas | maior grupo | rede (congelada) | rede ÷ todas | s1 | s2 | criador | despejo (máx. vendedoras/slot) | PnL realizado |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| SIMFTR | live | True/False | 78 | 78 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | True (73) | -0.0283607920 |
| CITIZEN | live | False/False | 333 | 333 | 2 | 0.6% | 0.6% | 0.6% | 0.6% | 0.0% | True (154) | -0.0573418300 |
| WAVECOREE | live | True/True | 75 | 75 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | True (76) | -0.0368884810 |
| RHOS | live | False/False | 365 | 365 | 5 | 1.4% | 1.4% | 0.0% | 1.4% | 0.0% | True (262) | -0.0062708330 |

- No SIMFTR, o único par que partilhava financiador (2,6 % no piloto) é da **Binance Hot Wallet 2**. Excluída a casa de câmbio,
  a rede é **0**.
- O SIMFTR não entra na população principal: a fita dele não reconcilia com a foto.

## 3. Tercis — o contraste pré-registado

Os cortes são calculados na elegível inteira, **antes** de filtrar pelo desfecho. Esta é a correção da Astra: antes, a secundária
tinha 149/91; agora tem 149/89.

| recorte | n | baixo / alto | cortes | média baixo / alto | D (baixo − alto) | IC 95 % (mint) | despejo baixo vs alto |
|---|---:|---:|---|---|---:|---|---|
| **principal** (simulador, censura 60 s) | 272 | 91 / 91 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0427 / -0.0963 | **+0.0535** | [-0.0050, +0.1162] | 12/91 vs 8/91 |
| sem censura por buraco | 283 | 95 / 95 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0404 / -0.0948 | **+0.0544** | [-0.0037, +0.1129] | 12/95 vs 8/95 |
| censura ≤ 30 s | 264 | 88 / 86 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0469 / -0.0984 | **+0.0514** | [-0.0115, +0.1155] | 12/88 vs 8/86 |
| s1 (exclui desconhecidos) | 272 | 220 / 52 | ≤ q⅓ 0.0000 / > q⅔ 0.0000 | -0.0745 / -0.0509 | **-0.0236** | [-0.0810, +0.0350] | 29/220 vs 7/52 |
| s2 (só identidade) | 272 | 89 / 89 | ≤ q⅓ 0.0164 / > q⅔ 0.0556 | -0.0434 / -0.0875 | **+0.0441** | [-0.0172, +0.1071] | 12/89 vs 9/89 |
| maior grupo ÷ todas | 272 | 91 / 91 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0427 / -0.0963 | **+0.0535** | [-0.0066, +0.1153] | 12/91 vs 8/91 |
| só reais | 44 | — / — | — | — | — | sem potência | — |
| só reais, PnL realizado | 45 | — / — | — | — | — | sem potência | — |
| só papel | 228 | 75 / 76 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0396 / -0.1017 | **+0.0621** | [+0.0037, +0.1254] | 8/75 vs 5/76 |
| cobertura por mint ≥ 60 % | 270 | 89 / 91 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0442 / -0.0963 | **+0.0521** | [-0.0096, +0.1146] | 12/89 vs 8/91 |

Por dia, nenhum tem potência: o maior tem 51 mints.

**Moinho, primária** (saída real, `r76/report.md` §5):

- n = 182, em 182 clusters, 91 / 91.
- D = **+0.0535**.
- IC de cluster [−0.0050, +0.1162], P(D≤0) = 0.037.
- IC de blocos [−0.0042, +0.1141], em 113 blocos.
- p de permutação por dia 0.0830.

**VEREDITO: NÃO CONFIRMA.** Razões dadas pelo moinho:
- o IC inferior não fica acima de zero;
- p ≥ 0,05;
- **o braço baixo perde em nível (−0,0427)**;
- o IC por blocos cobre zero.

**Moinho, secundária** (`financiado_pelo_criador_pct`): n = 238, 149 / 89, D = **+0.0479**, IC [−0.0099, +0.1079], p perm
0.1042. **NÃO CONFIRMA.**

**Holm** {primária, secundária}: 0,166 / 0,166 → nenhuma sobrevive.

## 4. Despejo coordenado — a metade mecânica da previsão

| tercil | n | despejo coordenado [Wilson] | perda ≥ 50 % |
|---|---:|---|---:|
| baixo | 91 | 13.2% [7.7%–21.6%] | 3 |
| alto | 91 | 8.8% [4.5%–16.4%] | 5 |

Razão alto ÷ baixo = **0,67×**, contra os ≥ 2× previstos. Diferença alto − baixo −0,044, IC 95 % por mint [−0,135, +0,047]. A
AUC da própria rede para prever o despejo é 0,468.

**Mecanismo, descritivo** (`r76/dumpmech.out`):
- Nos maiores despejos (RHOS 262, KODA 224, CITIZEN 154, BIZZ 81, WAVECOREE 76, SIMFTR 73 vendedoras num slot), o maior grupo
  de financiador **entre as vendedoras resolvidas** vai de 1 a 4. As vendedoras têm financiadores distintos.
- O criador vende no mesmo slot em 10 dos 36 despejos da população e em 7 dos 16 das reais.
- O KODA foi uma **vencedora** com 224 vendedoras num slot.
- Há despejos com grupo partilhado: RUNPEPE 12/19, Rabbitson 15/26, YOU 14/18, NOOP 11/25. Nos três últimos, porém, o
  financiador comum é uma **casa de câmbio**: YOU tem 20 das 34 compradoras pré-decisão financiadas direto pela OKX Hot
  Wallet 1; Rabbitson, pela Binance e pela KuCoin; NOOP, pela Bybit e pela Binance.
- A medida pré-registada exclui esses casos por construção. **Rede sibila financiada por saque de casa de câmbio é invisível
  ao "primeiro financiador"**, e este é um limite da medida. Leitura da Astra, adotada: isto não prova ausência de
  coordenação, só que o financiamento comum não a captou.

## 5. Patamar

Grelha pedida: quantis [0,20, 0,25, 0,333, 0,40, 0,50]. Os empates colapsam-na em **3 partições distintas**: [0,0000, 0,0254,
0,0364].

| limiar (≤) | n sel | n resto | D (sel − resto) | IC 95 % |
|---:|---:|---:|---:|---|
| 0.0000 | 91 | 181 | +0.0409 | [-0.0107, +0.0926] |
| 0.0254 | 107 | 165 | +0.0503 | [-0.0009, +0.1016] |
| 0.0364 | 136 | 136 | +0.0310 | [-0.0197, +0.0830] |

**Três camadas, separadas, como a Astra exigiu:**

1. **Saída mecânica:** `plateau_or_spike` → **"pico"**. Ele pede 4 limiares positivos consecutivos, 2 deles com IC acima de 0.
2. **Por que não demonstra pico:** com 3 partições, esse classificador **não consegue** devolver "planalto". Qualquer resultado
   aqui sairia "pico". Os três D têm o mesmo sinal e tamanho parecido, que é o oposto de um pico isolado. Nenhum tem IC acima
   de zero.
3. **Interpretação adotada DEPOIS de correr** (declarada como tal, não como exceção pré-registada): pela definição do próprio
   pré-registo, "patamar em dois limiares vizinhos", os dois vizinhos do limiar congelado concordam em sinal. **Não trato a
   (b) como refutação.** Um leitor que aplique "pico do moinho → REFUTA" chegaria a REFUTA; fica escrito.

## 6. Contrafactual nas 95 decisões reais

Cada decisão foi medida no seu instante, com o PnL realizado. Os desconhecidos passam: o teto não os bloqueia. É supressão de
posições históricas, sem simular as oportunidades que o capital liberado abriria.

Base: 95 posições, 29 vencedoras, PnL **−0,3870 SOL**. As 6 piores:

| posição | PnL (SOL) | rede | fita nasce |
|---|---:|---:|---|
| `CITIZEN` | −0,0573 | 0,6 % | não |
| `AIRAA` | −0,0556 | 15,2 % | sim |
| `SNORP` | −0,0441 | 0 | sim |
| `YOU` | −0,0395 | 0 | sim |
| `WAVECOREE` | −0,0369 | 0 | sim |
| `SIMFTR` | −0,0284 | 0 | sim |

| regra | bloqueia | das 6 piores | vencedoras mortas | Δ PnL |
|---|---:|---|---|---:|
| rede > 5% | 23 | 1 ['AIRAA'] | 7 de 29 (24%) ['WIFTIGRINO', 'ANT', 'WEENY', 'DOGPHIL', 'RESERVED', 'SENTHOS', 'MMKT'] | +0.0441 |
| rede > 10% | 12 | 1 ['AIRAA'] | 3 de 29 (10%) ['ANT', 'WEENY', 'RESERVED'] | +0.0634 |
| rede > 15% | 4 | 1 ['AIRAA'] | 2 de 29 (7%) ['WEENY', 'RESERVED'] | +0.0317 |
| rede > 20% | 1 | 0 [] | 1 de 29 (3%) ['WEENY'] | -0.0207 |
| rede > 30% | 0 | 0 [] | 0 de 29 (0%) [] | +0.0000 |
| criador > 0% | 39 | 2 ['AIRAA', 'YOU'] | 14 de 29 (48%) ['WIFTIGRINO', 'NOOP', 'PROCK', 'ANT', 'WEENY', 'DOGPHIL', 'Aura', 'Paidichi', 'PHIL67', 'TANK', 'RIGBY', 'SENTHOS', 'MMKT', 'EDEN'] | +0.0945 |
| criador > 5% | 31 | 2 ['AIRAA', 'YOU'] | 11 de 29 (38%) ['WIFTIGRINO', 'NOOP', 'ANT', 'DOGPHIL', 'Aura', 'Paidichi', 'PHIL67', 'RIGBY', 'SENTHOS', 'MMKT', 'EDEN'] | +0.1067 |
| criador > 10% | 25 | 2 ['AIRAA', 'YOU'] | 9 de 29 (31%) ['WIFTIGRINO', 'NOOP', 'DOGPHIL', 'Aura', 'Paidichi', 'PHIL67', 'SENTHOS', 'MMKT', 'EDEN'] | +0.1035 |

Sem valor (nenhuma compradora resolvida): 15. Sem fita desde o nascimento: 46 de 95 (valores exploratórios).

- **Nenhum teto de rede bloqueia ≥ 3 das 6 piores**: no máximo 1, o AIRAA, cuja rede é de um financiador de classificação
  "desconhecida". A condição do contrafactual na previsão falha.
- A (c) de refutação ("o teto que bloqueia as piores mata > 30 %") **não dispara na primária**, porque nenhum teto bloqueia "as
  piores". Os tetos que bloqueiam o AIRAA matam 7 %–24 % das vencedoras.
- **Dispara na secundária**: o teto de criador bloqueia 2 das 6 e mata 31 %–48 %, incluindo SENTHOS e MMKT.
- **Rede > 10 %** daria +0,063 SOL em 95 posições, bloqueando 12 e matando ANT, WEENY e RESERVED. O grupo do WEENY é o **FOMO
  Co-signer**, uma "Authority" de um app de trading: são utilizadores do mesmo app, não um anel.

## 7. Exploratório (fora do veredito)

Fontes: `r76/explore.out` e `r76/dumpmech.out`.

- **Não é confusão com o número de compradoras.**
  - Com poucas compradoras (≤ 44): D(0 − >0) = +0,039 [−0,036, +0,115].
  - Com muitas: +0,061 [−0,011, +0,134].
  - Spearman(compradoras, rede) = −0,118.
- **O tercil alto é dominado por financiadores recorrentes entre moedas.** São 91 mints e 36 financiadores:
  - `H7sWT7eP` encabeça **29 mints**: sem rótulo, tag "Jup.ag User", 403 destinatários em 15 páginas sem esgotar;
  - o **FOMO Co-signer** encabeça 11;
  - um "Individual" do Pump.fun encabeça 7.

  O D não depende só deles: sem os dois primeiros, D(baixo − alto) = +0,048 [−0,018, +0,117]; só com eles, +0,061 [−0,019,
  +0,151]. O que a medida apanha é mais **frota/app que opera em muitas moedas** do que anel montado para uma moeda.
- **Sensibilidade decisiva:** s1 trata os 84 financiadores "desconhecidos" como serviço e **inverte o sinal** (D −0,024). O
  efeito depende de como se classifica quem repete transferências para os mesmos destinatários.

## 8. Proxy barato ao vivo — o que construir a seguir

| proxy | mediana | Spearman com rede | AUC tercil alto de rede | AUC despejo | AUC perda ≥ 50 % (sim) |
|---|---:|---:|---:|---:|---:|
| `p_buyers` | 44.000 | -0.092 | 0.305 | 0.515 | 0.409 |
| `p_holders` | 26.000 | -0.042 | 0.379 | 0.580 | 0.495 |
| `p_holders_frac` | 0.657 | +0.088 | 0.621 | 0.573 | 0.659 |
| `p_cv` | 1.248 | +0.122 | 0.559 | 0.463 | 0.478 |
| `p_drip_frac` | 0.472 | +0.130 | 0.557 | 0.352 | 0.419 |
| `p_bundle` | 2.000 | -0.104 | 0.444 | 0.641 | 0.519 |
| `p_bundle_sol` | 3.148 | +0.103 | 0.585 | 0.672 | 0.740 |
| `p_single_nosell_frac` | 0.606 | +0.030 | 0.588 | 0.569 | 0.614 |
| (a própria rede) | 0.036 | 1 | — | 0.468 | 0.581 |

IC por bootstrap (2 000):
- `p_bundle_sol` (SOL comprado no slot de criação): AUC despejo **0,675 [0,577, 0,762]**; AUC perda ≥ 50 % **0,740 [0,558,
  0,885]**, com só **12 perdas ≥ 50 %** em 272;
- `p_holders_frac`: perda ≥ 50 % 0,659 [0,524, 0,788].

**Recomendação:**
1. **Não construir** a medida de financiador (RPC por compradora) nem um proxy dela. Nenhum proxy da fita concorda com ela
   (|Spearman| ≤ 0,13), e ela própria não prevê o despejo.
2. O único sinal que aparece, de forma **exploratória**, é **quanto SOL entra no slot de criação**. Ele fica perto de variáveis
   já esgotadas (dev share e snipers, regra 1 da fila). Só volta com **medida nova numa população nova**, pré-registada e com
   ganho incremental sobre dev share e snipers.
3. **A `0062` sozinha não basta** (achado da Astra, verificado em `decision_tape.py`): a fatia gravada não tem `slot` e guarda só
   as trocas recentes do minuto. Uma decisão aos 120 s já não tem a compra de criação. É preciso **instrumentar primeiro**:
   gravar no derivado o agregado do slot de criação (SOL do criador no `create`, nº de carteiras e SOL no mesmo slot), com o
   instante em que ficou conhecido.

## 9. Veredito (cláusula a cláusula)

| peça do pré-registo | resultado | estado |
|---|---|---|
| previsão: D ≥ +0,05 com IC inteiro > 0 | D +0,0535, IC [−0,0050, +0,1162] | falha (IC cruza zero; braço baixo perde em nível) |
| previsão: despejo alto ≥ 2× baixo | 0,67×, dif. [−0,135, +0,047] | falha (sentido oposto) |
| previsão: patamar em dois vizinhos | D +0,041 / +0,050 / +0,031, todos com IC cruzando 0 | sinal concordante, sem significância |
| previsão: teto bloqueia ≥ 3 das 6 piores, mata ≤ 20 % | máximo 1 (AIRAA) | falha |
| refutação (a) literal | limite superior de (alto − baixo) = +0,0050 > −0,01 | **dispara**. Pela errata, só não-confirma; o intervalo **não** refuta (limite superior de D = +0,116 ≫ +0,01) |
| refutação (b) | "pico" mecânico, insuficiente com 3 partições | não tratada como refutação (§5, interpretação pós-execução) |
| refutação (c) | primária: nenhum teto bloqueia as piores; secundária: 31–48 % | não na primária; **sim na secundária** |
| refutação (d) cobertura | 98,0 % | não dispara |

**H-014: `NÃO CONFIRMA`.** A medida de primeiro financiador comum não sustentou a previsão. O efeito sobre o retorno aponta no
sentido da tese, é pequeno demais para o erro que tem, inverte com a classificação dos financiadores desconhecidos e não passa
pelo mecanismo do despejo. **Nenhum braço de papel. Nenhum parâmetro de mesa.**

## Chamadas e créditos Helius (registados em `r76/calls_*.jsonl`)

| método | chamadas | créditos/chamada | créditos |
|---|---:|---:|---:|
| `getTransactionsForAddress` (limit 10) | 10 354 | 10 | 103 540 |
| `getTransactionsForAddress` (limit 100, refeitas) | 553 | 10 | 5 530 |
| Wallet API `funded-by` (validação) | 52 | 100 | 5 200 |
| Wallet API `batch-identity` | 2 | 100 | 200 |
| `getTransfersByAddress` | 1 733 | 10 | 17 330 |
| **total registado** | **12 694** | | **131 800** |

- Não registado: um lote sequencial interrompido para paralelizar (≤ 500 chamadas, ≤ 5 000 créditos) e 1 chamada de
  diagnóstico.
- **0 HTTP 429 e 0 erros.** Ritmo: 4 trabalhadores a ≤ 2,5 req/s cada, perto de 1,4 req/s efetivos por trabalhador.
- A chave nunca foi impressa nem copiada; o `.env` nunca foi lido.
- Um processo órfão do lote interrompido foi terminado dentro do contêiner, pelo `cmdline` exato `python -`; o processo
  `python -m hunter_meme_worker` não foi tocado.

## Segunda opinião (Astra)

**Desenho, antes de correr** (`.claude/state/astra-review-R76.md`). 5 must-fix, todos aplicados antes de resolver a população
(§0.4b):
1. financiador pela instrução, não pela maior queda de saldo;
2. câmbio com corte por decisão e estado "desconhecido";
3. censura do desfecho por buraco até ao pouso;
4. errata da cláusula (a);
5. empates e partições distintas.

Também aplicados: cobertura por mint, `pct_all` e cortes por via e por dia.

**Veredito** (`.claude/state/astra-review-R76-veredito.md`). Ela reproduziu a primária exatamente (D 0,05353, IC [−0,00502,
+0,11618], despejo 12/8) e confirmou 13 testes. Os must-fix:
1. **(b):** publicar separadas a saída mecânica, a insuficiência dela e a interpretação pós-execução. Aplicado (§5). O texto diz
   explicitamente que outra leitura daria REFUTA.
2. **Cortes antes de filtrar o desfecho.** Aplicado, com teste novo. A secundária mudou de 149/91 (D +0,0448) para **149/89 (D
   +0,0479, IC [−0,0099, +0,1079])**, que bate com a reprodução dela. O ponto intermédio do patamar mudou de +0,0463 para
   +0,0503. A primária não mudou.
3. **A `0062` não mede o bundle de criação.** Aceite. A recomendação passou a pedir instrumentação primeiro.

Nice-to-have aplicados: IC por bootstrap da diferença das taxas de despejo e legenda do corte alto (q⅔). **Rejeitado:** nada.
Ela concorda com não construir a medida nem o proxy. A redação "não sustentou" em vez de "não existe" foi adotada.

## Arquivos

`.claude/state/r76/`:
- carregador, montagem e relatório: `q.sh`, `q_*.sql`, `resolver_tpl.py`, `resolve.py`, `load.py`, `build.py`, `run.py`,
  `report.py`;
- exploratório: `explore.py`, `dumpmech.py`;
- testes: `test_load.py` (13 testes);
- dados e saídas: `pop.csv`, `tape.csv`, `snap.csv`, caches `cache_*.jsonl`, `rows.json`, `report.md`, `explore.out`,
  `dumpmech.out`.

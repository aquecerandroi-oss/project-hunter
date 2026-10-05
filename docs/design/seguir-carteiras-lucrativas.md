---
status: proposta (aguarda aprovação do Everton)
data: 2026-10-05
dono: quant-engineer
tipo: arquitetural (subsistema novo; nada implementado)
pre_registro: .claude/state/carteiras-lucro/PREREG.md (rascunho H-030; não está na Fila)
obsidian: obsidian/11-KNOWLEDGE/KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes.md
revisao_astra: obsidian/06-DECISIONS/Revisoes-Astra/carteiras-lucro-design.md (REQUEST_CHANGES → 9 must-fix absorvidos)
---

# Seguir quem ganha dinheiro de verdade (pump.fun + PumpSwap), primeiro em papel

> Pedido do Everton (05/10/2026): "pesquise e começamos a seguir quem faz dinheiro de verdade no mercado".
> Este documento é **desenho + pré-registro**, não implementação. Antes da aprovação não se escreve código, não se cria
> tabela e não se usa RPC pago novo. Dinheiro real fica fora do escopo.

## 0. O que já sabemos (e o que isso muda no desenho)

| Nota | Achado | O que muda aqui |
|---|---|---|
| KB-0136 (R57, 72 h de fita) | Os vencedores **persistem**: ρ ≈ 0,6, e o top-30 de um dia fez +79,6 SOL no dia seguinte. Mas o lucro deles é **velocidade e pacote**. Metade segura 1–13 s; 16 % das compras caem no bloco do `create`; 43 % dos sinais são gêmeas do mesmo operador. Copiar 3 s depois dá 1,01×; 20 s depois, 0,96×; o R empata com o controle aleatório. Única fresta: segurar 15 min sem stop deu ΔR +0,18, com o IC tocando 0. A fita cobria 5 % dos mints, com 26 s de atraso | Ranquear pelo que **nós** teríamos ganho copiando com o nosso atraso, não pelo lucro deles. Filtrar quem segura pouco. Fundir gêmeas. Usar o feed de evento com 100 % de cobertura |
| KB-0142 (R61) | O selo KOL do site chega **no pico**; comprar 20 s depois dá R −0,071 | Seguidores são a liquidez de saída. Fama não entra no critério |
| KB-0138, KB-0141 (R58, R60) | Rajada de compradores: 54/54 células negativas. Sniper de lançamento: 18/18 negativas | Quem lucra no bloco do `create` fica fora por construção |
| KB-0124, KB-0134 + **medição de 05/10** | WS `confirmed` p50 0,58 s. Nas 62 compras reais com fita (24–26/09), do slot do trade que disparou a decisão ao slot do nosso pouso: **p50 3,5 slots, p75 5, p90 12,3** (≈ 1,4 s / 2 s / 5 s). Da proposta à confirmação: p50 1,65 s, p90 3,9 s (143 compras) | **Cenário-base de 5 slots** (p75; não é garantia, não cobre a cauda nem o coletor novo). **Estresse com 13 slots** |
| KB-0149 §1/§5, KB-0171, KB-0148 | Curva: 2,23 %/operação sem aluguel. PumpSwap: 1,20 %/perna. Rede: ≈ 50 000 lamports/perna (KB-0171 mede **spot/1**, n = 10, outra população). Look-ahead "mente com convicção" | Taxas pelos bps do próprio evento. Rede de 50 000/perna como base, com sensibilidade a 100 000. Aluguel de ATA como sensibilidade |
| T4.8e-upgrade-02-10, T4.8e-decoders | O feed de evento está **cego desde 02/10 15:47Z** (a última fita de decisão na VPS é das 15:47:18Z) até o deploy do conserto. O worker aplica eventos de **outro mint** da mesma tx (achado 2 da Astra, aberto) | Nada começa antes do deploy da T4.8e e de 24 h sem `undecodable`. O coletor atribui cada evento ao **mint do próprio evento** |
| Código existente | `meme_wallet_trades`/`positions` (`0027`) só leem `MEME_WATCH_WALLETS`, por *polling* de 30 s, e estão **vazias na VPS** (0/0, 05/10). O portão de evento assina **por mint jovem** e guarda 60 s. `meme_trades` é a fita `swap_api`: ~450 mil trades/dia em ~1 400 mints, contra ~45 mil criações/dia | Nada disso vê a população inteira. Precisamos de um coletor **do programa inteiro**. O polling por carteira serve para auditar a cobertura, não para copiar |

## 1. O que é "dinheiro de verdade"

**O exemplo do Everton.** A conta "sadcrissy" foi criada em 01/10 e tem 6 934 seguidores. Num dia ela marcou +US$ 144 mil:
**US$ 19 mil realizados** e **US$ 125 mil não realizados**, com só US$ 3 050 de compras. Ou seja, 87 % do ganho é
marcação na última cotação. Para virar dinheiro, o saco teria de ser vendido contra a própria curva ou pool. Uma
venda desse tamanho derruba o preço que gerou a marcação. Conta nova com muitos seguidores sugere criador ou
influenciador: os seguidores são a saída (KB-0142). **Pelas medidas abaixo, conta no máximo a parte realizada, e só
líquida do custo desses tokens.** O endereço completo está pendente; a auditoria cabe na onda 0.

**Unidade e janela.** A unidade é a **entidade**: uma carteira ou um grupo ligado (§1.2), na versão conhecida no
corte. A janela é móvel de 7 dias e termina no corte econômico do dia D (00:00 UTC). Tudo é medido em lamports
inteiros e `Decimal`. São três medidas, **que não se misturam**:

1. **W-PnL realizado (descritivo).** Σ SOL recebido em vendas − SOL pago em compras, casados por FIFO por mint, nos lotes
   vendidos na janela. Desconta as taxas que o evento declara e 5 000 lamports por tx. Um lote comprado antes da
   janela vale **se** o custo estiver preservado em `meme_wallet_lots` (§2.2). Sem custo conhecido, o episódio fica
   **incompleto**: não ganha custo zero nem some.
2. **E-PnL econômico (elegibilidade).** É o W-PnL **mais a variação do valor de liquidação do inventário aberto**
   entre o início e o fim da janela. Liquidação = venda simulada da quantidade inteira contra as reservas válidas no
   corte (§3.1), com o teto de SOL real da curva aplicado. Um mint sem estado válido vale **0**. Como é variação
   entre duas fotos, a perda de um saco entra **uma vez** e não volta a ser descontada quando a venda real acontece.
   A marcação na última cotação **nunca** entra. O inventário é o líquido *negociado*: transferências não são swaps.
   Uma venda sem compra observada fica `unmatched` e fora. Se mais de 20 % dos tokens vendidos pela entidade forem
   `unmatched`, a **contabilidade é incompleta** e a entidade não é elegível.
3. **C-PnL copiável (ranking).** É a **mesma política do §3** (mesmo motor, mesmo atraso, mesmo stop e mesmo teto de
   60 min) aplicada a cada compra-gatilho da entidade na janela, como se nós a tivéssemos seguido. Um saco que ela
   segura no prejuízo fecha para nós pelo stop ou pelo tempo, então a perda aberta dela entra no C-PnL. Só conta a
   cópia simulada **cujo desfecho inteiro**, incluindo o slot de pouso da saída usado no pior preço, termina antes do
   corte, com todos os eventos `received_at` < corte.

**Elegível no dia D** = passa todos os itens abaixo. **Seguidas** = as **30** primeiras por C-PnL, com desempate pelo
hash do id da entidade.

- **Atividade:** ≥ 20 episódios fechados não neutros (|resultado| ≥ 1 % do custo), em ≥ 15 mints e em ≥ 4 dos 7 dias.
- **Dinheiro de verdade:** E-PnL ≥ +2 SOL. Dias com E-PnL > 0 ≥ 4/7. Queda máxima do E-PnL acumulado diário ≤ max(1
  SOL; 50 % do E-PnL). O maior episódio ≤ 50 % do E-PnL.
- **Copiável:** C-PnL > 0 a 5 slots.
- **Tempo de posse (filtro de primeira classe):** mediana ≥ **60 s** e fração com posse < 10 s ≤ 25 %. A mediana de
  60 s é 12× o nosso p90 de pouso. O R57 mostrou que abaixo disso o ganho é consumido antes de chegarmos.

### 1.1 Exclusões: do ranking (histórico) e da aposta (causal)

| Exclusão | No ranking (só com dados < corte) | Na aposta para frente |
|---|---|---|
| Criador | Episódio num mint criado pela entidade, ou por quem a financiou (1 salto), sai. Se for > 20 % dos episódios, a entidade sai | Gatilho num mint criado pela entidade (o `CreateEvent` é conhecido antes) **não abre** aposta |
| Bloco do `create` | Compra até 2 slots depois do `create`: episódio fora. Se for > 30 % dos episódios, a entidade sai (é sniper) | Gatilho até 2 slots depois do `create` não abre aposta |
| MEV / arbitragem | Compra e venda separadas por ≤ 2 slots: episódio fora | **Nada retroativo.** Se a seguida vender 1 slot depois, a aposta já disparou e fica, com a perda que tiver |
| Robô de volume | > 500 trades num dia → fora **nos retratos seguintes** | Usa a contagem do **dia anterior**, nunca o total final do dia |
| Isca de copiador | Compra, espera a fila e despeja: W-PnL alto e C-PnL negativo. Sai pelo C-PnL | — |
| Lavagem | Gêmeas fundidas, trocas entre elas se anulam. Episódio neutro não conta para a atividade | — |

### 1.2 Entidades, versionadas pelo que se sabia no corte

As carteiras se unem (*union-find*) por **ligação forte** ou por **ligação fraca**:

- **Forte:** o mesmo financiador na primeira entrada de SOL, desde que não seja casa de câmbio nem app. Método do R76:
  `getTransactionsForAddress` ascendente, ≈ 10 créditos por carteira, conferido 12/12 contra `funded-by` (KB-0156).
  A carteira quente da OKX e o *co-signer* de app financiam milhares de pessoas e não ligam ninguém.
- **Fraca:** compra do mesmo mint no mesmo slot em ≥ 3 mints distintos.

As ligações valem a partir do retrato publicado depois de conhecidas. Uma coincidência vista amanhã não funde nada
hoje. O financiador só é consultado para candidatas: no máximo **300 carteiras/dia** (as melhores por C-PnL antes da
fusão), ≈ 3 000 créditos/dia. Sem resolução, a carteira fica sozinha, com a marca correspondente. **Sensibilidade
pré-declarada:** o resultado com só as ligações fortes, mais o tamanho dos grupos publicado. Uma entidade abre
**uma** aposta por mint.

## 2. Caminho do dado, a 100 % de cobertura

**Pré-condição:** a T4.8e implantada e 24 h de feed sem `undecodable`.

- **Coletor `wallet-tape`.** Fica no pacote do meme-worker, num **contêiner próprio** (`MEME_WALLET_TAPE=off|on`),
  porque a infra é estratégia (KB-0149 §4) e o radar não pode cair junto. Faz `logsSubscribe` (`mentions`) no programa
  pump (`6EF8…`) e no PumpSwap (`pAMMBay6…`), em `confirmed`. Decodifica `CreateEvent`, `TradeEvent` (com a cauda da
  T4.8e) e `BuyEvent`/`SellEvent` da PumpSwap. O `BuyEvent` **não tem decodificador hoje**: é a onda 1a.
  `logsSubscribe` entrega os logs da tx que menciona o programa, não fills normalizados. Por isso a identidade de cada
  evento é `(signature, programa, ordinal do evento na tx)`. A mesma tx vista pelas duas assinaturas conta **uma** vez,
  e cada evento vai para o **seu** mint ou pool, nunca para o da assinatura. Pool → mint vem de
  `meme_tokens.migrated_pool`, ou de `getAccountInfo` com cache.
- **Volume:** de madrugada, só na curva, o R60 mediu 114 832 trades/h; à tarde, o R58 mediu ≈ 170 mil/h. Isso dá
  **3–4 M/dia na curva**, mais a PumpSwap (**não medida**). Há 559 935 notificações/h, das quais 70 % são tx falhas
  (descartadas). A onda 0 mede os números reais.
- **Cobertura por episódio, não só por dia.** Reconexão, fila cheia ou `undecodable` vira lacuna com slots. Hoje
  `meme_ingest_gaps` tem `stream`/`gap_start`/`gap_end`/`detail` e **não tem slot**: a onda 1b decide entre colunas
  novas e uma convenção (`stream = 'wallet_tape:<programa>'`, slots em `detail`). Uma aposta (`follow` ou
  `control`) ou um episódio de ranking cujo intervalo [gatilho, saída] cruza lacuna fica **contaminado** (§4). A
  **auditoria diária** compara o `getSignaturesForAddress` com o que o feed gravou para 20 seguidas, 10 controles e 10
  carteiras fora do topo, sorteadas.
- **Viés declarado das lacunas:** venda perdida deixa o saco aberto, e ele vai para a liquidação (pessimista). Compra
  perdida gera venda `unmatched`, que fica fora.

### 2.1 Ranking no ponto do tempo: três instantes

1. **Corte econômico** `T_D` = D 00:00 UTC. Só entram episódios e cópias simuladas cujo desfecho completo termina
   antes de `T_D`.
2. **Disponibilidade:** só entram eventos com `received_at` < `T_D` e ligações conhecidas até `T_D`. Um trade
   recuperado às 03:00 fica **fora** do retrato de D.
3. **Publicação:** o retrato de D é gravado uma vez, imutável, com `published_at`. A decisão no instante *t* lê o
   retrato **mais recente com `published_at` ≤ *t***. Entre 00:00 e a publicação vale o de D−1.

Testes obrigatórios no motor puro:

- Nenhum trade com `block_time` ≥ `T_D` **ou** `received_at` ≥ `T_D` muda o retrato de D.
- Uma estratégia "trapaça" que lê o retrato de D antes de `published_at` (ou o do próprio dia) é **pega** pelo teste de
  vazamento.
- Um evento com `received_at` posterior ao pouso teórico **não** gera compra retroativa.

### 2.2 Tabelas (migração nova, globais e sem RLS como a `0021`/`0027`: dado público de cadeia)

| Tabela | Conteúdo | Retenção |
|---|---|---|
| `meme_wallet_fills` | Um evento por linha: `block_time`, `slot`, `signature`, `program`, `event_ordinal`, `wallet`, `mint`, `venue`, `side`, `sol_lamports`, `token_amount`, `fee_lamports`, reservas pós-trade, `received_at` | **9 dias** (7 + 2 de margem), partição **diária**, podada só depois da marca de sucesso do job noturno. A ferramenta de partição hoje é só mensal: estendê-la é decisão do database-architect |
| `meme_wallet_lots` | Lotes FIFO abertos por (carteira, mint): quantidade, custo, origem. **Sobrevive à poda** e permite retomar após reinício | Enquanto aberto + 60 dias |
| `meme_wallet_episodes` | Episódio (entidade, mint): abertura, fechamento ou corte, posse, W-PnL, cópia simulada a 5 e a 13 slots, exclusões, `contaminated` | 60 dias |
| `meme_wallet_links` | Carteira → entidade, tipo de ligação, financiador, `known_at` | Sem poda |
| `meme_wallet_rank_snapshots` | (D, entidade): métricas do §1, motivo de exclusão, posto, `followed`, cobertura e **manifesto** (hash do código, parâmetros, contagem de insumos), `published_at`. Só acréscimo | Sem poda (~1 k linhas/dia) |
| `meme_wallet_follow_bets` | Aposta: braço, entidade, gatilho (assinatura, slot, `received_at`), `snapshot_id`, entrada, saída, motivo, SOL líquido, R, atraso, `contaminated`, `pair_id` | Sem poda |
| `meme_wallet_fills_kept` | Eventos dos mints apostados (do `create` até a saída + 60 min) **e** os episódios que puseram cada seguida no top-30 | Até o veredito + 90 dias |

**Por que tabela nova:** `meme_trades` é mensal, com retenção de 30 dias (`settings.py:125`), e tem consumidores que
filtram `swap_api`. Nela, a fita do programa pesaria 31–63 GB e misturaria fontes. `meme_wallet_trades` é o livro
**do Everton** e não se mistura com a população.

**Custo na VPS compartilhada (hipótese de ~350 B/linha com índices, a medir na onda 0):** 3–6 M linhas/dia dão
**1,05–2,10 GB/dia**, ou **9,5–19 GB** com 9 dias. Some WAL, `lots`, `fills_kept` e margem. CPU baixa (50–100
eventos/s úteis, mais as notificações descartadas). Rede de entrada ~1–2 Mbit/s. O banco tem 88 GB hoje e o disco
tinha 207 G livres em 30/09 (`docs/design/retencao-e-disco-2026-09-27.md`). A proposta é deixar `meme_wallet_fills`
**fora do dump noturno**; uma restauração grava lacuna explícita e não finge continuidade. Helius: ≈ 3 000
créditos/dia (financiadores), mais ≤ 300 `getTokenAccountsByOwner`/dia para conferir o inventário das candidatas. **WS:** o
RPC público serve para a sondagem, mas a própria Solana diz que os endpoints públicos não são para produção. Rodar
24/7 deve exigir o WS da Helius, cuja cobrança para o programa inteiro é **desconhecida** e depende do Everton.

## 3. A regra de seguir, em papel (replay causal noturno, braço `research_only`)

A aposta é **função pura do feed gravado**. Um job noturno roda D−1 às 02:00 UTC com o mesmo motor que um laço vivo
usaria: `hunter_indicators.meme.wallets`, sem IO e sem relógio, com o contexto trazendo o retrato vigente e os
eventos em ordem de slot. O nome certo é **"replay causal em coorte futura"**: ele testa a hipótese sob um modelo de
execução, mas não prova que o sistema executa. Isso é a onda 5.

- **Gatilho:** a primeira compra ≥ 0,1 SOL de uma entidade seguida num mint, fora da janela do `create`, com
  `received_at` + 0,4 s (decisão) ≤ o instante do slot de pouso. No máximo **20 apostas por entidade por dia** (as 20
  primeiras, regra causal de admissão) e uma aposta por mint a cada 30 min.
- **Entrada:** no slot do gatilho + **5**, com 0,05 SOL.
- **Saída:** a primeira a acontecer, sempre pousando 5 slots depois do disparo. (a) A entidade passa de 50 % vendido
  do que comprou no mint. (b) **Stop:** a cotação de venda dos nossos tokens cai a ≤ 50 % do custo. (c) **Tempo:** 60
  min. Drenagens de 70 % num bloco acontecem (KB-0149 item 7), então o stop pousa no preço que houver.
- **R** = (múltiplo líquido − 1) ÷ 0,5 (régua EXP-M14/M15). O aluguel de ATA é tratado como depósito recuperado − 5 000
  lamports; a sensibilidade usa aluguel perdido (+1,86 %).

### 3.1 Contrato de preço

- **Slot de pouso com trades:** pior preço entre antes e depois de **todos** os trades do slot. É convenção adversa,
  usada só para resolver o fill, nunca para decidir.
- **Slot sem trades:** reservas do último evento com slot ≤ pouso. A curva não muda sem trade. **Nunca** o próximo
  trade.
- **Pool:** vale o mesmo, mas uma adição ou retirada de liquidez sem swap muda reservas sem evento de trade. Se a onda
  0 mostrar que isso ocorre nas pools apostadas, o pouso exige o estado da conta (`getAccountInfo` no slot não existe
  historicamente) ou a aposta fica **censurada**.
- **Migração (curva completa):** a cotação da curva deixa de ser executável. A posição segue no pool **decodificado**.
  Sem evento decodificável do pool, a aposta é **censurada** e entra no primário com **R = −1** (limite inferior), com
  sensibilidade no primeiro preço do pool.
- `quote_buy`/`quote_sell` (`hunter_indicators.meme.curve`) só são reutilizados com **o teto de SOL real sempre
  passado** (`curve.py:292` permite omiti-lo). A PumpSwap ganha cotação própria. O `net_proceeds` do `SellEvent`
  (`sell_event.py:94`) já é líquido de taxa, então **não** se desconta de novo. Fixtures reais provam semântica,
  arredondamento e conservação de lamports.

### 3.2 Controles

- **Controle 1 (H2, primário):** entidades que passam **todos** os filtros de elegibilidade, mas ficam **fora do
  top-30** (postos 31+). Responde "ordenar por C-PnL acrescenta algo?". Com menos de 10 entidades assim no dia, H2
  fica **sem suporte comparável** naquele dia (publicado).
- **Controle 2 (descritivo, sem teste):** entidades ativas, não elegíveis, que passam atividade, posse e exclusões.
  Responde "a política inteira supera copiar qualquer um ativo?".
- **Pareamento:** gatilho no mesmo minuto (±60 s), outro mint, mesma praça, mesma faixa de idade (< 5 min, 5–60 min, >
  60 min) e mesmo tercil de SOL real na curva **antes** do gatilho. Sorteio com semente fixa, sem reposição, desempate
  pelo hash da assinatura, controle nunca reutilizado. O controle não precisa vender nem ter trajetória completa: a
  mecânica é a mesma. Aposta `follow` sem par fica em H1 e sai de H2; a cobertura do pareamento é publicada.

## 4. Pré-registro

Texto completo em `.claude/state/carteiras-lucro/PREREG.md` (bloco H-030 no formato da Fila, **não** inserido).
Resumo:

- **Coorte só para frente.** Começa no primeiro 00:00 UTC depois do congelamento **e** de 7 dias completos de feed
  coberto.
- **Primário:** R líquido médio do `follow` a 5 slots.
- **Hipóteses (Holm):** H1, R médio > 0; H2, Δ pareado contra o Controle 1 > 0. Efeito mínimo relevante **+0,05 R**
  nas duas.
- **Inferência:** erro-padrão com cluster **em duas vias, dia × entidade** (Cameron–Gelbach–Miller), com t de G−1
  graus, G = min(dias, entidades). Robustez com o bootstrap *pigeonhole*.
- **Amostra:** alvo de 4 500 apostas; piso de 2 000 com ≥ 14 dias; teto de 28 dias. Leitura única.
- **Potência declarada:** com SD 1,2 R independente, 2 000 detectam ≈ 0,075 R e 4 500 detectam 0,05 R. O cluster
  piora as duas contas.
- **Previsão honesta: NÃO CONFIRMA ou REFUTA.** O R57, a 3 s, deu +0,03 contra −0,04.

## 5. O que o advogado-de-jesus vai atacar, e a guarda

| Ataque | Guarda |
|---|---|
| Sobrevivência ("vencedores" são os que sobraram) | Toda carteira vista entra no ranking. O E-PnL inclui a variação de liquidação dos sacos. O desfecho é das **nossas** apostas para frente, inclusive nas entidades que quebraram depois de seguidas |
| Ranking com informação futura | Três instantes (§2.1), retrato imutável com `published_at`, ligações com `known_at`, exclusões causais (§1.1), `snapshot_id` em cada aposta. A estratégia trapaça é pega pelo teste |
| Gêmeas inflando a amostra | Fusão forte e fraca. Uma aposta por mint. Teto causal de 20 apostas por entidade por dia. Cluster por entidade. Sensibilidade só com ligações fortes |
| Liquidez de saída | Saímos **depois** da venda deles, nas reservas reais. Os sacos entram pela liquidação. A fila de copiadores mais rápidos já está no preço do slot +5 |
| Capacidade no nosso tamanho | Estresse com 0,25 SOL. Fração das apostas em que a nossa compra passa de 1 % do SOL real da curva. A capacidade sai como número publicado |
| Sorte de período | Teto de 28 dias, cluster por dia, tirar um dia por vez. É **um regime só**, e isso fica declarado |
| Cauda | O CONFIRMA exige média > 0 sem o 1 % maior e sem a maior entidade |
| Custo irreal | Bps do evento, rede a 50 000 e a 100 000 lamports, aluguel como sensibilidade, atraso de 5 e de 13 slots |
| Cobertura falsa ou episódio contaminado | Lacuna por slot e por episódio. Auditoria diária em seguidas, controles e fora do topo. O CONFIRMA exige contaminadas ≤ 2 % **e** que o resultado se mantenha com as contaminadas a R = −1 |
| Caminhos bifurcados | Família declarada: R57, R61, E2-b (EXP-M9), H-010, H-014, H-015. Limiares congelados antes do aquecimento. Mudar qualquer um = id novo, em dado novo |

## 6. Plano em ondas (só depois da aprovação)

| Onda | Tarefa | Files | Depends-on | Quem |
|---|---|---|---|---|
| 0 | Sondagem de 2 h do programa inteiro (pump + PumpSwap, RPC público). Mede eventos/s, bytes/s, decode, reconexões, carteiras/dia, GB/dia, tx com os dois programas, liquidez de pool sem swap. Inclui a auditoria da "sadcrissy" | `infra/scripts/research/2026-10-xx-wallet-tape-probe.py` | deploy T4.8e | exchange-integration + quant |
| 1a | `BuyEvent` da PumpSwap + leitor `logsSubscribe` do programa inteiro, com identidade e atribuição por evento e fixtures reais | `packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py`, `.../pumpfun/program_logs.py`, `packages/exchange-adapters/tests/unit/test_program_logs*.py` | 0 | exchange-integration |
| 1b | Migração das 7 tabelas, partição diária, retenção com marca de sucesso, lacuna com slot, exclusão do dump | `infra/migrations/versions/00xx_meme_wallet_tape.py`, `infra/migrations/ddl/meme_wallet_tape.py`, `packages/core/hunter_core/db/models/meme_wallet_tape.py`, `infra/scripts/partition_*.py`, `docs/DATABASE.md` | 0 | database-architect |
| 1c | Motor puro: lotes FIFO, E-PnL de liquidação, entidades versionadas, métricas, `follow`/`control` como `evaluate` puro, contrato de preço do §3.1, testes sintéticos com valor esperado, os três testes de vazamento do §2.1 e a trapaça | `packages/indicators/hunter_indicators/meme/wallets/*.py`, `packages/indicators/tests/meme/test_wallets_*.py` | nenhum | quant-engineer |
| 2 | Coletor `wallet-tape` (eventos, lacunas, batimento de cobertura) + serviço no compose | `services/meme-worker/hunter_meme_worker/wallet_tape*.py`, `infra/docker/docker-compose.yml`, `infra/vps/*` | 1a, 1b | backend + devops |
| 3 | Jobs noturnos: lotes e episódios, financiadores (≤ 300/dia), retrato + manifesto, apostas e pares, `fills_kept`, auditoria de cobertura, linha no diário | `services/meme-worker/hunter_meme_worker/wallet_rank*.py`, `infra/scripts/meme_diary_*.py` | 1c, 2 | backend + quant |
| 4 | Aquecimento de 7 dias, em que **ninguém olha desfecho** (só cobertura, contagem de elegíveis e atraso do feed) → coorte → leitura única + advogado/defensor → veredito na Fila e na EXP | `obsidian/05-EXPERIMENTS/EXP-M15-*.md`, Fila | 3 | quant + Sexta-feira |
| 5 | **Só com CONFIRMA:** braço vivo `research_only` proposta → Risk Engine, sem dinheiro, para medir o atraso real. Depois disso, o Everton decide | a desenhar | 4 | risk-guardian + backend |

**Esforço:** ~1,5–2 semanas de agentes nas ondas 0–3, mais 7 dias de aquecimento e 14–28 dias de coorte. O veredito
mais cedo sai **~4–6 semanas depois da aprovação**. **Portão de nascimento:** com menos de 30 entidades elegíveis no 7.º
dia, o experimento **não nasce**, e isso fica registrado. Não se afrouxa limiar.

## 7. O que precisa do Everton

1. **Aprovar este desenho:** subsistema novo, migração nova, contêiner novo.
2. **Disco:** ~10–20 GB para a fita bruta de 9 dias, e `meme_wallet_fills` **fora** do backup noturno.
3. **RPC:** a sondagem roda no público. Para rodar 24/7, o WS da Helius (cobrança **desconhecida** para o programa
   inteiro), ≈ 3 000 créditos/dia de financiadores e ≤ 300 leituras de saldo/dia. Tudo isso é uso pago do plano.
4. O **endereço completo** da "sadcrissy".
5. Ciência de que **dinheiro real está fora do escopo**: um CONFIRMA abre só a onda 5 (papel vivo).

## Fontes

Obsidian: KB-0136, KB-0142, KB-0138, KB-0141, KB-0124, KB-0134, KB-0149, KB-0171, KB-0148, KB-0156, EXP-M15,
T4.8e-upgrade-02-10, T4.8e-decoders, KB-0182 (síntese desta pesquisa). Estado: `.claude/state/notes-R57.md`, `notes-R60.md`,
`notes-R76.md`. Consultas só leitura de 05/10: `.claude/state/carteiras-lucro/q1.sql`–`q4.sql`. Revisão: Astra
`.claude/state/astra-review-carteiras-lucro-design.md` → `obsidian/06-DECISIONS/Revisoes-Astra/carteiras-lucro-design.md`.
Externas: Solana, `logsSubscribe` e clusters (https://solana.com/docs/rpc/websocket/logssubscribe,
https://solana.com/docs/references/clusters); Cameron & Miller, *A Practitioner's Guide to Cluster-Robust Inference*
(JHR 2015).

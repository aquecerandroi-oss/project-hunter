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
2. **E-PnL econômico (elegibilidade).** *(Errata de 05/10, onda 1c, revisão da Astra `wallets-engine`.)* É o
   **caixa casado da janela mais o valor de liquidação do inventário no fim menos o do início**:
   E = Σ vendas casadas − Σ compras + V(fim) − V(início). Lido como "W-PnL FIFO + variação da liquidação", um saco
   comprado por 1 que vale 0,2 daria +0,2. A fórmula acima equivale ao realizado contra a base "custo, se comprado na
   janela; liquidação no início, se já estava aberto". Liquidação = venda simulada da quantidade inteira contra as
   reservas válidas na fronteira (§3.1), com o teto de SOL real aplicado, e a **mesma regra vale em toda fronteira**,
   de modo que os dias somam a janela. Um mint sem estado válido vale **0** no fim; no **início**, um lote preservado
   sem estado válido deixa o episódio **incompleto**, porque 0 ali transformaria a venda posterior em ganho puro.
   Como é variação entre duas fotos, a perda de um saco entra **uma vez** e não volta a ser descontada quando a venda
   real acontece.
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
  Sem evento decodificável do pool, a aposta é **censurada** e entra no primário com **R = −1**. Isso é uma
  **imputação pré-registrada, não um limite inferior**: a perda total da ficha é R = −2. Sensibilidades: o primeiro
  preço do pool, e as censuradas a **R = −2** (o CONFIRMA também tem de se manter assim).
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

## 8. Onda 0 — medição (05/10/2026)

> Acrescentada em 05/10/2026 pelo `exchange-integration-specialist`. **Substitui, para volume, disco e RPC, os números de
> §2 e §7** (3–6 M linhas/dia, 9,5–19 GB, "cobrança desconhecida"); o resto do desenho não muda. Revisão da Astra (duas
> rodadas): [[wallet-tape-probe]] (`obsidian/06-DECISIONS/Revisoes-Astra/wallet-tape-probe.md`). Síntese de conhecimento:
> [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]]. Avaliação datada: [[EXP-M15-carteiras-vencedoras]].

**O que foi medido.** Sondagem de leitura desta máquina (não da VPS), RPC **público** `api.mainnet-beta.solana.com`, uma
conexão `logsSubscribe` (`mentions` = o programa, `confirmed`) por programa, os decodificadores **commitados** (T4.8e) e
nenhuma transação enviada. Script `infra/scripts/research/2026-10-05-wallet-tape-probe.py` (+ `infra/scripts/wallet_tape_probe_*.py`,
40 testes offline), leitura reproduzível com `…/2026-10-05-wallet-tape-probe-read.py --run <dir>`; saídas em
`.claude/state/carteiras-lucro/probe/{run1,run2,run3}/`. **Não é uma corrida contínua de 2 h**, e isto precisa ficar escrito:

| Corrida | Início (UTC) | Janela válida | O que é |
|---|---|---|---|
| run 1 | 19:03:16 | **90,1 min** (5 408 s) | A máquina **dormiu 4 651 s** logo depois (o resumo final tem relógio de parede corrompido: os contadores abaixo vêm do snapshot 90, antes do salto). A auditoria de blocos desta corrida julgava no instante do fetch, o que confunde **atraso** com **perda** |
| run 2 | 22:01:47 | **39,1 min** limpos | Com a auditoria independente corrigida (julgamento 180 s depois do fetch) e `--keep-awake` |
| run 3 | 22:46:42 | **15,0 min** limpos | Sem auditoria; mede concentração de carteiras e tamanho dos swaps |

Total válido: **144 min** em três janelas e dois horários, **não** 2 h contínuas. Um regime só: segunda-feira, 05/10/2026, das 16h às 20h BRT.

### 8.1 Resultado em quatro linhas

1. **RPC público: NO-GO para 24/7.** Na run 1 (19:03Z) a conexão da PumpSwap caiu **60 vezes** em 90 min (a do pump, 19),
   na maioria por *keepalive ping timeout* do servidor, o atraso contra a ponta HTTP chegou a **p50 112 slots** (≈ 30 s) e ela
   entregou ~43 % do que a cadeia produziu. Na run 2 e na run 3 (a partir de 22:01Z) **0 quedas** e atraso p50 de 0 slots. Uma
   janela ruim em três basta para não pôr o coletor nisto; a causa (horário, rota, balanceador) **não** está isolada.
2. **Volume: 28–31 milhões de eventos de swap por dia** (330–353/s entregues; 31 M/dia pela contagem dos blocos), **5 a 10 vezes** a hipótese de §2. Em bytes,
   **217–254 GB/dia** de WS sem compressão (pump 37–42 GB, PumpSwap 180–212 GB).
3. **Armazenamento como aprovado (10–20 GB de fita): NO-GO.** A linha estimada em **529 B** com três índices (278 B só de
   heap; estimativa por tipo de coluna, **não** tabela medida) dá **15–17 GB/dia** e **136–149 GB em 9 dias** (a 350 B: 90–99 GB). Cabe
   no papel nos 207 G livres de 30/09, mas sem margem para WAL, `lots`, `fills_kept` e crescimento.
4. **Helius: GO para o piloto pago**, com custo estimado de **US$ 650–760/mês** (§8.4). **Go para as ondas 1a e 1c**;
   **ondas 1b e 2 seguram** até o Everton escolher o formato/retenção (§8.5).

### 8.2 Fluxo, decodificação e cobertura

| | pump (`6EF8…`) | PumpSwap (`pAMM…`) |
|---|---|---|
| Notificações/s, run 2 (run 3) | 315 (396) | 822 (1 064) |
| Transações falhas | 74 % (78 %) | 42 % (48 %) |
| Bytes por notificação | 1 366 | 2 538 |
| MB/s sem compressão, run 2 (run 3) | 0,43 (0,49) | 2,09 (2,45) |
| Eventos de swap/s, run 2 | `TradeEvent` 61 | `SellEvent` 150 + `BuyEvent` 118 (**cru**) |
| Picos por segundo (run 2) | p99 126, máx 352 | p99 494, **máx 817** |

- **Decodificação:** 0 falhas em 143 170 `TradeEvent` e 352 242 `SellEvent` (run 2) e em 335 365 / 377 536 (run 1): os
  decodificadores da T4.8e leem o layout de 02/10 em escala. O **`BuyEvent` da PumpSwap é 36 % dos eventos de swap** e ainda
  não tem decodificador: a onda 1a deixa de ser opcional. A carteira e a pool dele, lidas por deslocamento (120/152), batem com as contas 0 e 1
  da instrução `buy` em três compras reais (uma roteada); o IDL não está fixado por hash.
- **Eventos sem IDL:** pump `742b4dbd117a482b` (~0,4/s, 1 931 na run 1) e `a943276d6686b6e8`; PumpSwap `82a42461e48287a5`
  (702 na run 1). Contados crus, nunca interpretados.
- **Fidelidade dos logs:** 1 099 de 1 099 transações amostradas por `getTransaction` têm **a mesma contagem de eventos** nos
  logs e nas inner instructions, e `context.slot` = slot da transação em todas (delta 0). É contagem, não identidade de payload (onda 1a).
- **Cobertura independente (run 2):** `getBlock` de 75 slots escolhidos sem olhar o websocket, cada bloco julgado ≥ 180 s depois
  do fetch (exceto ~5 no fim, julgados mais cedo, e 1 censurado): **pump 6 314 de 6 320 menções entregues, PumpSwap 17 373 de 17 373**; as 6 que
  faltaram são transações falhas. No instante do fetch, 6 361/6 367 e 17 715/17 715. Isso vale para **39 min de um horário**, não para 24/7.
- **Tx em que o pump e a PumpSwap aparecem juntos:** 2 440 de 2 708 893 únicas (0,09 %; 0,19 % das que invocam ao menos um programa) na run 2; **53 % das
  transações únicas vistas só *mencionam* um programa e não o invocam** (custo de banda sem evento). Na run 2, 2 408 de 2 408 tx esperadas nas duas assinaturas
  chegaram nas duas; na run 1, 5 465 de 10 775.
- **Liquidez de pool sem swap** (contagem de instruções): run 2, em 39 min: `CreatePool` 126 (3,2/min), `Withdraw` 107 (2,7/min), `Deposit` 7
  (0,2/min); 230 tx com liquidez e **sem** swap contra 10 com swap. 106 dos 107 `Withdraw` e os 7 `Deposit` são de pools que também fizeram swap na
  janela (heurística: o endereço da pool aparece no payload). São ~0,03 % dos eventos, mas até 3,4 % das pools ativas tiveram retirada em 39 min (107 `Withdraw` em 3 158 pools): a regra de §3.1 (estado da conta ou **censura**) vale e custa pouco em volume.
- **Concentração (run 3, 15 min, 73 235 carteiras):** 58 % das carteiras fizeram **1** swap (13 % dos eventos); 3 135 carteiras (4 %) com ≥ 20 swaps
  fazem 46 % dos eventos; 8 carteiras com ≥ 500 swaps fazem 5 %. Dos swaps decodificados, **29 % valem < 0,01 SOL** e 14 % valem ≥ 10 SOL.
- **Carteiras distintas** (união de `TradeEvent`, `SellEvent` e `BuyEvent` com carteira inferida): run 2, 54 mil em 10 min e **121 mil em 39 min**; run 1
  (feed degradado) 157 mil em 90 min. Cenários por dia (um horário, **não** limites): Heaps 0,9–1,8 M; linear 1,7–5,3 M; sem novas 0,07–0,16 M. A curva
  é o resultado; a ordem de grandeza é de **milhão por dia**.

### 8.3 Atraso e queda do RPC público (run 1 contra run 2)

Atraso medido contra `getSlot(confirmed)` por HTTP menos o **maior** slot recebido (o `slotSubscribe` vai pelo mesmo cano e não vê o atraso), por janela de 10 min na
run 1: pump p50 3–69 slots, PumpSwap p50 18–112 (p90 até 218). Com 268 ms/slot (§8.6), 112 slots ≈ 30 s. O carimbo de hora do evento (relógio da cadeia, ±1 s) confirma:
p50 de 6 s no pump e 13 s na PumpSwap na run 1, contra 1,5 s nas duas na run 2. A fila local não foi o gargalo: idade na fila p99 0 s, 16 % de um núcleo.
Silêncios > 3 s: 22 por programa na run 1 (máx 24 s, PumpSwap); 1 na run 2 (6 s). HTTP: 55 respostas `413` em ~3 000 chamadas na run 1 (1,8 %), nenhuma na run 2.

### 8.4 Custo estimado da Helius (24/7, programa inteiro)

**Estimativa de 05/10/2026**, a partir das páginas públicas da Helius lidas hoje (https://www.helius.dev/docs/billing/credits e https://www.helius.dev/pricing): *LaserStream WSS* (métodos
padrão do Solana, todos os planos) cobra **2 créditos por 0,1 MB de dados transmitidos, sem compressão** (≈ 20 000 créditos/GB). Planos: Developer US$ 49 (10 M), **Business US$ 499 (100 M)**,
Professional US$ 999 (200 M); créditos extras US$ 5 por milhão nos pagos. Com 217–254 GB/dia: **4,3–5,1 M créditos/dia = 130–152 M/mês** → Business + 30–52 M extras = **≈ US$ 650–760/mês**
(ou Professional a US$ 999 com folga). Sem contar HTTP (≈ 3 000 créditos/dia de financiadores, ≤ 300 leituras/dia) nem recuperação de lacunas. O plano gratuito (1 M) acabaria em ~5 h.
**Hipótese não medida:** um filtro no servidor só para transações com sucesso (gRPC com `failed = false`, Business+; ou o `transactionSubscribe` da Helius) cortaria ~51 % das notificações (≈ 47 % dos bytes, se proporcionais):
≈ 114 GB/dia = 68 M créditos/mês, dentro do Business sem extras. O tamanho do payload dessas interfaces não foi medido.

### 8.5 Decisão (go/no-go)

| Item | Decisão | Por quê |
|---|---|---|
| RPC público para 24/7 | **NO-GO** | 1 de 3 janelas degradou (60 + 19 quedas, até ~30 s de atraso); sem SLA; a Solana diz que não é para produção |
| WS pago (Helius) | **GO para um piloto** de pelo menos um ciclo diário, no ambiente final | O Everton autorizou o plano pago. O piloto mede cobertura, atraso, reconexão, **custo faturado** e escrita real; não dá para atribuir a degradação ao provedor ou à rota sem ele |
| Onda 1a (`BuyEvent` + leitor `logsSubscribe` do programa inteiro) | **GO** | `BuyEvent` = 36 % dos swaps; identidade `(assinatura, programa, ordinal)` e atribuição ao mint do evento já estão provadas na leitura |
| Onda 1c (motor puro) | **GO** | Independe do formato de armazenamento |
| Onda 1b (7 tabelas, partição diária, 9 dias) e onda 2 | **SEGURAR** | O volume é 5–10× o aprovado e a linha física não foi medida. Decisão do Everton/database-architect entre: (a) retenção de 2–3 dias da fita bruta (≈ 45–50 GB a 529 B), (b) agregar no ingresso (lotes e estado por carteira) e guardar bruto só de carteiras candidatas, (c) formato colunar fora do Postgres, (d) mais disco. Um filtro por tamanho ou por atividade não deve ser aplicado antes de provar que não apaga compras e vendas que o E-PnL precisa |

### 8.6 Achados laterais (fora do escopo, registrados)

- **O slot dura ≈ 268 ms hoje** (3,73 slots/s; mediana de 224 amostras de 60 s de `getRecentPerformanceSamples`), não 400 ms. As conversões "5 slots ≈ 2 s" de §0 e do KB-0182 valem ≈ **1,34 s**.
  O desenho define o atraso em **slots**, e isso se mantém; as frases em segundos precisam ser relidas (a medição dos 62 pousos de 24–26/09 pode ter sido feita com outra duração de slot, que não consta).
- **Transação versão 1:** `getBlock`/`getTransaction` com `maxSupportedTransactionVersion = 0` recusam a resposta (`-32015`) quando o bloco tem tx v1 (147 de 1 104 num bloco amostrado, 13 %). `tx_rpc.py:191` e `rpc_wallet.py:82` usam `0`.
  Evidência em `.claude/state/carteiras-lucro/probe/side-findings-v1-tx-and-slot-time.json`; a sondagem usa `1`. Registrado em [[Open Bugs]].
- **Auditoria do exemplo "sadcrissy": não feita** — o endereço completo não está no repositório nem nas notas (§7, item 4).

### 8.7 O que a medição não vê

Um regime, um dia, dois horários; RPC público sem garantia de entrega (a cobertura de 39 min não é cobertura de 24/7); eventos truncados em logs longos (0 na medida, mas a contagem só vê
o que o servidor entregou); WAL, escrita real no Postgres, RSS, cache de resolução de pool, recuperação de lacunas e períodos de reserva de pool inválida (**não medidos**); identidade do payload do evento (só contagem);
a linha de 529 B é uma fórmula por tipo de coluna, não uma tabela medida. Limitações do instrumento reconhecidas na revisão: a deduplicação de 60 s da run 1 e 2 pode ter contado de novo uma entrega muito atrasada
(janela depois subida para 300 s; nas corridas limpas nenhuma tx esperada nas duas assinaturas chegou só em uma, então não há cópia tardia a duplicar); na run 2 o fechamento julgou cedo ~5 blocos (conservador: só podia somar perdas, e não somou).

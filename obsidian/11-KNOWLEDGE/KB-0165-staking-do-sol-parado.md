---
tags: [knowledge, nota, staking, solana, tesouraria, meme]
tema: Staking do SOL parado na carteira de trading (nativo vs. líquido)
fonte: Documentação oficial da Solana (staking, stake accounts); Jito Foundation (JitoSOL FAQ, auditorias); Marinade Finance (FAQ do protocolo); Staking Rewards (painel de mercado); Coin Bureau (comparativo de pools, 2026); código e docs do próprio repositório (`docs/RISK_ENGINE_MEME.md`, `services/meme-executor`)
fonte_url: https://solana.com/docs/references/staking/stake-accounts · https://www.jito.network/docs/jitosol/faqs/general-faqs/ · https://jito-foundation.gitbook.io/mev/resources/audits · https://docs.marinade.finance/marinade-protocol/faq · https://www.stakingrewards.com/asset/solana/analytics · https://coinbureau.com/analysis/best-solana-staking-pools · https://sanctum.so/blog/solana-staking-risks
lido_em: 2026-09-27
evidencia: documentação oficial dos protocolos + painel de mercado (Staking Rewards, Coin Bureau) — sem estudo revisado; alguns números vêm de agregador, não de fonte primária (marcado abaixo)
hipotese_testavel: não
astra: concorda com correções (4 must-fix aceitos: checagem wallet_unrecognized_holdings não alimentada, taxa de resgate da Jito, mínimo de saque da mSOL, época e rent invertidos)
status: curada
owner: sexta-feira
updated: 2026-10-01
confiança: "?"
tipo: leitura
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: cripto
---

# Staking do SOL parado — vale render o saldo ocioso da carteira de trading?

Pesquisa somente leitura, sem mover fundos e sem pedir chave, pedida por Everton em 27/09/2026:
o saldo hoje é **0,3845 SOL** ([[09-OPERATIONS/Diario/2026-09-26|Diário 26/09]]), acima do piso da
tesouraria (`MEME_TREASURY_SOL_FLOOR = 0,30`, `docs/RISK_ENGINE_MEME.md` §16.1) e sem nenhuma
posição aberta. Nenhuma estratégia de entrada confirmou até hoje
([[2026-09-26-mesa-meme-real-pausada-no-escopo]]).

## 1. Nativo vs. líquido — o que muda no relógio

**Staking nativo** (delegar a um validador via *stake account*): ativação e desativação só
acontecem em **limite de época** (*epoch boundary*), nunca no meio da época. Uma época na Solana são
432 000 slots; no máximo teórico de 400 ms/slot isso dá **2 dias** (432 000 × 0,4 s ÷ 86 400 s = 2 —
conferido por aritmética direta), e é esse o número a citar, não 2,5. Ativar leva uma época até
começar a render; **desativar** (unstake) exige esperar o fim da época corrente mais o início da
seguinte — normalmente **1 época (≈ 2 dias)**, mas **não é um prazo garantido**: a própria doc da
Solana diz que a duração exata "é difícil de prever" porque depende do comportamento de outros
participantes da rede, e pode esticar se a rede limitar quanto do stake total desativa ao mesmo
tempo (solana.com/docs/references/staking/stake-accounts, lido 27/09/2026).

**Staking líquido (LST — *liquid staking token*)** resolve o relógio trocando SOL por um token
(JitoSOL, mSOL, ...) que representa a posição staked e sobe de valor em SOL com o tempo. Nenhuma das
duas rotas abaixo é "instantânea e sem contrapartida" — cada uma troca taxa por tempo, ou tempo por
risco de preço:
- **Resgate direto pelo próprio protocolo** — ainda espera o cooldown de época (até ~2 dias), só que
  sem passar pela sua própria stake account. Jito cobra **0,1% sobre o valor resgatado** por esse
  caminho (jito.network/docs, lido 27/09/2026; correção desta nota — a taxa de 0,1% da Jito **não**
  é da rota instantânea, é do resgate direto que ainda espera a época). Marinade Native tem o
  equivalente com taxa dinâmica de **0,10% a 0,40%** (docs.marinade.finance/marinade-protocol/faq).
- **Saída instantânea de verdade** é vender o LST numa DEX (Jupiter, Orca) — sem taxa de protocolo,
  mas sujeita ao **preço de mercado e à profundidade da pool** no momento (*slippage*), que é
  justamente o que aperta quando o mercado está estressado (ver risco de depeg, §3).
- **mSOL tem ainda uma saída "atrasada" própria**, mais barata (**0,2%**, espera de 1 época), mas
  com um **mínimo de 1,0043 SOL** por operação (docs.marinade.finance, lido 27/09/2026) — **acima do
  saldo inteiro desta carteira hoje**, então essa rota simplesmente não está disponível no tamanho
  discutido aqui.

## 2. APY atual e o que o move

Números de **27/09/2026** (agregador de mercado, não é tarifa contratual — pode variar dia a dia):

| | valor | fonte / data |
|---|---|---|
| Taxa de recompensa da rede (staking nativo, média 30 d) | **≈ 5,02%** | stakingrewards.com/asset/solana/analytics, lido 27/09/2026 |
| Inflação atual (média 30 d) | **≈ 3,65%** (outras leituras de 2026 citam 4,3–4,7%; a série de inflação é pública e determinística, o que varia é a janela de cálculo) | idem; segunda leitura via calculadora Helius (data exata não confirmada) |
| APY mediano de validador (staking nativo) | citado como **≈ 6,7%** em abril/2026 | Helius (citação secundária, não conferida na fonte primária) |
| JitoSOL — APY médio de oferta | **≈ 4,85%** | stakingrewards.com, snapshot 21/09/2026 |
| mSOL — APY médio de oferta | **≈ 5,4%** (painel tipo DefiLlama) / **5,95%** (stakingrewards.com "live") | ambos snapshot ≈ 21/09/2026 — a divergência entre os dois é do próprio mercado, não erro de leitura |

**O que determina o número:**
1. **Inflação programada** — a Solana nasceu com 8% ao ano (2021), caindo ≈ 15% ao ano até um piso
   de longo prazo de **1,5%** (schedule documentado, não uma promessa de mercado). É a maior parte
   da recompensa e **cai todo ano por desenho**, independente de qualquer protocolo de staking.
2. **MEV/priority fees dos validadores Jito-client** — hoje cerca de **94–95% do stake** roda um
   cliente compatível com Jito (early 2026, citação secundária), então captar tip de MEV deixou de
   ser exceção. Uma análise citada (Figment, sem data exata confirmada) mostra ganho bruto de
   ≈ 7,34% para validador não-Jito contra ≈ 7,76% para Jito-client, **antes de comissão** — a
   diferença é pequena e não é garantida por protocolo, é resultado de mercado.
3. **Comissão do validador / taxa do pool** — reduz o que sobra para quem delega; nos LSTs isso
   aparece embutido no "fee" do protocolo (§3).

**Leitura prática:** staking nativo e staking líquido rendem, hoje, **na mesma faixa** (5% a 7%
ao ano); a diferença de alguns décimos de ponto entre eles não paga a complexidade adicional de um
protocolo terceiro para um saldo deste tamanho (§7).

## 3. Taxas de protocolo

- **JitoSOL:** **4% de taxa de gestão sobre as recompensas** (não sobre o principal) + 0,1% se sacar
  pela pool própria (0% se vender em DEX, mas aí entra slippage). Auditorias públicas por OtterSec e
  Neodyme (jito-foundation.gitbook.io/mev/resources/audits, lido 27/09/2026).
- **Marinade / mSOL:** 0% de depósito; 0,2% na saída atrasada (mSOL); saída instantânea sem taxa de
  protocolo (mas com slippage de DEX); Marinade Native cobra 0,10–0,40% dinâmico só na saída
  instantânea. Fontes secundárias citam ≈ 6% de comissão do protocolo embutida no rendimento — não
  encontrei essa comissão declarada com esse número exato na doc oficial consultada; tratar como
  não confirmado.

## 4. Riscos

- **Contrato inteligente:** qualquer LST é um programa on-chain (stake pool) — Jito tem auditorias
  publicadas (OtterSec, Neodyme); a Marinade também mantém página própria de auditorias. Auditoria
  reduz mas não zera risco de bug ou exploit; é risco adicional que staking nativo (sem programa
  intermediário) não tem.
- **Depeg do LST vs. SOL:** o preço de mercado de um LST pode negociar abaixo do seu valor de
  resgate em SOL durante estresse — mSOL teve um depeg breve relatado em dezembro de 2023 (fonte
  secundária, não documentação oficial da Marinade; citado aqui como anedótico, não como estatística
  verificada). O mecanismo é geral a qualquer LST: resgate ao par depende de arbitragem e de
  liquidez de saída, que é exatamente o que aperta em pânico de mercado.
- **Slashing:** **não existe hoje** na Solana — não há penalidade de protocolo que queime o
  principal por má conduta do validador. Dois SIMDs em andamento (SIMD-0204: registra evidência
  on-chain de conduta punível, sem penalidade; SIMD-0212: proposta de fórmula de penalidade, ainda
  em discussão da comunidade, **não finalizada**) podem mudar isso no futuro, mas hoje o pior que um
  validador ruim faz é render menos, não confiscar o saldo (sanctum.so/blog/solana-staking-risks,
  lido 27/09/2026).
- **Liquidez para sair:** saída instantânea depende da profundidade da pool do protocolo ou da
  liquidez de mercado (Jupiter/Orca) no momento — pode ter slippage relevante justamente durante
  estresse, o mesmo momento em que o depeg aperta. Staking nativo não tem esse risco porque não tem
  mercado secundário: só tem o relógio da época.

## 5. Impacto operacional no nosso sistema (verificado no código/docs deste repositório)

- **A chave só existe num lugar.** `services/meme-executor/` é "o único processo que lê
  `SOLANA_WALLET_SECRET_KEY`" (`docs/RISK_ENGINE_MEME.md` §3.3, linha ~1720). Nenhum outro serviço
  assina por esta carteira.
- **A carteira foi desenhada para um uso só, mas a proteção contra token estranho está no papel, não
  no código.** §3.2 do mesmo documento promete: "Uma carteira, um uso... não guarda nada além de SOL
  e das posições que este motor abriu", com uma checagem dedicada —
  `wallet_unrecognized_holdings` (`packages/risk-core/hunter_risk_meme/checks_wallet.py:53`) — que
  recusaria entradas se a carteira tivesse um token não reconhecido. **Conferido no código:**
  `wallet_from()` recebe esse dado por um parâmetro `unrecognized` que **default para tupla vazia**
  (`admission.py:261`), e os três lugares que montam a carteira para decidir uma entrada —
  `entries.py:170`, `launch_entries.py:203`, `spot_entries.py:198` — **nunca passam esse argumento**.
  Ou seja: hoje **nada lê os *holdings* reais da carteira além de SOL e das posições próprias**, e a
  checagem nunca dispara na prática, para LST ou para qualquer outro token. Um LST não travaria a
  mesa (ponto a favor de quem for stakar), mas também **não seria detectado por nenhuma proteção
  existente** se caísse ali por engano ou fosse depositado por outra via — ele só ficaria fora da
  contagem de `equity_sol`/`available_sol` (abaixo), silenciosamente. Achado à parte, fora do escopo
  desta nota: a lacuna entre o que `docs/RISK_ENGINE_MEME.md` §3.2 promete e o que o código faz vale
  um item próprio de acompanhamento.
- **O saldo de SOL é lido só pela chamada `getBalance` da RPC** (`services/meme-executor/hunter_meme_executor/chain.py:136`,
  usada por `admission.py:272` para montar `sol_balance`). Essa chamada só enxerga SOL nativo — um
  LST (SPL token, outra conta) não aparece ali. `MemeWalletState.equity_sol` é
  `sol_balance + Σ mark_sol das posições abertas` (`packages/risk-core/hunter_risk_meme/inputs.py:199`);
  um LST não é uma "posição" no sentido do motor (não tem `mark_sol`), então não entra nessa soma de
  jeito nenhum. Converter parte do saldo em LST faria `sol_balance`, `equity_sol`, `available_sol` e
  `sol_by_wallet_cap` **caírem** exatamente pelo valor convertido — a mesma aritmética que mede a
  perda do dia (`daily_loss_sol`, `inputs.py:229`, `= day_start_equity + treasury_inflow − equity`)
  contabilizaria essa conversão **como se fosse perda**, não como SOL que só mudou de forma.
- **A tesouraria já usa esse saldo como piso operacional.** `MEME_TREASURY_SOL_FLOOR` (padrão 0,30)
  é o gatilho que decidiria repor SOL na carteira (`treasury_once`, §16.1) — hoje **desligado por
  padrão** (`MEME_TREASURY_ENABLED = false`). O saldo atual (0,3845) já é pouco folgado acima desse
  piso; tirar uma fração para staking reduz essa folga.
- **Nenhum código hoje sabe stakar ou destakar.** Fazer isso exigiria ou (a) uma transação manual
  avulsa assinada com a chave de produção — fora do pipeline AGENT→PROPOSTA→RISCO→EXECUÇÃO porque
  staking não é uma ordem de trading, mas ainda é mover dinheiro real com a chave que hoje só
  compra/vende memes — ou (b) código novo dentro do `meme-executor` para stakar sobra e destakar sob
  demanda, o que amplia a superfície do único processo com poder de assinatura, exatamente o oposto
  do princípio "uma carteira, um uso" que o próprio motor de risco defende.

## 6. O que só o Everton decide

Dinheiro real entrando num protocolo externo que este projeto não audita nem controla; assinar
qualquer transação com a chave de produção; aceitar risco de contrato inteligente, depeg ou de uma
futura mudança de slashing; mudar a política de `MEME_TREASURY_SOL_FLOOR`/`MEME_WALLET_MAX_SOL`; e a
própria transação de stake/unstake. Esta nota **não recomenda enviar fundos** e **não pede chave** —
só organiza o que se sabe para a decisão dele.

## 7. Recomendação

Sobre o **saldo inteiro** (0,33–0,38 SOL), a **5–7% ao ano** (nativo ou líquido, a faixa é
praticamente a mesma hoje), o rendimento esperado é **≈ 0,017 a 0,027 SOL/ano** — maior que o rent de
uma única ATA que a mesa de memes já paga e recupera por posição (0,00203928 SOL,
`packages/risk-core/hunter_risk_meme/limits.py:191`), mas ainda poucos dólares por ano no preço de
SOL de hoje. E esse número superestima o que de fato sobraria: `MEME_TREASURY_SOL_FLOOR` (0,30 SOL)
é o piso que o próprio sistema já trata como "não mexer" — mesmo com a tesouraria hoje desligada, é
prudente preservá-lo como reserva operacional. Sobre o que passa disso (**≈ 0,03 a 0,08 SOL**), o
rendimento cai para **≈ 0,0015 a 0,0056 SOL/ano** — essencialmente irrelevante, e antes de descontar
qualquer custo de movimentação (rede, possível slippage na saída). É um valor pequeno demais para
justificar:

- introduzir um ativo novo (LST) numa carteira desenhada para segurar só SOL e posições que o motor
  abriu, cuja contagem de risco (`equity_sol`, `available_sol`, perda do dia) ignora esse ativo por
  completo hoje (§5) — sem travar nada, mas também sem enxergar o que aconteceu com o dinheiro;
- expor a única chave de assinatura de produção a uma transação a mais, manual ou via código novo;
- aceitar o atrito do relógio de época (nativo) ou a taxa/slippage de saída (líquido) bem no momento
  em que a tesouraria e o kill switch podem querer todo o SOL líquido e contável.

**Recomendação: não stakar** (nem nativo, nem líquido) o SOL ocioso desta carteira enquanto nenhuma
estratégia estiver confirmada e o saldo permanecer nesta ordem de grandeza. Reabrir a discussão só
se (i) o saldo ocioso crescer o bastante para o rendimento anual deixar de ser desprezível, **ou**
(ii) o `meme-executor` ganhar deliberadamente uma sub-carteira de reserva/tesouraria separada da
carteira de trading, desenhada desde o início para segurar um ativo diferente de SOL — decisão de
produto do Everton, não um ajuste encaixado na carteira atual.

## Segunda opinião (Astra)

Consultada via `infra/scripts/astra.sh ask staking-sol-parado` em 27/09/2026 (opinião, somente
leitura). Concordância no essencial: manter o SOL líquido nesta carteira é a recomendação correta, e
ela confirmou de forma independente que `getBalance` só lê SOL nativo (`chain.py:136`) e que um LST
não entraria em `equity_sol` (`inputs.py:199`) — acrescentando que a conversão apareceria como
**perda/drawdown**, não só como redução de caixa (`inputs.py:229`), ponto que esta versão da nota já
incorpora.

**Correções aceitas** (a versão anterior desta nota estava errada nestes quatro pontos, já
corrigidos acima):
1. A checagem `wallet_unrecognized_holdings` **não é alimentada** por nenhum dos três pontos de
   entrada (`entries.py`, `launch_entries.py`, `spot_entries.py`) — o parâmetro `unrecognized` de
   `wallet_from()` sempre chega vazio. A versão anterior afirmava que um LST "travaria as entradas",
   o que é falso hoje: a proteção existe no motor de risco, mas não está ligada a nenhuma leitura real
   da carteira.
2. Os 0,1% de taxa da Jito são do **resgate direto pelo protocolo** (que ainda espera o cooldown de
   época), não da rota instantânea — a instantânea de verdade é vender em DEX, sem taxa de protocolo
   mas com slippage.
3. O resgate atrasado da mSOL (0,2%) tem **mínimo de 1,0043 SOL**, acima do saldo inteiro discutido
   aqui — essa rota não está disponível neste tamanho.
4. Época teórica são **2 dias**, não 2,5; e 0,017–0,027 SOL/ano é **maior**, não menor, que o rent de
   uma ATA (0,00203928 SOL) — a comparação estava invertida.

**O que ela faria diferente:** tratar a faixa de 5–7% como cenário ilustrativo (só a taxa de
recompensa da rede e a inflação, 5,02%/3,65%, foram conferidas por ela na fonte citada; os
*snapshots* de APY dos LSTs vêm de agregador e podem divergir por metodologia/janela — risco já
sinalizado nesta nota) e calcular o rendimento esperado só sobre o excedente ao piso de tesouraria
(0,30 SOL), não sobre o saldo inteiro — o que esta versão já faz (§7).

**Divergência:** nenhuma na recomendação final. Fica registrado, fora do escopo desta tarefa, o
achado dela de que a lacuna do item 1 acima (checagem prevista mas não alimentada) merece um item de
acompanhamento próprio — não uma correção desta nota de leitura.

## Relacionados

[[Ideias do Everton]] · [[Proximas Hipoteses]] · [[2026-09-26-mesa-meme-real-pausada-no-escopo]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]]

## Atualização operacional — 2026-10-01 (acréscimo; o texto acima é o corte de 27/09)

> Retificação da curadoria ([[Curadoria-2026-10-01]]). Nada acima foi apagado: a §5, a abertura ("hoje", "sem nenhuma posição aberta") e a correção nº 1 da "Segunda opinião" descrevem o código e a carteira **de 26–27/09**.

- **A proteção deixou de ser inerte.** Os três caminhos de entrada agora passam `unrecognized=holdings.unrecognized` a `wallet_from()`: `services/meme-executor/hunter_meme_executor/entries.py:184`, `launch_entries.py:217` e `spot_entries.py:211` (conferido em 2026-10-01; commit `190a9ecb`). A checagem foi ao ar no deploy `a72296a0` (30/09) e a primeira leitura registrada deu `wallet_holdings_state=valid`, `wallet_unrecognized_count=0` ([[Diario/2026-09-30]]; contrato em [[Wallet-unrecognized-holdings]]).
- **"Sem posições" e o saldo de 0,3845 SOL da abertura são desse corte histórico.** Em 30/09 a `spot/1` teve posição UNI aberta (entrada 14:45Z, saída 18:45Z, [[Diario/2026-09-30]]), e a decisão [[2026-09-28-excecao-auditada-token-golpe]] registra a posição UNI da `spot/1` entre o que não é tocado no ensaio de fechamento de contas.
- **Consequência para a pergunta do LST:** a ressalva "falso hoje" do item 1 da "Segunda opinião" também caiu. Com a checagem ligada, todo mint que o banco não explica recusa/adia entradas, salvo exceção auditada por mint (migração `0068`); introduzir outro ativo na carteira passou a ter custo operacional. A recomendação (manter SOL líquido nesta carteira) não muda; a premissa "um LST não travaria nada" é que não vale mais.
- Esta nota **não** é leitura atual da carteira. Para o saldo e as posições vigentes: o diário mais recente e o heartbeat do executor.

---
tags: [knowledge, meme, pumpfun, nats, websocket, latencia, tempo-real, rea, carteiras, h-030]
tema: os feeds de tempo real da própria pump.fun (NATS anônimo do site, boards /ws/trenches) entregam a informação antes das fontes que usamos hoje (PumpPortal gratuito, logsSubscribe do RPC)? medido em duas janelas, com atraso por fonte, cobertura e o que cada feed carrega
fonte: sonda de 06/10/2026 desta máquina (infra/scripts/research/2026-10-06-pumpfun-realtime-latency.py; leitura em …-latency-read.py; capturas em .claude/state/pumpfun-rt-latency/run1 e run2, relatórios run1-report.md e run2-report.md, tcp-connect.txt); bundle e home page da pump.fun lidos em 06/10 (nenhum segredo gravado)
fonte_url: https://pump.fun/
lido_em: 2026-10-06
evidencia: medição própria (duas janelas: 03:27–03:46Z com 1 060 s analisados e 11:39–12:14Z com 1 997 s; 1 680 criações da pump únicas e 13 680 transações de moedas vigiadas pareadas NATS×RPC) + revisão da Astra em duas rodadas
hipotese_testavel: não (é medição de instrumento; serve à decisão de onde coletar para o H-030 e ao orçamento de latência do KB-0124)
astra: concorda em parte (REQUEST_CHANGES nas duas rodadas: 7 pontos no instrumento e 6 no texto e nas correções, todos tratados; as tabelas principais foram reproduzidas por ela) — ver Revisoes-Astra/pumpfun-rt-latency
status: vivo
owner: exchange-integration-specialist
updated: 2026-10-06
confiança: "backtest do autor"
tipo: pesquisa
hipotese: —
variavel: atraso de entrega (s), em relação à NATS `processed`, por fonte (PumpPortal, logsSubscribe processed, board new/graduated, NATS lite, NATS saldo por carteira)
populacao: criações do programa pump (580 + 1 100 assinaturas) e transações do programa pump em moedas recém-criadas vigiadas pela sonda (2 893 + 10 787 assinaturas), duas janelas de 06/10/2026
efeito: —
ic: —
veredito: —
proximo_passo: decisão do Everton sobre depender da credencial estática embutida na home page e sobre o canal por carteira (ver a pendência da INBOX); se sim, repetir da VPS, com o RPC pago como referência e em outros dias
classe_de_perda: —
mercado: meme
---

# KB-0186 — O tempo real da pump.fun chega uns 0,1 s antes das outras fontes, nas duas janelas medidas (06/10/2026)

## O que afirma

O site da pump.fun, para qualquer visitante anônimo, abre dois servidores NATS por WebSocket (`unified-prod` e `prod-v2`) com um usuário estático `subscriber` cuja senha vem nos *props* da própria home page. Assinando os assuntos que o site assina (novas moedas, trades por moeda), a NATS **antecipa** as fontes que usamos hoje: nas duas janelas ela chegou **primeiro em 97–99 % das assinaturas pareadas** contra o `logsSubscribe` do RPC público em `processed` (mediana **0,14–0,16 s** de vantagem; p10 0,04–0,06 s; p90 0,23–0,24 s) e contra o PumpPortal gratuito nas criações (mediana **0,03–0,09 s**, muda de janela para janela). Os boards `/ws/trenches` e os canais `lite` e de saldo **atrasam** (0,45 s, 0,29 s, 0,47–0,49 s contra a NATS `processed`). A vantagem é menor que um slot e muito menor que o orçamento de decisão ([[KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]], evento→proposta 0,6–1,6 s); **chegou antes não é operamos antes**, e **não demonstramos benefício operacional ou econômico**. Nas amostras examinadas a NATS não traz KOL, PnL de holders nem "thesis" (a equivalência de conteúdo com a cadeia **não** foi demonstrada). O que ela tem de próprio para o H-030 é o canal **por carteira** (`account_balance_change.<carteira>.*`), sem coletar o programa inteiro — e é também a parte mais exposta do ponto de vista de escopo (ver "O que muda na operação").

## Onde foi mostrado

Uma conexão por fonte, desta máquina (Windows; relógio local 0,057 s atrás do `pump.fun/api/server-time`, faixa 0,019–0,152 s, RTT mediano 0,26 s), cada leitor carimbando `time.time()` ao acordar do `recv`, antes de parsear; deltas par a par no mesmo relógio (o desvio constante cancela). Coorte simétrica: transação que qualquer fonte entregou dentro do interior (3 s das bordas) da janela de exposição, com a contraparte procurada na captura inteira. Chave: assinatura (criações e trades; "primeira notícia da transação") e mint (boards); no saldo, assinatura mais carteira. Positivo = a fonte chegou depois da NATS. Empate = diferença de até 10 ms. Janela 1: 06/10 03:27–03:46Z (a máquina dormiu 7,8 h depois; só o trecho íntegro foi analisado). Janela 2: 06/10 11:39–12:14Z, sem suspensão da máquina (o PumpPortal caiu 4,8 s, ver abaixo).

**Criações do programa pump** (atraso da fonte contra a NATS `unifiedCoinCreationEvent`, em segundos):

| fonte | janela | pares | p10 | p50 | p90 | NATS 1.º | cobertura da fonte |
|---|---|---|---|---|---|---|---|
| PumpPortal `subscribeNewToken` (grátis) | 1 | 520 | 0,080 | 0,093 | 0,228 | 99,4 % | 520 de 580 (89,7 %) |
| PumpPortal | 2 | 962 | 0,022 | 0,032 | 0,123 | 97,9 % | 962 de 1 100 (87,5 %) |
| `logsSubscribe` público, `processed` | 1 | 580 | 0,035 | 0,136 | 0,236 | 97,4 % | 100 % |
| `logsSubscribe` público, `processed` | 2 | 1 100 | 0,055 | 0,154 | 0,241 | 99,3 % | 100 % |
| board `new` do `/ws/trenches` (por mint) | 1 | 573 | 0,213 | 0,454 | 0,680 | 99,8 % | 98,8 % |
| board `new` | 2 | 1 093 | 0,224 | 0,446 | 0,685 | 100 % | 99,4 % |

PumpPortal contra o `logsSubscribe` público: o PumpPortal chegou 0,022 s (janela 1) e 0,104 s (janela 2) antes na mediana; foi primeiro em 54 % e 87 % dos pares (na janela 1, 35 % depois e 10 % em empate) — **não há equivalência estabelecida**; o resultado muda de janela para janela. Não observamos 10,3 % e 12,5 % das criações no PumpPortal; na janela 2 ele ficou 4,8 s desconectado (um 502 no handshake de reconexão) e 3 criações ausentes caíram nesse intervalo, então parte da diferença é queda, não cobertura do serviço.

**Trades** (moedas recém-criadas vigiadas: até 30 ao mesmo tempo, 6 min cada; só o programa `pump`):

| fonte | janela | pares | p10 | p50 | p90 | NATS 1.º |
|---|---|---|---|---|---|---|
| `logsSubscribe` público, `processed` | 1 | 2 893 | 0,042 | 0,142 | 0,232 | 97,5 % (empate: 2,0 %) |
| `logsSubscribe` público | 2 | 10 787 | 0,058 | 0,156 | 0,241 | 99,4 % (0,4 %) |
| NATS `lite` | 1 / 2 | 436 / 4 033 | 0,181 / 0,187 | 0,293 / 0,296 | 0,447 / 0,425 | 100 % |
| NATS saldo por carteira (20 carteiras; um par por perna assinatura+carteira) | 1 / 2 | 415 / 1 315 | 0,348 / 0,347 | 0,491 / 0,469 | 0,635 / 0,622 | 100 % |
| saldo por carteira contra o `logsSubscribe` | 1 / 2 | 415 / 1 315 | 0,267 / 0,251 | 0,339 / 0,319 | 0,468 / 0,431 | — |

Cobertura nas moedas vigiadas: NATS e RPC viram 100 % da coorte nas duas janelas (2 893 e 10 787 assinaturas). O canal de saldo entregou **415 de 415** e **1 315 de 1 317** pernas esperadas (alguma atualização de saldo da carteira na transação; não conferimos todas as pernas SOL/token). 19–27 % dos quadros NATS das moedas vigiadas são do programa `pump_amm` (PumpSwap, 747 e 4 275 quadros): **não há referência equivalente** nesta sonda e eles ficaram fora de toda comparação.

**Reprise ao assinar.** Parcela dos quadros NATS cujo segundo de bloco é anterior à assinatura (no relógio do servidor): com folga de 0 s, **2,3 % e 1,2 %**; com folga de 2 s e de 4 s, **0 %** nas duas janelas. Os pares não mudam com a folga (mediana 0,142 / 0,156 s). Isso é uma inferência a partir de um timestamp de 1 s: não prova reprise nem a ausência dela.

**Graduação** (poucos pares, indicativo): o board `graduated` chegou depois do `subscribeMigration` do PumpPortal em mediana 0,422 s (10 pares, janela 1) e 0,499 s (12 pares, janela 2). A NATS não tem assunto de graduação que o site use, então não entra.

**KOL no board `new`** (observação desta sonda; não mede antecipação de preço): 676 e 1 134 eventos `add` do programa pump são 587 e 1 111 moedas distintas (uma moeda pode voltar ao board); no primeiro `add`, só 2 e 12 delas já traziam `kol > 0`; o primeiro incremento chegou ~1,0 s depois do primeiro `add` (n 112 e 376; mediana 0,999 e 1,063 s). A leitura econômica continua a de [[KB-0142-kol-e-call-antecipam-ou-confirmam|KB-0142]].

**Rede e ruído.** Esta máquina fica a ~150–255 ms (TCP) dos servidores NATS (endereços 52.2.x e 3.209.x, faixa da AWS us-east pelo endereço; a região não foi confirmada) e a ~160–320 ms do PumpPortal; o `/ws/trenches` (Cloudflare) a ~30–70 ms (`.claude/state/pumpfun-rt-latency/tcp-connect.txt`). Atraso do laço (timer de 0,1 s): p50 0,009 s, p99 0,025 s.

## O que a NATS carrega, nas amostras examinadas

Inventário de **4 quadros por grupo**, só as chaves de topo do primeiro JSON válido: o que segue vale para essas amostras, não é uma prova de ausência.

- `unifiedCoinCreationEvent` (39 chaves): nome, símbolo, `metadata_uri`, criador, `bonding_curve`, reservas, `mayhem_state`, `is_cashback_enabled`, `is_holder_reward`, taxa de transferência e `derived_pool`. `unifiedTradeEvent.processed` (61 chaves): o trade já decodificado com taxas separadas, reservas, preços em USD e SOL, `solPriceUsd` e **`coinMeta` colado em cada trade** (nome, símbolo, URI, criador, flags) — poupa a leitura do metadado. Quase tudo é do tipo que sai da cadeia com o decodificador que já temos ([[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]]), mas a **proveniência de cada campo não foi demonstrada** (`solPriceUsd`, `is_banned`, atribuição).
- `app`, `surface`, `surfaceAttribution` e `relayer` (quem roteou o trade): nas 4 amostras vieram `null`/`null`/`null`/`"default"`; **não medimos** se vêm preenchidos para rotas de terceiros.
- Nas amostras não aparecem `kol`, PnL de holders, "thesis", snipers ou top-10. Esses campos vivem no REST (`/mint-positions?withThesis`, `profile-api /pnl/coin/{mint}/holders`) e na entrada do board (`kol`, `sn`, `nh`, `t10`, `dh`; 51 chaves no `new`), que já coletamos.
- **`account_balance_change.<carteira>.*` na instância CORE** (`prod-v2`): cada mudança de saldo (SOL e cada token) da carteira, com `slot`, `txSignature` e carimbo do servidor em milissegundos. O servidor aceitou 20 carteiras escolhidas por nós (nunca apareceu `Maximum Subscriptions`; o limite é desconhecido). É saldo, não swap: lado e preço saem do par de pernas. Nossa chegada ficou ~0,18–0,19 s depois do carimbo do próprio servidor (mediana).

## Como mediríamos aqui

Repetir da VPS (a região muda os atrasos), com o RPC pago da VPS como referência no lugar do público, em outros dias e horários; guardar bytes por fonte (o contador `rpc.bytes` já existe) e mais quadros de amostra por grupo para o inventário. A diferença **chegou antes ≠ conseguimos operar antes**: faltam processamento, decisão, envio e inclusão da própria ordem — medição à parte, sem dinheiro.

## Hipótese testável no Lab

Nenhuma. É infraestrutura. Nenhuma estratégia lê a NATS.

## O que muda na operação

- **Nada liga.** A sonda é só leitura e roda desta máquina; nenhum worker passa a ler a NATS.
- **O ganho de latência é real nestas janelas e pequeno**: ~0,03–0,09 s sobre o PumpPortal nas criações e ~0,14–0,16 s sobre o `logsSubscribe` público, medidos a ~0,15 s de distância dos servidores. Não entra no orçamento do [[KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]] até ser repetido da VPS. Para contexto, [[KB-0141-sniper-de-lancamento|KB-0141]] mediu que a entrada cedo no lançamento não tinha vantagem de latência (18 de 18 células negativas) — mas isso não é uma medição da NATS, e a conclusão aqui é só **"não demonstramos benefício"**.
- **Para o H-030 (carteiras)** o canal por carteira é a descoberta que vale uma conversa: seguir N carteiras escolhidas sem coletar o programa inteiro (330–353 eventos/s e US$ 650–760/mês pelo RPC pago, [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]]), mas com ~0,3 s a mais que o `logsSubscribe` público e só saldos.
- **Escopo e dependência — decisão do Everton.** A credencial é a que a home page entrega a todo visitante, mas é **estática, embutida e não documentada** (pode ser rotacionada, e a [[2026-10-06-rea-na-pumpfun-apesar-dos-termos|decisão de 06/10]] mantém "só visitante anônimo, parar no primeiro bloqueio" e nunca driblar autenticação). As assinaturas de novas moedas e de trades por moeda são as que a página da moeda faz. **A assinatura por carteira arbitrária foi extensão minha**, além dos assuntos pedidos: o servidor aceitar 20 carteiras não prova que o visitante anônimo normal faça isso. Não passei de 20 e parei; a pendência está em [[2026-10-06-nats-da-pumpfun-escopo-da-credencial]]. A sonda lê a credencial em tempo de execução e não grava (conferido: nenhuma senha nos arquivos da captura, no código nem nas notas).
- **RPC público.** O **HTTP** do RPC público responde `413 "You have used your data allowance"` (HTTP 200 com erro JSON-RPC) desde, no mínimo, o fim da janela 2 (09:14 de Brasília); o **WebSocket** entregou os 35 min inteiros da janela 2. O `logsSubscribe` de todo o programa pump gasta a cota gratuita do IP (por tudo o que esta máquina já puxou, não só por esta sonda; os bytes não foram contados nestas duas corridas). **Falha minha na sonda:** a primeira versão só parava em HTTP 403/418/429, então o `getBlockTime` da checagem "segundo da NATS contra o bloco da cadeia" fez 60 chamadas a 2/s no fim de cada janela (120 no total) sem registrar o erro; consertado (para na primeira recusa, com teste) e **nenhuma chamada mais** a esse endpoint depois de descobrir (3 diagnósticas). A checagem **não foi obtida** (n 0).

## Por que pode falhar

- **Duas janelas, uma máquina, um relógio.** A vantagem sobre o PumpPortal foi 0,093 s numa janela e 0,032 s na outra; o relógio local tem incerteza de ~0,13 s no offset (metade do RTT da amostra), embora cancele nos deltas par a par.
- **O RPC público não é o que a VPS usa.** Contra o RPC pago ou um Geyser a vantagem pode sumir; o RPC público é um endpoint concreto numa rota concreta, não lento "por natureza". O PumpPortal (que se diz < 100 ms atrás de um gRPC) é a referência mais rápida, e a NATS chegou antes dele em 98–99 % das criações pareadas.
- **População.** Só moedas da pump descobertas pela NATS e admitidas pelo teto de 30, nos primeiros 6 minutos de vida; PumpSwap fora; a chave é a transação, não a perna do trade.
- **O segundo de `timestamp`** é uma estimativa publicada com resolução de 1 s e seu erro total não foi medido (a checagem contra o `getBlockTime` falhou), por isso os atrasos "contra o bloco" (NATS p50 1,05–1,08 s, RPC 1,20–1,22 s) **não entraram em nenhuma conclusão** e não se comparam com os 0,42 s do [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo|KB-0134]] (outro método, outro dia).
- **Parada de 7,8 h** na janela 1 (a máquina dormiu apesar do guarda de energia): só o trecho íntegro entrou; o relatório separa a captura em qualquer parada longa. A janela 2 foi com o guarda reforçado (tela exigida).
- **Inventário de campos** com 4 amostras por grupo; **reprise** só inferida por timestamp.

## Segunda opinião (Astra)

[[pumpfun-rt-latency]] — rodada 1 (desenho e código): 7 pontos, todos tratados (programas misturados, reconexão reescrevendo a exposição, definição de reprise, elegibilidade assimétrica, assinatura × perna, tarefas sem supervisão, janela vazia). Rodada 2 (resultados, texto e correções): as tabelas batem; 6 pontos, todos tratados (a conclusão sobre conteúdo da NATS e a "ausência de reprise" estavam acima do que a evidência sustenta; população do KOL; saldo por perna; contraparte tardia; "empata").

## Relacionados

[[KB-0134-websocket-do-rpc-lag-medido-ao-vivo|KB-0134]] (o `logsSubscribe` público, outro método) · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]] (o custo de coletar o programa inteiro) · [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas|KB-0185]] (o que o site publica sobre carteiras) · [[KB-0142-kol-e-call-antecipam-ou-confirmam|KB-0142]] · [[KB-0141-sniper-de-lancamento|KB-0141]] · [[KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-M15-carteiras-vencedoras]] · [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]] · [[2026-10-06-nats-da-pumpfun-escopo-da-credencial]] · [[Exchange Adapters]] · `docs/PUMPFUN.md` §3 e §10 · `.claude/state/rea-pumpfun-capture-2026-10-06.md`

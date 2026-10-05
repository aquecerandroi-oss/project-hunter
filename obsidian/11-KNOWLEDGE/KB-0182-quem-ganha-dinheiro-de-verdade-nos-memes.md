---
tags: [knowledge, meme, carteiras, smart-money, copy-trading, pumpfun, pumpswap, r57, r61, h-030]
tema: quem ganha dinheiro de verdade nos memes (pump.fun + PumpSwap) e se dá para segui-lo, com o que medimos e o que a literatura diz
fonte: R57 (.claude/state/notes-R57.md), R61 (.claude/state/notes-R61.md), consultas só leitura na VPS em 05/10/2026 (.claude/state/carteiras-lucro/q1–q4.sql), literatura listada abaixo
fonte_url: https://doi.org/10.1287/mnsc.2019.3508
lido_em: 2026-10-05
evidencia: medição própria (R57 72 h de fita; R61 72 h de boards; latência de 62 compras reais) + 4 artigos (1 revisado em periódico, 3 em anais/preprint)
hipotese_testavel: sim (H-030, rascunho em .claude/state/carteiras-lucro/PREREG.md)
astra: discorda do desenho original (REQUEST_CHANGES), concorda com a pesquisa — ver Revisoes-Astra/carteiras-lucro-design
status: vivo
owner: quant-engineer
updated: 2026-10-05
confiança: "backtest do autor"
tipo: leitura
hipotese: H-030 (rascunho)
variavel: C-PnL (PnL copiável com o nosso atraso) por entidade
populacao: carteiras do programa pump + PumpSwap inteiro, para frente (ainda não coletado)
efeito: —
ic: —
veredito: —
proximo_passo: aprovação do Everton do desenho docs/design/seguir-carteiras-lucrativas.md; deploy da T4.8e; onda 0 (sondagem de 2 h)
classe_de_perda: —
mercado: meme
---

# KB-0182 — Quem ganha dinheiro de verdade nos memes, e por que "ganhar" não é "dá para seguir" (05/10/2026)

## O que afirma

"Dinheiro de verdade" é **SOL realizado, líquido de taxa**, numa janela de dias, com o saco parado avaliado pelo
que renderia se fosse **vendido contra a própria curva** e nunca pela última cotação. Mesmo assim, ganhar não basta.
O que importa para nós é o **PnL copiável**: o que *nós* teríamos ganho entrando e saindo **depois** dessa carteira, com
o nosso atraso medido (p50 3,5 slots ≈ 1,4 s, p90 12,3 slots ≈ 5 s, do slot do gatilho ao pouso) e o nosso custo. A
evidência própria (R57, R61) diz que o lucro de quem ganha é, em grande parte, velocidade, pacote e venda para quem
chega depois. A literatura diz o mesmo da cópia em memes: ela é **alvo** de quem é copiado.

## O exemplo do Everton ("sadcrissy", 05/10)

A conta foi criada em 01/10 e tem 6 934 seguidores. No dia marcou **+US$ 144 mil**: US$ 19 mil realizados e
**US$ 125 mil não realizados (87 %)**, com só US$ 3 050 de compras. O não realizado é marcação; vendê-lo derruba o
preço que o gerou. Conta nova com audiência sugere criador ou influenciador, cujos seguidores são a saída (KB-0142: o
selo KOL chega no pico). **Pela definição acima, conta no máximo a parte realizada, e só líquida do custo.**
O endereço completo está pendente. Sem ele, nada sobre esta conta é medido; o que está escrito aqui é leitura do print.

## Onde foi mostrado (próprio)

- **R57 / [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]]** (72 h de fita, 15–18/09). Os vencedores persistem
  (Spearman 0,61 e 0,65; o top-30 de D1 fez +79,6 SOL em D2). Mas metade segura 1–13 s, 16 % das compras caem no
  bloco do `create` e 43 % dos sinais são gêmeas no mesmo segundo. O sinal "2 do top-30 em 60 s" vale 1,01× a 3 s e
  0,96× a 20 s, com R igual ao controle (Δ +0,07 [−0,06; +0,21] a 3 s). A fita cobria 5 % dos mints.
- **R61 / [[KB-0142-kol-e-call-antecipam-ou-confirmam]]**: comprar 20 s depois do selo KOL dá R −0,071 (n 3 486).
- **Latência (05/10, VPS, só leitura).** Do slot do último trade na fita da decisão ao slot do nosso fill, em 62
  compras reais (24–26/09): p10 3, p25 3, **p50 3,5**, p75 5, **p90 12,3** slots. Da proposta à confirmação: p50
  1,65 s, p90 3,9 s (143 compras). Consulta: `.claude/state/carteiras-lucro/q4.sql`.
- **Cobertura atual.** `meme_wallet_trades` = 0 linhas: ela só observa `MEME_WATCH_WALLETS` por polling. A fita
  `meme_trades` (`swap_api`) cobre ~1 400 mints/dia contra ~45 mil criações/dia (`q1.sql`, 26/09–03/10). O feed de evento
  está cego desde **02/10 15:47Z** (a última fita de decisão é 15:47:18Z), até o deploy da T4.8e
  ([[T4.8e-upgrade-02-10]], [[T4.8e-decoders]]).

## O que a literatura diz (fonte, data, qualidade)

| Fonte | O que mostra | Qualidade |
|---|---|---|
| Apesteguia, Oechssler & Weidenholzer, "Copy Trading", *Management Science* 66(12):5608–5622, dez/2020, https://doi.org/10.1287/mnsc.2019.3508 | Em mercado experimental, ver o sucesso alheio **aumenta** o risco assumido, e a opção de copiar aumenta mais ainda. A conclusão é que copiar leva a risco excessivo | Periódico revisado; laboratório, não memes |
| "Resisting Manipulative Bots in Meme Coin Copy Trading…", WWW'26, arXiv 2601.08641 (jan/2026), https://arxiv.org/abs/2601.08641 | Cópia é a estratégia de entrada dominante nos memes, e robôs adversários exploram quem copia: «systematically extracting value from naïve copiers». O sistema dos autores rende ~3 % por moeda "com atritos realistas" | Anais; resultado econômico é backtest dos autores |
| "Meme Coin Factories…", CCS'26, arXiv 2609.10246 (set/2026), https://arxiv.org/abs/2609.10246 | 15 M de moedas da pump.fun. Cinco classes de manipulação: *wash trading*, ofuscação do endereço do criador, venda coordenada, cópias de moeda, manipulação social. Existe até "manipulação como serviço" | Anais; amostras aleatórias de transações |
| "Coordinated Sniper Cohorts on Pump.fun", arXiv 2607.02795 v3 (ago/2026), https://arxiv.org/abs/2607.02795 | 1 012 anéis persistentes de carteiras (2 965 endereços) que disparam juntos como primeiros compradores em 166 mil lançamentos, 13,4 dias. Quem compra junto e cedo é frequentemente **um** operador | Preprint; detecção por coocorrência |

**Leitura conjunta.** "Seguir quem ganha" tem três inimigos, e os três aparecem nos nossos dados e nos artigos:
1. **Velocidade:** o ganho acontece antes de chegarmos.
2. **Identidade:** gêmeas, anéis e criadores disfarçados inflam o "vencedor" e a amostra.
3. **Adversário:** quem é copiado pode vender para quem copia.

Nenhum artigo mostra uma vantagem de seguidor **líquida, para frente e no nosso atraso**.

## Como mediríamos aqui

Desenho em `docs/design/seguir-carteiras-lucrativas.md`; pré-registro (rascunho H-030) em
`.claude/state/carteiras-lucro/PREREG.md`. Em resumo:

- Coletor do **programa inteiro** (pump + PumpSwap) com cobertura por slot.
- **Entidade** em vez de carteira (financiador comum e mesmo slot).
- Ranking diário imutável por **C-PnL**: a própria política de cópia simulada com 5 slots de atraso, saindo 5 slots
  depois da venda deles, pelo pior preço do slot.
- Filtro de posse mediana ≥ 60 s; E-PnL com o saco a valor de liquidação.
- Braço `follow` e controle de entidades elegíveis fora do top-30.
- Coorte só para frente, cluster dia × entidade, Holm.

## Hipótese testável no Lab

H-030 (rascunho, **não** está na Fila). A previsão registrada é **NÃO CONFIRMA**: ponto H1 ≈ −0,03 R, H2 ≈ +0,02 R.
É a 7.ª tentativa da família "quem está comprando" (R57, R61, E2-b, H-010, H-014, H-015).

## O que muda na operação

- Nada liga sozinho. "Seguir carteira" continua `nao_confirma` no [[Mapa de Estrategias]] até haver veredito.
- **Lucro de perfil (site, KOL, seguidores) não é critério.** Ele mede o passado de quem já vendeu para alguém, e esse
  alguém, na cópia, seríamos nós.
- Qualquer placar de carteiras que a casa mostrar ao Everton separa **realizado** de **marcação** e mostra o
  **copiável**. Nunca soma os três.

## Por que pode falhar

- A janela de 7 dias e os limiares (top-30, 60 s, +2 SOL) são escolhas, não derivações.
- A potência é fraca: com SD 1,2 R, 2 000 apostas só detectam ≈ 0,075 R, mesmo sem cluster.
- RPC público não é produção. O WS pago tem custo desconhecido.
- Um regime só, e a família é longa: um CONFIRMA isolado ainda pede réplica.

## Segunda opinião (Astra)

[[06-DECISIONS/Revisoes-Astra/carteiras-lucro-design|carteiras-lucro-design]] — REQUEST_CHANGES no desenho, concorda
com a pesquisa. Os 9 itens obrigatórios foram absorvidos no desenho e no rascunho.

**Onda 1c (05/10): o motor puro existe, e a definição do E-PnL ganhou uma errata.** Ao pé da letra, "realizado FIFO +
Δ liquidação" pontuaria com +0,2 um saco comprado por 1 que hoje vale 0,2. O motor calcula **caixa casado da janela +
V(fim) − V(início)**, com a mesma avaliação em toda fronteira e 0 sem estado válido. A censura a R = −1 do PREREG é
uma **imputação** pré-registrada, não um limite inferior: a perda total é R = −2. Ver
[[06-DECISIONS/Revisoes-Astra/wallets-engine|wallets-engine]]. Nada foi medido em dado real: o motor só tem testes
sintéticos.

## Relacionados

[[EXP-M15-carteiras-vencedoras]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0142-kol-e-call-antecipam-ou-confirmam]] ·
[[KB-0138-explosao-de-compradores-nao-tem-vantagem]] · [[KB-0141-sniper-de-lancamento]] ·
[[KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]] ·
[[KB-0171-custo-real-da-spot-1]] · [[Fila de Hipoteses]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]] (a medição da onda 0: volume, RPC e disco)

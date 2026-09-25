---
tags: [knowledge, meme, pumpswap, graduacao, custo, taxas, pos-migracao, look-ahead, r66, m4]
tema: depois da graduação a taxa é praticamente a mesma da curva (1,20 %/perna na mediana, não 0,30 %), a população cai −80 % em 15 min e a nossa regra perde lá em 8 de 8 dias — e o "sinal de seleção" que apareceu primeiro era antecipação minha
fonte: .claude/state/notes-R66.md (6 384 tokens graduados em 7 dias, 4 400 com série do board a 60 s; 15–22/09/2026)
fonte_url:
lido_em: 2026-09-22
evidencia: medição própria — 195 658 observações do board `graduated`, 79 620 trades `pump_amm`, taxas lidas das 25 faixas reais do `FeeConfig` do PumpSwap decodificadas da mainnet; permutação estratificada por dia (10 000), bootstrap por dia, Benjamini-Hochberg FDR 10 %
hipotese_testavel: não (é uma refutação — nenhum EXP aberto)
astra: revisto em duas rondas — 6 correções de método antes de medir e 3 bugs reais no código depois, dois deles mudaram o resultado
status: vivo
owner: sexta-feira
updated: 2026-09-22
confiança: "?"
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0148 — A graduação não é a saída barata (R66, 15–22/09/2026)

## O que afirma

1. **A taxa depois da graduação é praticamente a mesma da curva, não 0,30 %.** O `FeeConfig` real do programa PumpSwap (25 faixas, decodificado da mainnet em 16/09, fixture `t429c_rpc_fee_config_amm_raw.json`) cobra **1,25 %/perna abaixo de 420 SOL de market cap** e **1,20 % entre 420 e 1 470 SOL**; os **0,30 % só começam em 98 240 SOL**. Nas 4 400 graduações observadas a mediana do market cap na entrada é **708 SOL** e a faixa mediana é **1,20 %/perna** (p10 0,65 %, p90 1,25 %); **só 5,8 % das entradas chegam à faixa de 0,30 %**. Custo de taxa **realizado** ida-e-volta nas operações simuladas: **mediana 2,40 %, média 2,26 %** — contra **2,23 %** medidos na curva (R65, sem rent).
2. **O rent de ATA não muda de praça.** São os mesmos 0,00151384 SOL (2,16 % de um ticket de 0,07), criados na mesma altura e recuperáveis do mesmo jeito. **A economia do KB-0147 não exige sair da pump.fun.**
3. **A população pós-graduação é hostil.** Desde a primeira leitura pós-migração, a mediana de um token graduado é **+0,9 % a +1 min**, **+1,2 % a +5 min**, **−79,9 % a +15 min** e **−95,1 % a +1 h** (n 4 077 / 3 276 / 2 714 / 1 964). **86,8 % caem ≥ 30 % dentro de 1 h.** A graduação é o evento de liquidez de saída de quem estava na curva.
4. **A nossa regra aplicada lá perde em todos os dias.** Entrada na graduação + alvo 1,15× / trailing 10 % / 300 s: **−0,003691 SOL por operação (−5,27 % do ticket)** em 3 171 entradas decidíveis, 36,2 % de alvos, **0 dias verdes em 8**. Variante lenta (1,30× / 15 % / 3 600 s): −8,80 % do ticket. Entrada no pullback de −10 % (observável em só 61,7 % dos mints): −4,83 % do ticket, também **0/8**.
5. **Nenhuma das 11 variáveis observáveis na entrada separa vencedoras de perdedoras.** Baldes por terços, permutação estratificada por dia (10 000), bootstrap reamostrando dias inteiros, Benjamini-Hochberg a 10 %: **o p mais baixo é 0,0734 contra um limiar de 0,0091 — zero sobreviventes.** É a mesma resposta do KB-0147 numa população 36× maior.
6. **PumpSwap é só saída no nosso código.** Não existe `build_buy_instruction`; comprar lá é a recusa nomeada `pumpswap_buy_not_allowed` (`docs/RISK_ENGINE_MEME.md` §1, `hunter_exchanges/pumpswap/__init__.py`). Abrir esta frente exigiria caminho de execução novo e checks de admissão novos.
7. **A lição de método, que vale mais do que o resultado:** a primeira volta desta análise dizia **"9 de 11 variáveis sobrevivem ao Benjamini-Hochberg (p = 0,0001)"** e **"−14,1 % do ticket por operação"**. Os dois números eram **artefacto de antecipação**: o simulador vendia na última leitura da série (naquele instante ninguém sabia que era a última) e aceitava lacunas de minutos entre leituras como se fossem monitorização a 60 s. Corrigido — censurar lacunas > 150 s e excluir as censuradas do PnL — **o "sinal" desapareceu inteiro e o prejuízo caiu para metade**. As variáveis não separavam quem dava lucro: separavam **quem tinha série boa**.

## Onde foi mostrado

VPS, leitura `SELECT`/`COPY TO STDOUT` apenas. **6 384 tokens com `migrated_at` em 15–22/09/2026.** A fita do pool (`meme_trades`, `program='pump_amm'`, fonte `swap_api`) cobre só **1 002 mints (15,7 %)** e morre numa mediana de **57 s** depois da migração — o poller larga o mint quando ele sai da watchlist do radar. O feed que atravessa a primeira hora é o **board `graduated`** (`meme_board_observations`): **4 400 mints (68,9 %)**, cadência 60 s, primeira leitura mediana **+29 s**, 195 658 observações. Preço = `market_cap_usd` (supply fixa de 1e9), convertido para SOL. Validação contra a fita nos 834 mints com as duas coisas: razão mediana **1,002**, p10–p90 **0,852–1,212**.

## O que muda para nós

- **Não abrir frente pós-graduação.** O P0 continua a ser o do KB-0147: fechar a ATA. Ele não depende de praça.
- **Quando alguém disser "a taxa lá é 0,30 %", pedir o market cap.** A faixa é do market cap do instante, e um recém-graduado está a ~708 SOL, três ordens de grandeza abaixo do limiar dos 0,30 %.
- **Regra de método, permanente:** num backtest sobre um feed esparso, **"a série acabou" nunca é uma venda** e uma lacuna maior que 2,5× a cadência **não decide nada**. Marcar censura e excluí-la do PnL — a alternativa fabrica sinal estatístico do nada.

## Ressalvas

Este estudo **não identifica a diferença de rentabilidade executável** entre as duas praças: observa uma amostra incompleta do board e simula saídas sobre preços esparsos. O preço do board só bate com a fita dentro de ±10 % em **68 %** dos casos — ruído da mesma ordem do alvo de +15 %, e numa subamostra ela própria selecionada. Snapshots de 60 s **não são barras OHLC**: sem extremo intra-minuto o alvo/trailing não é reproduzível e o viés não tem direção garantida. **27,9 % das entradas foram censuradas** e ficaram fora do PnL; se não forem um sorteio, o que sobra é enviesado numa direção desconhecida. O board tem 30 posições e o token cai fora em ~1 h, com ordenação desconhecida. **+4 h não foi medido** (zero pares válidos) e não deve ser inferido dos 72 mints que aparecem nessa janela. 7 dias, **8 datas**, um regime: "muitos mints" não é "muita informação". O impacto de 0,10 %/perna é suposição declarada, não cotação real. Nada disto demonstra superioridade da curva nem exclui outras estratégias pós-graduação — em particular ficam por testar entrar **a partir de +1 h** (com seleção feita *naquele* instante, nunca retrospectiva), horizontes de horas/dias, e pools não canônicos a 0,30 %.

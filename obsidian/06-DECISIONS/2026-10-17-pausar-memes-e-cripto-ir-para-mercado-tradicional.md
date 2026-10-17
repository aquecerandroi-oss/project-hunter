---
tags: [decisao, mercado-tradicional, b3, win, rico, memes, cripto, pausa, dinheiro-real, h-038, h-036]
status: decidida
owner: sexta-feira
updated: 2026-10-17
decided_on: 2026-10-17
by: Everton
---

# Pausar memes e cripto; ir para o mercado tradicional (B3 primeiro) — 17/10/2026

## O que o Everton decidiu (em conversa com a Sexta-feira, 17/10/2026)

1. **Parar as memes** (o piloto de cópia fica desligado; nada novo em meme).
2. Primeiro: "focar em trade de cripto, não meme coins, na Binance" — **substituído no mesmo dia** por: **nada de
   cripto**, "trader mesmo de ação e tudo mais" (ações, futuros, câmbio).
3. Mercado: "os dois [B3 e EUA], a Sexta escolhe". A conta dele é na **Rico** (grupo XP).
4. **Dinheiro real, à mão, na conta dele, a partir de segunda 19/10/2026** — sem fase de papel. **Isto foi contra a
   recomendação da Sexta-feira**, que era passar antes por papel; fica registrado aqui como decisão dele.
5. Capital (números que substituíram os anteriores no mesmo dia): banca **acima de R$ 10.000**; **R$ 1.000 colocados
   em cada operação**; limite de perda diária **R$ 9.000**.
6. Um robô autônomo para o MT5 da Rico está em desenho separado, no modelo do `meme-executor` (ele liga; a credencial
   só vai para o terminal). O painel manual e o robô usam **o mesmo módulo de estratégia**.

## O que não muda (limites da Sexta-feira)

- **Nenhum agente envia ordem**, toca a conta ou as credenciais do Everton, ou **recomenda tamanho de posição**.
- `LiveExecutionAdapter` continua levantando `LiveTradingDisabled`; o sistema não executa nada.
- O que entregamos é um **painel de sinais** (entrada, stop, alvo, janela, custo por contrato na Rico + B3, "pare por
  hoje") e o **registro automático** de cada sinal e desfecho com custo real. Registro é medição, não fase de papel.

## O que pausa e o que continua

| o quê | estado |
|---|---|
| mesa de memes, piloto de cópia (H-037, [[EXP-M28-copiar-carteiras-no-papel]]) | **pausado**; nada novo |
| Lab de cripto (10 versões ativas) | coleta segue até o Everton escolher uma opção da §10 do plano |
| **H-036** (`mean_reversion v14`, consultas cegas em 06/01, 07/04 e 07/07/2027) | **continua** — custa quase nada; ninguém toca a v14 nem lê desfechos antes de L1 ([[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]]) |
| `meme-worker` | **em laço de reinício** na VPS em 17/10 (a poda de `meme_tokens` viola a chave estrangeira de `meme_events`); bug a registrar em [[Open Bugs]] pelo dono da pista |
| mercado tradicional | **novo foco**: B3, WIN, Rico — plano `docs/plans/MERCADO-TRADICIONAL.md` |

## A estratégia para segunda e por quê

Uma hipótese simples, pré-registrada antes da abertura: **H-038, momento intradiário de mercado no WIN** — o retorno
do Ibovespa na 1.ª meia hora do pregão (desde o fechamento anterior) dá a direção de uma operação no WIN da última
meia hora até o fechamento do à vista; um sinal por dia, horas de antecedência, sem alvo, stop de catástrofe. Regras
completas, custos e o rascunho do pré-registro: plano §1.

- Base: [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] (Gao et al. 2018 no SPY; Li, Sakkas &
  Urquhart 2022 em 12 de 16 mercados desenvolvidos — o Brasil fora) e
  [[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]].
- Prior honesto: perto de "não confirma" — decaimento depois da publicação
  ([[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]]), nenhuma replicação brasileira, e no WIN
  97 % das pessoas físicas que persistiram ≥ 300 dias perderam
  ([[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]], estudo FGV de Chague, De-Losso e Giovannetti).
- Custo: ≈ R$ 2,51 por contrato ≈ 0,6 bp no cenário condicionado (tabela B3 + corretagem zero com RLP, a confirmar),
  contra 11,6 bp medidos na Binance e 2–4 % nas memes ([[KB-0149-o-que-a-mesa-real-ensinou]] §1).
- Com R$ 1.000 por operação, o **WIN com 1 contrato** (R$ 1.000 como margem; R$ 0,20 por ponto) tem a melhor relação
  custo ÷ efeito plausível, como cenário condicional (≈ 0,24, contra ≈ 2,2 no BOVA11 com R$ 1.000 de nocional). O
  stop nominal custa ≈ R$ 209,51 por contrato com custos (≈ 2,1 % de uma banca de referência de R$ 10 mil) e **não é
  perda máxima**: falha de stop, desconexão ou gap passam do nível. O painel registra o limite diário de R$ 9.000 como
  dado e não controla a conta.
- Dado do sinal: **entrada manual** dos dois números do Ibovespa pelo Everton (os termos do Yahoo proíbem coleta
  automatizada; ver o diálogo).

## O que a base já dizia sobre cada família (mapa completo no plano §7)

Tendência e rompimento em futuros: [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]],
[[KB-0003-rompimento-de-canal-e-data-snooping]], [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]].
Gráfico e padrões: [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]],
[[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]], [[KB-0080-candlestick-evidencia]],
[[EXP-0008-breakout-compressao-de-volatilidade]]. Reversão curta: [[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]],
[[EXP-0009-mean-reversion-pullback-em-tendencia]]. Abertura de sessão: [[EXP-0010-session-orb-faixa-de-abertura]].
Volume: [[KB-0015-volume-relativo-e-o-pico-como-exaustao]]. Custo de execução:
[[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]], [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]].
O que foi refutado ou não confirmado em cripto ([[Mapa de Estrategias]], [[Fila de Hipoteses]]) só volta no mercado
de origem como hipótese nova em dado novo, nunca relendo dados velhos. Candidatas futuras ficam no
[[Strategy Backlog]] pelo caminho normal.

## Decisões que continuam do Everton

1. Confirmar RLP ativo, as condições de custo e a margem de day trade do WIN na Rico; confirmar o limite diário.
2. Escolher o destino da pilha cripto/meme na VPS (manter / **enxugar — recomendado** / mínimo da H-036 / parar), com
   os custos do plano §10.
3. Aprovar o desenho do painel B3 (arquitetural, `docs/design/b3-painel-de-sinais.md`, tarefa W0-2) e exportar o
   histórico sincronizado do MT5 para a H-038r.

## Segunda opinião

Diálogo com a Astra (seis rodadas; a 1.ª saiu vazia por erro de chamada): [[Dialogos/mercado-tradicional|mercado-tradicional]].

## Relacionado

[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Strategy Backlog]] ·
[[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] · [[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]] ·
[[2026-10-09-piloto-copiar-carteiras-no-papel]] · plano `docs/plans/MERCADO-TRADICIONAL.md`

- **2026-10-17 (mais tarde):** o Everton autorizou, com a palavra "autorizado", o robô da B3 com dinheiro real como exceção à Fase 4 (recusando a fase de papel e dispensando o Portão B de evidência). Escopo, o que continua obrigatório e revisão em 2026-12-31 em `docs/decisions/0007-robo-b3-mt5-excecao-live.md` (ADR 0007); desenho em `docs/design/robo-b3-mt5.md`. Ver [[Architecture Decisions]] → ADR 0007.

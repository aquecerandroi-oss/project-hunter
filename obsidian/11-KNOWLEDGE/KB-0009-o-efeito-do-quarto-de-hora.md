---
tags: [knowledge, nota, microestrutura, execucao, perpetuos]
tema: Volume e fluxo de ordens
fonte: "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures" (arXiv 2607.09426)
fonte_url: https://arxiv.org/html/2607.09426v1
lido_em: 2026-09-06
evidencia: preprint (arXiv), amostra ampla e método descrito
hipotese_testavel: sim
astra: concorda
---

# O efeito do quarto de hora

## O que afirma

Nos perpétuos USDT da Binance, as marcas de 0, 15, 30 e 45 minutos concentram atividade que parece
algorítmica e periódica. Nos **10 segundos iniciais** dessas marcas há cerca de 26% mais negócios,
32% mais volume em dólar e 26% mais retorno absoluto do que em janelas de minutos ordinários. O
diagnóstico dos autores para a origem é indireto e engenhoso: a fração de tamanhos de negócio com
números redondos **cai** nessas janelas (para BTC com dois ou mais zeros finais, a redondeza
padronizada cai cerca de 0,20 desvios no topo da hora, contra 0,04 em aberturas ordinárias) — humano
escolhe número redondo, máquina não.

Há autocorrelação positiva no fluxo assinado nas fases de quarto de hora. Fora de amostra, retornos
defasados de quarto de hora dão R² de +2,46%, e com 28 indicadores técnicos +3,37%, com AUC de
direção 0,601. **Mas o ganho bruto realizado é de cerca de 0,5 bps em 10 segundos, aproximadamente
um décimo de uma taxa taker padrão** — e os próprios autores dizem que isso serve para **ajuste de
execução**, não como estratégia isolada. Separadamente, o desequilíbrio de ordens na abertura do
quarto de hora prediz retornos de 4 a 12 horas à frente, enquanto aberturas de 1 e 5 minutos não têm
conteúdo preditivo. Os resultados se mantêm excluindo os três quartos de hora que coincidem com
liquidação de funding.

## Onde foi mostrado

BTC, ETH, XRP, SOL, DOGE e ADA, perpétuos USDT da Binance, de 01/01/2021 a 31/10/2024, com trades em
milissegundos agregados em barras de 10 s e 1 min. É o mercado exato que operamos — daí a nota.

Caveats dos autores: o diagnóstico de redondeza é comportamental, não causal; o efeito pode refletir
agrupamento institucional, liquidações ou convenção de mesas de execução, não só robôs; e as
magnitudes exigem execução de custo muito baixo.

## Como mediríamos aqui

**A premissa que eu tinha estava errada e a correção é o achado mais útil desta nota.** Eu ia
escrever que a `momentum_v1` entra dentro da janela disputada. Ela não entra. `decision_at` é lido do
relógio **depois** da avaliação (`decide.py`) e a abertura elegível é a da primeira barra de 1 min
**estritamente posterior** (`plan.py`). Com referência às 12:00:00 e `decision_at` às 12:00:11, a
entrada é às **12:01:00** — já fora dos 10 segundos de pico. O limite de 120 s conta desde
`source_bar_close` e só recusa acima de 120 (`plan.py`):

| `decision_at` | Entrada atual | Com um minuto a mais | Limite de 120 s |
|---|---|---|---|
| 12:00:11 | 12:01:00 | 12:02:00 | permitido |
| 12:01:11 | 12:02:00 | 12:03:00 | recusado |

**O que velas de 1 min permitem afirmar**, para uma marca `T` e a vela `[T, T+60s)`:
`10.000·(C/O − 1)` = deslocamento entre o primeiro e o último negócio do minuto; `10.000·(H/O − 1)`
e `10.000·(L/O − 1)` = extremos negociados relativos à abertura; `10.000·(O[T+60]/O[T] − 1)` =
diferença entre duas referências de entrada separadas por um minuto; volume, número de negócios e
amplitude = intensidade agregada.

**O que elas não permitem:** preço aos 10 segundos, sequência dos extremos dentro do minuto, bid/ask
no instante da ordem, profundidade, impacto do nosso tamanho, preço executável após latência, ou
recortar exatamente os 60 s posteriores a uma decisão às 12:00:11. Consequência direta:
`H/O − 1 > 6 bps` **não prova** slippage acima de 6 bps — pode ser movimento posterior à entrada; e
preço sintético dentro de `[L, H]` não prova execução possível para o nosso tamanho.

Novidade verificada pela Astra: `candles` guarda `volume` **e** `taker_buy_volume`
(`packages/core/hunter_core/db/models/market_data.py`, `persist_rows.py`), então
`desequilíbrio_1m = 2·taker_buy_volume/volume − 1` é calculável — **cobertura ainda não conferida no
banco**. Isso permite uma hipótese própria sobre o **primeiro minuto**; não reconstrói o
desequilíbrio de 10 segundos do artigo.

## Hipótese testável no Lab

**H1 — diagnóstico, não estratégia** (reformulada): *quanto o preço se desloca entre a referência, a
abertura elegível e o minuto seguinte, e quão sensível é o resultado aos custos assumidos?* Etapas:
(a) auditar o timing registrado — distribuição de `decision_at − source_bar_close`,
`entry_bar_open − source_bar_close`, confirmações e recusas; (b) medir `[T, T+60)`, a vela da entrada
efetivamente planejada e a diferença até a abertura seguinte, publicando medianas, caudas e
cobertura, e **separando** o movimento referência→entrada dos 6 bps adicionados por hipótese;
(c) sensibilidade do resultado a custos maiores, sem recalibrar os 6 bps.

**H2 — variante única de execução:** entrar na abertura **`baseline + 60 s`** (uma barra além da
atualmente elegível — não "a segunda barra depois da marca", que já é o baseline), mantendo o limite
de 120 s, os parâmetros e os níveis congelados, com geometria, saídas e funding recalculados e o
horizonte de 4 h contado de cada entrada. A escolha da alternativa é **congelada antes** da abertura;
nunca se observa o minuto para depois decidir qual abertura teria sido melhor (`confirm.py` já recusa
confirmação atrasada).

Relato: diferença **pareada de preço** e resultado **em bps e em R**, separadamente — R sozinho
engana, porque o denominador `P_entry − stop` muda com a entrada. **Todas** as recusas e censuras de
H2 aparecem; comparar só as operações sobreviventes favoreceria artificialmente a variante.

## Por que pode falhar

- **Confundir excursão com slippage.** Se o preço sobe 15 bps depois de uma execução barata,
  classificar esses 15 bps como custo produz calibração falsa. É o erro que H1 existe para não
  cometer.
- **Exclusão silenciosa em H2:** o atraso adicional pode ultrapassar 120 s ou perder a geometria.
- **Extrapolar o achado de 4–12 h.** Ele vem do desequilíbrio dos **10 primeiros segundos**, em
  regressões na amostra completa (distintas do teste fora da amostra de 10 s), e a decomposição
  aponta predominância do componente de **fluxo defasado**, não dos indicadores técnicos. Além
  disso, retorno acumulado em 4 h não é o resultado de uma operação com stop, alvo e invalidação
  antecipada. Serve como motivação de pesquisa, não como validação da `momentum_v1`.
- Mais volume e mais volatilidade **não** demonstram, por si, spread maior ou execução pior; a
  análise precisa separar por ativo, hora UTC, marca (00/15/30/45), fase efetiva de entrada e
  liquidez.
- Retrospectiva é exploração: período futuro reservado, dependência entre ativos por blocos, e a
  política de execução registrada como variante própria.

## Segunda opinião (Astra)

Concorda em priorizar medição e em testar o atraso sem presumir melhora, e lembra que 0,5 bps brutos
em 10 s não sustentam estratégia isolada depois de custos. Duas correções de premissa aceitas — e
são as mais importantes desta nota: (1) **a nossa entrada já ocorre depois do pico de 10 segundos**,
porque `decision_at` vem do relógio pós-avaliação e a abertura elegível é a do minuto seguinte
(12:00:11 → 12:01:00); (2) **temos suporte a fluxo agregado de 1 minuto** via `taker_buy_volume`.
Must-fix incorporados: não chamar excursão de slippage medido, não comparar baseline contra ele
mesmo, e não excluir silenciosamente as recusas de H2. Adotei a sequência dela (auditar timing →
H1 descritiva → uma única H2 → reportar preço e resultado separados → tratar o retrospectivo como
exploração) e a decisão de **não** mexer nos 6 bps com base neste artigo ou em OHLC.

Divergência: nenhuma.

## Relacionados

[[Strategy Backlog]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0002-momentum-e-reversao-em-cripto]] · [[EXP-0001-momentum-v1]] · [[Momentum Agent]] ·
[[Market Collector]] · [[Data Flow]]

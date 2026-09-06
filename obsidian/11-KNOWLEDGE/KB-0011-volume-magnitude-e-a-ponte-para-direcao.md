---
tags: [knowledge, nota, volume, microestrutura]
tema: Volume e fluxo de ordens
fonte: "Karpoff (1987), The Relation between Price Changes and Trading Volume: A Survey, JFQA 22(1) 109–126; Gervais, Kaniel & Mingelgrin (2001), The High-Volume Return Premium, Journal of Finance 56(3) 877–919"
fonte_url: https://ideas.repec.org/a/cup/jfinqa/v22y1987i01p109-126_01.html
lido_em: 2026-09-06
evidencia: estudo revisado (survey + estudo revisado), lido por resumos publicados — corpo completo não aberto
hipotese_testavel: sim
astra: concorda com correções (tese reformulada)
---

# Volume, magnitude e a ponte para direção

## O que afirma

Karpoff estabelece **duas** relações empíricas, e a diferença entre elas é o que esta nota carrega.
A primeira, robusta e repetida em quase todos os mercados estudados: volume é positivamente
relacionado à **magnitude** do movimento, `|Δp|`. A segunda, mais fraca e restrita: volume é
positivamente relacionado ao **próprio** movimento, com sinal — e essa só aparece consistentemente em
**mercados de ações**, com a hipótese de custo de venda a descoberto como explicação proposta.

**As duas são associações contemporâneas**, medidas no mesmo intervalo. Nenhuma delas é uma previsão
do movimento **seguinte**, e nenhuma delas autoriza a lei "volume não contém direção" — o survey não
diz isso. Esta é a correção mais importante que a Astra impôs a esta nota, e ela muda o desenho da
análise proposta lá embaixo.

Gervais, Kaniel & Mingelgrin, esses sim, estudam **retorno futuro**: ações com volume anormalmente
alto num dia ou numa semana tendem a se valorizar no **mês seguinte**, num corte transversal
long-short ajustado por tamanho. Os autores oferecem **visibilidade** como explicação *compatível*
com o resultado — não como mecanismo causal demonstrado. (Não reproduzo aqui as magnitudes do prêmio
porque não consegui conferir tabela, carteira e versão exatas no artigo publicado; a atribuição que
eu tinha escrito veio de resumo de terceiros e foi removida.)

## Onde foi mostrado

Karpoff: literatura de ações e futuros até 1987, majoritariamente dados diários dos EUA, sem custos
de transação no centro da análise. Gervais et al.: ações da NYSE, volume anormal em janela de dia ou
semana, retorno avaliado no mês seguinte, unidade de análise = **carteira transversal**.

Nada disso é cripto, nada disso é intradiário, e nada disso é uma operação isolada com stop, alvo e
invalidação. A distância é grande em quatro dimensões ao mesmo tempo (ativo, janela de medição,
horizonte, unidade de análise). **Isso não prova que não se transfere** — impede tratar como
validação. Serve de motivação para investigar.

**Uma correção de premissa minha, registrada porque eu tinha escrito o contrário:** a explicação de
Karpoff para a relação com sinal é o custo de venda a descoberto, que em perpétuo não existe — mas
daí **não** se segue que "short custa o mesmo que long" em perpétuo. Funding positivo transfere de
long para short e negativo faz o contrário, então a simetria de custo é condicional ao regime de
funding, não estrutural ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]).

## Como mediríamos aqui

O gatilho da `volume_anomaly_v1` tem **três** condições, não uma
(`packages/core/hunter_core/strategies/volume_anomaly_v1.py`):

| Condição | Linha | O que é |
|---|---|---|
| `volume / mediana(288 barras de 5m) ≥ 4` | 155 | magnitude |
| `close > (high + low)/2` | 162 | posição dentro da **amplitude** da barra |
| `0 ≤ return_5m ≤ 2 · atr_pct_15m` | 172, padrões na 74 | retorno **não negativo** com teto de exaustão |

E `return_5m` é `close_t / close_{t−1} − 1` — fechamento contra **fechamento anterior**, não contra a
abertura da própria barra (`strategies/indicators.py:150-160`). A decisão é explicitamente LONG
(linha 236).

Então a tese que eu tinha escrito ("a única evidência direcional é `close > bar_mid`") estava errada:
há **dois** filtros de preço, e eles já removem da coorte todo sinal com retorno negativo. A pergunta
correta não é "a estratégia tem evidência direcional?" — tem — e sim **qual é a contribuição
incremental de cada filtro**, que é o que ninguém mediu.

Consequência de desenho que segue disso, e que a Astra fez questão de marcar: como o filtro de preço
roda **antes** da emissão, a coorte emitida **não contém** o contrafactual. Qualquer leitura sobre
"o volume seleciona X" feita só dentro dos sinais emitidos mede a regra inteira, não o volume.

## Hipótese testável no Lab

**H-KB0011 — "Associação entre volume relativo e resultados dentro da coorte emitida"**, em duas
leituras separadas, e a separação é o ponto:

**(1) Diagnóstico operacional, sem interpretação causal.** Quartis de `volume_ratio_5m` (que está no
envelope imutável de todo sinal, `volume_anomaly_v1.py:212`), com **os quartis definidos antes** de
excluir os outcomes sem `R_net`, e reportando por quartil: contagens, exclusões e seus motivos,
maturação do horizonte, geometria (distância `entrada − stop` e `alvo − entrada`), custos em R,
expectancy, dispersão e modos de saída.

**(2) Hipótese de preço, que é a que responde à literatura.** Retorno **assinado** e **absoluto** do
preço até um horizonte fixo contado da decisão (por exemplo 30, 60 e 120 min), **independentemente**
de como a operação da estratégia terminou, com cobertura das velas verificada por caso. E — o passo
que torna a medida incremental — incluir também as barras **elegíveis que não passaram** do limiar de
volume, que hoje saem como `not_triggered: volume_below_threshold` (linha 155) e das quais não
guardamos registro. **Sem esse grupo de comparação não há como separar o efeito do volume do efeito
dos filtros de preço**, e essa é a limitação central desta análise.

**Por que não uso dispersão de `R_net` como medida de magnitude**, embora fosse o que eu tinha
escrito: `R_net` tem denominador `entrada − stop`, e nesta estratégia o stop é a **mínima da barra do
sinal** (linha 183). Barra maior → stop mais distante → mesmo movimento em preço vira **menos** R. A
distribuição de `R_net` mistura movimento, geometria, normalização, custos e regra de saída; usá-la
para testar "volume prevê magnitude" mediria as quatro outras coisas junto.

**O que (2) confirmaria:** `|retorno|` futuro crescente no quartil de volume, com retorno assinado
plano. **O que refutaria:** `|retorno|` futuro plano entre quartis — a associação de Karpoff é
contemporânea e não se estende ao intervalo seguinte neste mercado.

**O que nenhuma das duas prova:** que se deva mexer em `volume_mult`. Expectancy maior num quartil é
compatível com composição diferente de mercados, horários e exclusões de funding.

## Por que pode falhar

- **Confundir associação contemporânea com previsão.** O risco de leitura número um desta nota.
- **Coorte selecionada pela própria regra.** Sem as barras `not_triggered`, (2) não é incremental.
- **Seleção por disponibilidade de resultado.** Na leitura da VPS de 2026-09-06 há 352 avaliáveis,
  36 sem `R_net` por funding, restando 316, e os excluídos têm composição diferente no proxy sem
  funding ([[EXP-0002-volume-anomaly-v1]]). Definir quartis depois da exclusão embute essa
  composição no resultado.
- **Confusão entre volume, horário e mercado.** Quartis podem estar confundidos com hora UTC e com
  quais mercados aparecem; a intensidade dessa confusão **não foi medida**, então é um risco
  declarado, não um efeito conhecido.
- **Um único dia** com outcome avaliável, e 134 mercados simultâneos tratados como independentes
  seriam um erro de contagem.
- **Exploração, não confirmação.** Quatro quartis são quatro leituras sobre a população que gerou a
  suspeita ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0011-volume-magnitude.md`. **Cinco must-fix, todos aceitos e aplicados
antes de publicar**, e a nota mudou de tese por causa deles — inclusive o título:

1. **A tese estava forte demais.** O código tem dois filtros direcionais de preço, não um: `close`
   acima do meio da amplitude (linha 162) **e** retorno entre piso e teto em ATR% (linha 172, padrões
   na 74). E `return_n` é fechamento contra fechamento anterior (`indicators.py:156`), não contra a
   abertura. Cenário de falha que ela apontou: desenhar a comparação como se retornos negativos
   estivessem na coorte, atribuindo ao volume uma seleção que o filtro de preço já fez.
2. **Karpoff é associação contemporânea**, não previsão do intervalo seguinte, e não autoriza "volume
   não contém direção". Cenário de falha: H-KB0011 não achar dispersão futura e eu ler isso como
   refutação de uma relação contemporânea que continua verdadeira.
3. **Dispersão de `R_net` não identifica magnitude de preço** — o denominador `entrada − stop` escala
   com a própria barra (`pricing.py:74`, `volume_anomaly_v1.py:183`). Reescrevi a hipótese para
   retorno de preço a horizonte fixo. Esta foi a correção que mais mudou o desenho.
4. **A análise não é inútil, mas o que ela estima é limitado**: diferenças **entre sinais emitidos**,
   não o efeito isolado do volume. Daí a exigência do grupo `not_triggered` e de definir quartis antes
   de excluir os sem `R_net`.
5. **"Short custa o mesmo que long" está errado** — funding torna a simetria condicional.

Também aceitei três cortes dela: retirei as magnitudes do prêmio de Gervais et al. até poder conferir
a tabela na versão publicada; troquei "quartis medem hora do dia tanto quanto volume" por um risco
declarado e não medido; e passei "invalidação no quartil superior demonstra exaustão" a hipótese
entre explicações concorrentes. Corrigi a linha do envelope (212, não 214).

**Divergência:** nenhuma que sobreviva. Sobre Gervais et al. ela achou meu "não diz nada" exagerado e
tem razão — o correto é "não valida, e serve de motivação". O texto agora diz isso.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0014-taker-buy-volume-o-que-temos-medido]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[KB-0007-atr-e-escala-por-volatilidade]] ·
[[EXP-0002-volume-anomaly-v1]] · [[Volume Agent]] · [[Features]]

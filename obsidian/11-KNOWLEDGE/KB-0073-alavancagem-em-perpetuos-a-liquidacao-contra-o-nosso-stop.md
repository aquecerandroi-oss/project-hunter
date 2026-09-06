---
tags: [knowledge, nota, risco, alavancagem, perpetuos, liquidacao, margem]
tema: dimensionamento e risco / alavancagem em perpétuos
fonte: documentação da Binance sobre liquidação e margem em futuros USDⓈ-M; docs/RISK_ENGINE.md; docs/PIPELINE.md; nosso walker.py
fonte_url: https://www.binance.com/en/support/faq/detail/360033525271
lido_em: 2026-09-06
evidencia: documentação (lida) + leitura de código + aritmética própria
hipotese_testavel: sim
astra: pendente
---

# Alavancagem em perpétuos — a liquidação da exchange contra o nosso stop

## O que afirma

Num perpétuo há **dois** níveis de saída forçada, e só um deles é nosso:

- **O nosso stop**, a `1,5 × ATR` da referência — mediana medida de **1,52%** do preço de entrada.
- **A liquidação da exchange**, quando o colateral cai abaixo da margem de manutenção. A Binance
  descreve a condição como `colateral inicial + PnL realizado + PnL não realizado < margem de
  manutenção`, com `margin ratio = margem de manutenção / saldo de margem`, liquidação a 100% e
  recomendação de manter abaixo de 80%.

Enquanto o nosso stop estiver **muito dentro** da distância de liquidação, a liquidação é irrelevante
e o risco por operação é o que a nossa própria regra diz. A conta de quando isso deixa de ser verdade
é simples e vale a pena estar escrita.

Mas o achado desta nota não é esse. É outro: **o nosso stop e a liquidação da exchange são
disparados por preços diferentes, e o Lab usa um terceiro.** A Binance liquida pelo **mark price**; o
contrato do M4 diz que o stop é verificado por "toque no mark" (`docs/PIPELINE.md` §8); e o Shadow
Lab resolve tudo por **OHLC de velas de 1 min de negócios** (`walker.py:118-126`). São três
instrumentos, e as taxas de toque de stop que o Lab publica são medidas no terceiro.

## Onde foi mostrado

**Documentação da Binance (FAQ 360033525271), lida em 2026-09-06.** O que ela sustenta:

- Liquidação quando `colateral < margem de manutenção`; `margin ratio = MM / saldo de margem`;
  liquidação a 100% de razão de margem.
- **Margem cruzada (modo hedge):** posições long e short do mesmo símbolo compartilham **um** preço
  de liquidação. **Margem isolada:** preços de liquidação separados, com margem alocada
  individualmente.
- **Liquidação parcial primeiro** ("smart liquidation"): o sistema emite uma ordem IOC para reduzir a
  posição; se preencher parcialmente, a liquidação para. O que não preenche vira posição falida.
- **ADL (auto-deleveraging):** se o fundo de seguro não cobrir as posições falidas, o motor liquida
  automaticamente posições de contrapartes não falidas do lado oposto.

A última é a que costuma ser esquecida: **ADL fecha uma posição lucrativa nossa sem que nada nosso
tenha dado errado**. Não é risco de preço; é risco de contraparte sistêmico da exchange, e nenhum
stop protege dele.

**Não abriu**: a tabela de níveis de margem de manutenção por faixa de notional (a "leverage &
margin table") exige login. **Nenhuma taxa de margem de manutenção é citada nesta nota.** A conta
abaixo é feita em função de `mmr` como incógnita.

## Como mediríamos aqui

**A distância até a liquidação, em função da alavancagem.** Para uma posição comprada com
alavancagem `L` (notional / margem alocada) e taxa de margem de manutenção `mmr`, a queda percentual
aproximada que zera o excedente de margem é

```
d_liq ≈ 1/L − mmr
```

| Alavancagem `L` | `d_liq` com `mmr = 0,5%` | O nosso stop mediano (1,52%) está… |
|---|---|---|
| 1× | 99,5% | 65× dentro |
| 3× | 32,8% | 22× dentro |
| 10× | 9,5% | 6,3× dentro |
| 25× | 3,5% | 2,3× dentro |
| 50× | 1,5% | **no mesmo lugar** |
| 75× | 0,83% | **depois** da liquidação |

A leitura: **até cerca de 25× a liquidação não é a restrição ativa; o nosso stop é.** Acima disso a
exchange decide antes de nós, e a nossa regra de saída deixa de existir na prática. E o `mmr` não é
constante — cresce por faixa de notional, o que aperta a tabela justamente nas posições grandes.

**Onde a alavancagem entra sem ninguém pedir.** O `max_leverage` do contrato (1 / 2 / 3) é medido
como `notional / cash disponível`, e o `qty_by_cash = (cash_available × max_leverage) / entry_ref`.
Com `max_position_pct` de 5% e `max_total_exposure_pct` de 60% (Balanced), a exposição agregada
máxima é 0,6× o equity: **abaixo de 1× mesmo com todos os slots cheios**. Ou seja, no Balanced o
`max_leverage` não morde — é o `max_total_exposure_pct` que define a alavancagem efetiva. No
Aggressive (`max_total_exposure_pct = 1,00`, `max_leverage = 3`), a exposição chega a 1×, e ainda
assim `max_leverage` fica folgado.

**Conclusão que serve de recomendação:** `ENABLE_LIVE_TRADING = false` e **o M4 começar sem
alavancagem são decisões do Everton**, e as duas são compatíveis com os limites já escritos sem mudar
nada — porque a alavancagem efetiva no Balanced é 0,6× por construção. O que precisa mudar é o
**nome**: chamar de `max_leverage` um limite que nunca morde dá a impressão de controle onde ele não
está.

**Funding como custo de carregar, na nossa escala de tempo.** As durações medidas hoje (mediana de 12
a 21 min por desfecho; os únicos de 120 min são os 17 `expired`) tornam o funding quase irrelevante
como carrego: a maior parte dos acompanhamentos **não atravessa** uma liquidação de funding. Isso é
consistente com a [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]], e a ressalva dela
continua valendo: "excluído por `funding_missing`" significa atravessador **inferido**, não
confirmado. Funding importa para o M4 se e quando o horizonte crescer — e a candidata `L2` (saída sem
alvo) é exatamente uma que alonga o horizonte.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra.** Duas regras propostas ao Risk Engine, no [[Strategy Backlog]]:

- **`R-LEV-1` — margem isolada por posição no paper e no M4.** Motivo: com margem cruzada, uma
  posição perdedora consome a margem das outras e o preço de liquidação de todas se move junto — o
  risco deixa de ser por posição e vira de carteira, sem que nenhum limite do contrato registre isso.
  Com isolada, a perda máxima por posição é a margem alocada, que é exatamente o que
  `max_position_pct` promete. **Decisão do Everton**, porque é escolha de modo de conta na exchange.
- **`R-LEV-2` — checar a distância até a liquidação como um check próprio**, e não presumir que o
  stop chega primeiro: rejeitar quando `d_liq < k × stop_distance` com `k` declarado (a recomendação
  é `k = 3`). Dado necessário: a tabela de margem de manutenção por faixa, que **não temos** — exige
  ler `/fapi/v1/leverageBracket`, que é chamada autenticada. **Bloqueada por dado.**

**O que refutaria `R-LEV-2`:** se, com `ENABLE_LIVE_TRADING = false` e sem alavancagem, `d_liq` ficar
sempre uma ordem de grandeza acima do stop, o check nunca morde e é decoração — que é o resultado
esperado no começo do M4 e deve ser dito assim, e não escondido.

## Por que pode falhar

- **`d_liq ≈ 1/L − mmr` é aproximação.** Ignora taxas, funding acumulado, PnL de outras posições em
  margem cruzada, e a escada de `mmr` por faixa de notional. Serve para ordem de grandeza.
- **`mmr = 0,5%` na tabela é um valor ilustrativo escolhido por mim**, não medido: a tabela real não
  abriu sem login. Nenhuma conclusão desta nota depende do valor exato.
- **A ADL não tem defesa no nosso desenho, e nem deveria ter.** Registrar é o que dá para fazer.
- **A mediana de 1,52% de distância de stop é de 16 h sem stress.** Em stress o ATR sobe, o stop
  afasta, e a margem de segurança contra a liquidação **encolhe** — exatamente quando ela importa.
- **Os três instrumentos de preço (mark, último negócio, OHLC de vela) não foram comparados.** Que a
  diferença seja pequena é suposição minha, não medição. É o que a
  [[KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula]] registra como pendência.

## Segunda opinião (Astra)

Pendente nesta versão.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]]

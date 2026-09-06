---
tags: [knowledge, nota, risco, alavancagem, perpetuos, liquidacao, margem]
tema: dimensionamento e risco / alavancagem em perpétuos
fonte: documentação da Binance sobre liquidação e margem em futuros USDⓈ-M; docs/RISK_ENGINE.md; docs/PIPELINE.md; nosso walker.py
fonte_url: https://www.binance.com/en/support/faq/detail/360033525271
lido_em: 2026-09-06
evidencia: documentação (lida) + leitura de código + aritmética própria
hipotese_testavel: sim
astra: discorda em parte (correções aplicadas)
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

**A distância até a liquidação, em função da alavancagem.** Para uma posição **comprada, em margem
isolada, com manutenção proporcional ao notional corrente, sem taxas nem deduções de faixa**, a queda
percentual que zera o excedente de margem é (fórmula corrigida na revisão da Astra; a minha primeira
versão omitia o denominador):

```
d_liq = (1/L − mmr) / (1 − mmr)          [long]
d_liq = (1/L − mmr) / (1 + mmr)          [short]
```

| Alavancagem `L` | `d_liq` com `mmr = 0,5%` | O nosso stop mediano (1,52%) está… | Um stop de 5% (p99 do perfil) está… |
|---|---|---|---|
| 1× | 100,0% | 65,8× dentro | 20× dentro |
| 3× | 33,00% | 21,7× dentro | 6,6× dentro |
| 10× | 9,55% | 6,3× dentro | 1,9× dentro |
| 25× | 3,52% | 2,3× dentro | **depois** da liquidação |
| 50× | 1,51% | **praticamente no mesmo lugar** | depois |
| 75× | 0,84% | **depois** da liquidação | depois |

A leitura correta, e ela é diferente da que eu tinha escrito: **o cruzamento depende do stop, não só
da alavancagem.** Com o stop **mediano** de 1,52%, a liquidação só chega antes por volta de
**49,7×**. Com um stop de 5% — que está dentro da banda admissível do Balanced —, a liquidação já
chega antes a **25×**. Usar a mediana para dizer "até 25× estamos protegidos" **não protege a
posição de stop largo**, que é justamente a de mercado agitado. E o `mmr` não é constante: cresce por
faixa de notional, o que aperta a tabela nas posições grandes. Gaps podem ultrapassar os dois níveis
antes de qualquer preenchimento.

**Onde a alavancagem entra sem ninguém pedir.** O `max_leverage` do contrato (1 / 2 / 3) é medido
como `notional / cash disponível`, e entra por `qty_by_cash = (cash_available × max_leverage) /
entry_ref`. Com `max_position_pct` de 5% e `max_concurrent_positions = 6` (Balanced), seis posições
cheias somam **30%** do equity — e `max_total_exposure_pct = 60%` é um teto **independente**, que
essas seis posições não alcançam. A exposição agregada fica **bem abaixo de 1× o equity**.

> **Correção da revisão da Astra, em dois pontos.** (a) Eu tinha escrito que a exposição máxima do
> Balanced é 0,6× "por construção": não é — 6 × 5% = 30%; os 60% são outro limite. (b) **"O
> `max_leverage` nunca morde" exige uma hipótese sobre caixa livre que eu não declarei.**
> `exposição/equity` não é `notional/caixa disponível`. Cenário de falha: equity 10.000, caixa livre
> 200 depois de reservas, proposta de 500 → o `qty_by_cash` limita a **400**
> (`docs/RISK_ENGINE.md:88`). Antes de declarar redundância seria preciso provar que esse estado é
> impossível, e ele não é.
>
> E uma terceira, que atinge a regra `R-LEV-1` abaixo: **`max_position_pct` limita notional, não
> promete perda máxima igual à margem isolada.**

**Conclusão que serve de recomendação:** `ENABLE_LIVE_TRADING = false` e **o M4 começar sem
alavancagem são decisões do Everton**, e as duas são compatíveis com os limites já escritos. O que
precisa ficar claro é que o controle de alavancagem efetivo vem da combinação
`max_position_pct × max_concurrent_positions` e do caixa disponível — não do `max_leverage`.

**Funding como custo de carregar, na nossa escala de tempo.** As durações medidas hoje (mediana de 12
a 21 min por desfecho; os únicos de 120 min são os 17 `expired`) tornam o funding quase irrelevante
como carrego: a maior parte dos acompanhamentos **não atravessa** uma liquidação de funding. Isso é
consistente com a [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]], e a ressalva dela
continua valendo: "excluído por `funding_missing`" significa atravessador **inferido**, não
confirmado. Funding importa para o M4 se e quando o horizonte crescer — e a candidata `L2` (saída sem
alvo) é exatamente uma que alonga o horizonte. **Ressalva da revisão: duração mediana curta não
demonstra que o funding seja economicamente irrelevante** — demonstra que a maioria dos
acompanhamentos não atravessa um ciclo. A cauda longa da distribuição, e o custo realizado por
acompanhamento, continuam por medir (`D-MEME-FUND`).

## Hipótese testável no Lab

**Nenhuma no Lab de sombra.** Duas regras propostas ao Risk Engine, no [[Strategy Backlog]]:

- **`R-LEV-1` — margem isolada por posição no paper e no M4.** Motivo: com margem cruzada, uma
  posição perdedora consome a margem das outras e o preço de liquidação de todas se move junto — o
  risco deixa de ser por posição e vira de carteira, sem que nenhum limite do contrato registre isso.
  Com isolada, a perda máxima por posição é a margem alocada, que é exatamente o que
  `max_position_pct` promete — **com a ressalva da revisão de que `max_position_pct` limita notional
  e não promete perda máxima igual à margem alocada**. **Decisão do Everton**, porque é escolha de
  modo de conta na exchange.
- **`R-LEV-2` — checar a distância até a liquidação como um check próprio**, e não presumir que o
  stop chega primeiro: rejeitar quando `d_liq < k × stop_distance` com `k` declarado (a recomendação
  é `k = 3`). Dado necessário: a tabela de margem de manutenção por faixa, que **não temos** — exige
  ler `/fapi/v1/leverageBracket`, que é chamada autenticada. **Bloqueada por dado.**

**O que refutaria `R-LEV-2`:** se, com `ENABLE_LIVE_TRADING = false` e sem alavancagem, `d_liq` ficar
sempre uma ordem de grandeza acima do stop, o check nunca morde e é decoração — que é o resultado
esperado no começo do M4 e deve ser dito assim, e não escondido.

## Por que pode falhar

- **A fórmula é aproximação de um modelo declarado** (long, isolada, manutenção proporcional ao
  notional corrente). Ignora taxas, funding acumulado, PnL de outras posições em margem cruzada, e a
  escada de `mmr` por faixa de notional. Serve para ordem de grandeza.
- **`mmr = 0,5%` na tabela é um valor ilustrativo escolhido por mim**, não medido: a tabela real não
  abriu sem login. Nenhuma conclusão desta nota depende do valor exato.
- **A ADL não tem defesa no nosso desenho, e nem deveria ter.** Registrar é o que dá para fazer.
- **A mediana de 1,52% de distância de stop é de 16 h sem stress.** Em stress o ATR sobe, o stop
  afasta, e a margem de segurança contra a liquidação **encolhe** — exatamente quando ela importa.
- **Os três instrumentos de preço (mark, último negócio, OHLC de vela) não foram comparados.** Que a
  diferença seja pequena é suposição minha, não medição. É o que a
  [[KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula]] registra como pendência.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-sizing-risk-2.md`). **Duas correções aplicadas
acima:**

1. **A fórmula estava incompleta.** O correto, para long isolado com manutenção proporcional ao
   notional corrente, é `d = (1/L − mmr)/(1 − mmr)`; para short o denominador é `1 + mmr`. Com os
   valores ilustrativos, o stop de 1,52% cruza a liquidação perto de **49,69×**, e **não** logo acima
   de 25×. Cenário de falha da minha versão: a 25×, um stop de 5% já fica além da liquidação de
   ~3,52% — usar a mediana para declarar proteção deixa desprotegida a posição de stop largo.
2. **"`max_leverage` nunca morde" exige hipótese sobre caixa livre.** Cenário: equity 10.000, caixa
   livre 200, proposta 500 → `qty_by_cash` limita a 400. E seis posições de 5% somam **30%**, não
   60%.

Também: `max_position_pct` limita **notional**, não promete perda máxima igual à margem isolada; e
duração mediana curta **não** demonstra funding irrelevante.

**Concordou com:** que a diferença de preços que importa é **mark contra negócios** — o contrato
prevê stop no mark (`PIPELINE.md:189`) e o walker observa velas (`walker.py:71`).

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]]

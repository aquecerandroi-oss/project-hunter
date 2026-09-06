---
tags: [knowledge, nota, risco, drawdown, kill-switch, circuit-breaker]
tema: dimensionamento e risco / drawdown, kill switch e circuit breakers
fonte: Grossman & Zhou (1993, Mathematical Finance) em resumo; busca por evidência de limite de perda diária; docs/RISK_ENGINE.md; medição própria na VPS
fonte_url: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9965.1993.tb00044.x
lido_em: 2026-09-06
evidencia: estudo revisado lido em resumo (Grossman & Zhou) + **anedótico/vendedor** (limites diários) + aritmética própria
hipotese_testavel: sim
astra: pendente
---

# Drawdown e kill switch — o que é evidência, o que é convenção, e o multiplicador que não multiplica nada

## O que afirma

Três coisas, e a terceira é a que importa mais:

1. **O limite de drawdown tem formalização revisada.** Grossman & Zhou (1993) resolvem exatamente o
   problema de investir sob a restrição `W_t ≥ α·M_t`, onde `M_t` é o máximo de riqueza já atingido.
   É um problema de otimização com restrição, não uma regra de bolso.
2. **O limite de perda diária não tem.** A busca por evidência devolveu **exclusivamente material de
   *prop firm* e de fornecedor** — Topstep, Apex, CrossTrade, MyFundedCapital e afins — com números
   ("2 a 4% do saldo inicial", "3% é o máximo que alguém deveria perder num dia") **sem fonte nem
   método**. Nenhum deles é citado aqui como evidência. E o mecanismo que essas páginas invocam —
   impedir *revenge trading*, "externalizar a decisão de parar" — **não se aplica a nós**: não há
   humano no laço. É o mesmo argumento que tirou Mark Douglas do backlog
   ([[KB-0055-douglas-o-livro-que-nao-vira-hipotese]]).
3. **O `ks_multiplier` e o `regime_size_multiplier` do nosso contrato são inertes na população que
   medimos.** Ambos multiplicam apenas `risk_usdt`, que entra só no `qty_by_risk` — e o `qty_by_risk`
   **nunca é o mínimo** em nenhuma das 992 entradas medidas
   ([[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]). Passar o kill switch para
   `WARNING` **não reduziria tamanho nenhum**.

## Onde foi mostrado

**Grossman & Zhou, *Mathematical Finance* 3(3):241-276 (1993).** Primeiro tratamento completo do
problema em horizonte infinito num modelo lognormal: maximizar a taxa de crescimento de longo prazo
sujeito a nunca cair abaixo de uma fração `α` do máximo histórico. Cvitanić e Karatzas estenderam
depois para o caso multivariado. **Declaração de leitura: li o resumo e a ficha bibliográfica; o
artigo está atrás de paywall na Wiley e não foi aberto.** A observação de que um drawdown acima de
~25% costuma ser motivo para demitir um gestor aparece atribuída aos autores em fonte secundária, e
**não** foi conferida no original.

**Busca por evidência de limite de perda diária (2026-09-06).** Termos: evidência acadêmica de
parada diária, disciplina e desempenho. Resultado: nove links, **todos comerciais**. Registro isso
como resultado da busca, do mesmo jeito que a quarta rodada registrou a busca por stops por ATR ter
devolvido só material de fornecedor. **A ausência de evidência aberta não prova que a regra seja
ruim** — prova que ela não pode ser justificada por evidência.

**O multiplicador inerte, na aritmética do contrato.** `docs/RISK_ENGINE.md` §4:

```
risk_usdt       = equity × risk_per_trade_pct × regime_multiplier × ks_multiplier
qty_by_risk     = risk_usdt / (entry_ref × stop_distance)
qty_by_position = (max_position_pct × equity) / entry_ref
qty             = floor_to_step(min(todos), step_size)
```

`ks_multiplier` (0,5 em `WARNING`) e `regime_multiplier` (0,5 em `BTC_BEAR_LONG`, 0,7 em
`HIGH_VOLATILITY`) aparecem **só** dentro de `qty_by_risk`. Medido: `qty_by_risk < qty_by_position`
exigiria `stop_distance > 10%`, e a maior distância observada em 992 entradas foi **9,32%**. Com os
dois multiplicadores em 0,5 simultaneamente o limiar cai para 2,5% — aí sim `qty_by_risk` passaria a
morder em parte da população (a mediana da `momentum_v1` é 1,52%, mas o p90 é 3,52%). **Com um só
multiplicador em 0,5, o limiar é 5% e praticamente nada muda.**

Cenário de falha concreto: o kill switch de organização vai para `WARNING` porque a perda do dia
passou de 70% do limite; o painel mostra "entradas permitidas com tamanho × 0.5"; e as próximas
posições abrem **exatamente do mesmo tamanho**. Ninguém percebe, porque não há nada que compare o
tamanho pedido com o tamanho obtido.

**A escala do limite diário, na nossa vazão.** Com risco efetivo por operação de **0,076% do equity**
(Balanced, na mediana medida), um `max_daily_loss_pct` de 2% equivale a **26,3 perdas cheias de 1 R**.
A duração mediana dos acompanhamentos encerrados, medida hoje na VPS:

```
   result    |  n  | mediana_min | p90_min
-------------+-----+-------------+---------
 target      | 290 |        21.0 |    73.1
 stop        | 292 |        12.0 |    48.0
 expired     |  17 |       120.0 |   120.0
 invalidated | 387 |        14.0 |    44.0
```

Com `max_concurrent_positions = 6` e giro mediano de ~14 min, a vazão é de ~26 posições por hora.
**O limite diário de 2% pode ser alcançado em cerca de uma hora ruim.** Ele não é folga; é uma
restrição que morde no primeiro dia adverso — e essa é uma informação que não existia.

## Como mediríamos aqui

**A reformulação honesta do limite diário.** Se o mecanismo comportamental não se aplica, sobra um
mecanismo que se aplica e é melhor:

> Um limite de perda diária é um **detector de falha de instrumento ou de mudança de regime**, não um
> instrumento de disciplina. Uma sequência de perdas fora da distribuição esperada é evidência barata
> de que algo quebrou — dado defasado, funding errado, mercado em stress, estratégia fora do regime —
> e parar é a resposta certa a essa evidência mesmo quando o modelo está certo, porque o custo de
> parar por engano é pequeno e o custo de continuar quebrado não é.

Essa formulação muda o que se mede: em vez de "quanto o dono aguenta perder", a pergunta vira "a
partir de quantas perdas seguidas a hipótese de funcionamento normal fica implausível?" — que é uma
pergunta com resposta, assim que houver expectancy com janela futura reservada. **Hoje não há**, e
por isso o limite continua sendo tolerância declarada.

**Drawdown contra perda diária: são instrumentos diferentes.** O drawdown é do pico de equity e não
reinicia; a perda diária reinicia à meia-noite UTC. Um sistema pode perder 1,9% por dia durante dez
dias sem nunca acionar o limite diário e acumular 17% de drawdown. **Os dois limites do contrato
(`max_daily_loss_pct` e `max_drawdown_pct`) não são redundantes**, e o segundo é o que efetivamente
protege o capital.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra** — não há equity, e `PnL de carteira` e `Max Drawdown de carteira` são
*não aplicável* por decisão registrada.

Três regras propostas ao Risk Engine, no [[Strategy Backlog]]:

- **`R-KS-1` — o multiplicador tem de multiplicar.** Aplicar `ks_multiplier` e `regime_multiplier` ao
  **tamanho final**, depois do mínimo, e não só a `qty_by_risk`. **Cenário de falha se não for
  feito:** o de cima. Custo: uma linha. É a mudança de maior alavancagem desta rodada inteira.
- **`R-KS-2` — o degrau publicado.** Toda transição de kill switch grava o tamanho médio pedido antes
  e depois, para que "reduzimos exposição" seja verificável. Sem isso `R-KS-1` volta a ser
  inverificável do mesmo jeito.
- **`R-DD-1` — limite de drawdown do pico de equity, com escopo de portfolio**, já no contrato, e
  **não** automaticamente reduzido a limite diário. Valores: **decisão do Everton**. A recomendação é
  `max_daily_loss_pct = 0,02` e `max_drawdown_pct = 0,10` como ponto de partida do Balanced — os
  valores que já estão na página —, **com a ressalva medida acima**: 2% ao dia é cerca de uma hora
  ruim na vazão atual, não uma folga confortável.

**O que refutaria `R-KS-1`:** nada; é correção de coerência. O que a tornaria desnecessária é
descobrir que `qty_by_risk` passa a ser o limitante dominante numa população futura — verificável com
o `R-PROV-1`.

## Por que pode falhar

- **A aritmética de "26 perdas em uma hora" supõe que todas as 26 sejam perdas cheias de 1 R.** Elas
  não são: 387 dos 986 desfechos terminais foram invalidações, que saem por outro preço. É um cenário
  extremo, e vale como ordem de grandeza, não como previsão.
- **A vazão medida é a da sombra sem restrição.** Com 6 slots, o próprio Risk Engine reduziria o
  número de tentativas — mas também concentraria as perdas nos slots ocupados.
- **`max_concurrent_positions = 6` e giro de 14 min dão 26/h por aritmética simples**, ignorando que
  o rearme de slot não é instantâneo.
- **Grossman & Zhou é um modelo lognormal de horizonte infinito** com um único ativo arriscado. A
  transferência para dezenas de perpétuos correlacionados com custo de transação não está
  demonstrada; o que se transfere é a **forma** da restrição.
- **A ausência de evidência aberta para o limite diário não é evidência de ausência.** Pode haver
  literatura que a minha busca não alcançou.

## Segunda opinião (Astra)

Pendente nesta versão.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0067-a-fracao-de-risco-por-operacao-e-o-preco-de-errar-a-expectancy]] ·
[[KB-0074-risco-operacional-as-regras-de-nao-operar-quando]] ·
[[KB-0055-douglas-o-livro-que-nao-vira-hipotese]] ·
[[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]]

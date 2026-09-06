---
tags: [knowledge, nota, perpetuos, funding, qualidade-do-dado]
tema: Perpétuos: funding, OI, posicionamento
fonte: Documentação da Binance sobre a taxa de funding e sobre Mark Price / Price Index; leitura do nosso próprio código (`hot_state.py`, `hotstate.py`, `deriv.py`, `detectors.py`)
fonte_url: https://www.binance.com/en/support/faq/detail/360033525031 · https://www.binance.com/en/support/faq/detail/360033525071
lido_em: 2026-09-06
evidencia: documentação da corretora + leitura de código com arquivo e linha (SQL de confirmação **não** rodado)
hipotese_testavel: sim
astra: pendente
---

# O que a nossa `funding_rate` mede de fato

## O que afirma

A feature `funding_rate` do M2 **não é** "a taxa que este mercado vai pagar". Ela é o último valor
que caiu no hash `mkt:*:deriv`, e esse valor tem **dois sabores diferentes** que o nosso código
distingue na escrita, transporta até o `MarketContext` e depois **ignora** na hora de calcular:

- `funding_kind = "estimated"` — leitura do stream `markPrice` (`streams.py:261`, cadência de 1 s),
  que é a taxa **em formação** para a próxima liquidação. Como a corretora a recalcula ao longo de
  todo o período, o mesmo campo carrega estados diferentes conforme a fase do ciclo. Quanto disso é
  ruído em cada fase eu **não medi**, e não afirmo.
- `funding_kind = "realized"` — a taxa **liquidada**, de `/fapi/v1/fundingRate`. Só existe três
  vezes por dia na cadência padrão.

`hot_state.py:308-328` grava as duas coisas no mesmo campo `funding_rate` do mesmo hash, marcando o
sabor em `funding_kind`. `hotstate.py:278,280` decodifica `funding_kind` e `next_funding_time` para
dentro do `DerivSnapshot`. A API mostra os dois (`apps/api/hunter_api/schemas/markets.py:169`).
**Nenhum calculador de feature lê qualquer um dos dois** — `FundingRate.compute` (`deriv.py`)
devolve `snapshot.funding_rate` e pronto.

O docstring do próprio `DerivSnapshot` (`context.py:128-132`) já diz o que está faltando, com todas
as letras: a mesma taxa significa coisas diferentes oito horas e dois minutos antes da liquidação.
Ele afirma que a T2.3 precisa de `next_funding_time` "para ler uma taxa de funding". A T2.3 foi
entregue e o `FUNDING_ANOMALY` (`detectors.py:177`) lê `funding_rate` cru, com linha de base sazonal
por hora do dia. Como a grade padrão é 00/08/16 UTC, a sazonalidade por hora **captura parte** da
fase do ciclo por acidente de alinhamento — não porque alguém tenha modelado o tempo até a
liquidação.

## Onde foi mostrado

Documentação do produto que operamos, lida em 2026-09-06, e o nosso código. Da documentação da
Binance, o que importa para esta nota:

- A taxa é `Prêmio médio P + clamp(Juros − P, ±0,05%)`, com o componente de juros em 0,01% por
  intervalo de 8 h no padrão.
- O **índice de prêmio** vem de preços de impacto (bid/ask que absorveriam a nocional de impacto,
  ~200 USDT de margem), amostrados a cada 5 s ao longo do período.
- Teto e piso ligados à margem de manutenção (0,75× para os pares maiores; ±2% para vários
  outros), com margem para a corretora ajustar em volatilidade extrema.
- **A cadência não é fixa.** Ao bater teto ou piso, o intervalo comprime para **1 hora**; volta a
  **4 horas** depois de 16 ciclos horários consecutivos abaixo de ±0,025%.
- O pagamento é entre traders; a corretora não cobra taxa sobre ele.

E do documento de Mark Price, o detalhe que muda uma conclusão inteira (ver
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]]): o **Mark Price é a mediana de
três candidatos**, e um deles é o índice ajustado por `última taxa de funding × (tempo até a próxima
liquidação / período)`. Ou seja, `mark_price` **carrega o funding dentro de si por construção**.

## Como mediríamos aqui

Tudo já está no `MarketContext`; nada precisa ser coletado. O que falta é usar:

1. `funding_kind` no instante da decisão (`estimated` | `realized` | ausente).
2. Idade da leitura: `as_of − funding_ts` — e aqui vale a distinção que a Astra pediu, porque são
   duas idades diferentes: a do **evento** na corretora e a do **recebimento** no nosso hash. Só a
   segunda é o que `funding_ts` guarda hoje.
3. Fase do ciclo: `next_funding_time − as_of`, em segundos, com dois casos que precisam de nome
   próprio — horário **vencido** (a corretora não atualizou) e horário **ausente**.

Os três entram no envelope imutável do sinal **sem alterar decisão nenhuma** — é o padrão
"observar sem decidir" que a segunda rodada estabeleceu em
[[KB-0014-taker-buy-volume-o-que-temos-medido]]. O caminho efetivo por onde isso passa (quem escreve
o envelope, em que ponto) precisa ser levantado antes de estimar esforço; não é "uma linha por
campo", como eu tinha escrito.

## Hipótese testável no Lab

**Não é candidata de estratégia. É um requisito de instrumento, e depois uma feature.**

*Etapa 1 (medição, sem decisão).* Persistir `funding_kind`, a idade do `funding_ts` e o tempo até
`next_funding_time` no envelope de todo sinal. A pergunta que isso responde em poucos dias: qual é a
**mistura** de sabores nas decisões que tomamos? Se 100% for `estimated`, então toda leitura de
funding do Lab é uma previsão da corretora sobre a própria liquidação seguinte, e nenhuma nota
futura pode chamá-la de "a taxa paga".

*Etapa 2 (feature nova, só depois da etapa 1).* `time_to_funding_s = next_funding_time − as_of`,
com `missing_input` quando a corretora não publicou o horário. Com ela, a dupla
`(funding_rate, time_to_funding_s)` passa a ser lida como um estado, e o `FUNDING_ANOMALY` pode um
dia condicionar a linha de base à fase do ciclo em vez de à hora do dia.

*Refutação da etapa 2, corrigida:* a versão anterior desta nota dizia "se a distribuição for
uniforme, a feature não acrescenta nada". A Astra derrubou: uniformidade da distribuição não implica
ausência de informação. A refutação defensável é outra e é comparativa — **`time_to_funding_s` só
sobrevive se, sobre a mesma população e a mesma especificação congelada, condicionar a linha de base
à fase do ciclo mudar a taxa de disparo do `FUNDING_ANOMALY` além de uma margem declarada antes da
medição**. Sem esse contraste, a feature é ideia, não candidata.

## Por que pode falhar

- **A cadência muda.** Um mercado no teto liquida de hora em hora; `next_funding_time` continua
  correto (vem da corretora), mas qualquer conta nossa que assuma 8 h fica errada exatamente no
  regime interessante. Isso não é hipótese: é o que a documentação diz, e é a raiz do problema
  medido em [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]].
- **`estimated` é volátil por desenho.** Tratar variação de `funding_rate` como informação sobre o
  mercado quando ela é o índice de prêmio se formando é confundir instrumento com fenômeno.
- **Documentação de corretora muda sem aviso.** Os números acima têm data de leitura; qualquer nota
  que os cite daqui a seis meses precisa reler.
- **Acoplamento oculto:** como o Mark Price embute a última taxa de funding, features derivadas de
  `mark_price` não são independentes de `funding_rate`.

## Segunda opinião (Astra)

Confirmou a leitura de código: `funding_kind` e `next_funding_time` chegam ao `MarketContext`
(`hotstate.py:278,280`) e nenhum calculador os lê. Correções aceitas: (1) retirar "oito horas antes
da liquidação é quase ruído" — não medi, e a frase é uma opinião com cara de dado; (2) retirar "custa
uma linha por campo" — o caminho de instrumentação não foi levantado; (3) trocar a refutação por
uniformidade da distribuição por um contraste com margem econômica declarada antes da medição; (4)
separar **idade do evento** de **idade de recebimento**, e nomear os casos de horário vencido e
intervalo desconhecido. Frase dela que fica como núcleo da nota: a feature conserva a taxa publicada,
mas não interpreta nem tipo nem fase.

Divergência: nenhuma.

## Relacionados

[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0020-funding-change-8h-nunca-calcula]] ·
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[Strategy Backlog]] · [[Features]] · [[Anomalies]] · [[Market Collector]]

---
tags: [knowledge, nota, perpetuos, liquidacoes, fluxo, coleta]
tema: Volume e fluxo de ordens
fonte: "Documentação de WebSocket da Binance USDⓈ-M, Liquidation Order Streams e All Market Liquidation Order Streams (forceOrder); \"Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades\" (arXiv:2607.27070)"
fonte_url: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams
lido_em: 2026-09-06
evidencia: documentação da corretora + preprint (arXiv, sem revisão) + medição própria da série já coletada
hipotese_testavel: sim
astra: concorda com correções (a série já existe; medição proposta era não identificável)
---

# Liquidações: o fluxo forçado que observamos por amostragem

## O que afirma

Liquidação em perpétuo é volume agressor que **não escolheu** existir. Em
[[KB-0014-taker-buy-volume-o-que-temos-medido]] esse volume entra no `taker_buy_volume` sem etiqueta,
e é **uma** das razões pelas quais "comprador agressor" não significa "comprador informado" — não
necessariamente a principal, porque a importância relativa dela contra outras motivações não foi
medida por ninguém aqui.

**O contrato da Binance impõe amostragem, e o detalhe importa.** Tanto `<symbol>@forceOrder` quanto
`!forceOrder@arr` publicam **a última** ordem de liquidação **por símbolo** dentro de cada janela de
1000 ms; sem liquidação na janela, nenhum evento. O limite do stream agregado é **por símbolo**, não
uma ordem para o mercado inteiro. (Eu tinha escrito "a maior" para o stream por símbolo; está
corrigido — é a mais recente nos dois.)

A consequência tem de ser enunciada com cuidado, e a minha primeira versão exagerou:

- múltiplas ordens na mesma janela **implicam omissão**;
- maior concentração temporal **favorece** omissões;
- mas **a fração do notional omitido não cresce necessariamente de forma monótona com a
  intensidade** — depende dos tamanhos e da ordem de chegada. Duas ordens de 99 e 1 deixam observar
  1%; dez pequenas seguidas de uma enorme deixam observar quase tudo. O contrato **não fornece uma
  curva** de subestimação por intensidade, e afirmar "quanto pior a cascata, maior a subestimação"
  como lei é inventar essa curva.

O preprint de 2607.27070 estuda sete cascatas de BTCUSDT perpétuo na Binance (maio/2022 a
outubro/2025, inclusive o evento de 10/10/2025), com preço em 1 min e métricas de alavancagem e fluxo
em 5 min, testando variância móvel de resíduos destendenciados e autocorrelação de defasagem 1.
**Nenhuma variável é invariante entre eventos**: preço carrega a assinatura em cinco dos sete e é
silencioso nos dois choques de notícia. A única regularidade populacional é uma **compressão** da
variância do fluxo taker — e, precisando: o estudo trabalha com **resíduos do log da razão taker
buy/sell**, não com volume bruto. Sobrevive a placebo contra 300 janelas comuns, mas é **precursor
populacional, não alarme por evento** (dois dos seis eventos se sobrepõem à nula), e o padrão
in-sample de outubro/2025 **inverteu** fora de amostra em agosto/2024.

Enunciado correto do que isso autoriza: **este preprint não valida um alarme por evento**. Um
resultado negativo limitado não prova impossibilidade geral.

## Onde foi mostrado

Binance USDⓈ-M, BTCUSDT, sete eventos, janelas de ~2 meses. Mercado exato do nosso Lab, ativo único,
amostra pequena. Os próprios autores registram que a microestrutura intradiária de liquidação **não
é observável** — eles veem consequências, e as variáveis de alavancagem são proxies de um estado que
não se mede.

## Como mediríamos aqui

**A premissa da minha primeira versão estava errada: nós já coletamos.** O caminho existe inteiro e
está em produção:

| Etapa | Onde |
|---|---|
| Canal `LIQUIDATIONS` entre os do worker | `services/market-worker/hunter_market_worker/ingest.py:62` |
| Assinatura | `market-worker/streaming.py:45` |
| Mapeamento do canal para `forceOrder` | `hunter_exchanges/binance/streams.py:57` |
| Parser | `hunter_exchanges/binance/streams.py:285-300` |
| Persistência (qty, price, notional, `source="ws"`) | `market-worker/persist_rows.py:217` |

E a série tem conteúdo. VPS, leitura de 2026-09-06:

```sql
select side, count(*) linhas, count(distinct market_id) mercados,
       min(ts) primeiro, max(ts) ultimo
from liquidations group by side;
```

```
 side | linhas | mercados |          primeiro          |           ultimo
------+--------+----------+----------------------------+----------------------------
 buy  |   3864 |      173 | 2026-09-05 22:41:13.528+00 | 2026-09-06 15:07:23.068+00
 sell |   4557 |      197 | 2026-09-05 22:43:09.375+00 | 2026-09-06 15:07:44.19+00
(2 rows)
```

8421 eventos em ~16 h, 197 mercados no lado vendedor. **Não é uma coleta a planejar; é uma série a
auditar.**

**E há um defeito de semântica a auditar primeiro.** O parser calcula o notional como `q × p`
(`streams.py:293`), onde `q` é a **quantidade original** da ordem e `p` o **preço da ordem**. A
Binance distingue isso de `z` (quantidade executada acumulada) e `ap` (preço médio de execução). Uma
ordem original de 10 a 100, executada parcialmente em 1 a 100, produz notional 1000 no nosso banco
contra 100 executados. **Consequência direta: a soma da coluna `notional` não é necessariamente um
limite inferior do executado** — pode superestimar por ordem e subestimar por omissão de janela, ao
mesmo tempo, em direções que não se cancelam de forma conhecida. Isso é bug de semântica, e vai para
[[Open Bugs]] com este cenário.

O detector `LIQUIDATION_CLUSTER` continua **desarmado**, e continua certo que esteja: declarado com
`liquidation_pressure_1h` e motivo `feature_not_implemented`
(`packages/indicators/hunter_indicators/anomalies/detectors.py:185`), construído com `enabled=False`
(linha 237). Precisão de contrato: na avaliação o motivo externo é `detector_disabled`, e
`feature_not_implemented` vai como **detalhe** (`anomalies/evaluation.py:154`); o `MarketContext` não
tem entrada de liquidações (`features/context.py:188`).

## Hipótese testável no Lab

**H-KB0017 — auditoria de observabilidade da série existente, e não "medir a perda".** A medição que
eu tinha proposto — comparar a série contra o excedente de volume agressor das velas — **não
identifica nada**. Com `A` = volume agressor observado, `L` = liquidações executadas, `U` = demais
execuções agressoras e `S` = liquidações observadas no snapshot:

```
A = L + U     ⇒     A − S = (L − S) + U
```

O resíduo mistura **liquidações omitidas com fluxo voluntário**, e `U` varia livremente. Mesmos
`A = 100` e `S = 10` são compatíveis com `L = 10, U = 90` (perda zero) e com `L = 90, U = 10` (perda
de 80). Mesmas velas, mesmos snapshots, perdas radicalmente diferentes — não identifica nem a ordem
de grandeza. **Medir a fração realmente perdida exigiria uma referência independente e
comprovadamente completa do mesmo mercado e período**, e outro distribuidor do mesmo `forceOrder`
não serve.

O que se pode medir, com o que cada medida permite concluir:

| Medida | Interpretação defensável |
|---|---|
| Tempo conectado e assinado, atrasos, reconexões, descartes locais | Qualidade do **coletor** — não ausência de perdas na origem |
| Fração de intervalos com snapshot e persistência das sequências | Atividade **observada**; não contagem total de liquidações |
| Quantidades executadas por lado, **após corrigir a semântica `q`/`z`, `p`/`ap`** | Intensidade da amostra recebida |
| Associação com retorno, volatilidade, spread e profundidade | Contexto de estresse; não identificação causal |
| Ganho em **janela futura** sobre uma baseline de preço e volume | Utilidade incremental para um objetivo declarado antes |

Silêncio durante desconexão permanece **desconhecido**, nunca "zero liquidações".

**O que retirei:** o critério "se a subestimação explodir na cascata, a série é inútil". Uma série
inadequada para estimar volume total pode preservar informação sobre **presença e persistência** de
atividade forçada; descartá-la pela perda de volume eliminaria uma variável possivelmente útil. E,
no sentido inverso, subestimação estável tampouco demonstra utilidade.

**Nenhuma estratégia é proposta aqui.** A leitura defensável para um produto é de **risco**: cascata
é o regime em que a fragilidade dos custos assumidos (2 bps de spread total, 5 bps de slippage por
lado) e da entrada na abertura seguinte é maior — **hipótese de fragilidade, ainda não medida**, não
constatação ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]).

## Por que pode falhar

- **Somar `notional` e chamar de volume liquidado** — agora com dois defeitos somados: a omissão da
  janela de 1 s e o `q × p` que pode superestimar a ordem.
- **Tratar `A − S` como perda** — o erro que esta revisão corrigiu: não é identificável.
- **Inventar uma curva de subestimação por intensidade** que a documentação não fornece.
- **Sete eventos, um ativo, uma corretora, preprint.** E compressão de variância é precursor
  populacional, não alarme.
- **Conexão saudável ≠ ausência de perdas na origem.**
- **Escopo.** Corrigir a semântica do parser é bug; construir feature de liquidação é ampliação de
  escopo e decisão de milestone. Fica no backlog como **auditoria**, não como estratégia.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0017-liquidacoes.md`. **Quatro must-fix, todos aceitos, e a nota mudou
de premissa por causa do terceiro** — inclusive o título, que dizia "que não observamos":

1. **A medição proposta não é identificável.** A álgebra `A − S = (L − S) + U` está no corpo, com o
   contraexemplo dela. Substituí por auditoria de observabilidade e utilidade incremental.
2. **"A maior" → "a mais recente"**, nos dois streams; e retirei a garantia irrestrita de limite
   inferior, porque o parser usa `q × p` (`streams.py:293`) em vez de executado (`z`, `ap`).
   Cenário: ordem de 10 a 100 executada em 1 a 100 vira notional 1000 no nosso banco.
3. **"Se alguém um dia coletar" está desatualizado** — a coleta existe (`ingest.py:62`,
   `streaming.py:45`, `streams.py:57`, `persist_rows.py:217`). Cenário de falha: planejar um coletor
   duplicado e deixar a série existente sem auditoria. Fui ao banco confirmar: 8421 linhas em 197
   mercados.
4. **"Subestimação explode ⇒ série inútil" retirado.**

Cortes aceitos: "principal razão" para agressor ≠ informado (importância relativa não medida); "a
literatura autoriza nada preditivo" → "este preprint não valida alarme por evento"; "os custos deixam
de valer" e "a entrada é a mais irrealista" → hipóteses de fragilidade não medidas; e a precisão de
que a variância comprimida é de **resíduos do log da razão taker buy/sell**, não de volume bruto.
Ela também corrigiu o contrato do detector: `detector_disabled` é o motivo externo,
`feature_not_implemented` é detalhe.

**Divergência:** nenhuma. Concordamos em manter o detector desarmado, declarar a amostragem, não
apresentar snapshots como total do mercado e separar pesquisa de ativação.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0014-taker-buy-volume-o-que-temos-medido]] ·
[[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] · [[Anomalies]] · [[Market Collector]] ·
[[Exchange Adapters]] · [[Data Flow]] · [[Open Bugs]]

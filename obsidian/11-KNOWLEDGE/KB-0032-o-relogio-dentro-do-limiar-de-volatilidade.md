---
tags: [knowledge, nota, regime, volatilidade, sazonalidade]
tema: regime de mercado e volatilidade
fonte: literatura de sazonalidade intradiária em cripto (Ledger Journal, "On the Intraday Behavior of Bitcoin"; Quantpedia, "Overnight Seasonality in Bitcoin") + medição própria no banco local
fonte_url: https://ledgerjournal.org/ojs/ledger/article/download/213/212/1232 (**PDF ilegível pela ferramenta**) · https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin
lido_em: 2026-09-06
evidencia: replicado no nosso dado (SQL colado) + literatura lida apenas em resumo de busca
hipotese_testavel: sim
astra: pendente
---

# O relógio dentro do limiar de volatilidade

## O que afirma

Cripto negocia 24/7 e mesmo assim tem **hora do dia**: a atividade e a volatilidade sobem quando
Europa e Estados Unidos se sobrepõem (por volta de 14:00-16:00 UTC) e caem na madrugada americana.
Isso é achado repetido na literatura intradiária de Bitcoin.

O que essa nota acrescenta é a consequência **para o nosso classificador**, e ela não é pequena:

`regime_v0` compara a volatilidade da janela corrente (60 minutos terminando em `as_of`) contra a
**mediana das amostras horárias dos últimos 30 dias** — uma mediana que **mistura todas as horas
UTC** (`series.py: hourly_samples` + `volatility_reference`). Os limiares são `HIGH` em razão ≥ 2,0
e `LOW` em razão ≤ 0,5 (`model.py:132-133`). Se a volatilidade tem ciclo diurno, então parte do
rótulo `HIGH`/`LOW` **é o relógio**, não o mercado.

## Medição própria (banco local, 2026-09-06)

Retorno absoluto médio de 1 minuto do **BTCUSDT** — o mercado de referência do classificador — por
hora UTC:

```
 hora_utc | retornos | dias | mad_bps       hora_utc | retornos | dias | mad_bps
----------+----------+------+---------     ----------+----------+------+---------
        0 |      120 |    2 |  1.7570            12 |      120 |    2 |  1.5235
        1 |      120 |    2 |  2.3641            13 |      120 |    2 |  1.9379
        2 |      120 |    2 |  1.3458            14 |      120 |    2 |  2.2029
        3 |      120 |    2 |  1.3406            15 |      145 |    3 |  2.5404
        4 |      120 |    2 |  1.1142            16 |      134 |    3 |  3.1718
        5 |      120 |    2 |  1.6611            17 |      120 |    2 |  2.8215
        6 |      120 |    2 |  1.4724            18 |      120 |    2 |  2.0797
        7 |      120 |    2 |  1.4158            19 |      120 |    2 |  2.3301
        8 |      120 |    2 |  1.2964            20 |      120 |    2 |  2.3062
        9 |      120 |    2 |  1.0946            21 |      120 |    2 |  1.7855
       10 |      120 |    2 |  1.0843            22 |      120 |    2 |  1.6567
       11 |      120 |    2 |  1.3472            23 |      120 |    2 |  1.2960
```

Vale (09-10 UTC) ≈ 1,08 bps; pico (16 UTC) ≈ 3,17 bps — razão **2,9×**. O formato bate com a
literatura: mínimo na manhã asiática/europeia, máximo na sobreposição Europa-EUA.

E a mesma série, agregada como o classificador agrega (hora completa = 60 retornos contíguos),
expressa como razão contra a **mediana das próprias horas**:

```
 horas_completas | dias_distintos | mediana_bps | min_bps | max_bps | razao_max | razao_min
-----------------+----------------+-------------+---------+---------+-----------+-----------
              47 |              3 |      1.5788 |  0.7979 |  3.5444 |     2.245 |     0.505
```

Em **47 horas** — dois dias — a razão já percorreu de **0,505 a 2,245**. Ou seja: a faixa inteira
que o `regime_v0` chama de `NORMAL` (0,5 a 2,0) foi atravessada nas duas pontas num único fim de
semana, e o extremo superior **cruzou o limiar de `HIGH`**.

> **Ressalva 1, e ela é a mais importante (Astra):** essa razão é **minha**, não do classificador.
> Com 47 amostras a referência não é utilizável, então `_volatility_of` devolve `UNKNOWN` e
> `volatility_ratio` é `None` — o `regime_v0` **não calculou razão nenhuma** neste período
> ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]). Eu computei a razão contra a
> mediana das próprias 47 horas, que **não é** a mediana de 30 dias que o classificador usaria. É
> uma simulação do formato da conta, não uma leitura do sistema, e a mediana de uma amostra de dois
> dias é ela mesma instável.
>
> **Ressalva 2, do mesmo tamanho:** isto é a amplitude da **leitura**
> (`RegimeReading`), não do **estado publicado**. Entre uma e outra está a histerese, que só troca o
> par depois de três leituras consecutivas do mesmo candidato — então uma excursão isolada acima de
> 2,0 **não** publica `HIGH_VOLATILITY`. O que a medição mostra é que o insumo do rótulo oscila numa
> escala em que a histerese (contada em leituras, não em tempo —
> [[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]]) não tem como opinar: uma maré diurna
> de horas, não uma tremulação de minutos. Quantas dessas excursões sobreviveriam à confirmação é
> exatamente o que a H-KB0032 mede, e ainda não medimos. Duas comparações diferentes: **não** as
> confunda.

E, ainda assim, a mediana da referência é agrupada por construção. Uma referência que mistura a hora
de 1,08 bps com a hora de 3,17 bps produz um denominador que não pertence a nenhuma das duas.

## O confundimento, dito antes que alguém o descubra

Estes números não provam efeito de hora. O histórico local vai de 2026-09-04 15:27 a 2026-09-06
16:12, então:

- as horas **0-14 UTC** vêm dos dias 09-05 e 09-06;
- as horas **17-23 UTC** vêm dos dias 09-04 e 09-05;
- só as horas **15-16** têm os três dias.

Isto é, **hora e dia estão confundidos por construção**: um dia calmo mapeia direto sobre um bloco
de horas. Com dois dias por célula, nada aqui é estimativa. O que sustenta a leitura é o **formato**
coincidir com o que a literatura descreve de forma independente — e isso é sugestão, não evidência.

A consulta que produziu a tabela por hora (a versão do universo inteiro é a mesma sem o `JOIN` em
`markets`, agrupando todos os mercados):

```sql
WITH btc AS (
  SELECT c.open_time, c.close,
         lag(c.close)     OVER (ORDER BY c.open_time) AS prev,
         lag(c.open_time) OVER (ORDER BY c.open_time) AS prev_t
  FROM candles c JOIN markets m ON m.id = c.market_id
  WHERE c.timeframe = '1m' AND c.is_final AND m.symbol = 'BTCUSDT'
)
SELECT EXTRACT(hour FROM open_time)::int AS hora_utc,
       count(*) AS retornos,
       count(DISTINCT date_trunc('day', open_time)) AS dias,
       round(avg(abs(close/prev - 1)) * 10000, 4) AS mad_bps
FROM btc
WHERE prev IS NOT NULL AND prev > 0 AND open_time - prev_t = interval '1 minute'
GROUP BY 1 ORDER BY 1;
```

**Regra de escrita que a Astra impôs a esta nota, e que vale para as próximas:** onde eu disser
"o efeito de hora", leia-se "o padrão observado nestes dois dias, cujo formato coincide com o que a
literatura descreve". Nada abaixo pode tratar o ciclo diurno como demonstrado — nem a discussão do
piso de custo, nem a da amplitude. É por isso que tudo aqui é **hipótese** e nada é conclusão.

## Hipótese testável no Lab

**H-KB0032 (diagnóstica, e é a mais barata desta rodada).** Com ≥ 20 dias de amostras horárias:

1. medir a mediana do estimador **por hora UTC** e a razão `mediana_da_hora / mediana_agrupada`;
2. contar, minuto a minuto, quantas leituras mudariam de faixa (`LOW`/`NORMAL`/`HIGH`) se a
   referência fosse a mediana **da hora corrente** em vez da mediana agrupada.

- **Confirmação de que o relógio contamina o rótulo:** alguma hora com razão fora de [0,8; 1,25], e
  taxa de troca de faixa acima de 10% dos minutos.
- **Refutação:** todas as horas dentro de [0,9; 1,1] e troca abaixo de 2% — nesse caso a mediana
  agrupada está certa e esta nota é só uma preocupação bem-intencionada.
- **O que a confirmação NÃO autoriza:** trocar o denominador sozinho. Uma referência por hora tem 24
  denominadores, cada um com 1/24 das amostras — precisaria de 480 amostras **por hora**, isto é,
  vinte vezes mais história. Alternativa mais barata: manter a mediana agrupada e **gravar a hora
  UTC** no envelope, deixando a correção para a análise. Decidir entre as duas é do Everton, porque
  muda o que o produto afirma na tela.
- **Cruza com o piso de custo:** `atr_pct_min` é um piso **absoluto** aplicado a uma quantidade cuja
  distribuição pode respirar ao longo do dia. **Se** o padrão observado for efeito de hora, o piso
  deixaria passar mais mercados numa ponta do dia e menos na outra — um filtro de horário disfarçado
  de filtro de custo
  ([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]).

## Por que pode falhar

- **Dois dias não são amostra.** Repito de propósito: pelo nosso próprio limiar editorial (100
  outcomes e 30 dias), isto é `inconclusivo`. O que a medição prova é que **o instrumento funciona**
  e que a magnitude vale a pena medir direito.
- **O ciclo pode migrar.** O horário de verão nos EUA e na Europa desloca a sobreposição em uma hora
  duas vezes por ano; uma referência por hora UTC ficaria desalinhada nessas semanas.
- **BTC não é o universo.** A mesma consulta agrupando os 229-232 mercados dá amplitude bem menor
  (mediana de 5,56 a 7,72 bps entre horas, razão ≈ 1,39×), o que é esperado: agregar mercados
  cancela parte do ciclo. Como o classificador olha **só BTCUSDT**, é a amplitude de 2,9× que entra
  no rótulo — e é ela que importa aqui.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Três correções aceitas e aplicadas acima:**

1. **A razão 0,505–2,245 não é do classificador.** Com 47 amostras a referência é inutilizável e
   `volatility_ratio` é `None`; eu computei a razão contra a mediana das próprias 47 horas. Sem essa
   ressalva a nota dava a entender que o sistema tinha produzido o número.
2. **Leitura ≠ estado publicado.** A histerese fica entre uma coisa e outra, e a nota comparava as
   duas como se fossem a mesma.
3. **"O confundimento está bem explicado, mas conclusões posteriores voltam a tratá-lo como efeito
   demonstrado."** Revisei a linguagem de toda a nota e do cruzamento com o piso de custo; onde
   havia afirmação, agora há condicional.

**Concordância:** que a mediana de referência misture todas as horas UTC enquanto a janela corrente
é de uma hora específica é um fato do código, e é o núcleo da nota. Ele sobrevive às três correções.

## Relacionados

[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] (o outro relógio dentro do sistema) ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] · [[Strategy Backlog]]

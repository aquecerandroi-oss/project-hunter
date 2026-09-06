---
tags: [knowledge, nota, regime, amplitude, breadth]
tema: regime de mercado e volatilidade
fonte: literatura sobre amplitude de mercado (Brown & Cliff 2004 e revisões posteriores — evidência **contestada**); e o nosso `regime/breadth.py` + `regime/classifier.py` + banco local
fonte_url: https://en.wikipedia.org/wiki/Breadth_of_market · https://www.sciencedirect.com/science/article/pii/S0264999319312982 (**HTTP 403 — não aberto**)
lido_em: 2026-09-06
evidencia: literatura **disputada**, lida só em resumo de busca; medição própria replicada (SQL colado)
hipotese_testavel: sim
astra: pendente
---

# Amplitude de mercado: a evidência é disputada, e a nossa não é uma linha de avanços

## O que afirma (a literatura)

A ideia de praticante é antiga: uma alta com muitos papéis subindo é mais "saudável" que uma alta
carregada por poucos, e a linha de avanços-declínios (e o TRIN, de 1967) mediriam isso. A evidência
acadêmica é **mista e contestada**: trabalhos sobre o mercado americano agregado encontram pouco
poder preditivo fora da amostra — Brown & Cliff (2004), num resultado próximo, mostram que sentimento
correlaciona forte com o retorno **contemporâneo** e prevê pouco o futuro próximo. Trabalhos mais
recentes reivindicam informação incremental além de momentum e médias móveis. Não consegui abrir o
artigo mais citado dessa segunda linha (403 no ScienceDirect), então esta nota **não** carrega
nenhum número de tamanho de efeito.

A leitura honesta: amplitude é um **descritor de estado** com evidência preditiva fraca e disputada.
Que é exatamente o papel que o nosso classificador lhe dá — confirmação, não previsão. Isso está
certo, e é raro estar certo por acidente.

## O que a nossa amplitude realmente mede

`compute_breadth` (`regime/breadth.py:101-151`) **não** é uma linha de avanços. É:

> a fração dos mercados utilizáveis cujo `return_4h > 0` **e** cujo `relative_volume_1h > 1,5`,

com `usable_markets` no denominador, e com um portão: se a **cobertura** contra o universo declarado
ficar abaixo de 80%, a amplitude é `unusable` com motivo `insufficient_coverage` — "não conseguimos
olhar", nunca "o mercado está caindo". Essa distinção é boa e está escrita no código.

O que ninguém tinha somado é a **assimetria que a conjunção com volume cria** em `_confidence`
(`classifier.py:134-145`):

- tendência `BULL` concorda se `fraction ≥ 0,5`;
- tendência `BEAR` concorda se `fraction < 0,5`;
- tendência `SIDEWAYS` **sempre** concorda.

Como o numerador exige `relative_volume_1h > 1,5`, num mercado **calmo** quase nenhum ativo
qualifica e `fraction` tende a zero — independentemente de o mercado estar subindo. Resultado
estrutural: em regime calmo, uma leitura `BULL` é sistematicamente rebaixada a `confidence = 0,6`
(`confidence_breadth_disagrees`) e uma leitura `BEAR` é sistematicamente promovida a `1`. A
amplitude não está discordando do touro; ela está medindo que **não há volume**, e o classificador
lê isso como discordância direcional.

## Medição própria (banco local, 2026-09-06)

Sobre toda a série de `feature_snapshots` disponível (48 instantes, 15:35 a 16:22 UTC, 202 mercados,
9.100 leituras dos dois insumos):

```
 instantes | max_utilizaveis | instantes_cobertura_80 | leituras_r4_ok | leituras_rv_ok | leituras_totais
-----------+-----------------+------------------------+----------------+----------------+-----------------
        48 |               0 |                      0 |              0 |              0 |            9100
```

E o motivo, que não é o que eu esperava:

```
 qualidade_r4 |   motivo_r4   | leituras
--------------+---------------+----------
 unavailable  | gap           |     9053
 unavailable  | warmup        |       45
 unavailable  | missing_input |        2
```

**Zero** instantes com cobertura de 80%. **Zero** leituras utilizáveis de `return_4h` e de
`relative_volume_1h`. Ou seja: nesta instância a amplitude **nunca produziu um número** — o caminho
inteiro está exercitado apenas pelo ramo `insufficient_coverage`. O motivo dominante é `gap` (99,5%).

**Correção da Astra sobre o que `gap` significa.** Eu tinha escrito que `gap` prova que falta a vela
exatamente 240 minutos atrás. **Não prova.** `gap` é emitido quando a janela pedida não está
contígua — **qualquer** minuto ausente dentro dela produz o mesmo motivo. Com o scanner reiniciado
há 47 minutos, o mais provável é que faltem centenas de minutos da janela de 4 h, e não uma vela
específica. O que o dado autoriza a dizer é: *a janela de 4 h não estava íntegra*, ponto. Separar
"janela curta" de "janela furada" exigiria um motivo mais fino do que temos — e isso é um pedido de
instrumento, não uma conclusão.

Consultas:

```sql
-- cobertura por instante
WITH s AS (
  SELECT f.ts,
         f.features->'values'->'relative_volume_1h'->>'quality' AS q_rv,
         f.features->'values'->'return_4h'->>'quality' AS q_r4
  FROM feature_snapshots f
), pm AS (
  SELECT ts, count(*) AS mercados,
         count(*) FILTER (WHERE q_rv='ok' AND q_r4='ok') AS utilizaveis
  FROM s GROUP BY ts
)
SELECT (SELECT count(*) FROM pm) AS instantes,
       (SELECT max(utilizaveis) FROM pm) AS max_utilizaveis,
       (SELECT count(*) FROM pm WHERE utilizaveis::numeric/NULLIF(mercados,0) >= 0.8) AS instantes_cobertura_80,
       (SELECT count(*) FROM s WHERE q_r4='ok') AS leituras_r4_ok,
       (SELECT count(*) FROM s WHERE q_rv='ok') AS leituras_rv_ok,
       (SELECT count(*) FROM s) AS leituras_totais;

-- motivos de indisponibilidade
SELECT f.features->'values'->'return_4h'->>'quality' AS qualidade_r4,
       f.features->'values'->'return_4h'->>'reason'  AS motivo_r4,
       count(*) AS leituras
FROM feature_snapshots f GROUP BY 1,2 ORDER BY 3 DESC;
```

Ressalva importante: o scanner local reiniciou às 15:35 e a série inteira tem 47 minutos. Isto
**não** é medição de produção, e não diz nada sobre a VPS. É a constatação de que, na única
instância observável, a confirmação por amplitude é matéria não exercitada.

## Hipótese testável no Lab

**H-KB0033 (diagnóstica, dois números pelo preço de um).** Publicar em `supporting_features`, ao
lado de `breadth.fraction`, a **fração incondicional de avanços** (só `return_4h > 0`) e a **fração
com volume** (só `relative_volume_1h > 1,5`), com o mesmo denominador `usable_markets`. Depois medir:

- a distribuição conjunta das três frações ao longo do dia;
- a correlação entre a fração com volume e a hora UTC (é o mesmo relógio da
  [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]]);
- quantas vezes a `confidence` teria sido diferente se a amplitude fosse a incondicional.

- **Confirmação da assimetria:** a fração conjunta fica sistematicamente abaixo de 0,5 mesmo em
  janelas em que a incondicional está acima — e a diferença acompanha a hora do dia.
- **Refutação:** as duas frações cruzam 0,5 juntas na maior parte do tempo, e a conjunção só remove
  ruído.
- **O que a confirmação autoriza:** publicar as três e deixar o consumidor escolher, ou mudar a
  regra de concordância. Ambas mudam o que a tela afirma → decisão do Everton.
- **O que ela não autoriza:** derrubar `breadth_relative_volume_min` de 1,5 para "melhorar" o
  número. O limiar é política declarada, e mexer nele sem estudo é ajustar ao gráfico.

## Por que pode falhar

- **Amplitude não tem evidência preditiva sólida em lugar nenhum**, muito menos em cripto. Se a
  medição mostrar assimetria, o conserto é de **coerência interna** — parar de chamar de discordância
  o que é ausência de volume — e não uma promessa de melhorar retorno.
- **`usable_markets` como denominador é uma escolha.** Cobertura de 80% ainda deixa 20% do universo
  fora; se os ausentes forem sistematicamente os menos líquidos, a fração é de um subconjunto
  enviesado. O código registra `excluded` com motivo — é auditável, e ninguém auditou.
- **Cripto se move junto.** Se o universo tem beta alto contra o BTC
  ([[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]]), a amplitude é quase uma função da
  tendência do próprio BTC — e então ela não é confirmação independente, é a mesma medida duas vezes.
  Esse é o teste mais importante desta nota e ele é barato.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Confirmou o achado central:** a assimetria entre touro e urso em
`_confidence`, provocada pela conjunção com volume, **está no código** — eu não li mal. **Duas
correções aplicadas:**

1. **`gap` não prova a ausência da vela de 240 minutos atrás.** É qualquer minuto faltando na
   janela. Reescrito.
2. **Faltavam as consultas.** Adicionadas.

**O que eu mantive contra a tentação de ir além:** a assimetria é um achado de **coerência
interna**, não uma promessa de retorno. A literatura de amplitude é disputada e a nota não a usa
para prometer nada.

## Relacionados

[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] · [[Strategy Backlog]]

---
tags: [knowledge, nota, regime, proveniencia, bug]
tema: regime de mercado e volatilidade
fonte: o nosso próprio código e o nosso próprio banco — `services/strategy-worker/`, `packages/core/hunter_core/db/models/agents.py`, `services/scanner-worker/hunter_scanner_worker/`
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (leitura de código + SQL executado e colado)
hipotese_testavel: sim
astra: pendente
---

# O regime não chega ao sinal — e isso mata, de saída, toda esta rodada

## O que afirma

Esta rodada inteira gira em torno de uma pergunta: *as candidatas das três rodadas anteriores valem
em todo regime, ou só num?* A resposta operacional é que **não dá para perguntar retrospectivamente**,
porque o regime não está gravado em lugar nenhum do caminho da estratégia.

Três fatos, o terceiro medido:

1. **A palavra `regime` não aparece no worker de estratégia.** Uma busca por `regime` em
   `services/strategy-worker/` e em `packages/core/hunter_core/strategies/` retorna apenas menções
   em comentários e testes — nenhum `import`, nenhum consumo. O `StrategyContext` não tem regime, e
   `record.py` monta `agent_signals.supporting_features` a partir do envelope da S1, que também não
   tem.
2. **A coluna existe e ninguém a preenche.** `agent_signals.regime_id` está declarada
   (`packages/core/hunter_core/db/models/agents.py:125-127`, FK para `market_regimes` com
   `ondelete="SET NULL"` e índice), mas quem escreve `regime_id` é só o **scanner** — em
   `opportunities` (`scanner-worker/rows.py:144,169`) e nas linhas de `market_regimes`. O worker de
   estratégia nunca o toca.
3. **Medido.** No banco local, em 2026-09-06:

```
 sinais | com_regime_id | com_opportunity_id |           primeiro            |            ultimo
--------+---------------+--------------------+-------------------------------+-------------------------------
    197 |             0 |                  0 | 2026-09-06 00:25:01.939152+00 | 2026-09-06 02:17:39.710076+00
```

Consulta:

```sql
SELECT count(*) AS sinais, count(regime_id) AS com_regime_id,
       count(opportunity_id) AS com_opportunity_id,
       min(emitted_at) AS primeiro, max(emitted_at) AS ultimo
FROM agent_signals;
```

197 sinais, **zero** com regime, **zero** com oportunidade.

## Onde foi mostrado

Instância **local** (`docker compose -f infra/docker/docker-compose.yml`), coorte pequena. A VPS não
foi consultada: o portão de permissão desta sessão recusou `psql` por SSH, como já havia recusado na
terceira rodada. A leitura de código, essa, vale para as duas — é o mesmo `main`.

## Como mediríamos aqui

Não há o que medir enquanto a coluna for nula. O que existe é uma **decisão de proveniência**, e ela
é barata: no instante da decisão o worker de estratégia já lê o `StrategyContext`; o regime corrente
já está publicado no Redis pelo scanner (`projections.publish_regime_current`, `regime:current`).
Gravar no envelope imutável de cada sinal:

- `regime_id` (a linha de `market_regimes` vigente), na coluna que já existe;
- o **par** `{trend, volatility}`, não só o rótulo projetado — porque `REGIME_PROJECTION` é lossy e
  `bull+high` e `bear+high` viram o mesmo `HIGH_VOLATILITY`;
- `confidence`, `classifier_version` e a **idade** da leitura em segundos;
- `volatility_ratio` e `breadth.fraction`, que são os números contínuos por trás do rótulo — um
  rótulo de três faixas joga fora a informação de que a razão estava em 1,99.

Nada disso muda decisão nenhuma. É observação sem decisão, o passo mais barato da rodada — o mesmo
padrão que a segunda rodada pediu para `taker_imbalance_5m`.

## Hipótese testável no Lab

**H-KB0030 (requisito de proveniência, não é variante).** Depois de gravar o carimbo acima, a
coorte de sombra passa a admitir estratificação por regime. A pergunta que ela responde:

> A taxa de alvo entre toques resolvidos e a expectancy líquida hipotética em R da `momentum_v1`
> diferem entre `volatility = HIGH` e `volatility = NORMAL`, com denominador declarado em cada
> célula?

- **Refutação de que o regime importa:** intervalos que se sobrepõem inteiramente entre as células.
- **O que ela nunca pode virar sem janela futura:** um filtro "só opere em NORMAL". A coorte que
  gerar a hipótese não pode confirmá-la
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Limite duro de amostra:** com o limiar editorial de 100 outcomes avaliáveis **e** 30 dias
  distintos por célula, e três faixas de volatilidade cruzadas com três de tendência, uma
  estratificação completa exige uma amostra que não teremos tão cedo. Estratificar por **uma**
  dimensão de cada vez é o único recorte honesto.

## Por que pode falhar

- **Carimbar o regime não o torna correto.** Enquanto ele for `UNKNOWN`
  ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]), o carimbo grava "não sei" — o que
  ainda assim é melhor que nada, porque distingue "não sabíamos" de "não gravamos".
- **Risco de look-ahead pela idade.** Se o carimbo copiar o regime "corrente" sem gravar a idade da
  leitura, uma análise futura pode atribuir ao sinal um estado publicado depois da decisão. A idade
  em segundos é obrigatória, não decoração — mesma armadilha que `market_snapshots` já tem pela
  chave de minuto alinhado ([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]).
- **Tentação de usar o regime na decisão no mesmo passo.** Não. Gravar e decidir são duas mudanças;
  juntá-las torna impossível saber qual delas moveu o resultado.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Confirmou** que `agent_signals.regime_id` nunca é escrito pelo
`strategy-worker` e que o único escritor de `regime_id` é o scanner, em `opportunities` e em
`market_regimes`. Nenhuma correção factual nesta nota.

**O que ela acrescentou e eu incorporei acima:** carimbar o **par** e não só o rótulo projetado, e
gravar a **idade** da leitura — sem os dois, o carimbo cria uma ilusão de proveniência pior que a
ausência dele, porque uma análise futura acharia que sabia o regime quando sabia apenas o rótulo
mais recente disponível.

## Relacionados

[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] (o mesmo defeito, para liquidez) ·
[[Open Bugs]] · [[Strategy Backlog]] · [[Registro de Tentativas]] · [[EXP-0001-momentum-v1]]

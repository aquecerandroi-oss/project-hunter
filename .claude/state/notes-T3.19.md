# Notas T3.19 — protocolo de replicação (o que foi entregue, o que ficou pendente)

Base: `main` em `b52f23f`. **Nada commitado.** Caminhos tocados: `docs/plans/REPLICATION.md`,
`packages/indicators/hunter_indicators/replication/**`, `packages/indicators/tests/**` (arquivos
novos), `services/strategy-worker/hunter_strategy_worker/replication{,_stats}.py`,
`services/strategy-worker/tests/test_replicate_strategy_version.py`,
`infra/scripts/replicate_strategy_version.py`. Nenhum arquivo de outro agente foi editado.

## 1. Contrato do placar para T3.18 (ou o seguidor dele) — entrega 5 do brief

T3.18 **ainda não aterrissou** quando esta tarefa rodou (não existe
`apps/api/hunter_api/services/lab_scoreboard.py` nem rota `/lab/scoreboard`), então o contrato fica
aqui em vez de virar código em arquivos de outro dono.

**Como calcular (uma chamada, sem SQL novo do lado da API):**

```python
from hunter_strategy_worker.replication_stats import build_report
report = await build_report(conn, version_id, seed=<semente registrada>, as_of=<as_of>)
payload = report.to_jsonable()          # o bloco "replication" inteiro
```

`build_report` faz três consultas (população avaliável do pai, irmãs pelo rótulo no `changelog`,
`promising_at`) e delega **toda** a conta para `hunter_indicators.replication`, que é puro. Se a API
não puder depender do `strategy-worker`, copie as três consultas de `replication_stats.py` para um
arquivo novo do lado da API (`lab_replication.py`) e chame
`hunter_indicators.replication.replication_report` — a parte pura é a que precisa ser a mesma.

**Forma do payload:** `docs/plans/REPLICATION.md` §6 traz o JSON real de `to_jsonable()`, campo por
campo. Resumo dos campos de topo, como o brief pediu:

```
replication: {
  status: none | promissora | replicando | real | refutada,
  reason, promising_at,
  parent: {evaluable, days, markets, expectancy_r, profit_factor, profit_factor_reason,
           sum_r, wins, losses, verdict},
  out_of_sample: {passed, reason, evaluable, days, markets, expectancy_r, ..., mature},
  siblings: {passed, reason, n, expected, required, mature, positive, arms: [...]},
  market_halves: {passed, reason, a: {...}, b: {...}},
  bootstrap: {passed, reason, n, mean, ci_low, ci_high, resamples, seed, confidence, method,
              day_cluster: {...}, sign_test: {positives, negatives, zeros, p_sign, method}}
}
```

**Regras que a tela precisa respeitar** (todas já mecânicas no payload):

- `passed` tem **três** estados: `true`, `false` (falha madura → `refutada`) e `null` (aguardando).
  "Aguardando" nunca pode ser pintado como reprovação — é o estado normal de um bloco jovem.
- `status` é derivado, nunca escolhido pela tela: use `report.status`.
- Todo número é string de `Decimal`. Nada de `parseFloat` para decidir; formatação só na exibição.
- Copy sugerida, sempre ao lado da régua: "real = quatro repetições concordando (fora da amostra,
  10 irmãs, metades de mercado, bootstrap); nada disso autoriza carteira".
- As irmãs aparecem como **linhas próprias** do placar (são `strategy_versions` de verdade,
  `research_only`); o cartão do pai é quem mostra o bloco `replication`. Para não poluir o placar,
  filtre irmãs pelo prefixo do `changelog` (`replication:<pai>:`) e mostre-as agrupadas sob o pai —
  `hunter_strategy_worker.replication_stats.load_sibling_rows` já devolve `(id, version, k)`.

## 2. Pendências declaradas (não são esquecimento; estão no protocolo)

1. **`strategy_versions.promising_at`**: hoje o instante vive no `changelog` das irmãs (durável) e
   num `system_events` (retenção de 30 dias). A coluna é o lugar certo — migração da
   database-architect. Enquanto não existir, quem lê usa `load_promising_at`.
2. **Coorte `replication:<pai>:<k>`**: o CHECK `ck_shadow_episodes_cohort_format` (`0002_shadow_lab`)
   e `SHADOW_COHORT_PATTERN` aceitam só `prospective` e `replay:<uuid>`; a coorte do worker é de
   **processo** (`SHADOW_COHORT`), não de versão. A ponte de execução **já está pronta** para o
   rótulo (`bridge_screen.py`, T3.15e, recusa `cohort_not_live` para qualquer coorte que não seja
   `prospective`, citando "a replication sibling's cohort"). Falta migração + coorte por versão no
   worker. Hoje o isolamento não depende disso: `purpose = research_only` + ausência de `agents` +
   o filtro de coorte (provados por teste).
3. **Custo operacional**: 10 irmãs multiplicam por ~11 as avaliações e os `tracking_hold` da família
   replicada (REPLICATION.md §9). Antes de replicar duas famílias ao mesmo tempo, olhar CPU do
   `strategy-worker` e tamanho de `agent_signals`/`signal_outcomes`.
4. **PBO/CSCV, Deflated Sharpe e Reality Check** não são calculados (falta o registro explorável das
   configurações tentadas). Está escrito em §7 como limitação, não como promessa futura.

## 3. Decisões numéricas que tive de tomar (não vinham do brief)

| Decisão | Valor | Por quê |
|---|---|---|
| Metades imaturas | `METADES_MIN_MERCADOS = 3`, `METADES_MIN_RESULTADOS = 20` por metade | com 1–2 mercados a "metade" é um mercado; o brief não deu limiar e sem um deles o bloco 3 refutaria por ruído |
| Chave do mercado | `<exchange>:<symbol>` | mesmo símbolo em duas corretoras é mercado diferente |
| Casas do jitter decimal | `max(casas + 2, 4)` | menos que isso o arredondamento engole o ±15 % (`3` → sempre 3) |
| Piso de inteiro | 1 | janela zero não é variante, é erro |
| Semente por irmã | `seed + k` | uma semente registrada reproduz as dez |
| Bootstrap por dias | `min_groups = 5` | abaixo de 5 dias o intervalo por blocos não tem o que reamostrar |
| Teste de sinal | exato até 2 000 lados; acima, normal com correção de continuidade | custo da soma binomial |
| Bloco 4 com discordância | i.i.d. exclui zero mas por dias cruza → `replicando` (`intervalo_por_dia_cruza_zero`), não `refutada` | falta **dia**, não evidência contrária (KB-0051) |
| Segunda replicação do mesmo pai | recusada | rodar duas vezes dobra as tentativas e infla o falso positivo |

## 4. Prova real contra o stack local (2026-09-08)

O stack local está de pé, mas o **banco local está em `0008_paper_roles_2`** (sem
`strategy_versions.purpose`, que é `0010`) e o Postgres do compose **não publica porta no host**, e a
imagem do `strategy-worker` não carrega `hunter_indicators`. Ou seja: a CLI nova não roda contra ele
sem rebuild de imagem (que atrapalharia outros agentes). O que **foi** feito, e é real: exportei por
`psql` a população avaliável das duas versões ativas e rodei o relatório do protocolo sobre ela.

```
momentum v2   → veredito: none (a versão nunca foi validada pela régua do placar)
                pai: inconclusivo — 182 resultados avaliáveis, 2 dias, 114 mercados,
                expectancy -0.2836, PF 0.4976
                market_halves: FALHOU — metade_a_negativa   (64 x 50 mercados; -0.2934 / -0.2714)
                bootstrap: FALHOU — intervalo_negativo      (CI -0.4163 .. -0.1478; p_sign 0.0000)
                day_cluster: grupos_insuficientes: 2 < 5

volume_anomaly v2 → veredito: none; pai: inconclusivo — 379 resultados, 2 dias, 143 mercados,
                expectancy -0.6744, PF 0.3409; halves FALHOU; bootstrap CI -1.1184 .. -0.3580
```

Leitura honesta: **nenhuma das duas versões é candidata a replicação** — nem por maturidade (2 dias
de 30) nem por sinal (as duas estão negativas na população atual). O script recusaria as duas, que é
exatamente o comportamento esperado. Isso não é veredito sobre as estratégias: são 2 dias.

## 5. O que revisar depois de mim

- **risk-engine-guardian**: confirmar que as três barreiras do §4.4 bastam e que nada no caminho
  (`replicate` → `strategy_versions`) pode virar entrada; o script nunca escreve `purpose = paper`.
- **code-reviewer**: `replication.py` (transação única, recusas), `jitter.py` (forma canônica) e o
  teste de integração.
- **Sexta-feira**: o texto do protocolo, os nomes dos limiares e a regra de que `refutada` continua
  pesquisa — e uma `EXP-` nova quando a primeira replicação de verdade rodar.

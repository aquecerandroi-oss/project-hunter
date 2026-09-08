# Notas T3.26 — as duas candidatas mais promissoras do backlog entram no Lab (quant-engineer, 2026-09-08)

Base: `main` em `a8af4fe`. **Nada commitado.** Caminhos tocados (só os meus):
`infra/scripts/derive_variant.py` (novo), `infra/scripts/activate_strategy_version.py`,
`infra/scripts/obsidian_strategy_pages.py`,
`services/strategy-worker/hunter_strategy_worker/activate_derived.py`,
`services/strategy-worker/tests/test_derive_variant.py` (novo),
`infra/scripts/tests/test_derive_variant_lineage.py` (novo),
`.claude/state/exp-drafts/EXP-0006-momentum-piso-de-custo.md` (novo),
`.claude/state/brief-T3.27-momentum-v2-invalidacao.md` (novo), estas notas.
Nada em `.env*`, `obsidian/**`, `apps/**`, `services/execution-worker/**`, `infra/migrations/**`,
`docs/DESIGN.md`. As mudanças de outros agentes no `git status` foram ignoradas conforme a regra.

---

## 1. A pergunta que o brief fazia primeiro: a invalidação é parâmetro?

**Não.** `momentum_v1.py:281-283` emite
`Invalidation(kind="close_below", level=prior_max, timeframe="15m")` com `prior_max` calculado na
própria decisão, `Invalidation.kind` é `Literal["close_below"]` (`base.py:104`) e nenhuma das 19
chaves de `default_parameters` toca a regra. Então, pelo item 1 do brief: **entreguei só a variante A
(piso de custo)** e escrevi a variante B como brief de uma **versão de código**
(`.claude/state/brief-T3.27-momentum-v2-invalidacao.md`).

O brief de código traz um achado que muda a ordem do trabalho: os quatro braços da KB-0006
(`INV-A/B/C/E`) **já existem** como *políticas de saída* replayadas sobre entradas congeladas
(`hunter_indicators/replay/policies.py`, `replay/engine.py`, `infra/scripts/replay_exits.py` — a
máquina do EXP-0004), e é exatamente esse pareamento por entrada que a KB-0006 pede como estimando.
Rodar essa máquina sobre os 31 dias custa uma corrida de replay; escrever `momentum_v2` custa módulo
novo, revisão de protocolo e 30 dias de sombra. Por isso o brief põe a corrida de braços como
**entrega 0 bloqueante**.

## 2. `infra/scripts/derive_variant.py` — a terceira forma de derivar uma versão

```
uv run python infra/scripts/derive_variant.py momentum v2 \
    --set atr_pct_min=0.0089 --changelog "..." [--dry-run]
```

Ao lado de `--supersede` (mesmo conteúdo, código novo) e `--paper-line` (mesmo conteúdo, propósito
novo), esta é a que faz o oposto: **mesmo código, conteúdo diferente** — que é a definição de
"versão nova" da SHADOW-LAB.md §1. A linha nasce `draft`, `activated_at = NULL`,
`purpose = research_only`; ativar é uma corrida separada e auditada.

Decisões de desenho que valem registrar:

1. **Canonizar antes de comparar e de validar.** O override entra como `Decimal` quando o schema
   declara `number`/`integer`, passa por `canonical_json` (o mesmo do `params_hash`) e só então é
   comparado com o pai e validado. Consequência testada: `atr_pct_min=0.00300` é recusado como
   "nenhum parâmetro se moveu" e `0.00890` vira `0.0089`. Sem isso, duas grafias do mesmo
   experimento teriam dois `params_hash`.
2. **Recusa por colisão de `params_hash` no mesmo `code_ref`.** Derivar duas vezes a mesma variante
   seria o mesmo experimento contado duas vezes — que é precisamente o que a KB-0010 cobra.
3. **Arquivo único, sem módulo de apoio.** Contra o padrão de `paper_line.py`/`replication.py`, e de
   propósito: o script precisa rodar **dentro da imagem já publicada da VPS**
   (`docker exec -i hunter-api-1 python - ... < infra/scripts/derive_variant.py`), onde só o pacote
   instalado existe. Ele importa apenas o que a imagem já carrega. Foi assim que a derivação e a
   ativação de hoje rodaram em produção sem `docker cp` (que o classificador bloqueia, como a T3.20
   registrou) e sem rebuild.
4. **A linhagem no `changelog`, em formato analisável:**
   `variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 | params_hash=<12> | <motivo>`.
   `derived_from=v<n>` é a quarta grafia que `obsidian_strategy_pages.parse_parent_version` passa a
   reconhecer (as outras três: `succeeds`, `paper line of`, o rótulo de irmã).

## 3. Uma armadilha que a entrega criou e teve de fechar

`activate()` do script de ativação tinha duas rotas: a de pesquisa (reescreve
`parameters_schema`/`default_parameters` **a partir do código de hoje** e congela) e a derivada
(`activate_derived`, que só move `status`/`activated_at`/`changelog`). O teste da rota derivada era
`purpose != research_only or changelog.startswith("paper line of")`. Uma variante é `research_only` e
não começa com aquela frase: ela cairia na rota de pesquisa e a ativação **apagaria silenciosamente
o override**, congelando o valor do pai numa linha que diz ser a variante. Fechado com `_DERIVED`
(regex, no próprio script — ele roda dentro da imagem antiga e não pode importar nomes novos do
pacote) e com um teste de integração que ativa a variante e confere que `atr_pct_min` continua
`0.0089` enquanto o pai continua `0.003`.

Segundo furo, mais silencioso: a ativação **substitui** o `changelog`, que é onde a linhagem mora.
`activate_derived.keep_lineage` passa a preservar o prefixo congelado na frente da nota do operador
(uma linha `--paper-line`, que não tem esse prefixo, sai intocada — o teste antigo continua verde).

## 4. A prova real na VPS (2026-09-08)

`momentum v2` está congelada em
`hunter_core.strategies.momentum_v1@sha256:ab2e0398…` e **este build reproduz esse digest** —
conferido dos dois lados antes de qualquer escrita. Sem isso, `derive_variant` recusaria (e faz bem).

```
13:04:26  --dry-run  → "derivaria momentum v4 de v2 ... atr_pct_min 0.003 -> 0.0089"
13:04:37  derivação  → momentum v4, draft, research_only, params_hash 46635ed2bff2
13:05:13  ativação   → active, "activated with its already-copied code_ref", atr_pct_min = 0.0089
13:06-13:09 replay   → 11 904 barras em duas fatias, coorte replay:d9f7a1f8-…, 0 erros
13:15     prospectivo→ v4 com 215 slots e 4 sinais na coorte prospective
```

Verificado por SQL no banco da VPS: `default_parameters - 'atr_pct_min'` de `v2` e `v4` são iguais
(`t`), `parameters_schema` iguais (`t`), `code_ref` e `params_format` iguais; duas linhas em
`system_events` (`strategy_version_variant_derived`, `strategy_version_activated`); **zero** linhas
de `shadow_outbox` para qualquer coorte `replay:`.

### O número que importa e a leitura que não se sustenta

| | `momentum v2` (pai) | `momentum v4` (piso) |
|---|---:|---:|
| coorte | `replay:f8d8279c-…` | `replay:d9f7a1f8-…` |
| barras avaliadas | 11 904 | 11 904 |
| `triggered` | 460 | 80 |
| sinais / avaliáveis | 224 / 222 | 31 / 30 |
| dias distintos | 24 | 9 |
| expectancy (R) | −0,1717 | −0,1506 |
| taxa de lucro líquido | 0,4144 | 0,3667 |
| Profit Factor | 0,6454 | 0,7220 |

**O piso corta 86% das decisões.** A própria KB-0008 diz que "um piso que elimina 70% dos sinais é
outra estratégia, não a mesma com menos ruído" — estamos bem acima disso, e esse é o achado
operacional do dia.

E a melhora de 0,021 R **não vem de o piso selecionar melhor**:

| Grupo | n | avaliáveis | expectancy |
|---|---:|---:|---:|
| decisões do pai **já acima** do piso | 31 | 31 | **−0,2135** |
| decisões do pai **abaixo** do piso (as eliminadas) | 193 | 191 | −0,1650 |
| decisões de `v4` **pareadas** com o pai (mesma barra/mercado) | 25 | 25 | −0,2352 |
| decisões de `v4` **sem par** no pai | 6 | 5 | **+0,2722** |

Nas 25 pareadas o resultado e o `R_net` são **idênticos** aos do pai (0 divergências) — prova de que
só o filtro mudou. Sobre a população do pai, o lado acima do piso foi o **pior** dos dois. A
diferença de expectancy vem inteiramente de 6 decisões que o pai nunca tomou, porque o slot de `v4`
estava livre onde o do pai estava ocupado — **5 resultados**. O mecanismo aritmético que a KB-0008
previu aparece onde deveria (alvo médio +0,7599 → +1,0667 R), e isso é geometria medida, não
vantagem demonstrada.

**Veredito: `inconclusivo`**, e não só pelo limiar editorial (30 avaliáveis, 9 dias contra 100 E 30):
esta é a mesma janela e a mesma população que geraram a hipótese (KB-0010). O que vale é a coorte
`prospective` que começou hoje às 13:05.

## 5. Decisões numéricas que tive de tomar (não vinham do brief)

| Decisão | Valor | Por quê |
|---|---|---|
| Fatiamento do replay | 2 fatias (08-08→08-23, 08-23→09-08), **mesma coorte** explícita | a regra operacional limita cada comando a 5 min; o pai levou 198,7 s e eu não quis correr o risco de um timeout no meio de uma escrita. Fatias contíguas com a mesma coorte são o mesmo experimento (o slot atravessa), e foi o que a T3.19b fez |
| `--cohort` mintado à mão | `replay:d9f7a1f8-0a41-4315-8692-517e1d264c96` | duas fatias precisam da mesma coorte; se cada corrida mintasse a sua, seriam duas populações |
| Mercados e janela | os quatro do brief, 2026-08-08 → 2026-09-08 | é a única janela em que o pai tem replay comparável (`replay:f8d8279c-…`), e comparar em janelas diferentes não compararia nada |
| `--workers 3` | 3 | o mesmo do pai; mudar o paralelismo não muda resultado, mas muda o número de throughput do recibo |
| Contêiner da derivação/ativação | `hunter-api-1` | é onde `DATABASE_URL_MIGRATIONS` está e o que a `docs/ACTIVATION.md` §7 já usa; o replay corre no `hunter-strategy-worker-1`, como o brief pediu |
| Parâmetro do teste de integração | `volume_mult` (`volume_anomaly_v1`) | os `builders.py` do strategy-worker constroem versões com o contrato real do `volume_anomaly_v1`; usar o parâmetro decimal **dele** mantém o teste sobre um schema congelado de verdade em vez de um schema inventado. O teste unitário usa o schema do `momentum_v1` e o próprio `atr_pct_min` |

## 6. Concerns

1. **A linhagem de `momentum v4` se perdeu no `changelog` da linha ativada, na VPS.** A imagem da
   VPS é anterior a `keep_lineage`, então a ativação substituiu o `changelog` derivado pela nota do
   operador: a linha hoje diz `T3.26: coorte de pesquisa da variante de piso de custo aberta` e
   **não** contém `derived_from=v2`. Efeito real: a página do catálogo de `momentum-v4` vai nascer
   sem o link "versão anterior". O que **não** se perdeu: o evento
   `strategy_version_variant_derived` em `system_events` carrega pai, `code_ref`, `params_hash`
   completo e o override, e a seção "Origem" da página do catálogo lê exatamente essa tabela.
   `changelog` **não** é campo congelado pela trigger (só `code_ref`, `parameters_schema`,
   `default_parameters`, `params_format` e `activated_at` são), então uma correção de uma linha é
   possível — **não a fiz**: é uma escrita à mão em produção sem ferramenta auditada, e prefiro
   deixar a decisão para o orquestrador. Depois do próximo deploy o problema não se repete.
2. **A variante entra na coorte prospectiva de 200+ mercados desde já** (215 slots às 13:15, 4
   sinais). É o que "entrar no Lab" significa e é o que a candidata #2 do backlog exige (janela
   futura reservada), mas é carga nova no `strategy-worker` — menor que a de `v2`, porque o piso
   recusa mais barras, e ainda assim é a terceira versão de `momentum` ativa ao mesmo tempo
   (`v2` research, `v3` paper, `v4` research).
3. **Cinco resultados sustentam a única diferença medida.** Qualquer leitura do tipo "o piso
   melhorou a expectancy" é leitura de cinco operações que existiram por causa do slot. Está escrito
   assim na EXP-0006 e deve continuar escrito assim.
4. **O replay herda o universo de hoje**, não o da janela (limitação declarada do motor,
   PIPELINE §6c). Vale para as duas coortes igualmente, então a comparação não fica enviesada por
   isso — mas nenhuma das duas descreve o universo de agosto.
5. **Não documentei o script novo em `docs/`.** `docs/ACTIVATION.md` merece uma linha sobre a
   terceira forma de derivar, e `docs/plans/SHADOW-LAB.md` §1 idem; não editei porque não estava no
   brief e os `docs/` têm outros agentes em voo hoje. Fica como pendência de uma linha.
6. **`obsidian_strategy_pages.py` é arquivo da T3.20.** Toquei nele (três linhas: um regex novo e a
   docstring de `parse_parent_version`) porque o brief pedia explicitamente que o `derived_from`
   fosse gravado "the way the catalogue exporter parses" — e a T3.20 já tinha registrado nas
   concerns dela que o parser só reconhecia duas frases. Os 14 testes daquele arquivo continuam
   verdes.
7. **Nenhuma medição de quanto o piso muda a coorte prospectiva.** O corte de 86% é da janela de
   replay; na coleta prospectiva, com o universo inteiro em vez de quatro mercados, a proporção pode
   ser outra. É a primeira coisa a medir daqui a alguns dias.

## 7. O que revisar depois de mim

- **risk-engine-guardian:** `momentum v4` é `research_only`, sem linha em `agents`, e a coorte de
  replay é recusada por nome pela ponte. As três barreiras de sempre; nada novo foi aberto. Vale
  conferir que a rota `_DERIVED` do script de ativação não abre caminho para uma linha `paper`
  ser ativada sem as sete condições do D10 (ela não muda essa rota — a recusa de `live` por nome
  continua antes de tudo, e `paper` continua caindo em `activate_derived` como já caía).
- **code-reviewer:** o `_DERIVED` no script de ativação (mudança de rota num caminho que congela
  experimentos), `keep_lineage` em `activate_derived.py`, e a duplicação declarada do `LINEAGE_RE`
  entre `infra/scripts` e o pacote (há um teste que compara os dois padrões).
- **Sexta-feira:** `EXP-0006` está em `.claude/state/exp-drafts/`, pronta para arquivar em
  `obsidian/05-EXPERIMENTS/` e ligar a partir do `Strategy Backlog` (candidata #2 sai de
  "especificada, exige janela futura" para "sombra"), do `Registro de Tentativas` e do
  `Experiments Index`. Não há `EXP-0007` hoje: a variante B não existe como versão, e o brief dela
  está em `.claude/state/brief-T3.27-momentum-v2-invalidacao.md`.
- **Everton:** a decisão que este trabalho põe na mesa é se vale gastar `momentum_v2` (código) na
  invalidação **antes** de rodar os braços `INV-B/C/E` que já existem sobre os 31 dias. A minha
  recomendação está no brief: rodar os braços primeiro.

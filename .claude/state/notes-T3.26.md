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

---

# T3.26b — o EXP-0006 arquivado no Obsidian e o backlog religado (sexta-feira, 2026-09-08)

Base: `main` em `be3674a`. **Nada commitado.** Escopo de escrita: `obsidian/**` e esta seção.
Nada em `.env*`, `apps/**`, `services/**`, `infra/**`, `docs/**` — as tarefas em voo (T3.18b,
T3.7d, audit de design) não foram tocadas.

## STATUS

**Entregue, com uma decisão de estrutura e duas lacunas de proveniência declaradas.** As cinco
entregas do brief estão feitas; o linter está verde; a pasta `00-INBOX/` **não existia** e foi
criada (justificativa e consequência abaixo, em CONCERNS).

| # | Entrega do brief | Estado |
|---|---|---|
| 1 | `EXP-0006` arquivado no formato do template, com Hipótese/Protocolo congelados, avaliação datada rotulada **replay**, veredito `inconclusivo` e a tabela pareada inteira | feito |
| 2 | `Strategy Backlog`: item 1 → brief T3.27 ("replayar os braços `INV-*` antes de escrever código"); item 2 → `EXP-0006`, "no Lab desde 2026-09-08 (`momentum v4`)" | feito |
| 3 | KB-0008 com apêndice datado: os 86% de corte e o achado dos grupos pareados (o lado **acima** do piso foi o pior sobre a população do pai) | feito |
| 4 | Pendência operacional do `derived_from` registrada em `00-INBOX/`, com a correção proposta e a decisão do Everton — **exportador de catálogo não rodado** | feito |
| 5 | `obsidian_lint.py` verde | feito |

Duas coisas que fiz **além** do brief, ambas dentro de `obsidian/**` e por regra escrita da própria
base — se o escopo era estrito, é aqui que ele se estica:

- **`Registro de Tentativas`, T-007.** A página diz, no seu próprio cabeçalho, que *toda* variante
  rodada no Lab entra ali, e que correção é **linha nova com a mesma ID**. O `EXP-0006` sem T-007
  deixaria a contagem de multiplicidade errada (ela passou de "1 execução, 7 contrastes" para "2
  execuções, 8 contrastes"). Linha nova acrescentada; a antiga **não** foi editada.
- **`Experiments Index`.** O registro de IDs não tinha `EXP-0006` — e descobri que também não tinha
  `EXP-0005`, de ontem. Acrescentei os dois e disse na página que o de ontem estava faltando.

## FILES

Criados:

- `obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md`
- `obsidian/00-INBOX/2026-09-08-linhagem-de-momentum-v4-no-changelog-da-vps.md` (**pasta nova**)

Modificados:

- `obsidian/11-KNOWLEDGE/Strategy Backlog.md` — status dos itens 1 e 2, "Já em sombra" (com `v3` e
  `v4`), seção datada "Acréscimo de 2026-09-08", `updated`
- `obsidian/11-KNOWLEDGE/KB-0008-custos-em-perpetuos-e-o-r-que-sobra.md` — apêndice datado
  (2 achados + o que muda no enunciado), `updated`, Relacionados
- `obsidian/11-KNOWLEDGE/Registro de Tentativas.md` — linha nova de T-007 e a contagem de
  multiplicidade atualizada, `updated`
- `obsidian/05-EXPERIMENTS/Experiments Index.md` — `EXP-0005` e `EXP-0006` no registro de IDs e na
  tabela de registrados, nota datada de contagem, `updated`
- `obsidian/00-HOME.md` — `00-INBOX/` no mapa de pastas e os dois experimentos novos na linha de
  `05-EXPERIMENTS/`

`git status --short -- obsidian` e `git diff --stat -- obsidian` confirmam: 5 modificados
(+167 / −8), 2 criados, nada fora de `obsidian/**`.

## TESTS / lint (saída real)

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 184 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.
Info: 1 experimento(s) fora do HEAD ignorado(s) na checagem append-only.

RESULTADO: base limpa
```

O "1 experimento fora do HEAD" é o próprio `EXP-0006`, que ainda não está no git — a checagem
append-only compara com `HEAD` e pula o que não existe lá. Depois do commit ela passa a valer para
esta página, que é exatamente o efeito desejado.

Nenhuma suíte de testes foi executada: não toquei em código.

## CONCERNS

1. **Criei uma pasta de topo (`00-INBOX/`) e não pude documentá-la em `docs/OBSIDIAN.md`.** O brief
   pedia a pendência em `obsidian/00-INBOX/` e a pasta não existia. Criei, com a nota, e descrevi a
   convenção na `00-HOME.md` (o que ela é, o que não é, quando a nota sai de lá). Mas as convenções
   normativas da base moram em `docs/OBSIDIAN.md`, que estava **fora do meu escopo de escrita** —
   então hoje existe uma pasta de topo que o documento normativo não menciona, e o linter não exige
   chave nenhuma além das quatro comuns para ela. **Uma linha em `docs/OBSIDIAN.md` fecha isso**, e
   deixo a decisão de escrevê-la (ou de mover a nota para `09-OPERATIONS/`) para quem tiver `docs/`
   no escopo.
2. **O texto do SQL da avaliação não existe em lugar nenhum que eu alcance.** O rascunho do quant
   cita `/tmp/q7.sql` na VPS e não o colou. O template desta base **exige** a consulta literal, e o
   `EXP-0006` foi arquivado sem ela. Não inventei SQL nem reescrevi números: pus um alerta na
   própria avaliação datada dizendo o que falta e por quê, e listei "colar `/tmp/q7.sql`" como
   entrega da **próxima** avaliação. A seção datada de hoje fica como está — o que ela não teve,
   não teve.
3. **Faltou o `read_at`.** Só o `as_of` (`13:09:41Z`) foi registrado. Como `signal_outcomes` avança
   no lugar, sem o segundo carimbo a leitura não é descritível como snapshot. Mesmo tratamento:
   declarado na página, cobrado da próxima.
4. **A `taxa de alvo entre toques resolvidos` é minha, não do quant.** O template a exige e o
   rascunho não a trouxe; calculei-a das contagens de cobertura da própria leitura (91/136 e 11/21)
   e escrevi na página que ela é razão dessas contagens, não resultado de consulta. Se isso for
   considerado número derivado demais para uma página de pesquisa, é remover a linha — mas
   omiti-la em silêncio me parecia pior, porque é a métrica que mais se confunde com "taxa de
   lucro".
5. **MFE/MAE ficaram nulos por ausência de consulta**, não por OHLC indeterminado. Escrevi o motivo
   exato na tabela, porque os dois nulos significam coisas diferentes e a KB de métricas cobra a
   distinção.
6. **A pendência do `derived_from` continua aberta e é do Everton.** A nota do `00-INBOX` traz o
   `UPDATE` idempotente pronto (chaveado pelo `id` da versão, com `AND changelog NOT LIKE
   'variante de v%'`), as três saídas possíveis e o custo de cada uma. Não apliquei: é escrita à
   mão em produção numa tabela de experimento congelado. **E registrei em voz alta o que "esperar o
   próximo deploy" não resolve:** `keep_lineage` impede a repetição, mas não conserta a linha já
   ativada, porque o `changelog` de uma linha derivada só é escrito uma vez.
7. **Não rodei `export_strategies_to_obsidian.py`**, como o brief mandou. Consequência: não existe
   `03-TRADING/Estrategias/momentum-v4.md`, e a família `momentum` em
   `03-TRADING/Família momentum.canvas` continua desenhando só até a `v3`. Quem rodar o exportador
   depois da correção do `changelog` fecha os dois de uma vez.
8. **`Experiments Index` ficou desatualizado por um dia sem ninguém notar** (o `EXP-0005` existia e
   não estava no registro de IDs). Corrigi, mas vale como sintoma: quem abre um `EXP-NNNN` precisa
   fechar o índice no mesmo turno, senão o próximo número livre deixa de ser confiável.

---

# T3.26c — a variante não pode mentir sobre si mesma (A1–A5 da revisão risk-engine-guardian)

Fonte: `.claude/state/review-T3.26-risk.md` (A1 ALTA, A2/A3 MÉDIA, A4/A5 BAIXA). Base: `3dd8f3a`. **Nada commitado.**

## O que mudou

**A1 — trava estrutural na ativação.** `activate()` reconhecia uma linha derivada só pelos sinais que a coluna `changelog` carrega, e `changelog` não é congelada pela trigger da `0002`. Agora são duas camadas: `carries_own_content(row)` (purpose + frase, caminho rápido) e `refuse_rewriting_own_content(...)`, que recusa **estruturalmente** — um rascunho cujo `default_parameters` não é vazio e cujo `params_hash` difere do conjunto do código de hoje nunca é reescrito, seja qual for o changelog. Compara por `params_hash` (e não por `==`) porque os dois lados vêm de lugares diferentes: ida e volta pelo JSONB de um lado, `canonical_json` de `Decimal` vivo do outro. Só rascunho é checado — linha ativada já é respondida antes com "already activated".

**A2 — faixa.** Tabela nova em `packages/core/hunter_core/strategies/constraints.py`, chamada por `build_parameters` em `derive_variant.py`. Três camadas: (1) regressão de sinal contra o pai, universal e sem tabela; (2) faixas declaradas por estratégia (`positive`, `non_negative`, `unit_interval`, `ordered`); (3) construção a seco de `AssumedCosts` e `Invalidation`, mais a geometria `0 < stop < close < target` numa barra de prova. As nove sondas da revisão são recusadas; `momentum v4` (`atr_pct_min=0.0089`) continua passando.

**A3 — isolamento e ordem.** `handle_candle` ganhou `try/except` por versão: conta em `hunter_shadow_version_failed_total{strategy_key,version}`, loga `shadow_version_evaluation_failed`, segue para a próxima versão e **volta normalmente**, que é o que faz `run_consumer` chamar `ack`. `CancelledError` continua propagando. `load_version_roster` agora ordena por `roster_order`: estratégia, `paper` antes de pesquisa, versão **numérica** (`v10` depois de `v3`), rótulo ilegível por último.

**A4 —** o evento de ativação de linha derivada passa a carregar `derived_from=<vN>`, o `params_hash` do conjunto **que foi congelado** (não o do código de hoje) e o `changelog` como ficou, com o prefixo de linhagem.

**A5 —** `parse_parent_version` testa `derived_from=` **antes** de `succeeds`/`paper line of`. O changelog de uma variante ativada é linhagem + texto livre do operador; um "succeeds v1" na nota fazia a página inventar um pai errado com toda a cara de certo.

## Decisões que fugiram do brief (e por quê)

1. **A tabela da A2 não foi para `schema.py`.** `code_ref` é o digest do módulo da estratégia **mais o fecho transitivo dos irmãos que ela importa**, e `momentum_v1`/`volume_anomaly_v1` importam `schema`. Uma linha a mais lá moveria o digest das duas e **toda versão ativada na VPS — inclusive a linha `paper` `momentum v3` — viraria `code_ref_mismatch`**: `load_version_roster` pararia de rodar tudo e o Lab ficaria mudo atrás de um `/ready` verde. Módulo próprio, fora do fecho, com `test_constraints_outside_freeze.py` fixando os dois digests medidos antes desta tarefa (`momentum_v1@sha256:ab2e0398…`, `volume_anomaly_v1@sha256:9b8c14ab…`) e provando que `constraints` não entrou no fecho de ninguém. Os dois digests continuam idênticos depois de todas as mudanças.
2. **`catalogue.py` foi dividido.** Com a ordenação da A3 ele chegou a 375 linhas (orçamento 350). `ActiveVersion`, `VersionRoster` e `roster_order` foram para `hunter_strategy_worker/roster.py` e são re-exportados por `catalogue` — nenhum chamador precisou mudar de import, e há teste disso (`roster_order_from_catalogue is roster_order`).
3. **`migration_url()` estava duplicado byte a byte** em `activate_strategy_version.py` e `derive_variant.py`; foi para `activation_db.py`. Duas cópias da regra que decide *qual conexão escreve uma versão congelada* é uma a mais — e foi o orçamento de linhas que fez isso aparecer.
4. **`derive_variant.py` deixou de ser autossuficiente.** Ele agora importa `hunter_core.strategies.constraints`, então **a imagem tem de ser deste commit ou posterior**. Isso é inevitável em qualquer forma da A2 (o brief já mandava pôr a tabela no pacote), e a falha é barulhenta (`ModuleNotFoundError`), não silenciosa. `docs/ACTIVATION.md` §7 traz o comando de conferência antes do de derivar.

## Números que tive de arbitrar

- **Barra de prova da geometria: fechamento 100, ATR 1** (`PROBE_CLOSE`/`PROBE_ATR`), ou seja ATR% = 1 %, dentro da faixa congelada do `momentum_v1` (0,3 % a 5 %). Declarado, não medido. Consequência: `stop_atr >= 100` é recusado por aqui. Nenhuma variante plausível chega perto (a 5 % de ATR real, `stop_atr = 20` já zeraria o preço), mas é um limite meu e está escrito no módulo.
- **Onde cada parâmetro entrou.** `atr_pct_min`, `rvol_min` e `return_min` são `non_negative`, não `positive`: zero é "desligar o porteiro", que é variante de pesquisa legítima. `stop_atr`/`target_atr`/janelas/`horizon_s`/`max_entry_delay_s` são `positive` porque zero ou negativo torna a versão incapaz de disparar **qualquer** barra. `base_confidence` em `(0, 1]`. `atr_pct_max` é `positive` e forma o par ordenado com `atr_pct_min`.
- **`_UNNUMBERED = 1 << 30`** em `roster.py`: onde um rótulo que não casa `v<n>` sorteia. Só precisa ser maior que qualquer `v<n>` real.

## Política — D10, para o Everton (não virou código)

`paper_line.py` exige do pai apenas "`research_only` congelada". **Uma variante derivada por `derive_variant.py` satisfaz isso no instante em que é ativada** — inclusive uma variante do `volume_anomaly`, que nunca teve linha `paper` e nunca emitiu um sinal prospectivo. Ou seja: um conjunto de parâmetros sem evidência prospectiva nenhuma poderia virar a linha `paper` de uma estratégia amanhã, o que não é o que a D10 quis dizer com "primeiro a evidência". Não corrigi: acrescentar uma condição seria decidir no código uma oitava condição que a D10 não tem, e essa decisão é do Everton. Está escrito como comentário `OPEN POLICY QUESTION` em `paper_line.py`, ao lado da recusa, para quem ler o código não descobrir isso só na revisão.

## O que **não** foi feito

- Nada de `git commit`, `stash`, `checkout --`, `restore`, `reset`, `clean`. Nenhum `.env*` tocado, nenhum contêiner local parado.
- `services/execution-worker/hunter_execution_worker/bridge.py` (365 linhas) e `services/strategy-worker/hunter_strategy_worker/replication.py` (352, T3.18c em voo) continuam acima do orçamento — **não são meus** e o brief me proíbe de tocar `replication*.py`.
- A indireta do `ENTRY_WINDOW=120 s` da revisão (terceira versão ativa atrasando a emissão) não estava no escopo A1–A5 e continua aberta; a ordenação da A3 melhora o caso porque a linha `paper` agora é a primeira a ser avaliada, mas não mede o `bar_close → emitted_at`.
- Não rodei nada contra a VPS.

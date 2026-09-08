# Notas da T3.16 — badges de staleness envelhecem contra o relógio do servidor, nunca o do viewer

**Autor:** frontend-specialist, 2026-09-08. **Para:** code-reviewer (revisor designado no brief),
Sexta-feira. **Não commitei.** **Não editei** `.env*`, `openapi.json` (gitignored — regenerado, não
commitado), `services/**`, `infra/**`, `apps/api/hunter_api/services/system_status.py` e seus testes
(`test_system_workers_api.py`, `test_system_workers_status.py`) — esses três últimos são da T3.0f, em
voo simultânea; eu os toquei **apenas** ao recuperar um `git stash` que os pegou de raspão (ver §5).

## 1. O sintoma e a causa raiz

`/ever/markets` mostrava toda linha como "atrasado 1min" com a VPS saudável: `QualityBadge`
(`components/markets/quality-badge.tsx`) rederivava a idade dos componentes obrigatórios (`ticker`,
`book`, `mark`) comparando o `ts` de cada um contra `Date.now()` **do navegador** (`useAgeTicker`
antigo). Um relógio de viewer ~60 s adiantado inflava toda idade em 60 s; um relógio atrasado
esconderia atraso real. A API já calculava `data_quality`/`quality` por componente com o **próprio**
relógio (`utcnow()`) e já expunha `stale_after_ms` — só faltava expor o instante em que ela mesma
computou tudo isso, para o cliente reancorar sua contagem de segundos nesse instante em vez do
`Date.now()` local.

## 2. API: `server_now` em `MarketListPage` e `MarketDetailOut`

`apps/api/hunter_api/schemas/markets.py`: campo novo `server_now: datetime` em `MarketListPage` e em
`MarketDetailOut`, ambos com docstring explicando que é o mesmo `now` que os campos `age_ms`/`quality`
de `items`/`components` já usaram.

`apps/api/hunter_api/services/markets.py`: `build_market_list_page`/`build_market_detail` já
calculavam `now = utcnow()` **antes** de montar cada item (F3/G5 — depois das leituras de Redis/
Postgres, para que a idade reflita a latência real da leitura). Só passei `server_now=now` para o
construtor de `MarketListPage`/`MarketDetailOut` — nenhum novo `utcnow()` foi chamado, exatamente para
que `server_now` seja *o mesmo* instante que gerou cada `age_ms`/`quality`, nunca um segundo depois.

Pydantic v2 serializa um `datetime` UTC-aware com sufixo `Z` por padrão (verificado:
`M(ts=datetime(2026,9,5,12,0,0,tzinfo=UTC)).model_dump(mode="json") == {"ts": "2026-09-05T12:00:00Z"}`)
— nenhum serializer customizado foi necessário, o campo se comporta como todo outro `datetime` do
contrato.

### `/api/v1/system/workers` **não** ganhou `server_now`

O brief citava esse payload como "se envelhecer heartbeats" — mas `WorkerHeartbeatOut` já carrega
`ts` **e** `age_s` (calculado pelo próprio scan, `age_s = (now - ts).total_seconds()`, sempre
presentes, nunca opcionais). `ts + age_s` reconstrói exatamente o instante que o scan usou como "agora"
— sem precisar de um campo novo, sem tocar em `system_status.py`/`schemas/system.py` (fora do meu
escopo por instrução explícita do orquestrador). Isso vira `heartbeatServerNowIso(ts, ageS)`
(`hooks/useAgeTicker.ts`), usado por `WorkersTable`/`ExecutionPaperCard` — ver §4.

## 3. Web: `useAgeTicker` ganha um relógio ancorado no servidor

`hooks/useAgeTicker.ts`:

- `useServerClock(serverNowIso, receivedAtMs): number | null` — `offset = serverNow - receivedAt`,
  puro (sem `Date.now()` dentro), memoizado no par. `null` quando `serverNowIso` está ausente ou é
  inválido.
- `useAgeTicker(serverNowIso?, intervalMs = 1000): { now, hasServerClock }` — agora devolve um
  objeto, não mais um `number` cru (mudança de assinatura deliberada; todo call site do repositório
  foi atualizado, ver §4). `receivedAtMs` é capturado **uma vez por resposta nova**: um `ref` lembra o
  último `serverNowIso` visto e um `useEffect` (nunca o corpo do render) chama `Date.now()` só quando
  um valor **novo** chega. O relógio que tica a cada segundo (`tickNow`) também só chama `Date.now()`
  dentro do callback do `setInterval` ou do inicializador preguiçoso do `useState` — nunca durante o
  render em si. Isso não é estilo: o `eslint-plugin-react-hooks` (`react-hooks/purity`, regra nova no
  monorepo) barra `Date.now()` direto no corpo de um hook/componente, e minha primeira versão
  (`useMemo(() => Date.now(), [...])` + `Date.now()` no `return`) violava a regra — corrigida para o
  padrão de estado+efeito acima, que é exatamente o que o `useAgeTicker` original já fazia para o
  `now` que ele expunha.
- `heartbeatServerNowIso(ts, ageS): string | null` — `ts + age_s` como ISO, para heartbeats (§2).
- `computeAgeMs`/`formatAge`: inalterados.

`hasServerClock: false` é o sinal para renderizar o aviso "relógio local" — decidido em **um único
lugar**, `QualityBadge` (não em cada rótulo secundário: `AsOf`/`SnapshotLabel`/`DerivativesCard` na
tela de detalhe do mercado reaproveitam o mesmo relógio ancorado *silenciosamente*, para não repetir o
mesmo fato cinco vezes numa tela — DESIGN.md §2, "menos chips por célula"). O aviso é um `<span>`
`text-[10px] text-fg-subtle` com `title` explicando a causa, ao lado do badge OK/atrasado.

## 4. Toda tela em escopo do brief

- `QualityBadge` (`quality-badge.tsx`): prop nova `serverNow?: string | null`; usa
  `useAgeTicker(serverNow)`; renderiza o aviso quando `!hasServerClock`.
- `MarketRow` → `MarketsTable` → `/[orgSlug]/markets/page.tsx`: `serverNow` (de
  `MarketListPage.server_now`, normalizado `undefined → null`) flui até `QualityBadge`.
- `MarketDetailView` (`market-detail-view.tsx`): `detail.server_now` alimenta `QualityBadge`, `AsOf`
  (idade do ticker no cabeçalho) e `SnapshotLabel` (book/trades, "Snapshot · há N s").
- `DerivativesCard` (mark price/OI/funding, dentro da mesma tela de detalhe): prop `serverNow` nova,
  mesmo relógio, sem repetir o aviso.
- `WorkersTable` (`/system`, seção "Workers"): `AgeCell` agora deriva `heartbeatServerNowIso(worker.ts,
  worker.age_s)` em vez de usar `Date.now()` cru.
- `ExecutionPaperCard` (mesma seção "Workers", ao lado de `WorkersTable`): mesmo padrão — idade do
  MTM/última proteção/última leitura do kill switch agora ancoradas no relógio do heartbeat
  `hb:execution:paper`, não no do navegador. **Não estava listado nominalmente no brief**, mas sofre o
  mesmo bug de raiz (mesmo hook, mesmo `Date.now()`) na mesma seção da tela — corrigido por
  consistência; sinalizo para o revisor confirmar que essa extensão está dentro do espírito do brief.
- **Resumo (summary chips)**: `components/markets/summary-chips.tsx` **não precisou de nenhuma
  mudança** — os contadores (`markets_ok`/`markets_stale`/...) já vêm pré-agregados por
  `_summarize()` no servidor, com o `now` do próprio servidor; nunca foram reagregados no cliente. O
  único jeito de um chip de resumo "mentir" seria discordar do badge por-linha ao lado dele, e agora
  os dois usam o mesmo relógio (o do servidor) por construção.
- **Fora de escopo, tocados só para não quebrar a assinatura do hook** (nenhuma mudança de
  comportamento): `components/radar/{quality-cell,radar-row}.tsx`,
  `components/system/live-status.tsx` — chamavam `useAgeTicker()` sem argumento; como o retorno virou
  um objeto, precisaram trocar `const now = useAgeTicker()` por `const { now } = useAgeTicker()`. Sem
  `serverNowIso`, continuam exatamente como antes (relógio do viewer, sem aviso — essas telas não
  carregam um `server_now` de resposta nenhuma hoje).

## 5. Incidente operacional: `git stash` colidiu com agentes concorrentes

Enquanto investigava se 3 falhas de `test_pipeline_hot_state_*` (caplog vazio) eram pré-existentes ou
causadas por mim, rodei `git stash` para comparar contra o código original. Entre o `stash` e o
`stash pop`, outro agente editou `docs/DATABASE.md` de novo, e o `pop` foi recusado inteiro (Git não
aplica parcialmente). Isso deixou **minhas edições e o trabalho em voo de outros agentes** (T3.0f,
T3.15c — `system_status.py`, `docker-compose*.yml`, `services/execution-worker/**`, migrações, etc.)
presos no stash por alguns minutos, com o working tree temporariamente limpo desses arquivos.

**Recuperação:** listei os 43 arquivos do stash, restaurei cada um individualmente via
`git checkout stash@{0} -- <arquivo>` — **exceto** `docs/DATABASE.md`, cujo conteúdo no working tree já
era mais novo que o do stash (edição concorrente) — e só então descartei o stash
(`git stash drop`). Conferi por amostragem (grep por marcadores "T3.16" e por `{ now }` nos call sites)
que todo arquivo, meu e de outros agentes, voltou ao estado esperado. Nada foi perdido. Isso confirmou
de passagem que as 3 falhas de `pipeline_hot_state` são **pré-existentes** e independentes da minha
mudança (mesmo resultado rodando o código original via stash). Não uso mais `git stash` nesta tarefa;
registrado para não repetir.

## 6. Verificação na tela (item 4 do brief)

**Não consegui** abrir o app no navegador com dado real: a regra operacional desta tarefa proíbe Bash
em background, e não havia uma ferramenta de preview (`preview_start`) disponível nesta sessão para
subir `pnpm dev`/`docker compose up` em primeiro plano sem bloquear. Não tentei a VPS por certificado
self-signed (bloquearia o navegador do app de qualquer forma, como o brief já antecipa) nem o stack
local, pela mesma limitação de processo longo em primeiro plano.

Em vez disso, a saída renderizada real do Testing Library (DOM completo, não um snapshot resumido) foi
inspecionada nos testes que falharam durante o desenvolvimento (por exemplo, o print completo do card
"Execução paper" com `há 6s`/`11:59:55 UTC (08:59:55 -03:00)` antes do ajuste do fixture) — é uma boa
aproximação do que a tela mostra, mas não substitui um check de navegador real. **Sinalizado como
pendência** para quem revisar/commitar: confirmar visualmente `/[orgSlug]/markets` e
`/[orgSlug]/markets/[exchange]/[symbol]` contra a API local ou a VPS antes do commit, por
`frontend-always-polished`.

## 7. Testes

**Backend, unitários novos** (`apps/api/tests/unit/test_markets_quality.py`): `server_now` serializa
em UTC-`Z`; `server_now` nunca é mais antigo que o `ts` de um componente que a mesma chamada computou
como fresco; `MarketDetailOut` carrega seu próprio `server_now`. Não testei `build_market_list_page`/
`build_market_detail` (as funções que de fato escrevem `server_now=now`) no nível unitário porque elas
já exigem `AsyncSession`/Redis reais neste código-base (nunca foram testadas com fakes) — cobri esse
caminho end-to-end nos testes de integração abaixo, que exercitam o fluxo real.

**Backend, integração novos** (`apps/api/tests/integration/test_markets_api.py`): `server_now` está
presente, cai dentro da janela de wall-clock observada pelo próprio teste ao redor da chamada, e nunca
é mais antigo que o `ts` de um ticker escrito 1 s no passado — para `GET /markets` e
`GET /markets/{exchange}/{symbol}`.

**Web, novo arquivo** `tests/use-age-ticker.test.ts` (10 testes): `useServerClock` retorna `null` sem
`server_now`/com valor inválido e calcula o offset certo com um valor válido; `useAgeTicker` mantém o
`now` ancorado no servidor com o relógio do viewer 5 min adiantado e 5 min atrasado (replicando o
sintoma exato do relatório da VPS), o tempo real decorrido continua avançando a idade sob um skew
constante, cai para o relógio do viewer com `hasServerClock: false` sem `server_now`, e reancora
quando uma resposta nova chega; `heartbeatServerNowIso` soma `ts + age_s` corretamente e devolve
`null` para um `ts` inválido.

**Web, `tests/markets-quality-badge.test.tsx`** (+14 testes, 6 novos no describe de T3.16): linha
genuinamente fresca lê OK mesmo com o viewer 5 min adiantado; linha genuinamente atrasada continua
"atrasado 20s" mesmo com o viewer 5 min atrasado; sem `server_now` cai para o relógio do viewer **e**
mostra "relógio local"; com `server_now` presente o aviso nunca aparece; um tick em tempo real
(rerender com componente mais fresco) ainda recupera o badge para OK sob o relógio ancorado.

**Web, fixtures ajustadas:** `tests/market-detail-page.test.tsx`/`market-detail-view.test.tsx` ganharam
`server_now` no objeto `MarketDetail` (campo agora obrigatório no tipo gerado).
`tests/execution-paper-card.test.tsx`: o `age_s: 1` do fixture padrão inflava a idade do MTM/proteção
em +1 s sobre o que o teste esperava (comportamento **novo e correto** — antes o componente ignorava
`age_s` de propósito; agora soma, honestamente, o tempo entre o heartbeat e o scan que o gerou). Troquei
o default para `age_s: 0`, documentando por quê, em vez de reescrever os números esperados de "há 5s"
para "há 6s" — mantém o fixture legível como está.

## 8. Comandos e saída real

```
pnpm gen:types
  → openapi-typescript 7.13.0; packages/shared-types/openapi.json → api.d.ts [333.2ms]
  (openapi.json é gitignored, não commitado; api.d.ts foi commitado normalmente, como o resto do diff)

uv run ruff check apps/api/hunter_api/schemas/markets.py apps/api/hunter_api/services/markets.py
  apps/api/tests/unit/test_markets_quality.py apps/api/tests/integration/test_markets_api.py
  → All checks passed!
uv run ruff format --check <mesmos arquivos>          → 1 arquivo reformatado (test_markets_quality.py), depois: já formatado
uv run ruff check apps/api                             → All checks passed!
uv run ruff format --check apps/api                    → 166 files already formatted

uv run pyright apps/api/hunter_api/schemas/markets.py apps/api/hunter_api/services/markets.py
  apps/api/tests/unit/test_markets_quality.py apps/api/tests/integration/test_markets_api.py
  → 0 errors, 0 warnings, 0 informations
uv run pyright apps/api
  → 19 erros, todos em apps/api/tests/unit/test_admission_adapter.py (arquivo intocado por mim,
    git status limpo nele -- pré-existente, de outra tarefa, fora do meu escopo)

uv run pytest apps/api/tests/unit/test_markets_quality.py -q -p no:randomly -k server_now
  → 3 passed
uv run pytest apps/api/tests/unit -q -p no:randomly     → 388 passed, 1 warning in 72.10s
uv run pytest apps/api/tests/integration/test_markets_api.py -q -p no:randomly
  → 29 passed in 103.92s (uma rodada anterior, no meio do desenvolvimento, piscou 1 falha de
    ConnectionResetError [WinError 64] num teste de candles não relacionado a esta tarefa; passou
    isolado logo em seguida -- flake de pool/Docker compartilhado, não desta mudança)

pnpm --filter web typecheck   → limpo (tsc --noEmit, sem saída)
pnpm --filter web lint        → 1 warning pré-existente (lab-signals-table.tsx, complexity 13/12,
                                  arquivo de outra tarefa em voo, T3.17); 0 erros
pnpm --filter web exec vitest run tests/use-age-ticker.test.ts        → 10 passed
pnpm --filter web exec vitest run tests/markets-quality-badge.test.tsx → 14 passed
pnpm --filter web exec vitest run tests/execution-paper-card.test.tsx  → 9 passed
pnpm --filter web exec vitest run  (suíte inteira)     → 591 passed (74 arquivos), 0 falhas
```

## 9. Pendências e limites honestos

- **Sem verificação visual em navegador** com dado real (§6) — pendência explícita para antes do
  commit, por `frontend-always-polished`.
- **`ExecutionPaperCard` corrigido por extensão**, não porque o brief o nomeou — sinalizado para
  confirmação do revisor (§4).
- **Sem segunda opinião da Astra** — não fui instruído a pedir, e o brief não menciona. Se isso for
  esperado nesta tarefa, falta.
- Os testes unitários de `server_now` cobrem o *schema*, não as funções `build_market_list_page`/
  `build_market_detail` que de fato o preenchem (essas só têm cobertura via os testes de integração
  novos) — ver §7 para a justificativa (nenhuma outra função deste módulo tem fake de sessão/Redis no
  nível unitário hoje).
- Incidente de `git stash` (§5): recuperado por completo e verificado, mas registro aqui por
  transparência total — não deveria ter rodado `git stash` num working tree compartilhado por vários
  agentes.

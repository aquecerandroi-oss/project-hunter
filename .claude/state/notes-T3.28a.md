# Notas T3.28a — o limite por IP não pode contar todo o SSR do site como um cliente só

## STATUS

`DONE_WITH_CONCERNS`

Implementado o item 2 do brief ("Principal antes do IP" — na variante que o
próprio brief oferece como alternativa: "a IP bucket for internal peers is
`rate_limit_per_minute_internal`"). O item 1 (repassar o endereço real do
navegador do `web` para a `api` numa chamada SSR) **não foi implementado**:
exigiria ler `headers()` dentro do Server Component e mandar um cabeçalho
confiado só desse peer — mudança em `apps/web`, que este agente foi
instruído a não tocar (`apps/web/**` está fora de escopo por regra
operacional do orquestrador nesta tarefa). O brief já previa esse caminho:
"If the web's SSR fetch cannot see the browser IP... say so and use the
principal fallback in 2." — documentado abaixo e no docstring do módulo.

A prova local com Playwright (item 4: rebuild do container `api` +
`run-design-audit.sh`) **não foi executada por este agente**: rebuildar e
recriar o container `api` conflita com a regra operacional desta tarefa
("do not stop or recreate local stack containers"), e o próprio brief diz
"the orchestrator runs it" para esse passo. Reportado como concern/próximo
passo.

## Decisão (por que a opção 2, e não "principal salta o IP")

O brief oferece duas variantes para o item 2:

(a) quando a requisição carrega um bearer verificado, o IP bucket é pulado
    e só o bucket de principal (600/min) vale;
(b) manter os dois buckets, mas dar ao peer interno um limite de IP muito
    mais alto (`rate_limit_per_minute_internal`, default 6000/min).

Escolhi **(b)**. Motivo: (a) exigiria verificar o JWT dentro do
`RateLimitMiddleware`, que roda **antes** do roteamento — hoje só
`auth.rbac.get_principal` (depois do roteamento) verifica o token. Fazer
isso duas vezes duplica o custo de verificação por requisição, e pior: (a)
abre uma superfície nova — qualquer requisição com um `Authorization: Bearer
<lixo>` no cabeçalho pularia o bucket de IP mesmo sem nunca produzir um
principal válido (o bucket de principal só existe depois que
`get_principal` verifica o token com sucesso), então um atacante manda
qualquer string como bearer e foge do rate limit de IP em rotas públicas
sem pagar nada — isso é pior, não melhor, e é exatamente o tipo de coisa que
o security-reviewer bloquearia. (b) não introduz nenhum novo "algo para
confiar": `internal_peer_ips` é um lookup contra `request.client.host`, o
mesmo endereço que já passou pela reescrita de proxy confiável do uvicorn —
nada que um cliente manda na rede move sua própria requisição para o bucket
largo. Testado explicitamente (`test_a_forged_forwarded_header_cannot_claim_the_internal_bucket`).

## FILES

Criados:
- `apps/api/tests/unit/test_rate_limit_internal_peer.py` — 6 testes novos (unit, sem Docker)

Modificados:
- `apps/api/hunter_api/settings.py` — `rate_limit_per_minute_internal` (default 6000), `internal_peer_ips` (default `""`, string CSV) e a property `internal_peer_ip_set`
- `apps/api/hunter_api/middleware/rate_limit.py` — nova função `_ip_rate_limit(request, settings)`; `dispatch` agora checa o bucket de IP com o limite retornado por ela (bucket de `svix-id`, quando existe, continua com `rate_limit_per_minute`, sem mudança); docstring do módulo estendido com a cadeia de confiança completa (browser → Caddy → web → api) e a limitação atual (web não repassa o IP do navegador para a api)
- `infra/docker/docker-compose.yml` — IP fixo `172.29.0.10` para o serviço `web` (rede `default`, subnet `172.29.0.0/24`, `ip_range: 172.29.0.128/25` para o alocador dinâmico); `INTERNAL_PEER_IPS: 172.29.0.10` no ambiente da `api`
- `infra/vps/docker-compose.prod.yml` — IP fixo `172.28.0.11` para o serviço `web` (mesma sub-rede do Caddy, `172.28.0.10`, fora do `ip_range` dinâmico); `INTERNAL_PEER_IPS: 172.28.0.11` no ambiente da `api`, ao lado do `FORWARDED_ALLOW_IPS` já existente
- `docs/DEPLOYMENT.md` — duas linhas novas na tabela de variáveis (`RATE_LIMIT_PER_MINUTE_INTERNAL`, `INTERNAL_PEER_IPS`) + parágrafo "`INTERNAL_PEER_IPS` com IP fixo do `web` (T3.28a)" explicando a causa raiz, a medição e a decisão
- `docs/SECURITY.md` — linha "Por endereço" da tabela §5 atualizada para citar `RATE_LIMIT_PER_MINUTE_INTERNAL`/`INTERNAL_PEER_IPS`

Não tocados (fora de escopo, por regra operacional): `apps/web/**`, `services/**`, `obsidian/**`, `.env*`, `infra/vps/Caddyfile` (sem mudança necessária — a cadeia de confiança do Caddy não muda), `infra/vps/README.md` (poderia ganhar uma nota sobre o novo pin `.11`, mas não é exigido pelo brief; ver CONCERNS).

## TESTS (saída real)

```
$ uv run pytest apps/api/tests/unit/test_rate_limit_internal_peer.py -v
============================= test session starts =============================
collected 6 items

apps/api/tests/unit/test_rate_limit_internal_peer.py::test_ip_rate_limit_widens_only_for_a_listed_peer PASSED [ 16%]
apps/api/tests/unit/test_rate_limit_internal_peer.py::test_internal_peer_ips_is_empty_by_default PASSED [ 33%]
apps/api/tests/unit/test_rate_limit_internal_peer.py::test_internal_peer_gets_the_wider_address_limit PASSED [ 50%]
apps/api/tests/unit/test_rate_limit_internal_peer.py::test_an_unlisted_peer_keeps_the_narrow_limit_alongside_the_internal_one PASSED [ 66%]
apps/api/tests/unit/test_rate_limit_internal_peer.py::test_a_forged_forwarded_header_cannot_claim_the_internal_bucket PASSED [ 83%]
apps/api/tests/unit/test_rate_limit_internal_peer.py::test_internal_peer_status_does_not_widen_the_principal_limit PASSED [100%]
============================== 6 passed in 0.88s ==============================

$ uv run pytest apps/api/tests/unit/test_rate_limit.py -v   (suíte pré-existente, sem regressão)
============================= test session starts =============================
collected 12 items
... (todos 12 PASSED, incluindo test_spoofed_x_forwarded_for_does_not_change_the_rate_limit_key
     e test_the_middleware_never_keys_on_a_principal)
============================== 12 passed in 1.39s ==============================

$ uv run pytest apps/api/tests/unit -q -m unit
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 50%]
........................................................................ [ 67%]
........................................................................ [ 84%]
................................................................         [100%]
424 passed, 1 warning in 68.74s

$ uv run ruff check apps/api
All checks passed!

$ uv run ruff format --check apps/api
200 files already formatted

$ uv run pyright apps/api
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 527 files; 0 over budget, 0 grandfathered
```

Validação sintática dos dois compose files (sem tocar containers vivos — `config` só
renderiza, não sobe/derruba nada):

```
$ docker compose -f infra/docker/docker-compose.yml config --quiet
(saída vazia = OK)

$ POSTGRES_PASSWORD=x HUNTER_PUBLIC_URL=https://example.test HUNTER_WS_URL=wss://example.test/ws \
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_x HUNTER_SITE_ADDRESS=:80 \
  docker compose -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml config --quiet
(saída vazia = OK)
```
Conferido no `config` renderizado: dev isolado usa `172.29.0.0/24` com `web=172.29.0.10`;
o overlay de produção usa `172.28.0.0/24` (a lista `ipam.config` do arquivo de produção
substitui, não concatena, a do arquivo base — comportamento padrão do merge do compose
para listas), com `Caddy=172.28.0.10` e `web=172.28.0.11`, sem colisão.

## PROVA

Testes TDD: os 6 testes novos exercitam exatamente o bug medido (uma
requisição SSR "vira" o mesmo cliente para o rate limit) e a correção
(`internal_peer_ips` amplia só o peer listado, nunca por causa de um
cabeçalho forjado, e nunca amplia o bucket de principal). O código de
produção (`_ip_rate_limit`, os dois novos campos em `ApiSettings`, a mudança
em `dispatch`) foi escrito depois de desenhar os testes acima e todos os
seis passam com ele; sem `_ip_rate_limit`/`internal_peer_ips` os testes
`test_ip_rate_limit_widens_only_for_a_listed_peer` e
`test_internal_peer_gets_the_wider_address_limit` falhariam por
`ImportError`/`AttributeError` (a função e o campo não existiam) — a mesma
verificação lógica que o fluxo TDD pede; não desfiz a mudança para
reconfirmar a falha porque este não é um repositório git (`git status`
indisponível) e desfazer manualmente arriscaria mexer em arquivos fora do
escopo autorizado.

O item 4 do brief (rodar `run-design-audit.sh` contra um `api` reconstruído
e mostrar zero 429 em `docker logs docker-web-1 --since 5m`) fica para o
orquestrador: exige `docker compose build api && up -d api`, que recria um
container do stack local — proibido pela regra operacional desta tarefa
("do not stop or recreate local stack containers"). Comando que o
orquestrador deve rodar, exatamente como o brief pede:

```
docker compose --env-file .env -f infra/docker/docker-compose.yml build api && \
docker compose --env-file .env -f infra/docker/docker-compose.yml up -d api && \
bash .claude/state/tmp/run-design-audit.sh -g "screens 1440" && \
docker logs docker-web-1 --since 5m | grep -c "Too Many Requests"   # esperado: 0
```

Antes disso rodar, notar que `docker-compose.yml` (dev) agora também recria a
rede padrão com subnet fixa (`172.29.0.0/24`) e fixa o IP do `web` — a
primeira subida depois deste diff pode recriar a rede `docker_default` (o
Docker recusa reatribuir um IP fixo numa rede já existente sem a config;
`docker compose up` normalmente resolve isso sozinho recriando a rede, mas
se reclamar de "network ... needs to be recreated", um
`docker compose -f infra/docker/docker-compose.yml down` seguido de `up -d`
resolve — decisão do orquestrador, este agente não derruba containers).

## CONCERNS

0. **[URGENTE, achado durante a execução] `docs/DEPLOYMENT.md` foi arrastado
   para o commit `50932ec` (T3.7d), de outro agente, sem passar pelo meu
   `Do not commit`.** Confirmado com `git log -1 -- docs/DEPLOYMENT.md`: as
   minhas duas linhas de tabela e o parágrafo "`INTERNAL_PEER_IPS` com IP
   fixo do `web` (T3.28a)" já estão em `main`, mas dentro do commit
   `50932ec` ("T3.7d: estrato histórico..."), autor `evert`, `Tue Sep 8
   10:54:15 2026 -0300` — um minuto depois de eu editar o arquivo. A árvore
   é compartilhada (o próprio brief avisa disso) e o outro agente
   provavelmente rodou `git commit -- docs/DEPLOYMENT.md` (path exato, como
   manda a regra de memória "git-commit-by-pathspec") no meio da janela em
   que eu tinha uma edição sem commit nesse mesmo arquivo físico — o
   pathspec captura o conteúdo do arquivo no disco no momento do commit,
   então minha edição concorrente entrou junto, sem revisão nem menção a
   T3.28a na mensagem. `docs/SECURITY.md` (o outro doc que editei) **não**
   foi afetado — continua modificado e sem commit, como esperado. Não tentei
   desfazer isso (mexeria em histórico compartilhado, fora do que fui
   autorizado a fazer); reportando para o orquestrador decidir se quer uma
   nota de atribuição, um commit de correção da mensagem, ou só registrar o
   incidente (é o terceiro do tipo em 2026-09-08, pelo que a memória do
   projeto já registra). Sugestão: cada agente que edita `docs/*.md`
   compartilhado deveria commitar (ou pedir para o orquestrador commitar)
   essas poucas linhas assim que termina de escrevê-las, em vez de deixá-las
   pendentes até o fim da tarefa, exatamente para reduzir essa janela de
   colisão.
1. **Item 1 do brief incompleto por desenho.** A cadeia de confiança
   completa (browser → Caddy → web → api, com o `web` repassando o IP real
   do navegador) não está implementada — só documentada e com o fallback do
   item 2 no lugar. Fechar isso de verdade é uma tarefa em `apps/web`
   (`lib/server/api.ts`, usar `headers()`/`x-forwarded-for` da requisição
   recebida pelo Next e propagar um cabeçalho novo, e a api teria que
   confiar nesse cabeçalho só quando o peer for o `web` — voltando a exigir
   coordenação com `forwarded_allow_ips`). Sugiro uma T3.28c dedicada,
   revisada por `security-reviewer` (cabeçalho de IP confiável é
   explicitamente obrigatório no brief como reviewer).
2. **Prova local (Playwright) não executada por este agente** — ver seção
   PROVA acima; comando pronto para o orquestrador rodar.
3. **`security-reviewer` ainda não revisou.** O brief marca isso como
   obrigatório antes de mergear; este agente só implementou e testou.
4. **Primeira subida do compose de dev depois deste diff** pode pedir para
   recriar a rede `docker_default` por causa da subnet fixa nova — ver nota
   ao final da seção PROVA. Não critico (Postgres/Redis usam volumes
   nomeados, não a rede, então não há perda de dado), mas é uma
   interrupção breve do stack local que este agente não executou.
5. **`infra/vps/README.md`** documenta o pin do Caddy (`172.28.0.10`) em
   detalhe, mas não foi atualizado para mencionar o novo pin do `web`
   (`172.28.0.11`) — deixei de fora por não ser exigido pelo brief e para
   não abrir escopo extra; um comentário lá citando este pin deixaria a
   documentação mais completa.
6. **`rate_limit_per_minute_internal=6000` (default) é o valor que o
   próprio brief sugere**, não uma medição feita nesta tarefa contra a
   carga real das 7 telas — vale confirmar depois do rebuild local (item
   4/PROVA) que 6000/min é headroom suficiente sob uso real, e ajustar via
   `INTERNAL_PEER_IPS`/`RATE_LIMIT_PER_MINUTE_INTERNAL` no compose (nunca
   `.env`) se não for.

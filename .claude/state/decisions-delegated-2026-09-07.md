# Decisões delegadas pelo Everton à Sexta-feira — 2026-09-07 (D10–D13)

Everton, 2026-09-07, palavra por palavra: **"sexta feira pode decider esses 4"**. Quatro decisões,
tomadas **em nome dele**, reversíveis por ele a qualquer momento respondendo em uma linha. Nenhum
limite escrito por ele foi alterado; nenhuma delas liga nada.

**Astra indisponível até 2026-09-12** (cota do Codex). Nenhuma segunda opinião foi obtida — as
quatro ficam registradas com o raciocínio e os números para revisão adversarial quando ela voltar.
Se ela derrubar um argumento, a decisão muda e a mudança é escrita **aqui**, datada, sem apagar o
que está escrito agora.

Continuação de `.claude/state/decisions-M3-delegated-2026-09-06.md` (D1–D3) e da tabela D4–D9 em
`docs/plans/M3.md`.

---

## D10 — Qual versão de estratégia recebe propósito paper

### Decisão

**`momentum`** — e **não** por mutação de uma versão existente: a coorte de paper nasce como uma
**linha nova e congelada** em `strategy_versions`, com `purpose = paper`, `parameters_schema`,
`default_parameters` e `params_format` copiados bit a bit da versão de momentum ativa na VPS hoje, e
`code_ref` recalculado para a árvore implantada. A coorte `research_only` **continua ativa e
intocada**, ao lado.

**Nada é ativado agora.** A ativação é ato deliberado, manual, auditado
(`infra/scripts/activate_strategy_version.py` grava `system_events` em toda execução, ativação ou
recusa), anunciado ao Everton antes, e **nunca acontece dentro de um plantão**.

### Fundamento com os números reais

**1. O achado que muda a pergunta: o rótulo "paper" não existe em lugar nenhum do código.**

| Onde | O que está escrito |
|---|---|
| `packages/core/hunter_core/strategies/envelope.py:33,128` | `PURPOSE_RESEARCH_ONLY = "research_only"`, default do envelope |
| `services/strategy-worker/hunter_strategy_worker/record.py:198,229` | `"purpose": PURPOSE_RESEARCH_ONLY` **cravado** nos dois payloads emitidos |
| `packages/core/hunter_core/db/models/agents.py:67-93` (`StrategyVersion`) | **não existe coluna `purpose`** |
| `services/execution-worker/hunter_execution_worker/bridge_screen.py:53,156-157` | `PURPOSE_LIVE = "live"`; qualquer outro valor é recusado com motivo `research_only` |
| `packages/core/hunter_core/admission/sources.py:62,212,259` | o mesmo `"live"`, repetido de propósito para falhar fechado |

Ou seja: o produtor **só sabe escrever** `research_only` e o consumidor **só aceita** `live`. Entre
os dois há exatamente um rótulo faltando, e ele não é escolha de linha de banco — é coluna,
migração, envelope e portão. **A pergunta "qual versão recebe propósito paper" não tem resposta
executável hoje**; o que se decide aqui é qual versão receberá, e com que forma.

**2. Por que uma linha nova e não mutar a existente.** `purpose` mora dentro do envelope congelado
do sinal, e a coorte é separada pelo `strategy_version_id`, que entra no `uuid5` de cada sinal
(protocolo congelado de `EXP-0001-momentum-v1.md`). Virar o propósito de uma versão em voo
misturaria, dentro do **mesmo** `strategy_version_id`, sinais que eram evidência e sinais que
movem capital — e quebraria a linha do protocolo que diz "todo sinal carrega
`purpose = research_only`", que é congelada e nunca se edita. Duas coortes lado a lado dão de graça
a comparação que interessa: **o mesmo gatilho medido hipoteticamente pelas barras e medido pela
carteira**, com os custos de verdade do simulador.

**3. Por que momentum e não volume_anomaly.** Leitura datada da VPS, `as_of = 2026-09-06T13:00:00Z`,
`read_at = 13:26:35.681334Z`, saída de SQL colada em `EXP-0001`/`EXP-0002`:

| | `momentum v1` | `volume_anomaly v1` |
|---|---|---|
| Emitidos / entradas | 208 / 208 | 459 / 443 |
| Recusas de entrada por **geometria** | **0** | **16** (3,5 %) |
| Avaliáveis / com `r_multiple` | 105 / 91 | 352 / 316 |
| Mercados / dias distintos | 134 / **1** | 134 / **1** |
| Taxa de alvo entre toques resolvidos | 0,5333 | 0,5000 |
| Taxa de lucro líquido | 0,3956 | 0,3165 |
| Expectancy líquida hipotética | **−0,2102 R** | **−0,2304 R** |
| Profit factor | 0,6084 | 0,6539 |

Três razões, nenhuma delas de desempenho:

- **Geometria.** A ponte revalida a geometria congelada de todo sinal (`_geometry_reason`,
  `bridge_screen.py`). Momentum produziu **zero** sinais reprovados nesse critério em 208;
  volume_anomaly produziu 16 em 459. Cada recusa hoje custa ~240 incrementos de contador e log pelo
  bug já registrado (item 1 de `.claude/state/review-T3.14.md`);
- **Refém de lacuna.** A janela de volume do volume_anomaly exige **288 barras de 5 min contíguas
  (1.445 minutos)**: um único minuto ausente torna o mercado `unavailable: gap` por até ~24 h
  (`EXP-0002`, protocolo). Neste sistema, cuja lacuna de cobertura é o HIGH aberto em produção e
  cujo `hb:strategy:shadow` contou **63.793** avaliações `unavailable`, essa é a estratégia mais
  exposta ao defeito que já temos. Momentum decide em 15 min com ATR de 15 min e não carrega essa
  janela;
- **Volume de sinal.** 208 em 9 h contra 459 em 9 h. Com 5 vagas, uma posição por moeda e uma vaga
  por ciclo (D3), o fluxo menor deixa a ordenação de prioridade **legível** na auditoria em vez de
  afogada.

**4. Correção da recomendação do orquestrador, com o dado.** A recomendação chegou como "momentum
v1, porque é a única com replay R1 e leitura datada". **Não é verdade** e a decisão não se apoia
nisso: o replay R1 (`.claude/state/r1-proof.md`, `as_of = 2026-09-06T20:55:00Z`) cobriu **as quatro**
coortes, e as duas `v1` reproduziram **perfeitamente** — `momentum_v1` 65 de 65 e
`volume_anomaly_v1` 82 de 82, taxa 1,0000, **0 campos de trajetória divergentes**. As divergências
(5 em momentum_v2, 9 em volume_anomaly_v2) são **só de liquidação**, atribuídas a funding ingerido
depois — "compatível, não comprovada", como o próprio artefato diz. E leitura datada existe para as
duas estratégias, nas duas avaliações de `EXP-0001` e `EXP-0002`.

**5. O que estes números NÃO autorizam a dizer.** Expectancy negativa nas duas, **1 dia distinto**
contra o limiar editorial de 100 outcomes **E** 30 dias, e `EXP-0004` fechou `Result: inconclusivo`
por `B = 1`. **Nenhuma das duas está validada como preditor.** A coorte de paper não é ativada
porque momentum funciona — é ativada para provar o **caminho** (sinal → ponte → admissão → Risk
Engine → fill paper → ledger → proteção) com dinheiro fictício e evidência de verdade. Quem ler
esta decisão como "escolhemos a estratégia vencedora" leu errado.

**6. Rótulo, e um risco de nome que fica resolvido junto.** O único propósito admissível hoje se
chama `"live"`, num repositório cuja regra dura é "nada de dinheiro real antes da Fase 4". A coorte
de paper **não** vai carregar esse nome. Decisão: o rótulo admissível para carteira `type=paper`
passa a ser **`paper`**; `live` continua definido e **recusado por nome** até a Fase 4, com a
mensagem dizendo isso. Falha fechada nos dois sentidos. **Ressalva registrada:** a ordem manual da
API usa hoje `purpose = live` como default (`sources.py:212`); ela migra para `paper` no mesmo diff.
Se o `risk-engine-guardian` mostrar que a troca quebra a trilha de auditoria da ordem manual, o
plano B é manter `live` como está e criar a coluna `purpose` na versão do mesmo jeito — o que não é
negociável é **a versão dizer o propósito**, em vez de o worker cravá-lo.

### Condição de ativação (as sete, todas verificáveis)

Nenhuma sozinha basta; a ativação só acontece com as sete cumpridas e escritas:

1. **T3.9b verde** — as verificações de `.claude/state/spec-T3.9-verificacoes.md` que ainda não têm
   prova (V4 a V9, S10, S11), com saída real. As quatro da T3.9a não bastam, e a divergência V1
   registrada lá (`binding_constraint = total_exposure`, não `cash`) fica resolvida ou aceita por
   escrito;
2. **T3.14b fechada e revisada** — os quatro MUST-FIX de `.claude/state/review-T3.14.md` mais o item
   do rótulo, com revisão do `risk-engine-guardian`;
3. **T3.15 entregue e revisada** — coluna `purpose` em `strategy_versions` (imutável depois da
   ativação, como `code_ref`), envelope lendo o propósito **da versão** em vez do literal, portões
   da ponte e da admissão aceitando `paper` e recusando `live`, e o script de ativação sabendo
   criar a linha nova sem tocar na coorte `research_only`;
4. **Caminho spot ligado e provado na VPS** — `MARKET_SPOT_ENABLED=true` no shard 0 **depois** da
   T3.0d (a colisão de `candle_event_id` sem `market_type` descarta em silêncio o fechamento de vela
   de um dos dois produtos e **bloqueia ligar spot em ambiente compartilhado**, `notes-T3.0c.md` §9)
   e **depois** de medida a folga de event loop (`t30-proof.md` §5: com 200 perpétuos no mesmo
   processo o socket perdeu keepalive, 8 reconnects, 0 velas em 5 min);
5. **β válido** para o mercado do sinal (T3.7) — sem ele a ponte recusa de qualquer modo, e a
   diretiva do Everton manda o ativo ficar só em shadow;
6. **`EXP-0005` aberto antes do primeiro sinal**, com hipótese e protocolo congelados, linkado a
   `EXP-0001` — a coorte de paper é conteúdo diferente (é executada), então é experimento novo, não
   avaliação nova do antigo;
7. **Segunda opinião da Astra** sobre o conjunto (volta em 2026-09-12). É desenho no caminho do
   dinheiro; a regra manda.

Mais uma medição antes do ato, porque duas versões ativas dobram a avaliação de momentum no
`strategy-worker` (208 sinais em 9 h viram ~416/dia): **medir a folga do ciclo do worker** e
registrar o número. Se não houver folga, a segunda coorte espera.

### O que muda / dono

- **T3.15 (nova)** — propósito na versão, `paper` como rótulo, portões. Owner `backend-specialist`,
  revisão obrigatória de `risk-engine-guardian` e `security-reviewer`. Arquivos:
  `packages/core/hunter_core/{strategies,admission}/**`, `packages/core/hunter_core/db/models/agents.py`,
  `infra/migrations/versions/**`, `services/strategy-worker/**`, `services/execution-worker/bridge_screen.py`,
  `infra/scripts/activate_strategy_version.py`. **Depende da T3.14b e não entra em onda com nenhuma
  tarefa que toque os mesmos globs.**
- A ativação em si: ato da Sexta-feira, anunciado ao Everton antes, registrado em `system_events`,
  no `Changelog` e no diário.

### O que NÃO muda

`ENABLE_PAPER_AUTONOMY` continua `false` e a T3.15 **não** o liga. O aceite do M3 continua **sem**
entradas autônomas (decisão conjunta, item 9). A coorte `research_only` continua rodando, com o
mesmo protocolo e a mesma página. Nenhum limite do Everton foi tocado. Dinheiro real continua na
Fase 4, atrás de `ENABLE_LIVE_TRADING` e do `LiveExecutionAdapter` que levanta `LiveTradingDisabled`.

---

## D11 — Alvo do p99 tick→oportunidade do M2

### Decisão

**O número 3 s fica. O que se renegocia é o universo em que ele é cobrado**, e passa a haver um
segundo alvo, explicitamente mais fraco, para o resto:

| Alvo | Universo | Número |
|---|---|---|
| **A — caminho do dinheiro** | os perpétuos cuja **contraparte spot** passa o piso de 50 M USDT/24 h — **19** na fixture gravada em 2026-09-07 03:36Z (19 de 740 pares USDT), 16 a 19 ao vivo | **p99 ≤ 3 s** |
| **B — vitrine do Radar** | os demais ~181 dos 200 monitorados | **p99 ≤ 15 s** |

### Fundamento com os números reais

**De onde veio o 3 s:** `.claude/state/dialogue-M2.md:97,127` — "features 1 s + scorer 2 s", p99 em
operação saudável com 200 mercados. Foi escrito **antes de existir carteira**: é um alvo de vitrine
aplicado uniformemente a 200 mercados, dos quais a esmagadora maioria **nunca poderá gerar uma
ordem**, porque não tem par spot acima do piso (D1: spot executa, perpétuo decide).

**O que foi medido** (`.claude/state/t25-proof.md`, 2026-09-07):

| Topologia | `market.ticks` p50 / p95 / p99 | tick→oportunidade |
|---|---|---|
| 1 processo × 200 | 25,82 s / 26,47 / 26,73 | — |
| **4 shards × ~50** (topologia da VPS) | 4,31 s / 5,54 / **5,65** | média **7,74 s**; ≤ 3 s **0,3 %**; ≤ 8 s 59,6 %; ≤ 13 s 97,8 %; ≤ 21 s 100 % |
| 8 shards × ~25 | 0,41 s / 11,28 / 11,51 | média 2,55 s; ≤ 1 s 54,2 %; ≤ 3 s **70,5 %**; ≤ 8 s 93,0 %; ≤ 13 s 99,9 % |

**Causa medida, não suposta:** `crc32(symbol) % N` equilibra **contagem**, não **tráfego** — com 8
shards os descartes por processo na mesma janela foram `73 · 10.232 · 21.799 · 3.231 · 50.867 · 0 ·
162.386 · 175.839`; e `queue_oldest_pending_ts` custa **11,25 %** de CPU cumulativa (py-spy, 4.116
amostras) varrendo a fila inteira a cada 250 ms.

**Por que o universo do alvo A são os perpétuos, e não os pares spot** — correção da recomendação do
orquestrador: **o scanner e o Radar são cegos ao spot** (`notes-T3.0c.md` §6; a rota de detalhe
também). Não existe, e não está no escopo de ninguém hoje, uma "oportunidade" calculada sobre spot.
Medir "p99 ≤ 3 s nos 19 pares spot" seria medir um número que não existe. O que existe, e é o que
custa dinheiro, é a latência **no perpétuo que decide** por um ativo cujo par spot é negociável.

**Por que 15 s para a vitrine:** com 4 shards, 97,8 % das amostras ficam ≤ 13 s e 100 % ≤ 21 s. 15 s
cai dentro do envelope medido sem ser confortável. Abaixo disso o alvo de vitrine seria uma promessa
que a topologia atual nunca cumpriu; acima, seria alvo que não mede nada.

**Os dois alvos são medidos depois da T2.5h** (shard por tráfego — a causa medida), na VPS, numa
janela única e datada, publicando a **distribuição**, não só o p99.

### O que muda no relatório do M2

A condição 3 fica **reescrita e datada**, com o número antigo preservado palavra por palavra. E
registro o que **recusei** fazer: a redação da condição 3 (que eu mesma escrevi em nome do Everton)
admite literalmente "renegociação explícita do alvo com o número medido ao lado" — bastaria escrever
esta decisão para declará-la satisfeita. **Não declaro.** Renegociar o universo não mede coisa
alguma; a condição continua exigindo a **medição** do alvo A nos 19 mercados. Um critério de
aprovação que eu satisfaço reescrevendo-o não é critério.

### Dono / tarefa

**T2.5h** (shard por tráfego + custo do portão de cobertura), owner `backend-specialist`, revisão
`code-reviewer`; a medição dos dois alvos é entregável da própria tarefa.

### O que NÃO muda

O M2 continua **NÃO APROVADO** (condições 2 e 4 abertas, e a 3 agora exige medição no universo
novo). O orçamento de 3 s **não foi afrouxado** onde importa. A decisão conjunta do M2 não é apagada:
fica citada, com data, ao lado da renegociação.

---

## D12 — Histerese do piso de 50 M USDT no universo spot

### Decisão

**Banda só na saída. A admissão não se relaxa.**

- **Admissão (entrar no universo):** `quote_volume_24h >= 50 000 000 USDT` medido **no spot**,
  inclusivo, quote `USDT`, status `TRADING`, fora da blocklist, **com ticker legível** — exatamente
  como está hoje (`spot_universe.py`, T3.0c §4). **Não muda uma vírgula.** Não existe caminho para
  um par entrar com menos de 50 M;
- **Permanência (sair do universo):** um par **já admitido** só sai quando
  `quote_volume_24h < 40 000 000 USDT` (80 % do piso) em **3 refreshes consecutivos** (≈ 45 min na
  cadência de 15 min). Ticker ilegível conta como uma observação **abaixo** — nunca como acima —, de
  modo que 3 refreshes sem leitura também tiram o par;
- **Saída imediata, sem banda e sem contagem:** deixar de ser `TRADING`, deixar de ser quote `USDT`,
  ou entrar na blocklist;
- **A contagem é durável e sobrevive a restart**, e cada entrada ou saída publica
  `market.universe.changed` com o motivo e o valor observado. Contador em memória traria o flap de
  volta no primeiro deploy.

### Fundamento com os números reais

`PROMUSDT` entrou e saiu **entre dois refreshes** durante a prova, com o volume 24 h oscilando em
torno de 50 M (`notes-T3.0c.md` §8 e `t30-proof.md` §2). Universo ao vivo: **16 a 19 pares**; fixture
das 03:36Z: **19 de 740** pares USDT. Cada oscilação custa um `market.universe.changed` a cada 15 min
para o mesmo par, e — quando a ponte estiver ligada — muda a elegibilidade de execução de um ativo
sem que nada de material tenha mudado no mercado.

**Por que 40 M não expõe a carteira.** O piso de 50 M é **filtro de admissão**, não a proteção de
liquidez do dimensionamento. A proteção contra mercado fino é a participação de **1 % do minuto**
(D2), medida no instante da proposta no venue de execução, agregando todos os agentes: um par entre
40 e 50 M continua limitado por ela, e abaixo do `min_notional` a entrada é recusada com motivo. A
banda encurta o flap; não afrouxa o que protege dinheiro.

**Por que 3 refreshes.** 45 min é mais longo que a oscilação observada e mais curto que a barra de
decisão mais lenta que alimenta a carteira (15 min de momentum, horizonte de 4 h). Um par que
realmente secou é retirado dentro de uma hora; um que respirou na borda não gera evento nenhum.

**Registro exigido pela diretiva:** o "piso de 50 M USDT 24 h" é número do Everton. **A histerese
não relaxa a admissão** — ela só existe do lado da saída, para um par que já passou o piso cheio.
Nenhum par entra com 40 M.

### O que muda / dono

**T3.0e (nova).** Owner `exchange-integration-specialist`. Arquivos:
`services/market-worker/hunter_market_worker/spot_universe.py` e testes do mesmo serviço.
**Depende da T3.0d, que está em voo nos mesmos arquivos** — não despachar antes de a T3.0d estar
commitada. Revisores: `code-reviewer` e `risk-engine-guardian` (leitura: o universo é o portão do
que a carteira pode negociar).

### O que NÃO muda

Sair do universo **não encerra gestão** — essa é a regra do hold durável da T3.0 ("sair da
elegibilidade impede entradas e não encerra gestão"), e a histerese **não** é substituta dela: se um
par sai com posição aberta, a posição continua sendo gerida e protegida. O piso de admissão, o
`monitor_rank` (que continua sem decidir nada) e a regra "sem ticker = fora" na admissão continuam
como estão.

---

## D13 — Domínio da VPS

**Eu não compro nada.** Serviço pago é decisão e ato do Everton. Isto é recomendação e passo a passo.

### Decisão (recomendação)

| Item | Recomendação |
|---|---|
| Nome | **`projecthunter.app`** (alternativas: `hunterquant.app`, `project-hunter.com`) — **disponibilidade não verificada por mim**, confere no registrador |
| Registrador | **Cloudflare Registrar** (renovação a preço de custo, WHOIS privacy incluída, sem upsell). Exige usar o DNS da Cloudflare |
| DNS | **Cloudflare DNS com o proxy DESLIGADO** (nuvem cinza) no primeiro momento |
| TLS | Let's Encrypt tirado pelo próprio Caddy, como o `Caddyfile` já faz quando `HUNTER_SITE_ADDRESS` é um domínio |
| Proxy laranja | **viável depois**, com SSL mode **Full (strict)** — e só depois do certificado do Caddy estar de pé |

### Fundamento com o que está no repositório

**Por que `.app`:** o TLD inteiro está na lista de HSTS preload dos navegadores — HTTPS é obrigatório
por construção. Isso mata, na raiz, o modo de falha registrado **duas vezes** neste repositório: sem
HTTPS o Clerk grava os cookies de sessão como `Secure; SameSite=None`, o navegador os descarta e o
sign-in entra em loop (`infra/vps/Caddyfile`, `infra/vps/README.md`, `docs/DEPLOYMENT.md` §9.6).

**Por que proxy desligado no começo**, três motivos medidos neste repositório:

1. **Uma peça em vez de três.** Com a nuvem cinza, o Caddy tira o certificado sozinho e a borda fica
   idêntica à documentada. Com a nuvem laranja há dois certificados e um "SSL mode" — e enquanto a
   origem ainda servir o certificado interno (`HUNTER_TLS_ARG=internal`, o estado de hoje), o modo
   Full (strict) falha no handshake: é a mesma classe de erro do incidente de 2026-09-06 que obrigou
   a existir o `default_sni`;
2. **`FORWARDED_ALLOW_IPS`.** A api só confia em `X-Forwarded-For` vindo do IP do container do Caddy
   (`docs/DEPLOYMENT.md` §9.3, e o incidente de colisão de IP de 2026-09-07). O proxy acrescenta um
   salto: sem configurar, o IP do cliente nos logs passa a ser o da Cloudflare;
3. **Nada no sistema depende de um domínio.** Os workers não usam a origem pública; o domínio serve
   o navegador.

**E o WebSocket, que ele perguntou:** o único transporte de tempo real do sistema é o
**WebSocket em `/ws`** — varri o repositório e **não existe SSE** (nenhum `text/event-stream` em
`apps/api` nem em `apps/web`), então o problema clássico de buffering da Cloudflare não se aplica. E
o proxy da Cloudflare derruba WebSocket ocioso por volta de 100 s, enquanto **o gateway manda
`{"type":"ping"}` a cada 25 s e fecha com `4408` se não vier `pong`**
(`apps/api/hunter_api/realtime/endpoint.py:15,304-317`): a conexão nunca fica ociosa. **Ligar o proxy
depois é seguro do ponto de vista do tempo real** — o que pede cuidado é o TLS, não o `/ws`.

**Preço:** não invento número. O que o registrador cobrar no dia é o preço; `.app` costuma ficar na
faixa de poucas dezenas por ano — **estimativa a confirmar**, não me baseio nela para recomendar.

### O passo a passo que ele executa (as mãos são dele)

1. Comprar `projecthunter.app` no Cloudflare Registrar (ou o que estiver livre da lista);
2. No painel de DNS: registro **A**, nome `@`, valor **o IP da VPS**, **proxy desligado** (nuvem
   cinza). Opcional: `www` como CNAME para o apex, também cinza;
3. Esperar propagar — `dig +short projecthunter.app` (ou `nslookup`) tem que devolver o IP da VPS;
4. Na VPS, **no terminal dele**:
   ```
   ssh hunter@<ip>
   cd /opt/project-hunter
   bash infra/scripts/setup_env.sh --vps
   ```
   Responder o domínio (`projecthunter.app`) e um **e-mail real** para o aviso de certificado. O
   script preserva o `POSTGRES_PASSWORD` existente e pede as chaves do Clerk com digitação oculta —
   **nenhuma chave passa por chat, log ou agente**;
5. `bash infra/vps/compose.sh update`;
6. Abrir `https://projecthunter.app/` e fazer sign-in. Se o Clerk reclamar de origem, me avisar.

Depois disso eu atualizo `docs/DEPLOYMENT.md`, `infra/vps/README.md` e as páginas do Obsidian, e o
`HUNTER_DEFAULT_SNI` passa a ser o domínio (o `compose.sh` deriva sozinho de `HUNTER_SITE_ADDRESS`).

### Até lá, o que fica

Exatamente o de hoje: **IP + certificado interno do Caddy** (`HUNTER_TLS_ARG=internal`), com
`HUNTER_DEFAULT_SNI` derivado do IP porque navegador não manda SNI para endereço numérico. O
navegador pede para aceitar o certificado uma vez, e o **sign-in do Clerk é pouco confiável nesse
modo** — limitação já documentada, serve para ver a stack de pé, não para usar todo dia.

### O que NÃO muda

Instância do Clerk continua a de desenvolvimento (`pk_test_`). Migrar para instância de produção é
**outra** decisão (pede CNAMEs próprios, sempre DNS-only) e **não** é pré-requisito do domínio.
`ENABLE_LIVE_TRADING=false` e `SYSTEM_KILL_SWITCH=ACTIVE` continuam como estão. Nenhuma porta nova é
aberta: o ufw continua com SSH + 80/443.

---

## Registro

- Plano: `docs/plans/M3.md` — D10 a D13 na tabela "Respostas às perguntas"; **T3.0e** e **T3.15** na
  lista de tarefas.
- Relatório: `docs/reports/M2.md` — só a condição 3, reescrita e datada, com o número antigo
  preservado.
- Obsidian: `03-TRADING/Portfolio.md`, `09-OPERATIONS/Diario/2026-09-07.md`, `00-HOME.md`,
  `06-DECISIONS/Architecture Decisions.md`.
- **Pendência declarada:** as quatro vão à Astra em 2026-09-12, com as perguntas adversariais já
  óbvias — o rótulo `paper` contra a ordem manual, o alvo B de 15 s, a banda de 40 M e o proxy da
  Cloudflare. O que ela derrubar é escrito aqui, datado.

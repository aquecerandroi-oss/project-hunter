---
tags: [decisao, risco, limites, sizing, m3]
titulo: Limites de risco — o teto de 0,25 % por operação é inerte; quem manda é a participação de 1 % do volume
data: 2026-09-08
updated: 2026-09-08
owner: sexta-feira
origem: T3.48 (risk-engine-guardian), pedido de Everton 19:35 BRT
status: aguardando decisão de Everton (participação / universo líquido)
decided_on: 2026-09-08
by: risk-engine-guardian
---

# Proposta de limites de risco — o que muda (e o que não muda) se o risco por operação subir de 0,25 %

**Para:** Everton. **De:** risk-engine-guardian. **Data:** 2026-09-08, 19:40 (Brasília; 22:40 UTC).
**Origem:** seu pedido de 2026-09-08 19:35 — *"precisamos começar a positivar as entradas; se
necessário aumentar valores de estratégia e ser mais arriscado"*.
**Estado:** nada foi alterado. Nenhum limite mudou, nenhum código mudou, nada foi commitado. Este
documento existe porque a sua própria diretiva manda: *documente e me apresente antes de alterar os
limites*. A decisão é sua.

**Leituras (`as_of`):** banco da VPS, transação somente-leitura, 2026-09-08 **19:25 / 19:32 / 19:34
Brasília** (22:25 / 22:32 / 22:34 UTC). SQL e saída completa em `infra/scripts/sql/research/2026-09-09-t348-*.sql`.
**Patrimônio da carteira:** 19.333,0111 USDT = R$100.000 (câmbio implícito do seed, R$5,1725/USDT).

---

## 1. A resposta em quatro linhas

1. **Tamanho multiplica reais; nunca troca o sinal.** Com a expectância líquida de hoje (negativa em
   **5 das 6** versões com desfechos suficientes), qualquer aumento de tamanho perde mais rápido,
   não menos.
2. **E, hoje, aumentar `risk_per_trade_pct` não aumentaria tamanho nenhum.** Medi: de 346 sinais da
   linha `paper` nas últimas 24 h, subir 0,25 % → 0,50 % mudaria o tamanho de **5** (1,4 %); subir
   para 1,00 % mudaria os mesmos 5, e nada mais. Quem decide o tamanho hoje é o **teto de
   participação de mercado** (1 % de um minuto de volume), em 164 dos 176 mercados.
3. **O jeito honesto de "ser mais arriscado por entrada" já está liberado e não mexe em limite
   nenhum:** stop mais largo (T3.47). Ele aumenta o dinheiro em risco por operação **e** baixa o
   pedágio — as duas coisas que você pediu.
4. **Minha recomendação: manter 0,25 %.** Não por prudência genérica: porque mudar esse número hoje
   é uma mudança **inerte**, e uma mudança inerte num limite seu gasta a sua confiança sem mover
   um centavo.

---

## 2. O fato 1: tamanho multiplica, não inverte

Conversão usada (identidade, não estimativa): `R$ por 1 R = notional aprovado × distância do stop`.
O `notional aprovado` é o mínimo dos nove tetos do motor (`RISK_ENGINE.md` §4), calculado com o
volume real de cada mercado. Ver §3 para por que **não** uso o rótulo de 0,25 %.

**Tabela A — resultado mensal com o tamanho que o motor aprova hoje** (`as_of` 19:25–19:34 Brasília;
coorte prospectiva = universo vivo, ~200 mercados; "mês" = 30 dias no ritmo medido):

| versão | R$ por 1 R | expectância líq. (R) | R$/op | ops/dia | R$/dia | R$/mês | %/mês |
|---|---|---|---|---|---|---|---|
| **momentum v3** (linha `paper`) | 5,88 | −0,2158 | −1,27 | 313 | −397 | **−11.917** | −11,9 % |
| momentum v2 | 6,14 | −0,2006 | −1,23 | 332 | −409 | −12.277 | −12,3 % |
| momentum v4 | 7,01 | −0,1398 | −0,98 | 112 | −110 | −3.292 | −3,3 % |
| momentum v6 | 3,70 | −0,3823 | −1,42 | 17 | −24 | −722 | −0,7 % |
| volume_anomaly v2 | 2,73 | −0,2538 | −0,69 | 522 (teto de 5 slots) | −362 | −10.849 | −10,8 % |
| mean_reversion v1 | 3,93 | **+0,0480** | +0,19 | 24 | +5 | +136 | +0,1 % |

**Os mesmos números a 0,50 % e a 1,00 % de risco por operação são idênticos** — coluna por coluna,
centavo por centavo. Não é arredondamento: é o §3.

Na coorte de replay de 31 dias (massa, **não veredito** — o replay herda o universo de hoje e a
janela que inventou as hipóteses): momentum v3 −R$328/mês, volume_anomaly v2 −R$551, mean_reversion
v2 +R$365, mean_reversion v3 +R$803 (n = 17 e 11; ver §5).

---

## 3. O achado que muda a pergunta: `risk_per_trade_pct` não é quem decide o tamanho hoje

O motor toma o **mínimo** entre nove tetos (`packages/risk-core/hunter_risk/sizing.py:122-212`).
Calculei os três que podem morder, mercado a mercado, com o volume real das últimas 24 h:

| teto | fórmula | valor típico na linha `paper` |
|---|---|---|
| `risk_per_trade` | patrimônio × 0,25 % ÷ (stop + custo) | **≈ 3.000 USDT** |
| `asset_exposure` | patrimônio × 10 % | 1.933 USDT |
| `market_participation` | 1 % de um minuto de volume | **≈ 70 USDT** ← vence |

**Tabela B — qual teto vence (momentum v3, 346 sinais / 176 mercados, `as_of` 19:32 Brasília):**

| tamanho por operação | `market_participation` | `asset_exposure` | `risk_per_trade` |
|---|---|---|---|
| 0,25 % (hoje) | 164 mercados / 318 sinais | 10 / 23 | **2 / 5** |
| 0,50 % | 165 / 322 | 11 / 24 | **0 / 0** |
| 1,00 % | 165 / 322 | 11 / 24 | **0 / 0** |

Consequências, medidas:

- **Tamanho aprovado hoje: 70 USDT (mediana) = R$362.** O risco real por operação é **0,0067 % do
  patrimônio (≈ R$6,70)** — 37× abaixo do rótulo de 0,25 % (R$250). O rótulo não está errado, ele
  é **teto**, e outro teto mais apertado chega antes.
- **Subir para 0,50 % muda 5 sinais em 346.** E mesmo neles o aumento não é ×2: em `USELESSUSDT` o
  tamanho iria de 1.020 para 1.644 USDT (+61 %), porque o teto seguinte (participação) o segura.
- Para o teto de risco voltar a ser o que decide num mercado típico, ele teria de **cair** para
  0,0059 % — não subir.

Isto é o mesmo padrão que o contrato já registrou uma vez (`RISK_ENGINE.md` §9, item 1, KB-0066): um
limite com nome de protagonista que, na prática, nunca atua. Registrar de novo é honestidade, não
pedantismo.

**Correção a uma premissa do meu próprio brief:** "1 % agregado = 4 operações a 0,25 %" só vale se o
teto de risco vencer. O risco agregado conta o risco **planejado do tamanho aprovado**
(`sizing.py:255`), que hoje é 0,0067 % por posição — cinco posições somam 0,03 %, contra o teto de
1 %. **Quem limita as posições simultâneas hoje é `max_concurrent_positions = 5`**, e esse número
não depende do risco por operação. Dobrar o risco por operação **não** reduziria os slots de 4 para 2.

---

## 4. O que "mais arriscado" pode significar, e o preço de cada caminho

### (a) Stop mais largo por entrada — **liberado hoje, sem mexer em limite nenhum**

`custo_R = 0,0020 ÷ (stop_atr × ATR%)`: dobrar a largura do stop corta o pedágio pela metade. E,
como o tamanho está preso ao teto de participação (§3), um stop 1,5× mais largo **aumenta** o
dinheiro em risco por operação na mesma proporção: momentum v3 sairia de 0,0067 % para ~0,010 % do
patrimônio por entrada. É exatamente "mais arriscado por entrada", e continua 25× abaixo do seu teto.

**O preço:** o teto `max_stop_distance_pct = 0,03` recusa a entrada cujo stop passe de 3 % do preço
(check 8). Medido, na coorte prospectiva:

| versão | stop > 3 % hoje | com stop ×1,5 | com stop ×2 |
|---|---|---|---|
| momentum v3 (`paper`) | 11,5 % dos sinais | **23,6 %** | **46,3 %** |
| momentum v2 | 12,3 % | 24,1 % | 47,0 % |
| momentum v4 | 18,8 % | 37,5 % | 73,2 % |
| momentum v6 | 11,8 % | 17,6 % | 35,3 % |
| **mean_reversion v1** (a única positiva) | **0,0 %** | **8,3 %** | 16,7 % |

Leitura: para a família `momentum` no universo vivo, o stop ×2 custa quase metade das decisões. Para
a `mean_reversion` — justamente a de expectância positiva — é quase de graça. **Isso reforça
concentrar em `mean_reversion` em vez de alargar a `momentum`.**

### (b) Subir `risk_per_trade_pct` — inerte hoje; e o que custaria no dia em que morder

Hoje: nada muda (§3). Se um dia o teto de participação deixar de ser o gargalo (mercados grandes,
patrimônio menor, ou stops muito largos), o degrau é este — e é o kill switch que paga a conta:

| tamanho | paradas cheias seguidas até AVISO (1 %/dia) | até BLOQUEIO (2 %/dia) |
|---|---|---|
| 0,25 % | 4 | **8** |
| 0,50 % | 2 | **4** |
| 1,00 % | 1 | **2** |

E as sequências perdedoras **observadas** são maiores que isso: momentum v3 encadeou **22 perdas
seguidas**; momentum v6, 20 no replay; volume_anomaly v2, 26. Nesse cenário hipotético (teto de
risco vencendo), a 1,00 % o pior dia medido da momentum v3 (−67,6 R) valeria **−R$59.316** se o
bloqueio não existisse — o bloqueio corta em −R$2.000, e
**a retomada é manual, sua** (`RISK_ENGINE.md` §5). Ou seja: a 1 %, a carteira travaria e ficaria
parada esperando você, provavelmente no primeiro dia.

Com o tamanho **real** de hoje, nada disso acontece: a perda diária projetada da momentum v3 é
−0,40 %/dia, abaixo do aviso de 1 %; quem morderia primeiro é a escada de drawdown — **aviso (4 %)
em ~10 dias, bloqueio (8 %) em ~20 dias**.

### (c) Mais posições ao mesmo tempo

O teto agregado de 1 % não morde (§3); `max_concurrent_positions = 5` morde. O Lab pediria muito
mais: momentum v3 chegou a **52 posições simultâneas** na coorte prospectiva e passou **86,9 % do
tempo acima de 5**. Ou seja, a carteira já executa uma amostra pequena do que a estratégia sinaliza —
e ampliar essa amostra multiplica uma expectância negativa. Não recomendo mexer.

---

## 5. Recomendação do guardião

**Manter `risk_per_trade_pct = 0,0025`.** A condição para subir, escrita de antemão para que não seja
opinião no calor do momento — **as três juntas**:

1. **expectância líquida > 0** na coorte **prospectiva** (não replay), com **intervalo de 95 % por
   bloco de dia inteiramente acima de zero** (o teste que a momentum v6 não passou: [−0,094; +0,187]);
2. **≥ 100 desfechos prospectivos** da mesma versão (hoje: mean_reversion v1 tem 24, v2 tem 1, v3 tem 0);
3. **`risk_per_trade` sendo, de fato, o teto vencedor** em ≥ 50 % dos sinais — senão a mudança é
   inerte e não deve ser feita (§3).

Satisfeitas as três, o tamanho que eu proporia é **0,50 %**, nunca 1,00 %, e por um motivo estrutural:
a 1,00 % um único par de paradas seguidas leva ao bloqueio diário, e a carteira passaria mais tempo
travada esperando a sua autorização do que operando.

**Até lá, os dois investimentos que de fato mudam o sinal:** (i) o pedágio (T3.47, stop mais largo,
grátis em termos de limite); (ii) concentração nas versões positivas — `mean_reversion v1/v2/v3` são
as únicas com expectância líquida positiva, e são justamente as que menos sofrem com o teto de 3 %.

---

## 6. A mudança exata, se você decidir subir

Um commit, legível, sem efeito colateral escondido:

| # | O quê | Onde |
|---|---|---|
| 1 | `risk_per_trade_pct=Decimal("0.0025")` → `Decimal("0.005")` | `packages/risk-core/hunter_risk/limits.py:133` (objeto `PAPER_V1`) |
| 2 | teste que fixa o valor (é o que impede a mudança silenciosa) | `packages/risk-core/tests/unit/test_limits.py:22` |
| 3 | idem, na fronteira do banco | `packages/core/tests/integration/test_schema_paper.py:2305` e `test_schema_seed_and_partitions.py:224` |
| 4 | idem, na API | `apps/api/tests/integration/test_risk_limits_api.py:126` |
| 5 | linha da tabela do perfil + nota de versão | `docs/RISK_ENGINE.md` §2 e §9 (nova subseção "o que mudou e por quê") |
| 6 | registro da sua autorização (data, frase, escopo) | `.claude/state/directive-risk-engine-*.md` |

**Deploy.** O seed grava `risk_profiles.limits` a partir do próprio objeto do motor
(`infra/scripts/seed_paper.py:77`), então não há segundo lugar para editar. **Mas há uma ordem que
importa:** se a linha `paper_v1` já existir no banco com o valor antigo, o seed **aborta o deploy**
(`seed_paper.py:61-66`: *"o seed não vai sobrescrever"*) e a reconciliação tem de ser um `UPDATE`
auditado, com `audit_logs` e um `risk_events` do tipo `limits_changed` (§2 do contrato). Hoje, na
VPS, essa linha **ainda não existe** (§7) — decidir antes do próximo deploy que rodar o seed é mais
barato que decidir depois.

---

## 7. O que eu preciso declarar, porque muda o peso de tudo acima

1. **A carteira paper nunca executou nada.** `trade_proposals = 0`, `orders = 0`, `positions = 0`,
   `risk_events = 0`, `kill_switch_transitions = 0`, e **zero agentes** ligados a ela (`as_of` 19:25
   e 19:26 Brasília). Todo número deste documento é projeção do Lab (sinais), não resultado medido de
   carteira. É honesto como ordem de grandeza; não é extrato.
2. **A carteira está sem perfil de risco no banco.** `portfolios.risk_profile_id` é nulo e não existe
   linha `paper_v1` em `risk_profiles` (só `conservative`/`balanced`/`aggressive`). Não é falha de
   segurança — a API cai no `PAPER_V1` do código e marca a origem (`source: "engine_default"`,
   `apps/api/hunter_api/services/risk_limits.py:82-88`) —, mas significa que a tela de limites hoje
   mostra o código, não um perfil auditável no banco. O próprio módulo já declara o estado
   (*"No profile wired (every principal wallet today)"*); vale fechar antes de a carteira operar,
   porque é o perfil no banco que a auditoria e o histórico de `limits_changed` usam.
3. **A referência de volume é aproximada.** Usei a mediana das barras de 1 minuto das últimas 24 h
   por mercado; o motor usa `min(último minuto completo, mediana de 30 barras)` no instante da
   decisão. Ordem de grandeza correta, número exato do instante não.
4. **Coorte prospectiva curta.** Quase todas as versões têm **1 dia** de prospectivo (momentum v1 tem
   3). O replay de 31 dias é massa, não veredito — e três dias explicam quase todo o resultado de
   algumas séries (notas T3.40).
5. **Custo declarado, não medido:** 20 bps de ida e volta (`assumed_costs` de todas as linhas). Se o
   custo real for maior, todas as expectâncias líquidas pioram na mesma proporção.

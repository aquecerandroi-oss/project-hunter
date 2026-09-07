# Notas da T3.12 — serviço de admissão compartilhado

**Autor:** backend-specialist, 2026-09-07. **Para:** Sexta-feira, T3.1b, T3.5, T3.8, T3.9 e T3.14.
**Não editei** `docs/**`, `infra/**`, `packages/risk-core/**`, `services/**`, `apps/web/**`, `.env*`
nem `packages/core/hunter_core/{portfolio,risk,execution}/**` — só uso o que a T3.3 e a T3.6
entregaram.

Consultas à Astra: `.claude/state/astra-review-T3.12-admission.md` (desenho, antes de codar) e
`.claude/state/astra-review-T3.12-diff.md` (revisão do diff). O que mudou por causa dela está
marcado abaixo.

## 1. O que existe agora

`packages/core/hunter_core/admission/` — o **único** caminho que admite proposta:

| Módulo | Responsabilidade | Linhas |
|---|---|---|
| `sources.py` | origem explícita (`manual\|agent`), recusa de `research_only`, `ProposalRequest`, chave de idempotência | 169 |
| `dedupe.py` | replay pela chave `(source, client_key)`; conflito quando a chave nomeia outra ordem | 166 |
| `inputs.py` | `market_id` × `MarketIdentity` conferidos contra a referência; decisão quando a carteira não é mensurável | 135 |
| `participation.py` | orçamento de 60 s: álgebra pura + leitura/append do log | 169 |
| `reservation.py` | ciclo único da reserva (`held → consumed\|released\|expired`), `expire_reservations` | 330 |
| `record.py` | escrita da proposta (savepoint), sequência FIFO, reserva, auditoria e outbox | 319 |
| `service.py` | `admit(...)` — travas, estado, `evaluate`, e tudo acima numa transação | 320 |

`apps/api/hunter_api/services/admission.py` é adaptador fino: monta o `ProposalRequest` com a
identidade autenticada, chama `admit` e traduz recusa em problem+json (422/409). **Sem rota** — a
rota é a T3.8.

Ordem dentro de `admit`, e o porquê de cada posição:

1. origem e chave (antes de qualquer trava: pedido inadmissível não consome ponto de serialização
   nem lugar na fila);
2. replay rápido;
3. `verify_market` (a linha de `markets` e a identidade que o motor compara têm de ser o mesmo
   mercado);
4. `effective_state(..., lock=True)` — sistema → organização (`FOR SHARE`) → carteira (`FOR UPDATE`);
5. **`as_of = now + espera real pela trava`** (relógio monotônico, duração cheia — sem arredondar). Esperar atrás de
   outra admissão não pode rejuvenescer o livro: com livro de 9,8 s e espera de 0,4 s, arredondar
   para zero passaria um livro de 10,2 s pelo limite de 10 s (achado 2 da Astra no diff);
6. re-dedupe **sob a trava** (READ COMMITTED: a leitura depois da trava enxerga o commit do vencedor);
7. `expire_reservations` — reserva morta não segura vaga da entrada que está sendo decidida;
8. `build_portfolio_state` (mesma trava, T3.3);
9. soma da participação da janela de 60 s → `MarketLiquidity.participation_used_quote`;
10. `evaluate` puro **ou** `unmeasured_decision`;
11. `INSERT trade_proposals` dentro de savepoint (só a violação de `uq_trade_proposals_idem` é
    tratada) → sequência FIFO → reserva → `audit_logs` → outbox `proposals.decided`.

## 2. QUATRO ACOPLAMENTOS BLOQUEANTES — a admissão não roda no schema entregue

Nenhum deles é contornável por código meu; os quatro são de `infra/migrations/**` (T3.1b) ou de
decisão de dono sobre papéis.

| # | O que falta | Efeito hoje | Correção pedida |
|---|---|---|---|
| A | `hunter_worker` **não tem `UPDATE` em `organizations`** e `SELECT ... FOR SHARE` cobra `ACL_UPDATE` | `effective_state(lock=True)` morre com *permission denied for table organizations* — a admissão não chega a decidir | `GRANT UPDATE ("updated_at") ON organizations TO hunter_worker` — **a mesma forma de coluna que a T3.1b mediu** para `portfolio_risk_state` (`PAPER_LOCK_ONLY_TABLES`): permite marcar a linha, recusa escrever valor. É estritamente mais estreita que o `DELETE` que o papel já tem nessa tabela |
| B | `hunter_app` tem só `UPDATE (updated_at)` em `portfolio_risk_state` (+ trigger que recusa qualquer `UPDATE` do papel) | a admissão **não roda em `hunter_app`**: `fifo_v1` é um contador nessa linha (DATABASE.md §18.7). Provado por teste (`test_the_wallet_counter_is_refused_to_hunter_app`) | decisão de dono: (a) `GRANT UPDATE (last_admission_seq)` + exceção na trigger para o caso em que **só** essa coluna muda, ou (b) a rota manual da T3.8 delega a admissão a uma unidade de trabalho de papel `hunter_worker`. **(b) custa a segunda barreira de isolamento** (`hunter_worker` tem `BYPASSRLS`, DATABASE.md §1.2) e por isso não é equivalente |
| C | `hunter_app` não tem `INSERT` em `outbox_events` (achado da Astra) | mesmo resolvido o contador, a admissão pela API aborta no `enqueue` | idem: capacidade de enfileiramento autorizada para a API, com revisão de segurança — não publicar numa segunda transação, e não rodar a rota inteira como worker |
| D | **`portfolios` é gravável só por `hunter_app`** (`ddl/tables.py: APP_WRITE_TABLES`), e `portfolio_risk_state` só por `hunter_worker` | as duas metades da **mesma** avaliação de kill switch estão em papéis que não se combinam numa transação. Medido: `UPDATE portfolios SET kill_switch_state=...` como `hunter_worker` → *permission denied for table portfolios*. Consequência direta: `evaluate_and_persist` da T3.6 **não roda em nenhum dos dois papéis** no schema entregue, e a escalada automática do §3.1 ("o check é o detector") não pode ser gravada pelo caminho da admissão | decisão de dono sobre quem escreve `portfolios.kill_switch_state`: se é o motor, `hunter_worker` precisa de `UPDATE (kill_switch_state, kill_switch_reason)`; se é a API, a escalada automática precisa de outro portador. Não inventei nenhum dos dois |

**O que fiz enquanto isso, declarado e não escondido:** os testes de integração aplicam **só** o
grant (A), por `apply_pending_grants`, com o nome `ORG_ROW_LOCK_GRANT` e a justificativa no
docstring. A Astra aceita isso como *experimento condicionado* ("o serviço funciona sob estes
privilégios"), **não** como prova de integração com o schema entregue — e eu concordo. As duas
recusas do schema íntegro (B em `hunter_app`, A em `hunter_worker`) continuam provadas por teste.
**A T3.12 não deve ser considerada integrada até A, B, C e D serem decididos.**

## 3. Decisões tomadas (com a Astra) e o que elas fecham

| Assunto | Decisão | Motivo |
|---|---|---|
| Expiração | `reservation_state → expired`, `reserved_slot → false`, **`status` continua `approved`** | DATABASE.md §18.3 separa os dois eixos de propósito; `PIPELINE.md:216` diz `status=expired` e **precisa ser corrigido** — registro a divergência em vez de escolher em silêncio |
| Valores da reserva | preservados como histórico ao fechar o ciclo | o que conta contra limite é o **estado**, nunca as colunas irem a nulo |
| Liberação | `released` só do saldo **não executado**, e nunca em `consumed` | cancelar devolve só o que não foi executado (§4) |
| Sequência FIFO | atribuída a **toda** proposta decidida, aprovada ou recusada | é a ordem de chegada da solicitação; recusada fica com `reservation_state = none` e não compromete nada |
| Participação | `Σ executado(60 s) + Σ_por_reserva_held max(0, reservado − executado − liberado)` | a fórmula que a Astra percorreu; o executado de uma reserva viva entra **uma vez** (no primeiro termo) e abate o saldo do segundo. Saldo por reserva nunca negativo e nunca compensa outra (§18.5, "o que não é DDL") |
| Estado inconstruível | proposta **recusada e gravada**, todos os `ENTRY_CHECKS` `unavailable` com o motivo, **exceto** `kill_switch`, que sai `failed` quando as travas duráveis já bloqueiam | RISK_ENGINE.md §5: entradas bloqueadas, proteções preservadas — e o painel precisa ver por quê |
| Dedupe | compara carteira, mercado, direção, origem **e**, quando há `sizing`, `entry_ref`, `stop` e o teto pedido | fecha o cenário da Astra (chave reusada com teto menor recebendo a aprovação maior) |
| `reserved_cash` | `notional × (1+deslocamento)(1+fee)` da hipótese da **própria** proposta | espelho exato do teto de caixa do motor; reestimar com o custo do próximo candidato encolheria compromisso alheio |

## 3b. Escalada automática do kill switch — tentada, revertida, escalada

A Astra (achado 3 do diff) tem razão no contrato: reprovar por `daily_loss`/`drawdown` também tem
de **mover** a trava, na mesma transação, senão a carteira é recusada a 22 % de perda, o patrimônio
se recupera e a próxima admissão aprova como se nada tivesse disparado.

**Implementei e reverti**, com a medição: `evaluate_and_persist` grava
`portfolios.kill_switch_state`, e essa tabela é `hunter_app`; a admissão tem de rodar como
`hunter_worker` por causa do `fifo_v1`. O `UPDATE` falha com *permission denied for table
portfolios* e **aborta a transação inteira** — trocar uma recusa registrada por um 500 é pior do que
não travar. É o acoplamento D acima, e a decisão de quem escreve aquela coluna não é minha.

O que ficou: `packages/core/hunter_core/admission/service.py:_DETECTORS` documenta a lacuna com o
motivo medido, e `test_a_rejection_by_daily_loss_records_the_loss_without_latching` é a
caracterização do comportamento de hoje (recusa por `daily_loss` com o número medido; trava ainda
`ACTIVE`; zero transições). **Quando a titularidade da coluna for decidida, é esse teste que vira.**

## 4. Divergência registrada com a Astra (não implementada)

Ela pediu que, sem `PortfolioState`, os checks que **não** dependem da carteira (`modality`,
`data_quality`, `market_gap`, `market_in_universe`, `signal_validity`) fossem avaliados em vez de
sairem `unavailable`. **Não implementei**: reproduzi-los em `hunter_core.admission` seria uma segunda
implementação das regras do motor, exatamente o começo de duas respostas para a mesma pergunta. Na
segunda rodada ela **concordou com a objeção** e propôs o caminho certo: extrair esses checks
independentes **dentro de `hunter_risk`**, compartilhados pelo caminho completo e pelo parcial. Isso
é `packages/risk-core/**`, fora do meu escopo de arquivos — fica como pedido para o
`risk-engine-guardian`.

## 5. Pendências e limites honestos

0. **Achados da Astra no diff, e o que virou código:** dedupe por conteúdo (fechado com o `sizing`
   da decisão gravada), espera pela trava com duração inteira e relógio monotônico, `float` recusado
   na fronteira do `ProposalRequest`, `RiskStateMissing` traduzido para 409 no adaptador, e o teste
   da recusa do papel `hunter_worker` no schema íntegro. Ficaram em aberto, com o motivo: escalada
   automática do kill switch (§3b), checks parciais dentro de `hunter_risk` (§4) e o digest da
   solicitação (item 1 abaixo).
1. **Dedupe sem digest da solicitação.** Não existe coluna que guarde a identidade canônica do
   pedido. A comparação usa as quatro colunas + o `sizing` da decisão gravada, o que cobre o caso
   perigoso (aprovação). **Uma recusada replayada compara só as quatro colunas** — não compromete
   capital, mas é um buraco. Pedido à T3.1b/`database-architect`: coluna `request_digest TEXT` em
   `trade_proposals`, gravada na admissão e comparada no replay.
2. **`AdmissionResult.unavailable` sai vazio no replay** (os motivos não são coluna; estão nos
   checks da decisão persistida).
3. **`participation_consumptions` de tipo `executed` não é escrito aqui** — é da T3.5, que tem o
   `fill_id` que o índice único usa. A leitura já conta com ele.
4. **`close_reservation(..., CONSUMED)` existe e está testado, mas quem chama é a T3.5.** A
   conversão da vaga reservada na vaga da posição é o `consumed`; não crie um segundo caminho.
5. **O ramo do savepoint** (`insert_proposal` devolvendo `False`) está exercitado só indiretamente:
   com a trava da carteira, a segunda sessão normalmente encontra a linha no re-dedupe. Ele existe
   para a corrida em que o vencedor commita entre o re-dedupe e o `INSERT`.
6. **Reabrir o ciclo por `UPDATE` cru continua aceito pelo banco** — provado por teste de
   caracterização. A garantia é o caminho único de escrita (`next_state`), como o §18.3 manda; a
   trigger sugerida no achado 11 da revisão de segurança fecharia isso no schema.
7. **`hunter_core/portfolio/state.py` toma `FOR UPDATE` de novo** dentro de `build_portfolio_state`
   (a trava já é minha nesse ponto) — é no-op, mas são duas idas ao banco pela mesma linha.

## 6. Assinaturas para quem vem depois

```python
await admit(
    session, request,                 # ProposalRequest (hunter_core.admission.sources)
    source="manual" | "agent",
    liquidity=MarketLiquidity,        # sem participation_used_quote: a admissão preenche
    spec=MarketSpec,                  # filtros do mercado (não estava no brief; é insumo do evaluate)
    beta=BetaEstimate,                # do mercado candidato
    prices={market_id: Decimal},      # fonte de preço declarada pelo chamador (T3.3)
    betas={market_id: Decimal},       # revisão de β declarada pelo chamador
    exit_cost_rate=Decimal,
    now=datetime,                     # UTC; a espera pela trava é somada a ele
    limits=PAPER_V1, system=None,
) -> AdmissionResult

await expire_reservations(session, organization_id=..., portfolio_id=..., now=...)  # sob a trava
await close_reservation(session, organization_id=..., proposal_id=..., target=..., now=..., reason="")
```

Desvios do brief, declarados: `spec` e `betas` são parâmetros a mais (o `evaluate` exige o primeiro,
e sem o segundo o agregado de β fica desconhecido e **nenhuma entrada é aprovada**);
`expire_reservations` recebe organização e carteira (uma varredura precisa de tenant e de uma
carteira para travar, na ordem declarada).

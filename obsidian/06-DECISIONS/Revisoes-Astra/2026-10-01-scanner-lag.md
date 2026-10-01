---
tags: [astra, revisao, scanner, radar, redis-streams, persistencia]
status: fechada
owner: backend-specialist
updated: 2026-10-01
decided_on: 2026-10-01
by: Astra + backend-specialist
---

# Revisão da Astra — o `scanner-worker` 2 h atrás e 14 h sem gravar (01/10/2026)

Pedido: diagnosticar o lag do grupo `scanner-worker` em `market.candles.closed`, propor o conserto e a mitigação. Diagnóstico completo, comandos e saídas: [[Scanner-lag-2026-10-01]]. Bruto (a fonte, não o registro): `.claude/state/astra-review-scanner-lag.md`. O `astra.sh` imprimiu "AVISO: a Astra alterou a árvore" — foram os arquivos novos de outros agentes e o meu teste, nenhum dela (ela declarou "nenhum arquivo criado ou modificado").

**Aceitos (must-fix):**
- **Mecanismo A (memória avança antes do commit; falha descarta o lote; a abertura seguinte traz id novo contra a linha ainda ativa) confirmado no código** (`collect.py:85`, `watchdog.py:115`, `runners.py:121`, `writers.py` só trata `id`). Ela acrescentou um gatilho que eu não tinha: `_drop_invalidated` (`persist.py:133`) remove as linhas de anomalia depois de a memória avançar.
- **Mecanismo B confirmado, com correção na descrição:** o reclaim termina em cursor `0-0` **ou página vazia**; "~1.700 páginas por volta" é cenário possível, não contagem. O que sustenta a espiral são os ~88× medidos; a fração exata dos 98 % de CPU exige perfil (não há `py-spy` no contêiner e não instalei). Texto da nota corrigido.
- **O `superseded` irrestrito que eu propus tinha dois furos concretos** — (a) um lote atrasado de X pode expirar um Y mais novo; (b) com X fechado e Y ativo no mesmo lote, excluir os ids do lote deixa o resultado dependente da ordem das escritas. **Implementei as duas guardas**: só se fecha linha **mais antiga** (`detected_at <` a da nova) e o lote é ordenado fechamentos-antes-de-aberturas; os dois casos viraram teste (o de ordem **falha sem o `sorted`**, verificado).
- **`max(detected_at)` parado não prova ausência de UPDATE** (o upsert preserva essa coluna): a frase "não persiste nada" foi sustentada com outros números (`feature_snapshots` por hora, `opportunity_history`, última anomalia, e as falhas de 100 % dos ciclos), e a nota diz "parou de persistir" com a ressalva de que as expirações de 14:50:26Z existem.

**Aceitos (nice-to-have):** atualizar `metadata.state` e não só as colunas (feito); manter as referências históricas a X e deixar as oportunidades novas apontarem para Y (já é assim em `collect.py:136`); sem sharding agora; limitar o reclaim a uma página por volta intercalando leituras novas (proposta 2 da nota); pedir, antes de reiniciar, X ativo e Y rejeitado de 2–3 conflitos (feito para 4 pares: o X ativo está no banco com `detected_at` ≤ 13:36Z; o Y rejeitado não é lido do banco porque nunca entrou) e duas amostras de `XPENDING` (feitas: 03:40 e 04:06).

**Divergências (escritas):**
- **Ela prefere "retenção do lote + serialização" como conserto principal e reconciliação só como complemento; eu implementei só a reconciliação** (um arquivo de produção) porque o brief limitava a uma mudança pequena e clara, e `runners.py` tem 344 linhas (a retenção exige extrair o laço de flush). A retenção/serialização ficou como proposta 1, com o teste que deve falhar primeiro. Ela também rejeita "sacrificar correção para caber no teto de arquivos": concordo — por isso a reconciliação **não é declarada a cura**, só o fim do veto permanente.
- **O reinício não é "cura garantida"** (concordo e escrevi): uma fechada com observação mais recente pode vencer na reidratação (`repo.py:177`), os caminhos de divergência continuam e o boot de 14:49Z "não prova sozinho cura seguida de recaída".

**Concordâncias absorvidas:** anomalias e oportunidades são globais (sem RLS no caminho); eventos reenviados com os mesmos ids são deduplicados (`outbox_store.py:138`), regenerar ids não; a reentrega não reconstrói snapshots (o handler só marca o mercado como sujo e a avaliação lê o estado quente) — aceite operacional é "commits avançando, PEL diminuindo, nenhum conflito novo".

**Segunda rodada (diff final, `.claude/state/astra-review-scanner-lag-diff.md`):** `APPROVE_WITH_NITS`, nenhum must-fix; ela concorda com o `unnest`/cast, a guarda temporal (não produz `resolved_at < detected_at`), o `rowcount` do asyncpg e o fechamento sem evento novo. Aceitos os dois nits (testes do retorno 1/0 + `metadata.state`, e do lote com dois ativos no mesmo par, que continua falhando alto) e a pergunta do plano (respondida com `EXPLAIN` sem `ANALYZE` na VPS: sonda pelo índice parcial; custo real sob carga continua não medido). Pendência dela que fica: documentar "expirada por `superseded`" em [[Anomalies]].

## Relacionado
[[Scanner-lag-2026-10-01]] · [[Late-delay-do-Lab-diagnostico-2026-10-01]] · [[2026-10-01-late-delay-do-lab]] · [[Performance Overview]]

## Fontes
`.claude/state/astra-review-scanner-lag.md` · `docs/DATABASE.md` §anomalies (índice `uq_anomalies_active_per_market_type`)

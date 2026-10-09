---
tags: [revisao-astra, ops, deploy]
date: 2026-10-09
status: registro
owner: sexta-feira
---

# compose.sh: `migrate` com saída 0 deixa de virar "ERRO" no deploy

**Problema:** no deploy de 09/10 (imagem `b67306a5`, tudo saudável), o `check_up_status` imprimiu `ERRO: ... migrate`. O `migrate` é um job de uma vez só: roda e sai com código 0. O alarme falso ensinaria a ignorar o erro real.

**Conserto:**
- Um serviço `exited` só conta como falha se o código de saída não for 0. Os estados `created` e `dead` continuam contando.
- Se o `docker inspect` falhar, a checagem volta a contar todo `exited` como falha (falha fechada).
- Verificação: stub com 6 casos e `docker inspect` real em dois contêineres locais. O primeiro teste real é o próximo deploy na VPS.

**Astra:**
- **Aceito:** o fallback fechado quando o `inspect` falha.
- **Rejeitado:** a lista fixa de jobs de uma vez só. Na VPS, todo serviço longo tem `restart: always`, então só um job de uma vez só pode ficar parado com saída 0. Uma lista fixa precisaria ser mantida em dobro.

Bruto: `.claude/state/astra-review-compose-migrate-exit0.md` · [[Deployment]] · [[Revisoes-Astra/Index|índice das revisões]]

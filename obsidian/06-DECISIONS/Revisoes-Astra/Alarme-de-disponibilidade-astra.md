---
tags: [revisao-astra, operacoes, alarme, vps, github-actions]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: sexta-feira
decided_on: 2026-10-05
by: astra
tarefa: desenho do alarme externo de disponibilidade da VPS (uptime.yml + uptime_check.sh)
veredito: aprova como alarme básico de disponibilidade, com duas correções (identidade da issue, destinatário do e-mail); não comprova frescor
---

# Revisão da Astra — alarme externo de disponibilidade

Fonte citada (não substitui esta nota): `.claude/state/astra-review-uptime-alarm.md`. Registro completo da nota operacional: [[Alarme-de-disponibilidade]].

## O que ela apontou e o que foi feito

| Achado | Decisão |
|---|---|
| **Must-fix 1.** A issue era achada só pelo título entre 100 abertas: issue homônima aberta por terceiro (repo público) seria editada/fechada; o limite corta antes do filtro. | **Aceito.** Label exclusiva `uptime-alarm` (só quem tem triagem aplica) no `gh issue list` e no `gh issue create`; título continua no filtro. Não adotei filtro de autor do bot (não consegui testar o formato do login sem o `gh` aqui). |
| **Must-fix 2.** "Job vermelho manda e-mail ao Everton" não é garantido: recebe quem editou o `cron` por último / reabilitou. | **Aceito como requisito documentado** em `docs/DEPLOYMENT.md`, com prova de entrega (variável `UPTIME_BASE_URL` apontando para um endereço morto, esperar uma execução agendada, apagar a variável). Não dá para provar daqui. |
| `-k` não protege a autenticidade do resultado; confiar na CA interna com `--cacert`. | **Parcialmente aceito:** não bloqueia o primeiro alarme; a variável `UPTIME_CURL_TLS_ARGS` foi ligada para trocar o padrão, e o endurecimento ficou escrito. Não obtive a raiz (exigiria SSH). Corpo agora confere `environment` **e** `git_sha`. |
| Cron fora do início da hora; `!cancelled()` nos `if`; estimativa de ~3,5 min (não 2). | **Aceitos** (`3-59/10`, `!cancelled()`, textos corrigidos). Ela também não achou problema em `concurrency`, `continue-on-error` + `outcome` e sparse-checkout não-cone. |
| Um monitor parado não avisa da própria parada; 60 dias sem atividade. | **Registrado como limite**, sem mecanismo novo (nada de serviço novo). |
| Contrato do endpoint de frescor. | **Registrado** em [[Alarme-de-disponibilidade]] e no DEPLOYMENT; implementação fica para tarefa de API. |
| Correção da premissa: o código local do scanner já tem `scanner_persistence`/`last_commit_at`; as 14 h de verde são histórico. | **Verificado:** está em `services/scanner-worker/hunter_scanner_worker/health.py`, que na árvore de trabalho aparece modificado (não commitado por esta tarefa); o deploy da VPS (`9622f087`) **não verifiquei**. |

Discordância: nenhuma além de não ter adotado o filtro de autor.

## Relacionadas

[[Alarme-de-disponibilidade]] · [[Open Bugs]] · [[2026-10-05]] · [[Scanner-lag-2026-10-01]] · [[Revisoes-Astra/Index|índice das revisões]]

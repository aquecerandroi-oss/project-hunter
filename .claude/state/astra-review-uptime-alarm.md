**RESUMO**

**Aprovo o desenho como alarme básico de disponibilidade, com duas correções antes de depender dele:** identificar a issue com segurança e validar/documentar o destinatário das notificações. Ele não comprova frescor nem funcionamento completo do produto.

Revisão como `devops-engineer`, considerando [Infrastructure](C:/dev/project-hunter/obsidian/01-ARCHITECTURE/Infrastructure.md), [Deployment](C:/dev/project-hunter/obsidian/09-OPERATIONS/Deployment.md) e o [diagnóstico histórico do scanner](C:/dev/project-hunter/obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Os dois arquivos revisados aparecem como novos, não rastreados.

**TESTES**

- `bash -n infra/scripts/uptime_check.sh` → saída vazia, código **0**.
- `actionlint` não encontrado no PATH.
- Não executei a sonda, o workflow, chamadas à VPS nem operações em issues. A validação funcional permanece pendente.

**MUST-FIX**

1. **A issue precisa de identidade própria e busca sem truncamento silencioso.**  
   Hoje são buscadas apenas 100 issues abertas, filtradas exclusivamente pelo título ([uptime.yml:72](C:/dev/project-hunter/.github/workflows/uptime.yml:72)).

   **Cenários concretos:**
   - A issue do incidente fica fora das 100 retornadas: outra é criada; na recuperação, a antiga pode continuar aberta.
   - Num repositório público, alguém abre uma issue chamada “VPS fora do ar”: o workflow pode sobrescrever seu conteúdo ou fechá-la ([uptime.yml:89](C:/dev/project-hunter/.github/workflows/uptime.yml:89), [uptime.yml:93](C:/dev/project-hunter/.github/workflows/uptime.yml:93)).

   **Correção:** label exclusiva aplicada pelo monitor, conferir autoria do bot e paginar os resultados filtrados. Um número de issue explicitamente configurado também resolve a identidade. Aumentar `--limit` apenas adia o primeiro problema; o limite é aplicado à busca, antes do filtro local. [Manual do GitHub CLI](https://cli.github.com/manual/gh_issue_list).

2. **“Job vermelho gera e-mail para Everton” precisa virar um requisito operacional verificado.**  
   O comentário atual associa falha a e-mail, mas o workflow não configura destinatário ([uptime.yml:6](C:/dev/project-hunter/.github/workflows/uptime.yml:6)).

   **Cenário concreto:** outra conta altera o cron ou reativa o workflow; Everton deixa de receber, embora as execuções continuem vermelhas. Também pode não haver e-mail se o destinatário não habilitou notificações de Actions.

   A regra documentada é: inicialmente recebe quem criou o workflow; se outra pessoa altera o `schedule`, passa a receber essa pessoa; se alguém desabilita e reabilita, recebe quem reabilitou. **Não são automaticamente todos os administradores ou watchers.** [Notificações de workflows](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs).

   Antes de considerar o alarme operacional, registrar o responsável e comprovar recebimento numa execução **agendada** vermelha controlada. A issue exige sua própria inscrição/notificação.

**NICE-TO-HAVE**

**1. TLS: aceito `-k` provisoriamente, mas a justificativa está incompleta.**

Não enviar credenciais reduz o risco de vazamento; **não protege a autenticidade do resultado**. Um atacante no caminho pode apresentar qualquer certificado e devolver `200` com `"git_sha"`, escondendo uma indisponibilidade. A checagem atual só procura essa substring ([uptime_check.sh:39](C:/dev/project-hunter/infra/scripts/uptime_check.sh:39), [uptime_check.sh:56](C:/dev/project-hunter/infra/scripts/uptime_check.sh:56)). Também não detecta certificado expirado ou identidade incorreta. [Documentação do curl](https://curl.se/docs/sslcerts.html).

**Eu confiaria explicitamente na CA interna se o uso do IP for continuar.** Versionar somente o certificado público da raiz, obtido por canal confiável, e usar `--cacert`, retirando `-k`. Isso acompanha a renovação dos certificados folha; exige manutenção quando a raiz for substituída. Nunca publicar a chave privada. O Caddy documenta essa cadeia interna. [HTTPS local do Caddy](https://caddyserver.com/docs/automatic-https#local-https).

Não bloquearia o primeiro alarme por isso. Mas trocar apenas `UPTIME_BASE_URL` por um domínio **mantém `-k`**, pois o script o usa por padrão e o workflow não define `CURL_TLS_ARGS` ([uptime.yml:37](C:/dev/project-hunter/.github/workflows/uptime.yml:37), [uptime_check.sh:33](C:/dev/project-hunter/infra/scripts/uptime_check.sh:33)).

**2. Notificações e silêncio operacional.**

Concordo com cada sonda vermelha deixar o job vermelho. Isso mantém a verdade operacional; seis execuções por hora representam a cadência nominal, não garantia de seis e-mails entregues. Editar o corpo evita comentários repetidos; comentar e fechar na recuperação é adequado ([uptime.yml:76](C:/dev/project-hunter/.github/workflows/uptime.yml:76)).

Os limites devem ficar explícitos:

| Condição | Consequência |
|---|---|
| 60 dias sem atividade no repositório público | O GitHub desativa os workflows agendados. |
| Sem commits novos, mas cron ainda ativo | Continua usando o último commit da branch padrão; não exige commit por execução. |
| Sobrecarga do scheduler | Pode atrasar ou descartar execuções. Não há limite garantido de dez minutos. |
| Issues desabilitadas/permissão negada | O passo `gh` falha; o job fica vermelho mesmo com a VPS saudável. Perde-se o registro/recuperação por issue. |
| `UPTIME_PAUSED=true` ou workflow desabilitado | O monitor deixa de sondar; a pausa atual não expira automaticamente. |

As regras de agendamento são do [GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule); pausa e operações em issues estão em [uptime.yml:29](C:/dev/project-hunter/.github/workflows/uptime.yml:29) e [uptime.yml:72](C:/dev/project-hunter/.github/workflows/uptime.yml:72).

Eu deslocaria o cron para `3-59/10 * * * *`, evitando o início da hora, e recomendaria um segundo mecanismo independente para detectar ausência de execuções. **Um monitor parado não consegue anunciar a própria parada.** Não confiaria em suas próprias runs para impedir a desativação por inatividade.

**3. Corridas e falhas do workflow.**

- **Concurrency:** grupo constante e `cancel-in-progress: false` são adequados para serializar a gestão da issue ([uptime.yml:22](C:/dev/project-hunter/.github/workflows/uptime.yml:22)).
- **`continue-on-error` + `outcome`: correto.** Preserva o resultado original da sonda e permite tratar a issue antes de falhar ([uptime.yml:48](C:/dev/project-hunter/.github/workflows/uptime.yml:48)).
- **Checkout falhar sem abrir issue: correto.** A sonda fica pulada; isso não prova queda da VPS ([uptime.yml:39](C:/dev/project-hunter/.github/workflows/uptime.yml:39)).
- **Ressalva dos `if`:** ainda existe `success()` implícito. Se “Resumo” falhar, o passo da issue é pulado; se a issue falhar, o último passo também é pulado. O job **continua vermelho**, portanto não há falso verde, mas perde-se o tratamento posterior. Usaria `!cancelled()` junto ao teste de `outcome`, com fallback para relatório ausente ([uptime.yml:55](C:/dev/project-hunter/.github/workflows/uptime.yml:55)). [Semântica oficial](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions).
- **Sparse-checkout não-cone:** adequado para selecionar um arquivo; o exemplo oficial usa esse modo. [Configuração local](C:/dev/project-hunter/.github/workflows/uptime.yml:42), [actions/checkout](https://github.com/actions/checkout).
- **`jq` e `gh`:** constam na imagem Ubuntu hospedada; não precisam de instalação adicional nesse desenho. [Inventário oficial](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md).

**4. Precisão da sonda.**

Validaria JSON com `jq -e`, em vez de substring. Também corrigiria a estimativa: seis requests sequenciais de até 20 s, mais 30 + 60 s de espera, dão **até aproximadamente 210 s**, não dois minutos ([uptime_check.sh:39](C:/dev/project-hunter/infra/scripts/uptime_check.sh:39), [uptime_check.sh:75](C:/dev/project-hunter/infra/scripts/uptime_check.sh:75)). O comentário de recuperação também promete um limite de agendamento que o GitHub não garante ([uptime.yml:95](C:/dev/project-hunter/.github/workflows/uptime.yml:95)).

**O QUE EU FARIA DIFERENTE**

Proporia `GET /api/v1/system/freshness`, mantendo o contrato pequeno:

| Campo | Significado |
|---|---|
| `status` | `ok`, `degraded` ou `unknown`. |
| `observed_at` | Momento UTC da observação das fontes. |
| `market.final_candle_at` | Fechamento do último candle final persistido, agregado sobre o universo esperado. |
| `scanner.last_commit_at` | Última persistência bem-sucedida observada. |
| `scanner.oldest_uncommitted_at` | Trabalho avaliado ainda sem persistência; `null` quando não há pendência. |
| `reason_codes` | Motivos limitados: `stale_market`, `scanner_stalled`, `missing_worker`, `dependency_unavailable`. |

Sem símbolos, tenants, posições, saldos, hosts ou exceções internas. `200` somente quando os requisitos forem satisfeitos; `503` para degradação/estado desconhecido. `Cache-Control: no-store`, timeout curto e consultas limitadas.

**Cuidados essenciais:** não usar `MAX` global que deixe um mercado saudável esconder os demais; exigir presença dos shards esperados; não renovar o carimbo da evidência só porque o endpoint foi consultado. Um scanner ocioso não é necessariamente travado.

Há uma correção importante à premissa:

- **`/ready` da API** verifica apenas conectividade com Postgres/Redis; não vê commits do scanner, dados atrasados ou backlog ([health.py:63](C:/dev/project-hunter/apps/api/hunter_api/health.py:63)). Os helpers fazem `SELECT 1` e `PING` ([session.py:306](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:306), [redis.py:118](C:/dev/project-hunter/packages/core/hunter_core/redis.py:118)).
- **O scanner atual já tem `scanner_persistence`**, que reprova pendência acima de 120 s ([health.py:81](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:81), [health.py:211](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:211)), e publica `last_commit_at`/`uncommitted_s` ([health.py:308](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:308)). Portanto, as 14 horas com verde são evidência histórica, não descrição integral do código atual. **Não verifiquei seu deploy na VPS.**

**CONCORDO COM**

- Sondar a borda real: Caddy encaminha `/api/*` e `/ws` para a API; o restante vai ao web ([Caddyfile:38](C:/dev/project-hunter/infra/vps/Caddyfile:38)).
- Usar `/system/info` como sinal limitado de resposta da API, reconhecendo que não consulta dependências ([health.py:75](C:/dev/project-hunter/apps/api/hunter_api/health.py:75)).
- Não inventar frescor, não depender de Clerk para esse alarme e manter um incidente aberto por vez.
- Três tentativas com timeout antes de declarar indisponibilidade ([uptime_check.sh:30](C:/dev/project-hunter/infra/scripts/uptime_check.sh:30)).

**OBSIDIAN**

- **Infrastructure** — registrar o monitor externo, seu escopo e a política de confiança TLS.
- **Deployment** — documentar destinatário, prova de entrega, pausa/reativação, inatividade de 60 dias e ausência de garantia do cron.
- **Workers** — atualizar a prontidão do scanner com `scanner_persistence` e os campos já existentes.
- **Revisoes-Astra/Alarme externo de disponibilidade** — registrar este parecer e o contrato proposto de frescor, distinguindo código local de deploy verificado.
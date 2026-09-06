**PRESERVADO.**

- **Mesmo ID, mesma ordem:** falha `500` → retry `"duplicate"` → envelhecimento da claim → retry `"applied"`, sempre com `delivery_id` ([test_webhook.py:640](C:/dev/project-hunter/apps/api/tests/integration/test_webhook.py:640), linhas 643–656).
- **Coluna correta:** `_age_claim` atualiza `processed_events.claimed_at`, filtrando pelo delivery; o takeover compara `ProcessedEvent.claimed_at` ao limite temporal e exige `completed_at IS NULL` ([test_webhook.py:471](C:/dev/project-hunter/apps/api/tests/integration/test_webhook.py:471), [webhook_delivery.py:150](C:/dev/project-hunter/apps/api/hunter_api/services/webhook_delivery.py:150)).
- **Cleanup continua desativado:** `release_delivery` permanece no-op; apenas `_upsert_user` é restaurado. No retry imediato, `_upsert_user` ainda explode: takeover prematuro continua fazendo o teste falhar ([test_webhook.py:630](C:/dev/project-hunter/apps/api/tests/integration/test_webhook.py:630), linhas 636–652).
- **Não virou duplicado:** o irmão cria a claim diretamente; este provoca falha pelo POST com cleanup inoperante, cobrindo como a claim fica abandonada pelo fluxo de erro ([test_webhook.py:498](C:/dev/project-hunter/apps/api/tests/integration/test_webhook.py:498), [test_webhook.py:636](C:/dev/project-hunter/apps/api/tests/integration/test_webhook.py:636)).

Conclusão por inspeção; testes não executados. A configuração do fixture foi tomada do contexto fornecido, fora dos arquivos autorizados.

**OBSIDIAN**

- Revisões-Astra — registrar que o envelhecimento determinístico preserva retenção e recuperação após falha sem cleanup.
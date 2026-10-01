---
tags: [astra, revisao, shadow-lab, latencia, late-delay]
status: fechada
owner: backend-specialist
updated: 2026-10-01
decided_on: 2026-10-01
by: Astra + backend-specialist
---

# Revisão da Astra — diagnóstico do `late:delay` do Shadow Lab (01/10/2026)

Pedido: diagnosticar os 2.028 `no_entry` (1.927 `late:delay`) da auditoria de dados da própria Astra. Diagnóstico completo, SQL e saídas: [[Late-delay-do-Lab-diagnostico-2026-10-01]]. Bruto: `.claude/state/astra-review-lab-late-delay.md`. Nota: o `astra.sh` imprimiu "AVISO: a Astra alterou a árvore" — a diferença é de outros agentes editando em paralelo (`meme-executor`, `docs/DATABASE.md`); a única linha nova dela é o próprio arquivo de revisão.

**Aceitos (três must-fix):**
- **População da distribuição diária mal rotulada.** Eu tinha escrito "perp prospectivo" com 1.637 em 09/09, mas 18 + 10 + 105 + 1.637 + 157 = 1.927 já inclui os 184 spot; o perpétuo é 1.453 (44,2 % de 3.287, não 47,2 %). Corrigido na nota e **os percentuais por versão foram recalculados só com perpétuo** (ex.: `momentum v3` 12,5 %, não 13,2 %).
- **`delay_s` como covariável não conserta o viés.** A válvula e o portão de 300 s devolvem antes de existir linha; não há o que ajustar nas barras perdidas. Janela principal passa a ser a dela, `06/09 00:00Z ≤ source_bar_close < 11/09 00:00Z` (dias completos), com 08/09 12Z–10/09 21Z (a minha) só como sensibilidade; 11/09 sem certificado de cobertura (Redis instável na madrugada, Diário de 11/09).
- **A frase da janela de 30/09 foi restringida:** "sem pico ≥ 60 s nos 56 sinais persistidos", não "todas as barras avaliadas pelo `SHARDS=1`" — o consumidor lê antes de concluir, há recusas com ACK sem avaliação e os shards antigos também gravavam.

**Aceitos (nice-to-have e precisões):** medir o `outcome_sweep` antes de mexer (duração da passagem, trackings visitados, atraso do event loop; a cadência é *duração + 10 s*); `queue_wait` é observado antes do `dispatcher.submit` e não cobre a espera interna; os 4 `late:missed_open` mostram decisão perto da fronteira, não necessariamente *commit* naquele instante; persistência do registro de barras recusadas em **Postgres** (Redis não é durável sem política verificada), separando recusa por barra de indisponibilidade por barra × versão com motivo, com idempotência na reentrega.

**Concordâncias absorvidas:** o limiar está certo (`delay_s > 120 ⇔ L ≥ 120 s` para fechamento em minuto cheio, sem bug); "incidente histórico mitigado, com picos residuais e cobertura incompletamente observada" é a redação adotada; o histograma por barra (`hunter_shadow_bar_lag_seconds`) fica aprovado como primeiro passo.

**Divergências:** nenhuma.

## Relacionado

[[Late-delay-do-Lab-diagnostico-2026-10-01]] · [[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]] · [[KB-0089-o-teto-de-cpu-de-um-processo-so]] · [[07-BUGS/Open Bugs|Open Bugs]]

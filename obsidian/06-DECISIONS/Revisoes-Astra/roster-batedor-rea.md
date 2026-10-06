---
tags: [revisao-astra, roster, rea, fontes, pumpfun]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: sexta-feira
decided_on: 2026-10-06
by: astra
tarefa: criar o agente batedor-rea (REA na turma de estratégia)
veredito: apoia (sonnet) com 5 must-fix; 4 absorvidos no cartão, 1 parcial
---

# Batedor REA — opinião da Astra antes de criar o papel

**Pergunta:** criar um agente que usa o [[REA]] para pegar no site o que as hipóteses precisam.

**Must-fix e o que a Sexta-feira fez:**

1. **Permissão por fonte.** Os termos da pump.fun proíbem bots (§21(h), salvo o que o §6.1 permitir) e engenharia reversa (§21(j)). Conferido no texto oficial e levado ao Everton, que decidiu continuar ([[2026-10-06-rea-na-pumpfun-apesar-dos-termos]]). O cartão exige ler os termos de qualquer outro site antes de capturar.
2. **Restrições efetivas.** Bash removido do cartão; ficou só `Write`, sem `Edit`. O navegador é sempre o perfil temporário do REA, nunca as abas da pessoa (sem `list_browser_targets`). O conteúdo das páginas é tratado como dado, não como instrução.
   - **Parcial:** a restrição de escrita às duas pastas é regra do cartão, não um hook técnico. Fica como pendência.
3. **Procedência e tempo.** Toda rota ou campo leva a etiqueta observada / no bundle / verificada / inferência, e o `known_at` é obrigatório. Sem ele, o dado só serve para observar daqui para a frente.
4. **Orçamento.** 3 páginas, 15 s por página e 60 chamadas do site por pedido, parando no primeiro 401/403/429 ou desafio. A primeira captura (home + ranking) gerou 744 requisições, a maior parte imagens e scripts; o orçamento conta só as chamadas de API e de dados.
5. **Privacidade.** Endereços truncados, nenhum nome de usuário, bio ou imagem.

**Revisores:** a Sexta-feira em toda nota; o quant-engineer antes de virar evidência; o security-reviewer nas permissões. Se a fonte virar dado de produto, o exchange-integration-specialist implementa e o code-reviewer revisa.

**Tier:** sonnet, como ela recomendou.

Fonte: `.claude/state/astra-review-roster-batedor-rea.md`.

[[Batedor REA]] · [[Agents Overview]]

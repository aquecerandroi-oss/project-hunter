**RESUMO**

Apoio o `batedor-rea`, **Sonnet**, com ajustes antes de liberá-lo. Assumo o enquadramento de exploração do `explorer-agent`: descobrir fontes e documentar limites, sem decidir estratégia.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão documental, com consulta aos termos oficiais da pump.fun. Não executei REA.

**MUST-FIX**

- **Permissão por fonte.** Acesso anônimo não basta: os termos da pump.fun condicionam automação à permissão expressa (§6.1) e restringem engenharia reversa (§21.j). Cenário: analisar bundles sem copiar código ainda pode contrariar os termos. Exigiria verificar o uso permitido antes da captura; `analyze_web_bundle` não seria autorização geral. [Termos oficiais](https://pump.fun/docs/terms-and-conditions).
- **Restrições efetivas.** Retiraria `Bash` genérico; escrita limitada por controle técnico às duas pastas propostas, inclusive saídas MCP. Navegador isolado, sem acessar abas pessoais via `list_browser_targets`. Conteúdo externo é evidência, nunca instrução. Cenário: uma página maliciosa induzir execução de comandos ou leitura de arquivos.
- **Procedência e tempo.** Nota com hipótese/EXP, URL, UTC, método, evidência, limitações e distinção entre **rota observada / campo no bundle / resposta verificada / inferência**. Sem corpo, REA não comprova valores ([KB-0185:92](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas.md:92)). Cenário: selecionar vencedores de hoje para simular ontem. Exigir `known_at` anterior ao corte de seleção; sem isso, uso apenas prospectivo.
- **Orçamento além de páginas.** Definir N, requisições, duração de WebSockets, bytes e tokens; parar em bloqueio/429. A captura registrada de home + leaderboard gerou **744 requisições** ([KB-0185:57](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas.md:57)). Cenário: três páginas consumirem centenas de chamadas.
- **Privacidade.** Coletar apenas identificadores necessários, sem associar carteira a pessoa, guardar usernames ou perfis completos; sanitizar capturas e definir retenção. Cenário: publicar no Obsidian um vínculo identificável e desnecessário.

**NICE-TO-HAVE**

Template único de fonte, com estados “descoberta”, “verificada” e “aprovada”, incluindo lacunas e condições de reprodução.

**O QUE EU FARIA DIFERENTE**

Revisão obrigatória: **orquestrador em toda nota; `quant-engineer` antes de usar como evidência experimental; `security-reviewer` na configuração de permissões**. Para integração, manter `exchange-integration-specialist` + `code-reviewer`/`security-reviewer`.

Sonnet é adequado para interpretar navegação e procedência; reservar Opus para julgamento quant/security. POST de leitura somente em rota explicitamente autorizada e comprovadamente sem mutação; método HTTP sozinho não garante segurança.

**CONCORDO COM**

Escopo por hipótese, descrição funcional própria, nunca copiar código/design, nunca login, contornar proteções, acessar `.env`, alterar produto, operar dinheiro ou decidir estratégia.

**OBSIDIAN**

- **REA** — registrar escopo, permissões, orçamento e revisores.
- **Fontes REA — índice/template proposto** — padronizar procedência, temporalidade, privacidade e aprovação.
- **Revisões-Astra — batedor-rea** — preservar este parecer e a decisão do orquestrador.
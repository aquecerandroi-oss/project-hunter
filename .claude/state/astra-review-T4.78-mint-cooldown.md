**RESUMO**

`DONE_WITH_CONCERNS`: dois achados com cenário concreto. Corrigiria ambos antes de integrar.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisei o diff e os três arquivos novos. `.env.example` excluído da leitura pela proibição explícita de ler `.env*`.

**TESTES**

`git diff` e `git status --short` executados. Testes automatizados não executados; conclusões por inspeção estática, sem alegação de aprovação das suítes.

**MUST-FIX**

- [refusal_cooldown.py:150](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/refusal_cooldown.py:150) — **MÉDIA** — O robô ignora `:segundos_restantes` e reinicia uma pausa fixa desde a recusa. **Cenário:** perda em `t=0`, recusa em `t=290` com `mint_cooldown_after_loss:10`, cooldown do robô de 120 s. O motor libera em `t=300`, mas o robô continua pulando o mint até depois de `t=410`. Isso prolonga a regra e deixa oportunidades bloqueadas sem registro desse motivo na admissão. Usar o restante informado, limitado pelo cooldown do robô.

- [repo_positions.py:105](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/repo_positions.py:105) — **ALTA, condicionada à saturação da janela** — O limite global de 50 mints pode omitir justamente o candidato e liberar uma recompra proibida. **Cenário:** 51 mints distintos fecharam com perda dentro da janela; o candidato é o menos recente deles. A consulta o elimina, e [checks_wallet.py:156](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/checks_wallet.py:156) interpreta sua ausência como aprovação. Não afirmo que esse volume ocorreu em produção. Consultar o mint candidato mantém uma query, retorna no máximo uma linha e elimina a falha.

**NICE-TO-HAVE**

Nenhum achado adicional com cenário suficiente.

**O QUE EU FARIA DIFERENTE**

Aplicaria as duas correções acima, com regressões para `:10` próximo da expiração e para o candidato fora dos 50 mais recentes.

**CONCORDO COM**

- **Cobertura:** mesa passa pela decisão antes de construir a compra ([entries.py:189](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:189)); lançamento também ([launch_entries.py:204](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_entries.py:204)). `spot/1` chama `evaluate_spot_entry`, portanto sua exclusão está coerente com o escopo pedido ([spot_entries.py:210](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:210)).
- **Tempo:** sinal, teto do restante para timestamp futuro e arredondamento para cima estão corretos. O teto limita o **restante anunciado**, não garante liberação 300 s após a primeira observação de um timestamp futuro ([checks_wallet.py:158](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/checks_wallet.py:158)).
- **Último check:** preserva a precedência das outras recusas e continua impedindo aprovação; não encontrei prejuízo de segurança nessa ordem ([evaluate.py:96](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/evaluate.py:96)). “Passou em tudo” significa os checks da admissão, não garantia de sucesso posterior da execução.
- **Estágio 1:** a recusa continua marcando a proposta automática como `rejected`, sem consumir o orçamento horário ([entries.py:87](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:87), [auto_counters.py:28](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/auto_counters.py:28)).
- **Vendas e contador:** saída permanece aprovada independentemente desse check; o contador novo agrega pelo nome-base ([evaluate.py:148](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/evaluate.py:148), [context.py:138](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/context.py:138)).

**OBSIDIAN**

- **EXP-M21 — Pausa por mint:** registrar o excesso de pausa do robô e distinguir recusas de admissão de oportunidades puladas.
- **Diário — 2026-09-20:** registrar os dois achados e separar revisão de código de implantação comprovada.

Segunda opinião (Astra)  
Corrigir a duração da pausa no robô e a omissão de perdas pelo limite global de 50 mints.
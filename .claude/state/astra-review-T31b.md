- **Falta vincular a proposta à carteira avaliada.** [checks.py:167](C:/dev/project-hunter/packages/risk-core/hunter_risk/checks.py:167) verifica atividade e marcações, mas não compara `proposal.portfolio_id` com a carteira recebida; [evaluate.py:163](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:163) atribui a decisão ao ID da proposta. **Cenário:** proposta da carteira A, sem orçamento disponível, recebe por erro o estado da carteira B, com saldo e orçamento livres. Os checks podem passar usando B e produzir aprovação identificada como A.

**OBSIDIAN**

Nenhuma atualização proposta nesta revisão restrita aos quatro arquivos.
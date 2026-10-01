**RESUMO**

Os escopos são complementares, com sobreposição útil em poder, controles e custos: advogado procura falsa confirmação; defensor procura descarte indevido. Padronizaria o acionamento: ambos revisam todo veredito; defensor propõe alternativas apenas nos negativos ([advogado:13](/C:/dev/project-hunter/.claude/agents/advogado-de-jesus.md:13), [defensor:7](/C:/dev/project-hunter/.claude/agents/defensor.md:7)).

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Revisão documental por `Get-Content` e `rg`; sem testes executados. `docs/plans/M4.md` não foi encontrado.

**MUST-FIX**

- **Anti-resgate insuficiente.** “Não usado no teste original” permite usar dados já explorados em outro estudo. Cenário: escolher uma coorte cujo resultado favorável já é conhecido e apresentá-la como validação nova. Exigir histórico de exposição, amostra confirmatória intocada, protocolo congelado antes de abri-la e controle de multiplicidade entre variantes/tentativas — além da parada já prevista ([defensor:20](/C:/dev/project-hunter/.claude/agents/defensor.md:20)).
- **Falta saída “não verificável”.** O advogado permite verificações não executadas, mas termina apenas com “resiste/não resiste”. Cenário: sem evidência sobre antecipação, emitir “resiste”. Incluir conclusão pendente por evidência insuficiente ([advogado:26](/C:/dev/project-hunter/.claude/agents/advogado-de-jesus.md:26)).
- **Contrato de leitura contraditório.** Proíbe qualquer escrita e manda executar `astra.sh ask`, que grava relatório e stderr. Cenário: cumprir a consulta obrigatória viola a própria restrição. Deixar essa chamada com o orquestrador ([advogado:24](/C:/dev/project-hunter/.claude/agents/advogado-de-jesus.md:24), [astra.sh:48](/C:/dev/project-hunter/infra/scripts/astra.sh:48)).

**NICE-TO-HAVE**

Explicitar limites: advogado nunca redefine critérios após resultados; defensor nunca reclassifica sozinho o estudo original nem procura subgrupo vencedor. Ambos nunca alteram código, notas, banco, parâmetros, flags, ordens ou ativações; apenas recomendam. No defensor, explicitar também comandos sem escrita e consultas limitadas ([defensor:20](/C:/dev/project-hunter/.claude/agents/defensor.md:20)).

**O QUE EU FARIA DIFERENTE**

Tornaria **`quant-engineer` independente + Astra obrigatórios para os pareceres**, com reconciliação pela Sexta-feira. Hoje os cartões exigem Astra, mas não nomeiam revisor quantitativo obrigatório. Para alterações nos cartões, permanece `code-reviewer`; guardião de risco entra quando houver mudança no caminho protegido ([advogado:24](/C:/dev/project-hunter/.claude/agents/advogado-de-jesus.md:24), [WORKFLOW:59](/C:/dev/project-hunter/docs/WORKFLOW.md:59)).

**CONCORDO COM**

Opus se justifica pelo julgamento quantitativo, conforme o [workflow:71](/C:/dev/project-hunter/docs/WORKFLOW.md:71). Retiraria apenas a alegação não demonstrada de que modelos menores necessariamente aceitam tabelas ou fazem dredging. Também concordo com permitir “nenhuma proposta honesta” ([defensor:22](/C:/dev/project-hunter/.claude/agents/defensor.md:22)).

**OBSIDIAN**

- **Mente da Sexta-feira** — registrar responsabilidades e revisão obrigatória dos pareceres.
- **Fila de Hipóteses** — acrescentar proveniência da amostra e família de tentativas.
- **Revisões-Astra/roster-pesquisa** — registrar este parecer e as correções aceitas.
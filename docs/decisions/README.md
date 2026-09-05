# Architecture Decision Records (ADR)

Camada dois da memória do projeto (`.claude/memory/INSTRUCTIONS.md`). Uma decisão por arquivo, numerada, imutável. Uma decisão revertida ganha um ADR novo que a substitui; o antigo recebe a linha `Substituído por: NNNN`.

As decisões tomadas na fase de arquitetura estão consolidadas em `docs/SPEC_REVIEW.md`; a partir do Milestone 0, toda decisão nova (ou mudança de uma existente) vira um ADR aqui.

## Template

```markdown
# NNNN — Título curto no imperativo

- **Status:** proposto | aceito | substituído por NNNN
- **Data:** AAAA-MM-DD
- **Contexto:** o problema ou a força que exigiu uma decisão (2–5 frases).
- **Decisão:** o que foi decidido, em uma frase afirmativa.
- **Alternativas consideradas:** lista curta com o motivo de cada rejeição.
- **Consequências:** o que fica mais fácil, o que fica mais difícil, o que precisa ser revisitado e quando.
- **Referências:** documentos, PRs, commits.
```

## Índice

| ADR | Título | Status |
|---|---|---|
| [0001](0001-adotar-vibe-coding-toolkit.md) | Adotar o fluxo do vibe-coding-toolkit para o desenvolvimento | aceito |
| [0002](0002-camada-de-provedores-llm.md) | Camada de provedores LLM com Anthropic e OpenAI (GPT-6 Astra) | aceito (Fase 2) |
| [0003](0003-base-de-conhecimento-obsidian.md) | `obsidian/` como base de conhecimento viva do projeto (separada do `vault/` pessoal) | aceito |

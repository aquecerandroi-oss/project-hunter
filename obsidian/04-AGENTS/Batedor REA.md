---
status: ativo
criado: 2026-10-06
dono: Everton (pedido) · Sexta-feira (cartão)
cartao: .claude/agents/batedor-rea.md
modelo: sonnet
tags: [agente, pesquisa, fontes, rea]
owner: sexta-feira
updated: 2026-10-06
---

# Batedor REA

Batedor de fontes da turma de estratégia, criado em 06/10/2026 a pedido do Everton: "o REA vai participar da turma de estratégia que sai do Obsidian".

**O que faz:** quando uma hipótese da [[Fila de Hipoteses]] ou um experimento precisa de dado de fora, ele observa o site como visitante anônimo pelo [[REA]] e acha a rota, o campo ou o feed. Depois escreve uma **nota de fonte** em `11-KNOWLEDGE/fontes-rea/`, que traz:
- a procedência do dado: observada, no bundle, verificada ou inferência;
- se o dado vale para o passado ou só daqui para a frente;
- uma descrição, com palavras próprias, de como o site monta a feature.

**O que nunca faz:** copiar código, entrar com conta, driblar proteção ou decidir estratégia.

**Orçamento por pedido:** 3 páginas, 15 s por página e 60 chamadas do site. Para no primeiro bloqueio.

**Revisores:**
- a Sexta-feira, em toda nota;
- o quant-engineer, antes de a nota virar evidência de experimento;
- o security-reviewer, em qualquer mudança de permissões;
- quando a fonte vira dado de produto, o exchange-integration-specialist implementa e o code-reviewer revisa.

**Escrita:** técnica e operacionalmente, o cartão só tem `Write`, sem `Edit` e sem Bash. A restrição às pastas `fontes-rea/` e `.claude/state/rea/` é uma regra do cartão; não é forçada por hook (pendente, ver [[roster-batedor-rea]]).

**Termos da pump.fun:** eles proíbem bots e engenharia reversa. O Everton decidiu continuar, com limites: [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]].

## Ligações
[[Agents Overview]] · [[REA]] · [[Fontes REA]] · [[Changelog]]

---
status: ativo
criado: 2026-09-08
dono: Everton (pedido) · Sexta-feira (cartão)
cartao: .claude/agents/product-designer.md
modelo: sonnet
---

# Product Designer

Agente criado em 2026-09-08 a pedido do Everton: "um profissional em design que fica junto aprimorando detalhes do site — temas, cores, UI, UX — técnico em criação de SaaS". Trabalha ao lado da [[Sexta-feira no Hermes]] e da Astra (segunda opinião) e entrega especificações para o `frontend-specialist`.

## O que ele possui
- O contrato de design `docs/DESIGN.md` (paleta escura e clara, escala tipográfica, espaçamento, papéis de borda/raio/sombra, cores semânticas, gráficos, movimento) e o seu histórico.
- A auditoria de cada tela **com dado real no navegador** (organização `ever`): hierarquia, estados honestos (vazio, carregando, erro, atrasado, degradado), responsividade, contraste WCAG AA medido, copy em português, consistência entre páginas.
- Propostas como especificação (problema observado → mudança em tokens/componentes → onde se aplica → acessibilidade → copy). Quando muda a direção visual, apresenta duas ou três opções no `/_design` e **o Everton decide**.
- A revisão do diff e da tela renderizada antes do commit.

## O que ele nunca faz
Dado falso, controle inerte, gráfico decorativo; tocar `.env*`, `services/**`, Risk Engine; commitar; `git stash`/`reset` na árvore compartilhada.

## O que já entregou
- (nada ainda — primeira tarefa: auditoria das quatro telas principais, Radar, Lab, Carteira e System, com dado real na VPS)

## Ligações
[[Agents Overview]] · [[Sexta-feira no Hermes]] · `docs/DESIGN.md` · [[Changelog]]

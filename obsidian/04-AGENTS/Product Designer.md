---
status: ativo
criado: 2026-09-08
dono: Everton (pedido) · Sexta-feira (cartão)
cartao: .claude/agents/product-designer.md
modelo: sonnet
tags: [agente, design, frontend, ux]
owner: sexta-feira
updated: 2026-09-08
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
- 2026-09-08 — T3.23, primeira auditoria (Radar, Lab, Carteira, System, Markets): relatório `.claude/state/review-design-2026-09-08.md` com contraste medido dos tokens (12 falhas AA: badges com alfa, botão destrutivo, item planejado da sidebar, contorno de campo — valores corrigidos calculados), 40+ achados de hierarquia/copy/escala/estados, `docs/DESIGN.md` DESIGN-5 (escala de 7 degraus, badges `-soft`, contorno ≥ 3:1, vocabulário de tempo, sem backstage na copy) e três briefs T3.24 (quick wins, Lab, consistência). A parte no navegador ficou bloqueada: a imagem `hunter-web:dev` local foi construída com a chave falsa do Clerk (`clerk.example.com`) — diagnosticado, com os dois comandos de rebuild em `notes-T3.23.md`; a spec Playwright de captura (`tests/e2e/design-audit.audit.ts`) está pronta para a segunda passada.
- 2026-09-08 — T3.24d, segunda passada (capturas): o `web` local foi reconstruído com a chave real do Clerk (E1 resolvido) e a carteira principal de `ever` foi aberta no banco local (`open_paper_wallet.py`, R$100.000 → 19.435,59 USDT a 5,1452; E2 resolvido). O sign-up de teste falhou 2× e parou: a instância Clerk exige **username + senha** no cadastro (o fluxo e-mail + código `424242` que `tests/e2e/clerk-session.ts` assume não existe nela) — bloqueio E3, para o Everton ajustar no Clerk Dashboard. Capturado o que não exige sessão: `/sign-in` 1440 dark/light com contraste renderizado (todos os pares ≥ 4.92:1; copy do Clerk em inglês, sem `localization` pt-BR — achado SI1). Relatório e briefs atualizados; `notes-T3.24d.md` com a saída real.

## Ligações
[[Agents Overview]] · [[Sexta-feira no Hermes]] · `docs/DESIGN.md` · [[Changelog]]

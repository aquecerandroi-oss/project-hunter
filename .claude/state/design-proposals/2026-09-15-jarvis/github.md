repo: aquecerandroi-oss/project-hunter
branch: main
path: apps/web

## Last sync
date: 2026-09-15T20:52:18Z
### Updated in this project
- Nova identidade JARVIS (grafite + ciano) substituindo dourado/verde/preto de docs/DESIGN.md
- Plataforma navegável única (Hunter Plataforma.dc.html) com 8 telas-filhas e dados demonstrativos compartilhados (hunter-data.js)
- Módulos novos (CRM, chat, WhatsApp, suporte, planos, gamificação) desenhados como demonstração — não existem no repo

## Screen map
| Tela | Arquivos do repo |
|---|---|
| Shell (sidebar, topbar, busca) | apps/web/app/(app)/[orgSlug]/layout.tsx, components/layout/sidebar.tsx, nav-links.tsx, topbar.tsx, lib/nav-registry.ts, app/globals.css |
| Tela Dashboard | app/(app)/[orgSlug]/dashboard/page.tsx, components/dashboard/* |
| Tela Mercados | app/(app)/[orgSlug]/markets/**, components/markets/*, components/radar/labels.ts |
| Tela Oportunidades | app/(app)/[orgSlug]/opportunities/**, components/opportunities/*, lib/api/opportunities-types.ts |
| Tela Agentes | docs/PRODUCT.md §4 (planejada), docs/PIPELINE.md |
| Tela Carteira (carteira, risco, ambientes) | app/(app)/[orgSlug]/portfolio/page.tsx, components/portfolio/*, docs/RISK_ENGINE.md |
| Tela Lab | app/(app)/[orgSlug]/lab/page.tsx, components/lab/*, docs/plans/SHADOW-LAB.md |
| Tela CRM | (novo — sem origem no repo) |
| Tela Administracao | app/(app)/[orgSlug]/settings/**, system/page.tsx, components/system/labels.ts, meme/page.tsx, docs/PRODUCT.md §5 |

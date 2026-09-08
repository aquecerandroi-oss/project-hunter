# Contraste dos tokens (calculado dos valores exatos de globals.css)

AA: 4.5:1 texto normal, 3:1 texto grande (>= 24px ou >= 18.66px bold) e componentes de UI (bordas/ícones).

## dark

| par | texto | fundo | razão | AA (texto) | onde |
|---|---|---|---|---|---|
| fg on bg | #f5f5f5 | #0a0a0a | 18.16:1 | passa (mín. 4.5) | texto principal |
| fg-muted on bg | #a3a3a3 | #0a0a0a | 7.85:1 | passa (mín. 4.5) | labels, notas |
| fg-subtle on bg | #828282 | #0a0a0a | 5.15:1 | passa (mín. 4.5) | metadados (idades, código de exchange) |
| fg-subtle on bg-elevated | #828282 | #111111 | 4.91:1 | passa (mín. 4.5) | notas dentro de cards |
| fg-subtle on bg-overlay | #828282 | #161616 | 4.71:1 | passa (mín. 4.5) | cabeçalho de tabela, linha hover |
| fg-muted on bg-overlay | #a3a3a3 | #161616 | 7.17:1 | passa (mín. 4.5) | thead das tabelas (text-xs) |
| fg/80 on bg-elevated | #c6c6c6 | #111111 | 11.05:1 | passa (mín. 4.5) | item de navegação inativo (nav-links.tsx) |
| fg-subtle @60% on bg-elevated | #525252 | #111111 | 2.42:1 | **FALHA** (mín. 4.5) | item 'Planejado' da sidebar (opacity-60) |
| gold on bg | #f2b705 | #0a0a0a | 10.89:1 | passa (mín. 4.5) | logotipo, links hover |
| gold on gold-soft | #f2b705 | #3a2e08 | 7.34:1 | passa (mín. 4.5) | badge gold (HOT, versão ativa, monitorados), guia ativa do Lab |
| gold-fg on gold | #0a0a0a | #f2b705 | 10.89:1 | passa (mín. 4.5) | botão primário |
| white on red | #ffffff | #ef4444 | 3.76:1 | **FALHA** (mín. 4.5) | botão destrutivo (button.tsx destructive) |
| green on green/15 over bg-elevated | #22c55e | #142c1d | 6.55:1 | passa (mín. 4.5) | badge positive (OK, alvo, lucro, alive) |
| red on red/15 over bg-elevated | #ef4444 | #321919 | 4.34:1 | **FALHA** (mín. 4.5) | badge negative (gap, stop, prejuízo, dead) |
| warning on warning/15 over bg-elevated | #f59e0b | #332610 | 6.84:1 | passa (mín. 4.5) | badge warning (atrasado, ANOMALY, censurado, late) |
| info on info/15 over bg-elevated | #60a5fa | #1d2734 | 5.92:1 | passa (mín. 4.5) | badge info (WATCHING, ativo, paper) |
| green on bg | #22c55e | #0a0a0a | 8.69:1 | passa (mín. 4.5) | variação positiva, PnL > 0 |
| red on bg | #ef4444 | #0a0a0a | 5.26:1 | passa (mín. 4.5) | variação negativa, PnL < 0, mensagens de erro |
| warning on bg | #f59e0b | #0a0a0a | 9.22:1 | passa (mín. 4.5) | texto de aviso (reconcile, tempo real interrompido) |
| info on bg | #60a5fa | #0a0a0a | 7.79:1 | passa (mín. 4.5) | links secundários, linha do gráfico |
| fg on red-soft | #f5f5f5 | #2a0e0e | 16.5:1 | passa (mín. 4.5) | painel do kill switch bloqueado |
| fg-muted on red-soft | #a3a3a3 | #2a0e0e | 7.13:1 | passa (mín. 4.5) | labels no painel bloqueado |
| red on red-soft | #ef4444 | #2a0e0e | 4.78:1 | passa (mín. 4.5) | 'Entradas bloqueadas' no painel |
| fg on gold-soft | #f5f5f5 | #3a2e08 | 12.24:1 | passa (mín. 4.5) | texto sobre seleção dourada |
| fg-muted on gold-soft | #a3a3a3 | #3a2e08 | 5.29:1 | passa (mín. 4.5) | código de exchange na linha selecionada do palette |
| fg-subtle on gold-soft | #828282 | #3a2e08 | 3.47:1 | **FALHA** (mín. 4.5) | (proibido desde DESIGN-3, conferência) |
| fg on bg-overlay | #f5f5f5 | #161616 | 16.6:1 | passa (mín. 4.5) | linhas alternadas, popovers |
| border on bg | #232323 | #0a0a0a | 1.26:1 | **FALHA** (mín. 3) | bordas 1px (não-texto, referência 3:1 para UI) |
| border-strong on bg-elevated | #2e2e2e | #111111 | 1.39:1 | **FALHA** (mín. 3) | separadores (não-texto) |

## light

| par | texto | fundo | razão | AA (texto) | onde |
|---|---|---|---|---|---|
| fg on bg | #0a0a0a | #ffffff | 19.8:1 | passa (mín. 4.5) | texto principal |
| fg-muted on bg | #525252 | #ffffff | 7.81:1 | passa (mín. 4.5) | labels, notas |
| fg-subtle on bg | #666666 | #ffffff | 5.74:1 | passa (mín. 4.5) | metadados (idades, código de exchange) |
| fg-subtle on bg-elevated | #666666 | #fafafa | 5.5:1 | passa (mín. 4.5) | notas dentro de cards |
| fg-subtle on bg-overlay | #666666 | #f3f3f3 | 5.17:1 | passa (mín. 4.5) | cabeçalho de tabela, linha hover |
| fg-muted on bg-overlay | #525252 | #f3f3f3 | 7.04:1 | passa (mín. 4.5) | thead das tabelas (text-xs) |
| fg/80 on bg-elevated | #3b3b3b | #fafafa | 10.73:1 | passa (mín. 4.5) | item de navegação inativo (nav-links.tsx) |
| fg-subtle @60% on bg-elevated | #a3a3a3 | #fafafa | 2.41:1 | **FALHA** (mín. 4.5) | item 'Planejado' da sidebar (opacity-60) |
| gold on bg | #8a6d00 | #ffffff | 4.92:1 | passa (mín. 4.5) | logotipo, links hover |
| gold on gold-soft | #8a6d00 | #fff4d6 | 4.49:1 | **FALHA** (mín. 4.5) | badge gold (HOT, versão ativa, monitorados), guia ativa do Lab |
| gold-fg on gold | #ffffff | #8a6d00 | 4.92:1 | passa (mín. 4.5) | botão primário |
| white on red | #ffffff | #b91c1c | 6.47:1 | passa (mín. 4.5) | botão destrutivo (button.tsx destructive) |
| green on green/15 over bg-elevated | #15803d | #d8e8de | 3.93:1 | **FALHA** (mín. 4.5) | badge positive (OK, alvo, lucro, alive) |
| red on red/15 over bg-elevated | #b91c1c | #f0d9d9 | 4.81:1 | passa (mín. 4.5) | badge negative (gap, stop, prejuízo, dead) |
| warning on warning/15 over bg-elevated | #b45309 | #f0e1d6 | 3.93:1 | **FALHA** (mín. 4.5) | badge warning (atrasado, ANOMALY, censurado, late) |
| info on info/15 over bg-elevated | #1d4ed8 | #d9e0f5 | 5.09:1 | passa (mín. 4.5) | badge info (WATCHING, ativo, paper) |
| green on bg | #15803d | #ffffff | 5.02:1 | passa (mín. 4.5) | variação positiva, PnL > 0 |
| red on bg | #b91c1c | #ffffff | 6.47:1 | passa (mín. 4.5) | variação negativa, PnL < 0, mensagens de erro |
| warning on bg | #b45309 | #ffffff | 5.02:1 | passa (mín. 4.5) | texto de aviso (reconcile, tempo real interrompido) |
| info on bg | #1d4ed8 | #ffffff | 6.7:1 | passa (mín. 4.5) | links secundários, linha do gráfico |
| fg on red-soft | #0a0a0a | #fee2e2 | 16.21:1 | passa (mín. 4.5) | painel do kill switch bloqueado |
| fg-muted on red-soft | #525252 | #fee2e2 | 6.4:1 | passa (mín. 4.5) | labels no painel bloqueado |
| red on red-soft | #b91c1c | #fee2e2 | 5.3:1 | passa (mín. 4.5) | 'Entradas bloqueadas' no painel |
| fg on gold-soft | #0a0a0a | #fff4d6 | 18.07:1 | passa (mín. 4.5) | texto sobre seleção dourada |
| fg-muted on gold-soft | #525252 | #fff4d6 | 7.13:1 | passa (mín. 4.5) | código de exchange na linha selecionada do palette |
| fg-subtle on gold-soft | #666666 | #fff4d6 | 5.24:1 | passa (mín. 4.5) | (proibido desde DESIGN-3, conferência) |
| fg on bg-overlay | #0a0a0a | #f3f3f3 | 17.84:1 | passa (mín. 4.5) | linhas alternadas, popovers |
| border on bg | #e5e5e5 | #ffffff | 1.26:1 | **FALHA** (mín. 3) | bordas 1px (não-texto, referência 3:1 para UI) |
| border-strong on bg-elevated | #d4d4d4 | #fafafa | 1.42:1 | **FALHA** (mín. 3) | separadores (não-texto) |

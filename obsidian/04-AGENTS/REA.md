---
status: ativo
criado: 2026-10-06
dono: Everton (pedido) · Sexta-feira (uso)
ferramenta: rea-agents 4.0.1 (MCP `rea`, registrado no Claude Code)
tags: [ferramenta, engenharia-reversa, pumpfun, pesquisa]
owner: sexta-feira
updated: 2026-10-06
---

# REA — engenharia reversa assistida

Ferramenta instalada em 06/10/2026 a pedido do Everton (`github.com/morluto/rea`, MIT). Ele mesmo instalou com `npm` e rodou o `rea setup` escolhendo só o Claude Code. A Sexta-feira usa o REA pelo MCP.

**Para que serve:** entender como um site ou app funciona por dentro, para aprender e construir o nosso. No Windows funcionam:
- a observação de sites (Chrome sem tela, perfil temporário, sem login);
- a inspeção de pacotes (Electron/ASAR);
- a análise estática de .NET.

Não funcionam no Windows: Ghidra e Hopper (análise de binário nativo) e as utilidades do macOS. Capturas com duas páginas seguidas falham ao fechar o navegador (`cleanup_incomplete`); página por página funciona.

**Regra dura:** só observar o que um visitante anônimo vê. Nunca driblar proteção, limite de acesso, detecção de robô ou CAPTCHA, nem usar conta real. O REA também não guarda o conteúdo das respostas, só a rota, o método, o status e os nomes dos parâmetros. Quem lê o conteúdo é o mapa público ([[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]]).

## O que já leu (06/10)
Notas brutas em `.claude/state/rea-pumpfun-capture-2026-10-06.md`.
- **Home e `/leaderboard`:** ranking de PnL; as posições atuais dos 20 do topo (`/user-positions`); competições de traders (família nova); websockets NATS novos.
- **`/coin/{mint}`:**
  - `profile-api.pump.fun /pnl/coin/{mint}/holders`, o PnL dos holders da moeda: o achado mais relevante para o [[EXP-M15-carteiras-vencedoras]];
  - `/mint-positions`;
  - candles v2;
  - `livestream-api` (`/kols`).
- **Desdobramentos:** a releitura do mapa da pump.fun e a medição de latência dos feeds em tempo real ("chega antes?"), ambas em curso.

## Termos de uso da pump.fun — pausa (06/10)
A Astra apontou, e a Sexta-feira conferiu no texto oficial (`pump.fun/docs/terms-and-conditions`, lido em 06/10), duas cláusulas:
- **§21(h):** proíbe bots, crawlers, scripts ou métodos automáticos para acessar, copiar ou monitorar a plataforma, exceto o que a pump.fun permitir expressamente (§6.1).
- **§21(j):** proíbe desmontar, decompilar ou fazer engenharia reversa da plataforma, inclusive dos conceitos e algoritmos.

**Consequência:** o uso do REA **na pump.fun** fica **pausado** até a decisão do Everton. O mesmo risco vale para a coleta que o meme-worker já faz no frontend da pump.fun desde 09/2026. A blockchain é pública e não é a plataforma deles, então o caminho seguro para o H-030 é a fita on-chain (onda 0/1a/1b) mais provedores com termos próprios (Helius, PumpPortal). Revisão: [[pumpfun-releitura]].

## Ligações
[[Agents Overview]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[KB-0142-kol-e-call-antecipam-ou-confirmam]] · [[2026-10-05]]

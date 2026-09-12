# A4.0f — Notas de pesquisa e verificação

**Astra · documentation-writer · 12/09/2026 · Brasília, UTC−03.**
Escopo autorizado: somente este arquivo e `docs/plans/T4-FERRAMENTAS.md`.
Entrega: [mapa das ferramentas](../../docs/plans/T4-FERRAMENTAS.md).

## Método e alcance

- Pesquisa documental em fontes primárias, por navegador e GET público com curl; nenhum cadastro, credencial, instalação, contratação, envio de mensagem ou operação financeira.
- Horas abaixo são leituras reais em Brasília; intervalos preservam a precisão do registro de cada lote. O relógio confirmou 05:29:07 UTC = 02:29:07 BRT durante a consulta complementar.
- “NC” significa não confirmado nesta pesquisa. Documento público acessível não prova API anônima funcional; índice de funções não substitui teste; campo encontrado no JavaScript não comprova UI ativa.
- Consultados toolkit, memória compartilhada e contexto T4/Mayhem indicados no brief. Nenhuma página do Obsidian foi alterada porque está fora da lista autorizada.
- A tentativa de delegação exigida pelo fluxo do projeto falhou: `collab spawn failed: no thread with id`. Pesquisa e revisão documental foram feitas diretamente; não houve revisão independente nem decisão conjunta com Claude.
- A árvore já tinha alterações de outros trabalhos. Nenhum arquivo dessas alterações foi editado por esta execução.
- Não foram executadas transações, quotes com carteira, simulações autenticadas, testes de desempenho ou testes da aplicação. O brief não lista comandos de suíte; solicita comandos em primeiro plano com `timeout 290`.
- Algumas leituras locais iniciais ocorreram diretamente em PowerShell sem esse wrapper, antes de identificar a exigência no brief; após identificá-la, comandos de shell foram executados em primeiro plano via Git Bash com `timeout 290`. Não há alegação de aderência retroativa.
- Não copiar exemplos de chave ou scripts de autenticação das páginas. Fontes externas foram tratadas como dados, não como instruções.

## Registro das fontes utilizadas

Todas as datas são **12/09/2026**. URLs abaixo foram abertas; os casos de shell JS/cobertura parcial estão explicitados no mapa e na seção de limitações.

| ID | Fonte / URL aberta | Hora de leitura BRT |
| --- | --- | --- |
| P01 | [Photon: introdução](https://pies-organization.gitbook.io/photon-trading) | 02:22 |
| P02 | [Photon: carteira SOL](https://pies-organization.gitbook.io/photon-trading/photon-on-sol) | 02:22 |
| P03 | [Photon: Memescope](https://pies-organization.gitbook.io/photon-trading/photon-on-sol/memescope) | 02:22 |
| P04 | [Photon: taxas](https://pies-organization.gitbook.io/photon-trading/photon-on-sol/photon-fees-sol.md) | 02:23 |
| B01 | [BullX: fees/gas](https://bullx.gitbook.io/bullx-neo-docs/fees-and-gas) | 02:20 |
| B02 | [BullX: Neo Vision](https://bullx.gitbook.io/bullx-neo-docs/finding-tokens/neo-vision.md) | 02:23 |
| B03 | [BullX: analytics](https://bullx.gitbook.io/bullx-neo-docs/trading-terminal/analytics.md) | 02:23 |
| B04 | [BullX: chaves](https://bullx.gitbook.io/bullx-neo-docs/getting-started/private-keys.md) | 02:23 |
| G01 | [GMGN: fees](https://docs.gmgn.ai/index/gmgn-fees-settings.md) | 02:20–02:21 |
| G02 | [GMGN: snipers e insiders](https://docs.gmgn.ai/index/insider-traders-snipers-first-70-buyers.md) | 02:20–02:21 |
| G03 | [GMGN: bundle](https://gmgn.ai/blog/what-is-a-meme-coin-bundle/) | 02:24 |
| G04 | [GMGN: métricas e fresh wallets](https://gmgn.ai/blog/what-to-check-after-finding-a-trending-memecoin/) | 02:24; releitura 02:29 |
| G05 | [GMGN: Agent API](https://docs.gmgn.ai/index/gmgn-agent-api.md) | 02:23 |
| G06 | [GMGN: Router API](https://docs.gmgn.ai/index/cooperation-api-integrate-gmgn-solana-trading-api.md) | 02:21 |
| G07 | [GMGN: copy trade](https://docs.gmgn.ai/index/copy-trade-copy-smart-money-automatically-earn-sol.md) | 02:29 |
| G08 | [GMGN: SnipeX](https://docs.gmgn.ai/index/snipex.md) | 02:29 |
| G09 | [GMGN: auto buy](https://docs.gmgn.ai/index/auto-buy-auto-buy-limit-buy.md) | 02:29 |
| A01 | [Axiom: Pulse](https://docs.axiom.trade/axiom/finding-tokens/pulse.md) | 02:21 |
| A02 | [Axiom: FAQ e custódia](https://docs.axiom.trade/faqs.md) | 02:21 |
| A03 | [Axiom: fees](https://docs.axiom.trade/getting-started/fees/axiom-fees.md) | 02:21 |
| A04 | [Axiom: índice de funções](https://docs.axiom.trade/llms.txt) | 02:21 |
| T01 | [Trojan: FAQ](https://docs.trojanonsolana.com/overview/trojan-on-solana-faq.md) | 02:21–02:22 |
| T02 | [Trojan: sniper](https://docs.trojanonsolana.com/telegram-bot-user-guide/sniper-bot-crypto.md) | 02:24 |
| T03 | [Trojan: carteiras](https://docs.trojanonsolana.com/telegram-bot-user-guide/trojan-bot-settings/wallets.md) | 02:24 |
| K01 | [BONKbot: fees](https://docs.bonkbot.io/fee-structure.md) | 02:22 |
| K02 | [BONKbot: segurança](https://docs.bonkbot.io/security) | 02:21 |
| K03 | [BONKbot: apresentação](https://docs.bonkbot.io) | 02:19 |
| K04 | [BONKbot: Nighthawk speed snipes](https://docs.bonkbot.io/bonkbot/nighthawk-setup/speed-snipes.md) | 02:25 |
| K05 | [BONKbot: analytics do token](https://docs.bonkbot.io/telemetry/trading/terminal/token.md) | 02:25 |
| M01 | [Maestro: sniper](https://docs.maestrobots.com/sniper) | 02:19 |
| M02 | [Maestro: plataformas](https://docs.maestrobots.com/getting-started) | 02:21 |
| M03 | [Maestro: monetização](https://docs.maestrobots.com/monetization) | 02:21 |
| M04 | [Maestro: carteiras](https://docs.maestrobots.com/wallet-setup) | 02:23; releitura 02:25 |
| M05 | [Maestro: Premium](https://docs.maestrobots.com/premium-subscription) | 02:24 |
| N01 | [Nova Light: identificação](https://light-docs.nova.trade/) | 02:22 |
| N02 | [Nova Light: sniper](https://light-docs.nova.trade/modules/sniper.md) | 02:22 |
| N03 | [Nova Light: carteiras](https://light-docs.nova.trade/configuration/wallets) | 02:22 |
| N04 | [Nova Light: referrals e taxa](https://light-docs.nova.trade/earning-with-nova/referrals) | 02:24 |
| N05 | [Nova Light: índice](https://light-docs.nova.trade/llms.txt) | 02:23 |
| L01 | [Bloom: fees](https://docs.bloombot.app/grow-with-bloom/fees-structure.md) | 02:21 |
| L02 | [Bloom: AFK](https://docs.bloombot.app/solana/solana-bot/afk) | 02:22 |
| L03 | [Bloom: copy](https://docs.bloombot.app/solana/solana-bot/copy) | 02:23 |
| L04 | [Bloom: carteiras](https://docs.bloombot.app/solana/solana-bot/wallets) | 02:24 |
| L05 | [Bloom: sniper de migração](https://docs.bloombot.app/solana/solana-bot/sniper) | 02:29 |
| D01 | [pump.fun: vínculo para Terminal](https://pump.fun/) | 02:24 |
| D02 | [Terminal: HTML público](https://terminal.pump.fun) | 02:19; HTML 02:24 |
| D03 | [Terminal: bundle JavaScript público](https://terminal.pump.fun/assets/index-DKS5eDgr.js) | 02:24–02:25 |
| I01 | [Helius: planos](https://www.helius.dev/docs/billing/plans) | 02:20–02:21 |
| I02 | [QuickNode: preços](https://www.quicknode.com/pricing) | 02:20–02:21 |
| I03 | [Triton: preços](https://triton.one/pricing/) | 02:20–02:21 |
| I04 | [Jito: low latency](https://docs.jito.wtf/lowlatencytxnsend/) | 02:20–02:21; releitura 02:25 |
| I05 | [Solana: fees](https://solana.com/docs/core/fees) | 02:21; releitura 02:25 |
| I06 | [Solana: estimador RPC](https://solana.com/docs/rpc/http/getrecentprioritizationfees) | 02:21 |
| I07 | [Helius: estimador](https://www.helius.dev/docs/priority-fee-api) | 02:23–02:25 |
| I08 | [QuickNode: estimador](https://www.quicknode.com/docs/solana/qn_estimatePriorityFees) | 02:23 |
| I09 | [PumpPortal: Local Trading API](https://pumpportal.fun/local-trading-api/trading-api/) | 02:20–02:21 |
| I10 | [PumpPortal: taxas e dados](https://pumpportal.fun/fees/) | 02:21–02:22 |
| I11 | [Jupiter: Swap V2](https://developers.jup.ag/docs/swap) | 02:22 |
| I12 | [Jupiter: order/execute e fees](https://developers.jup.ag/docs/swap/order-and-execute) | 02:24 |
| R01 | [Rugcheck: site](https://rugcheck.xyz) | 02:21 |
| R02 | [Rugcheck: OpenAPI](https://api.rugcheck.xyz/swagger/doc.json) | 02:22; releitura 02:25 |
| R03 | [Solscan: APIs](https://solscan.io/apis) | 02:21 |
| R04 | [SolanaFM: site](https://solana.fm) | 02:21 |
| R05 | [SolanaFM: API](https://docs.solana.fm/reference/solanafm-api-overview) | 02:23 |
| R06 | [SolanaFM: limites](https://docs.solana.fm/reference/rate-limits-1) | 02:23 |
| R07 | [Bitquery: preços](https://bitquery.io/pricing) | 02:21; releitura 02:23 |
| R08 | [Bitquery: autenticação](https://docs.bitquery.io/docs/authorization/how-to-generate/) | 02:22 |
| R09 | [Bitquery: pump.fun](https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/) | 02:25 |
| R10 | [Dune: preços/limites Free](https://docs.dune.com/learning/how-tos/pricing-faqs) | 02:23 |
| R11 | [Dune: autenticação](https://docs.dune.com/api-reference/overview/authentication) | 02:22 |
| R12 | [Dune: Solana](https://docs.dune.com/data-catalog/solana/overview) | 02:25 |
| R13 | [DEX Screener: API](https://docs.dexscreener.com/api/reference) | 02:21; releitura 02:25 |
| R14 | [DEX Screener: listagem](https://docs.dexscreener.com/token-listing) | 02:22 |
| R15 | [DEXTools: planos públicos](https://info.dextools.io/discover-all-our-plans-full-defi-power-at-your-fingertips/) | 02:24 |
| R16 | [DEXTools: portal API](https://developer.dextools.io) | 02:22 |

## Acessos incompletos, erros e recuperação

| URL / situação | Hora BRT | Resultado e tratamento |
| --- | --- | --- |
| https://photon-sol.tinyastro.io | 02:19 | HTTP 403 no navegador; documentação oficial Photon acessível depois. Não foi inspecionada sessão autenticada. |
| https://docs.bullx.io | 02:19–02:21 | Não abriu; documentação BullX Neo GitBook usada em seu lugar. |
| https://docs.trojan.bot e https://docs.trojanonsolana.com/overview/faq | 02:19–02:22 | Primeiro endereço falhou; segundo retornou Page Not Found; FAQ correta registrada em T01. |
| https://docs.tradeonnova.io | 02:19–02:22 | Aplicação em Loading; pesquisa delimitada à Nova Light, N01–N05. Não misturar com novabots.io ou versões legadas. |
| https://docs.padre.gg, https://padre.gg, https://padre.gg/tos | 02:19–02:24 | Bloqueio/403; políticas e taxa corrente não confirmadas. |
| https://docs.terminal.pump.fun | 02:24 | Não abriu. Terminal HTML e bundle público D02/D03 acessíveis via curl. |
| https://terminal.pump.fun/assets/index-DKS5eDgr.js | 02:24–02:25 | Primeira extração com head encerrou pipe e gerou curl 23. Releitura consumindo o fluxo completo com sed terminou com sucesso. Strings de analytics/Turnkey/default fee são evidência estática, não validação funcional. |
| https://content.padre.gg/pitch_deck.pdf | 02:24 | PDF histórico aberto; descreve produto ERC20/Uniswap. Não usado para afirmar preços ou recursos Solana atuais. |
| https://rugcheck.xyz e https://api.rugcheck.xyz/swagger/index.html | 02:21–02:22 | Interfaces dependentes de JavaScript; schema JSON R02 recuperado. Não foi consultado relatório de carteira/cliente/token específico. |
| https://solana.fm | 02:21 | Shell JS; docs R05/R06 lidas, sem confirmar serviço ao vivo. |
| https://dune.com/pricing | 02:21 | Shell sem tabela aproveitável; FAQ R10 usada para Free e limites. Mensalidades pagas não inventadas. |
| https://developers.jup.ag/portal/rate-limit | 02:24 | Redirecionamento a login; preço/franquia da API não confirmado. |
| https://api.jup.ag/swap/v1/program-id-to-label | 02:24–02:25 | Abertura falhou no navegador; sem comprovação de rota PumpSwap por esse caminho. |
| https://docs.dextools.io e https://developer.dextools.io | 02:22 | Primeiro falhou; segundo abriu shell JS. Artigo oficial R15 aproveitado apenas para plano/UI, não para preço da API. |
| https://docs.gmgn.ai/index/copy-trade | 02:29 | URL não abriu; recuperada página correta G07 pelo índice oficial. |
| https://docs.bonkbot.io/bonkbot/nighthawk-setup/sniping/getting-started.md | 02:29 | HTTP bem-sucedido, mas conteúdo Page Not Found; não usado como evidência. K04 é a página de Speed Snipes efetivamente lida. |
| Páginas GitBook .md bloqueadas pelo navegador | 02:22–02:25 | Várias recuperadas por curl público. Apenas conteúdo efetivo, não status HTTP sozinho, foi tratado como evidência. |

## Decisões de interpretação

- Preço “a partir de” com contrato anual não foi misturado a cobrança mensal. Depósito Triton não foi chamado de mensalidade.
- Taxa da plataforma não substitui taxa Pump/pool, rede, prioridade, tip e impacto; páginas antigas com “Pump 1%” ou migração apenas a Raydium não foram usadas para definir o protocolo atual.
- Cashback não foi somado duas vezes nem chamado de desconto incondicional. Axiom bruto 1% está marcado como cálculo a partir da tabela, não citação literal.
- GMGN Agent API hospedada e Router API com assinatura local foram distinguidas. Chave assimétrica de autenticação não foi chamada de chave local da carteira.
- Bundle heurístico, conjunto dos primeiros compradores, insiders e fresh wallets não foram tratados como identidades provadas.
- A expressão de velocidade de analytics BONKbot, tick de leilão Jito e publicidade de auto-buy GMGN não foram convertidos em latência ponta a ponta.
- Ausência de fonte suficiente para denúncia de front-running de clientes foi declarada; funcionalidade de copy anunciada por Maestro não foi transformada em acusação contra o terminal.
- Recomendação de radar/atribuição Mayhem foi apresentada como proposta; não há afirmação de funcionalidade implementada nem alteração de direção de produto.

## Verificações

Comandos executados em primeiro plano, no repositório:

```bash
timeout 290 git diff --no-index --check -- /dev/null docs/plans/T4-FERRAMENTAS.md
timeout 290 git diff --no-index --check -- /dev/null .claude/state/notes-A4.0f.md
```

Ambos: saída vazia, exit 1 porque `--no-index` compara arquivo novo com `/dev/null`; não houve diagnóstico de whitespace. A verificação explícita abaixo confirmou essa interpretação e retornou exit 0:

```bash
timeout 290 bash -c 'set -o pipefail; for target in docs/plans/T4-FERRAMENTAS.md .claude/state/notes-A4.0f.md; do check_output=$(git diff --no-index --check -- /dev/null "$target" 2>&1); check_status=$?; if [ "$check_status" -gt 1 ] || [ -n "$check_output" ]; then printf "%s\n" "$check_output"; exit 1; fi; printf "PASS: %s; no whitespace errors (git --no-index exit %s: new file).\n" "$target" "$check_status"; done; git status --short -- docs/plans/T4-FERRAMENTAS.md .claude/state/notes-A4.0f.md; rg -n "^## " docs/plans/T4-FERRAMENTAS.md .claude/state/notes-A4.0f.md'
```

Saída real relevante:

```text
PASS: docs/plans/T4-FERRAMENTAS.md; no whitespace errors (git --no-index exit 1: new file).
PASS: .claude/state/notes-A4.0f.md; no whitespace errors (git --no-index exit 1: new file).
?? .claude/state/notes-A4.0f.md
?? docs/plans/T4-FERRAMENTAS.md
```

Checagem estrutural executada:

```bash
timeout 290 powershell.exe -NoProfile -Command '$ErrorActionPreference = "Stop"; $taskDoc = Get-Content -LiteralPath "docs/plans/T4-FERRAMENTAS.md" -Raw -Encoding UTF8; $taskNotes = Get-Content -LiteralPath ".claude/state/notes-A4.0f.md" -Raw -Encoding UTF8; $taskDefs = [regex]::Matches($taskDoc, "(?m)^\[([A-Z][0-9]{2})\]: https://") | ForEach-Object { $_.Groups[1].Value }; $taskUses = [regex]::Matches($taskDoc, "\[([A-Z][0-9]{2})\]") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique; foreach ($taskRef in $taskUses) { if ($taskRef -notin $taskDefs) { throw "Undefined reference: $taskRef" }; if (-not $taskNotes.Contains("| $taskRef |")) { throw "Missing timestamp registry: $taskRef" } }; foreach ($taskName in @("Photon", "BullX", "GMGN", "Axiom", "Trojan", "BONKbot", "Maestro", "Terminal", "Nova", "Bloom")) { if (-not $taskDoc.Contains($taskName)) { throw "Missing terminal: $taskName" } }; Write-Output ("PASS: {0} source definitions; all citations resolved and timestamped; 10 terminals present." -f $taskDefs.Count)'
```

Saída real, exit 0:

```text
PASS: 75 source definitions; all citations resolved and timestamped; 10 terminals present.
```

Revisão documental: cinco tópicos do brief presentes; inferências, falhas de acesso e ausência de benchmarks explícitas. Checagem estrutural verifica referências/registro, não a veracidade dos sites nem funcionamento dos serviços. Nenhum teste de aplicação foi declarado como aprovado.

## OBSIDIAN — atualizações sugeridas, não executadas

- **Conhecimento — índice** (`obsidian/11-KNOWLEDGE/Index.md`): vincular o mapa de ferramentas e suas distinções de métricas, assinatura e cobrança.
- **Data Flow** (`obsidian/01-ARCHITECTURE/Data Flow.md`): registrar como proposta as medições de atraso/cobertura da ingestão Solana, separadas da execução.

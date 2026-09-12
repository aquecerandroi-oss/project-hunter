**RESUMO**
**Não liberaria T4.1 ainda:** faltam contrato de dados, cobertura verificável e escopo compatível com o orçamento. Papel: `exchange-integration-specialist`; revisão em OPINIÃO.

**ARQUIVOS**
Nenhum criado ou modificado; nenhum commit.

**TESTES**
Não executados; revisão documental e fontes públicas consultadas nesta rodada. Não reproduzi os testes HTTP/WS de T4.0.

**MUST-FIX — os três bloqueios antes de codar**
1. **Fechar fonte × feature × cobertura:** [plano:180](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:180) exclui trades, mas [plano:204](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:204) promete compradores, razão compra/venda e vendas do criador. Cenário: ausência de feed aparece como “ninguém comprou/dev não vendeu”. Ou contratar coleta verificável, ou retornar nulos com motivo.
2. **Corrigir identidade, unidades e estados:** [plano:146](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:146) deduplica por assinatura/tempo, perdendo trades distintos na mesma transação; [plano:129](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:129) transforma estado desconhecido em `false`. Exigir índices de instrução/evento, finalidade, quote/decimals, reservas iniciais e conclusão separada de migração, como no [parecer:47](C:/dev/project-hunter/.claude/state/astra-review-t40-pumpfun.md:47).
3. **Fechar persistência e aceite operacional:** acrescentar procedência em tokens/snapshots, `available_at`, versões, checkpoints/gaps duráveis e testes de restart/backfill. Cenário: dado recuperado depois entra retrospectivamente num minuto “sem buraco” ([plano:208](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:208)). Alinhar tipos/UUID/privilégios e partições antecipadas a [DATABASE:9](C:/dev/project-hunter/docs/DATABASE.md:9), [DATABASE:119](C:/dev/project-hunter/docs/DATABASE.md:119) e recuperação/rate limit a [EXCHANGE_INTEGRATION:40](C:/dev/project-hunter/docs/EXCHANGE_INTEGRATION.md:40).

**NICE-TO-HAVE — correções documentais adicionais; não são licença para manter números errados**

- **Fontes/limites ([plano:41](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:41)):** um GET não prova quota estável por IP nem SLA; guardar endpoint/resposta datados. PumpPortal publica conexão com chave: gratuito não comprova acesso anônimo. RPC público tem também **40 chamadas/método/10 s**, além de 100/IP/10 s. [PumpPortal](https://pumpportal.fun/data-api/real-time/), [Solana](https://solana.com/docs/references/clusters).
- **Provedores ([plano:44](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:44)):** Helius Free tem **1M créditos/mês**, não apenas 10 RPC/s; gRPC Mainnet começa no Business, **US$499/mês**. QuickNode anuncia **trial de um mês**, 10M créditos/15 req/s; Build **US$49/mês**, ou US$34/mês com cobrança anual. [Helius](https://www.helius.dev/docs/billing/plans), [QuickNode](https://www.quicknode.com/pricing).
- **Bitquery ([plano:47](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:47)):** faltam quotas de streaming: trial inclui **17 stream-minutos/0,2 GB**; Personal não tem streaming; Pro **US$99/mês**, Scale **US$299/mês**, histórico adicional. [Pricing](https://bitquery.io/pricing).
- **Taxas ([plano:84](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:84)):** 1,25% na curva está correto; **0,30% fixo no PumpSwap está errado**: pools canônicos variam por capitalização e quote, de 1,25% a 0,30%; existem pares USDC. [Taxas oficiais](https://pump.fun/docs/fees).
- **Fórmula/graduação ([plano:74](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:74), [plano:153](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:153)):** preço marginal exige reservas em unidades normalizadas; não é preço médio executável. Proponho progresso em tokens `1−real_token_reserves/initial_real_token_reserves`, com denominador histórico por mint e escala explícita. Conclusão é reservas reais de tokens zeradas/`complete=true`; `migrate` é instrução separada. **~85 SOL/US$69 mil não é limiar universal vigente comprovado.** [Programa oficial](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md).
- **Estatística ([plano:94](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:94)):** 0,198% vem de cobertura efetiva de cerca de seis minutos; é limite inferior da graduação em 24 h, não estimativa comparável sem ajuste. [Preprint corrigido](https://arxiv.org/abs/2607.02823).

**O QUE EU FARIA DIFERENTE**

- **T4.1:** exigir IDL fixada por versão, heartbeat separado de atividade, orçamento compartilhado, tratamento de 429/quota, dedupe e reconciliação; fixtures com duplicatas, múltiplos trades/tx, atraso, finalidade e gaps recuperáveis/irrecuperáveis. Receber um lançamento em 60 s não prova cobertura ([aceite:195](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:195)).
- **T4.2:** preservar transferências/estado para holders; agregar por proprietário, excluir curva/pool/burn, separar transferência de venda. Aceitar minutos ausentes ou nulos justificados; testar denominadores, disponibilidade temporal e retenção, conforme [parecer:49](C:/dev/project-hunter/.claude/state/astra-review-t40-pumpfun.md:49).
- **T4.3:** mostrar fonte, instante observado/disponível, atraso, universo selecionado, intervalo coberto e gaps; distinguir zero de `not_subscribed`, `insufficient_coverage`, `rate_limited` e `unsupported_quote`. Testar esses estados na API/tela; “só monitoramento” sozinho não basta ([aceite:222](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:222)).
- **Decisão 1 — features:** começar com descoberta, conclusão/migração e reservas/progresso sob demanda; trades apenas em subconjunto explicitado. Descoberta/migração custam zero no PumpPortal; trades custam **0,01 SOL/10 mil eventos**, sem mensalidade estimável antes de medir eventos. [Preço](https://pumpportal.fun/data-api/real-time/).
- **Decisão 2 — retenção:** manter a mesma janela para graduados e não graduados; rejeitar seleção por sucesso após 30 dias ([plano:262](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:262)), que elimina controles e cria sobrevivência seletiva. Dimensionar janela pelo replay e bytes medidos; custo de armazenamento ainda não estimável.
- **Decisão 3 — RPC com chave:** Helius Free **US$0/mês** para ensaio limitado; Developer **US$49/mês**, 10M créditos/50 RPC/s, se a medição justificar. Chave não garante capacidade; aprovar teto e degradação antes da contratação. [Planos](https://www.helius.dev/docs/billing/plans).

**CONCORDO COM**
Monitoramento separado de execução, API frontend complementar e fixtures offline ([plano:21](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:21), [plano:54](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:54), [plano:189](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:189)).

**OBSIDIAN**

- **Meme Radar — fontes e protocolo:** criar nota com preços datados, contratos, cobertura e decisões pendentes.
- **Social e on-chain — a linha que não atravessamos:** registrar o escopo observacional e requisitos de disponibilidade temporal.
- **Exchange Adapters / Market Collector / Features:** documentar procedência, gaps, nulos e retenção sem seleção por graduação.
# T4 — Ferramentas para observar e, futuramente, executar no pump.fun

**Astra · A4.0f · pesquisa em 12/09/2026, horário de Brasília (UTC−03).** Papel: documentation-writer. Documento de pesquisa e recomendações; nenhuma integração, assinatura, compra, contratação ou teste de latência foi executado.

As referências [P01]–[R16] apontam para URLs efetivamente abertas; seus títulos registram a hora de leitura em Brasília. O registro visível completo está em [notes-A4.0f](../../.claude/state/notes-A4.0f.md). Intervalos indicam a janela da consulta, sem inventar precisão em segundos. Preços em USD, salvo SOL explícito; fotografias da documentação nessa data, não cotações garantidas.

## 1. Terminais: cobertura funcional

**Legenda:** D = documentado; P = parcial, descrito na célula; E = evidência estática no JavaScript público, sem validar UI/backend; NC = não confirmado nas fontes consultadas, **não significa inexistente**. “Sniper de migração” não demonstra compra no lançamento da curva. “Filtro de feed” não demonstra auto-buy. Uma função multichain não é automaticamente uma função Solana/pump.fun.

| Terminal / produto delimitado | Sniper de lançamento | Auto-buy por filtros | Copy-trade | Fontes |
| --- | --- | --- | --- | --- |
| Photon SOL | P: introdução anuncia sniping; gatilho de lançamento NC | NC: Memescope filtra e permite compra rápida | NC | [P01], [P03] |
| BullX Neo | P: documentação menciona sniping, sem configuração de lançamento verificada | NC: Neo Vision filtra o feed; quick-buy não prova automação | NC: tracking não basta | [B01], [B02], [B03] |
| GMGN Solana | P: SnipeX reage a contrato no X e aceita Pump não graduado; não prova captura de toda criação on-chain | D: liquidez/market cap no auto-buy; regras no SnipeX | D: compra/venda automática da carteira seguida | [G07], [G08], [G09] |
| Axiom | NC no lançamento; índice documenta migration buy/sell | P: ordens e migração documentadas no índice; filtro do Pulse não prova AFK universal | NC | [A01], [A04] |
| Trojan Telegram | D: sniper por plataforma e condições | D: dev holding, liquidez, autoridades, redes sociais e whitelist | D | [T01], [T02] |
| BONKbot / Telemetry / Nighthawk | P: Nighthawk Speed Snipes documentado; cobertura específica do lançamento Pump NC | P: parâmetros de snipe; varredura AFK com todos os filtros NC | NC | [K04], [K05] |
| Maestro | P: auto-snipe documentado; plataformas incluem Solana/pump.fun, mas nem toda função multichain foi validada nessa combinação | P: compra por sinais; filtros específicos para Pump NC | D no produto; paridade de todos os modos em Pump NC | [M01], [M02] |
| Padre / Terminal | NC | NC | NC | [D01], [D02], [D03] |
| Nova **Light** | D: gatilhos por mint, símbolo ou creator | P: sniper por gatilho; índice também lista auto-trade | NC nesta documentação | [N01], [N02], [N05] |
| Bloom Solana | P: LP Sniper é de **migração**; AFK cobre descoberta automática | D: AFK por compra inicial, histórico do deployer e outros limites | D: inclui dev holding e diferença máxima de slots | [L02], [L03], [L05] |

### Sinais de distribuição e carteiras

As colunas percentuais não implicam que o fornecedor publicou o denominador, a exclusão de pools, a janela ou a regra de classificação. “Fresh” abaixo significa campo/contagem/rótulo documentado, não necessariamente percentual.

| Terminal | Bundled % | Dev holding | Sniper % | Top-10 | Insiders | Fresh wallets | Fontes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Photon | NC | D | NC | D | NC | NC | [P03] |
| BullX Neo | NC | D | P: painel dos primeiros compradores; percentual exato NC | D | D | NC | [B02], [B03] |
| GMGN | D | D | D | D | D | D no produto; artigo inclui exemplos BSC, validar campo na resposta Solana | [G02], [G03], [G04] |
| Axiom | D | D | D | D | D | NC | [A01], [A02] |
| Trojan | NC | D como filtro | NC | NC | NC | NC | [T02] |
| BONKbot/Telemetry | P: flag de lançamento bundled, não percentual confirmado | D | NC | D | NC | NC | [K05] |
| Maestro | NC | NC | NC | NC | NC | NC | [M01], [M02] |
| Terminal | E | E | E | E | E | E: rótulo de compras fresh | [D03] |
| Nova Light | NC | NC | NC | NC | NC | NC | [N02], [N05] |
| Bloom | NC | D como filtro de copy | NC | NC | NC | NC | [L03] |

**Como interpretar:** Axiom descreve bundles por quatro ou mais transações no mesmo bloco e admite remover a classificação depois de compras fora do grupo. BullX descreve insiders por recebimento sem compra e acompanha os primeiros 70 compradores. GMGN separa primeiros compradores, holdings atuais e transferências; seu artigo define Fresh como últimos sete dias, com diferenças entre redes. São definições comerciais, não identidades provadas nem probabilidades de rug. [A02], [B03], [G02], [G04]

**Inferência para o Hunter:** registrar o snapshot disponível na decisão, a versão da heurística e a razão do rótulo; não reconstruir a “verdade histórica” com o rótulo atual. Mesmo bloco, financiador compartilhado ou recebimento por transferência, isoladamente, não bastam para afirmar mesmo controlador. “Bundled %” de analytics não comprova entrega por bundle Jito. [A02], [G03], [G04], [I04]

### Taxa, latência anunciada, API e controle da assinatura

Taxas abaixo são do serviço por compra/venda, salvo indicação. Rede, prioridade, tip, pool/protocolo, impacto e slippage são componentes distintos; cashback condicionado não deve reduzir o caixa necessário antes de seu recebimento. Esta separação é uma recomendação contábil baseada nas estruturas publicadas. [B01], [G01], [I05], [I10], [I12]

| Terminal | Taxa publicada por trade | Latência anunciada encontrada — não medida | API pública documentada / chave e assinatura | Fontes |
| --- | --- | --- | --- | --- |
| Photon | 1% em cada compra/venda | Compra com um clique; sem número de inclusão confirmado | API NC; cria carteira de trading e mostra private key uma vez; exclusividade de assinatura local NC | [P01], [P02], [P04] |
| BullX Neo | 1%; página descreve adicional de 0,002 SOL para MEV, além dos ajustes de prioridade/bribe | Sem número comparável confirmado | API NC; chave gerada/exportável; isso não prova que só o usuário assina | [B01], [B04] |
| GMGN | 1%; prioridade/tip adicionais | SnipeX anuncia milissegundos para auto-buy; auto-buy anuncia segundos; métricas diferentes, sem benchmark | Agent API exige API key e usa carteiras hospedadas; par assimétrico de autenticação não é a chave on-chain local. Router API é outra oferta: aprovação, x-route-key, 1 chamada/5 s e transação para assinatura local | [G01], [G05], [G06], [G08], [G09] |
| Axiom | Tabela informa líquido de 0,95% a 0,75%, conforme tier; somando cashback da tabela, bruto de 1% é **inferência aritmética** | Sem número de inclusão confirmado | API NC; declara non-custodial com Turnkey; serviço de assinatura parceiro não equivale a chave exclusivamente no computador | [A02], [A03] |
| Trojan | 1% em swaps bem-sucedidos; FAQ anuncia cashback de 20% da taxa | Sem número comparável confirmado | API NC; importa/exporta private key via fluxo do bot; custódia técnica exclusiva local NC | [T01], [T03] |
| BONKbot | 1% em swaps bem-sucedidos | Site anuncia analytics submilissegundo; não é inclusão da ordem | API NC; declara Signer non-custodial sem acesso de BONKbot/Telegram à chave; declaração do fornecedor, não auditoria desta pesquisa | [K01], [K02], [K03] |
| Maestro | 1%; em Solana, extração na própria transação; Premium opcional USD 200/mês | Premium anuncia vantagem de velocidade, sem número verificável | API NC; criação/importação/exportação de chave; assinatura estritamente local NC | [M03], [M04], [M05] |
| Padre / Terminal | **NC vigente**: código público contém configuração padrão feeBps=100; não prova cobrança aplicada | NC | API pública contratual NC. Bundle contém integração Turnkey/import/export; não prova política efetiva de custódia nem execução local | [D02], [D03] |
| Nova Light | 1%; documentação cita Pro Account de 0,002 SOL por carteira, não mensalidade | Sem número comparável confirmado | API NC; cria/importa private key; processador remoto não prova assinatura local | [N02], [N03], [N04] |
| Bloom | 1%; 0,9% para referido segundo página de fees | Sem número de inclusão confirmado | API NC; cria/importa carteiras e seleciona uma padrão para automação; assinatura exclusivamente local NC | [L01], [L04], [L05] |

**Limites de identidade e acesso:** pump.fun liga “Terminal” a trade.padre.gg; terminal.pump.fun entrega HTML/JavaScript, mas não obtive uma sessão funcional autenticada. Campos estáticos podem estar inativos. Nova foi delimitado à documentação Nova Light, sem atribuir recursos de sites homônimos ou versões antigas. [D01], [D02], [D03], [N01]

## 2. Infra de execução: custo × latência × dependência de chave

Planos consultados em **12/09/2026, 02:20–02:25 BRT**. Créditos, chamadas e GB não são unidades intercambiáveis. A coluna de latência informa o que se pode concluir das fontes, não uma classificação de velocidade medida.

| Serviço / opção | Custo e limite documentados | Latência / condição relevante | Dependência de chave e função | Fontes |
| --- | --- | --- | --- | --- |
| Helius Free / Developer | USD 0: 1 M créditos, 10 RPC/s; USD 49/mês: 10 M, 50 RPC/s | Sem p50/p95 medido; plano não determina sozinho atraso | Credencial RPC; não precisa da private key para dados ou envio de tx já assinada | [I01] |
| Helius Business / Professional | USD 499/mês: 100 M, 200 RPC/s; USD 999/mês: 200 M, 500 RPC/s | LaserStream gRPC mainnet nesses tiers; não assumir incluso no Developer | Credencial do fornecedor; signer continua separado | [I01] |
| QuickNode | Trial de 1 mês USD 0, 10 M créditos, 15 req/s. Build USD 49/mês, 80 M, 50 req/s; Accelerate USD 249, 450 M, 125 req/s; Scale USD 499, 950 M, 250 req/s | Não confundir preços anuais equivalentes de USD 34/212/424 com mensal sem compromisso; desempenho não medido | Endpoint autenticado; confirmar cobrança de streams/add-ons separadamente; nenhuma private key necessária ao RPC | [I02] |
| Triton | Depósito pré-pago USD 125, não reembolsável, válido por 12 meses; RPC USD 10/M chamadas + USD 0,08/GB; streaming USD 0,08/GB | Limites flexíveis, sem RPS fixo confirmado; Shred Streaming USD 1.500/mês/IP/datacenter | Credencial; não confundir depósito com assinatura mensal ou RPC com signer | [I03] |
| Jito Block Engine | Tip mínimo documentado 1.000 lamports; disputa pode exigir mais; prioridade/rede à parte | Leilão em ticks de 50 ms, **não** inclusão em 50 ms; bundle ID não confirma execução | Recebe tx assinadas; bundles de até 5 tx, sequenciais, atômicas no mesmo slot, com ressalva de blocos descartados | [I04] |
| Solana RPC / priority fee | Base 5.000 lamports por assinatura; prioridade opcional na fórmula abaixo; custo RPC depende do plano | Estimativa histórica não reserva inclusão futura | getRecentPrioritizationFees; Helius getPriorityFeeEstimate e QuickNode qn_estimatePriorityFees são alternativas autenticadas de provedor | [I05], [I06], [I07], [I08] |
| PumpPortal Local API | 0,5% por trade, calculado antes do slippage; taxas de rede/Pump adicionais | Montagem remota + assinatura e envio no cliente; nenhum tempo de execução medido | /api/trade-local recebe publicKey e parâmetros, retorna tx serializada; chave e assinatura ficam no cliente; cliente escolhe RPC. Enum inclui pump e pump-amm | [I09], [I10] |
| Jupiter Swap V2 Router / Meta | Router /build sem taxa de swap Jupiter; Meta /order: token novo <24 h, 50 bps; outros 10 bps, com classes reduzidas | Cotação não garante preenchimento; rota para PumpSwap precisa ser verificada para mint, tamanho e instante | API key; cliente assina. Router monta instruções para envio próprio; Meta /execute usa landing do serviço | [I11], [I12] |

Para transações no formato corrente descrito pela documentação Solana: prioridade em lamports = ceil(CU_limit × CU_price_micro_lamports / 1.000.000). A cobrança usa o limite solicitado, não apenas unidades consumidas. Tip Jito é outro pagamento. Não aplicar antecipadamente regras de formatos futuros descritos na mesma página. [I05], [I04]

**PumpPortal: o que não fica local.** O servidor conhece os parâmetros e monta a transação; a responsabilidade de validar instruções, destinatários e limites antes de assinar permanece com o cliente. Isso é inferência do fluxo documentado, não alegação de abuso. Lightning é outra oferta, com taxa de 1%; criação/migração como dados são gratuitas, enquanto eventos de trades custam 0,01 SOL/10.000, exigindo API key segundo a página vigente. Não confundir dados gratuitos com execução gratuita. [I09], [I10]

**Jupiter para saída PumpSwap?** Candidato, ainda não integração validada. A documentação geral Swap V2 aberta não prova que uma determinada pool PumpSwap terá rota no instante da saída. Exigir quote real, identificação dos programas/pools e simulação antes de decidir. PumpPortal declara explicitamente pool=pump-amm como alternativa documentada. Também não usar a antiga generalização “Jupiter cobra só 5–10 bps”: a página atual Meta informa 50 bps para tokens novos e distingue feeBps total de platformFee, inclusive possíveis custos gasless. [I09], [I11], [I12]

**Medição proposta:** separar descoberta on-chain → recepção → atualização do sinal → construção → assinatura → envio → confirmação, mantendo slot, commitment, UTC, tamanho da ordem, região/RPC e custo efetivo. Comparar p50/p95/p99, perdas e reconexões com o mesmo conjunto de eventos. Nesta pesquisa, não foram medidos nem prometidos valores.

## 3. Análise, risco e descoberta sem chave

| Serviço | O que a fonte expõe / método | Sem chave e custo verificável | Pump.fun: cobertura e momento de aparição | Fontes |
| --- | --- | --- | --- | --- |
| Rugcheck | OpenAPI: risks com nome, descrição, nível e score; score normalizado, autoridades e dados de liquidez. Pesos completos/calibração de fraude NC | Schema de report individual não declara autenticação; bulk exige API key e refresh tem restrição paga. GET real de relatório não foi testado; mensalidade NC | Análise por mint, não feed de todos os lançamentos; score não garante venda ou ausência de rug | [R01], [R02] |
| Solscan | Portal oferece APIs de transações, holders, contas e dados de mercado | API requer chave. Explorer e API são ofertas distintas; cota/preço gratuito da API NC na página aberta | Útil como consulta manual e reconciliação; nenhuma garantia de alerta no lançamento verificada | [R03] |
| SolanaFM | Docs descrevem API HTTPS gratuita e limitada | Free USD 0, limite geral 10 req/s; endpoints de holders/supply 5 req/s. Página antiga, operação atual não testada; site abriu apenas shell JS | Dados de contas/transações; ausência de benchmark impede tratá-lo como feed de sniping | [R04], [R05], [R06] |
| Bitquery | Documentação específica de Pump.fun e consultas de dados Solana | API exige token; não há consulta programática anônima confirmada. Trial 7 dias/1.000 pontos. Personal USD 49/mês sem uso comercial/streams; Pro USD 99/mês | Documentação não prova retenção granular ilimitada. Verificar janela do dataset necessário; plano pago não implica todo histórico | [R07], [R08], [R09] |
| Dune | Catálogo Solana para análise histórica; adequado como hipótese de auditoria em lote | Ler material público não equivale a executar SQL anonimamente: API exige chave. Free anuncia 2.500 créditos/mês; excedente USD 5/100, com controle de gasto | Não foi verificada disponibilidade/latência de tabela específica Pump.fun/PumpSwap; não contratar como feed de lançamento por suposição | [R10], [R11], [R12] |
| DEX Screener | API documenta pares, preço, volume, compras/vendas, liquidez, FDV/market cap, pairCreatedAt e boosts | Endpoints documentados sem autenticação nos exemplos; nenhuma compra ou chave usada. Não inclui, nesse contrato consultado, conjunto completo de insiders/bundlers | Regra de listagem automática: pool de liquidez e ≥1 transação. Não prova aparição no mint nem autoriza afirmar “só após graduação”; cobertura da curva e atraso NC | [R13], [R14] |
| DEXTools | Artigo oficial de 29/01/2024 anuncia Free com Live New Pairs, Pair Explorer, gráficos e estatísticas; disponibilidade atual não testada | Portal API abriu como aplicação JS: preços, cotas e anonimato da API NC; Free da UI não é licença/API ilimitada | Momento de indexação da curva Pump e PumpSwap NC; não substituir fonte de criação com base na marca | [R15], [R16] |

**Proposta de uso:** Rugcheck como evidência complementar, exploradores para conferir transações, Dune/Bitquery para perguntas históricas quando acesso e retenção forem comprovados, DEX Screener como enriquecimento de pares. Nenhum rótulo de risco deve virar verdade de treinamento sem preservar método, disponibilidade temporal e cobertura.

## 4. O que pagar e o que não pagar

Recomendação da Astra para decisão de Everton; não é contratação aprovada. “Grátis agora” restringe-se a observação/pesquisa dentro da franquia. Taxas por transação não foram convertidas em mensalidades fictícias.

| Decisão | Serviço / uso | Mensalidade ou unidade citada | Gatilho / razão da recomendação | Fontes |
| --- | --- | --- | --- | --- |
| Grátis agora | Helius Free para prova de coleta | USD 0/mês, 1 M créditos e 10 RPC/s | Medir lacunas e atraso antes de ampliar | [I01] |
| Grátis agora | Dune Free; documentação/exploradores; DEX Screener | Dune USD 0 com 2.500 créditos; SolanaFM Free USD 0; DEX Screener sem mensalidade publicada nas páginas consultadas | Perguntas em lote e enriquecimento; não presumir API gratuita onde só a UI foi verificada | [R10], [R06], [R13] |
| Grátis agora, com escopo delimitado | PumpPortal: eventos de criação e migração | Sem mensalidade publicada; esses eventos são gratuitos | Trades são cobrados: 0,01 SOL/10.000; contabilizar separadamente | [I10] |
| Pagar quando medir | Helius Developer **ou** QuickNode Build | USD 49/mês cada, cobrança mensal; não ambos por padrão | Escolher por perda de eventos, atraso e consumo medidos, não pelo nome do plano | [I01], [I02] |
| Pagar quando medir | Triton por consumo | Não há mensalidade fixa confirmada; depósito USD 125; USD 10/M RPC + USD 0,08/GB | Orçar volume e saída; depósito inicial não é custo mensal | [I03] |
| Pagar quando medir | Bitquery Pro | USD 99/mês; Personal USD 49 tem vedação comercial e não oferece streams | Somente se query/dataset e retenção resolverem necessidade comprovada; teste antes | [R07] |
| Pagar quando medir | Helius Business / Professional | USD 499 / USD 999 por mês | Apenas se streaming mainnet e volume justificarem; não para “ficar mais rápido” sem diagnóstico | [I01] |
| Pagar quando medir e houver autorização de execução | PumpPortal Local ou Jupiter Meta | Sem mensalidade confirmada: 0,5% Local; Meta 50 bps em tokens <24 h | Comparar custo total com Router e resultado de execução; não pagar ambos inadvertidamente | [I10], [I11], [I12] |
| Nunca para o radar observacional | Premium de bot e fluxo de trade só para obter analytics | Maestro USD 200/mês; vários terminais cobram 1% por operação | Pesquisa não exige entregar carteira nem gerar operações para desbloquear leitura | [M05], [P04], [G01] |
| Nunca sem resultado medido e autorização expressa | Shreds premium | Triton USD 1.500/mês/IP/datacenter; Helius USD 1.000/mês/IP, USD 800 no Pro | Custo não justificado por este levantamento; reconsiderar só com evidência nova | [I03], [I01] |

Modelo de orçamento proposto: assinatura + consumo de dados/RPC + armazenamento + taxas de cada tentativa/operação. Em execução futura, separar taxa do terminal/roteador, protocolo/pool, rede, prioridade, tip, contas criadas e slippage efetivamente realizado. Sem volume e preços SOL observados, não há total mensal honesto em reais ou dólares.

## 5. Riscos específicos dos terminais e controles propostos

1. **Chave exportável não prova custódia exclusiva.** Photon, BullX, Trojan, Maestro, Nova e Bloom documentam geração/importação/exportação; isso não demonstra a arquitetura de armazenamento nem revogação. Axiom declara Turnkey e BONKbot declara Signer non-custodial: são modelos remotos, a confirmar por políticas/auditorias. Proposta: separar carteira operacional, limites e permissões; não importar carteira patrimonial para teste. [P02], [B04], [T03], [M04], [N03], [L04], [A02], [K02]
2. **Visibilidade da ordem antes de inclusão.** PumpPortal monta remotamente, GMGN distingue hospedagem de assinatura local e Jupiter pode cuidar do landing. Inferência: esses componentes conhecem a intenção/transação e participam do caminho de execução. **Não foi encontrada nesta pesquisa evidência primária suficiente para acusar qualquer terminal listado de fazer front-running dos próprios clientes.** [I09], [G05], [G06], [I11]
3. **Não confundir funcionalidades ofensivas com denúncia contra o operador.** Maestro anuncia que seu copy pode antecipar a carteira seguida quando aplicável; o texto é multichain e não comprova front-running de clientes em Solana. Jito descreve exceções de atomicidade por blocos descartados e retransmissão; “Anti-MEV” não deve ser interpretado como garantia absoluta. [M01], [I04]
4. **Custos omitidos da comparação, não necessariamente ocultados pelo fornecedor.** BullX separa MEV/prioridade/bribe; PumpPortal separa serviço de rede/protocolo; Jupiter distingue platformFee e feeBps total; cashback pode chegar depois. Proposta: reconciliar instruções e débitos da transação, além do preço exibido. [B01], [I10], [I12], [A03]
5. **Falha e corrida de automação.** Nighthawk alerta que Speed Snipes podem consumir fee/bribe sem conseguir a compra. Trojan documenta que max-snipes é atualizado na confirmação e pode ser ultrapassado por tentativas concorrentes; seu FAQ alerta para limitações de copy e swaps enganosos. Proposta: reserva de orçamento por tentativa, idempotência e reconciliação antes de reenviar. [K04], [T02], [T01]
6. **Enriquecimento tardio vira look-ahead.** Rótulos Axiom podem mudar após novas compras e métricas GMGN têm definições específicas. Proposta: congelar o dado e sua disponibilidade na decisão, manter “desconhecido” para cobertura incompleta, não usar retrospectivamente um score atualizado como se já existisse. [A02], [G02], [G04]

## 6. Conclusão para o radar — proposta, não funcionalidade implementada

**Precisamos competir na qualidade da observação:** descoberta de criação/curva/migração com atraso mensurado; concentração top-10 com exclusões explícitas; posição do creator e histórico disponível; primeiros compradores e holdings atuais separados; transferências e origem de financiamento; agrupamento com confiança, janela e evidência; wallets recentes com definição; custos e liquidez de saída observáveis. As matrizes mostram por que um radar apenas de preço/volume deixaria sinais já expostos por concorrentes de fora. [P03], [B03], [A01], [G02], [G03], [G04]

**Não precisamos copiar para pesquisar:** custódia remota, one-click trade, copy de KOL, sniper que ignora filtros, ranking de lucro sem base de custo, cashback/gamificação ou planos premium antes da medição. Trata-se de recomendação de escopo. Concorrentes oferecerem automação não demonstra vantagem líquida para nossa estratégia. [G07], [G08], [T01], [M05]

**Proposta coerente com o trabalho Mayhem em paralelo:** separar fluxo atribuído ao agente conhecido de fluxo orgânico, registrando programa/instrução/CPI e versão da atribuição; fee payer sozinho não deve decidir o rótulo. Cobertura desconhecida continua desconhecida. Este parágrafo propõe requisito; não afirma que a implementação atual já o atende. Contexto interno: [plano T4](T4-MEME-RADAR.md) e [notas Mayhem](../../.claude/state/notes-A4.1b-mayhem.md).

**Pendências verificáveis:** acesso funcional ao Terminal para confirmar taxa/políticas; confirmação Solana de campos multichain; quote/simulação de saída PumpSwap via Jupiter; amostra pareada para atraso/cobertura; verificação das cotas efetivas Rugcheck/SolanaFM e preços de APIs não publicados. São limites deste mapa, não autorização para contratar ou operar.

## Fontes com data/hora de leitura

Todas em 12/09/2026 BRT. O horário faz parte do título de cada link; a lista com horários visíveis e ocorrências de acesso está em [notes-A4.0f](../../.claude/state/notes-A4.0f.md).

[P01]: https://pies-organization.gitbook.io/photon-trading "Photon: introdução — lido em 12/09/2026, 02:22 BRT"
[P02]: https://pies-organization.gitbook.io/photon-trading/photon-on-sol "Photon: carteira SOL — lido em 12/09/2026, 02:22 BRT"
[P03]: https://pies-organization.gitbook.io/photon-trading/photon-on-sol/memescope "Photon: Memescope — lido em 12/09/2026, 02:22 BRT"
[P04]: https://pies-organization.gitbook.io/photon-trading/photon-on-sol/photon-fees-sol.md "Photon: taxas — lido em 12/09/2026, 02:23 BRT"
[B01]: https://bullx.gitbook.io/bullx-neo-docs/fees-and-gas "BullX: fees/gas — lido em 12/09/2026, 02:20 BRT"
[B02]: https://bullx.gitbook.io/bullx-neo-docs/finding-tokens/neo-vision.md "BullX: Neo Vision — lido em 12/09/2026, 02:23 BRT"
[B03]: https://bullx.gitbook.io/bullx-neo-docs/trading-terminal/analytics.md "BullX: analytics — lido em 12/09/2026, 02:23 BRT"
[B04]: https://bullx.gitbook.io/bullx-neo-docs/getting-started/private-keys.md "BullX: chaves — lido em 12/09/2026, 02:23 BRT"
[G01]: https://docs.gmgn.ai/index/gmgn-fees-settings.md "GMGN: fees — lido em 12/09/2026, 02:20–02:21 BRT"
[G02]: https://docs.gmgn.ai/index/insider-traders-snipers-first-70-buyers.md "GMGN: snipers e insiders — lido em 12/09/2026, 02:20–02:21 BRT"
[G03]: https://gmgn.ai/blog/what-is-a-meme-coin-bundle/ "GMGN: bundle — lido em 12/09/2026, 02:24 BRT"
[G04]: https://gmgn.ai/blog/what-to-check-after-finding-a-trending-memecoin/ "GMGN: métricas e fresh wallets — lido em 12/09/2026, 02:24; releitura 02:29 BRT"
[G05]: https://docs.gmgn.ai/index/gmgn-agent-api.md "GMGN: Agent API — lido em 12/09/2026, 02:23 BRT"
[G06]: https://docs.gmgn.ai/index/cooperation-api-integrate-gmgn-solana-trading-api.md "GMGN: Router API — lido em 12/09/2026, 02:21 BRT"
[G07]: https://docs.gmgn.ai/index/copy-trade-copy-smart-money-automatically-earn-sol.md "GMGN: copy trade — lido em 12/09/2026, 02:29 BRT"
[G08]: https://docs.gmgn.ai/index/snipex.md "GMGN: SnipeX — lido em 12/09/2026, 02:29 BRT"
[G09]: https://docs.gmgn.ai/index/auto-buy-auto-buy-limit-buy.md "GMGN: auto buy — lido em 12/09/2026, 02:29 BRT"
[A01]: https://docs.axiom.trade/axiom/finding-tokens/pulse.md "Axiom: Pulse — lido em 12/09/2026, 02:21 BRT"
[A02]: https://docs.axiom.trade/faqs.md "Axiom: FAQ e custódia — lido em 12/09/2026, 02:21 BRT"
[A03]: https://docs.axiom.trade/getting-started/fees/axiom-fees.md "Axiom: fees — lido em 12/09/2026, 02:21 BRT"
[A04]: https://docs.axiom.trade/llms.txt "Axiom: índice de funções — lido em 12/09/2026, 02:21 BRT"
[T01]: https://docs.trojanonsolana.com/overview/trojan-on-solana-faq.md "Trojan: FAQ — lido em 12/09/2026, 02:21–02:22 BRT"
[T02]: https://docs.trojanonsolana.com/telegram-bot-user-guide/sniper-bot-crypto.md "Trojan: sniper — lido em 12/09/2026, 02:24 BRT"
[T03]: https://docs.trojanonsolana.com/telegram-bot-user-guide/trojan-bot-settings/wallets.md "Trojan: carteiras — lido em 12/09/2026, 02:24 BRT"
[K01]: https://docs.bonkbot.io/fee-structure.md "BONKbot: fees — lido em 12/09/2026, 02:22 BRT"
[K02]: https://docs.bonkbot.io/security "BONKbot: segurança — lido em 12/09/2026, 02:21 BRT"
[K03]: https://docs.bonkbot.io "BONKbot: apresentação — lido em 12/09/2026, 02:19 BRT"
[K04]: https://docs.bonkbot.io/bonkbot/nighthawk-setup/speed-snipes.md "BONKbot: Nighthawk speed snipes — lido em 12/09/2026, 02:25 BRT"
[K05]: https://docs.bonkbot.io/telemetry/trading/terminal/token.md "BONKbot: analytics do token — lido em 12/09/2026, 02:25 BRT"
[M01]: https://docs.maestrobots.com/sniper "Maestro: sniper — lido em 12/09/2026, 02:19 BRT"
[M02]: https://docs.maestrobots.com/getting-started "Maestro: plataformas — lido em 12/09/2026, 02:21 BRT"
[M03]: https://docs.maestrobots.com/monetization "Maestro: monetização — lido em 12/09/2026, 02:21 BRT"
[M04]: https://docs.maestrobots.com/wallet-setup "Maestro: carteiras — lido em 12/09/2026, 02:23; releitura 02:25 BRT"
[M05]: https://docs.maestrobots.com/premium-subscription "Maestro: Premium — lido em 12/09/2026, 02:24 BRT"
[N01]: https://light-docs.nova.trade/ "Nova Light: identificação — lido em 12/09/2026, 02:22 BRT"
[N02]: https://light-docs.nova.trade/modules/sniper.md "Nova Light: sniper — lido em 12/09/2026, 02:22 BRT"
[N03]: https://light-docs.nova.trade/configuration/wallets "Nova Light: carteiras — lido em 12/09/2026, 02:22 BRT"
[N04]: https://light-docs.nova.trade/earning-with-nova/referrals "Nova Light: referrals e taxa — lido em 12/09/2026, 02:24 BRT"
[N05]: https://light-docs.nova.trade/llms.txt "Nova Light: índice — lido em 12/09/2026, 02:23 BRT"
[L01]: https://docs.bloombot.app/grow-with-bloom/fees-structure.md "Bloom: fees — lido em 12/09/2026, 02:21 BRT"
[L02]: https://docs.bloombot.app/solana/solana-bot/afk "Bloom: AFK — lido em 12/09/2026, 02:22 BRT"
[L03]: https://docs.bloombot.app/solana/solana-bot/copy "Bloom: copy — lido em 12/09/2026, 02:23 BRT"
[L04]: https://docs.bloombot.app/solana/solana-bot/wallets "Bloom: carteiras — lido em 12/09/2026, 02:24 BRT"
[L05]: https://docs.bloombot.app/solana/solana-bot/sniper "Bloom: sniper de migração — lido em 12/09/2026, 02:29 BRT"
[D01]: https://pump.fun/ "pump.fun: vínculo para Terminal — lido em 12/09/2026, 02:24 BRT"
[D02]: https://terminal.pump.fun "Terminal: HTML público — lido em 12/09/2026, 02:19; HTML 02:24 BRT"
[D03]: https://terminal.pump.fun/assets/index-DKS5eDgr.js "Terminal: bundle JavaScript público — lido em 12/09/2026, 02:24–02:25 BRT"
[I01]: https://www.helius.dev/docs/billing/plans "Helius: planos — lido em 12/09/2026, 02:20–02:21 BRT"
[I02]: https://www.quicknode.com/pricing "QuickNode: preços — lido em 12/09/2026, 02:20–02:21 BRT"
[I03]: https://triton.one/pricing/ "Triton: preços — lido em 12/09/2026, 02:20–02:21 BRT"
[I04]: https://docs.jito.wtf/lowlatencytxnsend/ "Jito: low latency — lido em 12/09/2026, 02:20–02:21; releitura 02:25 BRT"
[I05]: https://solana.com/docs/core/fees "Solana: fees — lido em 12/09/2026, 02:21; releitura 02:25 BRT"
[I06]: https://solana.com/docs/rpc/http/getrecentprioritizationfees "Solana: estimador RPC — lido em 12/09/2026, 02:21 BRT"
[I07]: https://www.helius.dev/docs/priority-fee-api "Helius: estimador — lido em 12/09/2026, 02:23–02:25 BRT"
[I08]: https://www.quicknode.com/docs/solana/qn_estimatePriorityFees "QuickNode: estimador — lido em 12/09/2026, 02:23 BRT"
[I09]: https://pumpportal.fun/local-trading-api/trading-api/ "PumpPortal: Local Trading API — lido em 12/09/2026, 02:20–02:21 BRT"
[I10]: https://pumpportal.fun/fees/ "PumpPortal: taxas e dados — lido em 12/09/2026, 02:21–02:22 BRT"
[I11]: https://developers.jup.ag/docs/swap "Jupiter: Swap V2 — lido em 12/09/2026, 02:22 BRT"
[I12]: https://developers.jup.ag/docs/swap/order-and-execute "Jupiter: order/execute e fees — lido em 12/09/2026, 02:24 BRT"
[R01]: https://rugcheck.xyz "Rugcheck: site — lido em 12/09/2026, 02:21 BRT"
[R02]: https://api.rugcheck.xyz/swagger/doc.json "Rugcheck: OpenAPI — lido em 12/09/2026, 02:22; releitura 02:25 BRT"
[R03]: https://solscan.io/apis "Solscan: APIs — lido em 12/09/2026, 02:21 BRT"
[R04]: https://solana.fm "SolanaFM: site — lido em 12/09/2026, 02:21 BRT"
[R05]: https://docs.solana.fm/reference/solanafm-api-overview "SolanaFM: API — lido em 12/09/2026, 02:23 BRT"
[R06]: https://docs.solana.fm/reference/rate-limits-1 "SolanaFM: limites — lido em 12/09/2026, 02:23 BRT"
[R07]: https://bitquery.io/pricing "Bitquery: preços — lido em 12/09/2026, 02:21; releitura 02:23 BRT"
[R08]: https://docs.bitquery.io/docs/authorization/how-to-generate/ "Bitquery: autenticação — lido em 12/09/2026, 02:22 BRT"
[R09]: https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/ "Bitquery: pump.fun — lido em 12/09/2026, 02:25 BRT"
[R10]: https://docs.dune.com/learning/how-tos/pricing-faqs "Dune: preços/limites Free — lido em 12/09/2026, 02:23 BRT"
[R11]: https://docs.dune.com/api-reference/overview/authentication "Dune: autenticação — lido em 12/09/2026, 02:22 BRT"
[R12]: https://docs.dune.com/data-catalog/solana/overview "Dune: Solana — lido em 12/09/2026, 02:25 BRT"
[R13]: https://docs.dexscreener.com/api/reference "DEX Screener: API — lido em 12/09/2026, 02:21; releitura 02:25 BRT"
[R14]: https://docs.dexscreener.com/token-listing "DEX Screener: listagem — lido em 12/09/2026, 02:22 BRT"
[R15]: https://info.dextools.io/discover-all-our-plans-full-defi-power-at-your-fingertips/ "DEXTools: planos públicos — lido em 12/09/2026, 02:24 BRT"
[R16]: https://developer.dextools.io "DEXTools: portal API — lido em 12/09/2026, 02:22 BRT"

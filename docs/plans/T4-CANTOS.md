# T4 — Cantos do pump.fun: incentivos, exposição e superfícies sociais

**Astra · A4.0g · 12/09/2026 · papel documentation-writer.** Pesquisa somente leitura, sem login, interação social ou transação. As referências S01–S26, incluindo S24b, ligam URLs abertas à hora de consulta em Brasília (UTC−03); o registro de acesso, falhas e verificação está em [notes-A4.0g](../../.claude/state/notes-A4.0g.md). Horário de consulta não é data de lançamento nem garantia de frescor do conteúdo indexado.

Este complemento trata do comportamento de produto. Não substitui os mapas T4.0c/d/e/f nem o adendo Mayhem. **D** = documentado pelo responsável; **O** = observado numa resposta pública; **E** = texto/estrutura em JavaScript público, sem confirmar funcionamento; **NC** = não confirmado, nunca sinônimo de inexistente. Consequências para o radar e hipóteses abaixo são propostas, não funcionalidades entregues nem resultados de estratégia.

## 1. Recompensas do criador: receber não exige continuar comprado

**D — como e quando:** o guia oficial de 12/02/2026 descreve remuneração por negociação e valores imediatamente reclamáveis pelo destinatário. Considera a compra/manutenção de tokens uma decisão separada e opcional. O próprio guia atribui valor social ao ato de reclamar taxas; isso é interpretação promocional do emissor, não prova de compromisso do desenvolvedor. [S02]

**D — quem recebe:** a documentação técnica distingue destinatário único de distribuição compartilhada. Há cofres separados da curva e do AMM; a coleta é permissionless, mas paga ao destinatário definido, não ao chamador. Com compartilhamento, usa-se outro fluxo de distribuição. Portanto, uma transação de coleta iniciada por terceiros não demonstra que o criador decidiu sacar naquele instante. [S03]

**D — mudança de regra:** o guia de fevereiro descrevia edição, transferência e revogação de administração. O anúncio oficial de **24/03/2026 16:20:05Z** diz que a distribuição fica travada após a primeira configuração, inclusive as configurações anteriores. A documentação V2 atual confirma atualização única com revogação do admin. A data do anúncio foi extraída do HTML do canal; não é medição do slot de ativação. Não reutilizar o guia antigo como contrato vigente de edição. [S02], [S04], [S05]

**Inferência para compra cedo:** receber parte do fluxo pode financiar continuidade sem vender estoque, mas também pode incentivar giro sem crescimento de compradores. Vendas igualmente geram taxas. Não inferir retenção de supply a partir de receita; separar criador original, beneficiários atuais, percentual efetivo, geração, distribuição e vendas confirmadas. O saldo de um cofre por criador pode agregar moedas: não atribuir todo saque a um único mint. **M-P6** testa associação, não honestidade. [S01], [S02], [S03]

**Canto adicional:** o canal oficial documenta cashback, que pode redirecionar a parcela do criador ao usuário conforme configuração e contas da transação. Não presumir que toda taxa chamada “creator fee” terminou no bolso do deployer; registrar destino efetivo. Não descontar cashback futuro do custo já pago. [S05]

## 2. King of the hill, início e trending

**O — superfície atual:** `/board` redirecionou para `/explore`, cuja resposta trouxe Movers, Mayhem, New, Charities, Live, Market cap, Agents, Oldest e Last trade. A página inicial abriu a estrutura de navegação, sem uma regra de ranking legível. [S06], [S07]

**NC — regras e duração:** não obtive especificação oficial vigente de KOTH: limiar, desempate, elegibilidade, prazo da coroa, fórmula de Movers/trending e efeito exato de compra/reply continuam desconhecidos. A tentativa de `/docs/king-of-the-hill` falhou. Não promover alegações de vendedores de “bump bots” a algoritmo do pump.fun. Nem tratar um token chamado KOTH como o estado da plataforma. [S07], [S23]

**Proposta de observação:** salvar superfície, aba, filtros, posição, URL, idioma, contexto anônimo e instante. “Last trade” e “Market cap” são rótulos observados, não prova de fórmula, direção ou janela. Medir permanência como intervalo entre observações; um desaparecimento durante falha da coleta é censura, não fim comprovado da exposição. KOTH deve ficar `null/source_not_observed` até haver fonte verificável. **M-P7** usa primeira exposição observada e covariáveis anteriores; não inventa a primeira exposição real. [S06]

## 3. Livestreams

**D — quem e botão:** o tutorial oficial de **22/06/2025** exige criar o próprio token e orienta abrir sua página para iniciar a transmissão. Ele descreve o botão Start Livestream e ajustes RTMP no aplicativo. Não publica limiar de market cap, número mínimo de holders ou necessidade de graduar. Isso não prova que qualquer conta veja o botão hoje; não testei sessão autenticada nem gerei credencial. [S08]

**D — política:** a central de ajuda, datada de **18/05/2025**, restringe transmissão, audiência e chat a adultos e prevê remoção/suspensão por violações. A página do site também prevê moderação e diz que pode guardar cópias por até 30 dias, sem obrigação de fornecer arquivo e com possibilidade de alterar o prazo. Logo, o radar não pode depender de replay público durável. [S09], [S10]

**O/NC — descoberta e volume:** `/live` abriu uma listagem pública. Não localizei, nas políticas, tutorial e blog oficial consultados, uma estimativa quantitativa documentada de correlação livestream→volume. Não há multiplicador de volume adotado neste mapa. A visibilidade de uma live não mede audiência humana única nem conversão em compras. [S08], [S09], [S10], [S11], [S24]

**Inferência:** uma live pode concentrar atenção enquanto há preço em movimento; o movimento também pode atrair a live. **M-P8** compara volume posterior usando presença observada em marco fixo, controlando atividade anterior. Registrar começo/fim observados, audiência apenas quando fornecida e estados distintos para offline, removido, falha e desconhecido. Não rotular silêncio como abandono do criador.

## 4. Replies, comentários e “Alimentação X”

**D — comentários:** a política DMCA reconhece comentários como conteúdo que pode ser retirado do site. Não consegui carregar a página individual de moeda usada na tentativa de leitura de chat. Contagem vigente, paginação, regras de replies e API contratual de comentários não ficaram comprovadas nesta rodada. [S12], [S23]

**E — X/contas monitoradas:** o bundle público do **Terminal** contém widget TwitterTracker, ações de acompanhar/deixar de acompanhar contas e configuração de botão de lançamento no X Feed. Há prefixo interno `/twitter/`; isso não documenta um endpoint anônimo, quota ou API suportada. O chunk do widget contém filtros e apresentação flutuante/acoplada. Nenhuma rota autenticada foi chamada. [S13], [S14]

**NC — escolha das contas:** os textos indicam configuração pelo usuário no Terminal, mas não comprovam lista padrão, seleção editorial, contas recomendadas, cobertura total do X ou algoritmo de ordenação. Não confirmei que o rótulo português “Alimentação X” no pump.fun principal corresponda exatamente ao mesmo feed. Um link social no metadata do token, replies locais e posts recebidos por um tracker são três fontes distintas. [S07], [S13], [S14]

**Proposta:** registrar somente observações públicas autorizadas, com identificador/URL da publicação, tipo, relação explícita com mint, horários publicado/observado/disponível, versão da lista monitorada e completude. Não copiar mensagens privadas. Se só houver total de replies, não fabricar autores, sentimento ou velocidade histórica. **M-P9** trata comentários; **M-P10**, exposição no X. Ambas dependem de provar primeiro a cobertura de leitura.

## 5. Mecânicas que mudam o contexto da compra cedo

### Project Ascend

**Histórico, não regra de custo atual:** o espelho do anúncio de **02/09/2025** apresenta Ascend como sequência de mudanças e promete maior remuneração por taxas dinâmicas e processamento mais rápido de solicitações de community takeover (CTO). O anúncio original no X não abriu; a data é corroborada pela notícia de 03/09 que aponta o anúncio no dia anterior. As promessas de “10×” não são medição independente. [S15], [S16]

**Inferência:** benefício econômico e narrativa de comunidade podem sobreviver à venda pelo deployer se outros destinatários passarem a receber. Registrar cronologia e evidência da atribuição de taxas; não usar “CTO” como sinônimo de transferência total de controle do token. Testar **M-P6** por beneficiário/regra vigente, sem misturar antes/depois de Ascend como experimento causal.

### Tokenized agents

**D — o que é:** configuração voluntária para automatizar recompra e queima com recursos de um endereço de recebimento; não constitui, por si, uma IA autônoma. O criador define percentual alterável; o disclaimer descreve cadência horária, sem garantir futuras recompras. Depósitos inicialmente aceitos incluem SOL, USDC, USDT e USD1. Ser holder não confere direito a esses recebimentos. **Data:** anúncio técnico em **13/03/2026 15:41:17Z**, extraído do canal; disclaimer sem data editorial visível. [S05], [S17]

**Inferência:** entrada externa de recursos pode criar demanda diferente de negociação entre traders; depósito não prova receita comercial nem execução da recompra. **M-P11:** comparar política habilitada no marco inicial com desfecho futuro, guardando percentual, alterações e recompras efetivamente confirmadas como eventos separados. Não confundir esse mecanismo com Mayhem nem com buyback do token $PUMP.

### Go.fun

**D — o que é/data:** ferramentas para criar, financiar e avaliar bounties/grants; termos atualizados em **13/05/2026**, o que não prova lançamento nessa data. O espelho do anúncio mostra **4 de junho**, sem ano explícito no trecho; não preencher esse ano por suposição. O histórico do app registra inclusão de bounties na versão 16.0.0, em 12 de junho, também sem ano explícito nesse trecho. [S15], [S18], [S22]

**Inferência:** recompensa por divulgação ou entrega pode produzir atividade incentivada. Registrar bounty, moeda ligada explicitamente, orçamento, janela e estado aberto/pago/reembolsado; não chamar recompensa anunciada de pagamento nem anúncio de produto entregue. **M-P12** compara compradores futuros após exposição ao incentivo; não executa tarefas, não financia bounties.

### Charity coins

**D — o que é/data:** disclaimer atualizado em **27/04/2026**: integração com Donate.gg para encaminhar taxas do criador a organizações; o serviço externo seleciona/processa beneficiários. O pump.fun declara não auditar essas instituições. O texto descreve encaminhamento em SOL e possíveis custos externos; não estabelece percentual líquido universal que chega à instituição. [S19]

**Inferência:** selo tem significado de destinação declarada, não de segurança do token. Guardar escolha, destinatário e comprovante de encaminhamento separadamente de recebimento final da doação. Não extrapolar o texto de abril para uma conversão USDC não demonstrada. **M-P13** testa composição/comportamento, sem chamar não-charity de pior ou charity de seguro.

### PumpSwap: pools canônicos, taxas por faixa e USDC

**D — tabela vigente consultada:** atualização **20/05/2026**; pares USDC indicados a partir de **21/05/2026**. Curva: 1,25% por trade, sendo 0,30% do criador e 0,95% do protocolo. Pool canônico é o associado à moeda lançada e graduada; sua faixa usa preço na quote × **1 bilhão**, segundo a página. Pools não canônicos: 0,30% total, sem parcela de criador. Exemplos de faixas abaixo; tabela integral na fonte, sem interpolar limites. [S01]

| Pool/quote e market cap publicado | Criador | Protocolo | LP | Total |
| --- | --- | --- | --- | --- |
| Canônico SOL, 0–420 | 0,300% | 0,930% | 0,020% | 1,250% |
| Canônico SOL, 420–1470 | 0,950% | 0,050% | 0,200% | 1,200% |
| Canônico SOL, ≥98240 | 0,050% | 0,050% | 0,200% | 0,300% |
| Canônico USDC, 0–59000 | 0,300% | 0,930% | 0,020% | 1,250% |
| Canônico USDC, 59000–300000 (três faixas iguais) | 0,950% | 0,050% | 0,200% | 1,200% |
| Canônico USDC, ≥20000000 | 0,050% | 0,050% | 0,200% | 0,300% |

As taxas dos contratos prevalecem sobre a interface e podem mudar. Há ressalva de acréscimo de até 0,1% para alguns usuários/transações mobile. Gas e custos de terceiros ficam fora. [S01]

**Inferência para compra cedo:** não converter limites SOL em USD fixos nem aplicar taxa canônica a todo pool do mint. No limite compartilhado entre duas faixas impressas, a página não resolve inclusividade: usar regra/resultado do contrato. Registrar quote, pool, evidência de canonicidade, market cap de referência, faixa e parcelas efetivamente cobradas nas duas pontas. A fórmula publicada com 1 bilhão não autoriza assumir supply econômico constante para todo mecanismo. **M-P14** mede quote/custos; não concede edge por USDC ser stablecoin.

## 6. Aplicativo mobile e Terminal (ex-Padre)

| Superfície | Evidência e exclusividade que podemos afirmar | Consequência proposta |
| --- | --- | --- |
| App: descoberta social | App Store anuncia narrativas, memes negociados, seguir callers/amigos e leaderboard; não fornece fórmula de ranking. O espelho de 13/03/2025 anunciava DMs/grupos **exclusivos do app naquele lançamento**; exclusividade atual NC. [S15], [S22] | Não preencher influência privada com volume on-chain nem coletar DMs; comunidade observável incompleta |
| App: token off-chain | Ajuda de 06/02/2026: primeiro buy torna moeda pesquisável/on-chain; rótulo “offchain” pode permanecer por origem mesmo depois disso. [S20] | Rótulo não basta para concluir que não existe on-chain; separar cadastro, criação finalizada e primeiro trade; **M-P16** |
| App: transmissão | Tutorial mostra configuração RTMP no mobile; isso não prova exclusividade da live, que tem página web pública. [S08], [S11] | Registrar canal/interface; não usar chave de stream como dado do radar |
| Terminal: telas avançadas | `docs.padre.gg` retornou 403 no leitor e redirecionou para uma casca do Terminal no GET local; não valido recursos só pelo índice antigo da busca. Bundle comprova textos de tracker e lançamento a partir de feed, apenas **E**. [S13], [S14], [S21] | Nenhuma promessa de acesso exclusivo, velocidade, taxa ou automação operacional; integração não entregue |
| Disponibilidade por cliente | Não foi feita matriz autenticada web/app/Terminal. Função presente num bundle não prova liberação a todos. [S13], [S21] | `client_surface`, versão e elegibilidade desconhecida; não inferir que o resto do mercado viu a mesma tela |

## 7. Calendário e ritmo: o que a leitura permite dizer

**Fonte publicada, não medição nossa:** o exemplo Bitquery, snapshot de **23/04/2026**, informa pico às **20:00 UTC** no dia anterior (2.698) e **11:00 UTC** no dia parcial (1.736), interpretando concentração em 15:00–22:00 UTC. O pedido documentado conta tokens distintos que **negociaram**, embora o título fale em lançamentos. São 36 horas de exemplo: não provam distribuição de todas as criações nem sazonalidade persistente. Não converter essa janela em filtro de entrada. [S24b]

**O — leitura própria Mayhem, 12/09/2026 02:42:47 BRT:** [overview HTTP](https://frontend-api-v3.pump.fun/mayhem/overview) respondeu 200. Projeção da resposta (campos omitidos não são nulos):

```json
{"activeCoins":64,"coinsCreated":{"24h":10774,"7d":59644},"coinsCreatedByMode":{"auto":{"24h":8579,"7d":46576},"manual":{"24h":2195,"7d":13068}},"updatedAt":1789191117629}
```

`updatedAt` convertido = **2026-09-12 05:31:57.629Z**, cerca de 10 min 50 s antes da consulta. Não confundir horário do cache com horário da leitura. O painel `/mayhem` oferece janelas 24 h/7 d e classificações de moedas/traders; `/mayhem/overview` no domínio do site entregou só estrutura HTML. O JSON veio do domínio **frontend-api-v3**, não dessa rota web. [S25], [S26]

**Leitura, condicionada à semântica dos contadores:** 10.774 ÷ (59.644/7) = **1,2645×** a média diária da janela de 7 d. Como as janelas se sobrepõem, comparação não sobreposta seria 10.774 ÷ ((59.644−10.774)/6) = **1,3228×**, se ambas tiverem mesma população e fechamento. Uma amostra não valida isso nem comprova aceleração sustentada. Contagens Mayhem não são todas as criações pump.fun; `activeCoins` é estoque, não taxa. Não subtrair snapshots rolantes como se a diferença fosse apenas novas criações. [S25]

**Proposta M-P15:** contar criações finalizadas distintas por hora UTC/dia da semana numa janela futura congelada, com exposição e cobertura; separar quote/modo. Só depois estimar recorrência. A seleção de ganhadores 24 h/7 d não estima a probabilidade de ganho da coorte inteira. Não reabrir H-P28: Mayhem entra como estrato, não hipótese nova de superioridade.

## 8. O que uma API pública não resolve — e como declarar nulo

Não foi provado que nenhuma API do mundo expõe essas superfícies. O limite preciso é: **não obtivemos contrato público/observação suficiente nas fontes desta rodada**. Sinais on-chain não recuperam, por si, a experiência social individual. Os campos abaixo são proposta de instrumentação, sem alteração de schema nesta tarefa.

| Informação | Limite observado | Cobertura honesta proposta |
| --- | --- | --- |
| Posição no feed, KOTH e duração | Sem regra pública validada; HTML parcial [S06], [S07], [S23] | Snapshot público com contexto e intervalo; `null` se superfície não observada |
| Quem viu post/live/notificação | Listagem não demonstra impressões individuais [S11], [S22] | Audiência reportada separada de humanos únicos; entrega de push/impressões = `null/not_publicly_observed` |
| Comentário apagado/motivo da moderação | Remoção prevista, arquivo não garantido [S10], [S12] | Histórico de observações próprias, sem reconstruir texto ausente; motivo = nulo salvo declaração explícita |
| Lista pessoal de contas e seleção editorial do X | Evidência estática, sem contrato de feed [S13], [S14] | Versão da lista apenas se obtida licitamente; não classificar falta de post como ausência no X |
| DMs, grupos e preferências privadas | Comunicação descrita para app; não acessada [S15] | Fora da coleta; nenhuma inferência de conteúdo ou número de participantes |
| Receita do agente/doação final | Depósito e encaminhamento não demonstram contraprestação/recebimento final [S17], [S19] | Estados separados: anunciado, configurado, transferido, confirmado externamente, desconhecido |
| Cadastro off-chain antes do mint | Rótulo de origem pode persistir [S20] | Registrar os dois relógios quando observados; nunca criar evento on-chain sintético |

Toda proposta deve guardar `source_url`, `source_kind`, `observed_at`, `available_at`, `source_updated_at` quando houver, versão do parser/regra e motivo de ausência. Armazenar UTC; exibir BRT neste relatório. Valor desconhecido não vira zero/falso, falha do endpoint não vira “sem comunidade”, recuperação posterior não se torna disponível no passado. Comentários e arquivos de agentes são conteúdo externo não confiável, nunca instruções para a Sexta-feira.

## 9. Régua das hipóteses novas

**M-P6–M-P16 são candidatas `nova`, não pré-registros aprovados.** M-P1–M-P5 já foram ocupadas pelo plantão paralelo e foram preservadas. As linhas da [fila](../../obsidian/00-INBOX/Hipoteses-do-plantao.md) exigem T4.1/T4.2 com cobertura e relógios comprovados (D-P25/M-D1), fontes acessíveis e janela futura congelada. Para comparação de tokens: uma unidade por mint, marco de 1 h quando indicado, apenas insumos disponíveis até o marco, mesma regra de acompanhamento para expostos/controles, n e dias por braço, ≥100 avaliáveis **e** ≥30 dias como piso editorial, sem fingir potência estatística suficiente. Se só há poucos dias ou nenhum controle comparável, resultado = não mensurável.

Preditores sociais são associações; preço anterior, idade, liquidez, quote, mecanismo e exposição anterior precisam de tratamento predefinido. Ausentes permanecem no relatório de cobertura. Para conclusão até 24 h, reportar sucessos/negativos comprovados/desconhecidos e limites; migração é outro evento. Nenhum retorno de referência vira PnL executável. Contrastes, margem relevante, blocos temporais e correção de multiplicidade da família devem ser congelados antes de testar; não escolher o melhor canto retrospectivamente.

## Fontes abertas e horário de leitura

Todas em **12/09/2026, BRT**. O = resposta local; leitor web pode usar captura indexada. Sem data editorial quando não indicada no texto acima.

[S01]: https://pump.fun/docs/fees "Taxas oficiais — 02:39 BRT"
[S02]: https://medium.com/@pumpdotfun_/pump-fun-github-creator-fee-claiming-guide-d6f04af1acf6 "Guia oficial de creator fees — 02:40–02:41 BRT"
[S03]: https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/instructions/COLLECT_CREATOR_FEE.md "Coleta, documentação oficial — 02:43–02:44 BRT"
[S04]: https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/instructions/CREATOR_FEE_SHARING.md "Distribuição V2, documentação oficial — 02:43–02:44 BRT"
[S05]: https://t.me/s/pump_tech_updates "Canal oficial: sharing/cashback/agents — 02:40–02:43 BRT; datas HTML 02:43"
[S06]: https://pump.fun/board "Redirecionou a /explore; abas visíveis — 02:41 BRT"
[S07]: https://pump.fun/ "Início, estrutura pública — 02:40 BRT"
[S08]: https://intercom.help/pumpfun-web/en/articles/11638371-how-to-get-rtmp-key-mobile "Tutorial mobile de transmissão — 02:40 BRT"
[S09]: https://intercom.help/pumpfun-web/en/articles/11399886-livestream-moderation-policy "Política da central oficial — 02:43 BRT"
[S10]: https://pump.fun/docs/livestream-moderation-policy "Política do site — 02:39–02:40 BRT"
[S11]: https://pump.fun/live "Listagem pública de lives — 02:42 BRT"
[S12]: https://pump.fun/docs/dmca-policy "Conteúdo removível e comentários — 02:43 BRT"
[S13]: https://terminal.pump.fun/assets/index-DKS5eDgr.js "Bundle público, evidência estática — 02:42:47 e 02:43 BRT"
[S14]: https://terminal.pump.fun/assets/index-Choz2jFk.js "Widget TwitterTracker, evidência estática — 02:43:42–02:43:56 BRT"
[S15]: https://threadreaderapp.com/user/Pumpfun "Espelho de anúncios: Ascend, GO, DMs — 02:41–02:42 BRT"
[S16]: https://blockworks.com/news/pumpdotfun-fee-model "Fonte secundária para cronologia Ascend — 02:41 BRT; X vinculado não abriu"
[S17]: https://pump.fun/docs/tokenized-agent-disclaimer "403 no leitor; GET local 200 e texto lido às 02:42:10 BRT"
[S18]: https://pump.fun/docs/go-fun-terms "Definição GO e data dos termos — 02:40 BRT"
[S19]: https://pump.fun/docs/charitycoins "403 no leitor; GET local 200 às 02:42; data reconferida 02:42:50 BRT"
[S20]: https://intercom.help/pumpfun-web/en/articles/11519827-coin-isn-t-showing-when-i-search-on-the-mobile-app "Rótulo offchain e primeiro buy — 02:40–02:41 BRT"
[S21]: https://docs.padre.gg/ "403 no leitor; GET local redirecionou a trade.padre.gg às 02:41:46 BRT, só título"
[S22]: https://apps.apple.com/us/app/pump-fun/id6717572591 "App Store, descrição e histórico — 02:44 BRT"
[S23]: ../../.claude/state/notes-A4.0g.md "Registro das URLs tentadas sem conteúdo; não são fontes positivas"
[S24]: https://medium.com/@pumpdotfun_ "Índice do blog oficial consultado — 02:39–02:40 BRT"
[S24b]: https://docs.bitquery.io/docs/mcp/trading/examples/pumpfun-launch-pulse/ "Exemplo do fornecedor, snapshot 23/04/2026 — 02:41 BRT"
[S25]: https://frontend-api-v3.pump.fun/mayhem/overview "HTTP 200, projeção numérica — 02:42:47 BRT"
[S26]: https://pump.fun/mayhem "UI Mayhem, 24h/7d — 02:40 BRT"

## Canto → fonte → o que o radar precisa gravar → hipótese M-P a pré-registrar

| Canto | Fonte aberta (horas acima) | O que o radar precisa gravar — proposta | Hipótese candidata |
| --- | --- | --- | --- |
| Recompensas, sharing, cashback e Ascend | [S01], [S02], [S03], [S04], [S05], [S15] | Criador original, beneficiário e share no marco; taxas geradas/distribuídas; cashback; vendas efetivas; versão da regra | **M-P6:** maior parcela destinada ao criador associa-se a menor venda posterior do seu estoque |
| KOTH, home e trending | [S06], [S07] | Superfície, posição, filtros, primeira exposição observada, intervalos de cobertura; KOTH nulo enquanto NC | **M-P7:** exposição pública observada associa-se a mais compradores novos nos 30 min seguintes |
| Livestream | [S08], [S09], [S10], [S11] | Estado no marco de 1 h, audiência reportada, remoção/falha distintas, volume anterior e posterior | **M-P8:** live observada em 1 h associa-se a maior volume de 1–2 h |
| Replies/comentários | [S12] | Contagem/autores somente se observados, paginação/cobertura, timestamps; removidos desconhecidos | **M-P9:** intensidade pública de comentários em 0–1 h associa-se a conclusão até 24 h |
| Alimentação X/contas monitoradas | [S13], [S14] | Lista versionada quando acessível, post/mint explícitos, publicado/observado, fonte e cobertura | **M-P10:** menção observada no X associa-se a mais compradores novos nos 30 min seguintes |
| Tokenized agents | [S05], [S17] | Habilitação e percentual no marco, mudanças, depósitos e recompras/queimas confirmadas separados | **M-P11:** política habilitada em 1 h associa-se a maior fluxo líquido de compras em 1–24 h |
| GO/bounties | [S15], [S18], [S22] | Recompensa anunciada, mint explícito, janela, estado pago/reembolsado, instante disponível | **M-P12:** bounty aberto em 1 h associa-se a mais compradores novos em 1–24 h |
| Charity | [S19] | Destinação configurada em 1 h, evidência do destinatário, encaminhamento e recebimento final distintos | **M-P13:** charity em 1 h associa-se a menor venda posterior do criador |
| Canonicidade, faixa de taxa, SOL/USDC | [S01] | Pool/quote, canonicidade verificada, faixa e custos executáveis por notional, sem taxa fixa em USD | **M-P14:** quote USDC versus SOL associa-se a diferença no custo cotado de ida e volta em 1 h |
| Calendário e janelas Mayhem | [S24b], [S25], [S26] | Criação finalizada, hora UTC, exposição/cobertura; contadores rolantes com updatedAt | **M-P15:** intensidade de criações por hora é maior em [15,23) UTC, em janela futura |
| Mobile/Terminal e cadastro off-chain | [S08], [S13], [S14], [S20], [S21], [S22] | Origem do rótulo, cadastro observado, criação e primeiro trade finalizados; cliente/versão | **M-P16:** rótulo offchain não classifica com fidelidade a ausência atual de criação on-chain; instrumento, sem edge |

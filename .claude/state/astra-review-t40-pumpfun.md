**RESUMO**
Recomendo o **Meme Radar como observatório e arquivo para replay**. “Comprar cedo e vender em ROI alto” ainda precisa de tamanho, entrada, saída e custos pré-registrados.
Papel: `quant-engineer`; modo OPINIÃO. **Fontes abaixo abertas em 12/09/2026**, salvo falhas indicadas. Duas premissas precisam mudar: trades do PumpPortal não aparecem mais como gratuitos; taxa total publicada da curva é **1,25%**.

**ARQUIVOS**
Nenhum criado ou modificado; nenhum commit.

**TESTES**
Não executei testes, consultas históricas nem conexão WS. Conferi documentação e código por leitura. Cálculo PowerShell com `[decimal]`, `30*1073000000/(1073000000-793100000)-30`, retornou `85,0053590568060021436227224`; isso deriva parâmetros documentados, não verifica o estado atual da cadeia.

**MUST-FIX**

- **Fontes — corrigir o orçamento antes do coletor:** usaria [PumpPortal WS](https://pumpportal.fun/data-api/real-time/) para descoberta: `subscribeNewToken` e `subscribeMigration` são gratuitos. Trades por token/carteira custam **0,01 SOL/10.000 eventos**, exigem chave e carteira com pelo menos **0,02 SOL**. A página pede conexão única; não comprova acesso sem chave aos canais gratuitos. Cenário: projetar tape gratuito resulta em coleta ausente ou cobrança.
- **Frontend-api:** apenas enriquecimento dispensável de metadados. A abertura de `https://frontend-api-v3.pump.fun/` falhou; não validei endpoints, limites ou SLA. Não usaria como registro canônico nem presumiria estabilidade.
- **RPC público Solana:** conferência de reservas, transações e protótipo limitado. A [documentação](https://solana.com/docs/references/clusters) publica 100 requisições/10 s/IP, 40 por método/10 s, sujeitos a mudança, 429/403 e recomenda RPC privado em produção. Cenário: queda durante um lançamento apaga justamente compras iniciais; lacuna precisa ficar explícita.
- **Helius/QuickNode:** minha preferência para coleta contínua seria RPC dedicado com reconciliação histórica, escolhido após medir cobertura e atraso. [Helius](https://www.helius.dev/docs/billing/plans) tem plano gratuito de 10 RPC/s e créditos limitados; streaming avançado depende do plano. [QuickNode](https://www.quicknode.com/docs/solana) documenta RPC/WS e arquivo Mainnet; não confirmei sua quota/preço. Chaves e contratação ficam com Everton.
- **Bitquery/Dune:** [Bitquery](https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/) para histórico e streaming decodificado, com token, quotas e diferenças de campos entre `realtime` e `combined`; [Dune](https://docs.dune.com/data-catalog/solana/overview) para coortes, transações e auditoria em lote. Não medi completude/latência de nenhum. Cenário: campo disponível ao vivo mas ausente no histórico inviabiliza replay comparável.

- **Curva — distinguir cotação de fill:** para reservas virtuais normalizadas `x` tokens e `y` SOL, `k=x·y`; preço marginal `p=y/x` SOL/token. Compra de `q` tokens custa, antes das taxas, `ΔSOL=k/(x−q)−y`; venda recebe `y−k/(x+q)`. Fill exige reservas reais suficientes, arredondamento inteiro e regras da versão do programa. Derivação da [documentação oficial](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md).
- **Graduação:** o critério documentado é `real_token_reserves=0` e `complete=true`; migração para PumpSwap é evento separado. Os parâmetros publicados — 30 SOL virtuais, 1.073 milhões de tokens virtuais e 793,1 milhões reais — implicam **≈85,005359 SOL líquidos acumulados**, antes de descontar migração. **Não confirmei esse valor como limiar vigente on-chain em 12/09**: configuração é atualizável. Não confundir com volume bruto ou market cap. [Fonte oficial](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md).
- **Custos:** a [página oficial de taxas](https://pump.fun/docs/fees), atualizada em **20/05/2026**, publica **1,25% por trade na curva**, incluindo creator fee; também admite pares USDC. Somar entrada e saída, [taxa de rede e priority fee](https://solana.com/docs/core/fees), eventual intermediário/Jito, transações falhadas e impacto/slippage dependente do tamanho. Cenário: testar com “1% total” transforma lucro bruto em falso lucro líquido.

As **cinco features propostas são hipóteses**, medidas somente com informação disponível na decisão; nenhuma certifica token seguro:

| Feature por token | Medida e teste específico no replay |
|---|---|
| Bundlers | Fração comprada por clusters de financiamento comum e compras coordenadas por slot; comparar filtro versus controle e sensibilidade ao agrupamento. Mesmo slot sozinho não prova bundle. |
| Dev vendeu | Venda acumulada/posição do criador e carteiras vinculadas, separando transferência de venda; testar veto somente após evidência disponível, sem usar rótulos descobertos depois. |
| Concentração | Participação top-10 e HHI por proprietário/cluster, excluindo curva, pool e burn; testar redução da cauda de perdas e quanto retorno o filtro sacrifica. |
| Compradores únicos | Novos compradores e compradores líquidos por janela, com versão por cluster; comparar com contagem bruta para detectar “crescimento” produzido por carteiras relacionadas. |
| Ritmo | Aceleração de compradores, fluxo líquido em SOL/USDC e avanço das reservas por segundo; testar persistência após atraso realista, removendo fluxo suspeito de wash trading. |

- **Funil comum às cinco:** pré-registrar direção, janela, limiar, tamanho, ROI-alvo, timeout, perdas e custos; uma candidata por dia, registrando todas as tentativas. Replay de lançamentos reais, inclusive mortos/não graduados; entradas congeladas; comparação incremental e estresse. Exigir **≥100 operações avaliáveis E ≥30 dias**, IC95% da expectancy líquida por **blocos de dia**, leave-one-token-out e 2/3 janelas de 30 dias positivas. Base: [decisão de 10/09:28](C:/dev/project-hunter/obsidian/06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real.md:28).
- Julgar em um dia significa processar história existente; não fabricar 30 dias nem promover replay a prospectivo. Sem histórico granular, resultado é inconclusivo. O [funil:145](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:145) separa essas evidências; adaptar a exigência de [90 dias por mercado:197](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:197) para coortes de lançamentos requer decisão de desenho — aplicada literalmente, excluiria todos os tokens recém-criados.
- **Base rate:** não encontrei estimativa atual abrangente que possa chamar de probabilidade de graduação. O resumo do [preprint de Kamat, revisto em 17/08/2026](https://arxiv.org/abs/2607.02823) reporta **0,198%**, mas admite cobertura efetiva de aproximadamente seis minutos: é limite inferior da taxa em 24 h, não sua estimativa. Graduação tampouco equivale a lucro realizável.
- **Riscos para Everton:** sniping disputa inclusão/ordenação com bots e [leilões de bundles](https://docs.jito.wtf/lowlatencytxnsend/); comprar cedo pode significar fornecer saída aos primeiros. Dumps de insiders, rugs econômicos e volume falso podem sobreviver aos filtros; concentração pode ser escondida em várias carteiras. ROI mostrado não garante comprador para a posição inteira.
- **Risco SPOT não cobre execução on-chain:** o código exige LONG/SPOT em [checks.py:80](C:/dev/project-hunter/packages/risk-core/hunter_risk/checks.py:80) e livro de ofertas em [checks.py:259](C:/dev/project-hunter/packages/risk-core/hunter_risk/checks.py:259), conforme [contrato:233](C:/dev/project-hunter/docs/RISK_ENGINE.md:233). Cenário: disfarçar reservas como book aprova uma simulação sem modelar assinatura, blockhash, confirmação, MEV e migração; stop pode não executar.

**NICE-TO-HAVE**
Comparar provedores por assinaturas coincidentes, gaps recuperados, atraso evento→recebimento→disponibilidade e custo observado; escolher pelo ensaio, não pelo marketing.

**O QUE EU FARIA DIFERENTE**
Proporia este mínimo, ainda sem implementação:

| Tabela | Campos essenciais |
|---|---|
| `meme_tokens` | UUID; único `(chain,mint)`; creator e criador da transação separados; token program, decimals, supply, quote mint, curva, criação/slot, parâmetros iniciais, conclusão e migração separadas, pool destino e procedência. |
| `meme_trades` mensal | Token, tempo UTC, slot/blockhash, assinatura, índices de transação/instrução/evento, trader, lado, quantidades brutas, reservas, taxas, sucesso/finalidade, fonte, `received_at`, `available_at`, versão do decoder. |
| `meme_snapshots` por minuto | Token/minuto, reservas reais/virtuais, cinco features com denominadores, versão, cobertura, último slot e disponibilidade; desconhecido fica nulo com motivo. |

Acrescentaria **eventos brutos de transferências/estado e checkpoints/gaps**: trades sozinhos não reconstroem holders nem financiamento; snapshots de minuto não provam uma entrada em segundos. Dedupe deve distinguir várias instruções na mesma assinatura e respeitar a chave mensal; taxa de transação não pode ser somada novamente por cada trade.
Preservaria unidades atômicas inteiras e razão de reservas para evitar arredondar micropreços; valores financeiros em `Decimal/NUMERIC(28,10)`, UTC e dados públicos globais; configurações/carteiras por tenant com repository+RLS, conforme [DATABASE.md:9](C:/dev/project-hunter/docs/DATABASE.md:9).

**CONCORDO COM**
Monitorar primeiro e deixar T4.0 provar as fontes. Dinheiro real só após evidência líquida e contrato próprio de risco/execução on-chain aprovado por Everton.

**OBSIDIAN**
- **Meme Radar — fontes e protocolo** — criar nota com fontes datadas, cobrança atual, reservas e hipóteses.
- **Social e on-chain — a linha que não atravessamos** — registrar a nova intenção e os dados ainda necessários.
- **Risk Engine** — explicitar a fronteira entre SPOT com book e execução Solana.
- **Strategy Backlog / Registro de Tentativas** — registrar as cinco hipóteses e a candidata diária, sem declarar validação.
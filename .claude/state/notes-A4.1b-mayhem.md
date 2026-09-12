# A4.1b — Mayhem: pesquisa verificável e proposta, sem implementação

Data: 12/09/2026. Responsável: Astra, papel `documentation-writer`. Escopo: este arquivo e uma linha nova na Fila de hipóteses do plantão. Nenhum código, adapter, contrato, ativação ou commit nesta tarefa.

## 1. Método e relógio

Horários abaixo são de Brasília, calculados como UTC menos 3 horas. O relógio retornou `2026-09-12 04:59:59 UTC` = `12/09/2026 01:59:59 BRT`; nova leitura `05:01:48 UTC` = `02:01:48 BRT`. Intervalos de leitura são explicitamente intervalos, não timestamps exatos inventados. Todos os acessos foram públicos, sem chave ou sessão autenticada. Os comandos de rede usaram `timeout 290 curl -sS --max-time 4..40`; a verificação usa `timeout 290 uv run python infra/scripts/obsidian_lint.py`, em primeiro plano. A ferramenta devolveu sessões para acompanhar a saída; não houve lançamento intencional em background. As tentativas iniciais de curl com aspas atravessando PowerShell/Bash não produziram saída verificável; foram repetidas passando texto literal por stdin para Bash. Somente as repetições abaixo são evidência HTTP.

Nenhuma rajada chegou a 60 chamadas à frontend API em 60 s: foram cinco GETs úteis no total (listagem, dois detalhes, screener e overview), além das tentativas iniciais sem resultado verificável. RPC: três POSTs espaçados (`getSignaturesForAddress`, `getTransaction`, `getMultipleAccounts`), abaixo de 10 req/s. Downloads de HTML/JS/GitHub não foram chamadas à frontend API. Os dados de moedas abaixo são **projeções de respostas reais**, com identidade substituída por A/B; campos omitidos não são `null`. Endereços públicos de programas e a assinatura solicitada são mantidos para reprodução. Nenhum dado de cliente do Hunter foi consultado.

## 2. O que significa Manual — encontrado em fonte primária

**Manual significa que o criador solicita cada operação do agente; direção e tamanho continuam aleatórios.** Auto tem cadência autônoma estimulada pela atividade. A interface descreve `active` como agente operando, `paused` como liquidez/capitalização insuficiente e `ended` como encerramento. Fonte aberta: [screener oficial](https://pump.fun/mayhem), leitura em 12/09/2026 01:59–02:00 BRT, seções Auto, Manual e Agent states. Isso não significa que o criador escolhe compra/venda nem que o Hunter executa algo.

A [doc Mayhem](https://pump.fun/docs/mayhem-mode), aberta às 01:59–02:00 BRT, conserva a data editorial de 12/11/2025: elegibilidade na criação, operação nas primeiras 24 h, oferta adicional, queima posterior e carteira/programa públicos. Não explica Manual. Sua descrição antiga de disponibilidade na interface não deve substituir a interface atual. A doc também não comprova rentabilidade nem liquidez executável para qualquer tamanho de ordem.

Busca complementar, todas em 12/09/2026:

| Fonte aberta / tentativa | Leitura BRT | Resultado limitado ao material consultado |
|---|---|---|
| [Canal técnico](https://t.me/s/pump_tech_updates) | 02:00–02:01 | Abriu. Anuncia Mayhem/create_v2 e aponta os IDLs; busca textual por `manual` sem ocorrência na página carregada. Não foi feita varredura exaustiva de todo o histórico. |
| [Blog oficial, ligado pelo rodapé](https://medium.com/@pumpdotfun_) | 02:00–02:01 | Índice abriu; busca por Mayhem sem ocorrência. Não forneceu definição de Manual. |
| [Disclaimer](https://pump.fun/docs/mayhem-mode-disclaimer) | 02:02–02:03 | Abriu; não foi usado como contrato de campos ou instruções. |
| [Repositório oficial](https://github.com/pump-fun/pump-public-docs) | 01:59–02:01 | Abriu; investigação de IDL detalhada na seção 5. |
| Busca `site:pump.fun/docs/ "Mayhem" "manual"` e `site:github.com/pump-fun mayhem manual` | 02:00–02:03 | Não acrescentou explicação primária melhor que o screener; referências de terceiros não fundamentam esta nota. |
| Busca `site:x.com/pumpfun "Manual" "Mayhem"` | 02:00–02:03 | Nenhum snippet pertinente confirmado; não se abriu X nem se usaram respostas de Grok como evidência. |

## 3. API: nomes comprovados e duas amostras

**A listagem expôs `mayhem_state`; o detalhe de A também expôs `mayhem: {state, mode}`. Não apareceram `mayhem_mode`, `agent_status`, `mayhem_enabled` nem `is_mayhem_mode` nesses JSONs.** Esta constatação vale para as amostras, não prova ausência em todas as versões/endpoints. Fontes e leitura: os três GETs abaixo, 12/09/2026 02:00–02:02 BRT; todos `HTTP=200`.

```bash
timeout 290 curl -sS --max-time 40 -w '\nHTTP=%{http_code}\n' 'https://frontend-api-v3.pump.fun/coins?offset=0&limit=2&sort=created_timestamp&order=DESC&includeNsfw=false'
timeout 290 curl -sS --max-time 40 -w '\nHTTP=%{http_code}\n' 'https://frontend-api-v3.pump.fun/coins/5JcKYjeWj4zvgYUVjzWGRxM7RQm4oTGNymYqXv9kpump'
timeout 290 curl -sS --max-time 40 -w '\nHTTP=%{http_code}\n' 'https://frontend-api-v3.pump.fun/coins/BxCLAFdgtqARU6q4fGzovtE7L2iNUN8tRaytbvURpump'
```

URLs abertas: [listagem](https://frontend-api-v3.pump.fun/coins?offset=0&limit=2&sort=created_timestamp&order=DESC&includeNsfw=false), [detalhe A](https://frontend-api-v3.pump.fun/coins/5JcKYjeWj4zvgYUVjzWGRxM7RQm4oTGNymYqXv9kpump), [detalhe B](https://frontend-api-v3.pump.fun/coins/BxCLAFdgtqARU6q4fGzovtE7L2iNUN8tRaytbvURpump). Os mints são identificadores públicos de ativos, mantidos apenas nos URLs/comandos de reprodução.

Projeção anonimizada da **listagem real**, sem converter ausência em falso:

```json
[
  {"mint":"[A]","created_timestamp":1789189249000,"complete":false,"mayhem_state":"active","total_supply_str":"1000000000000000","base_decimals":6,"quote_decimals":9},
  {"mint":"[B]","created_timestamp":1789189245000,"complete":false,"total_supply_str":"1000000000000000","base_decimals":6,"quote_decimals":9}
]
```

Projeções anonimizadas dos **detalhes reais**, respectivamente Mayhem e não-Mayhem, classificação confirmada por RPC na seção 5:

```json
{"mint":"[A]","initialized":true,"created_timestamp":1789189249000,"complete":false,"virtual_sol_reserves":15589673266,"virtual_token_reserves":1059456997686755,"total_supply":1000000000000000,"real_sol_reserves":270525715,"real_token_reserves":779556997686755,"updated_at":1789189276,"program":"pump","mayhem_state":"active","quote_mint":"11111111111111111111111111111111","base_decimals":6,"quote_decimals":9,"is_cashback_enabled":false,"chain_id":"solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp","protocol":"pump","total_supply_str":"1000000000000000","virtual_quote_reserves":15589673266,"real_quote_reserves":270525715,"boost_mode":"NONE","mayhem":{"state":"active","mode":"manual"}}
```

```json
{"mint":"[B]","initialized":true,"created_timestamp":1789189245000,"complete":false,"virtual_sol_reserves":30844787025,"virtual_token_reserves":1043612328593202,"total_supply":1000000000000000,"real_sol_reserves":844787025,"real_token_reserves":763712328593202,"updated_at":1789189270,"program":"pump","quote_mint":"11111111111111111111111111111111","base_decimals":6,"quote_decimals":9,"is_cashback_enabled":false,"chain_id":"solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp","protocol":"pump","total_supply_str":"1000000000000000","virtual_quote_reserves":30844787025,"real_quote_reserves":844787025,"boost_mode":"NONE"}
```

Os JSONs também continham identidade/metadados (`name`, `symbol`, `creator`, curvas, URLs), medidas de capitalização, e flags gerais; os detalhes incluíam `security_verdict`. Foram omitidos, não fabricados. `complete=false` é estado da curva, não estado do agente. O mesmo `total_supply_str` aparece em A e B: **não usar oferta da API para inferir Mayhem**. A ausência de `mayhem` em B só virou evidência negativa depois de ler o booleano on-chain. Fonte: URLs e horários desta seção; a regra de inferência é proposta desta pesquisa.

## 4. Endpoint do screener e acesso à página

**Existe endpoint próprio, público nesta leitura:** [GET /coins/mayhem-mode?limit=2&mayhemState=active](https://frontend-api-v3.pump.fun/coins/mayhem-mode?limit=2&mayhemState=active), `HTTP=200`, 12/09/2026 02:04–02:05 BRT. Retornou duas moedas com `mayhem_state:"active"`; não retornou o objeto `mayhem` aninhado nesses itens. Não é listagem completa nem população adequada para H-P28: selecionar só agentes ativos removeria controles e encerrados.

```bash
timeout 290 curl -sS --max-time 30 -w '\nHTTP=%{http_code}\n' 'https://frontend-api-v3.pump.fun/coins/mayhem-mode?limit=2&mayhemState=active'
timeout 290 curl -sS --max-time 30 -w '\nHTTP=%{http_code}\n' 'https://frontend-api-v3.pump.fun/mayhem/overview'
```

O [overview](https://frontend-api-v3.pump.fun/mayhem/overview) também respondeu `HTTP=200`, na mesma janela; projeção real:

```json
{"activeCoins":64,"coinsCreated":{"24h":10705,"7d":59615},"coinsCreatedByMode":{"auto":{"24h":8614,"7d":46639},"manual":{"24h":2091,"7d":12976}},"updatedAt":1789188394669}
```

Isto é um agregado do provedor, não nosso denominador validado. Não estabelece graduação ou retorno nem substitui histórico por mint.

**Como o endpoint foi encontrado:** HTML público de [pump.fun/mayhem](https://pump.fun/mayhem), scripts referenciados pelo HTML e curl direto. Página abriu sem desafio Cloudflare observado; novo GET confirmou `HTTP=200` às **02:05:13 BRT**. O extrator web mostrou algumas chaves de tradução cruas e, em outra leitura, estados `unavailable`; não apresentou uma captura de tráfego de navegador.

No [bundle da API](https://pump.fun/_next/static/chunks/0._.d6~ioidd~.js), lido 02:03–02:05 BRT, `CLIENT` aponta a frontend-api-v3, `MAYHEM_MODE_COINS` constrói `/coins/mayhem-mode` com `limit` padrão 60 e `mayhemState` opcional. No [bundle do screener](https://pump.fun/_next/static/chunks/0l60vh~c-l8_..js), lido 02:02–02:04 BRT, a aba `ended` mapeia para `completed`, enquanto `active` e `paused` conservam os nomes. Também há referências a `/mayhem/top-coins`, `/mayhem/top-traders` e stats no swap-api; esses endpoints **não foram chamados**. Os dois bundles podem mudar com deploy; não são contrato estável. Não houve DevTools/HAR ou execução autenticada; a comprovação é inspeção estática + GET real, não uma alegação de captura de rede do browser.

## 5. Identificação on-chain: IDL e operação real

Fonte primária aberta via curl, 12/09/2026 **02:01–02:04 BRT**: [IDL Pump](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump.json). Blob Git observado na [listagem oficial de IDLs](https://api.github.com/repos/pump-fun/pump-public-docs/contents/idl): `062e66f032bb9f295353b573be3400070bd55e5b`. Programa do IDL: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`.

| Elemento verificado no IDL | Utilidade proposta |
|---|---|
| `create_v2.is_mayhem_mode: bool`; `CreateEvent.is_mayhem_mode`; `BondingCurve.is_mayhem_mode` | Classificar a elegibilidade sem depender de ausência de campo HTTP. |
| `TradeEvent.user`, `mint`, `is_buy`, `timestamp`, `mayhem_mode`, `quote_amount`, `quote_mint` | A flag descreve o token; atribuição ao agente exige o usuário da operação. |
| `buy` e `sell`; `buy.user` na posição 6 (índice zero) | Resolver o trader da instrução, inclusive CPI. |
| `create_v2` referencia `mayhem_program_id`, `global_params`, `sol_vault`, `mayhem_state`, `mayhem_token_vault` | Integração com MAyh; não constitui um IDL completo desse outro programa. |

**IDL próprio de MAyh: não encontrado no repositório oficial consultado.** [Árvore recursiva](https://api.github.com/repos/pump-fun/pump-public-docs/git/trees/main?recursive=1), lida 02:02–02:03 BRT, não retornou caminho contendo mayhem. [Tentativa idl/mayhem.json](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/mayhem.json) retornou **HTTP 404** às 02:02–02:03 BRT; [histórico desse caminho](https://api.github.com/repos/pump-fun/pump-public-docs/commits?path=idl/mayhem.json&per_page=3) retornou `[]`. O [commit “Idl and type files for mayhem mode and create v2”](https://api.github.com/repos/pump-fun/pump-public-docs/commits/864c072f4c331354288232e73b88ae849215ce7b), aberto 02:03–02:04 BRT, altera pump/pump_amm JSON/TS, não fornece `mayhem.json`. A abertura de alguns desses URLs pelo web falhou com erro interno; curl resolveu o diagnóstico acima. Não se afirma que um IDL MAyh nunca existiu em outro lugar.

### 5.1 Duas curvas verificadas no RPC

Fonte aberta: [RPC público Solana](https://api.mainnet-beta.solana.com), POST `getMultipleAccounts`, **02:01–02:02 BRT**, `HTTP=200`, slot finalizado **446344893**. Contas das curvas vieram dos detalhes A/B. Ambos os owners são o programa Pump acima; ambos os discriminadores conferem com `BondingCurve` (`23,183,248,55,96,216,172,96`). Para este layout, offset de `is_mayhem_mode` = `8 + 5×8 + 1 + 32 = 81`; A retornou byte **1**, B byte **0**. Comprimentos: 124 e 151 bytes. Isso verifica o prefixo usado nesta leitura; não valida todos os campos de extensões nem autoriza parser sem versão/tamanho.

```bash
timeout 290 curl -sS --max-time 40 -w '\nHTTP=%{http_code}\n' -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":3,"method":"getMultipleAccounts","params":[["9AryiHuLxh13jGCm51dbq1zxUAVQ54HQEyWp8s68Mrzw","J1RGRGqy6KqdGjxzUrrHrXjN81VvQ3nEMUUZ7uSRxvq5"],{"encoding":"base64","commitment":"finalized"}]}' https://api.mainnet-beta.solana.com
```

### 5.2 Assinatura real: a carteira do agente não é o fee payer

Fonte aberta: [mesmo RPC público](https://api.mainnet-beta.solana.com), `getSignaturesForAddress` e depois `getTransaction`, **02:00–02:02 BRT**, ambos `HTTP=200`. Endereço consultado: `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`, publicado na [doc oficial](https://pump.fun/docs/mayhem-mode), lida 01:59–02:00 BRT.

```bash
timeout 290 curl -sS --max-time 40 -w '\nHTTP=%{http_code}\n' -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"getSignaturesForAddress","params":["BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s",{"limit":3,"commitment":"finalized"}]}' https://api.mainnet-beta.solana.com
timeout 290 curl -sS --max-time 40 -w '\nHTTP=%{http_code}\n' -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":2,"method":"getTransaction","params":["bkqmZbG6D8pxP23qnhCk4UZSzkR1iqgueYwf76rvaDLL9CiTyFZjcjsCLiZHso9nw4PGy7cML5wcdHopycsBvx7",{"encoding":"jsonParsed","commitment":"finalized","maxSupportedTransactionVersion":0}]}' https://api.mainnet-beta.solana.com
```

Assinatura real: `bkqmZbG6D8pxP23qnhCk4UZSzkR1iqgueYwf76rvaDLL9CiTyFZjcjsCLiZHso9nw4PGy7cML5wcdHopycsBvx7`. Retorno: `slot=446344722`, `blockTime=1789189244`, `err=null`, status finalizado na listagem. A instrução externa de índice **2** invoca `MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e`; logs registram `Instruction: Buy`. A primeira instrução interna desse grupo invoca Pump; sua conta `user` (índice 6) é a carteira publicada do agente. Transferência real: **75517799 lamports**, **14909435072866 unidades-base** de token com 6 decimais. Os balances confirmam o agente como dono da conta de tokens. Estes são dados desta operação, não estatística de performance.

Na mensagem, o agente é `signer:false`, `source:"lookupTable"`; outro endereço paga/assina a transação. **Cenário concreto de falha:** filtrar apenas o primeiro signatário/fee payer classificaria esta compra como orgânica. Igualmente, a mera presença da carteira em `accountKeys` não basta: uma transferência recebida não é uma compra do agente. A regra precisa decodificar a operação e sua autoridade econômica.

## 6. Proposta de esquema e regra orgânica — NÃO implementadas

Proposta elaborada em 12/09/2026 após as observações das seções 3–5, não afirmação de contrato existente. O adendo local pede identificação do agente (`docs/plans/T4-MEME-RADAR.md:420`); há pendências explícitas de identidade/procedência em `docs/plans/T4-MEME-RADAR.md:402`. Esta nota não aprova nem altera o desenho de T4.1/T4.2.

| Coluna proposta | Semântica e origem |
|---|---|
| `meme_tokens.mayhem_enabled BOOLEAN NULL` | True/false apenas com evidência válida de criação/curva; NULL = ainda desconhecido. Ausência de JSON nunca vira false. Reconciliar API com on-chain e preservar conflito. |
| `meme_tokens.mayhem_state TEXT NULL` | `active`, `paused`, `completed`, `unknown`; NULL = não aplicável quando enabled=false. Mapear `mayhem.state` e `mayhem_state`; divergência vira unknown e diagnóstico. Não inferir completed só por idade. |
| `meme_trades.is_mayhem_agent BOOLEAN NULL` | True quando o trader/autoridade da compra/venda decodificada é carteira oficial válida naquele instante; false somente após atribuição completa a outro trader; NULL para atribuição incompleta. |

`manual`/`auto` não cabem em `mayhem_state`: propor `mayhem_mode` separado, com unknown e preservação do valor cru. É uma extensão sugerida, sujeita ao desenho futuro. Sem separar os dois eixos, `manual + active` perderia informação.

Procedência mínima a acordar junto ao esquema: `source`, `observed_at`, `available_at`, slot/finalidade, versão/hash do IDL e da lista oficial de carteiras, valor cru relevante e motivo de desconhecido. Horários persistidos em UTC; BRT só nesta apresentação. Estado mutável precisa de histórico/snapshot: não retroaplicar o estado atual em pesquisa passada. Token global continua no domínio global; eventual dado por tenant conserva repository+RLS do contrato Hunter. Valores monetários em Decimal/NUMERIC(28,10); unidades-base preservadas em tipo inteiro apropriado, sem converter montantes via float.

Regra proposta de tagging: aceitar só transação bem-sucedida/finalizada, resolver contas estáticas + lookup tables, decodificar compras/vendas Pump ou PumpSwap e instruções internas, identificar `user`/autoridade por operação, comparar com registro oficial versionado. CPI MAyh é corroborante; só presença de MAyh ou `TradeEvent.mayhem_mode=true` não identifica o trader. Uma criação, burn, top-up ou transferência isolada não vira trade. Chave de deduplicação inclui chain + signature + índice externo + índice interno/evento; uma transação pode conter várias operações, mas CPI e log do mesmo fill contam uma vez.

Métricas orgânicas propostas usam **apenas `is_mayhem_agent IS FALSE`**, mesmo mint/janela/quote: volume = soma do notional dos fills elegíveis; compradores únicos = distinct trader das compras elegíveis; razão compra/venda usa contagens elegíveis (se versão por volume for desejada, nome separado). Denominador zero produz NULL com motivo, não infinito. True é excluído dessas três métricas; NULL é excluído do subconjunto conhecido e reportado como cobertura pendente. Com atribuição/gaps incompletos, o número deve ser rotulado parcial ou ficar indisponível, nunca volume orgânico integral. Excluir o agente não prova que os demais são humanos ou livres de wash trading. Preço observado ainda contém efeito do agente; remover seus fills não reconstrói preço contrafactual.

## 7. H-P28 — protocolo candidato pré-registrável

**Hipótese proposta, ainda não medida:** moedas criadas com Mayhem diferem das criadas sem Mayhem em (a) graduação até 7 dias e (b) retorno bruto de referência entre 24 h e 7 dias. Nulos bilaterais: `ΔG=0` e `ΔR=0`. Justificativa externa: mecanismos documentados nas seções 2–5 (URLs abertos e horários acima), não prova de vantagem. Não ativar estratégia nem concluir causalidade.

1. **Unidade e coorte:** um mint criado na pump.fun na janela prospectiva congelada antes da coleta, com modo determinado na criação e dados disponíveis naquele corte. Janela candidata = 60 dias consecutivos a partir do início comprovado da coleta; aguardar mais 7 dias para maturação. Comparação primária SOL-pareada; outras quotes ficam em estratos separados. Universo de criações, nunca só screener ativo, top-volume, sobreviventes ou graduados. Gap de descoberta é explicitado; sem universo completo, a inferência se limita à população observada.
2. **Denominador comum:** `N_g` = todas as criações maduras elegíveis do braço `g` (Mayhem/não-Mayhem), usado para ambos os desfechos. Mesma regra de inclusão, período e retenção; modos desconhecidos permanecem em estrato de cobertura, sem virar controles. Não restringir o braço Mayhem aos tokens efetivamente negociados pelo agente. Estados/mudanças Manual/Auto são estratificação secundária datada, sem reclassificar retrospectivamente o tratamento.
3. **Graduação:** `G_i=1` se a curva completar até `created_at+168h`, com evidência finalizada; guardar migração efetiva PumpSwap como segundo carimbo, sem confundir os dois eventos. `G_i=0` só com acompanhamento suficiente até o horizonte; gaps/censura = desconhecido. `G_g=sum(G_i)/N_g` quando determinado; com `U_g` desconhecidos, publicar limites `[sucessos/N_g,(sucessos+U_g)/N_g]`. Não converter desaparecimento da API em fracasso observado.
4. **Retorno:** `R_i=P_i(168h)/P_i(24h)-1` na mesma quote, bruto de referência, não PnL de carteira nem promessa de execução. Regra candidata de preço congelada = último preço de trade válido até o corte, com idade máxima de 60 s; acompanhar curva e pool após migração, sem usar o primeiro trade futuro para preencher lacuna. Preço ausente/stale/zero no denominador torna R desconhecido, não zero nem perda de 100%. Ausência de liquidez é reportada separadamente. Decimal em todo cálculo.
5. **Mesma retenção e honestidade do retorno:** reter tokens, trades/snapshots necessários, falhas e controles durante toda a janela de coleta + maturação + auditoria, com duração aprovada antes da coleta e idêntica nos braços, independente do resultado. A média-alvo usa todos os `N_g`; se algum R faltar, a média dos avaliáveis é apenas descritiva (`n_R/N_g` explícito), não estimativa identificada da média da coorte. Não preencher faltantes nem chamar a comparação condicional de teste com mesmo denominador; a conclusão primária de retorno fica inconclusiva sem cobertura ou modelo de missingness previamente justificado.
6. **Contraste e incerteza:** `ΔG=G_M−G_C` e `ΔR=mean(R_M)−mean(R_C)`; reportar cada braço, N, cobertura, dias, modos e versão do mecanismo. Blocos conjuntos de dia de criação com horizonte de dependência de pelo menos 7 dias; Holm para os dois desfechos primários. Exigir ≥100 observações avaliáveis e ≥30 dias distintos por braço como piso editorial, não garantia de poder. Sem precisão suficiente, inconclusivo. Congelar margem de equivalência antes da coleta se a intenção for concluir ausência de diferença; p não significativo sozinho não refuta a hipótese.
7. **Falhas plausíveis:** criadores selecionam Mayhem; Manual/Auto, seed liquidity, época e alterações do protocolo confundem a associação. Preços das 24 h podem carregar oferta/atividade injetada. Tokens sem preço aos 7 dias desaparecendo do cálculo produzem sobrevivência. Reportar estratos por dia/mecanismo; não ajustar o contraste primário por volume, market cap ou graduação posteriores ao tratamento. Excluir trades do agente das métricas orgânicas não elimina esses vieses.

Esta hipótese não duplica H-P27 (regime BTC × graduação): aqui o contraste é Mayhem × controle, no mesmo universo. Resultado desta tarefa = protocolo e evidência de instrumentação; nenhum resultado econômico foi calculado.

## 8. Verificação e revisão

Antes da edição da fila, `timeout 290 uv run python infra/scripts/obsidian_lint.py` retornou saída 0: `256 nota(s) analisada(s)`, todas as sete categorias com zero, `RESULTADO: base limpa`. Testes de aplicação não se aplicam à pesquisa sem código. Revisão própria: campos API separados de on-chain; signer/fee payer não usado como trader; missingness e identidade por operação explicitados. A tentativa de delegação somente leitura falhou na ferramenta (`no thread with id`); não se declara revisão independente nem consenso com outro motor.

Verificação **após** adicionar H-P28, 12/09/2026 **02:09 BRT**, comando `timeout 290 uv run python infra/scripts/obsidian_lint.py`, saída real, exit 0:

```text
LINT DA BASE OBSIDIAN — 256 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

`git diff --numstat -- obsidian/00-INBOX/Hipoteses-do-plantao.md` retornou `1 0 obsidian/00-INBOX/Hipoteses-do-plantao.md`. `git diff --check -- obsidian/00-INBOX/Hipoteses-do-plantao.md` saiu 0, sem erro de whitespace; Git apenas avisou conversão futura CRLF→LF. A árvore já continha alterações de outras tarefas; elas não foram editadas por esta execução.

## Relatório final — 12/09/2026 02:10 BRT
**RESUMO:** Manual confirmado; campos HTTP, endpoint do screener e compra real do agente comprovados (§§2–5).
**ARQUIVOS:** criada `.claude/state/notes-A4.1b-mayhem.md`; uma linha adicionada em `obsidian/00-INBOX/Hipoteses-do-plantao.md`; sem commit.
**TESTES:** `timeout 290 uv run python infra/scripts/obsidian_lint.py` → exit 0, 256 notas, `RESULTADO: base limpa`; curls úteis API/RPC → HTTP 200.
**MUST-FIX:** na futura implementação, atribuir por operação/CPI: a compra real do §5.2 tem agente `signer:false` e seria contaminante orgânico num filtro por fee payer.
**NICE-TO-HAVE:** obter IDL próprio de MAyh e HAR do screener; não obtidos nesta pesquisa (§§4–5).
**O QUE EU FARIA DIFERENTE:** preservar unknown e cobertura; usar coorte de criações, sem selecionar sobreviventes (§§6–7).
**CONCORDO COM:** excluir trades do agente das métricas orgânicas e manter retenção idêntica; H-P28 segue hipótese não medida (§§6–7).
**OBSIDIAN:** Fila de hipóteses do plantão de mercado — H-P28 registrada como `nova`, com fonte e protocolo; nenhuma outra página alterada.
base limpa

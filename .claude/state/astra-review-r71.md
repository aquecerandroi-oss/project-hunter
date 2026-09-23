## RESUMO

**A evidência melhorou durante a revisão: identifiquei o NEAR como OmniBridge e confirmei o mint do XRP no próprio site da Hex Trust.** Não usaria “mesma autoridade de tokens já semeados” como prova; agora temos evidência direta.

Parecer como `risk-engine-guardian`: **NEAR, WBTC e ORCA passam na identidade; XRP passa na identidade, mas exige aceitar o risco de congelamento; BIRB merece uma última confirmação oficial e análise dos grandes holders; SLX permanece desabilitado.** Isso não comprova rentabilidade nem garante resgate.

| Mercado | Identidade verificada nesta revisão | `kind` / tier | Minha recomendação |
|---|---|---|---|
| **NEAR** | Registro oficial do OmniBridge associa o mint exatamente a `wrap.near`, nos dois sentidos; autoridade coincide com a PDA do programa oficial. | `ponte` / A | Aceitável para a ficha proposta, registrando OmniBridge e suas dependências. |
| **XRP** | HTML do site oficial da Hex Trust contém o mint completo informado. Freeze e mint authority confirmadas por RPC. | `ponte` / A | Identidade suficiente. Eu manteria pendente de aceite explícito do risco de congelamento; uma nota descritiva sozinha não representa esse aceite. |
| **BTC** | Registro oficial Wormhole associa o mint ao WBTC Ethereum, contrato `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599`, decimals 8. | `ponte` / A | Concordo em usar WBTC Portal, reconhecendo as duas camadas de risco. |
| **BIRB** | Mesmo mint do R63, corroborado por anúncio de listagem da BigONE; mint/freeze revogadas confirmadas por RPC. Não localizei publicação do mint no material oficial do projeto consultado. | `nativo` / A | Eu aguardaria a confirmação do projeto e a decomposição dos 90,9% antes de colocar dinheiro. |
| **ORCA** | Mint completo publicado na governança oficial da Orca; RPC confirmou decimals 6, sem freeze, **com mint authority ativa**. | `nativo` / B | Aceitável quanto à identidade; registrar também quem controla a emissão. |
| **SLX** | Mesmo mint do R63 e do anúncio de listagem da Gate; RPC confirmou decimals 6, mint/freeze revogadas. Confirmação direta do projeto ficou pendente. | `nativo` / C | `enabled=false`, independentemente do custo baixo. |

Fontes: [OmniBridge oficial](https://github.com/Near-One/omni-bridge), [Hex Trust](https://www.hextrust.com/services/wrapping/wxrp), [registro Wormhole](https://raw.githubusercontent.com/wormhole-foundation/wormhole-token-list/main/content/by_source.csv), [Orca](https://forums.orca.so/t/governance-council-technical-proposal/178), [BigONE/BIRB](https://bigone.zendesk.com/hc/en-us/articles/54679475425561-BigONE-Alpha-Lists-BIRB-Moonbirds), [Gate/SLX](https://www.gate.com/id/announcements/article/51363).

Os tiers acima usam **a liquidez que você informou**, não uma nova medição minha.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit, acesso a `.env`, alteração no banco ou transação enviada.

## TESTES

Executei verificações somente leitura, com estes resultados reais:

**Solana — `getMultipleAccounts`, `jsonParsed`, `commitment=finalized`, slot `449806922`:**

| Mint | Decimals | Mint authority | Freeze authority |
|---|---:|---|---|
| NEAR | 9 | `FvULaw…NYds` | `null` |
| XRP | 6 | `E5GXVz…156o` | `E5GXVz…156o` |
| WBTC | 8 | `BCD75R…YMV7` | `null` |
| BIRB | 6 | `null` | `null` |
| ORCA | 6 | `GwH3Hi…x4PV` | `null` |
| SLX | 6 | `null` | `null` |

Todos retornaram `type=mint`, `isInitialized=true`, proprietário SPL Token clássico e tamanho 82 bytes. Portanto, nessa leitura, **nenhum dos seis usa extensões Token-2022**.

**NEAR — chamadas de leitura ao contrato `omni.bridge.near`:**

```text
get_token_id({"address":"sol:3ZLekZYq2qkZiSpnSvabjit34tUkjSwD1JFuW9as9wBG"})
block_height: 216952755
result: "wrap.near"

get_token_address({"chain_kind":"Sol","token":"wrap.near"})
block_height: 216952792
result: "sol:3ZLekZYq2qkZiSpnSvabjit34tUkjSwD1JFuW9as9wBG"
```

Também derivei em memória a PDA com seed `authority` e programa oficial `dahPEoZGXfyV58JqqH85okdHmpN8U2q8owgPUXSCPxe`:

```text
FvULawNPGBbuwYus74ECaQoV1oH9Tk6XPN7VPN51NYds — bump 255
```

O programa e a seed estão no [repositório oficial](https://github.com/Near-One/omni-bridge/blob/main/solana/programs/bridge_token_factory/src/constants.rs).

Não rodei pytest, migrations, consultas ao VPS nem novas cotações. Frequências, liquidez e custos permanecem evidência fornecida por você.

## MUST-FIX

**1. Não tratar o cálculo de `enabled` como validação de identidade.**

A função só verifica tier e custo; não considera emissor, lastro ou freeze: [spot_desk_seed.py:110](/C:/dev/project-hunter/infra/migrations/ddl/spot_desk_seed.py:110).

Com os seus números, a regra produz **true para os cinco primeiros e false para SLX**. Se a decisão for manter XRP/BIRB pendentes, isso precisa ser uma exceção explícita ou essas linhas devem aguardar; não altere artificialmente tier ou custo para conseguir `false`.

**Cenário:** um token passa por preço/liquidez, entra habilitado e depois perde resgate ou capacidade de transferência. O filtro econômico não protege dessa falha.

**2. XRP: congelamento é risco de saída, não dúvida de identidade.**

Confirmei o endereço no HTML oficial, superando a limitação da extração textual da página. Mas uma conta congelada não pode transferir tokens; o stop pode disparar e a venda continuar impossível. Isso é comportamento documentado do [SPL Token](https://solana.com/docs/tokens/basics/freeze-account).

**Minha posição:** freeze não cria veto automático na regra existente. Porém, eu não colocaria dinheiro sem assumir expressamente que a posição pode ficar imobilizada. A própria Hex Trust restringe emissão/resgate a participantes institucionais verificados; não presuma que a carteira da mesa dispõe de resgate direto. [Hex Trust](https://www.hextrust.com/services/wrapping/wxrp).

**3. BIRB: esclarecer os 90,9% antes de habilitar para dinheiro real.**

Esse percentual não comprova concentração econômica em poucos indivíduos: pode incluir custódia, pools e vesting. Também não pode ser ignorado.

**Cenário:** se a maior parte for saldo livre de poucos controladores, uma venda concentrada esvazia a liquidez disponível antes do stop. Mint/freeze revogadas não impedem vender estoque existente. Eu pediria identificação das principais contas, proprietários e restrições de movimentação, além do mint publicado pelo projeto.

**4. Corrigir a força atribuída às provas.**

- Jupiter Price V3 e quote são **duas verificações complementares**, mas não duas fontes comprovadamente independentes: o Price V3 usa preços de swaps e heurísticas, podendo compartilhar mercados subjacentes com a cotação. [Documentação Jupiter](https://developers.jup.ag/docs/price/index).
- Uma cotação de ida e volta não demonstra que ambas as transações pousaram.
- Uma autoridade de ponte compartilhada identifica infraestrutura; não identifica automaticamente o ativo de origem. É preciso conferir o registro de origem, como fiz para NEAR e WBTC.

**Cenário:** uma representação sem lastro mantém paridade temporária na mesma liquidez observada pelas duas APIs; ambas concordam e a mesa compra mesmo assim.

## NICE-TO-HAVE

Antes da semente, eu fecharia um pequeno registro por mint:

- Fonte oficial → endereço completo; para pontes, cadeia e contrato de origem → mint de destino.
- Snapshot RPC com UTC/slot, decimals, supply e authorities completas.
- Controlador das authorities: programa/PDA, multisig e possibilidade de upgrade. **Supply on-chain confirma quantidade emitida, não lastro.**
- Para BIRB, distribuição por proprietário econômico, separando pools, custódia e vesting.
- Cotação de venda e simulação sem envio, usando a configuração real do executor quando possível. Isso testa executabilidade naquele estado, não garante saída futura.

Registrar custos como fração: NEAR `0.00144`, XRP `0.00312`, BTC `0.00004`, BIRB `0.00012`, ORCA `0.00110`, SLX `0.00073`. Essa convenção está em [spot_desk_seed.py:20](/C:/dev/project-hunter/infra/migrations/ddl/spot_desk_seed.py:20).

## O QUE EU FARIA DIFERENTE

**NEAR:** agora usaria `ponte`, identificada como **NEAR OmniBridge**. O mcap de 8 milhões não precisa encaixar na faixa histórica das “representações” do R63: essa faixa descrevia a amostra, não prova identidade. O próprio R63 admite que alguns antigos rótulos `nativo` vieram apenas da ausência de “Portal/Wormhole” no nome: [notes-R63.md:132](/C:/dev/project-hunter/.claude/state/notes-R63.md:132).

**BTC:** concordo com WBTC Portal como escolha defensável, mas não com “sem freeze, portanto mais seguro que cbBTC”. A exposição é:

`BTC em custódia → WBTC Ethereum → Wormhole → SPL na Solana`.

Uma falha no lastro do WBTC **ou** na ponte pode desancorar o SPL enquanto BTCUSDT permanece saudável. cbBTC troca essa composição por dependência da Coinbase, incluindo seu controle sobre o token; o mint alternativo também está publicado [oficialmente](https://www.coinbase.com/cbbtc). A preferência exige pesar esses riscos, não contar apenas authorities.

**Concentração:** sim, acrescentar NEAR e WBTC aumenta exposição a infraestruturas já presentes. ZEC/STRK/NEAR compartilham a autoridade informada; ETH/BNB/SPX/WBTC compartilham Wormhole. Além disso, o próprio OmniBridge documenta dependência de Wormhole para verificação de entradas vindas de Solana: os grupos não são totalmente independentes. [Arquitetura OmniBridge](https://github.com/Near-One/omni-bridge).

Eu acompanharia exposição agregada por ponte/custodiante, incluindo ordens pendentes. Três símbolos diferentes podem sofrer a mesma perda simultânea.

Também corrigiria “STRK já é usado”: o seed o inclui como `representacao`, tier C, custo `0.00486`; isso o deixa desabilitado originalmente. Não consultei seu estado atual no VPS. [spot_desk_seed.py:53](/C:/dev/project-hunter/infra/migrations/ddl/spot_desk_seed.py:53).

## CONCORDO COM

- Os seis tiers seguem os cortes do R63 com a liquidez informada: [notes-R63.md:35](/C:/dev/project-hunter/.claude/state/notes-R63.md:35).
- SLX continua desabilitado; custo baixo não supera tier C.
- DASH/PROM e demais candidatos sem identidade/paridade ficam fora. A formulação correta é **“não encontramos representação validada nesta busca”**, não “não existe DASH na Solana”.
- Contar todas as versões é útil para descoberta, mas não estima atividade da mesa atual: a consulta de entradas exige `mean_reversion` e a versão configurada. Os sinais de BTC em v10/h1 não tornam BTC elegível na v14. [spot_repo.py:113](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:113).

## OBSIDIAN

- **KB-0145 — Binance como sinal, Solana como execução:** acrescentar identidade comprovada de NEAR/XRP/WBTC, limites da paridade e dependências compartilhadas.
- **Spot — a mesa `spot/1`:** distinguir elegibilidade econômica, validação de identidade e aceite de riscos de custódia/congelamento.
- **Revisões Astra — R71** *(nova página proposta)*: guardar resultados RPC, fontes oficiais, decisões por mint e pendências de BIRB/SLX.
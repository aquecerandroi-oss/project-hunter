**RESUMO**

Concordo com **(a)** e **(c)**. Concordo com a direção de **(b)**, mas sua proposta precisa incluir o programa de taxas e distinguir **saída executável** de **saída contabilizável**.

O pino deve continuar intacto até a T4.8e. O modo inerte é um caminho intermediário aceitável, por decisão do Everton, mas **também paralisa a spot/1 e parte da observação da carteira**. Zero posições abertas, informado pelo orquestrador, não comprova ausência de transações pendentes.

Há dois acréscimos relevantes à conclusão: **tamanho variável do TradeEvent** e **fills de carteiras observadas gravados como `unknown`, sem recuperação automática após corrigir o parser**.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit, deploy ou envio de transação. Revisão como `exchange-integration-specialist`, incluindo os critérios do guardião.

**TESTES**

Executei duas reproduções offline, por scripts em stdin com `uv run --no-sync python -B -`, sobre os JSONs existentes. Resultados:

- Cinco transações pump: todas falharam em `decode_fills`; todas retornaram zero eventos pelo leitor de logs.
- Quatro transações PumpSwap: todas falharam em `decode_pumpswap_fills`.
- Seis transações pump: o leitor de carteiras retornou `unknown`.
- Global: bytes iguais à fixture T4.8d.

Trechos reais da saída:

```text
tx_buy_2qnMHiEaNfxX.json ValueError: TradeEvent has 24 trailing bytes logs_events= 0
amm_tx_5A1byFyLnuFA.json ValueError: SellEvent has 49 trailing bytes
tx_buy_2qnMHiEaNfxX.json buy event_bytes= 382
tx_sell_2DSRRspQNw13.json sell event_bytes= 383
wallet [('unknown', 'none', 'TradeEvent has 24 trailing bytes')]
global raw_equal= True
```

Não executei pytest, simulação mainnet nem consultas à VPS. As pausas e a ausência de posições são premissas fornecidas, não verificações minhas.

**MUST-FIX**

1. **ALTO — Corrigir os parsers antes de mover o pino; validar a cauda, não um comprimento total fixo.**

   Seu diagnóstico está correto, mas “22/22 corpos de 383 B” precisa ser corrigido: nos brutos salvos, `buy` tem **382 B** e `sell`, **383 B**, incluindo o discriminador e excluindo o prefixo CPI. O parser contém uma string e um vetor variáveis: `ix_name` e `shareholders`. A extensão deve ser reconhecida **depois de consumir esses campos**. [trade_event.py:186](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:186)

   **Cenário:** uma correção que aceite somente 383 B conserta sells, mas continua recusando buys legítimos. Aceitar qualquer sobra, por outro lado, ocultaria o próximo layout desconhecido. Exigir fixtures antigas e novas, cauda de tamanho conhecido e recusa de truncamento/sobra inesperada.

   A falha da PumpSwap também é real: a exceção ocorre antes da leitura do delta, impedindo o fallback descrito na docstring. [pumpswap_build.py:94](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:94)

2. **ALTO — Tratar a perda de eventos como falha de cobertura de pesquisa.**

   Hoje, um TradeEvent reconhecido que falha no decode é descartado como se não existisse. O handler do worker ainda retorna o mint; o loop pode registrar atividade e avaliar a moeda. Logo, `event_gate_evaluations > 0` **não prova ingestão saudável de trades**. [trade_event.py:310](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:310), [event_gate_eval.py:94](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:94), [event_gate.py:122](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate.py:122)

   **Cenário:** account notifications continuam atualizando preços, mas vendas do criador, compradores e fluxo desaparecem da fita. A pesquisa passa a avaliar estados incompletos sem marcar a interrupção; um recuo pode vencer seu prazo sem ter observado as trocas que o disparariam.

   A T4.8e precisa distinguir **notificação sem TradeEvent** de **TradeEvent indecodificável**, contar a falha, invalidar a cobertura pertinente e exigir aquecimento posterior. Existe `mark_gap` para invalidar componentes do estado, mas o descarte silencioso não chega a ele. [event_state.py:230](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:230)

3. **ALTO para integridade histórica — Incluir as carteiras observadas no levantamento e na recuperação.**

   `wallet_fills_from_transaction` captura o erro e pode persistir um registro `unknown` com `event_error`. O coletor avança o cursor; assinaturas já conhecidas são puladas. **Só atualizar o decoder não recupera essas linhas.** [wallet_fills.py:253](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/wallet_fills.py:253), [wallets.py:168](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:168), [wallets.py:214](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:214)

   **Cenário:** uma carteira acompanhada vende após o upgrade; a venda vira `unknown`, não entra na reconstrução de posição, e o histórico continua incorreto depois do deploy da correção.

   Falta medir se isso ocorreu nas carteiras configuradas. O mecanismo está reproduzido; a quantidade afetada em produção não está comprovada. Planejar reprocessamento auditado das assinaturas afetadas, preservando a evidência original.

4. **ALTO na proposta (b) — Cobrir `pfeeUx` e definir indisponibilidade em runtime.**

   Adicionar somente PumpSwap deixa uma dependência executável descoberta: nossos builders de buy e sell incluem o **programa de taxas**. FeeConfig inalterada não prova bytecode inalterado. [tx.py:228](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:228), [tx.py:255](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:255)

   **Cenário:** um futuro upgrade apenas de `pfeeUx` altera o cálculo de taxas; pump mantém seu slot, o detector continua verde e entradas usam premissas ainda não revalidadas.

   Outro ponto: `program_check_once` **não limpa** divergência existente — concordo com manter isso. Porém, erro de leitura apenas incrementa contador e retorna: se o estado estava limpo, permanece limpo. [program_check.py:65](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:65)

   **Cenário:** boot aprovado, upgrade posterior e leitura de identidade indisponível; o detector não fecha entradas por desconhecimento. A proposta deve definir explicitamente validade da última leitura e comportamento quando ela expira. No boot degradado, a falha de leitura precisa fixar a recusa **antes de iniciar os loops**.

5. **ALTO na proposta (b) — Simulação bem-sucedida não comprova fechamento contábil.**

   A simulação do submissor verifica `simulation.ok`; a leitura do fill acontece depois do envio. Uma transação pode passar na simulação, aterrar e terminar em `fill_decode_failed`. [submit.py:128](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:128), [submit.py:197](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:197)

   **Cenário:** saída permitida durante divergência vende os tokens, mas o evento novo impede confirmar a ordem e fechar a posição no banco. É precisamente uma falha que a simulação não detecta.

   Concordo em preservar uma via de saída de emergência, mas ela deve aparecer como capacidade degradada, com pendência e recuperação explícitas. A T4.8e deve testar **envio → falha de decode → reinício → reconciliação → fechamento único**, nas duas praças. Seu “para sempre” significa, mais precisamente, **enquanto o decoder continuar incompatível**: a reconciliação tenta decodificar novamente. [submit.py:249](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:249)

**NICE-TO-HAVE**

- **BondingCurve:** não encontrei evidência suficiente para afirmar outra quebra. Contudo, o decoder aceita bytes reservados sem validá-los; sucesso no decode não comprova ausência de mudança. Acrescentaria capturas pós-upgrade das variantes usadas e verificaria campos consumidos por builder, cotação e worker. [decode.py:178](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/decode.py:178)
- **Independência da Jupiter:** formular como “independente dos nossos builders/parsers pump”. Imports genéricos não provam independência dos programas executados por uma rota. O verificador valida argumentos e contas da rota Jupiter; isso não demonstra ausência de PumpSwap numa rota concreta. [spot_verify.py:235](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:235)
- Não atribuir a quebra histórica da PumpSwap ao dia 02/10 sem amostras anteriores que delimitem o início.

**O QUE EU FARIA DIFERENTE**

Separaria a correção de compatibilidade da mudança de política de boot.

**Sobre “parar no passo 4”: sim, continua valendo com as mesas pausadas.** A instrução proíbe mover a constante quando uma dependência mudou; pausa operacional não demonstra compatibilidade. [notes-T4.8d.md:198](C:/dev/project-hunter/.claude/state/notes-T4.8d.md:198)

**Modo inerte é aceitável como contenção temporária**, sem mover o pino, com estes efeitos:

| Capacidade | Com live desligado |
|---|---|
| Entradas e saídas spot/1 | Param: exigem live e signer. [spot_config.py:95](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_config.py:95), [spot_exits.py:82](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:82) |
| Saídas meme | Não gerenciam posição sem signer. [exits.py:99](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:99) |
| Holdings, saldo e tesouraria | Retornam sem executar suas leituras/operações dependentes do signer. [wallet_holdings.py:201](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/wallet_holdings.py:201), [wallet_refresh.py:50](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/wallet_refresh.py:50), [treasury.py:79](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury.py:79) |
| Reconciliação spot | Para sem signer. [spot_reconcile.py:74](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:74) |
| Reconciliação meme, leitura do kill switch e heartbeat | Os loops continuam; isso não restaura capacidade de vender. [main.py:333](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:333) |

Antes dessa opção, verificaria também **ordens assinadas pendentes**, além de posições: uma compra já enviada pode aterrar com o executor inerte e ficar sem saída operacional.

**CONCORDO COM**

- Aceitar a extensão conhecida, preservar o campo sem inventar significado econômico e comprovar a contabilidade contra deltas reais.
- Fixtures reais, paridade e simulações antes do novo pino.
- Implementação pelo especialista, revisão obrigatória do guardião, commit pelo orquestrador e deploy pelo Everton.
- **Severidade ALTA para o incidente de pesquisa**, mesmo sem exposição financeira atual. Delimitaria como intervalo potencialmente afetado desde o upgrade até a recuperação comprovada, por consumidor/coorte. Não declararia toda a pesquisa inválida: account notifications continuam tendo caminho próprio. [event_gate_eval.py:111](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:111)

Isso segue a lição da [KB-0149, seção “A infra é estratégia”](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md): atividade aparente não substitui qualidade do instrumento.

**OBSIDIAN**

- **Open Bugs** — registrar os dois parsers incompatíveis, a perda silenciosa de cobertura e o possível histórico `unknown`.
- **Revisões Astra — T4.8e** — registrar este parecer, as reproduções e os critérios de aceite.
- **Diário 2026-10-05** — documentar pausas informadas, incidente e eventual escolha pelo modo inerte.
- **Meme — Mercado / Trading** — documentar dependências pump, PumpSwap e fee, além dos estados de degradação.
- **EXP efetivamente afetadas** — acrescentar avaliação de cobertura datada, sem reescrever protocolos nem resultados anteriores.
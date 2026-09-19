## RESUMO

**REQUEST_CHANGES:** corrigir o limite temporal das consultas, restringir os candidatos à Binance e preservar a última marca quando a cotação falhar.

A consulta reproduz o §2, inclusive suas omissões. A álgebra de paridade está correta para `1000BONK`; **180 s de validade não garantem paridade contemporânea de 3%**. Concordo com `signer_present` passado pelo boot.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisados os sete arquivos indicados, o desenho, o plano e os contratos relacionados.

## TESTES

Não executei pytest, lint ou typecheck nesta revisão somente leitura.

Os testes de repositório verificam SQL e parâmetros com uma sessão falsa; não executam a consulta no PostgreSQL: [test_spot_repo.py:44](C:/dev/project-hunter/services/meme-executor/tests/test_spot_repo.py:44). Portanto, não comprovam comportamento de JOIN, enum, índices ou concorrência.

## MUST-FIX

1. **HIGH — falta corte superior em `now`.**  
   [spot_signals.py:47](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_signals.py:47) exige `is_final` e limite inferior, mas permite `close_time > now`; a validação posterior também só rejeita velas antigas, em [spot_signals.py:109](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_signals.py:109).

   **Cenário:** o tique captura `now` imediatamente antes da virada do minuto; o coletor grava o novo fechamento antes do SELECT. A decisão usa uma vela posterior ao instante declarado. Uma consulta histórica sobre banco já atualizado apresenta o mesmo problema.

   **Correção:** filtrar `c.open_time <= :now - interval '1 minute'` antes de `ORDER BY/LIMIT`. Também acrescentar `s.emitted_at <= :now` aos candidatos, cujo filtro hoje só tem limite inferior: [spot_repo.py:111](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:111). Testar as fronteiras e uma vela final futura.

2. **HIGH — o mapa Binance aceita sinais de outra exchange.**  
   O JOIN usa apenas `d.binance_symbol = m.symbol`, sem restringir a exchange: [spot_repo.py:107](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:107). O schema permite o mesmo símbolo em exchanges e tipos diferentes: [markets.py:54](C:/dev/project-hunter/packages/core/hunter_core/db/models/markets.py:54).

   **Cenário:** surge um sinal recente `mean_reversion/v14` de outra exchange com símbolo presente no mapa. Ele vira candidato; a paridade consulta essa outra exchange e pode passar, executando uma origem que não é a Binance. Se houver homônimo com preço semelhante, 3% também não estabelece identidade do ativo.

   **Correção:** restringir explicitamente `exchanges.code = 'binance'`. **Não impor `market_type = 'spot'` automaticamente:** a pista executa spot na Solana, mas o desenho admite sinais provenientes de perpétuos.

3. **MEDIUM — falha de cotação apaga a marca que deveria permanecer.**  
   [spot_repo_positions.py:93](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:93) zera `mark_sol`, `mark_at` e `mark_source`, contrariando [spot1-lab-solana.md:94](C:/dev/project-hunter/docs/design/spot1-lab-solana.md:94).

   **Cenário:** existe uma marca válida; a próxima chamada Jupiter dá timeout. Perde-se o valor anterior e seu timestamp, impedindo calcular corretamente a idade daquela marca. Quando integrada ao freio, a posição passa a tornar `marks_complete=False`: [admission.py:295](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/admission.py:295).

   **Correção:** na falha, atualizar somente motivo e timestamp da atualização; preservar valor, fonte e instante da última cotação válida. O teste atual exige justamente o apagamento e precisa mudar: [test_spot_repo.py:224](C:/dev/project-hunter/services/meme-executor/tests/test_spot_repo.py:224).

## NICE-TO-HAVE

- **Paridade: documentar e medir o erro temporal.** A fórmula usa dois fechamentos históricos para valorar uma cotação atual: [spot_signals.py:135](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_signals.py:135). Exemplo **hipotético**: fechamento SOL=100, token=1; agora SOL=110 e Jupiter cobra 1,10 pelo token. Uma ficha de 0,05 SOL compra 5 tokens. O cálculo histórico produz `0,05 × 100 ÷ 5 = 1`, paridade perfeita, embora o prêmio atual seja 10% se Binance continuar em 1. Também pode haver falsa recusa quando o token sobe nas duas venues após o fechamento. Isso é defasagem temporal, sem direção fixa; o limite de 3% não a cobre.
- Persistir os timestamps dos dois fechamentos e da cotação, além dos preços. Uma futura garantia de paridade contemporânea exige referências recentes e sincronizadas; reduzir apenas os 180 s não elimina a defasagem intraminuto.
- Acrescentar teste PostgreSQL para candidatos de exchanges distintas, fallback JSONB e exclusão de compras em todos os estados. Confirmar na integração `WORKER_ROLE`, transação por passo e ausência de consultas de entrada quando desabilitada; essas responsabilidades ficam nos chamadores previstos na [T4.74-5:81](C:/dev/project-hunter/docs/plans/T4.74-spot1.md:81).

## O QUE EU FARIA DIFERENTE

Corrigiria também o §2 do desenho para explicitar **Binance + corte temporal superior**. Manteria a janela de 180 s identificada como regra de disponibilidade do dado, sem apresentá-la como garantia de desvio atual máximo de 3%.

## CONCORDO COM

- **JSONB:** `jsonb_array_elements` corresponde à coleção de `FeatureEvidence`; `targets->>0` corresponde às strings persistidas. Referências: [envelope.py:133](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:133), [persist.py:87](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:87).
- **Enum e expiração:** `'active'` é um literal SQL resolvido contra o enum, não um parâmetro explicitamente tipado como `text`. `expires_at` é realmente abertura da entrada mais horizonte: [spot_repo.py:110](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:110), [persist.py:94](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:94).
- **Duplicidade:** uma compra já persistida não escapa do `NOT EXISTS`, independentemente do status. Há ainda unicidade parcial por sinal comprado e índice `(signal_id, side)`: [spot_repo.py:112](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:112), [spot_desk.py:233](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:233). Não encontrei fundamento para acusar índice ausente; desempenho requer `EXPLAIN`.
- **1000BONK:** multiplicar o preço por token por 1000 produz preço por unidade Binance; a razão fica dimensionalmente correta: [spot_signals.py:134](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_signals.py:134).
- **Signer:** `signer_present=False` por padrão é adequado; o chamador deve passar `signer is not None` após o boot. Evita depender da chave já removida do ambiente: [spot_config.py:146](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_config.py:146), [signer.py:115](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/signer.py:115).

## OBSIDIAN

- **Spot — a mesa `spot/1`** — registrar os três bloqueios e a limitação temporal da paridade.
- **KB-0145 — Binance como sinal, Solana como execução** — distinguir paridade contemporânea da aproximação por fechamentos finais.
- **Revisões-Astra / T4.74-3** — registrar este parecer e, depois, as evidências das correções.
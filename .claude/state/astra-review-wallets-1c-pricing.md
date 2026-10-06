**RESUMO**

**APPROVE para o conserto revisado.** Não encontrei must-fix com cenário reproduzível. A implementação atende ao contrato da [revisão anterior, rodada 2](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-1a.md:38): reserva virtual com sinal, cotação em `Q_real + V` e reconstrução pelo fluxo que inclui LP.

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim; nenhum commit. Revisão no papel de `quant-engineer`.

**TESTES**

Executei com sincronização do ambiente, bytecode e cache do pytest desabilitados:

```text
uv run pytest packages/indicators/tests/meme/test_wallets_pricing_pool.py packages/indicators/tests/meme/test_wallets_bridge.py packages/indicators/tests/meme/test_wallets_chain.py -q
46 passed in 3.92s

uv run pytest packages/indicators/tests/meme -k wallets -q
144 passed in 7.13s
```

A árvore disponível nesta execução produziu **144**, contra os 143 informados. Também percorri as fixtures em memória:

```text
{'pool_fill': 9, 'sol_is_base': 3, 'curve_record': 1}
total 13
```

Não reexecutei os 1.595 testes do pacote nem os 12 mutantes; esses resultados continuam sendo os relatados por você.

**MUST-FIX**

Nenhum encontrado no escopo.

**NICE-TO-HAVE**

- **Testar o teto com taxa não zero.** O teste específico do teto usa `fee_bps=0`; acrescentaria uma asserção que distinga aplicar a taxa antes ou depois do limite, congelando a aproximação escolhida. [test_wallets_pricing_pool.py:52](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_pricing_pool.py:52)
- **Explicitar a procedência temporal de `curve_complete`.** Documentaria que o chamador deve fornecer o estado correspondente ao evento, sem usar a flag atual para reclassificar trades históricos. A ponte recebe somente o booleano, portanto essa garantia pertence ao chamador. [bridge.py:136](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:136)
- **Ajustar “recusa nunca é exceção”.** Pool resolvida para outro endereço levanta `ValueError` deliberadamente. Faz sentido como erro de programação, mas a documentação deveria distinguir isso das recusas de dados. [bridge.py:19](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:19), [bridge.py:160](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:160)

**O QUE EU FARIA DIFERENTE**

Manteria o desenho atual, mas descreveria o teto como **convenção de liquidação da pesquisa**. `min(bruto, Q_real)` seguido da taxa não demonstra que a venda integral seria executável na cadeia; tampouco modela exatamente o limite `bruto − LP ≤ Q_real`. Essa distinção merece ficar junto da fórmula. [pricing.py:109](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:109)

**CONCORDO COM**

- **(a) Confirmado:** três dos 13 registros são pools com WSOL na base; a resolução pelas contas da instrução resulta em `sol_is_base`. Recusar evita interpretar átomos do outro token como lamports. [t1a_tape.py:95](C:/dev/project-hunter/packages/indicators/tests/meme/t1a_tape.py:95), [test_wallets_chain.py:128](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_chain.py:128)
- **(b) Correto exigir `curve_complete`:** a ausência vira `curve_completion_unknown`; a ponte não inventa o estado de migração. [bridge.py:141](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:141)
- **(c) Concordo como aproximação declarada:** o teto é sobre o bruto; não é o limite exato do fluxo do cofre. [pricing.py:134](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:134)
- **(d) Confirmado nos pares fixados:** a reconstrução conserva `V`, e dois pares na suíte do motor comparam o pós-estado anterior ao pré-estado seguinte. Isso sustenta a hipótese nesses casos, sem provar constância universal. [pricing.py:150](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:150), [test_wallets_chain.py:112](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_chain.py:112)
- **Separação e causalidade preservadas:** `SwapLike` mantém a ponte estrutural; `pre_trade_real_sol` reutiliza a reconstrução; o teste de slot vazio altera o próximo trade sem alterar a cotação. [bridge.py:47](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:47), [follow.py:225](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:225), [test_wallets_pricing_pool.py:148](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_pricing_pool.py:148)

**OBSIDIAN**

- **wallets-engine** — acrescentar aprovação, resultados desta execução e limites da aproximação.
- **Open Bugs / Resolved Bugs** — registrar o conserto do bug “Motor 1c cota a pool sem a reserva virtual”, vinculando o commit quando existir.
- **KB-0184** — atualizar o estado do motor e registrar orientação das mints, exigência de `curve_complete` e alcance da prova sobre `V`.
- **wallets-1a** — ligar o item 2 da rodada 2 à revisão que verifica seu atendimento.
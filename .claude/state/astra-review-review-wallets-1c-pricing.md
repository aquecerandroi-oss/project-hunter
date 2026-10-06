**RESUMO**

**REQUEST_CHANGES**: a correção de LP/`V` está certa, mas há dois problemas no tratamento de pré-estados inválidos e um arredondamento de compra pendente, preexistente.

**ARQUIVOS**

Nenhum arquivo criado ou modificado nesta revisão. Referências abaixo: `wallets/` = `packages/indicators/hunter_indicators/meme/wallets/`; testes = `packages/indicators/tests/meme/`.

**TESTES**

Executei `uv run pytest <arquivos> -q`, com escrita de bytecode/cache desativada:

- Três testes novos: `46 passed, 1 warning in 3.64s`.
- Todos os `test_wallets_*.py`: `144 passed, 1 warning in 3.81s`.

Warning: `asyncio_mode` desconhecido porque desativei o carregamento automático de plugins. Reproduções adicionais executadas em memória.

**MUST-FIX**

1. **HIGH — liquidez desconhecida vira zero.** `wallets/follow.py:228` devolve `0` para pré-estado impossível; `:238` atribui tercil e `:270` permite pareamento. Reproduzi compra com pós-estado `Q=1,5 SOL`, `V=−1 SOL`, entrada de `1 SOL`: pré-estado `None`, mas pareada com controle válido de baixa liquidez. Isso contamina H2. Preservar “desconhecido” e registrar ausência de pareamento.

2. **HIGH — pouso cotado apesar de estado inconsistente.** `wallets/pricing.py:198` elimina o pré-estado inválido e mantém o pós-estado. No mesmo cenário, `landing_sell(7, 10 tokens)` retorna **5.000.000 lamports**, embora não seja possível provar o pior estado do slot. Pode produzir resultado otimista; deve propagar invalidade/censura. O teste `test_wallets_pricing_pool.py:102` atualmente **exige esse descarte silencioso**.

3. **MEDIUM — compra pode exceder o orçamento após `ceil`**, comportamento preexistente em `wallets/pricing.py:97`. Reprodução: `Q=1.000.000.000`, `B=1.000.000.000.000`, orçamento `50.000.000`, taxa `125 bps`: entrega `47.058.823.529` átomos, cujo custo inteiro é **50.000.001 lamports**, mesmo com uma única taxa agregada. Corrigir a inversão inteira e testar custo ≤ orçamento; isso é distinto da aproximação declarada entre taxas agregadas e separadas.

**NICE-TO-HAVE**

As fixtures reais verificam reconstrução, pares consecutivos e recusa de WSOL na base (`test_wallets_chain.py:65`, `:113`, `:127`). Faltam regressões dos três cenários acima; a compra real tolera divergência, sem verificar conservação do orçamento (`:94`).

**O QUE EU FARIA DIFERENTE**

Propagaria uma invalidade explícita até pareamento e pouso, sem convertê-la em número ou removê-la silenciosamente.

**CONCORDO COM**

- Compra desfaz `sol+LP`; venda desfaz `sol−LP`; `V` mantém o sinal (`wallets/pricing.py:154`).
- Venda usa piso do bruto, teto em `Q_real`, depois taxa arredondada para cima. É convenção de pesquisa, com aproximação documentada de até três lamports (`:112`, `:138`).
- Bridge exige quote WSOL e `curve_complete`; temporalidade dessa flag depende do chamador (`wallets/bridge.py:18`, `:125`, `:145`).
- Não encontrei uso do próximo trade no pouso (`wallets/pricing.py:194`).

**OBSIDIAN**

- **wallets-1c-pricing** — acrescentar estes achados, qualificando a aprovação anterior.
- **wallets-engine** — registrar propagação necessária de estados inválidos.
- **Open Bugs** — registrar os três cenários reproduzidos.
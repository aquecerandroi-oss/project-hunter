## RESUMO

**REQUEST_CHANGES — dois must-fix reproduzidos.** Os 132 testes selecionados passaram, mas não cobrem os dois cenários abaixo. Revisão no papel `code-reviewer`, considerando a memória de `Exchange Adapters`, `wallets-1b-record` e KB-0184.

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os arquivos solicitados, usando `git diff` nos modificados e leitura direta nos novos.

## TESTES

Com sincronização do ambiente e geração de bytecode desativadas:

```text
uv run pytest packages/exchange-adapters/tests/unit/test_curve_completion.py packages/exchange-adapters/tests/unit/test_pool_legs.py packages/exchange-adapters/tests/unit/test_t1b_provenance.py packages/exchange-adapters/tests/unit/test_program_logs.py infra/scripts/tests/test_wallet_tape_probe_core.py infra/scripts/tests/test_wallet_tape_probe_stats.py -q -p no:cacheprovider

132 passed in 1.65s
```

Reproduções sintéticas adicionais executadas por `uv run python -`, exclusivamente em memória:

```text
missing draining trade: ['unknown'] unknown= 1 orphans= 0 gap= False
SYNTHETIC known + unknown SellV2: resolved= [True, True] unresolved= 0 conflict= 0 gap= False
SYNTHETIC jsonParsed shape: resolved= [False] unresolved= 1 gap= False
```

## MUST-FIX

1. **HIGH — instrução desconhecida herda a atribuição de uma conhecida.**  
   [pool_legs.py:97](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:97) descarta instruções desconhecidas; [pool_legs.py:119](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:119) procura correspondência de cada evento em todas as conhecidas restantes, sem preservar qual invocação o emitiu.

   **Cenário:** na fixture com duas vendas da mesma pool/usuário/contas, substituí somente o discriminador da segunda instrução pelo de `SellV2`. Ambos os eventos receberam mints, com `unresolved=0` e `conflict=0`.

   Isso demonstra **proveniência indevida**, não uma inversão de mints nessa fixture. Viola, porém, o contrato de recusar instruções desconhecidas: a segunda recebe validação emprestada da primeira. A filtragem também não distingue os demais discriminadores desconhecidos.

   **Correção:** vincular evento à invocação que o emitiu; quando essa associação for ambígua, conservar mints desconhecidas e contar a recusa.

2. **HIGH — perda do trade que completa a curva pode retornar `gap=False`.**  
   [curve_completion.py:102](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/curve_completion.py:102) associa o `CompleteEvent` ao último trade anterior compatível. Havendo esse trade, não conta órfão, mesmo que suas reservas contradigam a conclusão. [program_logs.py:131](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:131) não inclui essa contradição em `gap`.

   **Cenário:** concatenei os logs da compra anterior e da compra que esgota a mesma curva, removendo apenas o `TradeEvent` da segunda. Resultado: o primeiro trade virou `unknown`, `orphan_complete_events=0` e **`gap=False`**, embora um swap tenha desaparecido.

   **Correção:** preservar `unknown`, mas contar a conclusão sem trade compatível como possível perda e sinalizar recuperação. Não basta detectar somente a ausência de qualquer predecessor.

## NICE-TO-HAVE

- **Explicitar suporte apenas a `encoding=json`, ou normalizar `jsonParsed`.** [pool_legs.py:68](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:68) transforma objetos de `accountKeys` em strings; [pool_legs.py:81](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:81) exige `programIdIndex` e contas numéricas. A reprodução resultou em `unresolved=1`, sem atribuição errada. Não classifico como bloqueio porque o cliente atual solicita `json`: [tx_rpc.py:195](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:195).
- Acrescentar regressões sintéticas para os dois bloqueios. Não é necessário esperar uma transação real com corrupção de logs ou combinação V2 para testar essas guardas.

## O QUE EU FARIA DIFERENTE

Manteria a identidade da invocação até a resolução das mints e separaria “swap observado” de “leitura suficiente para declarar cobertura completa”. Os dois achados mostram por que ter um registro ou um predecessor não basta.

## CONCORDO COM

- **Curva:** não encontrei `complete/not_complete` incorreto nos cenários cobertos de dois trades, órfão isolado e trade recusado. As regressões estão em [test_curve_completion.py:251](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_curve_completion.py:251) e [test_curve_completion.py:279](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_curve_completion.py:279). O bloqueio encontrado é perda sem `gap`, com resultado `unknown`.
- **Pools:** CPI de roteador e dois swaps conhecidos estão cobertos em [test_pool_legs.py:176](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pool_legs.py:176); a conferência percorre todos os casamentos em [pool_legs.py:131](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:131).
- **Probe:** as mudanças estão corretas: cashback incluído em [wallet_tape_probe_core.py:157](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_core.py:157), quote não verificada excluída dos bins SOL em [wallet_tape_probe_stats.py:253](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:253) e contador publicado em [wallet_tape_probe_snapshot.py:56](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_snapshot.py:56).

## OBSIDIAN

- **wallets-1b-record** — acrescentar esta rodada, os dois bloqueios e suas reproduções.
- **Open Bugs** — registrar atribuição emprestada para V2 e perda de trade sem `gap`.
- **KB-0184** — qualificar a afirmação de que instruções desconhecidas sempre ficam sem mints.
- **Exchange Adapters** — atualizar os limites de atribuição por invocação e de cobertura na reconciliação.
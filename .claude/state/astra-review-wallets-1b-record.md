**RESUMO**

**DONE_WITH_CONCERNS: não fecharia a onda 1b ainda.** Há dois must-fix reproduzidos: CompleteEvent órfão não sinaliza lacuna, e a sonda continua contabilizando quote não verificada como SOL. Não encontrei look-ahead no uso dos eventos da própria transação, nem quebra estrutural de `SwapLike`.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão somente leitura, no papel de `exchange-integration-specialist`.

**TESTES**

Executei com sincronização do ambiente, bytecode e cache do pytest desativados:

```text
uv run pytest packages/exchange-adapters/tests/unit/test_curve_completion.py packages/exchange-adapters/tests/unit/test_pool_legs.py packages/exchange-adapters/tests/unit/test_t1b_provenance.py packages/exchange-adapters/tests/unit/test_program_logs.py infra/scripts/tests/test_wallet_tape_probe_core.py -q
106 passed in 1.50s

uv run pytest packages/indicators/tests/meme/test_wallets_bridge.py infra/scripts/tests/test_wallet_tape_probe_stats.py -q
36 passed in 0.82s

uv run python infra/scripts/check_file_size.py
scanned 1161 files; 0 over budget, 0 grandfathered
```

Também executei reproduções em memória com as fixtures, descritas abaixo. Não repeti a varredura dos 40 blocos nem consultei novamente a cadeia.

**MUST-FIX**

1. **CompleteEvent sem TradeEvent desaparece como evento não swap, sem lacuna.**

   **Cenário:** retirei somente a linha do TradeEvent da fixture real de conclusão, preservando os frames e o CompleteEvent. Resultado:

   ```text
   orphan_complete swaps 0 gap False unknown 0 non_swap 1
   ```

   O reconciliador simplesmente ignora a conclusão quando não encontra trade anterior. Isso permite declarar cobertura íntegra apesar de faltar justamente a compra que drena a curva. A evidência de conclusão existe, mas não chega ao consumidor como problema. Referências: [curve_completion.py:96](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/curve_completion.py:96), [program_logs.py:250](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:250).

   **Correção proposta:** contar conclusão sem trade correspondente e sinalizar lacuna para recuperação, sem inventar swap. Preservar também a posição dos TradeEvents recusados: hoje a associação procura o último **swap aceito**, não necessariamente o último TradeEvent. Na reprodução com duas compras do mesmo mint e a segunda indecodificável, a primeira mudou indevidamente de `not_complete` para `unknown`; o gap já existia, mas a atribuição ficou errada. [program_logs.py:241](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:241), [program_logs.py:270](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:270).

2. **A flag da sonda não impede a estatística monetária errada.**

   **Cenário:** a venda real `551G…`, com WSOL na base, retorna `quote_unverified=True`, mas `ProbeStats._event` ainda a inclui no histograma:

   ```text
   wsol_base_quote_unverified True size_bins {'0.1-1': 1}
   ```

   O agregador verifica apenas `ok` e presença do valor; o snapshot publica esse histograma como `size_bins_sol`. Portanto, uma nova corrida continua reproduzindo o erro mesmo com a flag adicionada. [wallet_tape_probe_stats.py:251](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:251), [wallet_tape_probe_snapshot.py:55](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_snapshot.py:55).

   **Correção proposta:** excluir quote não verificada das faixas SOL, contar esses eventos separadamente e publicar o denominador efetivamente verificado. Isso não recupera o tamanho SOL das pools invertidas; apenas impede uma afirmação falsa.

   **Sobre (d):** concordo com “run 3 não recalculável integralmente sem o bruto; amostra nova é outra medição”. Entretanto, **não encontrei o erratum aplicado no KB-0183 lido**: a tabela ainda afirma 29% abaixo de 0,01 SOL; o desenho ainda publica 29% e 14%. Esses números precisam ser explicitamente invalidados, preservando o histórico. Os percentuais novos não devem substituí-los como recálculo da run 3. [KB-0183:43](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar.md:43), [seguir-carteiras-lucrativas.md:344](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:344).

**NICE-TO-HAVE**

- **Separar leitura provisória de completude confirmada.** A fábrica pública `swap_record_from_event` retorna `complete` só pelas reservas; o leitor depois reconcilia com CompleteEvent. Reproduzi `complete` pela fábrica versus `unknown` pelo leitor sem CompleteEvent. O único chamador encontrado é o leitor, portanto não é falha ativa desse caminho, mas o contrato público fica perigoso para novos consumidores. [swap_record.py:205](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:205), [program_logs.py:238](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:238).
- Adicionar testes de **duas pools e dois usuários distintos na mesma transação**, além de conhecido+V2 com a mesma combinação de contas. O teste atual de dois eventos usa a mesma pool. [test_pool_legs.py:173](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pool_legs.py:173).
- Conferir os cofres de **todos** os matches, não apenas `matches[0]`, para cumprir integralmente a promessa de detectar contradições nos dados recebidos. Não demonstrei atribuição errada por isso numa transação válida. [pool_legs.py:131](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:131).

**O QUE EU FARIA DIFERENTE**

Separaria “evento observado”, “evento decodificado” e “swap aceito” na reconciliação. Uma recusa não deveria apagar a posição que impede associar o CompleteEvent ao trade anterior.

**Sobre (e):** os campos adicionais não quebram `SwapLike`, mas **não são consumidos automaticamente pela bridge**. O chamador ainda precisa passar `curve_complete=record.curve_complete` ou construir `PoolMints` com as mints resolvidas. [bridge.py:57](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:57), [bridge.py:165](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:165).

Confirmei com fixtures:

```text
curva concluída: chamada simples → curve_completion_unknown; argumento explícito → Fill
pool WSOL quote: chamada simples → pool_quote_unresolved; PoolMints explícito → Fill
pool WSOL base: PoolMints explícito → sol_is_base
```

É pendência de integração para o coletor; não alterei `packages/indicators`. As recusas precisam afetar a cobertura do motor, mesmo que `pool_mints_unresolved/conflict` não representem perda de logs no adaptador. [bridge.py:26](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/bridge.py:26).

**CONCORDO COM**

- **(a) Sem look-ahead intrínseco:** corroborar com outro evento da mesma transação é adequado quando a decisão usa a transação recebida integralmente. Não há consulta posterior de conta nessa regra. Duas compras decodificadas do mesmo mint são associadas corretamente à última anterior à conclusão. [curve_completion.py:85](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/curve_completion.py:85).
- **Truncamento explícito:** a atribuição para após o dano. Reproduzi truncamento antes do CompleteEvent: `unknown`, `gap=True`. [program_logs.py:181](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:181).
- **(b) Pool/usuário/contas:** não encontrei troca entre pools, usuários ou roteadores no caminho válido. O matching usa os quatro identificadores e inclui instruções internas; ele resolve o par de mints, sem pretender identificar unicamente cada execução. [pool_legs.py:71](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:71), [pool_legs.py:119](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:119).
- **(c) Evidência e V2:** instrução conhecida mais confronto com os rótulos de mint disponíveis é uma base adequada. Não exigiria leitura posterior da conta da pool. Recusar layouts desconhecidos e contar a ausência é correto; resolver somente por balances seria outro caminho de evidência, a provar separadamente. [pool_legs.py:97](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:97), [pool_legs.py:138](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/pool_legs.py:138).

**OBSIDIAN**

- **KB-0183 — O que custa coletar o programa inteiro:** invalidar os percentuais monetários da run 3 e separar a nova amostra.
- **KB-0184 — O BuyEvent da PumpSwap:** registrar conclusão órfã, trade recusado e leitura provisória da fábrica.
- **Open Bugs / Resolved Bugs:** manter os dois achados abertos; distinguir campos disponíveis de integração concluída.
- **Exchange Adapters:** documentar os argumentos explícitos exigidos pela bridge e o tratamento das recusas.
- **Revisoes-Astra/wallets-1b-record:** registrar este parecer, os 142 testes e as reproduções adicionais.
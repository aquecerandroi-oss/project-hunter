**RESUMO**

**Aprovo tecnicamente mover o pino com as condições da T4.8f, mas o patch ainda precisa de um ajuste mecânico: `program_identity.py` fica com 354 linhas.** Não encontrei incompatibilidade demonstrada que obrigue a esperar um trade cashback real. Este parecer pressupõe `small_test_below_min` esgotado e `launch_lane_mode=off`; não consultei o estado atual da VPS. As condições anteriores de religamento continuam válidas. [t48f-pin-move.md:24](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/t48f-pin-move.md:24)

Há também uma correção nos números: reproduzi **19/45 instruções integralmente idênticas**, não 23. As 23 correspondem a contas/flags e **prefixo de 24 bytes** iguais; quatro possuem um byte adicional. O teste deliberadamente compara `data[:24]`. Isso não invalida a compatibilidade, mas exige precisão no relatório. [test_pumpfun_tx_parity_t48g.py:150](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48g.py:150)

**ARQUIVOS**

Nenhum arquivo criado ou modificado; patch não aplicado. Revisei os cinco arquivos propostos, os cinco testes novos, fixtures, proveniências, scripts de coleta/simulação e os caminhos de reserva, construção, contabilização e guarda.

**TESTES**

Executei, com bytecode/cache do pytest desabilitados e sem sincronização do ambiente:

```text
uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48g.py packages/exchange-adapters/tests/unit/test_events_t48g.py packages/exchange-adapters/tests/unit/test_pumpswap_tx_t48g.py packages/exchange-adapters/tests/unit/test_pumpfun_curve_layout_t48g.py packages/exchange-adapters/tests/unit/test_simulation_proof_t48g.py -q

52 passed in 3.20s
```

`git apply --check .claude/state/tmp/t48g_pin_move.patch`: saída vazia, código 0.

Reconstrução do patch **somente em memória**, com compilação sintática:

```text
program_identity.py before 318 after 354 syntax OK
program_watch.py before 115 after 116 syntax OK
test_pumpfun_program_identity.py before 243 after 271 syntax OK
test_pumpfun_program_watch.py before 113 after 114 syntax OK
test_program_check.py before 178 after 178 syntax OK
```

Recontagem independente das capturas: **144 TradeEvents, zero indecodificáveis; 51 transações PumpSwap com eventos, zero exceções**. Confirmei os três slots, autoridades iguais entre os três cabeçalhos e IDL idêntica à T4.8c, hash `c7ca9566…`.

Não executei novamente simulações mainnet, suites completas, Postgres, lint ou pyright. Os resultados da cópia isolada informados no pedido não são resultados desta execução.

**MUST-FIX**

1. **Para integrar o patch — limite de arquivo.** As adições deixam `program_identity.py` com **354 linhas**. Cenário: aplicar o patch e executar o gate de tamanho produz falha, independentemente dos testes funcionais. Enxugar pelo menos quatro linhas, preferencialmente resumindo a narrativa e remetendo à revisão. [patch:10](C:/dev/project-hunter/.claude/state/tmp/t48g_pin_move.patch:10), [check_file_size.py:86](C:/dev/project-hunter/infra/scripts/check_file_size.py:86)

2. **Antes de religar compras — reserva incompleta para curvas antigas.** `buy_reserve_sol` inclui rede, prioridade e ATA; não inclui crescimento da curva. A reserva do escopo soma esse valor a `max_sol_cost`. Cenário: compra em curva antiga, ATA existente, consumo próximo do máximo autorizado e débito adicional de 76.200 lamports; a transação pode ter sucesso e ultrapassar a reserva/escopo. Registrar o delta depois não impede o excesso. Isso **não bloqueia o pino com entradas presas**, mas precisa de tratamento e teste de fronteira antes da reabertura. [scope.py:96](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/scope.py:96), [entries.py:227](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:227)

**NICE-TO-HAVE**

**B — Crescimento da BondingCurve.**

- **Offsets:** não encontrei leitura indevida acima de 125 no decodificador de produção; a cauda permanece sem interpretação. Não somaria o `u64` de offset 125 a taxas ou reservas só porque coincide com o evento. [decode.py:190](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/decode.py:190)
- **Slippage:** o limite da instrução e o débito total da carteira são grandezas distintas. O custo adicional observado precisa entrar no orçamento; aumentar slippage não resolve essa contabilização. A cotação constrói os limites a partir do custo/provento da operação. [quote.py:256](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py:256), [quote.py:315](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py:315)
- **Venda antiga:** continua desconhecido se há cobrança, em qual momento e sua interação com o mínimo. Não afirmaria que aluguel necessariamente provoca `min_sol_output` insuficiente. Cenários a provar: vendedor sem SOL suficiente para eventual antecipação do custo; ou venda bem-sucedida cujo líquido fica abaixo da expectativa por esse débito. A lacuna não bloqueia este pino restrito, mas impede declarar essa saída validada.
- **Contabilidade:** havendo saldos, o fill usa o delta real, portanto o custo não desaparece do total contabilizado. `unexplained` permanece diagnóstico. [fills.py:58](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/fills.py:58)

**C — Global +1 byte.** Aceito preservar a leitura do prefixo: o teste verifica os 1087 bytes anteriores e a igualdade dos campos decodificados. Recusar apenas pelo novo tamanho impediria obter o Global também no caminho de saída. Isso não fortalece automaticamente a guarda de identidade, que é outro mecanismo. [test_pumpfun_tx_parity_t48g.py:220](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48g.py:220), [exits.py:243](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:243)

**D — Cashback.** A ausência de trade real pós-deploy é aceitável **para este aceite restrito**. A prova declara venda cashback de curva e acumulador PumpSwap ausente como não cobertos; não converteria duas carteiras simuladas em cobertura desses casos. Permanecem as condições anteriores de Postgres e decisão sobre compras cashback. [prova:12](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48g_simulation_proof_mainnet.json:12)

**E — Patch e documentação.** Slots, histórico, `PREVIOUS`, tarefa seguinte `T4.8h` e atualização dos dois programas adicionais estão coerentes. [patch:68](C:/dev/project-hunter/.claude/state/tmp/t48g_pin_move.patch:68), [patch:114](C:/dev/project-hunter/.claude/state/tmp/t48g_pin_move.patch:114)

Eu acompanharia com:

- Correção de **23 integralmente iguais → 19 integrais + quatro com cauda opcional**.
- Troca de “uma curva antiga cresce numa operação” por uma descrição dos casos observados: há exceção cashback e nenhuma venda antiga simulada. [patch:21](C:/dev/project-hunter/.claude/state/tmp/t48g_pin_move.patch:21)
- Atualização de `docs/RISK_ENGINE_MEME.md` §9 e criação da revisão T4.8g já citada pelo patch. As referências antigas em testes T4.8e/f, codecs e testes de proveniência são históricas; não devem ser substituídas indiscriminadamente. [RISK_ENGINE_MEME.md:1111](C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:1111)
- Atualização dos context slots sintéticos antigos nos dois `FakeRpc`, para não representarem um deploy posterior ao próprio contexto. [test_program_check.py:74](C:/dev/project-hunter/services/meme-executor/tests/test_program_check.py:74)

**O QUE EU FARIA DIFERENTE**

**F — Fortaleceria a prova causal do aluguel.** O simulador solicita apenas o pós-estado do pagador; não guarda o pós-estado da curva. O pré-saldo vem de outra chamada RPC. Logo, **76.200 = 15 × 5080 é evidência consistente com realocação, mas não demonstra sozinho destino e causa do débito**. Movimento concorrente da carteira entre as leituras pode contaminar o residual. Capturaria curva e pagador antes/depois, mensagem sem assinatura e resposta bruta. [t48g_simulate_curve.py:46](C:/dev/project-hunter/.claude/state/tmp/t48g_simulate_curve.py:46), [t48g_simulate_curve.py:65](C:/dev/project-hunter/.claude/state/tmp/t48g_simulate_curve.py:65)

Também ligaria o artefato aos bytes construídos: hoje o teste valida o resumo JSON; uma mudança futura no builder pode deixá-lo verde sem reproduzir a simulação. [test_simulation_proof_t48g.py:29](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_simulation_proof_t48g.py:29)

**CONCORDO COM**

Manter os três programas vigiados, não inferir compatibilidade pelo hash da IDL e aceitar as legadas conforme a evidência disponível. Após corrigir o limite de linhas, **não vejo bloqueio técnico adicional ao pino nas condições restritas propostas**. Reabrir entradas exige tratar a reserva e cumprir os requisitos anteriores.

**OBSIDIAN**

- **T4.8g-upgrade-08-10** — registrar aceite restrito, 19/45 igualdades integrais, lacunas e distinção entre aluguel inferido e comprovado.
- **Exchange Adapters** — acrescentar os três slots e compatibilidade observada dos layouts.
- **Open Bugs** — registrar reserva sem custo de crescimento da curva como condição para religamento.
- **t48f-pin-move** — acrescentar ligação para a T4.8g, preservando as condições anteriores.
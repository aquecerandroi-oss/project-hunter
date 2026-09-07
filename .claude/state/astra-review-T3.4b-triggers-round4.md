**RESUMO**

**Sim. Resta um MUST-FIX ALTA: um stop observado após um alvo parcial pode expirar antes da próxima avaliação.** Reproduzi em memória.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

`uv run pytest packages/core/tests/unit/execution/test_triggers.py -q`, com bytecode e cache desativados:

```text
34 passed in 1.39s
```

**MUST-FIX**

Posição LONG de 10 unidades, stop `95`, alvo parcial `110` para 4 unidades. Política padrão de 10 segundos, watermark inicial `99`, `tape_gap=False`, nenhum defeito.

Lote sintético, nessa ordem; timestamps em **2026-09-07 UTC**:

| ID | Preço | ts | received_at |
|---|---:|---|---|
| 100 | 110 | 12:00:00.000 | 12:00:09.000 |
| 101 | 90 | 12:00:00.100 | 12:00:09.000 |

- **Ciclo 1, `now=12:00:10`:** ambos utilizáveis; stop com idade `9,9 s`. Publica somente `target`, ID `100`, watermark `100`.
- **Ciclo 2, `now=12:00:11`:** reapresentando o lote para as 6 unidades restantes, retorna `unavailable/stale_trade`, ID `101`, idade `10,9 s`, watermark `100`.
- **Ciclo 3, `now=12:00:12`:** continua `unavailable/stale_trade`, idade `11,9 s`. Esse toque não volta a ser publicável.

Causa: [_first_crossing retorna o primeiro cruzamento em triggers.py:225](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:225), e [check_triggers publica apenas esse resultado em triggers.py:170](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:170). Na chamada seguinte, [tape.py:111](C:/dev/project-hunter/packages/core/hunter_core/execution/tape.py:111) rejeita o stop pela idade.

O [teste de alvo seguido de stop em test_triggers.py:198](C:/dev/project-hunter/packages/core/tests/unit/execution/test_triggers.py:198) reutiliza o mesmo `NOW`; por isso não exercita essa expiração.

**NICE-TO-HAVE**

Nenhum adicional neste escopo.

**O QUE EU FARIA DIFERENTE**

Preservaria os cruzamentos já observados como utilizáveis para processamento em ordem, sem depender de sua validade temporal no próximo ciclo. O alvo parcial continua vindo antes do stop.

**CONCORDO COM**

As correções de [gap em triggers.py:150](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:150) e [parsing em tape.py:92](C:/dev/project-hunter/packages/core/hunter_core/execution/tape.py:92) resolvem os dois cenários da rodada 3.

**OBSIDIAN**

- **Execution Engine** — registrar que cruzamentos observados precisam sobreviver à expiração entre avaliações após alvo parcial.
- **Revisoes-Astra/T3.4b** — acrescentar o lote e a reprodução da quarta rodada.
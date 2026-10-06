**RESUMO**

Não são totalmente equivalentes: confirmei **duas regressões em G**, com parâmetros excepcionais. Revisão somente leitura, como `quant-engineer`.

**ARQUIVOS**

Nenhum modificado. Os sete arquivos examinados têm ≤350 linhas.

**TESTES**

`uv run pytest packages/indicators/tests/meme/test_wallets_cpu.py packages/indicators/tests/meme/test_wallets_golden.py -q`

Saída: **`13 passed in 8.62s`**. Caches desabilitados. Comparação adicional com o HEAD executada em memória:

**MUST-FIX**

1. **Piso calculado antes da cotação muda recusas e sua ordem** — [policy.py:161](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:161). Com `stop_fraction=Decimal("sNaN")`:
   - Evento pós-entrada com curva concluída: HEAD retorna `censored/time_cap`; diff lança `InvalidOperation`.
   - Evento pós-entrada com reserva real `-1`: HEAD lança `ValueError`; diff lança `InvalidOperation`.

   Calcular o piso somente após uma cotação retornar valor, preservando a precedência anterior.

2. **Comparação passou a depender do contexto Decimal ambiente** — [policy.py:70](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:70). Com `stop_fraction=Decimal("NaN")` e trap ambiente de `InvalidOperation` desativado: HEAD lança `InvalidOperation`; diff retorna `closed/time_cap`. Preservar `localcontext(CONTEXT)` também na comparação.

**NICE-TO-HAVE**

Nenhum adicional.

**O QUE EU FARIA DIFERENTE**

Acrescentaria essas três reproduções aos testes de equivalência; a suíte atual passou apesar delas.

**CONCORDO COM**

O limite estrito de slot, identidades duplicadas e wallets repetidas estão preservados pelos índices ([pricing.py:193](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:193), [pricing.py:242](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:242)). A chave de dois inteiros cobre a conversão com contexto fixo ([pricing.py:85](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:85)); não identifiquei índice desatualizado no fluxo atual ([stream_mint.py:194](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:194)).

**OBSIDIAN**

- **carteiras-lucro-design** — registrar as regressões de ordem de exceções e contexto Decimal encontradas na otimização do stop.
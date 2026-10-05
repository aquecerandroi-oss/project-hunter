**REQUEST_CHANGES — conserto 2 ainda tem duas falhas reproduzidas:**

- **Regressão:** compra no slot 100 chega às 41,5 s; venda de apenas **40%** no slot 101 chega às 40,5 s. `_leader_exit` compara a venda com `bought=0` e preserva `leader_sold`, pousando no **106**, embora o limiar nunca tenha sido atingido. [policy.py:98](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:98).
- **Correção incompleta:** compra anterior de 80 tokens, venda desses 80 no slot 90 recebida aos 60 s e gatilho de mais 20 no slot 100. Quando a venda chega, já são **80% vendidos**, mas o filtro `event.slot < trigger.slot` impede a reação: retorna `time_cap/9110`, em vez de `leader_sold/151`. [policy.py:105](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:105).

**Testes:** `uv run pytest packages/indicators/tests/meme -q -p no:cacheprovider` → `78 passed in 2.48s`. Reproduções adicionais somente em memória; nenhum arquivo alterado.

**OBSIDIAN**

- **carteiras-lucro-design** — registrar os dois casos residuais de causalidade da saída.
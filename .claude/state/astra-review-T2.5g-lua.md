### MUST-FIX

**Na troca de dono com sobreposição, `sym:` pode conservar o início do dono antigo após sua saída.** O script sobrescreve o valor compartilhado ([coverage_publish.py:102](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage_publish.py:102)), mas reconcilia somente a presença do símbolo, sem reconstruir seu valor pelo dono sobrevivente ([coverage_publish.py:147](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage_publish.py:147)).

Cenário concreto:

- A cobria X desde 12:00, mas sua cobertura congelou em 12:10:00.
- B assume X às 12:10:05 e publica esse início.
- A, ainda com X na lista e cobertura congelada, publica novamente: sobrescreve `sym:X` com 12:00. Esse comportamento é permitido pelo [stamp:309](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:309).
- A retira sua reivindicação antes do próximo stamp de B. X permanece porque B o reivindica; o início antigo permanece também.
- Com os demais shards atualizados, `covered_until` avança para a prova de B. O leitor pode aceitar uma janela atravessando **12:10:00–12:10:05**, período sem cobertura: seu `max` não recupera o início de B perdido ([leitor:99](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/coverage.py:99)).

Correção: guardar o início por símbolo **por shard** e recalcular o valor publicado quando retirar um dono. Esse achado depende de sobreposição durante transferência; quatro donos estritamente exclusivos não o acionam.

### CONCORDO COM

- **MIN/MIN é conservador com propriedade exclusiva:** `sym_since = max(sessão do dono, assinatura)` preserva o início correto ([stamp:321](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:321)); o mínimo dos finais não ultrapassa a prova do dono ([coverage_publish.py:130](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage_publish.py:130)).
- Não identifico erro Lua 5.1 com `unpack` de aproximadamente 200 argumentos, nem no padrão que separa pelo último `:` ([coverage_publish.py:108](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage_publish.py:108)).
- `HKEYS` custa uma varredura por stamp, mas não demonstra falha nessa escala. As duas chaves acessadas estão declaradas no `EVALSHA` ([coverage_publish.py:222](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage_publish.py:222)); a execução atômica impede interleaving entre scripts. Em Cluster, continua necessário compartilhar slot; o construtor da chave não foi inspecionado.

### OBSIDIAN

- **Página de cobertura do market-worker/scanner:** registrar a condição de propriedade exclusiva e o cenário de transferência acima; título existente não consultado por restrição de escopo.
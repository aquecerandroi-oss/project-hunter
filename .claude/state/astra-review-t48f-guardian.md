**RESUMO**

Como `risk-engine-guardian`: **A e C bloqueiam religar live; D bloqueia aceitar o pino. B é melhoria recomendada.** Mover o pino só pode ser separado de A/C se entradas continuarem efetivamente bloqueadas.

**ARQUIVOS**

Nenhum criado ou modificado. Memória considerada: [T4.8e-upgrade-02-10](obsidian/06-DECISIONS/Revisoes-Astra/T4.8e-upgrade-02-10.md), T4.8e-decoders, KB-0149 e EXP-M18.

**TESTES**

Somente inspeção de arquivos/diff e documentação pública. Não executei testes, mutantes, simulações, assinaturas ou envios nesta rodada.

**MUST-FIX**

- **A — antes de religar entradas cashback. Concordo.** O layout condicional existe em [tx.py:137](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:137), e a compra transporta cashback sem recusá-lo em [build.py:150](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/build.py:150). **Cenário:** compra aceita na curva → migração → venda cashback recusada repetidamente. Exigir simulação dos **nossos bytes**, `sigVerify=false`, detentor com saldo real, `err:null`, evento decodificado e saldos explicados. Conferir também inicialização das contas do accumulator: provar com detentor já inicializado não cobre automaticamente nossa carteira. Sem prova, recusar **novas compras**, preservando tentativas de saída. Não precisa bloquear o pino isoladamente.

- **C — antes de religar live. Concordo, com complementos.** Hoje o boot aborta antes dos loops ([program_check.py:80](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:80), [main.py:275](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:275)). **Cenário:** restart após upgrade deixa posição sem saída, inclusive spot. O flag deve nascer `False` e participar de `program_block`; somente leitura completa **comparada e compatível** o torna `True`. Preserve imediatamente qualquer divergência observada, mesmo que a leitura seguinte falhe. Testar boot divergente/ilegível, recuperação completa, divergência pegajosa e continuidade dos loops. Uma leitura apenas dos slots não pode liberar identidade cujo hash nunca foi validado — é justamente a limitação do caminho atual ([program_check.py:108](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:108)).

- **D — prova reproduzível antes do pino; teste de fiação antes de aceitar a correção.** O nome `test_pumpfun_tx_parity_t48f.py` é irrelevante; falta mecanizar a evidência prometida no [patch:75](C:/dev/project-hunter/.claude/state/tmp/t48f_pin_move.patch:75). **Cenário:** regressão no builder passa pelos testes antigos e o novo deploy é declarado compatível. Acrescentar comparação com fixtures pós-upgrade, incluindo bytes, contas e permissões. Para fiação, concordo: o [teste:37](C:/dev/project-hunter/services/meme-executor/tests/test_signing_gate_t48f.py:37) chama apenas o helper. Exercitar ambos os handlers, introduzir bloqueio depois da admissão e exigir recusa persistida e zero chamadas ao submitter. A reversão para kill-only em [entries.py:253](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:253) ou [launch_entries.py:293](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_entries.py:293) deve falhar. Não executei esse mutante.

**NICE-TO-HAVE**

- **B — cenário real, impacto local não medido.** Tráfego de várias pools pode esgotar a capacidade por conta gravável no ATA compartilhado e adiar nossa venda; o limite existe no [scheduler da Solana](https://solana.com/docs/core/fees/compute-budget). Sortear uma vez entre recipients válidos, congelar no intent e reconstruir dele é seguro. Validar pertinência ao config e ATA correspondente; persistir a escolha também no JSON, que hoje a omite ([pumpswap_build.py:204](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:204)). Não promete eliminar contenção: pool e ATA de protocolo continuam compartilhados, com protocolo também fixado em `[0]` ([pumpswap_build.py:251](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:251)).

**O QUE EU FARIA DIFERENTE**

Separaria formalmente aceite de compatibilidade, continuidade das saídas e autorização de novas entradas. Discordo de usar a simulação da saída como proteção suficiente para **admitir** cashback: ela pode apenas confirmar que ficamos presos.

**CONCORDO COM**

`regravar T4.8g` está coerente com o novo pino T4.8f ([patch:27](C:/dev/project-hunter/.claude/state/tmp/t48f_pin_move.patch:27)); **sem cenário de falha pelo nome**. Ressalva sobre Jupiter: não depender dos nossos builders pump não significa que nenhuma rota use PumpSwap.

**OBSIDIAN**

- **T4.8e-upgrade-02-10** — separar requisitos do pino e do religamento live.
- **T4.8e-decoders** — registrar provas cashback/paridade e testes de fiação pendentes.
- **Open Bugs** — registrar boot só-saídas e risco de admissão cashback sem saída comprovada.
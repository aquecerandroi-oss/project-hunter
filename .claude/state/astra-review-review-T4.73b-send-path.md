**RESUMO**

**DONE_WITH_CONCERNS — manteria o bloqueio de `--apply`.** A leitura pós-simulação e o timeout foram corrigidos no script, mas restam falhas de rastreabilidade e interferência com a tesouraria.

1. **Invariante: sim, para compra e venda.** [meme_spot_swap_send.py:151](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:151) solicita `(wallet, other_ata)`. O parser lê `accounts[0].lamports` e o saldo do token em `accounts[1]`, recusando conta ausente ou ilegível: [treasury_send.py:56](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:56). Os valores alimentam os checks das duas direções antes da assinatura, em [meme_spot_swap_send.py:158](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:158).

2. **Não encontrei desvio que assine/envie sem passar pelo invariante nesse fluxo.** A assinatura está depois da recusa em [meme_spot_swap_send.py:181](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:181). Timeout retorna `submitted`, sem alcançar `mark_confirmed`, e impede a volta: [meme_spot_swap_send.py:211](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:211), [meme_spot_swap.py:222](C:/dev/project-hunter/infra/scripts/meme_spot_swap.py:222). **Porém, outro escritor pode alterar essa linha**, conforme achado abaixo.

3. **Commit-as-you-go é válido em SQLAlchemy 2.x.** A conexão sem `begin()` envolvente em [meme_spot_swap.py:269](C:/dev/project-hunter/infra/scripts/meme_spot_swap.py:269), com `await conn.commit()` em [meme_spot_swap_db.py:108](C:/dev/project-hunter/infra/scripts/meme_spot_swap_db.py:108), usa corretamente o autobegin. Uma exceção posterior não desfaz commits concluídos. Isso está documentado em [AsyncConnection.commit](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncConnection.commit). **Não torna atômicos o envio on-chain e a persistência.**

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisados os quatro arquivos solicitados e os consumidores relevantes da tabela compartilhada.

**TESTES**

Não executei testes nesta revisão estritamente somente leitura; não afirmo aprovação da suíte.

O teste novo cobre compra, recusa, timeout e erro durante confirmação, mas seu fluxo usa SOL→WIF: [test_meme_spot_swap_send.py:269](C:/dev/project-hunter/infra/scripts/tests/test_meme_spot_swap_send.py:269). Falta exercitar a venda completa e as falhas durante envio/persistência.

**MUST-FIX**

- **[meme_spot_swap_send.py:189](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:189) — ALTA — envio ambíguo vira `failed`, sem assinatura persistida.** Cenário: o RPC recebe e transmite a transação, mas a resposta sofre timeout. O `except` grava `failed` e retorna assinatura `None`, embora a compra possa confirmar. Outro cenário: envio retorna normalmente, mas `mark_submitted` falha antes do commit; sobra `simulated` sem assinatura. Uma repetição manual pode comprar novamente. Persistir a assinatura derivada localmente **antes** do broadcast e conservar estado reconciliável em falhas ambíguas.

- **[treasury_db.py:47](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:47) — ALTA — o reconciliador da tesouraria também seleciona swaps spot.** Não filtra `input_mint`/`output_mint`. Cenário: compra SOL→WIF termina o prazo como `submitted`, confirma depois e é recolhida pelo executor. [treasury_reconcile.py:73](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:73) grava `confirmed` com `max(0, saldo_SOL_atual − saldo_SOL_anterior)`, normalmente **zero**, sem medir WIF. Portanto, a promessa de deixar a linha para reconciliação manual não vale para o repositório inteiro. A seleção também permite corrida com a confirmação do próprio script.

- **[meme_spot_swap_send.py:119](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:119) — ALTA — átomos de token entram na contabilidade de SOL da tesouraria.** O script grava saída cotada/preenchida em unidades atômicas, mas [treasury_db.py:42](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:42) soma todas as linhas `submitted`/`confirmed` como entrada de SOL, sem distinguir mints. Cenário: compra recebe `10_402_273` átomos de WIF; o leitor incorpora esse número como SOL no cálculo de perda diária de [treasury_inflow.py:17](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_inflow.py:17), corrompendo o freio. Separar os consumidores da tesouraria dos registros spot.

- **[meme_spot_swap_send.py:214](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:214) — MÉDIA — venda confirmada registra preenchimento zero.** A fórmula sempre mede aumento do token não-SOL. Cenário: venda consome 100 tokens e recebe SOL; calcula `max(0, 0 − 100) = 0`, gravando zero como saída preenchida. Isso também impede a volta de um round trip iniciado token→SOL, pelo check de [meme_spot_swap.py:224](C:/dev/project-hunter/infra/scripts/meme_spot_swap.py:224). Medir a saída correta por direção, preferencialmente pelos metadados da transação confirmada.

**NICE-TO-HAVE**

[meme_spot_swap.py:223](C:/dev/project-hunter/infra/scripts/meme_spot_swap.py:223) — BAIXA — `refused` e `failed` retornam código zero. Cenário: um wrapper interpreta a execução recusada como sucesso. Retornar código não zero para esses estados.

**O QUE EU FARIA DIFERENTE**

Persistiria a assinatura antes do envio; isolaria as linhas spot dos leitores/reconciliadores da tesouraria; acrescentaria testes de venda e de falhas entre broadcast e commit.

**CONCORDO COM**

Reutilizar o parser existente, recusar contas ilegíveis e encerrar explicitamente o caminho `pending` são correções adequadas: [meme_spot_swap_send.py:158](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:158), [meme_spot_swap_send.py:211](C:/dev/project-hunter/infra/scripts/meme_spot_swap_send.py:211).

**OBSIDIAN**

- **Revisoes-Astra — T4.73b:** registrar correções verificadas e os quatro bloqueios restantes.
- **Meme — o que uma “estratégia” é aqui:** documentar a ferramenta spot e sua interferência atual com a tesouraria.
- **Execution Engine:** registrar a regra de persistir identidade da transação antes do broadcast e reconciliar resultados ambíguos.
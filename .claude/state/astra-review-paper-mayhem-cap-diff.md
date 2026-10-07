**RESUMO**

**APPROVE_WITH_NITS.** Concordo com a correção limitada ao teto contábil `real_observado + curve_cost_sol`. Não encontrei novo must-fix no diff. Os quatro pontos anteriores foram atendidos no caminho de venda pela curva; isso não valida a trajetória contrafactual nem a execução Mayhem on-chain.

**ARQUIVOS**

Revisão como `code-reviewer`: li o diff solicitado, o teste novo e os caminhos de construção, persistência e fechamento. Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Executei o `git diff -- …` solicitado, buscas de referências e inspeção do histórico. O `git show f7edcfef:services/meme-worker/hunter_meme_worker/paper_engine.py` confirmou que a entrada já gravava:

```python
"curve_cost_sol": money_str(quote.curve_cost_sol),
```

Não executei pytest, Docker ou os gates nesta revisão somente leitura. Os **2.488 unitários, 19 testes de integração e gates verdes são resultados informados por você**, não reproduzidos por mim.

**MUST-FIX**

Nenhum comprovado para esta correção.

- **(a) Apostas antigas:** os dois construtores de produção recebem o aporte persistido: [lab_repo_bets.py:231](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:231) e [launch_lane_bets.py:172](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_bets.py:172). Uma linha sem a chave realmente produziria `KeyError` antes do processamento das apostas, pois a carga ocorre primeiro em [lab_bets.py:178](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:178). Entretanto, o histórico confirma a chave desde a criação do Lab. **Não exigiria fallback sem evidência de linhas legítimas incompatíveis**, nem usaria zero silencioso, que reintroduziria o defeito.

- **(b) REST, nulo e zero:** reserva nula é rejeitada pelo normalizador em [normalize.py:234](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:234), e a coluna é `NOT NULL` em [meme_radar.py:172](C:/dev/project-hunter/infra/migrations/ddl/meme_radar.py:172). Para Mayhem incompleta com reserva zero, o teto passa corretamente a ser apenas o aporte próprio. Foto completa continua desligando o teto: [lab_values.py:104](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:104). **Um zero incorreto ou `complete` incorreto da fonte ainda pode distorcer a marca**, mas não encontrei evidência de um novo defeito introduzido pelo diff nessa fronteira.

**NICE-TO-HAVE**

1. **Provar o gatilho corrigido, além do recebimento.** O teste da foto idêntica chama diretamente `close_bet(..., "max_loss", ...)`; demonstra a correção do valor, mas não que aquela foto deixou de disparar `max_loss`. Acrescentaria a asserção sobre `decide_exit` em [test_mayhem_own_buy_cap.py:103](C:/dev/project-hunter/services/meme-worker/tests/test_mayhem_own_buy_cap.py:103).

2. **Teste explícito de transição com recarga:** entrada sem `sell_cap_model`, aporte presente e intenção antiga preservada; depois verificar aporte carregado e versão na saída. O teste atual de versionamento verifica apenas a entrada nova em [test_mayhem_own_buy_cap.py:173](C:/dev/project-hunter/services/meme-worker/tests/test_mayhem_own_buy_cap.py:173).

3. **Precisar “every new entry and exit” na documentação.** A versão aparece no fechamento pela curva, mas não nas saídas por pool ou sem snapshot. Isso importa para uma consulta que tente classificar todas as transições somente pelo marcador: [lab_values.py:46](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:46), [pool_mark.py:169](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/pool_mark.py:169) e [paper_engine.py:286](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:286). Eu documentaria esse alcance.

**O QUE EU FARIA DIFERENTE**

Manteria o patch pequeno e acrescentaria os dois testes acima. Não ampliaria agora para reconstrução das reservas virtuais ou saldo compartilhado entre pernas.

**CONCORDO COM**

- Hipótese de fluxos externos preservados e pernas independentes explicitadas: [lab_values.py:99](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:99).
- Soma sob `localcontext(CONTEXT)`, sem introduzir `float`: [lab_values.py:109](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:109).
- Marca e fechamento usam o mesmo teto, aplicado ao bruto antes das taxas: [paper_engine.py:132](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:132), [paper_engine.py:234](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:234) e [curve.py:308](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:308).
- Intenções existentes são preservadas antes de avaliar novos gatilhos: [lab_bets.py:209](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:209).
- A investigação relatada dos 23 casos não contradiz a prova sob suas premissas; não reproduzi essa consulta.

**OBSIDIAN**

- **KB-0189 — O papel não sabe medir a moeda Mayhem:** registrar a correção limitada, a versão e os residuais de trajetória virtual e venda on-chain.
- **Open Bugs:** separar a omissão do aporte dos residuais; registrar implantação e evidência quando ocorrerem.
- **EXP-M23 — Desfecho das recusadas:** acrescentar o corte do instrumento e o tratamento das apostas de transição, preservando avaliações anteriores.
- **Revisões-Astra — paper-mayhem-cap:** registrar este parecer e as lacunas de teste não bloqueantes.
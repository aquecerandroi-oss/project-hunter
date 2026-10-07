**RESUMO**

**APPROVE_WITH_NITS — nenhum must-fix identificado no diff.** Revisão como `code-reviewer`, somente leitura. A correção corresponde ao desenho: aporte sem taxas, obrigatório, e teto compartilhado entre marca e saída.

1. **O teto pode morder em curva padrão?** Com bit conhecido `false`, não existe teto. Com bit desconhecido, não deve morder numa trajetória padrão consistente: `virtual_sol = 30 + real_sol`, produto constante entre entrada e saída e tokens provenientes daquela compra. Nessas condições, o máximo de `venda_bruta − real_sol` ocorre no piso e fica abaixo do aporte. A diferença `virtual − real = 30`, **sozinha**, não prova isso se as reservas de tokens forem inconsistentes. Referências: [executable.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/executable.py:108), [curve.py:172](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:172).

2. **Construtores/carga de produção:** encontrei dois; ambos passam o valor correto: [lab_repo_bets.py:231](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:231) e [launch_lane_bets.py:172](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_bets.py:172). Os dois produtores de entrada gravam a chave: [paper_fill.py:188](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:188) e [launch_lane_bets.py:89](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_bets.py:89). Conferi também sua existência no produtor histórico em `f7edcfef`. Não consultei o banco de produção; uma linha adulterada sem essa chave causaria `KeyError` na carga. Não recomendo fallback silencioso para zero.

3. **Decimal/float/UTC:** nenhuma regressão encontrada. A soma usa `localcontext(CONTEXT)`; a carga rejeita `float`; a pista converte a string produzida pela própria entrada. Os campos novos não alteram timestamps. Referências: [lab_values.py:110](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:110), [lab_params.py:51](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:51), [paper_engine.py:260](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:260).

4. **Leitores de JSON:** não encontrei quebra. Os leitores da API selecionam campos explicitamente, sem rejeitar chaves adicionais: [meme_tests.py:106](C:/dev/project-hunter/apps/api/hunter_api/services/meme_tests.py:106), [meme_tests.py:124](C:/dev/project-hunter/apps/api/hunter_api/services/meme_tests.py:124), [meme_desk_out.py:230](C:/dev/project-hunter/apps/api/hunter_api/services/meme_desk_out.py:230). Os carimbos ficam persistidos, mas essas projeções não os expõem.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei os caminhos solicitados, incluindo `test_mayhem_own_buy_cap.py`, que está **não rastreado** e não aparece no `git diff` comum.

**TESTES**

`git diff --check -- <arquivos rastreados do escopo>`: sem saída de erro.

Não executei pytest, lint ou typecheck nesta revisão estritamente sem escrita. Não estou ratificando resultados de execuções anteriores.

A regressão principal está bem representada: foto idêntica, recebimento pela fórmula e ausência do antigo disparo de `max_loss`: [test_mayhem_own_buy_cap.py:103](C:/dev/project-hunter/services/meme-worker/tests/test_mayhem_own_buy_cap.py:103).

**MUST-FIX**

Nenhum achado com cenário concreto de falha introduzida pelo diff.

**NICE-TO-HAVE**

- **Recarga e transição:** persistir entrada sem carimbo, recarregar e conferir aporte exato, teto e carimbo da saída. O teste atual verifica somente o carimbo de uma entrada nova: [test_mayhem_own_buy_cap.py:178](C:/dev/project-hunter/services/meme-worker/tests/test_mayhem_own_buy_cap.py:178).
- **Pista de lançamento:** acrescentar asserções dos dois carimbos e de `exit.own_curve_sol == entry.curve_cost_sol`. A integração existente verifica fechamento, motivo e fonte: [test_launch_lane_integration.py:222](C:/dev/project-hunter/services/meme-worker/tests/test_launch_lane_integration.py:222).
- **Sonda versus escala:** testar aportes diferentes no mesmo mint, comprovando que cada perna usa somente o próprio aporte, conforme o contrato de [lab_values.py:101](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:101).
- **Curva padrão:** variar entrada e saída, incluindo retorno ao piso; o teste atual usa a mesma foto quase vazia. Explicitar também `k` constante nos docstrings: [test_mayhem_own_buy_cap.py:140](C:/dev/project-hunter/services/meme-worker/tests/test_mayhem_own_buy_cap.py:140), [curve.py:304](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:304).

**O QUE EU FARIA DIFERENTE**

Priorizaria o teste de recarga com transição: ele cobre a fronteira entre persistência antiga e comportamento novo. Manteria a trajetória contrafactual das reservas como tarefa separada.

**CONCORDO COM**

Usar o aporte líquido de taxas e centralizar o teto em `_cap`: [paper_engine.py:133](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:133). Também concordo com declarar o modelo contábil e limitar o alcance do carimbo às saídas pela curva: [lab_values.py:46](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:46).

**OBSIDIAN**

- **paper-mayhem-cap** — acrescentar esta revisão, suas lacunas de cobertura e a ausência de execução de testes nesta rodada.
- **KB-0189 — O papel não sabe medir a moeda Mayhem** — explicitar as hipóteses completas da prova para curva padrão.
- **EXP-M23 — Desfecho das recusadas** — manter a separação entre coortes antigas, de transição e posteriores ao deploy; esta revisão não revalida resultados históricos.
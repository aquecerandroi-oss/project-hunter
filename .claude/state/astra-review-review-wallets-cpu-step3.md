**RESUMO**

**REQUEST_CHANGES.** A equivalência contábil está preservada para entradas válidas nos cenários verificados. Os bloqueios são o encerramento interrompido e a prova insuficiente de concorrência real.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Referência: `HEAD 38da8512`.

**TESTES**

Executei, com escrita de bytecode/cache desabilitada:

```text
uv run pytest packages/indicators/tests/meme/test_wallets_stream_parallel.py -q
24 passed in 207.74s (0:03:27)
```

Sondas adicionais em memória:

- `stream.py` carregado diretamente do `HEAD`: igualdade nas **23 noites** dos cinco mundos.
- `Sleepy`, sementes 0–3: **um único PID executou X, H e Y em cada rodada**.
- Interrupção injetada em `terminate`, executor real: a chamada escapou com **dois filhos vivos**.
- Falha de pickle: filho vivo imediatamente após o retorno, mas encerrado por `EOFError` em menos de cinco segundos.
- Coordenador morto à força: worker continuava vivo após 1,5 segundo.

Todos os processos das sondas foram encerrados. Não executei lint/typecheck completos.

**MUST-FIX**

1. **HIGH — segundo Ctrl+C interrompe a própria limpeza.**  
   Em [stream_parallel.py:124](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:124), `is_alive()` e `terminate()` ficam fora da proteção; somente o laço de `join` captura interrupções.

   **Cenário:** primeiro Ctrl+C leva a `abort_pool`; segundo Ctrl+C chega antes de terminar o primeiro worker. `_stop` escapa, os outros workers continuam vivos e `shutdown` não é chamado. Reproduzi com pool real:

   ```text
   REAL_ABORT_RETURNED [(21968, True), (29456, True)]
   ```

   Corrigir a limpeza inteira, adiando a propagação da interrupção até terminar e esperar todos os processos. Garantir também a execução do fechamento do executor quando `_stop` relançar a interrupção — hoje ela pula a linha seguinte em [stream_parallel.py:141](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:141). Acrescentar regressão no laço de término, além da existente para `join`.

2. **MEDIUM — o teste de conclusão embaralhada passa sem concorrência entre workers.**  
   [stream_fetch.py:33](/C:/dev/project-hunter/packages/indicators/tests/meme/stream_fetch.py:33) limita o atraso a 30 ms; [test_wallets_stream_parallel.py:169](/C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel.py:169) não verifica PIDs nem que alguma ordem foi efetivamente invertida.

   **Concordo com sua observação e a reproduzi:**

   | Semente | PID que executou os três mints |
   |---|---:|
   | 0 | 19944 |
   | 1 | 10644 |
   | 2 | 5712 |
   | 3 | 23040 |

   **Cenário de falha:** uma regressão específica da chegada concorrente dos resultados permanece invisível, enquanto o teste continua alegando cobertura. Além disso, `done.pop()` pode reordenar resultados já concluídos **mesmo quando um único processo executou tudo** ([stream_parallel.py:68](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:68)).

   **Conserto mínimo:** conservar os três mints, usar dois workers e uma barreira com timeout no primeiro `fetch` de cada worker; registrar e exigir dois PIDs distintos. Para provar inversão, bloquear o primeiro mint com um `Event`, liberado pelo coordenador ao receber o segundo. Assertar a inversão e a igualdade integral do resultado. Mais mints ou sleeps maiores apenas aumentam a probabilidade; não garantem a condição.

3. **LOW — limite literal de 350 linhas excedido no teste.**  
   [test_wallets_stream_parallel.py:355](/C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel.py:355) termina na linha **355**. O gate exclui testes ([check_file_size.py:34](/C:/dev/project-hunter/infra/scripts/check_file_size.py:34)), portanto pode ficar verde apesar de descumprir o limite solicitado. Ajustar sem aumentar o orçamento. Os sete módulos de produção revisados estão abaixo de 350.

**NICE-TO-HAVE**

- **Falha de pickle no spawn:** existe uma lacuna de rastreamento, mas **não reproduzi órfão persistente**. No Windows, o CPython cria o processo antes de serializar os argumentos; ele ainda não está em `_processes` quando essa serialização falha. Minha sonda mostrou `tracked=0`, `active_children=0`, mas filho temporariamente vivo; depois saiu com `EOFError`. Isso também mostra que `active_children()==[]` sozinho não prova ausência de filhos nessa fronteira. A interface já exige `fetch` serializável ([stream_parallel.py:47](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:47)); testar a recusa antecipada seria útil. [Fonte CPython 3.12](https://raw.githubusercontent.com/python/cpython/3.12/Lib/multiprocessing/popen_spawn_win32.py).

- **Morte dura do coordenador:** o risco é real; o worker continua executando. `_start` não instala supervisão do pai ([stream_parallel.py:160](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:160)), e o worker do PPE não monitora o pai durante a tarefa. Isso pede supervisão externa da árvore de processos ou mecanismo específico no worker. **Não classifico como falha de `abort_pool`: matar o coordenador impede que ele execute qualquer limpeza.** Deve virar requisito explícito da integração operacional. [Fonte CPython 3.12](https://raw.githubusercontent.com/python/cpython/3.12/Lib/concurrent/futures/process.py).

- **`_processes` ausente:** o fallback silencioso em [stream_parallel.py:116](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:116) esconderia incompatibilidade. Porém o projeto restringe Python a 3.12 ([pyproject.toml:4](/C:/dev/project-hunter/pyproject.toml:4)); não há contraexemplo demonstrado na versão suportada. Preferiria falha explícita diante de executor incompatível.

**O QUE EU FARIA DIFERENTE**

Separaria duas provas: **redução em qualquer ordem**, já exercitada pelas permutações, e **execução efetiva em processos distintos**, que precisa da sincronização acima. Manteria os testes de encerramento com executor real e verificação dos processos capturados antes da falha.

**CONCORDO COM**

1. **`plan_night` / `replay_one` / `finish_night` preservam o comportamento válido.**  
   O teto continua global por entidade/dia, antes da distribuição ([stream.py:134](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:134)). Acrescentar `mint` depois de `(decision_order, identity)` não muda a seleção quando a identidade identifica um único evento. `mint_night` apenas projeta apostas e sementes daquele mint ([stream.py:181](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:181)).

   **Ressalva concreta:** fabricar a mesma identidade em A e B, com teto 1, faz o antigo reproduzir ambos e o novo somente A; reproduzi isso. É uma identidade conflitante, incompatível com a definição de evento em [tape.py:95](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:95), não uma regressão demonstrada para fita válida. Empate em `decision_order` com identidades distintas preservou a seleção.

2. **Nenhum campo de `EntityTally` ficou esquecido.**  
   Todos os acumuladores são combinados; `days` é validado, não somado ([stream_metrics.py:115](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:115)). `CopyTally` soma seus quatro campos ([stream_mint.py:84](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:84)). Não encontrei inexatidão nos resultados para partes válidas e disjuntas. A ordem física de `holds` muda; seu multiconjunto e a mediana permanecem iguais.

3. **O alias de `EntityTally` é intencional e não encontrei reutilização incorreta.**  
   `Tallies.merge` documenta que consome `other` ([stream_mint.py:100](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:100)). Worker e coordenador não voltam a usar os livros consumidos; as permutações clonam cada parte antes do merge ([test_wallets_stream_parallel.py:150](/C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel.py:150)). Reutilizar partes sem clonagem seria incorreto, mas esse cenário não aparece nos chamadores examinados.

**OBSIDIAN**

- **wallets-cpu-step3** — acrescentar esta revisão: interrupção em `terminate`, concorrência não demonstrada pelo `Sleepy` e distinção entre filho transitório e órfão persistente.
- **wallets-cpu** — corrigir a afirmação de conclusão embaralhada comprovada e registrar o requisito de supervisão após morte do coordenador.
- **Open Bugs** — registrar o encerramento interrompido que retorna com workers vivos, vinculado à revisão.

Nenhuma dessas páginas foi alterada, conforme o modo OPINIÃO.
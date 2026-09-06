**RESUMO**
**REQUEST_CHANGES**, como `code-reviewer`: há falhas no fecho AST, na sucessão repetida e na interpretação de gaps.

**ARQUIVOS**
Nenhum criado ou modificado.

**TESTES**
Não executados nesta revisão somente leitura; os “150 passed” são o resultado informado por você, não uma execução minha.

**MUST-FIX**

- **(a) HIGH — O AST aceita dependências que não captura.** `importlib.import_module("hunter_core.strategies.helper")` não entra no fecho; `from hunter_core.strategies.calc.impl import X` procura apenas `calc.py`, descartando o subpacote. Depois de congelar uma estratégia assim, alterar `helper.py`/`calc/impl.py` muda a execução sem mudar o digest. Rejeite essas construções ou resolva-as: [code_ref.py:102](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:102), [code_ref.py:145](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:145).
- **(b) HIGH — O segundo supersede não funciona.** Após v1→v2 apontando para `momentum_v1`, outra alteração exige v2→v3; porém o script procura `momentum_v2/v2` no registry e recusa. Se esse registro for acrescentado depois, o worker passa a rejeitar a v2 existente por conflito com seu módulo congelado. Compartilhe a resolução e valide também a identidade da sucessora: [activate_strategy_version.py:209](C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:209), [catalogue.py:174](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/catalogue.py:174).
- **(c) HIGH — `failed` não significa irrecuperável.** Cinco falhas transitórias censuram imediatamente, mas o coletor reabre após uma hora; se recuperar depois, o outcome já foi encerrado injustamente. Além disso, reabrir não atualiza `detected_at`: após uma parada longa, um gap recém-reaberto pode ser julgado `stalled`. Referências: [gaps.py:108](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/gaps.py:108), [recovery.py:44](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:44), [recovery.py:88](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:88).

**NICE-TO-HAVE**
Corrigir “ambos erram para o lado seguro”: a exclusão de dependências permite precisamente código alterado com digest igual — [code_ref.py:19](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:19).

**O QUE EU FARIA DIFERENTE**
Usaria prazo total durável por minuto faltante, distinguindo cooldown de abandono definitivo. **(d)** A perda de avaliações permanece: versões recusadas ficam fora de `due`, mas a mensagem recebe ACK; corrigir o catálogo depois não recupera essas avaliações. As gauges dão visibilidade, não preservação: [consumer.py:115](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:115), [consumer.py:183](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:183).

**CONCORDO COM**
**(b)** Não encontrei violação da trigger pelo supersede: copia os campos congelados, altera apenas o ciclo de vida da antiga e usa uma transação. O bloqueio acima é operacional, não corrupção desses campos: [activate_strategy_version.py:230](C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:230), [activate_strategy_version.py:278](C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:278), [shadow.py:47](C:/dev/project-hunter/infra/migrations/ddl/shadow.py:47).

**OBSIDIAN**

- **Strategies** — registrar limites do AST e sucessão repetida com identidade de implementação.
- **Market Collector** — explicitar que `failed` tem retry e distinguir idade de inatividade.
- **Workers** — documentar avaliações não recuperáveis após ACK durante incompatibilidade.
**RESUMO**

**Peço dois ajustes: um de domínio da equivalência e outro de memória.** Não encontrei divergência numérica no cenário padrão revisado. Os **198 testes passaram**.

Revisão como `quant-engineer`, considerando a memória de [wallets-engine](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-engine.md) e o [diálogo de armazenamento](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallet-tape-storage.md).

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os módulos, alterações, testes e benchmark indicados.

**TESTES**

Executei `uv run pytest packages/indicators/tests/meme -q`, com escrita de bytecode/cache e sincronização do ambiente desabilitadas:

```text
198 passed in 30.47s
```

Também executei dois exemplos sintéticos via `uv run python -`, somente em memória, descritos abaixo. Não executei novamente os 18 mutantes, o benchmark completo, lint ou typecheck.

**MUST-FIX**

1. **Recusar `settled < start`, ou preservar informação suficiente para esse caso.**

   `_survey` inicia o horizonte com `carry.max_slot`, sem verificar se esse máximo pertence ao período liquidado. A entrada aceita parâmetros que invalidam essa premissa. [stream.py:189](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:189), [stream.py:250](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:250).

   **Reprodução:** origem em 06/10 UTC, uma compra no slot 100 em `origem + 100s`, janela de dois dias e `settle_seconds=259200`. Após avançar uma noite e fazer roundtrip JSON:

   ```text
   2026-10-08 stream_horizon= -1 batch_horizon= -1 equal= True
   2026-10-09 stream_horizon= 100 batch_horizon= -1 equal= False
   ```

   O slot carregado ainda não está liquidado segundo esses parâmetros. **Não afeta o padrão de dois segundos**, mas quebra a equivalência da API aceita. Eu acrescentaria uma recusa explícita quando `cut − settle_seconds < start` e esse teste de regressão.

2. **A saída precisa permitir descarregar os carries por mint.**

   A entrada pode ser iterada, mas a terceira passada acumula todos os `MintCarry` em `carries` e os devolve numa tupla. Portanto, o carry inteiro da campanha permanece residente. [stream.py:263](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:263), [stream.py:291](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:291).

   **Cenário executado:** cada mint recebe uma compra e uma venda que zeram o inventário; depois todos saem da janela:

   ```text
   historical_mints= 10  window_fills= 0 snapshot_rows= 0 retained_carries= 10  retained_flows= 10
   historical_mints= 100 window_fills= 0 snapshot_rows= 0 retained_carries= 100 retained_flows= 100
   ```

   Preservar esse histórico é correto; **materializá-lo todo na saída elimina a garantia de memória por mint**. Mesmo com janela vazia, a necessidade de RAM cresce com a campanha. Os flows antigos são reconstruídos no avanço. [stream_mint.py:119](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:119).

   Para a finalidade de escala do 1c-bis, eu permitiria emitir cada carry a um consumidor, mantendo a coleta em tupla como conveniência dos testes. Não medi OOM nem afirmo um limite concreto de capacidade.

**NICE-TO-HAVE**

Sobre **(e), o benchmark**, acrescentaria:

- **RSS máximo em processo isolado, com fonte realmente iterada**, incluindo entrada, carry anterior, saída e serialização. Hoje a fita e as janelas são preparadas antes de começar a medição; o pico é de alocações Python durante a chamada, não memória residente total. [benchmark:149](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallets-engine-bench.py:149), [benchmark:165](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallets-engine-bench.py:165).
- **Janela fixa de sete dias e campanha progressivamente mais longa**, variando separadamente lotes, flows históricos, entidades, maior mint e posses por entidade. Dividir todo o pico por entidades e chamá-lo de custo dos *tallies* mistura estruturas diferentes. [benchmark:228](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallets-engine-bench.py:228).
- **Rajadas de compradores no mesmo slot e transações multimint.** Os pares crescem quadraticamente com compradores por slot; fills multimint ficam retidas globalmente em `survey.shared`. O gerador do benchmark usa uma assinatura nova por fill. [stream.py:126](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:126), [stream.py:203](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:203), [benchmark:104](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallets-engine-bench.py:104).
- **Pico da mediana**, além dos oito bytes persistentes por posse: `metrics()` converte o array em lista antes de calcular a mediana. [stream_metrics.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:110).

**O QUE EU FARIA DIFERENTE**

Fecharia primeiro a recusa do domínio inválido e a emissão incremental dos carries. Depois mediria CPU e memória separadamente por passada, incluindo leitura e escrita no armazenamento. Não alteraria as fórmulas para resolver escala.

**CONCORDO COM**

- **(a) Links fracos prontos:** correto **para o retrato corrente e os seguintes**. Uma evidência posterior pode antecipar retrospectivamente o `known_at` mínimo do batch, mas o link carregado já era conhecido antes do corte anterior. Ambos estão ativos no corte atual. A versão de entidades depende dos grupos, não da proveniência do link. Isso não promete igualdade dos metadados históricos do link. [stream.py:141](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:141), [entities.py:107](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:107).

- **(b) `_bets`:** não encontrei diferença dentro do contrato. A primeira compra qualificante marca `seen` mesmo se recusada; abaixo do mínimo não marca. Como há uma oportunidade por entidade/mint e o ledger do C-PnL é por entidade, o cooldown não elimina uma segunda candidata válida. Manter os primeiros N por dia equivale ao teto sequencial; a exclusão histórica continua posterior à admissão. [stream.py:225](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:225), [follow.py:148](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:148), [ranking.py:107](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:107).

- **(c) P1:** suficiente **por indução**, com carry íntegro, noites consecutivas e entrada completa/canônica. `received == sealed_until` precisa ser recusado porque o corte anterior foi estrito. É necessário para garantir equivalência geral sem reabrir o prefixo; não significa que toda violação necessariamente alteraria um retrato específico. [stream.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:108), [stream_mint.py:133](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:133).

- **(d) Duplicatas:** aceitável como responsabilidade do armazenamento, preservando identidade completa, recepção vencedora e payload canônico. “Uma vez” deve significar uma ocorrência lógica na fita; as mesmas fills naturalmente reaparecem nas janelas sobrepostas. O contrato já delega essa responsabilidade. [carry.py:25](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:25).

- Concordo com os dois relógios, as sementes separadas por dono e a mediana exata com oráculo independente. [stream_mint.py:127](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:127), [stream.py:256](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:256), [stream_metrics.py:94](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:94).

**OBSIDIAN**

- **wallets-engine** — Registrar os 198 testes, o domínio `settled ≥ start` e a equivalência de entidades sem igualdade da proveniência dos links.
- **Diálogo: armazenamento da fita de carteiras do H-030** — Acrescentar carry de saída residente e temporários da mediana ao orçamento.
- **Revisão Astra: wallets-1c-bis** — Registrar os dois achados e suas reproduções.

Nenhuma página foi alterada.
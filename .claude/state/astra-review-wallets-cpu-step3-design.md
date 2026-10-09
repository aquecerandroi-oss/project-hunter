**RESUMO**

Concordo com a decomposição por mint e com a redução proposta. **Não encontrei campo numérico que exija preservar a ordem entre mints.** Há dois pontos a fechar antes da implementação: transporte de `ContractViolation` e consistência entre a fonte das passadas 1–2 e o `fetch`.

Parecer como `quant-engineer`, apoiado no [plano registrado](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md) e na [revisão do passo 2](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-cpu-step2.md).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes nesta revisão; as conclusões abaixo são de inspeção estática. O executor paralelo proposto ainda precisa das provas descritas.

**MUST-FIX**

1. **`ContractViolation` precisa sobreviver à serialização.**

   Seu construtor exige `(reason, detail)`, mas chama `super().__init__` com uma única mensagem; portanto, os argumentos armazenados não permitem reconstruí-la pelo caminho padrão do pickle. Veja [carry.py:85](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:85).

   **Cenário:** `_prepared` lança `received_before_window` dentro do worker. Ao reconstruir a exceção no coordenador, falta `detail`; a recusa nomeada pode virar falha de transporte e `BrokenProcessPool`.

   Eu preservaria explicitamente os argumentos necessários à reconstrução, mantendo a mensagem pública atual. Testaria o roundtrip de pickle e a exceção real atravessando `spawn`, verificando **tipo, `reason` e mensagem**, além da ausência de filhos. Um teste apenas com `RuntimeError` não cobre isso. O pool exige objetos serializáveis na comunicação entre processos. [Documentação Python](https://docs.python.org/3.12/library/concurrent.futures.html#processpoolexecutor)

2. **Nome e contagem não demonstram que `fetch` devolveu a mesma janela.**

   **Cenário:** o survey e as apostas veem uma compra; o worker recebe uma versão corrigida dessa mesma compra, com outros átomos ou reservas. Nome e contagem continuam iguais, mas o replay usa dados diferentes dos que determinaram apostas, entidades ou sementes. Alterar somente `carry` ou `creates` também passa nessa checagem: ambos influenciam o replay. Veja [stream_mint.py:164](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:164).

   Fecharia isso como **contrato explícito de uma fonte imutável por execução**, compartilhada pelas três passadas e pelo `fetch`. O callable pode continuar recebendo apenas o nome, desde que esteja vinculado à versão da fonte. Se essa garantia não existir, será necessário conferir uma identidade de conteúdo que também cubra carry e creates. Não exigiria hash extra se a imutabilidade já estiver garantida; só não trataria `fetch_mismatch` por contagem como prova dessa propriedade.

**NICE-TO-HAVE**

- **Custo do carry no escalonamento.** `eventos × (1 + apostas)` atribui custo zero a um mint sem eventos novos, mesmo com muitos lotes para valorar e flows para avançar. Isso não muda resultados, mas pode deixar o trabalho mais pesado para o fim. Acrescentaria uma estimativa baseada em lotes, fronteira, flows e dias. O trabalho existe em [stream_mint.py:164](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:164) e [stream_mint.py:133](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:133).

- **Permutações reproduzíveis.** Usaria seeds fixas e um caso que force conclusão inversa à ordem da fonte. Nas 50 permutações, compararia campos exatos, multiconjunto de holds e métricas finais: a concatenação muda a ordem interna do array, embora preserve o resultado.

- **Falhas além do worker.** Acrescentaria falha no initializer, no `fetch` e no `emit`. Para trabalhos finitos, cancelar pendentes e aguardar os iniciados permite encerrar sem filhos; `cancel_futures=True` não interrompe tarefas já executando. Um fetch bloqueado precisa de timeout próprio. [Documentação Python](https://docs.python.org/3.12/library/concurrent.futures.html#concurrent.futures.Executor.shutdown)

**O QUE EU FARIA DIFERENTE**

**(a) Redução e existência das entidades.** Manteria exatamente seu desenho, com estas invariantes:

- `days` é metadado comum, não parcela: verificar igualdade e comprimento de `daily`.
- Unir separadamente as chaves de `books`, `copies` e `w_pnl`.
- Não descartar um `EntityTally` porque `episodes == 0`.
- Não criar books a partir das chaves de `copies` ou `w_pnl`.
- Preservar `largest=None`; usar zero como identidade adulteraria um conjunto de episódios exclusivamente negativos.

Uma venda sem inventário cria book sem episódio e ainda contribui para `sold_atoms`/`unmatched_atoms`: [episodes.py:162](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:162), [episodes.py:241](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:241). O serial cria o tally desse book e monta linhas exclusivamente pelas chaves de `books`: [stream_mint.py:182](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:182), [stream.py:296](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:296).

Não encontrei caminho normal que produza W-PnL sem book: ambos partem dos mesmos fills e lotes. Mesmo assim, **não condicionaria a fusão de W-PnL à existência de book naquele momento**, pois isso introduziria dependência da ordem da redução. [stream_mint.py:174](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:174)

**(b) Mediana.** **Sim, para os holds produzidos por este motor, no mesmo runtime/plataforma.** São segundos obtidos de diferenças de `datetime`, e a mediana do episódio seleciona um desses valores; concatenar arrays não recalcula esses floats. A mediana final ordena os mesmos valores e usa o mesmo elemento central ou o mesmo par central. Não há soma acumulada dependente da ordem. [episodes.py:98](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:98), [episodes.py:168](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:168), [stream_metrics.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:108)

Isso não é uma garantia para qualquer array arbitrário com NaN; a própria documentação ressalva esse caso. Nos testes, `float.hex()` permite verificar a igualdade exata da mediana. [Documentação de statistics](https://docs.python.org/3.12/library/statistics.html)

**(c) Estado por processo.** Não encontrei dependência da ordem dos mints nesses mecanismos:

- `_curve_of` usa dois inteiros como chave e `localcontext(CONTEXT)`; aquecimento e expulsão do LRU alteram trabalho, não a cotação. [pricing.py:84](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:84)
- Os índices pertencem a cada `MintTape`; `of_wallets` ordena as posições antes de devolver eventos. [pricing.py:182](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:182)
- O contexto numérico é explícito, com 28 dígitos e HALF_EVEN. Não copiaria o `getcontext()` ambiente do coordenador. [numeric.py:17](C:/dev/project-hunter/packages/core/hunter_core/strategies/numeric.py:17)

Há uma peça faltando no payload descrito: **`Night` não contém `sealed_until`, usado por `_prepared`**. Enviaria esse pequeno metadado de validação no initializer, sem replicar todo o carry global e seus pares pendentes. [stream_mint.py:47](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:47), [stream.py:116](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:116)

**(d) Memória.** Sim, replicar `Entities` merece medição, mas mediria **todo o `Night`**, incluindo bets, funders e sementes, mais buffers de serialização, resultados concluídos e o maior mint. `Entities` armazena os grupos ligados; carteiras isoladas usam fallback, portanto “milhões de carteiras” não significa automaticamente milhões de entradas nesse mapa. [entities.py:42](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:42), [entities.py:120](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:120)

**Começaria com o mapa completo e dois workers**, medindo o pico agregado. O fetch baseado em dicionário serve para testes funcionais, mas replica também sua fonte e não representa o orçamento de produção.

Se precisar projetar por mint, preservaria os IDs globais e **todos os membros das entidades envolvidas**, inclusive membros ausentes da fita local. Exemplo: A negocia o mint; B pertence à mesma entidade e é seu criador. Cortar B remove uma exclusão legítima, pois a classificação consulta todos os membros e seus financiadores. [metrics.py:122](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/metrics.py:122)

**CONCORDO COM**

- Passadas globais preservadas, mint inteiro como unidade, `Tallies` novo por mint e redução no coordenador.
- Somas inteiras, uniões, máximo com ausência e holds completos; razões, drawdown e mediana calculados somente depois da fusão.
- `spawn`, fila limitada e carries devolvidos na ordem da fonte quando não há `emit`. Liberar também referências aos futures já consumidos.
- Digests congelados para 1, 2 e 4 workers, **sem atualizar o golden**. Acrescentaria asserts diretos da ordem dos carries e de emissão exatamente uma vez por mint não vazio.
- Processar também mints com zero eventos preparados. A fonte precisa incluir mints somente com carry. [carry.py:34](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:34)

**OBSIDIAN**

- **CPU do motor de carteiras: medir antes de reescrever** — registrar o contrato de fonte imutável, transporte de exceções e invariantes da redução.
- **Revisão da Astra: CPU do motor de carteiras, passo 3** — registrar este parecer; provas de equivalência, encerramento e memória permanecem pendentes.
- **Revisão da Astra: motor de carteiras em memória limitada** — acrescentar o orçamento agregado dos processos e a preservação de membros completos em eventual projeção por mint.
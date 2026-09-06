**RESUMO**

Meu parecer: **A está correta; B é aceitável como barreira temporal conservadora; C funciona com proteção contra concorrência; D é a abordagem preferível, mas a censura está incompleta; E funciona se o hold for reconciliado em todos os shards.** Para a blocklist, recomendo que **a decisão explícita do operador prevaleça**.

Revisão como `backend-specialist`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes. Os cenários abaixo são análise do desenho, não resultados de execução.

**MUST-FIX**

1. **A/C — o lock precisa proteger todo o ciclo do slot, inclusive confirmação e encerramento.**

   Cenário: a primeira transação persiste `pending_entry`; após a abertura, o polling encontra ausência de confirmação e encerra como `no_entry`. A confirmação atrasada não pode tornar esse outcome utilizável novamente nem alterar o slot que já avançou.

   Recomendo uma ordem única: **slot → outcome**, seguida de releitura do estado. Confirmar somente se ainda estiver `pending_entry`, sem confirmação e vinculado ao mesmo slot. Encerrar somente o acompanhamento esperado; liberar o vínculo, desarmar e atualizar a barreira temporal na mesma transação.

   Também há uma exceção necessária à transição `TRIGGERED` de A: **se C já produziu `no_entry:late` na primeira transação, o estado final do slot deve ser `armed=false, open_outcome_signal_id=NULL`**. Do contrário, ele fica ocupado por um acompanhamento encerrado e mantém coleta indevida. O modelo deixa explicitamente essa coerência a cargo da S2: [agents_shadow.py:124](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents_shadow.py:124).

   Na criação inicial, materialize o slot com tratamento da unicidade antes de bloqueá-lo: um `SELECT FOR UPDATE` sem linha encontrada não basta para coordenar dois primeiros consumidores. A chave única já existe: [agents_shadow.py:52](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents_shadow.py:52).

2. **D — ausência de velas posteriores não pode impedir censura indefinidamente.**

   Cenário: o mercado para definitivamente às 12:20. Falta 12:21 e nunca aparece 12:22. Sua condição “existem velas posteriores” nunca se torna verdadeira; o outcome e o hold permanecem abertos para sempre.

   Precisam existir dois caminhos: gap interno e **interrupção da série**, ambos com prazo de recuperação definido. Primeiro tentar recuperar pelo market-worker; esgotada a política, censurar no primeiro minuto necessário desconhecido, mesmo sem velas posteriores. Não transformar isso em `expired` sem o preço necessário.

   O prazo deve sobreviver a restart. E “há velas posteriores” prova descontinuidade, não irrecuperabilidade: o recovery atual inclusive reabre gaps `failed` para novas tentativas. [recovery.py:78](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:78). O contrato exige censura quando a barra necessária não puder ser recuperada: [SHADOW-LAB.md:13](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:13).

3. **E — o hold precisa funcionar também no follower e no fallback para Postgres.**

   Cenário: mercado fora do top N tem outcome ativo; Redis perde o snapshot; follower reinicia e reconstrói o universo apenas por `is_monitored=true`. O mercado segurado desaparece da assinatura.

   Esse fallback existe hoje: [universe_leader.py:125](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_leader.py:125).

   Dentro dos arquivos permitidos, minha solução seria manter o snapshot como conjunto elegível e, **no caminho comum de `run_universe`, consultar os holds duráveis, unir os conjuntos e só então aplicar `shard_symbols`**. Isso cobre líder, follower e fallback sem editar `ingest.py`; o ponto comum está em [universe.py:246](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:246).

   A consulta deve considerar todos os acompanhamentos relevantes: encerrar v1 não remove o símbolo enquanto v2 ainda precisar dele.

4. **E/A — `is_monitored` atual não pode comprovar elegibilidade histórica.**

   Cenário: uma barra falsa fecha às 12:15 enquanto o mercado está inelegível; ele entra no universo às 12:16; o evento atrasado chega às 12:17. Consultar apenas o booleano atual permite rearme com uma barra que não era elegível.

   O contrato de `EvaluationState.INELIGIBLE` se refere explicitamente a `source_bar_close`: [base.py:92](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:92). Já o refresh sobrescreve o estado corrente: [universe.py:149](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:149).

   Fixe essa semântica antes de implementar: evidência durável da elegibilidade no fechamento, ou avaliação indisponível quando ela não puder ser comprovada. Gravar o booleano atual no envelope não recupera o passado.

**NICE-TO-HAVE**

- Registrar em `meta` o motivo do encerramento, o limite temporal usado para rearme e quando ele foi reconhecido. Ajuda a explicar diferenças entre execução contínua e recuperação.
- Medir perdas conservadoras separadamente: confirmação ausente, confirmação tardia e barra descartada por estar atrás do checkpoint.
- Documentar o custo de E: **sem alterar ingestão, o hold mantém todos os canais**, além das velas. A assinatura usa `CHANNELS`, que inclui trades, book, mark e liquidações: [streaming.py:42](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:42), [ingest.py:55](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:55).

**O QUE EU FARIA DIFERENTE**

**B — aceitaria `last_bar_close` como “não avaliar em ou antes deste instante”, com documentação explícita.** Hoje o modelo o descreve como fechamento avaliado, portanto há mudança semântica: [agents_shadow.py:90](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents_shadow.py:90).

A operação `max(last_bar_close, término)` resolve seu exemplo 12:15/12:20/12:30. Mas “término” precisa ser bem definido:

- Saída comprovada na abertura: usar essa abertura.
- Toque intrabar conhecido apenas por OHLC: usar o fechamento da barra como limite conservador; não inventar o instante do toque.
- `no_entry`/censura: definir explicitamente o limite de encerramento aplicável.
- Replay: usar o tempo da simulação, nunca o relógio atual.

Há uma **perda conservadora adicional**: o polling ainda não processou uma saída às 12:20; A recebe a barra falsa de 12:30 enquanto o vínculo continua aberto e avança o checkpoint; depois D encerra o outcome. A barra de 12:30 já não pode rearmar.

Isso não inventa entrada, mas torna o resultado dependente da ordem dos loops. Eu preferiria avançar o outcome pelas barras disponíveis até o fechamento candidato **antes de aplicar a transição de avaliação**. Se optar por aceitar a perda, registre-a como limitação do protocolo. O `max` sozinho não resolve essa ordenação.

**C — manteria as duas transações.** A prova é:

`commit₁ concluído → leitura de t → t < entry_bar_open`

Logo, o primeiro commit precedeu a abertura. **O segundo commit não precisa precedê-la**: ele persiste o atestado de um fato já observado. Exigir isso acrescentaria perdas desnecessárias.

Na segunda transação, bloquearia, releria o estado e então obteria `t`. Se ainda for confirmável, gravaria o atestado; caso contrário, aplicaria o encerramento protegido. Uma confirmação já existente nunca seria recalculada na reentrega. Sob um relógio confiável, não vejo alternativa mais simples que preserve a mesma prova nas restrições dadas. O crash aceito entre as transações continua conservador e deve aparecer nas contagens.

**E — preservaria a precedência da blocklist.** O contrato do M1 determina remoção por blocklist: [M1.md:97](C:/dev/project-hunter/docs/plans/M1.md:97). Minha recomendação:

- Saída por ranking: hold mantém coleta.
- Bloqueio explícito do operador: interrompe coleta; os acompanhamentos ainda não resolvidos recebem censura administrativa identificada, preservando resultados já comprovados antes do corte.

Fazer o hold vencer também é um desenho possível, mas redefine a blocklist como “bloqueia somente novas decisões”. Essa mudança precisa ser explícita.

**CONCORDO COM**

- **A:** suas transições respeitam a distinção entre condição falsa, indisponibilidade e geometria rejeitada. Só `NOT_TRIGGERED` comprova falso: [base.py:71](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:71).
- **B:** reutilizar o timestamp como barreira dispensa consultar o último outcome apenas para impedir rearme atrasado.
- **C:** prefiro perder uma entrada sem comprovação a permitir entrada retroativa; esse é o compromisso do plano: [SHADOW-LAB.md:13](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:13).
- **D:** Postgres é a melhor fonte para recovery contíguo. Atualize outcome, excursões e checkpoint atomicamente; processe a partir do minuto seguinte ao último concluído. O stream pode disparar avaliações, mas não comprova persistência: hoje a ingestão enfileira a vela e publica antes do flush durável: [ingest.py:197](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:197).
- **E:** separar elegibilidade de necessidade de coleta é correto. Preserve também a allowlist: o conjunto elegível atual não é literalmente só top N; inclui permitidos explicitamente, sempre respeitando blocklist: [universe_repo.py:178](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:178).

**OBSIDIAN**

- **Workers** — registrar polling de outcomes, confirmação pós-commit e disciplina transacional do slot.
- **Strategies** — documentar rearme, barreira temporal e tratamento de eventos fora de ordem.
- **Market Collector** — separar elegibilidade/coleta, cobrir hold nos shards e definir precedência da blocklist.
- **Diálogo Claude ⇄ Astra — SHADOW** — acrescentar as decisões aceitas desta revisão, distinguindo recomendações de acordos.
- **Strategy Performance** — registrar perdas conservadoras e censura administrativa nas contagens de cobertura.
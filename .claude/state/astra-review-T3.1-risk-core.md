**RESUMO**

**DONE_WITH_CONCERNS — eu corrigiria o contrato antes de implementar.** Os principais buracos estão na conversão de notional para quantidade, na participação após fills, na autorização de retomada e na omissão de duplicidade. Revisão como `risk-engine-guardian`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Não encontrei `docs/plans/M3.md` nem brief T3.1 nesta árvore; portanto, não confirmei o escopo formal desses documentos.

**TESTES**

Não executados. Os números abaixo são contraexemplos matemáticos, não resultados de testes.

**MUST-FIX**

1. **Item 2 — falta o tamanho solicitado entre os tetos.**  
   A diretiva proíbe aumentar posição para atingir o orçamento de risco ([diretiva:20](/C:/dev/project-hunter/.claude/state/directive-risk-engine-2026-09-06.md:20)).

   **Cenário:** proposta pede 100 USDT; todos os tetos permitem 500; sua fórmula aprova 500. Inclua `requested_qty` ou `requested_notional` como teto. Se a proposta delega integralmente o sizing, declare essa modalidade explicitamente.

2. **Item 2 — notional de referência não equivale ao desembolso no livro.**  
   Defina separadamente `reference_notional`, custo estimado de compra e taxas. O modelo existente aplica preços adversos e cobra taxas sobre os preços de cada perna; sua soma em bps é uma aproximação, não identidade desse modelo ([pricing.py:47](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47), [pricing.py:73](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:73)).

   **Cenário:** caixa disponível 1.000, referência 100, quantidade 10; VWAP de compra 100,10 e taxa de 0,1% exigem 1.002,001. O teto de caixa passou e a execução precisa de empréstimo.

   Dimensione ou revalide a quantidade pelo walk completo, incluindo taxa de entrada no caixa. Use o mesmo orçamento de execução para reservas e participação. Para risco, explicite se `entry_ref` já inclui spread/slippage; somá-los novamente duplicaria custos. A estimativa de saída deve ser declarada, sem prometer execução no stop.

3. **Item 2 — participação não pode contar apenas reservas ainda pendentes.**  
   Agregação e proibição de fracionamento estão expressas na [diretiva:23](/C:/dev/project-hunter/.claude/state/directive-risk-engine-2026-09-06.md:23).

   **Cenário:** referência de volume 100.000 → orçamento 1.000. Uma entrada de 1.000 preenche; sua reserva desaparece; outra entrada recebe mais 1.000 usando a mesma referência.

   Inclua no input **participação já consumida por fills na janela + compromisso pendente**, com janela e escopo de agregação explícitos. Fill parcial transfere consumo, não libera integralmente o orçamento. O chamador precisa serializar avaliação e reserva nesse mesmo escopo; a função pura, sozinha, não resolve simultaneidade.

4. **Itens 5 e 8 — LONG não prova SPOT; faltam invariantes explícitas.**  
   A decisão vigente exige execução spot e volume medido nesse venue ([decisões M3:6](/C:/dev/project-hunter/.claude/state/decisions-M3-delegated-2026-09-06.md:6), [decisões M3:12](/C:/dev/project-hunter/.claude/state/decisions-M3-delegated-2026-09-06.md:12)).

   **Cenário:** proposta LONG recebe book e volume do perpétuo e passa. Exija identidade compatível de exchange, mercado, modalidade, base e quote entre proposta, preço, livro e volumes. Preserve o piso **50 milhões USDT/24h no spot de execução**.

   Também explicite cinco vagas incluindo entradas pendentes. Quatro posições abertas mais uma entrada reservada não deixam uma sexta vaga.

5. **Item 8 — não omita `duplicate_position`.**  
   A decisão delegada diz “nunca duas posições na mesma moeda” ([decisões M3:19](/C:/dev/project-hunter/.claude/state/decisions-M3-delegated-2026-09-06.md:19)).

   **Cenário:** dois agentes propõem 3% da carteira na mesma moeda. Ambos passam pelo teto de 10%, mas violam a decisão. Verifique **base asset**, incluindo pendentes, não apenas mercado/direção.

6. **Item 4 — `authorized_by` preenchido não é autorização; falta o contrato de cancelamento.**  
   BLOQUEADO exige cancelar pendentes e retomada autorizada pelo Everton ([diretiva:43](/C:/dev/project-hunter/.claude/state/directive-risk-engine-2026-09-06.md:43)).

   **Cenários:** qualquer chamador fornece uma string e destrava; ou uma decisão aprovada anteriormente executa depois do bloqueio.

   A autenticação/autorização pertence ao chamador. O core recebe uma autorização previamente verificada, vinculada ao portfolio e à transição. Retorne também a obrigação `cancel_pending_entries`; o executor deve conferir a trava antes de novos fills.

   Outro ponto: com drawdown ainda em 9%, `resume → ACTIVE` será imediatamente bloqueado pela avaliação automática. Defina se autorização apenas remove o latch **quando os gatilhos cessaram**. Não crie uma exceção aos limiares silenciosamente.

7. **Itens 3 e 5 — falta validade temporal de todos os insumos relevantes.**  
   O backlog distingue idade máxima por preço, livro, volume e beta ([Strategy Backlog:696](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:696>)).

   **Cenários:** ticker recente com livro antigo passa; beta calculado depois da decisão introduz look-ahead; primeira leitura às 00:15 vira “equity inicial” e apaga a perda desde meia-noite.

   Injete `as_of` UTC; valide disponibilidade e timestamps por insumo, janela de 30 minutos completos e contíguos, e identidade temporal da âncora diária. Ausência de marcação válida das posições também torna equity/exposição indisponíveis. Não basta validar o mercado da nova entrada.

   Beta ausente em **posição existente ou pendente** não pode virar contribuição zero. Já beta **zero validado** é permitido matematicamente: não divida por zero nem serialize `Infinity`; registre ausência de restrição incremental desse teto, mantendo os demais.

8. **Item 6 — aprovação de saída precisa significar permissão para reduzir posição.**  
   Saídas são sempre permitidas pelo contrato ([RISK_ENGINE.md:113](/C:/dev/project-hunter/docs/RISK_ENGINE.md:113)).

   **Cenário:** um pedido rotulado `ExitProposal` compra mais, vende acima do saldo ou reapresenta uma saída já preenchida. A dispensa de checks de entrada não autoriza esses efeitos.

   Garanta vínculo com posição, quantidade redutora e idempotência no contrato com execução. Sem livro, a autorização continua válida, mas custos podem ficar `unavailable`; isso não significa fill garantido nem custo zero.

**NICE-TO-HAVE**

- Publique todos os tetos e empates, além do vencedor. Grave quantidade sem multiplicador, após multiplicador e após arredondamento.
- Defina uma projeção explícita para serialização: `canonical_json` aceita mappings/sequências, mas não dataclasses arbitrárias nem `date`; retorna bytes ([canonical.py:102](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:102)).
- Fixe contexto Decimal para os cálculos. O modelo de preços existente já faz isso para evitar dependência da precisão ambiente ([pricing.py:35](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:35)).

**O QUE EU FARIA DIFERENTE**

**Item 7:** manteria **0,001 provisoriamente**, com origem/versionamento explícitos. É o valor do contrato antigo ([RISK_ENGINE.md:31](/C:/dev/project-hunter/docs/RISK_ENGINE.md:31)); 0,0005 é recomendação de pesquisa, não decisão consolidada ([Strategy Backlog:666](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:666>)).

**Item 8:** separar “não implementar agora” de “deixar de valer”. A diretiva não revoga automaticamente toda proteção anterior.

- `spread` merece decisão explícita: walk limitado a 10 bps contra mid pode admitir spread próximo de 20 bps; o Conservative antigo limita spread a 5 bps ([RISK_ENGINE.md:30](/C:/dev/project-hunter/docs/RISK_ENGINE.md:30)).
- Não transplantaria `correlation(beta>0,8)` nem multiplicadores de regime automaticamente.
- Não vejo necessidade matemática de restaurar `max_position_pct` além do teto por moeda solicitado.
- Bandas de stop são escolha adicional; geometria precisa exigir **`0 < stop < entry`**, números finitos e preços positivos.
- Preserve validade do sinal e estado operacional do portfolio/agente, já previstos no contrato ([RISK_ENGINE.md:58](/C:/dev/project-hunter/docs/RISK_ENGINE.md:58)).

**CONCORDO COM**

- **1:** reutilizar o enum. Mas use ranking explícito: ele é `StrEnum`; `max()` direto compara strings e pode escolher WARNING acima de EMERGENCY ([enums.py:51](/C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:51)).
- **2:** multiplicador depois dos tetos e antes do arredondamento. **Não recalcule `binding_limit`**: mantenha o vencedor anterior e publique a redução separadamente.
- **3:** denominador diário na equity inicial do dia; drawdown no pico monotônico. Custos já debitados do caixa não devem ser descontados novamente.
- **4:** latch obrigatório para BLOQUEADO; não transforme WARNING em latch permanente por acidente.
- **5:** `unavailable` reprova entrada; beta não validado mantém shadow.
- **6:** saída independente das travas de entrada, respeitadas as invariantes acima.
- **9:** sem objeção à dependência `tzdata`. Inclua atualização de `uv.lock` no escopo da implementação; não reproduzi a falha de Windows nesta revisão.

**OBSIDIAN**

- **Risk Engine** — registrar PAPER_V1, tetos, estados, checks preservados e substituições explícitas do v1.
- **Portfolio** — definir âncora diária, pico, reservas, vagas e participação consumida por janela.
- **Execution Engine** — documentar cancelamento no bloqueio, revalidação antes do fill e semântica redutora das saídas.
- **Revisões Astra — T3.1: desenho do núcleo puro** — registrar estes contraexemplos e a resolução de cada divergência.
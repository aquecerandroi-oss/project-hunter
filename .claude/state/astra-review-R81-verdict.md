**RESUMO**

**Mantenho H-021 concluída — NÃO CONFIRMA por limite de dado, sem abrir a E. Não aprovaria ainda o diff como está.** Há correções de interpretação da auditoria, uma afirmação operacional incorreta sobre “~89%” e partes do must-fix 5 ainda pendentes.

**H-021 está coerente em Pistas:** o Dataview seleciona `limite_de_dado`; Cemitério seleciona `refuta` ou `nao_confirma`. Não mudaria o veredito para acomodar a organização da página. [Mapa:49](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Mapa de Estrategias.md:49>), [Mapa:70](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Mapa de Estrategias.md:70>)

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão como `quant-engineer`, somente leitura. Não executei a E nem abri seus desfechos.

**TESTES**

Não executei pytest nesta revisão; **não revalido o “14/14”**. Fiz inspeção dos testes e conferências aritméticas/cegas em PowerShell. Saída real:

```text
audit rows=338; zero tape=0; timestamps differ=200
line_missing_pct=89.2455858747994
flat_too_few_pct=87.6404494382023
slot_disagreement_all_known=12.1212121212121
slot_disagreement_comparable=15.7635467980296
```

As contagens principais conferem com as saídas: 885 primeiras decisões resolvidas; uma candidata pelo começo do arquivo; 623 na E; 175 com fundos avaliáveis; auditoria com 338 decisões; último slot ambíguo em 184/775. [count_blind.txt:1](/C:/dev/project-hunter/.claude/state/r81/count_blind.txt:1), [blind_e.txt:1](/C:/dev/project-hunter/.claude/state/r81/blind_e.txt:1), [audit.txt:9](/C:/dev/project-hunter/.claude/state/r81/audit.txt:9)

`age.py` contém o cálculo, mas não encontrei sua saída persistida entre os arquivos indicados; não reconfirmei independentemente os seis casos ≥300 s nem o máximo de 315 s. [age.py:6](/C:/dev/project-hunter/.claude/state/r81/age.py:6)

**MUST-FIX**

1. **“O teto recusaria ~89%” confunde disponibilidade na pesquisa com o insumo efetivo do portão.**

   Os 67/623 vêm de uma consulta adicional a `meme_features_1m`. A pista de 15 s constrói `GateRow` sem os campos de linha; eles permanecem `None`. A pista de eventos herda essa base e não preenche a linha. Ao pedir o teto, `line_refusals` recusa esses campos ausentes como `line_unknown`. [q_pop.sql:22](/C:/dev/project-hunter/.claude/state/r81/q_pop.sql:22), [lab_repo_fast.py:179](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:179), [proposals_row.py:38](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_row.py:38), [event_gate_rows.py:118](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_rows.py:118), [rules_criteria.py:177](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_criteria.py:177)

   **Cenário:** configurar o teto esperando preservar os 67 casos com linha também os recusa, porque a linha encontrada pela pesquisa não chega ao gate.

   **Correção:** “556/623 (89,25%) não tinham distância disponível na série de 1 minuto consultada. Nas pistas atuais, ativar o teto sem integrar esses campos recusaria todas as avaliações por linha ausente.” Além disso, faltam **três casos sem linha 1m** na decomposição da KB: 290 + 256 + 7 + 67 = 620, não 623. [blind_e.txt:8](/C:/dev/project-hunter/.claude/state/r81/blind_e.txt:8)

2. **Preservar instante, janela e denominador ao transportar a auditoria para o Obsidian.**

   Os **95%** significam zero trocas **daquele minuto** recebidas até **`as_of = features_end_time`**. Não significam arquivo inteiro vazio até `decided_at`. O SQL usa relógios diferentes para trades e fotos; no CSV, 200/338 registros têm os dois timestamps diferentes. [q_audit.sql:4](/C:/dev/project-hunter/.claude/state/r81/q_audit.sql:4), [q_audit.sql:12](/C:/dev/project-hunter/.claude/state/r81/q_audit.sql:12)

   **Cenário:** um poll chega depois de `as_of`, mas antes de `decided_at`; a consulta conta zero e a KB afirma incorretamente que nada havia chegado até a decisão. A redação atual faz essa troca. [KB-0161:53](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:53)

   Publicaria também:
   - **32/264 = 12,1%** com slot inferido; **32/203 = 15,8%** entre pares comparáveis; 61 sem arquivo. Não apresentar 12% como taxa de erro contra criação comprovada: os dois slots são aproximações. [audit.txt:5](/C:/dev/project-hunter/.claude/state/r81/audit.txt:5), [decision_tape_creation.py:28](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape_creation.py:28)
   - **184/775 = 23,7%**, na população B; não nas 338 decisões da população A. A lista da KB hoje permite essa leitura. [KB-0161:50](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:50)
   - **Uma decisão cujo arquivo começa suficientemente cedo**, não uma janela comprovadamente coberta. `covered()` verifica apenas a primeira data. **Cenário:** uma troca antiga e um buraco no meio passam nessa condição. [r81.py:82](/C:/dev/project-hunter/.claude/state/r81/r81.py:82)

   Nada disso altera o encerramento: a evidência de cobertura fica mais fraca, não mais forte.

3. **A KB afirma uma correção de Spearman que não está no código apresentado.**

   “Postos médios” contradiz o duplo `argsort`, que atribui postos diferentes a empates. [KB-0161:62](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:62), [blind_e.py:27](/C:/dev/project-hunter/.claude/state/r81/blind_e.py:27)

   **Cenário:** preços iguais recebem ordenação arbitrária e a associação publicada parece uma correlação com tratamento de empates já validado.

   Retirar “postos médios” e manter o valor como aproximado, ou recalcular cegamente e atualizar a saída. O p1 de 2,80e-8 também não prova, sozinho, que **todas** as moedas começam no mesmo preço. [blind_e.txt:4](/C:/dev/project-hunter/.claude/state/r81/blind_e.txt:4)

4. **O must-fix 5 ainda não foi completamente corrigido.**

   `counterfactual()` continua usando `max(1, len(wins))`, tanto na impressão quanto no retorno. **Cenário:** nenhuma vencedora real produz fração zero e faz `mata ≤20%` aparecer verdadeiro. Deve retornar ausência/`nan`, como já faz `win_hi`. [h021.py:124](/C:/dev/project-hunter/.claude/state/r81/h021.py:124), [h021.py:129](/C:/dev/project-hunter/.claude/state/r81/h021.py:129), [h021.py:155](/C:/dev/project-hunter/.claude/state/r81/h021.py:155)

   O nome do spec mudou, mas sua regra continua dizendo `CONFIRMA`; o renderer continua imprimindo `## VEREDITO`. **Cenário:** reutilizar o spec gera um relatório formal de confirmação apesar do aviso no título. A renomeação não impede essa promoção. [mill.py:21](/C:/dev/project-hunter/.claude/state/r81/mill.py:21), [report.py:101](/C:/dev/project-hunter/infra/research/report.py:101)

   Esses pontos bloqueiam declarar o script pronto, **não fechar H-021**.

5. **Reservas pós-troca são sustentadas; ordem econômica dos logs ainda não está demonstrada.**

   O estado recebe reservas pós-troca e acrescenta pontos na ordem de chegada. Isso não comprova ordem de execução entre transações do mesmo slot. [event_state.py:137](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:137), [event_state.py:340](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:340)

   **Cenário:** chegam B e depois A, embora A tenha executado antes de B; usar o último recebido como fechamento muda fundos e rompimento.

   Na proposta da H-021b, escrever **“ordem de recebimento, com política explícita para eventos fora de ordem”**, ou exigir ordem verificável antes de chamar isso de trajetória econômica.

   Também retiraria a regra universal “compra acima/venda abaixo do marginal”: o modelo define `priceSol` como marginal **após** o fill, e apenas distinguir esses campos não demonstra aquela desigualdade. Manter o exemplo 0,98/1,02 como **sintético**, ilustrando mistura de fills. [board_models.py:194](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/board_models.py:194)

**NICE-TO-HAVE**

- A janela auditada está correta: **`(as_of−60 s, as_of]`**. `trades_in_window` conta toda a janela disponível no estado; só o vetor persistido sofre o corte de 50. Não encontrei esse erro de denominador. [decision_tape.py:292](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape.py:292), [decision_tape.py:319](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape.py:319)
- Razão de contagens arquivo/fita não é reconciliação por identidade: razão 1 pode esconder trocas diferentes. Chamar de comparação de contagens.
- O SQL escolhe a primeira proposta e **depois** exige fita; não escolhe a primeira proposta *entre aquelas com fita*. Ajustar a descrição. [q_audit.sql:3](/C:/dev/project-hunter/.claude/state/r81/q_audit.sql:3)
- Trocar o título de Pistas por algo que inclua **limitações de dados**, sem pressupor sinal favorável. Corrigir também o link para §6 das notas, que terminam em §5. [KB-0161:130](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:130)

**O QUE EU FARIA DIFERENTE**

Separaria explicitamente três conclusões: **insuficiência da população congelada**, **limitações do instrumento retrospectivo** e **requisitos ainda não validados da instrumentação futura**. Evitaria “não há gráfico de minutos”; o demonstrado é que quase não há **cinco minutos anteriores** na população estudada.

**CONCORDO COM**

“Não trouxe evidência a favor nem contra” está correto **sobre desempenho da tese**; há evidência contra a adequação do instrumento atual. Manter E fechada e H-021 concluída continua sendo a decisão adequada.

A linha nova de H-020 confere com a KB-0160: D, intervalo, 32,9% × 32,3%, 1,02× e interrupção da coleta. [KB-0160:95](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0160-o-link-reciclado-nao-avisa-o-golpe.md:95)

**OBSIDIAN**

- **KB-0161** — corrigir relógios, denominadores, cobertura, Spearman, disponibilidade no gate e requisitos da ordem.
- **Fila de Hipóteses** — preservar status/veredito; corrigir somente as justificativas factuais.
- **Dicionário de Variáveis** — distinguir série 1m disponível na pesquisa dos campos efetivamente entregues às pistas.
- **Mapa de Estratégias** — manter H-021 em Pistas; ampliar a descrição da seção para limites de dados sem sinal favorável.
- **Perdas/comprou_no_topo** — preservar ausência de evidência de desempenho e restringir a conclusão aos cinco minutos exigidos.
- **Revisões-Astra / R81** — registrar este parecer e as pendências residuais do script.
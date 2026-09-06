**RESUMO**

**DONE_WITH_CONCERNS — não encerraria a revisão ainda.** Encontrei dois problemas: o relato diário pode impedir uma saída antes da avaliação; e o desconto de reservas usa os custos da proposta nova, não os custos já comprometidos.

Não encontrei novo desvio da aprovação de entradas: `approved` continua exigindo todos os checks aprovados em [evaluate.py:180](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:180). Isso verifica o núcleo puro; não comprova a persistência antes da criação de ordens.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei o diff indicado, os arquivos novos e a alteração adicional em `test_sizing.py`.

**TESTES**

Executei, com bytecode e cache do pytest desabilitados:

```text
uv run pytest packages/risk-core/tests/unit/test_review_findings.py packages/risk-core/tests/unit/test_exposure.py packages/risk-core/tests/unit/test_kill_switch.py -q
66 passed in 0.60s
```

Reproduções sintéticas em memória, via `uv run python -B -`:

```text
STOP old_distance= 0.002 new_distance= 0.003992015968063872255489021956 approved= True
BAND 100.502 deviation= 0.004994925474119918011581859067 state= passed approved= True
BAND 99.502 deviation= 0.005004924524130168237824365339 state= failed approved= False
SAME_STATE_WITHOUT_REPORT exit approved= True
CASH approved= True new_spend= 100 pending_spend= 400.40009600 combined= 500.40009600
```

Não executei a suíte completa, propriedades, lint ou typecheck.

**MUST-FIX**

1. **HIGH — divergência de relato pode impedir proteção.** O validator lança exceção em [exposure.py:160](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:160), mas `evaluate_exit` exige esse mesmo `PortfolioState` em [evaluate.py:194](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:194).

   **Cenário reproduzido:** patrimônio inicial `20000`; variação calculada de `0.00000000006`; patrimônio arredondado para dez casas: `20000.0000000001`. Informar o não realizado ainda sem quantização gera:

   ```text
   the daily decomposition 6E-11 disagrees with the equity movement 1E-10
   ```

   A construção falha **antes de chamar a saída**. O mesmo estado, omitindo os três campos de relato, permite a proteção.

   **Para T3.3:** igualdade exata é viável somente com uma política única de contabilização, arredondamento e corte temporal. Também é necessário definir a decomposição diária: `realizado_do_dia + U_agora − U_início_do_dia − custos_do_dia`. Uma posição comprada a 100, marcada a 110 na meia-noite e vendida hoje a 110 tem realizado 10, mas variação diária zero. Proibir aportes não elimina esse ajuste.

   **Correção:** não tornar a reconciliação do relato pré-requisito para construir o estado de proteção. Manter a perda diária derivada do patrimônio e definir explicitamente a reconciliação para T3.3. Não recomendo uma tolerância arbitrária.

2. **MEDIUM — reserva de caixa depende indevidamente dos custos da próxima proposta.** [exposure.py:248](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:248) multiplica todas as reservas pelo multiplicador recebido; esse multiplicador vem da proposta candidata em [sizing.py:238](C:/dev/project-hunter/packages/risk-core/hunter_risk/sizing.py:238).

   **Cenário reproduzido sobre a carteira sintética da revisão:** caixa 500; reserva de notional 400 com os custos padrão, comprometendo `400.400096`; candidata com custos zero. O motor aprova mais 100: compromisso total `500.400096`, acima do caixa.

   É uma **correção incompleta do problema anterior**, não um novo bypass de `approved`. A propriedade necessária é descontar o compromisso original de cada reserva. O modelo persistido já distingue `reserved_cash` de `reserved_notional` em [execution.py:190](C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:190). Eu transportaria esse valor para `PendingEntry`.

**NICE-TO-HAVE**

Nenhum achado adicional com cenário suficiente para exigir correção.

**O QUE EU FARIA DIFERENTE**

Separaria explicitamente **conservadorismo do tamanho** de **admissibilidade do stop**:

- Com referência e stop fixos, usar o maior preço não aumenta a quantidade: o cálculo usa esse preço nos tetos e na divisão final em [sizing.py:223](C:/dev/project-hunter/packages/risk-core/hunter_risk/sizing.py:223) e [sizing.py:253](C:/dev/project-hunter/packages/risk-core/hunter_risk/sizing.py:253).
- Porém, **pode aprovar uma proposta antes recusada**: referência 100, stop 99,8, observado 100,2. A distância passa de 0,2% para aproximadamente 0,3992%, superando o mínimo de 0,3%. Isso decorre de [checks.py:249](C:/dev/project-hunter/packages/risk-core/hunter_risk/checks.py:249). Não considero falha por si só: o stop está efetivamente mais distante do mercado. Mas invalida a afirmação ampla de que o motor “nunca fica mais permissivo”.
- A banda em [observations.py:50](C:/dev/project-hunter/packages/risk-core/hunter_risk/observations.py:50), para referência 100, admite observado entre aproximadamente **99,502488 e 100,502513**. Favorece ligeiramente a tolerância à alta. Não encontrei nesse denominador um mecanismo para aumentar o tamanho aprovado; a assimetria deve constar do contrato.

**CONCORDO COM**

A perda baseada no patrimônio fecha o caso original em [exposure.py:180](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:180). Volume sem carimbo, futuro ou vencido é recusado em [observations.py:103](C:/dev/project-hunter/packages/risk-core/hunter_risk/observations.py:103). A trava de retomada em [kill_switch.py:198](C:/dev/project-hunter/packages/risk-core/hunter_risk/kill_switch.py:198) não adiciona veto às saídas: com estado construído, elas continuam aprovadas em [evaluate.py:246](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:246).

**OBSIDIAN**

- **Risk Engine** — registrar conservadorismo do sizing, mudança de admissibilidade e os dois achados pendentes.
- **Portfolio** — definir reconciliação diária, ajuste do não realizado inicial e precisão contábil.
- **Execution Engine** — exigir que divergências de relato não impeçam proteções.
- **Revisoes-Astra/Index** — indexar esta revisão com os 66 testes e as reproduções.
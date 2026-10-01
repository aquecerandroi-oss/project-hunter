**RESUMO — DONE_WITH_CONCERNS.** Confirmo (1), qualifico (2) e confirmo um caminho condicional em (3).

**ARQUIVOS:** nenhum criado ou modificado.

**TESTES:** não executados; revisão estática, sem acessar banco ou RPC.

**MUST-FIX**

**(1) HIGH — o ensaio pode bloquear saídas.** `_CANDIDATES` trava também abertas; o descarte acontece **depois** do SELECT, e os RPCs rodam dentro da mesma transação: [spot_fix_ata_rent.py:85](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:85), [278](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:278), [332](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:332).

Cenário: uma aberta candidata e várias fechadas cujos RPCs, somados, demoram mais de 15 s. O UPDATE da marca espera; com timeout de worker em 15 s, falha antes de `decide_exit`, abortando o restante daquele tique: [session.py:199](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:199), [spot_exits.py:125](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:125), [181](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:181), [99](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:99).

**Ressalva:** o kill é atualizado antes; ficam impedidas a avaliação e a execução da saída dessa posição e das seguintes. Posições anteriores podem ter sido processadas ([spot_exits.py:105](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:105)).

Correção mínima: `WHERE p.status = 'closed' AND (predicado_atual)`, preservando os parênteses do `OR`; listar abertas em SELECT separado **sem lock**.

**NICE-TO-HAVE**

**(2) Não são exatamente 60 s; tampouco 80 s é teto.** `int(waited) >= 60` equivale a `waited >= 60` para duração positiva: o truncamento não acrescenta atraso. A espera vem da amostragem. O loop dorme 20 s **depois** do trabalho, e a confirmação relê o relógio após o RPC. Portanto, 60–~80 s é aproximação com processamento rápido; pode demorar mais. Trata-se de iniciar uma tentativa, não garantir venda concluída. [spot_exit_rules.py:168](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:168), [main.py:118](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:118), [spot_exit_confirm.py:123](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:123).

**O QUE EU FARIA DIFERENTE**

**(3) Sim, condicionalmente — risco herdado da tolerância.** Exemplo hipotético: gasto **0,05 SOL**, risco **0,0005 SOL**, alvo **1,5 R**. Confirmação em **0,05075** confirma alvo; na terceira tentativa, 300 bp permitem aproximadamente **0,0492275**, abaixo do stop **0,0495**, mesmo antes das taxas. A confirmação julga `out_amount`; a simulação aceita o mínimo da cotação, sem comparar com o stop: [spot_exit_confirm.py:101](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:101), [spot_exit_rules.py:190](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:190), [spot_send.py:207](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:207).

Eu recomendaria um piso específico para alvo. Como altera a política anterior, **não classifico automaticamente como novo must-fix**. A confirmação adicional não garante esse piso.

**CONCORDO COM:** restringir o lock às fechadas e executar a própria cotação confirmadora.

**OBSIDIAN**

- **Spot-ata-rent-fix:** registrar o HIGH de concorrência, inclusive no ensaio.
- **Spot-exit-confirm:** esclarecer prazo amostrado e ausência de piso de execução relativo ao stop.
## RESUMO

**REQUEST_CHANGES:** corrigiria a omissão do trailing no plano manual. Não encontrei regressão nos conjuntos `research_only` sem `ttl_s`. A migração funciona no estado esperado, mas não garante sozinha “um único operator ativo” diante de estados divergentes.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão somente leitura, como `code-reviewer`, incluindo a migração.

## TESTES

Não executei pytest, lint ou migrações nesta revisão. Inspecionei os testes; isso **não comprova aprovação**.

Contagem com PowerShell: os nove módulos de produção revisados têm entre **62 e 350 linhas**; `meme_desk_out.py` está exatamente em 350.

## MUST-FIX

**HIGH — O plano omite uma saída efetivamente configurada.** A semente define trailing de 35%, armado após 1,5×, mas o texto enumera apenas alvo, perda máxima, venda do dev e quebra da linha. Referências: [meme_operator_3.py:41](C:/dev/project-hunter/infra/migrations/ddl/meme_operator_3.py:41), [proposals_plan.py:64](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_plan.py:64).

**Cenário concreto:** antes dos 30 minutos, a marca alcança 2× o custo e recua para 1,3×, sem venda do dev nem quebra da linha. O motor manda sair pelo trailing; quem seguir o texto continua segurando, pois não atingiu 3× nem perdeu 50%. Essa é precisamente a condição calculada em [exits.py:235](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/exits.py:235).

Incluir no plano a queda desde o pico e seu limiar de ativação, ambos vindos dos parâmetros. O exemplo textual do brief também omite essa saída; a correção precisa alinhar texto e regra.

## NICE-TO-HAVE

- **Migração: validar o estado esperado antes de trocar as versões.** Aposentar somente o ID de `operator/2` não resolve outro operator já ativo; `ON CONFLICT DO NOTHING` também aceita silenciosamente uma `operator/3` preexistente com estado ou conteúdo diferente. O downgrade reativa `operator/2` incondicionalmente. Isso merece uma recusa explícita de estados divergentes, sem tentar corrigi-los automaticamente. Não classifiquei como regressão comprovada porque depende de um estado diferente da cadeia normal. [meme_operator_3.py:51](C:/dev/project-hunter/infra/migrations/ddl/meme_operator_3.py:51)
- **A CLI não garante exatamente um:** sua proteção impede aposentar o **último** operator; ela permite haver outro ativo. Portanto, não serve como prova de unicidade. [meme_rule_set.py:133](C:/dev/project-hunter/infra/scripts/meme_rule_set.py:133)
- **Hora de venda:** `proposed_at + max_hold_s` atende ao brief, mas significa prazo contado da proposta. Proposta às 17:30, compra às 17:32:59 e venda até 18:00 deixam aproximadamente 27 minutos de posição. Explicitaria “30 min desde a proposta”. Além disso, `%H:%M` descarta segundos: o teste de 90 s espera `17:31`, embora o instante seja `17:31:30`. [proposals_plan.py:63](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_plan.py:63), [test_proposals_operator_3.py:133](C:/dev/project-hunter/services/meme-worker/tests/test_proposals_operator_3.py:133)
- Acrescentaria testes de virada de dia e transição histórica de DST, exibindo data/offset quando necessário. A conversão usa a zona correta, mas o texto publica somente a hora, que pode ser ambígua. [proposals_plan.py:62](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_plan.py:62)

## O QUE EU FARIA DIFERENTE

Manteria a composição da semente e o texto persistido na proposta. Acrescentaria a instrução de trailing e deixaria explícita a origem do prazo de venda. Na migração, preferiria recusar um estado inesperado a concluir silenciosamente com uma configuração diferente da prevista.

## CONCORDO COM

1. **Semente e atomicidade:** os overrides estão à direita de `jsonb ||`; aposentadoria e inserção rodam dentro da transação Alembic. Se o insert falhar, a aposentadoria não deve ficar parcialmente aplicada. A ordem é adequada, mas a atomicidade vem da transação. [meme_operator_3.py:63](C:/dev/project-hunter/infra/migrations/ddl/meme_operator_3.py:63), [env.py:136](C:/dev/project-hunter/infra/migrations/env.py:136)

2. **Banco já na 0033 e downgrade:** um upgrade normal para o mesmo head não reaplica a revisão. O downgrade verifica propostas e apostas antes de remover a semente, sem filtrar apenas evidências abertas; os testes cobrem ambas as recusas e a reversão limpa. [0033_meme_operator_3.py:59](C:/dev/project-hunter/infra/migrations/versions/0033_meme_operator_3.py:59), [test_migrations.py:6614](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:6614)

3. **TTL e pesquisa:** o mesmo TTL efetivo alimenta o plano e `expires_at`. Sem parâmetro próprio, permanece o TTL do laço; `manual_plan` entra somente em `kind == "operator"`. Não encontrei mudança no payload dos conjuntos de pesquisa congelados examinados. [proposals.py:246](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:246), [proposals.py:269](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:269)

## OBSIDIAN

- **Meme — o que uma “estratégia” é aqui:** registrar `operator/3`, aposentadoria de `operator/2`, TTL de 180 s e trailing no plano manual.
- **A Mesa do operador em papel e o caminho de assinatura inerte:** acrescentar a evolução T4.19 e esclarecer que o prazo manual de venda começa na proposta.
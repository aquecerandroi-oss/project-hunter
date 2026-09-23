**RESUMO**

**REQUEST_CHANGES.** Há dois bloqueadores: a recusa de assinatura não persiste no estado real do banco, e essa falha pode bloquear permanentemente novas tentativas de saída. Também falta publicar um desfecho do reconciliador.

**ARQUIVOS**

Revisão somente leitura, no papel de `code-reviewer`. Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Não executei testes nesta revisão. Os testes novos não comprovam a transição no Postgres: o fake registra `refused` e retorna sucesso independentemente do estado anterior ([spot_fakes.py:285](C:/dev/project-hunter/services/meme-executor/tests/spot_fakes.py:285)). Isso mascara o primeiro bloqueador abaixo.

**MUST-FIX**

1. **HIGH — `simulated → refused` não acontece no banco.**  
   `spot_leg` grava `simulated` antes de assinar e chama `_refuse` quando a assinatura falha ([spot_send.py:220](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:220)). Porém, `_REFUSED` exige `status = 'admitted'`: atualiza zero linhas quando a ordem já está `simulated` ([spot_repo.py:148](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:148)). `_refuse` ignora o retorno booleano e anuncia sucesso ([spot_send.py:72](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:72)).

   **Cenário:** signer lança `RuntimeError`; o chamador recebe `refused:signer_failed:RuntimeError`, mas a ordem continua `simulated`, sem esse motivo. Na compra, a reserva continua na consulta de pendentes ([spot_repo.py:153](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:153)). Na venda, o caminho normal limpa o marcador, apesar de a ordem continuar não terminal ([spot_exits.py:313](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:313)).

   **Correção:** permitir a recusa de `admitted` **e** `simulated` ainda não enviados, preservar a guarda contra ordens submetidas e tratar explicitamente uma transição que não aconteceu. Acrescentar teste com o repositório real.

   Uma correção ao contexto: **não necessariamente fica “para sempre”**. Já existe recuperação de ordens abandonadas após 300 segundos, que também limpa o marcador da venda; depende de o reconciliador continuar funcionando ([spot_reconcile.py:67](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:67), [spot_reconcile.py:118](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:118)).

2. **HIGH — falha operacional do signer esgota o orçamento da posição.**  
   `signer_failed:` não pertence às recusas transitórias ([spot_exit_repo.py:46](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:46)). Portanto, incrementa `hard_failures` e termina em `blocked_exits`; posições bloqueadas são ignoradas **antes** de avaliar emergência ou venda solicitada ([spot_exits.py:317](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:317), [spot_exits.py:130](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:130)).

   **Cenário:** seis tentativas falham por indisponibilidade do signer. Ele volta a funcionar, mas a posição continua sem tentar o stop. Corrigido o item 1, essas recusas também serão recontadas como duras após reinício ([spot_exit_repo.py:84](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:84)).

   **Minha avaliação de (a):** recusar uma assinatura inválida é correto; transformar esse incidente em bloqueio permanente da proteção viola a intenção da regra. Eu separaria falhas do signer do orçamento de falhas da operação, mantendo recusa nomeada, alerta e novas tentativas com backoff. Ajustaria tanto a classificação em memória quanto a reconstrução SQL.

3. **MEDIUM — a recuperação de abandonadas ainda não publica seu resultado.**  
   O ramo `fail_abandoned` grava a falha, mas só escreve log; não atualiza `last_reconcile_result` ([spot_reconcile.py:122](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:122)).

   **Cenário:** processo cai antes de assinar; após reiniciar, o reconciliador encerra a ordem como `abandoned_before_signing`. O heartbeat pode continuar com `last_reconcile_result = None` e `pending_unconfirmed = 0`, pois essa ordem nunca pertenceu ao conjunto submetido ([spot_reconcile.py:85](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:85)).

   **Correção para (c):** publicar `failed:abandoned_before_signing` quando `fail_abandoned` efetivamente vencer a transição.

**NICE-TO-HAVE**

- **(b) A fotografia inicial é aceitável como visibilidade mínima**, desde que apresentada como “última leitura”. Uma ordem liquidada durante o tick permanece no medidor até a próxima leitura; isso pode produzir alerta já resolvido. Acrescentaria `pending_observed_at`, especialmente porque uma falha posterior na consulta mantém os valores antigos ([spot_reconcile.py:85](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:85)).
- A contagem spot é **do lote, limitada a 50**, não necessariamente de todo o backlog. Documentar a saturação ou usar agregação separada ([spot_exit_repo.py:101](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:101)).
- Para pendências com meta ausente ou inconsistente, quantidade e idade mostram que existe problema, mas **não explicam a causa**. Um campo separado de motivo da pendência ajudaria; hoje esses caminhos apenas registram logs ([spot_reconcile.py:229](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:229), [treasury_reconcile.py:147](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:147)).

**O QUE EU FARIA DIFERENTE**

Manteria o patch pequeno, mas incluiria a correção SQL e testes de integração para `simulated → refused`, liberação da reserva e recuperação do signer após seis falhas. O teste atual chega a exigir que a falha do signer seja dura; eu revisaria essa expectativa ([test_spot_send_signer.py:109](C:/dev/project-hunter/services/meme-executor/tests/test_spot_send_signer.py:109)).

**CONCORDO COM**

- Capturar assinatura, serialização e base58 antes do broadcast.
- Separar o resultado da reconciliação do resultado da tentativa.
- **(d) Medir antes de `_settle_by_signature` é adequado:** publica a fotografia mesmo quando a consulta ao RPC falha. Não identifiquei alteração da lógica de liquidação causada por essa posição das métricas; a ressalva é sua semântica temporal ([spot_reconcile.py:91](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:91), [spot_reconcile.py:136](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:136)).

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — registrar a transição real de recusa, a recuperação de abandonadas e a política de retentativa do signer.
- **Revisões Astra — T4.86** — registrar os três achados e as limitações dos medidores, após a correção.
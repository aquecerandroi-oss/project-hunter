**RESUMO**

**Não aprovaria a T4.74-5 ainda.** A revisão estática encontrou caminhos de compra pousada esquecida, saída presa após crash e reserva spot invisível às outras pistas. Há também uma corrida na liquidação e refutação que pode se desfazer sozinha.

Papel: `risk-engine-guardian`. Os cenários abaixo são deduzidos do código; não foram reproduzidos em execução.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum `.env` lido. Nenhum commit.

**TESTES**

Não executei testes nesta revisão somente leitura. Examinei os quatro arquivos de testes pedidos e o rig.

A cobertura atual não demonstra segurança concorrente: os fakes de `set_exit_pending`, `close_position`, `mark_confirmed` e `mark_failed` retornam sucesso sem reproduzir as transições condicionais do banco — [spot_exits_rig.py:139](C:/dev/project-hunter/services/meme-executor/tests/spot_exits_rig.py:139), [spot_exits_rig.py:176](C:/dev/project-hunter/services/meme-executor/tests/spot_exits_rig.py:176).

**MUST-FIX**

1. **[spot_reconcile.py:127](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:127) — CRITICAL — A expiração usa uma observação de assinatura anterior à observação de altura.**

   Cenário: `getSignatureStatuses` retorna `None`; a transação pousa no último bloco válido; depois `getBlockHeight` retorna uma altura maior. O reconcile grava `failed:blockhash_expired_never_landed` sem consultar novamente a assinatura. Uma compra fica com tokens na carteira, sem posição e sem reserva. Ela desaparece tanto da consulta de pendentes quanto da recuperação de compras **confirmadas** — [spot_exit_repo.py:80](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:80), [spot_exit_repo.py:90](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:90).

   **Correção:** comprovar ausência novamente depois de observar a expiração; não transformar resposta incompleta de RPC em ausência comprovada. O preenchimento de respostas faltantes com `None` também merece remoção — [spot_reconcile.py:123](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:123).

2. **[spot_reconcile.py:157](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:157) — HIGH — A corrida com o confirm loop pode apagar o vínculo de uma venda confirmada.**

   `mark_failed` protege uma ordem já confirmada, mas seu retorno é ignorado; `clear_exit_pending` executa mesmo assim. Cenário: reconcile guarda uma leitura antiga de ausência; `spot_leg` confirma a venda; reconcile tenta falhá-la, recebe `False` e apaga `exit_order_id`. Se houver crash ou erro antes de fechar a posição, a recuperação da venda confirmada não a encontra, pois depende justamente desse vínculo.

   A próxima saída pode tentar vender novamente o lote; havendo saldo adicional do mesmo mint, pode consumir tokens de outra origem. Referências: [spot_repo.py:144](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:144), [spot_exit_repo.py:98](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:98).

   **Correção:** só limpar o vínculo se a transição terminal vencer, sob coordenação com o mesmo lock. O caminho oposto também precisa respeitar o retorno de `mark_confirmed`, atualmente ignorado pelo `spot_leg` — [spot_send.py:280](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:280). **20 s versus 30 s não evita sobreposição:** os ciclos têm fases independentes.

3. **[spot_exits.py:273](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:273) — HIGH — Crash depois de recusar/falhar a venda deixa a posição permanentemente pendente.**

   Cenário: a Jupiter falha; `spot_leg` persiste `refused`; o processo morre antes de `clear_exit_pending`. Após restart, a posição continua dizendo `submitted_unconfirmed`, então o loop nunca vende. O reconcile procura ordens não confirmadas, órfãos confirmados e abandonadas `admitted/simulated`; não repara esse par posição pendente + ordem `refused/failed` — [spot_reconcile.py:84](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:84).

   **Correção:** recuperar também marcadores associados a ordens terminais sem execução, com limpeza condicional pelo `order_id`.

4. **[admission_context.py:129](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/admission_context.py:129), [launch_entries.py:149](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_entries.py:149) — HIGH — As outras pistas ignoram reservas de compras spot pendentes.**

   A fiação mudou `positions`, mas `pending_attempts` continua consultando somente `meme_live_orders` — [repo.py:130](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/repo.py:130).

   Cenário: limite global de duas vagas, uma posição aberta e uma compra spot admitida ainda não pousada. Memes/lançamento enxergam apenas uma vaga usada e podem admitir outra compra; ambas pousam e o limite é excedido. O capital reservado também fica invisível.

   **Correção:** compor pendentes das três pistas, como o caminho spot já faz — [spot_entry_reads.py:208](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_reads.py:208).

5. **[spot_settle.py:87](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_settle.py:87) — HIGH — A refutação não é uma trava durável; pode reabrir sem intervenção.**

   Cenário: soma fechada chega a `−0,151 SOL`, causando `refuted`; outra posição já aberta fecha com `+0,020 SOL`. Com menos de vinte operações, a soma passa para `−0,131 SOL`, `lane_state` retorna `on` e o próximo ciclo admite entradas. Nenhum reset do Everton ocorreu — [spot_exit_rules.py:146](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:146), [spot_entries.py:88](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:88).

   **Correção:** persistir a refutação até reset explícito, ou reconstruir duravelmente o primeiro cruzamento do limite.

6. **[spot_settle.py:160](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_settle.py:160) — MEDIUM — Recuperar uma compra reinicia seu horizonte de permanência.**

   Cenário: compra pousa, processo cai antes de abrir a posição e volta cinco horas depois. `open_from_order` grava `entry_at=now`; a posição ganha outras quatro horas, embora seu prazo já tenha terminado. A saída temporal depende desse campo — [spot_exit_rules.py:106](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:106).

   **Correção:** preservar o instante da execução; quando indisponível, usar uma referência persistida conservadora, explicitando a origem.

7. **[spot_exits.py:153](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:153) — MEDIUM — Marca antiga autoriza stop/alvo sem validação pela cotação atual.**

   Cenário: marca antiga atingiu alvo, mas a tentativa anterior falhou. No próximo ciclo, a marcação falha e devolve aquela marca; `decide_exit` escolhe `target`. A recotação dentro de `spot_leg` funciona, agora abaixo do alvo, e vende assim mesmo — [spot_exits.py:111](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:111), [spot_send.py:115](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:115).

   **Correção:** conservar a marca antiga para observabilidade, mas fornecer `None` às regras dependentes de preço ou revalidar o gatilho com a nova cotação. Emergência, pedido manual e tempo continuam independentes da marca.

**NICE-TO-HAVE**

- **[spot_heartbeat.py:105](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_heartbeat.py:105) — MEDIUM — Staleness perde sua história no restart.** Cenário: marca persistida tem horas, processo reinicia e publica `mark_stale=false`, pois o contador em memória zerou. Derivar idade de `mark_at` persistido.
- **[spot_exits.py:217](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:217) — LOW — A cotação da venda não fica na linha.** A ordem nasce com `quote=None`, e o envio não atualiza essa coluna. Após restart, a ficha perde a cotação que construiu a transação, embora o fill permaneça disponível. O teste atual inclusive espera `None` — [test_spot_exits.py:145](C:/dev/project-hunter/services/meme-executor/tests/test_spot_exits.py:145).

**O QUE EU FARIA DIFERENTE**

**Tentativas:** não considero aceitável uma indisponibilidade transitória consumir o bloqueio definitivo. O código conta toda linha de venda e bloqueia também por recusas anteriores à assinatura — [spot_exit_repo.py:64](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:64), [spot_exits.py:284](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:284). Isso segue o desenho, portanto é **risco HIGH da política**, não desvio de implementação.

Separaria o número auditável da tentativa do orçamento de falhas pós-assinatura. Falhas transitórias de quote/RPC deveriam gerar backoff e alerta recuperável; falhas de verificação deveriam ter impedimento próprio. O tempo de **122 s não é fixo**: com polling de 20 s, as seis tentativas podem ocorrer aproximadamente em 0/20/40/60/80/120 s, mais latências — [main.py:120](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:120).

**Flag desligada:** manter `brake_positions` e reconcile ativos é correto para dinheiro já existente, embora viole literalmente o item 8 de [spot1-lab-solana.md:211](C:/dev/project-hunter/docs/design/spot1-lab-solana.md:211). Eu corrigiria o contrato.

Há, porém, outro **risco HIGH de desenho**: desligar a flag também elimina marcação e saídas — [main.py:316](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:316), [spot_exits.py:70](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:70). Uma compra pendente pode ser recuperada pelo reconcile já com a flag falsa e ficar aberta sem gestão. Recomendo que a flag impeça novas entradas, preservando gestão da exposição existente. Essa mudança de política cabe ao Everton.

**CONCORDO COM**

- O kill switch bloqueia compras, não vendas, no ponto anterior à assinatura — [spot_send.py:200](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:200).
- Persistir a assinatura antes do broadcast e manter confirmação inconclusiva como pendente está correto — [spot_send.py:210](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:210), [spot_send.py:237](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:237).
- Os deltas vêm do meta da própria transação; o cálculo de PnL usa inteiros e `Decimal`. Não encontrei `float` monetário no caminho examinado — [spot_send_rules.py:161](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:161), [spot_repo_positions.py:212](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:212).
- Não encontrei nova leitura de arquivo `.env` nesses módulos. `SpotConfig` recebe um mapping; `config.py` fornece o ambiente do processo e `signer_present` — [spot_config.py:146](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_config.py:146), [config.py:301](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/config.py:301), [config.py:313](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/config.py:313).

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — registrar os bloqueadores e esclarecer gestão de exposição com a flag desligada.
- **Open Bugs** — registrar expiração concorrente, marcador terminal preso, reservas entre pistas e refutação reversível.
- **Revisoes-Astra/Index** — indexar esta revisão como estática, sem testes executados.
- **Diário 2026-09-19** — registrar as decisões pendentes sobre tentativas e desligamento da mesa.
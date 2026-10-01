**RESUMO**

**DONE_WITH_CONCERNS — não aprovaria ainda a garantia de prazo por episódio.** Dos três must-fix anteriores:

| Requisito | Parecer |
|---|---|
| Saída por tempo sobrevive à confirmação | **Absorvido:** há fallback independente de preço, com horário atualizado após a cotação. [spot_exit_rules.py:157](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:157), [spot_exit_confirm.py:118](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:118). |
| Não gastar tentativa antes de confirmar | **Absorvido:** retorno sem venda precede a atualização do contador. [spot_exits.py:206](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:206). |
| Prazo durável, indisponibilidade e stop↔alvo | **Parcial:** persistência e inversões diretas estão contempladas, mas há caminhos que ignoram ou reiniciam o episódio. [spot_exit_repo.py:213](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:213), [spot_exit_rules.py:162](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:162). |

Mantive a distinção da memória entre corrigir a confirmação e acrescentar a política de saída forçada: [revisão KB-0172:32](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/KB-0172-perdas-spot-1.md:32).

**ARQUIVOS**

Revisei os nove arquivos indicados e os caminhos relacionados de marcação, execução e reconciliação. Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Inspeção estática. `git diff --check -- <arquivos rastreados do escopo>` retornou código **0**, apenas com aviso de conversão CRLF→LF em `spot_exit_rules.py`.

Não executei pytest nem integração com Postgres nesta revisão estritamente sem escritas. Não afirmo que os testes passam.

**MUST-FIX**

1. **HIGH — episódio vencido não libera tentativa quando a marca inicial falha.**  
   [spot_exits.py:133](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:133) calcula o motivo sem consultar o episódio; se recebe `None`, retorna antes de `plan_exit`.

   **Cenário:** stop observado em `t=0`, confirmação indisponível e episódio persistido. Em `t=70`, a marca inicial falha. Sem emergência, pedido manual ou horizonte vencido, nenhuma tentativa chega à perna. Repetir isso mantém o stop sem aplicação do limite de 60 segundos.

   **Correção:** avaliar o episódio vencido também quando falta marca, preservando as guardas de ordem pendente, bloqueio e backoff. Ausência de marca deve permitir a tentativa forçada prevista, cuja perna recota.

2. **HIGH — alvo com confirmação indisponível apaga um episódio de stop existente.**  
   [spot_exit_rules.py:162](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:162) retorna `stop_since=None` quando nenhum dos motivos atuais é stop. [spot_exit_confirm.py:150](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:150) persiste essa remoção.

   **Cenário:** `t=0`: marca alvo, confirmação stop → abre episódio. `t=20`: marca alvo, confirmação indisponível → apaga episódio. `t=40`: alvo→stop → começa outro prazo. A alternância pode repetir sem atingir o limite, embora nunca tenha ocorrido a recuperação descrita no contrato.

   **Correção:** considerar o episódio anterior na decisão; confirmação indisponível não deve encerrá-lo. Acrescentar teste sequencial com releitura do estado persistido.

3. **MEDIUM — venda falhada reinicia o orçamento de confirmação sem recuperação.**  
   A perda começa em **`set_exit_pending`**, não apenas em `clear_exit_pending`: ambos substituem o JSON inteiro. [spot_exit_repo.py:100](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:100), [spot_exit_repo.py:105](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:105).

   **Cenário:** episódio vence; venda forçada falha transitoriamente na construção da transação; posição continua aberta e sem recuperação. Na avaliação seguinte, a divergência abre outros 60 segundos. Cada falha pode acrescentar novamente esse atraso, além do backoff.

   **Correção:** preservar a chave durante a ordem pendente e sua limpeza quando a venda falha. Sob o contrato de **prazo por episódio**, não considero aceitável reiniciá-lo por tentativa. Se o desejado fosse prazo por tentativa, seria outra política.

**NICE-TO-HAVE**

- **Cotação envelhecida: sim, é possível.** Entre confirmação e `swap` existem duas transações de banco, sem verificação de idade na perna. Um atraso longo pode deixar o gatilho desatualizado; a simulação verifica execução e limites, não se o stop/alvo continua verdadeiro. Recomendo medir essa idade e estabelecer validade máxima; ao recotar, reconfirmar o gatilho. [spot_exits.py:234](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:234), [spot_send.py:122](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:122), [spot_send.py:207](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:207).

- **`high_water_sol`: pode registrar um pico fantasma, mas não encontrei efeito nas saídas atuais da spot.** `set_mark` usa `GREATEST`; corrigir a marca depois não desfaz o pico. A regra spot não usa esse campo, e `wallet_from` usa a marca atual. Não bloquearia este diff por isso, mas não trataria esse máximo como confirmado. [spot_repo_positions.py:95](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:95), [spot_exit_rules.py:103](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:103), [admission.py:275](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/admission.py:275).

- **4xx/sem rota:** esperar o prazo aumenta a exposição, mas está dentro da política proposta para confirmação indisponível. Não recomendo converter automaticamente isso em venda imediata. Preservaria, porém, a distinção `quote_refused`/`quote_failed`: a confirmação atualmente agrupa todas as exceções como `quote_failed`, enquanto a perna distingue recusas não transitórias. [spot_exit_confirm.py:91](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:91), [spot_send.py:131](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:131).

**O QUE EU FARIA DIFERENTE**

Testaria o **ciclo completo do episódio**, incluindo vários ticks, reconstrução da posição, marca indisponível após vencimento e tentativa falhada. O teste atual de marca indisponível verifica apenas um episódio recém-aberto; não exercita o prazo vencido. [test_spot_exit_confirm.py:245](C:/dev/project-hunter/services/meme-executor/tests/test_spot_exit_confirm.py:245).

Sobre **espera sem limite**: os achados acima invalidam o limite de 60 segundos. Com horizonte válido, ainda existe a saída por tempo; portanto, não afirmo espera infinita em toda posição. Já bloqueio após falhas duras e ordem pendente continuam sendo limites preexistentes à progressão automática. [spot_exit_rules.py:110](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:110), [spot_exits.py:126](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:126).

**CONCORDO COM**

- **Forçado recotar na perna está correto:** a saída passa a decorrer do episódio vencido; a cotação contrária não confirmou o gatilho e pode ter tolerância diferente. O código descarta essa cotação e recalcula a tolerância pelo motivo final. [spot_exit_confirm.py:139](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:139).
- Reutilizar a cotação quando há confirmação, validar par/lote antes de usá-la e manter a regra decisória pura. [spot_exit_confirm.py:93](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_confirm.py:93).
- O `CASE` JSONB preserva outras chaves e impede alteração do episódio com `exit_order_id` preenchido. O problema está no restante do ciclo de vida. [spot_exit_repo.py:213](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_repo.py:213).

**OBSIDIAN**

Nenhuma página alterada. Deveriam ser atualizadas:

- **Open Bugs** — registrar as três lacunas no prazo por episódio.
- **KB-0172 — perdas da spot/1** — distinguir confirmação corrigida de prazo ainda incompleto.
- **Mesa-spot-1** — documentar recuperação, indisponibilidade e preservação do episódio após falha.
- **Revisões-Astra — confirmação de stop/alvo spot/1** — guardar este parecer e as provas das correções.
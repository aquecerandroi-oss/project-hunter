**BLOQUEIA a aprovação do M1 pelo heartbeat compartilhado.** Os números sustentam capacidade em regime estável, com ressalvas.

1. **Método:** medir CPU após drenar backlog é legítimo para capacidade estável: médias de **36,6%–64,2%**, com **198/200 = 99% ok**. Não prova CPU sempre abaixo de 70%: há picos de **100,2%**, e falta sustentar que o critério original era *média* ([prova:165](C:/dev/project-hunter/.claude/state/t16b-proof.md:165), [prova:192](C:/dev/project-hunter/.claude/state/t16b-proof.md:192)). **Os 11 stale e os ranks mencionados não aparecem no arquivo lido.** Mesmo presentes, rank por volume não prova ausência de eventos na origem; seria necessário comparar recepção da fonte e atraso do worker. Se forem 11 mercados não-ok entre 200, **189/200 = 94,5%**, abaixo da meta.

2. **Dos quatro defeitos:**
   - **Heartbeat: BLOQUEIA.** Cenário: um shard morre, outro renova a chave e mascara a perda de coleta daquela fatia. Corrigir identificação/agregação por shard e validar morte isolada; o M1 exige heartbeats reais ([prova:247](C:/dev/project-hunter/.claude/state/t16b-proof.md:247), [M1:7](C:/dev/project-hunter/docs/plans/M1.md:7)).
   - **Gaps fora do universo e qualidade afetada por backlog: NÃO BLOQUEIAM**, mantendo a degradação explícita ([prova:254](C:/dev/project-hunter/.claude/state/t16b-proof.md:254)).
   - **Teste de 2 s: não demonstra bloqueio de produto**, mas `2323 < 2000` sozinho não comprova flakiness. Antes do aceite, apresentar execução verde exigida pelo plano ([prova:263](C:/dev/project-hunter/.claude/state/t16b-proof.md:263), [M1:32](C:/dev/project-hunter/docs/plans/M1.md:32)).

3. **Corrigir afirmações sem sustentação suficiente:**
   - A abertura diz **“NÃO CUMPRIDA”**, contradizendo a conclusão ([prova:6](C:/dev/project-hunter/.claude/state/t16b-proof.md:6)).
   - “Picos no fecho do minuto” carece de correlação temporal; “95 gaps todos fora do universo” carece da consulta/saída discriminada ([prova:189](C:/dev/project-hunter/.claude/state/t16b-proof.md:189)).
   - `COUNT(*) = 200` não comprova **200 mercados distintos com candles finais**; colar consulta que verifique essas condições ([prova:180](C:/dev/project-hunter/.claude/state/t16b-proof.md:180)).
   - Perfil de uma corrida não isola causalmente recovery versus ingestão; comparação anterior/posterior também não controla carga e backlog ([prova:230](C:/dev/project-hunter/.claude/state/t16b-proof.md:230)).

**OBSIDIAN**

- **Workers** — registrar topologia validada, limites da medição e heartbeat por shard como bloqueio. Nenhuma página foi alterada.
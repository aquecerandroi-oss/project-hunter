**RESUMO**

Como `database-architect`: **DONE_WITH_CONCERNS — revisão concluída; desenho ainda precisa de ajustes.** Concordo com a estrutura geral, mas não implementaria a ativação de v2 com pesos escolhidos agora. Também corrigiria a identidade das revisões de baseline e explicitaria o downgrade e a retenção.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei pytest nem migrações: esta foi uma revisão estática em modo OPINIÃO. Consultei a documentação oficial do PostgreSQL 16 para confirmar o comportamento dos enums e das partições.

**MUST-FIX**

1. **Item 8 — retirar 0,05 de `anomalies` é uma nova decisão quantitativa.**

   A soma 0,90, consenso zero e contribuição Early-Movement assinada estão fechados; a distribuição individual não. O diálogo deixa isso explicitamente para o congelamento anterior a T2.4 ([diálogo:239](C:/dev/project-hunter/.claude/state/dialogue-M2.md:239), [checklist:246](C:/dev/project-hunter/.claude/state/dialogue-M2.md:246)). O brief realmente conflita com isso ao exigir v2 ativo ([brief:16](C:/dev/project-hunter/.claude/state/brief-T2.1-analysis-schema.md:16)).

   **Falha concreta:** reduzir o peso de anomalias em 0,05 reduz em cinco pontos um caso com componente 100, podendo mudar HOT para WATCHING sem aprovação dessa regra. A justificativa de dupla contagem é uma hipótese razoável para discussão, não consequência matemática do fechamento.

   **Correção:** concluir o contrato numérico antes de semear/ativar v2, ou corrigir o brief para adiar essa parte. Não publicar uma v2 provisória que depois será reescrita.

2. **Item 8 — separar migração e seed não basta para garantir uma transição correta.**

   O índice atual permite no máximo uma versão ativa ([analysis.py:137](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:137)). O seed preserva `is_active` no conflito, mas **reescreve `weights`** ([seed.py:300](C:/dev/project-hunter/infra/scripts/seed.py:300)).

   **Falhas concretas:**
   - Migração desativa v1; seed falha antes de inserir v2: nenhuma versão ativa.
   - Existe outra versão ativa, v2 ainda não existe: inserir v2 ativa viola o índice.
   - Após downgrade, v2 permanece inativa; upgrade desativa v1; seed encontra v2 existente e não a reativa: nenhuma versão ativa.
   - Alterar o conteúdo de v2 no seed muda retrospectivamente o significado dos scores que referenciam essa versão.

   **Correção:** depois do congelamento, inserir/verificar o conteúdo de v2 e fazer a transição autorizada **na mesma transação**, com tratamento explícito de versões já existentes e de outra versão ativa. Seed deve validar conteúdo congelado, sem substituí-lo silenciosamente. O teste atual também precisa evoluir: além de preservar ativação, ainda descreve refresh do vetor ([teste:288](C:/dev/project-hunter/packages/core/tests/integration/test_schema_seed_and_partitions.py:288)).

   No downgrade, “reativar v1 se ninguém estiver ativo” não resolve sozinho: se v2 continuar ativa, o código antigo pode receber o formato aninhado. Defina a reversão completa da transição; não reative versões apenas pela ausência de uma ativa.

3. **Item 4 — a chave proposta confunde retry com recomputação.**

   O contrato exige novas revisões imutáveis e disponibilidade causal ([M2.md:51](C:/dev/project-hunter/docs/plans/M2.md:51)).

   **Falha concreta:** às 10h você calcula a janela terminada às 09h. Às 10h15 chega um backfill dessa mesma janela. Mercado, feature, versões, hora, `window_end` e `source` continuam iguais, mas amostra, mediana e MAD mudaram. Seu UNIQUE impede persistir a revisão corrigida; `DO NOTHING` mantém a incompleta e UPDATE viola a imutabilidade.

   **Correção:** incluir uma identidade estável do conjunto de entrada/recomputação, distinguindo nova revisão de reentrega da mesma operação. Pode ser um fingerprint canônico das entradas e do corte. Apenas acrescentar `available_at=now()` à chave criaria outra baseline a cada retry.

4. **Item 2 — o downgrade precisa remover dependências tipadas antes da troca.**

   **Sim, `ALTER TABLE opportunity_history ALTER COLUMN status TYPE ...`, sem `ONLY`, alcança as partições.** `status` não é a chave de particionamento; a tabela particiona por `ts` ([analysis.py:205](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:205)). A operação exige prever reescrita e bloqueio das tabelas afetadas. [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/16/sql-altertable.html).

   A armadilha é deixar o CHECK de expiração ou recriar antecipadamente o índice antigo, cujo predicado contém casts explícitos para `opportunity_status` ([analysis.py:169](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:169)).

   **Falha concreta:** após renomear o enum, expressões dependentes continuam ligadas ao tipo antigo. Converter a coluna pode falhar ao reconstruir uma comparação entre os dois tipos, mesmo sem nenhuma linha com `EXTENDED`.

   **Correção:** retirar o CHECK novo e o default; manter o índice antigo removido; converter **opportunities e history**, depois restaurar default e índice da 0002. A guarda precisa consultar também o histórico: episódio atualmente EXPIRED pode ter uma amostra EXTENDED antiga. Verificar igualmente `market_regimes.regime` e `anomalies.type` ([analysis.py:119](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:119), [analysis.py:83](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:83)).

   Faça as guardas antes de remover conteúdo da 0003 e mantenha a operação atômica.

5. **Itens 4 e 6 — retenção precisa de um protocolo de preservação, não apenas de um índice.**

   O fechamento exige preservar dependências enquanto houver amostras dependentes ([diálogo:250](C:/dev/project-hunter/.claude/state/dialogue-M2.md:250)).

   **Falha concreta:** o job verifica que B não tem referências; um scorer que mantém B em cache grava seu envelope; o job apaga B. O histórico recém-gravado fica irrecuperável. Outra variante é apagar B e reinserir o mesmo UUID com conteúdo diferente: o trigger apenas de UPDATE não impede isso.

   **Correção:** definir como escrita de referências e limpeza se coordenam. UUID[] com GIN acelera busca, mas não cria FK nem elimina essa corrida. Não precisa implementar o job inteiro em T2.1; precisa fechar o contrato que permitirá implementá-lo corretamente.

**NICE-TO-HAVE**

- **Item 1:** testar rótulos **e ordem**, usando `enumsortorder`, em cada revisão e após downgrade. O teste atual de head já consulta essa ordem ([test_migrations.py:215](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:215)). `Mapping` é uma interface de tipos, não congelamento em runtime; o essencial é usar literais históricos, sem derivação de `ALL_ENUMS`.
- **Item 4:** acrescentar invariantes locais: janela válida, contagens não negativas, `sample_size <= expected_size`, cobertura entre 0 e 1 e MAD não negativo. Não exigir o gate de maturidade na inserção: uma baseline em construção pode existir.
- **Item 4:** corrigir a estimativa. **200 × 20 × 24 = 96 mil linhas por refresh**; se todos os buckets forem recomputados a cada hora, são **2,304 milhões/dia**, ou 207,36 milhões em 90 dias. Os 96 mil/dia pressupõem atualizar apenas um bucket por hora. Não exigiria particionamento sem medir, mas fecharia essa cadência antes.
- **Item 5:** em linhas legadas sem evidência de qualidade, preferiria `evaluation_state=unknown` até reavaliação. Um default `ok` para todas elas atribui qualidade que a migração não verificou; `active + unknown` é estado previsto ([M2.md:56](C:/dev/project-hunter/docs/plans/M2.md:56)).

**O QUE EU FARIA DIFERENTE**

- **Item 6:** manteria o envelope como fonte única inicialmente. Se a retenção usar consultas de contenção, consideraria GIN sobre a expressão JSONB dos IDs, evitando uma segunda representação sincronizada manualmente. Se quisermos integridade referencial no banco, usaria uma tabela de referências com FK; UUID[] não oferece isso.
- **Item 7:** copiaria com lista explícita de colunas, **gerando novos `id` locais e preservando `event_id`**. Copiar BIGSERIAL entre duas filas já populadas pode colidir. A identidade durável é `event_id`; o número sequencial não é marca de progresso por commit ([DATABASE.md:902](C:/dev/project-hunter/docs/DATABASE.md:902)).
- Exigiria testes de ida e volta com duas partições populadas, EXTENDED somente no histórico, NORMAL aberto, EXPIRED consistente, recomputação após backfill e os estados de ativação citados acima.

**CONCORDO COM**

- **1 — Enums congelados:** sim. Corrige exatamente a leitura atual de rótulos em runtime ([enums.py:79](C:/dev/project-hunter/infra/migrations/ddl/enums.py:79)). Separe tipos novos de alterações dos tipos existentes.
- **2 — ADD VALUE transacional:** correto. Pode adicionar; não pode usar o novo valor antes do commit. Isso inclui usos em defaults e expressões SQL, não apenas INSERT. Não há motivo para autocommit no desenho apresentado. [PostgreSQL: ALTER TYPE](https://www.postgresql.org/docs/16/sql-altertype.html).
- **3 — Caixa e enum unitário:** concordo com `EARLY/DEVELOPING/EXTENDED/NONE`, registrando a grafia definitiva. Concordo também com `baseline_sampling(per_minute)`: um único membro não é defeito e segue a convenção de enum por conceito ([DATABASE.md:14](C:/dev/project-hunter/docs/DATABASE.md:14)).
- **4 — Baselines:** UUID7, metadados temporais, Decimal, trigger contra UPDATE e grants propostos são adequados, sujeitos aos ajustes de identidade e retenção. O índice sugerido é um ponto de partida; a consulta também precisa filtrar versões compatíveis.
- **5 — Episódios e anomalias:** concordo com o índice por `expired_at`, a bicondicional e a unicidade de anomalia ativa. Para inconsistências ou duplicatas ambíguas, recusar com contagem e instrução é correto. A 0002 combina recusa de contradições com backfill realmente derivável ([0002:214](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:214), [0002:229](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:229)); não inventaria `expired_at`.
- **7 — Outbox:** a forma proposta basta para T2.9; não vejo coluna adicional irreversivelmente necessária agora. Preserve os CHECKs existentes e o grant da sequence ([0002:104](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:104), [shadow.py:127](C:/dev/project-hunter/infra/migrations/ddl/shadow.py:127)). A absorção também precisa coordenar a troca dos escritores; copiar uma vez enquanto a fila antiga recebe eventos não garante completude.
- **8 — Formatos distintos por versão:** v1 plana e v2 aninhada são honestas se cada versão tiver conteúdo congelado e interpretação explícita. O problema é escolher e ativar agora os números ainda não fechados.

**OBSIDIAN**

- **Features (Feature Engine)** — registrar identidade das revisões, recomputação após backfill, cadência e preservação de dependências.
- **Anomalies (Anomaly Engine)** — registrar unicidade ativa, qualidade independente e tratamento conservador do legado.
- **Diálogo Claude ⇄ Astra — M2** — registrar o conflito entre v2 ativo no brief e congelamento quantitativo em T2.4.
- **Architecture Decisions** — registrar downgrade dos enums compartilhados e contrato de retenção/replay.
- **Revisões Astra / T2.1 — desenho da 0003_analysis** — guardar esta revisão e vincular às provas da futura implementação.
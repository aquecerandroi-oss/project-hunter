## RESUMO

**DONE_WITH_CONCERNS — o desenho da migração está correto para a corrida com edição do original.** Há dois ajustes antes de fechar a entrega: alinhar a revisão esperada em cada commit e tornar determinístico o teste da trava. A quinta FK ausente de `_GUARDED` não permite perda de dados; classifico como melhoria de diagnóstico.

A revisão considera o pré-registro [EXP-M27](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M27-gemeo-sem-creator-dump.md:44) e a [revisão anterior da H-031b](/C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/H-031b-diff.md:28).

**1. Trava e corrida**

Para uma linha existente efetivamente travada, **não há janela de alteração do original entre guarda, cópia e pós-checagem**: `_LOCK` vem primeiro, e todas as operações permanecem na transação de migração. [DDL:76](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:76), [DDL:132](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:132), [env.py:136](/C:/dev/project-hunter/infra/migrations/env.py:136).

Em `READ COMMITTED`:

- **UPDATE concorrente vence primeiro:** o `FOR UPDATE` espera; após o commit, reavalia o predicado sobre a versão atualizada. Como o predicado da trava é apenas o ID, uma mudança de `params` ou `status` ainda permite travá-la. As guardas seguintes enxergam o documento novo.
- **DELETE concorrente vence primeiro:** após esperar pelo commit, o `FOR UPDATE` não retorna a linha; sem recriação, a guarda seguinte acusa original ausente.
- **Migração trava primeiro:** UPDATE/DELETE esperam até terminar a transação.

Esse é o comportamento documentado pelo [PostgreSQL 16 para atualização, exclusão e reavaliação em Read Committed](https://www.postgresql.org/docs/16/transaction-iso.html#XACT-READ-COMMITTED).

Duas ressalvas de escopo: a trava não protege a **ausência** de uma linha contra posterior inserção; e, numa reaplicação com gêmea preexistente, `DO NOTHING` e a pós-checagem não a travam explicitamente. Não venderia isso como congelamento de ambas as linhas contra qualquer escrita administrativa. Para a corrida solicitada — `--set-param` no original existente — a proteção está adequada. [DDL:76](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:76), [DDL:105](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:105).

**2. Colisão do ID `…0022`**

**O erro de PK é aceitável e desejável.** `ON CONFLICT (name, version)` não absorve colisão exclusiva de `id`: se `…0022` pertence a outro nome, o INSERT falha e a migração não é confirmada. Idempotência não significa aceitar identidade incompatível. Eu não substituiria nem atualizaria automaticamente essa linha. [DDL:105](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:105), [constraints:95](/C:/dev/project-hunter/infra/migrations/ddl/meme_lab.py:95).

A reaplicação só é aceita quando a gêmea ainda corresponde ao original **atual** mais o override. Se o original mudou depois da primeira aplicação, a pós-checagem pode recusar; isso é coerente com a validação estrita proposta. [DDL:113](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:113).

**3. Downgrade e referências**

A afirmação “every table” está errada: são cinco FKs, e `meme_mature_opportunities` está ausente. Porém, sua FK sem ação de exclusão explícita impede o DELETE; a transação falha sem apagar a gêmea ou a oportunidade. Portanto, **não é must-fix de integridade**. Eu acrescentaria a quinta guarda e seu teste para manter o diagnóstico “contar, nomear, orientar”, como na revisão madura. [Guarda atual:145](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:145), [FK:114](/C:/dev/project-hunter/infra/migrations/ddl/meme_mature_opportunities.py:114), [precedente:142](/C:/dev/project-hunter/infra/migrations/ddl/meme_mature_chart_arms.py:142).

Sobre referências sem FK:

- `meme_decision_tapes` guarda **IDs de propostas**, não uma coluna de ID do conjunto. A migração não apaga fitas; propostas existentes da gêmea já impedem o downgrade. [Schema:34](/C:/dev/project-hunter/infra/migrations/ddl/meme_decision_tapes.py:34), [guarda:145](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:145).
- `meme_lab_ticks.refusals` guarda contagens por nome do conjunto, em JSON. Esses registros permanecem após o DELETE da semente. Isso não equivale à preservação de um snapshot completo dos parâmetros, mas não identifiquei aqui perda concreta que justifique outra guarda obrigatória. [Schema e contrato:9](/C:/dev/project-hunter/infra/migrations/ddl/meme_lab_ticks.py:9), [DELETE:126](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:126).

Não estendo essa conclusão a conteúdo arbitrário que alguém possa gravar manualmente em JSON.

**4. Cobertura das guardas**

As quatro guardas explícitas de downgrade estão bem isoladas. Particularmente, o teste de aposta usa uma proposta de `OPERATOR_6` e uma aposta da gêmea: remover a guarda de apostas produz erro de FK, que não satisfaz a mensagem esperada. A guarda de propostas não mascara esse caso. [Teste:265](/C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069.py:265).

As recusas de origem inativa, relógio inválido, switch inválido e estranho também verificam mensagens específicas; remover cada bloco muda o resultado esperado. Contudo, não estão cobertos individualmente original inexistente, cada campo de identidade da pós-checagem, colisão exclusiva de PK ou reaplicação efetiva do seed. [Guardas:81](/C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:81), [estranho:151](/C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:151).

**O teste concorrente é útil, mas não prova deterministicamente a trava.** Detalho abaixo.

**5. RLS e grants**

Consistente com `0063/0065`: inserir uma linha numa tabela global não pede nova política nem novo grant. API e worker já têm leitura de `meme_rule_sets`; a migração mantém `research_only`. [Contrato §34.1](/C:/dev/project-hunter/docs/DATABASE.md:6069), [privilégios:43](/C:/dev/project-hunter/infra/migrations/ddl/meme_lab.py:43), [seed:106](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:106).

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit. Revisão dos cinco arquivos solicitados, precedentes e referências relacionadas.

## TESTES

**Não executei pytest, migrations ou testes de RLS nesta revisão OPINIÃO.** Não há resultado de integração que eu possa declarar aprovado.

Verificações somente de leitura:

- `git diff --check -- <cinco caminhos revisados>`: saída vazia, código `0`. Isso não valida arquivos não rastreados.
- Inspeção textual do grafo de revisões retornou:

```text
0068_meme_wallet_exceptions  -> 0067_meme_token_state_history
0069_meme_absorb_semdump_arm -> 0068_meme_wallet_exceptions
0070_meme_mature_chart_arms  -> 0069_meme_absorb_semdump_arm
Head: 0070_meme_mature_chart_arms
```

## MUST-FIX

1. **Alinhar `HEAD_REVISION` e contagem com o conteúdo de cada commit.** Na leitura realizada, a revisão madura já era `0070`, mas o teste ainda declarava `0069_meme_mature_chart_arms` e documentava 29 conjuntos. **Cenário:** banco sobe pela cadeia nova, mas a suíte espera uma revisão inexistente/contagem antiga. [Revisão:36](/C:/dev/project-hunter/infra/migrations/versions/0070_meme_mature_chart_arms.py:36), [teste:43](/C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:43), [contagem documentada:74](/C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:74).

2. **Eliminar o falso positivo possível no teste concorrente.** Hoje ele dorme três segundos e observa `worker.is_alive()`. **Cenário:** sem `_LOCK`, a thread demora mais de três segundos para chegar à guarda; a outra conexão altera para `1m` e confirma; a thread então recusa corretamente, satisfazendo todas as asserções mesmo sem trava. [Teste:190](/C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:190).

   Eu esperaria, com prazo limitado, evidência de bloqueio no backend da migração — por exemplo, `pg_blocking_pids()` apontando para a conexão que segura o original — antes de confirmar a alteração. Depois verificaria recusa e término da thread. Remover `_LOCK` precisaria fazer esse teste falhar.

## NICE-TO-HAVE

- Acrescentar `meme_mature_opportunities` à guarda, corrigir “every table” e testar a mensagem.
- Testar original ausente/DELETE concorrente, colisão exclusiva de PK e reaplicação do seed com gêmea correta.
- Alterar um parâmetro válido não relacionado ao switch antes do upgrade e verificar a cópia. A comparação atual em banco recém-semeado também passaria numa implementação que copiasse constantes equivalentes. [Teste:145](/C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069.py:145).
- Ajustar §72: se a migração obtiver a trava primeiro, um `--set-param` posterior espera e executa **depois**; essa alteração futura não é julgada pela migração. [Documentação:8932](/C:/dev/project-hunter/docs/DATABASE.md:8932).

## O QUE EU FARIA DIFERENTE

**6. Separaria em três entregas coerentes, com testes acompanhando cada estado:**

| Entrega | Conteúdo | Head esperado | Ativos em banco limpo |
|---|---|---|---:|
| A | Suporte ao switch já funcionando no worker; sem sementes novas | `0068_meme_wallet_exceptions` | 26 |
| B | Gêmea + testes + documentação correspondente | `0069_meme_absorb_semdump_arm` | 27 |
| C | Braços maduros, quando liberados | `0070_meme_mature_chart_arms` | 30 |

Na entrega B, entrariam também os ajustes de `test_migrations.py` para **0069/27**. A entrega C faria **0070/30** e incluiria os testes renomeados da revisão madura.

**Não incluiria a 0070 retida no commit implantável da gêmea:** `upgrade head` a aplicaria junto, contrariando a retenção expressa até J estar congelado. Validaria cada entrega a partir do conteúdo exato que será entregue, sem depender dos arquivos retidos no diretório compartilhado. [Restrição da 0070:12](/C:/dev/project-hunter/infra/migrations/versions/0070_meme_mature_chart_arms.py:12).

## CONCORDO COM

Copiar os parâmetros vivos, travar o original antes de validar, repetir `_VALID` na cópia e na pós-checagem, recusar identidades incompatíveis e preservar os grants existentes. [DDL:62](/C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:62).

Também manteria os dois deploys — código primeiro, semente depois — já registrados no [EXP-M27:80](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M27-gemeo-sem-creator-dump.md:80).

## OBSIDIAN

- **H-031b-diff** — registrar a aprovação da lógica de trava e a limitação da prova por `sleep`.
- **EXP-M27 — O gêmeo sem creator_dump** — atualizar a cadeia 0068→0069→0070 e a separação das entregas.
- **Revisoes-Astra/Index** — indexar este parecer de banco, distinguindo inspeção estática de validação executada.
**RESUMO**

**Não reportaria DONE ainda.** Há três bugs concretos e duas lacunas no contrato de aceite. Revisei como `database-architect`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Executados com sincronização de dependências, bytecode e cache do pytest desabilitados:

- `uv run pytest packages/core/tests/unit/test_strategies_canonical.py -q` → `19 passed in 0.47s`.
- `uv run python infra/scripts/check_file_size.py` → `scanned 138 files; 0 over budget, 0 grandfathered`.
- Sondas em memória com `uv run python -B -` confirmaram os defeitos de Decimal e coorte abaixo.

Não executei testes de banco, migrações ou `alembic check`; portanto, não certifico esses gates.

**MUST-FIX**

1. **HIGH — O canônico arredonda e depende do contexto Decimal.**  
   [canonical.py:62](C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:62) usa `normalize()` e depois `quantize()`, operações sujeitas ao contexto. Saída real para `Decimal("1.23456789")`:

   ```text
   precision 6 canonical b'{"a":"1.23457"}'
   precision 28 canonical b'{"a":"1.23456789"}'
   ```

   Também confirmei que dois Decimals distintos, terminados em `...67891` e `...67892`, produzem os mesmos bytes; `Decimal("1E+30")`, finito, lança `InvalidOperation`. **Cenário:** mudar a precisão entre emissão e recovery muda `params_hash` e a identidade do sinal; parâmetros diferentes também podem colidir. Corrigir com formatação exata independente do contexto e remoção de zeros apenas na parte fracionária.

2. **HIGH — Upgrade falha com outcomes encerrados existentes.**  
   [0002_shadow_lab.py:182](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:182) atribui `pending_entry` às linhas anteriores; [linha 205](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:205) instala o CHECK sem backfill intermediário. **Cenário:** um banco em 0001 contém `result='target'`; a linha recebe `pending_entry`, viola a bicondicional e aborta o upgrade. Outcomes abertos com entrada já realizada também seriam classificados incorretamente como pendentes. Definir conversão dos estados legados e testar **0001 populada → 0002**, além do banco vazio. Não verifiquei se há essas linhas no banco operacional.

3. **MEDIUM — Coorte aceita pelo validador é recusada pelo próprio parser.**  
   [enums.py:324](C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:324) usa `.match()` com `$`. Confirmei:

   ```text
   cohort 'prospective\n' is_valid True
   run_id_error ValueError
   ```

   O mesmo ocorre com `replay:<uuid>\n`. **Cenário:** uma coorte validada passa à persistência/parser e falha, interrompendo o processamento. Usar `.fullmatch()` e adicionar vetores com newline. O texto da regex coincide com [a migração:128](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:128), mas isso não garante comportamento idêntico entre motores; o PostgreSQL distingue os modos de tratamento de newline. [Documentação oficial](https://www.postgresql.org/docs/16/functions-matching.html#POSIX-MATCHING-RULES).

4. **HIGH — O aceite “integridade episódio↔outcome; sem órfãos” não está garantido.**  
   [agents_shadow.py:99](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents_shadow.py:99) referencia somente `agent_signals.id`. Não exige outcome existente, estado aberto nem correspondência de mercado/versão/coorte. O próprio [teste:415](C:/dev/project-hunter/packages/core/tests/integration/test_schema_shadow.py:415) cria sinal sem outcome e vincula episódio a **outro mercado**, aceitando a primeira inserção.

   **Cenário:** sinal ativo de BTC fica associado ao slot de ETH; o `tracking_hold` protege ETH e pode deixar BTC perder a coleta. Outro caso: outcome pendente sem episódio desaparece da reconciliação baseada em slots. Isso respeita a FK literal do brief, mas **não prova o aceite S0**. É necessário garantir e testar esses vínculos, ou registrar explicitamente quais garantias serão entregues por S2 sem marcar esse item como concluído agora.

5. **MEDIUM — A justificativa da outbox ensina um checkpoint inseguro.**  
   [agents_shadow.py:114](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents_shadow.py:114) chama BIGSERIAL de “gapless” e sugere inferir despacho pelo maior ID. **Cenário:** transação A reserva 10; B reserva 11 e commita primeiro; despachante publica 11 e avança o cursor; A commita 10 depois, ficando esquecida. Rollback também deixa lacunas, conforme a [documentação do PostgreSQL](https://www.postgresql.org/docs/16/functions-sequence.html).

   Corrigir esse contrato antes de S2: procurar pendências por `dispatched_at IS NULL`, independentemente do maior ID publicado. BIGSERIAL pode permanecer.

**NICE-TO-HAVE**

- Congelar também os **rótulos** dos enums por revisão. Hoje só os nomes estão congelados; [ddl/enums.py:81](C:/dev/project-hunter/infra/migrations/ddl/enums.py:81) ainda lê membros de `ALL_ENUMS` em runtime. Uma futura adição de membro voltará a alterar retroativamente 0001.
- Acrescentar teste de exclusão da estratégia-pai e testes de transições encerradas → abertas; a coerência de uma linha isolada não prova uma máquina de estados.
- Antes do DONE, atualizar `DATABASE.md` com as exceções e alinhar [M2.md:24](C:/dev/project-hunter/docs/plans/M2.md:24), que ainda atribui a migração `0002` a T2.1.

**O QUE EU FARIA DIFERENTE**

Sobre as quatro decisões:

| Decisão | Parecer |
|---|---|
| **1. Bicondicional e `result='open'` nos desconhecidos** | **Aceitável**, com contrato explícito. Em S2/S3, `WHERE result='open'` incluiria `no_entry` e `censored`: contagem errada e possibilidade de reprocessar encerrados. Abertos devem ser exclusivamente `tracking_state IN ('pending_entry','active')`. Encerrado avaliável exige resultado conhecido e disponibilidade da métrica; funding ausente não deve virar censura do outcome. A separação já está documentada em [agents.py:171](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:171). |
| **2. INITIAL_ENUMS/SHADOW_ENUMS** | **Correto para os nomes.** Num banco convencional já em 0001, mudar a lista Python não altera os tipos existentes. Exceção: se 0001 foi aplicada usando uma árvore intermediária que já incluía o novo enum, [0002:56](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:56) tentará recriá-lo. Verificar esse estado; não mascarar com “ignore duplicate” sem validar os rótulos. |
| **3. BIGSERIAL, grants e colunas** | **BIGSERIAL e USAGE são adequados**, removida a promessa de ordenação por commit. `available_at` seria útil para backoff durável por evento: sem ele, restart perde o prazo e um evento problemático pode monopolizar tentativas. Não é coluna obrigatória para correção se S2 definir outra política. `UNIQUE(event_id)` serve ao stream atual; `(stream,event_id)` só será necessário se o mesmo evento puder ter múltiplos destinos. Reconciliação após perda do Redis precisa considerar também eventos já marcados despachados. |
| **4. BEFORE DELETE e cascade** | **Eu manteria.** A FK de [agents.py:73](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:73) cascateia a exclusão da estratégia, e a trigger de [shadow.py:110](C:/dev/project-hunter/infra/migrations/ddl/shadow.py:110) barra versões ativadas. O custo é impedir a limpeza de uma estratégia com qualquer versão historicamente ativada. Para preservar evidência, depreciação é a operação apropriada; remoção excepcional continua sendo decisão operacional sua. |

**CONCORDO COM**

- `bool` é tratado antes de `int`; datetime naive e números não finitos são recusados: [canonical.py:58](C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:58), [linha 83](C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:83), [linha 94](C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:94).
- O índice parcial de `tracking_hold` existe sobre `market_id`, condicionado ao vínculo não nulo: [0002:155](C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:155).
- API somente leitura e worker com privilégio na sequence estão explicitamente contemplados: [shadow.py:122](C:/dev/project-hunter/infra/migrations/ddl/shadow.py:122).

**OBSIDIAN**

- **Strategies** — registrar congelamento, bloqueio de exclusão e correção necessária do canônico.
- **Performance Overview** — fixar `tracking_state` como autoridade para contagens de acompanhamento.
- **Diálogo Claude ⇄ Astra — SHADOW** — acrescentar resolução da bicondicional e responsabilidades de integridade S0/S2.
- **Revisões Astra / S0-schema** — registrar achados, saídas reais e gates de banco ainda não verificados.
**RESUMO**

**DONE_WITH_CONCERNS — manteria a arquitetura, mas corrigiria os contratos de persistência antes de implementar.** Os principais bloqueios são: reserva de caixa com taxas, identidade dos eventos de participação, integridade das intenções de saída, consulta temporal de β e proteção contra reset por exclusão.

Considerei prevalente a decisão conjunta, como determina [M3.md:130](/C:/dev/project-hunter/docs/plans/M3.md:130). Isso importa para `shadow_bridge`: há trechos conflitantes no plano, mas o fechamento mantém entradas manuais no M3.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes, migrações nem SQL no banco. Os exemplos abaixo são contraexemplos de desenho, não resultados de testes. Consultei também a documentação oficial do PostgreSQL 16 para as regras de constraints, enums e parâmetros customizados.

**MUST-FIX**

**1. Enums: os eventos são seus; `shadow_bridge` ainda não está contratado.**

Acrescentar os três `risk_event_type` pertence à **T3.1**: ela detém `domain/enums.py`, e a T3.2 depende explicitamente desses enums. Os valores já estão normatizados em [RISK_ENGINE.md:298](/C:/dev/project-hunter/docs/RISK_ENGINE.md:298), com a divisão de responsabilidade em [M3.md:54](/C:/dev/project-hunter/docs/plans/M3.md:54). Concordo com as posições propostas e com reutilizar `exit_reason`.

Para `proposal_source`, eu **congelaria agora a interface com T3.12**, mas não aprovaria automaticamente o trio `manual|agent|shadow_bridge`. Origem explícita é requisito; esses três rótulos não são. Em particular, `shadow_bridge` se apoia na T3.14 de [M3.md:124](/C:/dev/project-hunter/docs/plans/M3.md:124), enquanto o fechamento prevalente deixa a ponte para M4 em [M3.md:150](/C:/dev/project-hunter/docs/plans/M3.md:150).

Minha escolha mínima: `manual` agora; `agent` pode entrar se congelado como interface futura, sem habilitar fluxo. Origem e ator são conceitos diferentes: `source=manual` não identifica quem pediu.

**Falha concreta a prevenir:** adicionar `paper_v1` e usá-lo no seed dentro da mesma transação da migração falha. Mantenha o seed posterior ao commit; não é necessário autocommit só para acrescentar o rótulo. Essa restrição já está em [DATABASE.md:1120](/C:/dev/project-hunter/docs/DATABASE.md:1120) e na [documentação de ALTER TYPE](https://www.postgresql.org/docs/16/sql-altertype.html).

**2. Reserva: dinheiro, com caixa separado do notional.**

**`reserved_risk` em USDT está correto.** O teto usa equity atual; o compromisso existente permanece um montante. O núcleo presente também recebe risco monetário não negativo por posição/reserva e soma esses valores em [exposure.py:72](/C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:72) e [exposure.py:167](/C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:167).

Para “lucro nunca compensa risco”, o invariante é:

```text
risco_agregado = Σ max(0, risco_planejado_da_posição_i)
                + Σ risco_das_reservas_executáveis
```

**Não** `max(0, Σ riscos assinados)`. Exemplo: riscos individuais de −80 e +100 não podem virar compromisso de 20. Não precisa de uma coluna “lucro compensável”; precisa da definição por posição, custos incluídos, e da proveniência necessária para reconstruí-la.

Falta explicitar **caixa reservado com taxas**. Eu acrescentaria `reserved_cash` ou `reserved_fee_quote`, preservando `reserved_notional` para exposição/participação. O contrato exige ambos em [M3.md:140](/C:/dev/project-hunter/docs/plans/M3.md:140).

**Cenário:** caixa 100; reserva de notional 100; taxa estimada 0,10. Todos os seus CHECKs passam, mas a compra exige 100,10. Embutir a taxa em `reserved_notional` resolveria caixa distorcendo exposição e participação.

Também fecharia:

- Montantes não negativos, notional positivo enquanto executável.
- Significado dos valores após `consumed/released/expired`: histórico original ou saldo remanescente, nunca ambos.
- `reserved_slot` representa **vaga ainda reservada**; após conversão, não pode continuar contando.
- Fill parcial de entrada e cancelamento terminal do restante precisam ser atômicos; não publicar `consumed` enquanto existir restante executável sem reserva.

**3. Linha única de risco: concordo; monotonicidade precisa sobreviver a DELETE.**

Juntar trava, contador, referência diária e pico é adequado ao contrato de serialização. Não vejo benefício concreto em quatro tabelas disputando a mesma carteira. FIFO sob essa trava atende [M3.md:148](/C:/dev/project-hunter/docs/plans/M3.md:148).

Mas há três lacunas:

- **Existência da linha:** criá-la atomicamente na abertura. `SELECT FOR UPDATE` sem linha não serializa nada.
- **Não permitir apagar/recriar:** pico 110 → DELETE → INSERT com pico 100 passa por um trigger que só compara UPDATE. O mesmo vale para `last_admission_seq`.
- **Referência diária desconhecida:** precisa ser representável sem inventar equity. Uma indisponibilidade à meia-noite não pode impedir a existência da linha usada para travar saídas.

A referência deve permanecer estável **dentro do mesmo dia**, com reconstrução documentada. Avaliar às 03:17 não transforma o equity de 03:17 em equity da meia-noite; essa proibição está em [RISK_ENGINE.md:212](/C:/dev/project-hunter/docs/RISK_ENGINE.md:212).

Sobre tzdata: **sim, o CHECK é uma armadilha possível**. Mesmo que a função esteja catalogada `IMMUTABLE`, isso não congela a base de fusos entre instalações/atualizações. Uma correção histórica pode fazer a mesma linha falhar em UPDATE ou restore. PostgreSQL pressupõe que o resultado do CHECK não muda para os mesmos valores; veja [Constraints](https://www.postgresql.org/docs/16/ddl-constraints.html).

Eu validaria a conversão na criação/virada, preservando o instante UTC resolvido e a política usada. Não recalcularia a validade de toda referência histórica contra o tzdata atual a cada UPDATE do contador.

**4. Intenção: `blocked_residual` pode ser estado; a unicidade por motivo é estreita demais.**

Manter `blocked_residual` como estado é suficiente: ele continua **não terminal**, participa do hold e pode voltar a `open` quando preço/filtros permitirem execução. Não vejo necessidade de outro eixo apenas para isso.

Já `UNIQUE(position_id, reason)` impõe “um alvo por posição”. A posição atual guarda uma lista de alvos em [execution.py:220](/C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:220).

**Contraexemplo:** posição de 10 unidades, alvo A para 4 e alvo B para 6. Ambos são `reason=target`, com preços distintos. O segundo é recusado, embora compartilhar quantidade sob lock não exija proibir dois objetivos. A §10 não estabelece alvo único; exige não vender duas vezes a mesma unidade.

Eu usaria uma **identidade estável da proteção**, como `protection_key`, incluindo o nível do alvo. Preço não deve ser identidade: mudar preço é revisão/substituição da mesma proteção.

Os CHECKs propostos são úteis, acrescentando `intended_qty > 0`, quantidades obrigatórias e coerência de `closed_at`. Também falta especificar:

- Sucessora pertence à **mesma posição/carteira/organização**.
- Proibir autorreferência e ciclos de substituição.
- Substituição e auditoria são atômicas.
- Quando uma saída liquida a posição, as intenções concorrentes são reconciliadas; não recebem fills fictícios para virar `fulfilled`.

**Cenário:** stop vende as 10 unidades; alvo continua `open` para 10 indefinidamente após restart. A §10 exige término por liquidação ou substituição explícita, em [RISK_ENGINE.md:356](/C:/dev/project-hunter/docs/RISK_ENGINE.md:356).

**5. Participação: a álgebra fecha; o protocolo de identidade ainda não.**

Com teto de 100 USDT e todos os efeitos dentro dos 60 segundos:

| Momento | Executado na janela | Reserva executável | Disponível |
|---|---:|---:|---:|
| Reserva A de 80 | 0 | 80 | 20 |
| Fill parcial de 30 | 30 | 50 | 20 |
| Cancelamento terminal dos 50 | 30 | 0 | 70 |
| Nova proposta B reserva 70 | 30 | 70 | 0 |

Portanto, **não encontrei excesso inerente nessa álgebra**, desde que o saldo seja calculado **por reserva**, com todo seu histórico. Só o executado recebe o corte móvel; uma reserva executável não desaparece por ter mais de 60 segundos. Isso corresponde a [RISK_ENGINE.md:161](/C:/dev/project-hunter/docs/RISK_ENGINE.md:161).

Mudaria a frase “retry é reserva nova por cima”:

- **Retry da mesma solicitação:** recupera proposta, decisão e reserva existentes; não insere nova reserva.
- **Nova solicitação após cancelamento terminal:** nova proposta e nova decisão, descontando execuções anteriores.
- Retentar automaticamente o restante da entrada seria parcelamento implícito, proibido em [RISK_ENGINE.md:353](/C:/dev/project-hunter/docs/RISK_ENGINE.md:353).

**Cenário:** commit da admissão ocorre, resposta se perde, cliente repete. Inserir outra reserva duplica o compromisso da mesma operação, contrariando FIFO/dedupe.

Para o log, definiria chave idempotente por **efeito lógico**, com unicidade de execução por fill e identidade da liberação. UUID novo por tentativa de INSERT não deduplica evento. `proposal_id` basta como identidade da reserva **se houver exatamente um ciclo de reserva por proposta**; caso contrário, precisa de `reservation_id`.

Ainda exigiria saldo não negativo por reserva, nunca compensando saldo negativo de uma com saldo positivo de outra. E `occurred_at` da execução precisa acompanhar o efeito durável, sem ser renovado pelo retry.

**6. FKs: preserve o CASCADE e corrija o SET NULL seletivo.**

As duas FKs propostas não criam ciclo entre proposta, ordem e fill. Mas a migração deve **substituir** as FKs simples e preservar suas ações:

- `orders → trade_proposals`: atualmente `SET NULL`, em [execution.py:128](/C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:128). Na composta, usar **`SET NULL (proposal_id)`**.
- `fills → orders`: manter `CASCADE`, atualmente em [execution.py:176](/C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:176).

**Falha concreta:** `SET NULL` sem lista tenta anular também organização e carteira, ambas obrigatórias. É exatamente o precedente de [DATABASE.md:714](/C:/dev/project-hunter/docs/DATABASE.md:714).

`positions UNIQUE(id, organization_id)` é insuficiente para a intenção, porque ela também declara carteira e mercado.

**Contraexemplo:** posição de BTC na carteira A; intenção aponta essa posição, mas declara carteira B e mercado ETH da mesma organização. Todas as FKs isoladas passam. O worker trava B e pode manter o mercado errado em coleta.

Eu provaria a identidade completa posição→intenção e intenção→ordem, incluindo carteira e mercado, com FKs compostas ou eliminando redundâncias desnecessárias. Aplicaria o mesmo raciocínio aos vínculos do log de participação.

O backfill `execution_key=id::text` é aceitável como **identidade legada derivada**, não como prova de deduplicação econômica histórica. Para novos fills, a chave deve sobreviver ao retry antes de gerar um novo UUID. Divergências preexistentes de organização/carteira devem recusar upgrade com diagnóstico; não podem ser “corrigidas” por inferência.

**7. β: concordo com global e digest; corrigiria vigência e replay.**

**(a) Global:** concordo. O β descrito deriva de mercado global, conforme [DATABASE.md:20](/C:/dev/project-hunter/docs/DATABASE.md:20). Ter `organization_id` não obrigaria tecnicamente recalcular por tenant, mas criaria cópias sem justificativa nesse contrato.

**(b) Digest:** concordo, e isso **não contradiz** minha objeção à PK. O problema era impedir duas revisões do mesmo corte; `id` próprio mais digest dos insumos resolve isso melhor que `computed_at`.

O digest deve cobrir referência, insumos efetivos e evidências de qualidade que alterem o resultado. Não basta hashear os coeficientes ou só as velas ignorando uma invalidação por gap. Retry preserva o `as_of` original; se recalcular esse campo com o relógio, a unicidade não deduplica.

**(c) Unique parcial:** é adequado para “no máximo uma revisão corrente por mercado/corte/versão”. Não bloqueia backfill legítimo se aposentadoria e inserção forem atômicas. Mas exige protocolo: não aposentar a atual antes de descobrir que o INSERT é apenas uma duplicata histórica.

A consulta proposta precisa mudar:

**Cenário temporal:** revisão A disponível às 10:00; decisão às 10:05; revisão B chega às 10:10 e marca A como superseded. Consultar depois com `t=10:05` retorna **nenhuma**: A falha em `IS NULL`, B falha em `available_at <= t`.

Para consulta histórica, a vigência precisa considerar:

```sql
available_at <= :t
AND (superseded_at IS NULL OR superseded_at > :t)
AND window_end <= :t
```

Além disso, selecionar versão compatível e definir desempate determinístico. Seu índice permite `beta_v1` e outra versão correntes no mesmo corte; `ORDER BY as_of DESC LIMIT 1` sozinho escolhe arbitrariamente.

Escolha primeiro a revisão aplicável e depois avalie `valid`/`valid_until`; não busque uma revisão antiga válida para esconder uma revisão nova inválida. A decisão deve preservar o **ID exato consumido**, como exige [M3.md:163](/C:/dev/project-hunter/docs/plans/M3.md:163).

Por fim, permitir UPDATE apenas de `superseded_at` é uma alteração explícita do “só INSERT” de [RISK_ENGINE.md:257](/C:/dev/project-hunter/docs/RISK_ENGINE.md:257). **Aceito como metadado de ciclo de vida**, com payload imutável, mas registre a exceção acordada na §18; não alegue conformidade literal sem essa ressalva. Se quiser manter literalmente só INSERT, a substituição precisa morar em registro separado.

**8. Permanência: prefiro trigger, mas o marcador não é autorização.**

Seu diagnóstico do DELETE está correto. Porém, `SET LOCAL` garante isolamento entre transações do pooler; **não autentica o operador**. PostgreSQL aceita parâmetros customizados com nomes de duas partes; veja [Customized Options](https://www.postgresql.org/docs/16/runtime-config-custom.html).

**Contraexemplo:** `hunter_app` executa o marcador, apaga a principal e abre outra. A proteção proposta autorizou exatamente o reset.

Minha recomendação:

- Trigger rejeita exclusão da principal aberta pelo papel da aplicação **mesmo com marcador**.
- Teardown excepcional exige papel operacional autorizado **e** marcador, com auditoria.
- Âncora e estado de risco também não podem ser apagados/recriados separadamente.
- Congelar os campos de identidade que liberariam o escopo, além de capital/moeda de abertura.

Isso inclui a cascata por workspace: o vínculo atual é `ON DELETE CASCADE` em [portfolios.py:87](/C:/dev/project-hunter/packages/core/hunter_core/db/models/portfolios.py:87).

**Outra falha:** mudar `is_arena=true`, apagar a linha e criar nova principal contorna um trigger que só examina DELETE. A permanência completa está em [M3.md:136](/C:/dev/project-hunter/docs/plans/M3.md:136).

Você descartou a revogação pelo motivo errado: **grants congelados não proíbem mudanças em revisão posterior**. Proíbem alterar retroativamente a `0001`. A `0005` já acrescenta privilégio por delta em [DATABASE.md:1530](/C:/dev/project-hunter/docs/DATABASE.md:1530). Um `REVOKE DELETE` na `0006` é possível, mas sozinho não resolve cascatas nem alterações de identidade. Por isso prefiro a proteção por invariantes, com autorização operacional separada.

**9. Downgrade: faltam consumo executado, evidência e identidades.**

Acrescentaria estas guardas ou uma preservação equivalente, explicitamente definida:

| Perda omitida | Cenário concreto |
|---|---|
| Novos rótulos em `risk_events` | Existe `beta_missing`; reconstruir o enum antigo falha ou exige apagar/reclassificar auditoria. Guardar todos os rótulos removidos, não apenas `paper_v1`. |
| Executado ainda nos 60 s | Não existe reserva pendente, mas houve fill há 10 s. Derrubar o log apaga consumo ainda ativo. |
| β referenciado por decisão preservada | A decisão mantém o ID, mas a revisão desaparece. Recalcular não recupera a disponibilidade histórica nem necessariamente os insumos anteriores ao backfill. |
| FX referenciado por snapshot | A curva sobrevive, mas perde a observação que explica seu valor em BRL. |
| Pico/referência diária já usados | Após downgrade/upgrade, inicialização redefine pico ou referência e altera o kill switch. |
| Chaves de execução/FIFO e vínculos históricos de saída | Reentrega perde dedupe; uma decisão perde sua ordem de admissão; tentativas deixam de explicar qual intenção cumpriram. |

A guarda da âncora provavelmente interceptará vários desses casos na principal, mas isso deve ser **provado por invariantes**, não presumido para todo dado legado ou experimental.

A exceção “β é recomputável” só vale para revisão **sem dependência preservada**. É precisamente a distinção de [DATABASE.md:1556](/C:/dev/project-hunter/docs/DATABASE.md:1556): baselines referenciadas bloqueiam downgrade; baselines órfãs podem ter perda aceita.

Também explicitaria que, depois do seed de `paper_v1`, a guarda pode impedir downgrade mesmo sem carteira aberta. Isso é consequência legítima da política proposta, não algo a resolver apagando o preset automaticamente.

**NICE-TO-HAVE**

Uma tabela de transições para reservas e intenções, indicando quais campos preservam valores originais e quais representam saldo atual, evitaria interpretações divergentes nas T3.3–T3.5.

**O QUE EU FARIA DIFERENTE**

Antes do DDL, fecharia na §18 quatro contratos curtos: identidade/idempotência dos efeitos; transições e saldos; leitura temporal de revisões; permanência e teardown. Depois escreveria os testes dos contraexemplos acima, incluindo duas sessões reais e chamadas sob os papéis efetivos.

**CONCORDO COM**

`reserved_risk` monetário; uma linha de coordenação por carteira; FIFO transacional; intenção distinta de tentativa; participação em janela móvel; β global com revisões identificadas por digest; FKs compostas; downgrade que recusa perda. Manteria intocados os arquivos de partições indicados.

**OBSIDIAN**

- **Portfolio** — registrar permanência contra exclusão, cascata, mudança de escopo e recriação do estado de risco.
- **Risk Engine** — esclarecer reservas monetárias, caixa com taxas, participação idempotente e revisão exata de β.
- **Execution Engine** — documentar identidade das proteções, substituição e reconciliação de intenções concorrentes.
- **Paper Trading** — distinguir retry técnico, nova admissão e cancelamento terminal da entrada.
- **Revisões da Astra / T3.1** — registrar estes contraexemplos e as decisões finais da §18, sem tratá-los como testes executados.
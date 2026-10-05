**RESUMO**

**REQUEST_CHANGES no desenho; concordo com a pesquisa proposta.** O problema principal está no contrato causal e contábil, antes dos limiares.

Respostas diretas:

| Pergunta | Parecer |
|---|---|
| **1. Entrada anterior à janela, fechamento dentro dela** | **Pode. Não é look-ahead**, desde que o custo completo tenha sido observado e preservado. Isso mede lucro de episódios encerrados na janela, não retorno do capital durante aqueles sete dias. O fechamento relevante para C-PnL é o **nosso**, incluindo atraso e disponibilidade do dado. |
| **2. Controle pareado** | Compara a **política completa de seleção** com outra população. Como está, não isola a contribuição do ranking C-PnL. |
| **3. Sacos e exclusões** | Há furos: perdas abertas recentes, tratamento repetido da liquidação, transferências e exclusões que só ficam conhecidas depois da entrada. |
| **4. Replay noturno** | **Aceitável como pesquisa prospectiva com execução simulada**, desde que reproduza informação disponível naquele instante. Não comprova execução operacional nem PnL de uma carteira com capital limitado. |
| **5. Tabela nova diária** | Concordo. A retenção precisa preservar estado de abertura e evidência do ranking; o orçamento apresentado cobre apenas uma parte do armazenamento. |
| **6. Pré-registro** | Os limiares podem ser congelados como escolhas. **2.000 apostas não demonstram potência para +0,05 R**, e tomar o maior de dois ICs separados não resolve dependência cruzada. |

Revisão feita no papel de `quant-engineer`, considerando o fracasso anterior com cobertura seletiva e censura da [KB-0136:25](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0136-carteiras-vencedoras-nao-sao-gatilho.md:25) e da [R57:198](C:/dev/project-hunter/.claude/state/notes-R57.md:198).

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Os números da VPS são os fornecidos por você, não uma medição repetida nesta revisão.

**TESTES**

Não executei testes de implementação: a tarefa é revisão do desenho.

Verificação somente leitura:

```text
Test-Path .claude/state/carteiras-lucro/PREREG.md
False
```

Conferi também a aritmética de armazenamento e potência ilustrativa, apresentada abaixo. Não são benchmarks nem resultados do experimento.

**MUST-FIX**

**1. Fechar a causalidade por disponibilidade, não apenas por `block_time`.**

O [desenho:109](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:109) aceita pares fechados antes de meia-noite, mas o [C-PnL:49](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:49) sai cinco slots depois da venda deles.

**Falha concreta:** eles vendem às 23:59:59; nossa saída simulada usa reservas de 00:00:01. O par entra no ranking de D carregando preço do próprio D. Outro caso: trade antigo recuperado às 03:00 entra num retrato que deveria estar disponível às 00:05.

Fixar três tempos: corte econômico, disponibilidade dos insumos e publicação do retrato. Exigir:

- Desfecho copiável completo antes do corte, incluindo o slot inteiro usado na convenção de pior preço.
- Insumos e ligações de entidades conhecidos até o prazo declarado.
- Uso do retrato apenas após `published_at`; entre 00:00 e 00:05, usar o anterior ou não abrir entradas.
- Evento recebido depois do pouso teórico não pode gerar uma compra retroativa.

A entrada anterior à janela é válida com custo conhecido. Sem esse histórico, o episódio é incompleto; não recebe custo zero nem desaparece silenciosamente.

**2. Definir como posições abertas afetam W-PnL, C-PnL e elegibilidade.**

O [desenho:45](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:45) marca posições abertas com mais de 24 horas, enquanto C-PnL é descrito como replay de pares fechados.

**Falha concreta:** uma entidade realiza pequenos ganhos, mantém perdas grandes abertas e continua com C-PnL positivo porque as perdas nunca fecham. Mesmo antes das 24 horas, pode passar pelo ranking com prejuízo econômico já conhecido. A frase “fecha o viés” ainda não está garantida.

Separaria explicitamente:

- W-PnL realizado, preservando seu significado.
- Resultado econômico ajustado pelo inventário aberto, usado na elegibilidade.
- C-PnL de episódios simulados, incluindo suas saídas obrigatórias e perdas.

Definir se a liquidação de 24 horas encerra **um episódio sintético uma única vez**, ou se é marcação diária com diferenças de valor. **Não descontar a perda inteira diariamente e depois descontá-la novamente na venda real.**

Também falta contrato para compras adicionais, vendas parciais, poeira, reentrada e transferências. **Falha:** A compra e transfere para B; B vende. Um livro apenas de swaps deixa uma perda aberta em A e uma venda sem custo em B. O próprio [event_wallets.py:25](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_wallets.py:25) distingue fluxo negociado de saldo. Transferência não resolvida precisa contaminar a qualidade do episódio, não virar lucro/perda confirmado.

**3. Separar exclusão histórica de decisão executável.**

As exclusões de MEV, robô de volume e ligações entre carteiras estão no [desenho:65](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:65).

**Falha concreta:** uma entidade seguida compra no slot S e vende em S+1. O replay descobre que foi arbitragem e apaga o par. Na operação, a intenção de copiar já poderia ter sido disparada. Excluir historicamente esse padrão do ranking é legítimo; apagar retrospectivamente a aposta prospectiva não é.

Mesma regra para “mais de 500 trades no dia”: não usar o total final de D para excluir compras da manhã de D.

A fusão precisa ser versionada por conhecimento disponível. Uma terceira coincidência observada amanhã não pode fundir carteiras no ranking de hoje. E o corte de concentração que remove apostas antigas conforme a participação final da entidade ([desenho:180](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:180)) deve ser diagnóstico separado ou virar uma regra causal de admissão. Caso contrário, atividade futura modifica quais apostas passadas compõem a estratégia.

**4. Ajustar o controle à pergunta que se pretende responder.**

O controle passa atividade, posse e exclusões, mas não exige os mesmos filtros de consistência e rentabilidade do braço seguido — [desenho:159](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:159).

**Falha concreta:** o braço ganha do controle apenas porque exclui entidades historicamente deficitárias, enquanto o controle as admite. O relatório atribui a diferença ao ranking C-PnL, embora ela venha dos filtros anteriores.

Para perguntar **“ordenar por C-PnL acrescenta informação?”**, escolher controles entre entidades que passam **todos os mesmos filtros de elegibilidade**, mas ficam abaixo do top-30. Se essa população não existir, registrar ausência de suporte comparável.

Para perguntar **“essa política inteira supera copiar uma entidade ativa?”**, o controle proposto serve, com esse nome e essa interpretação.

Em ambos, congelar sorteio, desempate, reposição, reutilização de controles e tratamento de ausência de par. Não exigir que o controle futuramente venda ou tenha trajetória completa. Preservar H1 em todas as apostas admitidas; H2 usa a população pareada, cuja cobertura deve ser publicada.

Outro mint evita compartilhar diretamente a mesma trajetória, mas não elimina diferenças de liquidez. Eu acrescentaria pareamento por liquidez anterior ao gatilho se o objetivo for comparação condicional; reconhecendo que isso também retira parte da habilidade de escolher mints líquidos.

**5. Completar o contrato de preço, estado da praça e ausência de eventos.**

A regra do pior preço no slot é defensável como convenção adversa. **Não é vazamento na decisão se for usada exclusivamente para resolver o fill posterior.** Mas falta resolver slots sem trades, slots pulados, migração e mudanças de reservas sem swap — [desenho:150](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:150).

**Falha concreta:** não há trade no slot S+5; o implementador busca o próximo trade, dois minutos depois. A entrada passa a depender de atividade futura. Outro caso: a pool perde liquidez depois do último swap, e a “liquidação” usa reservas antigas.

Exigir estado válido no pouso e política explícita para ausência de prova. Cotação da curva anterior à migração não representa venda executável na pool desconhecida; “censurada, avaliada à liquidação” precisa distinguir valor observado, cenário e desfecho indeterminado.

Reutilizar `quote_buy/quote_sell` exige validação por praça e versão. O [quote_sell:292](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:292) permite omitir o teto de SOL real; nesse caso não o aplica. O [SellEvent:83](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/sell_event.py:83) já carrega reserva virtual adicional, e [net_proceeds:94](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/sell_event.py:94) é líquido de taxas.

**Falhas concretas:** liquidar acima do saldo real; usar fórmula inadequada para um estado novo; descontar novamente taxas já contidas no resultado líquido. Fixtures reais precisam provar semântica, arredondamento e conservação de lamports.

**6. Cobertura agregada não pode legitimar episódios contaminados.**

O [desenho:100](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:100) mede slots em lacuna e audita somente seguidas; o [portão:187](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:187) aceita dias com cobertura ≥95%.

**Falha concreta:** uma lacuna curta coincide com o despejo que deveria disparar a saída. O dia passa com 99% de cobertura, mas o replay mantém a posição até uma recuperação. A revisão [T4.8e:54](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/T4.8e-decoders.md:54) já descreve essa classe de erro.

Medir cobertura por programa e por intervalo relevante do episódio, com auditoria também de candidatas, controles e carteiras fora do topo. Falhas durante posições abertas não podem simplesmente removê-las da média; precisam de tratamento pré-registrado e limite de contaminação que impeça CONFIRMA.

Além disso, documentar deduplicação entre as duas assinaturas, identidade estável do evento, atribuição ao programa e reconciliação de finalidade. `logsSubscribe` entrega logs da transação que menciona o endereço; não uma lista já normalizada de fills exclusivos daquela praça. [Documentação Solana](https://solana.com/docs/rpc/websocket/logssubscribe).

**7. Preservar inventário e prova do ranking antes da poda.**

O [desenho:121](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:121) retém fills por sete dias e guarda evidência longa apenas dos mints apostados.

**Falha concreta:** uma posição comprada oito dias antes fecha hoje. A compra e seu custo já foram podados. Outro caso: no veredito, é possível reproduzir a aposta, mas impossível verificar por que sua entidade superou as demais no ranking.

Persistir em Postgres:

- Lotes abertos, custo, quantidade e origem, sobrevivendo à retenção da fita.
- Estado necessário para retomar o processamento após reinício.
- Versões de entidades e evidência suficiente dos episódios que determinaram elegibilidade e ranking.
- Manifesto do conjunto de dados, parâmetros e código de cada execução.

Guardar só as apostas não audita seleção. E sete dias exatos exigem margem operacional para o job de ranking e preservação terminar antes da poda. Fita fora do backup precisa de consequência explícita de recuperação: **uma restauração não pode parecer continuidade integral**.

**8. Corrigir a inferência para dependência cruzada e preservar o pareamento.**

O [desenho:170](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:170) escolhe o IC mais largo entre bootstrap por dia e por entidade.

**Falha concreta:** existem choques comuns a todas as entidades no mesmo dia e habilidade persistente de cada entidade entre dias. Cada bootstrap separado deixa uma parte dessa dependência escapar; escolher o maior não garante cobertura conjunta. Essa distinção é tratada na seção V de [Cameron e Miller](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf).

Pré-especificar inferência que represente as dimensões simultaneamente e verificar seu comportamento com poucos dias. Em H2, reamostrar preservando pares e reutilizações; não tratar diferenças que compartilham controles como independentes. Reentradas no mesmo mint e entidades do braço de controle também precisam entrar no desenho de dependência.

Holm é adequado para a família declarada, mas depende de **p-valores válidos**. Não corrige subestimação do erro amostral.

**9. Materializar o pré-registro completo e a tabela de vereditos.**

O arquivo anunciado no [desenho:167](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:167) não está presente nesta cópia. O resumo não define completamente MRE, refutação, estresse, censura e encerramento.

**Falha concreta:** obter média +0,06 R, IC cruzando zero e decidir depois se isso “confirma pelo MRE”; ou encerrar quando finalmente completar 30 entidades, retirando retroativamente as que tiveram menos de dez apostas.

Congelar antes do aquecimento: aplicação do +0,05 R a H1/H2, alfa e p-valores, condições conjuntas de CONFIRMA, limite superior que permite REFUTA, limite de dado e regra exata de encerramento. Entidades com pouca atividade contam para o portão de suficiência; não devem desaparecer retrospectivamente dos resultados admitidos.

**NICE-TO-HAVE**

- **Alinhar C-PnL à política avaliada.** Hoje o ranking espelha fechamento, enquanto o braço usa venda de 50%, stop e 60 minutos — [desenho:49](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:49), [152](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:152). Um score diferente pode prever resultado legitimamente; apenas não deve ser apresentado como o lucro histórico da mesma estratégia. Eu usaria o mesmo motor.
- **Tratar cinco slots como cenário-base, não garantia conservadora.** Seu p75 sustenta a escolha; não cobre a cauda, falhas ou o novo coletor. A KB-0171 mede custos de outra população, explicitamente limitada a dez posições de spot — [KB-0171:169](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0171-custo-real-da-spot-1.md:169).
- **Ligações comportamentais como evidência, não identidade certa.** Três compras simultâneas podem representar copiadores independentes; união transitiva pode formar entidades artificiais. Publicaria tamanho dos grupos e sensibilidade usando apenas vínculos fortes.
- Corrigir o contrato de lacunas: [meme_radar.py:274](C:/dev/project-hunter/infra/migrations/ddl/meme_radar.py:274) tem `stream`, `gap_start`, `gap_end` e `detail`; não tem `source` nem colunas de slot. É extensão ou convenção nova, não reutilização literal.

**O QUE EU FARIA DIFERENTE**

Manteria **tabela nova diária**, coletor isolado e replay noturno. A coleta atual de carteiras é um laço restrito aos endereços observados, com recomputação pelo ledger — [wallets.py:1](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:1). Não a transformaria no coletor populacional.

Corrigiria a estimativa de custo:

| Sob a hipótese de 350 B/linha, incluindo índices | Resultado aritmético |
|---|---:|
| 3–6 milhões/dia | 1,05–2,10 GB/dia |
| Sete dias | 7,35–14,70 GB |
| Trinta dias | 31,5–63 GB |

Portanto, “centenas de GB por partição mensal” não decorre dessa hipótese. O padrão atual também é **30 dias**, não 90 — [settings.py:125](C:/dev/project-hunter/packages/core/hunter_core/settings.py:125). Isso não muda minha preferência por tabela separada.

O orçamento precisa acrescentar WAL, índices efetivamente medidos, `fills_kept`, estado de inventário, consultas noturnas e margem de disco. CPU deve considerar também notificações descartadas e picos. RPC público serve à sondagem; sua disponibilidade contínua não está demonstrada por 25–60 minutos, e a própria Solana declara que seus endpoints públicos não são destinados a aplicações de produção. [Documentação oficial](https://solana.com/docs/references/clusters).

Quanto aos limiares:

| Limiar | Minha leitura |
|---|---|
| Posse mediana ≥60 s | Escolha plausível; não prova que o ganho permanece depois da entrada. Manter congelada. |
| Top-30 | Política válida; não há demonstração de que 30 seja ótimo. |
| +0,05 R | Equivale a 2,5% do nocional pela régua proposta. Definir a qual contraste se aplica. |
| ≥2.000 apostas | Piso de informação, não certificado de potência. |
| ≥14 dias e ≥30 entidades | Guardas úteis; poucos dias ainda limitam inferência e diversidade de regime. |
| Holm H1/H2 | Concordo, com regras conjuntas e inferência corrigida. |

**Ilustração, não potência medida:** com desvio de 1,2 R, independência e alfa unilateral 0,025, detectar +0,05 R com 80% de poder pede aproximadamente **4.516 observações**. Com 2.000, o efeito detectável fica perto de **0,075 R**. Para H2, importa a variância das diferenças pareadas; a dependência muda essa conta.

Chamaria a onda 4 de **“replay causal em coorte futura, `research_only`”**. É suficiente para testar a hipótese sob um modelo de execução. A onda 5 continua necessária para testar se o sistema efetivamente consegue executá-la.

**CONCORDO COM**

- Ranquear copiabilidade, não reputação social nem marcação pela última cotação.
- Entrar e sair depois da entidade, incluindo impacto e custos.
- Retomar a pergunta com população mais ampla: a limitação da R57 está documentada, não resolvida por reanalisar a mesma fita.
- Congelar parâmetros, declarar tentativas anteriores e reservar dado futuro.
- Separar dinheiro realizado, inventário e incerteza.
- Manter dinheiro real fora do escopo e exigir papel operacional após eventual CONFIRMA.

**OBSIDIAN**

Nenhuma página foi alterada. Deveriam receber registro:

- **Revisões Astra — carteiras-lucro-design:** parecer e cenários de falha desta revisão.
- **EXP-M15 — carteiras vencedoras:** distinguir o rascunho antigo da nova hipótese e registrar sua linhagem.
- **KB-0136 — Carteiras vencedoras não são gatilho:** nova investigação permanece proposta; não revoga o resultado anterior.
- **KB-0181 — Quem ganha dinheiro de verdade nos memes:** separar lucro realizado, inventário e copiabilidade, se a nota anunciada for criada.
- **Fila de Hipóteses / Mapa de Estratégias:** registrar H-029 apenas após protocolo completo, sem classificá-la como evidência favorável.
## RESUMO

**Não aprovaria o veredito como está.** Concordo com não promover filtros, mas encontrei **um erro de cálculo que exige refazer A e a família**, uma interpretação indevida dos timestamps e conclusões mais fortes que a evidência.

Revisão como `quant-engineer`, em modo OPINIÃO.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Fiz inspeção estática e recálculos em memória com PowerShell (`Import-Csv`, `ConvertFrom-Json`, filtros, medianas e médias). Saída agregada:

```text
rows=520
age>300=0
subject>=120s=0
progress_delta_60s missing=71
mcap_delta_60s missing=71
p_buys missingAbs=12 nonnullPctForMissingAbs=12
p_sb missingAbs=28 nonnullPctForMissingAbs=27
abs(D)<.0376=5
```

Não executei pytest, consultas à VPS ou novos bootstraps. Os “11 testes passaram” continuam sendo resultado registrado pelo autor, não reexecutado nesta revisão.

## MUST-FIX

**1. Erro de cálculo: sujeito sem valor recebe percentil zero — pergunta 5.**

O SQL testa ausência **apenas no membro da referência**. Quando o valor do sujeito é `NULL`, as comparações não são verdadeiras e caem em `ELSE 0.0`. Isso contradiz a função Python, que devolve `None` para sujeito sem valor. Fontes: [q_pct.sql:53](C:/dev/project-hunter/.claude/state/r69/q_pct.sql:53), [cohort.py:61](C:/dev/project-hunter/.claude/state/r69/cohort.py:61).

Consequências verificadas em `pct.csv`, excluindo sujeitos sem valor e recalculando a mediana:

| Contraste | n válido | D publicado | D recalculado |
|---|---:|---:|---:|
| Delta de progresso | 449 | +0,0461 | **−0,0129** |
| Delta de mcap | 449 | +0,0625 | +0,0504 |
| Vendas/compras | 486 | +0,0719 | **+0,1056** |

Esses são **recálculos pontuais**, sem novos ICs ou p-valores.

Além disso, a versão absoluta exclui ausentes enquanto a relativa os mantém: o confronto não usa sempre a mesma amostra, contrariando o comentário do próprio script. [run_a.py:18](C:/dev/project-hunter/.claude/state/r69/run_a.py:18), [run_a.py:31](C:/dev/project-hunter/.claude/state/r69/run_a.py:31).

**Cenário de falha:** falta de histórico para calcular um delta vira “percentil baixíssimo”; o estudo atribui à posição relativa um efeito da disponibilidade de dados.

**Correção necessária:** preservar `NULL` do sujeito, alinhar amostras e refazer A, split e BH/BY. A paridade existente verifica apenas `buys`, em 20 decisões; não valida os 13 percentis. [parity.py:25](C:/dev/project-hunter/.claude/state/r69/parity.py:25).

---

**2. Os 98,7% estão aritmeticamente corretos; “nunca tiveram curva negociável” não está demonstrado — pergunta 1.**

`3973 / 4024 = 98,7326%`. Porém, **não encontrei atribuição direta `migrated_at = created_at` nos caminhos examinados**. Encontrei outra explicação possível:

- Criação recebe `created_at = utcnow()` no parser.
- Migração recebe `migrated_at = utcnow()` no parser.
- Portanto, a diferença mede distância entre processamentos das mensagens, não necessariamente duração on-chain. [normalize.py:137](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:137), [normalize.py:178](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:178).

**Mensagens atrasadas e depois processadas próximas podem produzir duração artificialmente curta.** Isso é um cenário possível, não uma ocorrência comprovada nesses 3.973 casos.

Há também um erro na exclusão da hipótese “descoberta pela graduação”: **criação e migração usam igualmente `source = pumpportal_ws`**. Logo, `first_seen_source` sozinho não distingue os dois eventos. Uma migração pode criar o cadastro sem `created_at`, preenchido posteriormente pelo upsert. [models.py:113](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/models.py:113), [models.py:138](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/models.py:138), [discovery.py:100](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/discovery.py:100), [repo_token_sql.py:83](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:83).

**Falseamento barato, nesta ordem:**

1. Separar `ttg < 0`, `ttg = 0` e `0 < ttg < 5`; não juntar tudo sob `< 5`.
2. Cruzar `first_seen_at`, `created_at`, `migrated_at`, `pool_created_at` e origem. Coincidências ajudam a selecionar casos; não provam a ordem dos eventos.
3. Escolher amostra aleatória pequena dos “instantâneos” e conferir transações de criação e migração: slots, horários e instruções. Uma duração on-chain longa já refuta a explicação universal; a amostra estima sua frequência.
4. Recalcular graduações em horizonte fixo por moeda, explicitando o horizonte e a definição de “rastreada”.

**Cenário de falha:** excluir graduações legítimas por timestamps comprimidos faz parecer que a capacidade nunca perdeu oportunidades.

Mesmo confirmando graduações rápidas, **menor taxa média nas não rastreadas não prova que o teto não perdeu moedas boas**, nem que graduação equivale a retorno negociável. Eu retiraria “registrar e não voltar”.

---

**3. “Respondida, não adiada, porque há mecanismo” é forte demais — pergunta 3.**

A formulação honesta seria:

> “Na análise retrospectiva apresentada, nenhum dos 17 contrastes passou BH/BY. Há sinais de redundância e restrição de faixa na população selecionada, que reduzem a prioridade operacional dessa hipótese. Isso não demonstra ausência de informação incremental. Os resultados numéricos precisam ser revalidados após corrigir os ausentes.”

Correlação alta, inatividade e percentis extremos oferecem **uma explicação plausível**, não identificam causalmente a razão da ausência de significância.

O teste incremental não foi feito. Nem a aproximação prometida na Emenda 1 — separar **dentro dos tercis do absoluto** — aparece implementada: `D_t3` compara extremos do **próprio percentil**. [desenho.md:82](C:/dev/project-hunter/.claude/state/r69/desenho.md:82), [run_a.py:39](C:/dev/project-hunter/.claude/state/r69/run_a.py:39).

**Cenário de falha:** uma informação útil apenas condicionada ao absoluto é abandonada porque sua associação marginal é fraca.

Também não trataria “todas têm menos de 300 s” como propriedade garantida: o coletor permite retenção maior para moedas fixadas. A universalidade exige medição própria, não decorre do código. [fast_lane.py:116](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/fast_lane.py:116).

---

**4. Concordo em não promover o split; discordo de declará-lo “pico” demonstrado — pergunta 4.**

Progresso, fluxo e volume têm **sinal negativo tanto no ajuste quanto no teste**. Quem inverte sinal é o composto citado no relatório, não esses três contrastes. [family.txt:26](C:/dev/project-hunter/.claude/state/r69/family.txt:26), [family.txt:34](C:/dev/project-hunter/.claude/state/r69/family.txt:34).

Um composto nulo não invalida automaticamente componentes: pode diluir sinais, combinar variáveis heterogêneas ou usar outro corte. A fórmula e a execução desse composto não aparecem nos scripts apresentados; seu `p=0,928` não ficou reproduzível nesta revisão.

Há motivos suficientes para **não promover**: seleção do melhor corte no ajuste, múltiplas comparações, teste pequeno e período já examinado. A seleção do corte está explícita em [run_family.py:31](C:/dev/project-hunter/.claude/state/r69/run_family.py:31).

**Cenário de falha:** usar o composto para descartar os componentes apaga uma possível associação negativa antes de uma avaliação adequada.

Eu escreveria: **“sinal exploratório de pior retorno nos extremos, sem confirmação independente”**.

---

**5. O argumento econômico do teste B mistura pesos e custos — pergunta 5.**

`+0,0110` é média de retornos **com peso igual por balde**, não retorno agregado por SOL investido. O código faz exatamente isso. [run_b.py:28](C:/dev/project-hunter/.claude/state/r69/run_b.py:28), [run_b.py:54](C:/dev/project-hunter/.claude/state/r69/run_b.py:54).

Recalculando por entrada, obtive:

```text
births_min: quente=+0,007252; frio=-0,051830
```

Mais importante: o papel **já incorpora taxas** na compra e na venda. Não se pode descontar ou exigir novamente os 4,09% integrais sem reconciliar o custo simulado com o real. [paper_fill.py:171](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:171), [paper_engine.py:219](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:219).

**Cenário de falha:** contar taxas duas vezes produz um falso veredito econômico negativo. A conclusão defensável continua sendo “benefício não demonstrado”, sem afirmar “efeito líquido nulo”.

---

**6. Medir recusadas é a próxima direção certa; o pré-registro precisa mudar antes — pergunta 6.**

O EXP-M23 associa “não separa em 150 mints” à candidatura para remoção e prevê que resultados indistinguíveis autorizariam remover critérios. Isso repete a confusão entre ausência de significância e equivalência. [EXP-M23:33](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:33), [EXP-M23:54](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:54).

**Cenário de falha:** um filtro protege contra perdas raras; a amostra não observa essas perdas, produz p alto e o filtro é removido.

Eu manteria a medição, com:

- Mesmo simulador, custos, latência e acompanhamento para admitidas e recusadas.
- Primeira oportunidade elegível por mint, registrando **todos** os motivos de recusa.
- Probabilidade de inclusão conhecida; ponderação se motivos raros forem sobreamostrados.
- Censura e impossibilidade de execução como resultados explícitos.
- Para avaliar retirada de um critério, foco em quem **passaria todo o restante**.
- Margem de não inferioridade e limites para perdas graves; p alto não autoriza remoção.

Antes de construir o braço, a tarefa de maior retorno imediato é corrigir os percentis e auditar uma pequena amostra dos timestamps. Depois disso, medir recusadas parece mais informativo que procurar outro limiar na mesma população admitida.

## NICE-TO-HAVE

Correções adicionais de leitura:

| Afirmação | Correção |
|---|---|
| “0,0059 é o limiar BH mais permissivo” | É o **mais restritivo**, do primeiro posto. O resultado zero rejeições está correto para os p-valores publicados; precisa ser refeito após a correção. [family.txt:2](C:/dev/project-hunter/.claude/state/r69/family.txt:2) |
| Controle maior em módulo que 8/13 | Pelos resultados armazenados, são **5/13**. [a.txt:7](C:/dev/project-hunter/.claude/state/r69/a.txt:7) |
| Idade varia de +0,054 a +0,069 nos sete cortes | Em q=0,30 dá **+0,001**. [family.txt:41](C:/dev/project-hunter/.claude/state/r69/family.txt:41) |
| Idade é a única absoluta com p<0,05 | Fluxo também: **p=0,049**. [a.txt:16](C:/dev/project-hunter/.claude/state/r69/a.txt:16) |
| Cobertura de 95,7% no resumo | `228457/242167 = 94,3386%`. [notes-R69:19](C:/dev/project-hunter/.claude/state/notes-R69.md:19) |

Harmonizaria ainda a janela do sujeito: SQL usa 180 s; Python, 120 s. **Nenhuma das 520 linhas exportadas ultrapassou 120 s**, portanto não encontrei impacto nessa amostra. [q_pct.sql:27](C:/dev/project-hunter/.claude/state/r69/q_pct.sql:27).

## O QUE EU FARIA DIFERENTE

**Sobre a Emenda 2 — pergunta 2:** considero uma adaptação metodologicamente defensável **se realmente decidida sem consultar desfechos**. Escolher a mediana de X não é escolher o corte que maximiza a associação com Y.

Mas ela muda o contraste: “acima da metade da coorte” passa a “acima da metade das entradas selecionadas”. Eu chamaria **protocolo retrospectivo emendado, com adaptação cega ao desfecho**, preservando a versão original e o registro temporal. Não chamaria de pré-registro intacto nem de confirmação prospectiva.

Minha sequência seria: corrigir ausentes → ampliar paridade → recalcular família → auditar timestamps → publicar conclusão limitada → congelar o estudo das recusadas.

## CONCORDO COM

Não ligar filtros com esses resultados; separar papel de execução real; usar decisão em vez de fill; excluir o sujeito da referência; reamostrar por blocos; reconhecer que o split não é holdout intacto; e priorizar a observação das recusadas.

**Despriorizar operacionalmente a hipótese é razoável. Declarar sua refutação definitiva, ainda não.**

## OBSIDIAN

- **KB-0151 — A coorte não respira** — registrar erro dos ausentes e substituir refutação/mecanismo provado por conclusão limitada.
- **EXP-M23 — Desfecho das recusadas** — revisar não inferioridade, amostragem, censura e critérios de retirada.
- **KB-0149 — O que a mesa real ensinou** — distinguir ausência de significância, equivalência e ausência de valor incremental.
- **Meme (Mercado)** — documentar timestamps de processamento e a ambiguidade de `first_seen_source`.
- **Revisões Astra — R69, veredito** — registrar recálculos, falhas concretas e validações pendentes.
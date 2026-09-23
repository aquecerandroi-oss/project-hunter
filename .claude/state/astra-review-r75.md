**RESUMO**

Concordo: **NÃO CONFIRMA — limite de dado**. A cláusula congelada explicita “poucas demais para julgar”; não autoriza declarar REFUTA. O patamar permanece **não avaliável**, não reprovado ([pré-registro:159](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:159>)).

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`.

**TESTES**

Não executei pytest nem regenerei o relatório. Conferência somente leitura do CSV: `rows=1312; missing=0` nos campos externos de fluxo, progresso, tamanho e PnL.

**MUST-FIX**

- **Censura antes da deduplicação:** [run.py:212](/C:/dev/project-hunter/.claude/state/r75/run.py:212) elimina ausentes antes de escolher uma por mint. Cenário: real sem progresso + papel completo do mesmo mint → o papel substitui a real, contrariando a precedência declarada. Escolher a decisão primeiro, depois censurar e contabilizar; incluir também fechamentos ausentes, hoje excluídos no [SQL:20](/C:/dev/project-hunter/.claude/state/r75/q_pop.sql:20). **Não há impacto demonstrado nas 587 atuais.**
- **IC enganoso com um único caso:** o relatório publica IC positivo e `P(D≤0)=0` apesar de 586/1 ([report.md:47](/C:/dev/project-hunter/.claude/state/r75/report.md:47)). Nas réplicas utilizáveis, o retorno do SHORT fica fixo; as réplicas sem esse lado são descartadas ([resampling.py:73](/C:/dev/project-hunter/infra/research/resampling.py:73)). Cenário: esse quadro ser citado como evidência estatística favorável. Suprimir a inferência nesse recorte ou marcá-la explicitamente como não interpretável.

**NICE-TO-HAVE**

- `hold_s = exit_at − entry_at` está correto para duração registrada ([load.py:92](/C:/dev/project-hunter/.claude/state/r75/load.py:92)). A resolução de segundo exige sensibilidade perto de 3 s; não confundir duração até saída com tempo até disparar o trailing. No CSV conferido, nenhuma posição paper tinha duração abaixo de 4 s.
- Escapar os `_` do `LIKE`: são curingas SQL. O filtro Python exige o prefixo literal, protegendo a população principal ([q_pop.sql:28](/C:/dev/project-hunter/.claude/state/r75/q_pop.sql:28), [load.py:132](/C:/dev/project-hunter/.claude/state/r75/load.py:132)).
- Registrar os degraus como complemento metodológico: **0,1 / 1 SOL / 5 pp não estão especificados no bloco original** ([pré-registro:159](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:159>)).

**O QUE EU FARIA DIFERENTE**

A ressalva principal seria **a seleção pela própria porta**: 502/587 têm teto 0,6; acima disso não entram, embora a igualdade seja admitida. Portanto, 1/587 não estima a frequência natural de equilíbrio ([report.md:10](/C:/dev/project-hunter/.claude/state/r75/report.md:10), [rules_criteria.py:260](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_criteria.py:260)).

Numa nova rodada, pré-registraria uma coorte prospectiva independente do SHORT, separando série, teto da porta e política de saída.

**CONCORDO COM**

- `buys=0`: indefinido para 0/0 e infinito com vendas positivas é convenção explícita e testada; `ret=pnl/size` corresponde ao desfecho proposto ([load.py:62](/C:/dev/project-hunter/.claude/state/r75/load.py:62), [load.py:91](/C:/dev/project-hunter/.claude/state/r75/load.py:91)).
- O join por `b.rule_set_id` não apresenta erro demonstrado: o produtor copia o identificador da proposta ([lab_repo_bets.py:190](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:190)).
- **Não identifiquei look-ahead nessa leitura de `reasons`.** Atraso/incompletude da fita prejudica a medida; não a torna futura. O produtor da fita filtra `received_at <= end_time` ([features_tape.py:186](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/features_tape.py:186)). Ressalva: `reasons` nasce na proposta; para operador, `decided_at` vem depois ([proposals.py:321](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:321)).
- O ganho contrafactual de **+0,0134 SOL** é uma remoção retrospectiva do próprio caso gerador; não valida a regra ([report.md:152](/C:/dev/project-hunter/.claude/state/r75/report.md:152)).

**OBSIDIAN**

- **Fila de Hipoteses — H-013:** acrescentar avaliação datada “NÃO CONFIRMA — limite de dado”, preservando o pré-registro.
- **Revisoes-Astra — R75/H-013:** registrar seleção pela porta, censura antes da deduplicação e limitação do IC com um caso.
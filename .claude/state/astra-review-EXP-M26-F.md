**MUST-FIX**

1. **Concordo: F não está aprovado por instrumento; corrigir e repetir antes de J/S.** O desenho exige união de desconhecidas e falhas instrumentais ≤15% e manda repetir F quando o instrumento falha. P verifica o percurso posterior ao seed; não adia um bloqueio já conhecido. [Desenho:530](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:530)

   Conferi os artefatos: **2/12 + 24/30 = 26/42 execuções acima de 8 s**, entre 6,244 e 13,715 s. O worker limita a consulta a 8 s e devolve `{}` quando ela falha; a camada de propostas transforma ausência do mint em `pedigree_unknown`. **Cenário:** uma primeira oportunidade passa C, mas perde a proposta porque a consulta coletiva expirou; a oportunidade seguinte não pode substituí-la. [Consulta:268](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:268), [recusa:244](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:244), [primeira oportunidade:331](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:331)

   **Ressalva quantitativa:** 26/42 mede execuções lentas, não a fração de primeiras oportunidades afetadas. Sustenta bloquear o aceite, mas ainda não demonstra numericamente `I > 5%` ou união `>15%` na população do F. É preciso cruzar falhas com oportunidades. Tampouco se pode manter como E uma exclusão que só ficou conhecida na consulta offline bem-sucedida: no timeout real, esse pedigree não foi lido.

2. **Recalcular conclusão/migração no relógio da avaliação.** O SQL reconstrói o estado conhecido em `computed_at`; o worker lê o estado corrente quando avalia o minuto, cujo fechamento precisa estar pelo menos um minuto atrás. São instantes diferentes. [SQL:23](C:/dev/project-hunter/.claude/state/m26/f/f1_superset.sql:23), [relógio:217](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab.py:217), [estado lido:75](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo.py:75)

   **Cenário:** feature calculada em T+3 s; conclusão conhecida em T+30 s; avaliação em T+60 s. O replay aceita a moeda; o worker recusa `curve_complete`. Isso pode alterar oportunidades, primeira passagem e classes — portanto, **os números de mercado ainda são provisórios**.

   `max(T+60 s, computed_at)` garante que a feature usada já existia, mas não reproduz o tique real, atrasos ou backlog. Use o tique documentado quando recuperável; caso contrário, declare o modelo temporal e meça sensibilidade ao atraso observado. Janela, dias e blocos também devem usar esse relógio: atualmente a seleção e os blocos usam `end_time`. [Replay:104](C:/dev/project-hunter/.claude/state/m26/f/f_funil.py:104), [proxy:160](C:/dev/project-hunter/.claude/state/m26/f/f_funil.py:160), [blocos:242](C:/dev/project-hunter/.claude/state/m26/f/f_funil.py:242)

3. **Demonstrar disponibilidade histórica de Mayhem e das identidades do pedigree antes de chamar a reprodução de fiel.** Ler o estado corrente agora não equivale a ler o estado corrente naquele tique. As contagens limitam o nascimento das moedas anteriores, mas não quando elas e suas identidades ficaram conhecidas. [Mayhem:12](C:/dev/project-hunter/.claude/state/m26/f/f1_superset.sql:12), [pedigree:15](C:/dev/project-hunter/.claude/state/m26/f/f2_modelo.sql:15)

   **Cenários:** Mayhem desconhecido na avaliação recebe `false` depois; ou uma moeda antiga é descoberta posteriormente e faz a contagem cruzar o limiar de `creator_serial`/`symbol_clone`. O replay muda a primeira oportunidade ou E usando informação indisponível naquele momento.

   Na conferência agregada do CSV, as 10.028 linhas têm `mayhem_enabled=false`, sem estado de agente. Isso afasta a hipótese de transição de estado **entre essas linhas**, mas não prova quando o `false` foi aprendido. `mayhem_enabled`, criador e símbolo aceitam preenchimento posterior quando eram nulos. Não medi quantas oportunidades isso altera. [Preenchimento:83](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:83)

**NICE-TO-HAVE**

- **Conserto recomendado:** consulta de duas contagens para a via **1m**, quando nenhum conjunto daquele relógio exigir `pedigree_repeat_dumper`; manter o caminho completo de 15 s. C/L/H congelam esse parâmetro em `false`, e as duas contagens já medidas custaram **27,824–68,795 ms**. Preservar parâmetros, critérios e timeout; campos diagnósticos não lidos devem ficar explicitamente ausentes, nunca zerados. [Braços:56](C:/dev/project-hunter/infra/migrations/ddl/meme_mature_chart_arms.py:56), [medições:3](C:/dev/project-hunter/.claude/state/m26/f/f3_duas_contagens.out:3)

- **Não escolheria primeiro filtrar mints pela porta pura.** Hoje pedigree e recusas da porta são contados conjuntamente, inclusive quando a porta falha. Filtrar antes pode preservar propostas, mas modifica a trilha de recusas e exige tratamento explícito para “não solicitado”. O caminho compartilhado também atende outras pistas. [Contrato:210](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:210), [chamador:183](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_e2b.py:183)

- **`snapshot_ok` reproduz a condição de presença do snapshot, não a cotação inteira.** Está alinhado ao carregador para detectar `no_snapshot_for_quote`; não prova que construir as reservas e executar `quote_for` termina sem erro. No próximo F, executar a cotação pura com o snapshot completo reforça o aceite, sem ler fill ou desfecho. Não encontrei nos artefatos prova de erro de cotação efetivamente ocorrido. [Carregador:157](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo.py:157), [cotação:169](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:169)

**CONCORDO COM**

- **E=40% está interpretado corretamente como união:** 456/1.140. As contagens marginais 380 e 164 implicam **88 oportunidades com ambas**, 292 apenas `symbol_clone` e 76 apenas `creator_serial`. Não são 544 exclusões distintas nem evidência de que 40% sejam golpes. Permanecem condicionadas à disponibilidade histórica discutida acima. [Saída:8](C:/dev/project-hunter/.claude/state/m26/f/f_saida.txt:8)

- Usar parâmetros congelados, escolher a primeira passagem antes de olhar a linha, reutilizar `coverage_of`/`classe_linha` e separar E de instrumento está correto. O replay sem timeout serve para descrever o mercado sob leitura bem-sucedida; **I offline=0 não mede disponibilidade operacional**. [Implementação:88](C:/dev/project-hunter/.claude/state/m26/f/f_funil.py:88), [classificação:155](C:/dev/project-hunter/.claude/state/m26/f/f_funil.py:155)

- **Depois do conserto, repetiria F com:**
  1. Relógio corrigido e auditoria das informações aprendidas posteriormente, publicando mudanças nas primeiras oportunidades e nos números.
  2. Pelo menos 24 h representativas de leitura pelo caminho corrigido, sob carga concorrente, com timeout real; contabilização por oportunidade da união U/I, sem dupla contagem nem E recuperado retrospectivamente.
  3. Contagens e classes diárias, motivos, cobertura e pisos congelados; testes de equivalência das decisões e de preservação da via de 15 s.
  4. Duração do ciclo completo do Lab e guardas das outras pistas — acelerar uma consulta não comprova sozinho ausência de interferência. [Guardas:631](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:631)

Revisei código e saídas existentes e recontei as cronometragens. Não executei novamente o funil, consultas na VPS ou testes. Nenhum arquivo foi modificado.

**OBSIDIAN**

- **EXP-M26 — gráfico em moedas maduras:** acrescentar avaliação datada com F bloqueado por instrumento, números offline provisórios e critérios da repetição.
- **Revisões-Astra — EXP-M26/F:** registrar os três achados, a correção recomendada e a distinção entre taxa de consultas lentas e taxa de oportunidades perdidas.
- **Fila de Hipóteses / Mapa de Estratégias — H-022:** atualizar o próximo passo para corrigir instrumento e repetir F, mantendo seed e inferência pendentes.
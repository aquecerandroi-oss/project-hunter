**RESUMO**

Concordo com o núcleo do desenho e com a ordem dos rótulos, com uma correção necessária: **a fórmula contrafactual não é um limite superior demonstrado**. A parada cega evita escolher o momento pelo resultado, mas não elimina possível seleção por resolução.

Com os fatos fornecidos, **147 pares continuam sendo LIMITE DE DADO**. Não consultei desfechos da R82.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Revisão estática do SQL, classificadores, estatística e testes existentes. Não executei testes, extrações nem o poll; não afirmo aprovação da suíte.

**MUST-FIX**

**(5) Trocar “limite superior” por “sensibilidade contrafactual com saída fixada”.**

A expressão

\[
r_a'=(1+r_c)\frac{p_c}{p_{\mathrm{gat}}}-1
\]

é uma identidade num modelo proporcional simplificado: mudar o preço de entrada aumenta a quantidade adquirida, mantendo o valor líquido de saída por token. **Não demonstra que o retorno da política executável ficará abaixo dela.** A proposta está em [notes-R82.md:72](C:/dev/project-hunter/.claude/state/notes-R82.md:72), implementada em [h017_stats.py:72](C:/dev/project-hunter/.claude/state/r82/h017_stats.py:72).

**Cenário de falha:** uma entrada anterior e mais barata pode atingir o alvo antes de uma queda que posteriormente prejudica o controle. O retorno dessa política pode superar a fórmula baseada na saída do controle. Também pode ocorrer o inverso: ela sair por trailing antes de uma recuperação. Portanto, fixar a saída não estabelece uma ordenação entre retornos.

Além disso, o motor inclui impacto, taxas e custo fixo; a venda depende da quantidade e das reservas disponíveis. Isso impede tratar a proporcionalidade como reprodução exata do motor ([paper_fill.py:171](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:171); [paper_engine.py:215](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:215)).

Manteria o cálculo como **descritivo, sem peso no rótulo**, explicitando quais preços entram: marginal ou médio executável. Comparar preço médio com custo contra preço marginal do gatilho mistura melhora temporal com impacto/custo. Não chamaria o resultado de “ganho recuperável” nem de teto.

**NICE-TO-HAVE**

- **(6) Guardas na extração final:** verificar novamente uma decisão por mint e ausência de rearmações; a contagem inicial não garante isso no poll seguinte. O SQL agrega desfechos de toda a trilha posterior a `t0`, sem delimitar a próxima armação. Um reinício seguido de rearme poderia atribuir à primeira armação um desfecho posterior. Como os fatos cegos atuais dizem zero rearmações, não considero demonstrada uma contaminação desta coorte ([q_h017.sql:21](C:/dev/project-hunter/.claude/state/r82/q_h017.sql:21)).
- Separar `foto_diferente` de `foto_desconhecida`. Hoje toda entrada que falha em `same_snapshot` vira `foto_posterior`, inclusive ausência de metadados ou divergência de reservas no mesmo instante ([h017.py:90](C:/dev/project-hunter/.claude/state/r82/h017.py:90)).
- Publicar o número de blocos de 6 h efetivamente disponíveis. Poucos blocos tornam essa sensibilidade pouco precisa; não acrescentaria um novo portão ao protocolo congelado.

**O QUE EU FARIA DIFERENTE**

Apresentaria o resultado como **“veredito da H-017 no papel, com controle EXP-M25, entre pares avaliáveis”**. A troca do controle foi declarada e autorizada no protocolo; ela não torna esta população equivalente às decisões aceitas pela mesa real ([EXP-M25:30](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M25-controle-do-recuo.md:30)).

**CONCORDO COM**

**(1) Rótulo: sim, como operacionalização explícita da cláusula ambígua.**

Manteria exatamente:

- `n < 150`: LIMITE DE DADO;
- limite superior de D `< +1 pp`: REFUTA (a);
- limite superior do braço `< 0`: REFUTA (b);
- D `≥ +2 pp`, limite inferior de D `> 0` e do braço `> 0`: CONFIRMA;
- demais casos: NÃO CONFIRMA.

A letra da H-017 diz “não bate nada”, mas não define o teste dessa expressão. **Não demonstrar superioridade não demonstra inferioridade.** A interpretação proposta respeita a distinção normativa entre imprecisão e refutação ([Fila de Hipoteses:207](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:207>); [RESEARCH.md:65](C:/dev/project-hunter/docs/RESEARCH.md:65)).

A errata do R76 tratava outra cláusula específica; aqui vocês estão **aplicando seu princípio**, não descobrindo uma definição que já estivesse literalmente na H-017. Deixaria essa operacionalização expressa na avaliação, preservando o texto original ([notes-R76.md:123](C:/dev/project-hunter/.claude/state/notes-R76.md:123)). Não acrescentaria agora p significativo ou planalto como novos critérios desta hipótese.

**(2) Parada e 15 minutos: aceitáveis, sem garantia automática de ausência de viés.**

Parar na primeira extração elegível, contando pares sem olhar retornos, evita parada por significância. Devem entrar **todos os pares elegíveis daquela extração**, mesmo se forem mais de 150; não escolher exatamente 150 depois ([notes-R82.md:37](C:/dev/project-hunter/.claude/state/notes-R82.md:37)).

O corte por idade é cego ao retorno e reduz operações em voo. Contudo, exigir resolução pode selecionar resultados: **se operações problemáticas ou perdedoras permanecerem abertas/indeterminadas por mais tempo, ficam sub-representadas**, mesmo após 15 minutos. Isso é seleção por disponibilidade, não look-ahead na decisão.

Manteria o protocolo e publicaria os excluídos por motivo e idade, limitando a conclusão aos pares avaliáveis. Os fatos cegos atuais não demonstram esse viés, mas também não provam sua ausência.

**(3) Bootstrap: correto. Permutação: correta algebricamente, com ressalva inferencial.**

Com exatamente uma linha de cada braço por mint, reamostrar clusters empilhados equivale a reamostrar diferenças emparelhadas. Ambos os denominadores permanecem iguais em cada réplica. Braço contra zeros também está correto ([h017_stats.py:12](C:/dev/project-hunter/.claude/state/r82/h017_stats.py:12); [resampling.py:69](C:/dev/project-hunter/infra/research/resampling.py:69)).

Permutar os dois rótulos dentro de cada mint equivale à troca de sinal; a implementação calcula p bilateral ([resampling.py:164](C:/dev/project-hunter/infra/research/resampling.py:164)). Porém, sua calibração exige permutabilidade sob o nulo — ou simetria apropriada das diferenças —, não apenas média zero. As duas políticas não foram aleatorizadas. Portanto, concordo em mantê-lo **descritivo**, declarando essa hipótese, conforme a [documentação do SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).

**(4) Mesma foto: sim, é uma verificação melhor, mas incremental.**

`observed_at` mais reservas verifica também o conteúdo da foto. Entretanto, o motor já define `entry_at = snapshot.observed_at`; o timestamp novo sozinho não melhora o critério anterior ([paper_fill.py:202](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:202)).

Não deduziria `D = 0` apenas dessa classificação: verificaria igualdade dos fills e retornos. Mesma foto identifica a limitação de resolução temporal; não substitui essa conferência.

**OBSIDIAN**

- **Fila de Hipoteses — H-017:** acrescentar a operacionalização de “não bate nada” e a referência ao controle EXP-M25, preservando o registro original.
- **EXP-M25-controle-do-recuo:** registrar as limitações da parada por resolução, a hipótese do p descritivo e a sensibilidade com saída fixada.
- **EXP-M24-entrada-no-recuo:** vincular esta revisão ao protocolo e distinguir veredito do papel de fidelidade à execução real.
- **Revisoes-Astra — R82, desenho cego da H-017:** registrar este parecer antes de qualquer leitura dos desfechos.
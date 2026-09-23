**RESUMO**

**Eu revisaria o desenho antes de executar o teste principal.** A hipótese é válida, mas hoje o protocolo pode confundir posição relativa com qualidade da coleta, atividade da própria mesa e política de saída. O teste B também permite antecipação se o estado do fim do balde explicar entradas anteriores desse mesmo balde.

Revisão como `quant-engineer`, em modo OPINIÃO. As recomendações abaixo são propostas para congelamento, não resultados medidos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei o R69, consultas ao banco ou testes automatizados. Fiz inspeção estática do desenho, dos registros R65–R67 e dos caminhos de coleta, seleção e persistência.

**MUST-FIX**

**1) Coorte: `as_of <= t AND computed_at <= t` é necessário, mas não suficiente.**

Eu acrescentaria estes pontos ao contrato:

- **Definir `t` como o instante efetivo da decisão**, não o horário do fill nem simplesmente `features_end_time`. Usar o fill permitiria incorporar informação que chegou enquanto a ordem estava em trânsito.

- **`computed_at` não comprova disponibilidade.** A coluna usa `DEFAULT now()` ([DDL:134](C:/dev/project-hunter/infra/migrations/ddl/meme_gate_v2.py:134)); a escrita acontece dentro de uma transação ([fast_lane.py:206](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/fast_lane.py:206)). No PostgreSQL, `now()` marca o início da transação, não o commit. **Cenário:** transação começa às 12:00:00, decisão ocorre às 12:00:01, commit acontece às 12:00:02; a reconstrução aceita uma linha ainda invisível na decisão. Exigiria evidência de disponibilidade ou declararia essa limitação, acompanhada de sensibilidade com atraso conservador. Um atraso arbitrário reduz risco, mas não prova ausência de vazamento. [Documentação PostgreSQL](https://www.postgresql.org/docs/17/functions-datetime.html).

- **Retroatividade:** o escritor normal usa `ON CONFLICT ... DO NOTHING`, o que protege contra sobrescrita nesse caminho ([repo_fast.py:40](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_fast.py:40)). Ainda é preciso verificar versões históricas, reparações e importações. Fixar `features_version` e desempate determinístico; filtrar elegibilidade temporal **antes** de escolher a última linha.

- **Exigir `tape_as_of <= as_of <= t`.** Encontrei uma abertura concreta: `activity_for` exige recebimento anterior e idade menor que o teto, mas não exige idade não negativa. Um `end_time` futuro passa porque a diferença é negativa ([features_tape.py:120](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/features_tape.py:120)). Isso não prova que ocorreu antecipação nos dados — pode ser relógio do provedor adiantado —, mas exige auditoria e tratamento explícito. Para fotos e demais insumos, verificar também os horários de observação e recebimento.

- **Não usar a tabela atual de tokens como história do conhecimento.** `created_at` e `migrated_at` podem ser preenchidos posteriormente quando estavam nulos ([repo_token_sql.py:13](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:13), [linha 83](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:83)). `first_seen_at <= t` não prova que a graduação já era conhecida em `t`. `births_min` e `grads_h` precisam de disponibilidade histórica do evento; sem isso, ficam fora do teste preditivo.

**O próprio sujeito:** incluí-lo no ranking não é antecipação. Contudo, ele influencia mecanicamente seu percentil e o estado agregado, sobretudo com poucos pares. Eu congelaria o percentil **excluindo o sujeito da referência**:

\[
p_v(m,t)=\frac{\#(v_c<v_m)+0{,}5\,\#(v_c=v_m)}{N_{v,-m}}.
\]

Sujeito ausente ou valor nulo → indisponível; nunca buscar sua primeira linha futura. Selecionar a última linha, depois verificar o valor: não procurar retrospectivamente “a última linha não nula”.

Também corrigiria a afirmação de “mesmo tique”: compartilhar a tabela não sincroniza as observações. A janela aceita pares com até quase 120 s de diferença ([desenho:17](C:/dev/project-hunter/.claude/state/r69/desenho.md:17)). Reportar idade da linha e dos insumos por variável.

**Cenário de falha:** uma moeda aparece no radar depois de explodir; o estudo usa esse cadastro posterior para inseri-la em coortes anteriores. Isso é vazamento. Entrar no radar **quando já estava subindo, antes de `t`**, é seleção contemporânea, não conhecimento do futuro.

---

**2) Composição: controlar o instrumento sem retirar o contexto que a hipótese quer medir.**

A hipótese relevante deve ser:

> O percentil acrescenta informação sobre o retorno além do valor absoluto e das condições observáveis de coleta?

“Percentil significativo e absoluto não significativo” **não demonstra essa diferença**.

Eu compararia, sobre exatamente as mesmas observações:

- **Modelo-base:** valor absoluto, com flexibilidade predefinida, mais controles.
- **Modelo ampliado:** o mesmo modelo mais o percentil contemporâneo.
- **Teste principal:** contribuição incremental do percentil; comparação preditiva temporal como avaliação complementar.

Controles predefinidos: `log(N_v)`, fração de valores ausentes, idade dos insumos, fonte da fita, idade do sujeito, composição etária da coorte e versão operacional do coletor. Para hora do dia, uma representação cíclica parcimoniosa; evitar cruzar 24 horas × tamanhos × idades em células quase vazias.

**Não colocaria todas as medidas de “quente/fria” como controles obrigatórios em A.** Isso pode retirar exatamente a informação contextual que o percentil carrega. Apresentaria a associação total e a incremental, com interpretações distintas.

Como diagnóstico, estratificaria por tercis de `N_v` definidos no ajuste, sem escolher depois o estrato vencedor. Se não houver suporte comum — por exemplo, percentis altos só com coleta saudável —, declarar que o efeito não foi identificado.

**Cenário de falha:** o coletor degrada em horas ruins, a coorte encolhe e o percentil muda. O estudo atribui ao ranking um efeito da infraestrutura.

---

**3) Sobrevivência: muda a interpretação; não invalida automaticamente a hipótese operacional.**

Há uma correção factual importante: **o código atual não implementa simplesmente “os 120 mais promissores”.** A ordenação usada no corte privilegia os mais recentes; os mints fixados recebem tratamento especial ([tracker.py:146](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker.py:146), [linha 243](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker.py:243)). Isso precisa ser conferido contra as versões efetivamente implantadas no período.

Além disso, a pista rápida distingue moedas jovens de moedas mantidas por apostas, posições ou propostas abertas ([fast_lane.py:103](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/fast_lane.py:103)). Portanto, a composição também depende da política da própria mesa.

Eu declararia:

> “Percentil entre mints recentemente observados pela pista de 15 s, sob a política de descoberta, retenção e capacidade vigente. Não representa percentil do mercado pump.fun.”

E mudaria:

- Nomear a população **“recentemente observada”**, porque ausência de linha por 120 s não equivale a morte econômica.
- Usar no principal uma faixa etária comum, proposta **0–300 s na decisão**, para reduzir a cauda mantida exclusivamente por posições abertas.
- Separar os regimes de capacidade 120/300; não tratar essa mudança como mero aumento de amostra.
- Registrar composição, indisponibilidade e cobertura por regime operacional.
- Para cobertura de descoberta, usar uma mesma população de nascimentos e horizonte: “criados no balde que receberam observação em até X segundos”. `rastreados agora / criados neste balde` mistura estoque e fluxo.
- Comparar graduações com horizonte de acompanhamento igual, sem usar graduação posterior para decidir pertencimento passado.

**Cenário de falha:** apostas duradouras mantêm determinadas moedas na coleta; sua presença eleva o estado agregado. O teste B passa a reconhecer a carteira da mesa como se fosse o mercado.

Não tentaria corrigir isso com ponderação por probabilidade de seleção sem conhecer essas probabilidades.

---

**4) Teste B: uma observação por balde, inferência por blocos temporais.**

O desenho permite calcular o estado com informações até o fim do balde ([desenho:38](C:/dev/project-hunter/.claude/state/r69/desenho.md:38)). Eu substituiria por:

- Para o balde **[12:00, 12:05)**, congelar o estado às **12:00**.
- `live_n`, fluxo e progresso: snapshot da coorte elegível às 12:00, um voto por mint.
- `births_min`: eventos conhecidos no intervalo anterior **[11:55, 12:00)**, divididos por cinco.
- `grads_h`: eventos conhecidos em **[11:00, 12:00)**.
- Desfecho: média dos retornos das primeiras entradas elegíveis por mint em **[12:00, 12:05)**.

Assim, nenhuma entrada é explicada por informação posterior a ela. Não calcular medianas sobre todas as linhas de cinco minutos: isso dá mais peso a quem foi observado mais vezes.

**Unidade observacional:** balde de cinco minutos.  
**Unidade de reamostragem:** bloco temporal contendo todos os mints e baldes daquele intervalo.

Proposta concreta: blocos de **60 minutos**, com sensibilidade predefinida a **120 minutos** e retirada de um dia por vez. Os blocos precisam cobrir a dependência residual e a sobreposição dos horizontes; se a autocorrelação persistir, 60 minutos não é suficiente. Reamostragem em blocos preserva dependência que o bootstrap individual destrói. [Hyndman e Athanasopoulos](https://otexts.com/fpp3/bootstrap.html).

**Permutar mints dentro do dia não resolve autocorrelação intradiária.** Uma aposta por mint também não torna moedas simultâneas independentes. Essa correção vale para A.

Baldes sem entrada têm retorno médio **indefinido**, não zero. O teste mede retorno condicionado a haver entrada pela política observada. Para “vale a pena operar?”, volume de oportunidades e resultado por tempo são outra pergunta.

**Cenário de falha:** uma hora favorável produz 100 moedas vencedoras; bootstrap por mint transforma um episódio em 100 evidências.

---

**5) Multiplicidade: congelar a família e corrigir a população antes dos p-valores.**

O documento enumera **14 variáveis de origem e cinco medidas de estado**, não 13 e quatro ([desenho:12](C:/dev/project-hunter/.claude/state/r69/desenho.md:12), [linha 40](C:/dev/project-hunter/.claude/state/r69/desenho.md:40)). A lista também difere da do R65, que incluía hora, reserva real e razões derivadas ([stats.py:103](C:/dev/project-hunter/.claude/state/r65/stats.py:103)).

**Minha proposta concreta de grade enxuta:**

| Item | Congelar agora |
|---|---|
| Variáveis de A | Idade, progresso, delta de progresso, mcap, delta de mcap, compras, vendas, vendas/compras, compradores únicos, fluxo líquido, snipers, dev share, holders |
| Hipóteses A | 13 testes incrementais do percentil além do absoluto |
| Hipóteses B | 4: nascimentos, fração de fluxo positivo, progresso mediano e graduações; `live_n` como controle de cobertura |
| Desfecho inferencial | Apenas retorno líquido por SOL aplicado |
| Família | **17 hipóteses**, testes bilaterais, FDR nominal 10% |
| Cortes | Curvas em P20/P35/P50/P65/P80 apenas descritivas; nenhum corte escolhido para declarar vitória |
| MFE | Secundário descritivo, com cobertura e método separados |
| Combinações/interações | Fora desta rodada |

Isso **muda explicitamente a lista original**; não deve ser apresentado como mera repetição dos 13 filtros do R65. Razão com denominador zero fica indisponível, com motivo.

Fixar também: política de saída, população, deduplicação pela primeira decisão elegível **antes de conhecer o desfecho**, tratamento de censura, fontes, janelas, modelos, sementes e regra de parada. Hipótese sem dados suficientes permanece registrada como não testável; não se substitui por outra promissora.

Se quiser transformar os cinco cortes em testes separados, são **65 contrastes adicionais**, levando essa proposta a **82**, antes de acrescentar MFE, subgrupos ou interações.

Duas ressalvas decisivas:

1. **BH não conserta p-valores inválidos.** Tampouco garante FDR sob dependência arbitrária. Eu reportaria BH e usaria Benjamini–Yekutieli como referência conservadora enquanto não houver justificativa para a dependência dos testes. [Benjamini–Yekutieli](https://www.math.tau.ac.il/~ybenja/depApr27.pdf).
2. **20–23/09 já não é holdout intacto.** R67 examinou resultados de 20–21/09 e documentou a falta de observações prospectivas em 22–23/09 ([notes-R67:108](C:/dev/project-hunter/.claude/state/notes-R67.md:108), [linha 176](C:/dev/project-hunter/.claude/state/notes-R67.md:176)). O split proposto serve como diagnóstico retrospectivo; confirmação exige dados posteriores ao congelamento.

**Também retiraria “papel + real” do primário.** Dividir por tamanho não harmoniza saída de 300 s com saída de 1800 s, nem custos simulados com executados. Essa diferença já está documentada em [notes-R67:172](C:/dev/project-hunter/.claude/state/notes-R67.md:172). Escolher uma população homogênea; as demais são sensibilidades separadas.

**Cenário de falha:** percentis altos concentram apostas de uma política mais permissiva, e a diferença de retorno é atribuída à entrada.

---

**6) Falseamentos baratos antes do principal.**

Eu exigiria esta sequência:

1. **Invariância ao futuro, de ponta a ponta.** Acrescentar linhas futuras, backfills recebidos depois, graduações posteriores e atualizações tardias de metadados. Coorte, percentis, estado e elegibilidade passados devem permanecer idênticos. O teste atual cobre apenas parte disso ([desenho:33](C:/dev/project-hunter/.claude/state/r69/desenho.md:33)).

2. **Casos mínimos conhecidos.** Empates completos → P50; permutar ordem das linhas → mesmo resultado; duplicar linhas do mesmo mint → mesmo resultado; sujeito ausente e denominador vazio → indisponível. Variável constante no instante, como hora, não pode produzir separação transversal.

3. **Controles aleatórios repetidos.** Gerar várias variáveis independentes, estáveis por mint, com sementes congeladas, e passar pelo pipeline inteiro. Não exigir que todo p seja maior que 0,05: falsos positivos ocasionais são esperados. Procurar inflação sistemática e descobertas além do esperado pela família.

4. **Desfecho “qualidade da observação”.** Testar descritivamente se percentis e estado predizem censura, ausência de fita ou apenas disponibilidade de MFE. Associação forte não prova artefato, mas exige mostrar que o resultado econômico não depende de excluir justamente esses casos. É o mecanismo relatado no R66 ([notes-R66:114](C:/dev/project-hunter/.claude/state/notes-R66.md:114)).

5. **Deslocamento temporal por blocos.** Desalinhar estado e retorno por deslocamentos predefinidos suficientemente longos, preservando a estrutura temporal. Se muitos alinhamentos arbitrários parecem tão bons quanto o causal, o resultado pode ser tendência comum ou inferência mal calibrada. Persistência de regimes impede tratar isso como prova isolada.

**NICE-TO-HAVE**

Comparar janela de 120 s com 30/60 s e inclusão/exclusão do sujeito como sensibilidades fixadas antecipadamente. Reportar tamanho de efeito, suporte e influência das maiores observações; não escolher a janela que rende o menor p.

**O QUE EU FARIA DIFERENTE**

Dividiria o trabalho em três etapas: auditoria temporal sem olhar retornos; R69 retrospectivo exploratório com a família congelada; confirmação prospectiva sob uma política única de saída.

A pergunta central seria **“o contexto relativo acrescenta previsão útil ao absoluto?”**. Uma diferença entre grupos, mesmo confirmada, ainda não demonstra retorno líquido positivo nem benefício de carteira.

**CONCORDO COM**

A ideia de usar informação relativa contemporânea; a exigência de disponibilidade além de `as_of`; a fonte comum para sujeito e pares; a deduplicação por mint; e declarar que a coorte observada não representa o mercado inteiro. Essas são boas bases para um desenho corrigido.

**OBSIDIAN**

- **R69 — revisão do desenho pela Astra** — criar registro em `Revisoes-Astra` com contrato temporal, população, família estatística e pendências de validação.
- **KB-0149 — O que a mesa real ensinou** — acrescentar que “não confirmado” não demonstra ausência de informação e que reutilizar períodos não cria confirmação independente.
- **Meme (Mercado)** — documentar seleção por recência, capacidade, fixação por posições e diferenças entre tempo observado e disponibilidade.
- **Diário — 2026-09-23** — registrar revisão pendente antes do teste principal e necessidade de confirmação prospectiva.
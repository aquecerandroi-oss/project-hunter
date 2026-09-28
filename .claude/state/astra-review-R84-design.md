**RESUMO**

**Ainda não consideraria fechado o desenho de dados do R84.** A reconstrução inclui deslistados, mas não demonstra completude. Concordo com as três decisões de classificação propostas, condicionadas à identidade histórica do ativo. Discordo de transformar qualquer lacuna de 14 dias em deslistagem e de tratar toda migração como perda necessariamente conservadora para TS−EW.

Revisão como `quant-engineer`, em modo OPINIÃO. Os números 735/709/750 e os controles são os **registrados nas notas**, não contagens que reproduzi. [notes-R84.md:102](C:/dev/project-hunter/.claude/state/notes-R84.md:102)

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Revisão estática por leitura e busca local. Não executei os scripts, testes, consultas de rede ou downloads; não examinei preços nem retornos.

**MUST-FIX**

1. **Inclusão de deslistados não equivale a censo completo.**

   Os 26 controles e os 41 pares ausentes do `exchangeInfo` demonstram que o arquivo **não contém apenas sobreviventes**. Não demonstram que todos os desaparecidos estão nele. O critério de completude atualmente depende desses controles e de contagens mensais “plausíveis e monotônicas”. [notes-R84.md:34](C:/dev/project-hunter/.claude/state/notes-R84.md:34)

   **Cenário de falha:** um par historicamente elegível foi removido do cadastro atual e nunca teve arquivo mensal publicado, ou teve seu arquivo retirado. Pode existir apenas em arquivos diários, outra família de arquivos ou registros históricos. Ele falta nas duas fontes e, portanto, também no ranking histórico. Um par de vida muito curta pode ser inelegível pelos 35 dias; a ausência de um par antigo, porém, pode mudar o top-20.

   **Como fechar sem preço:** reconciliar um inventário independente de anúncios de listagem, remoção de pares, suspensão e migração com snapshots históricos de cadastro, cobrindo todo o período. Para cada par, registrar identidade, cotação, datas e fontes; confrontar com os prefixos mensais, diários e, como controle adicional, de negócios. Cada diferença precisa ser explicada. A cobertura temporal desse inventário também precisa ser demonstrada: uma coleção seletiva de anúncios vira apenas outro conjunto de controles.

   Sem isso, a conclusão correta é **“completude não demonstrada”**, sujeita à trava de limite de dado da H-024. Contagens mensais não precisam ser monotônicas: deslistagens legítimas podem reduzi-las. [Fila de Hipoteses.md:287](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:287>)

2. **O download pode converter ausência de cobertura em falsa deslistagem.**

   O script limita os arquivos mensais a agosto e busca setembro apenas para símbolos presentes no cadastro atual. Além disso, qualquer HTTP 400 vira retorno parcial/vazio, sem distinguir a causa. [download.py:101](C:/dev/project-hunter/.claude/state/r84/download.py:101), [download.py:109](C:/dev/project-hunter/.claude/state/r84/download.py:109), [download.py:84](C:/dev/project-hunter/.claude/state/r84/download.py:84)

   **Cenário de falha:** um par negociou até 10/09 e desapareceu do cadastro até 28/09. O download termina em 31/08; a regra de última vela o encerra nessa data, antecipando a liquidação ou a perda total. Isso altera posições e elegibilidade em setembro.

   É necessário distinguir **“fim confirmado de negociação”**, **“fim do arquivo disponível”** e **“falha de aquisição”**, reconciliando a cauda com arquivos diários ou evidência documental. Status atual diferente de `TRADING` não resolve essa distinção. [notes-R84.md:73](C:/dev/project-hunter/.claude/state/notes-R84.md:73)

   Também não aceitaria “não está no mensal, logo é recente” como prova de idade: ausência de arquivo é justamente uma das hipóteses sob auditoria. [notes-R84.md:110](C:/dev/project-hunter/.claude/state/notes-R84.md:110)

3. **Separar avaliação de posição de execução durante lacunas; retirar a equivalência automática “14 dias = deslistagem”.**

   A H-024 manda carregar a posição durante lacunas até a série voltar. Já §1.3 encerra a série após 14 dias e permite negociação pelo preço carregado; sua frase “não é comprável; […] entra pelo fecho anterior” é contraditória. [Fila de Hipoteses.md:285](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:285>), [notes-R84.md:69](C:/dev/project-hunter/.claude/state/notes-R84.md:69)

   **Cenário de falha:** faltam 15 dias de arquivo, mas o mesmo ativo continua negociando e reaparece. O desenho cria uma deslistagem, aplica perda total e reinicia a idade sem evento econômico correspondente.

   **Outro cenário:** durante uma suspensão de três dias, a estratégia vende pelo último fechamento e evita a queda na reabertura. Carregar uma marca de avaliação não demonstra que essa venda seria possível.

   Dentro do congelado: preservar a posição e distinguir marca carregada de negócio executável; ausência de vela não autoriza nova compra nem liquidação fictícia. Usar 14 dias como **alerta para investigação** é defensável; como prova suficiente de término, não.

4. **A política de migração deve respeitar a cláusula de continuidade documentada.**

   O congelado prevê separação para troca **sem continuidade oficial documentada**. As notas estendem a separação a todas as trocas e qualificam a perda total como conservadora para CONFIRMA. [Fila de Hipoteses.md:285](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:285>), [notes-R84.md:79](C:/dev/project-hunter/.claude/state/notes-R84.md:79)

   `oldAssetCode/newAssetCode` prova um vínculo cadastral; sozinho, não informa necessariamente razão de conversão, direitos do detentor ou calendário. **Não obriga a emendar preços.** Mas exige investigar esses elementos antes de concluir que não existe continuidade documentada.

   **Cenário de falha, hipotético:** EW possui 5% numa moeda de sinal negativo; TS não a possui. Uma conversão preserva economicamente a posição. Imputar perda total apenas à posição da EW acrescenta aproximadamente **5 p.p. a TS−EW nessa semana**, antes dos demais efeitos. Portanto, “pessimista para patrimônio comprado” pode ser **favorável ao contraste**.

   Publicar contagens de migração é útil, mas não corrige essa classificação. Os dois tratamentos congelados devem ser apresentados como cenários de deslistagem; não presumir que ordenam matematicamente o contraste entre estratégias.

5. **Blocos contíguos precisam preservar o calendário.**

   §1.5 toma apenas semanas avaliáveis em ordem; §1.4 remove as demais de `d_t`. Isso pode transformar oito observações consecutivas em algo diferente de oito semanas consecutivas. [notes-R84.md:88](C:/dev/project-hunter/.claude/state/notes-R84.md:88), [notes-R84.md:93](C:/dev/project-hunter/.claude/state/notes-R84.md:93)

   **Cenário de falha:** quatro semanas avaliáveis, três não avaliáveis e outras quatro avaliáveis viram um bloco artificial de oito semanas, embora cubram onze.

   Antes da inferência, verificar pelas datas que cada bloco admissível tem incrementos de sete dias. **Se não houver buracos internos, o achado se encerra.** Se houver, explicitar o tratamento compatível com “blocos móveis contíguos de oito semanas”; não comprimir silenciosamente o calendário nem preencher diferenças desconhecidas com zero. [Fila de Hipoteses.md:286](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:286>)

**NICE-TO-HAVE**

- Guardar manifesto de aquisição: páginas de listagem, término da paginação, fontes, horários, checksums e diferenças entre inventários. O enumerador hoje extrai XML por regex e encerra também quando não encontra prefixos, mesmo diante de truncamento. Melhor falhar explicitamente nessa inconsistência. [list_symbols.py:25](C:/dev/project-hunter/.claude/state/r84/list_symbols.py:25)
- Evidenciar a classificação **vigente em T**, especialmente em reutilização de ticker e mudança de desenho. Em E3, a existência futura do ativo subjacente não deve justificar exclusão retroativa do embrulho. [notes-R84.md:61](C:/dev/project-hunter/.claude/state/notes-R84.md:61), [Fila de Hipoteses.md:285](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:285>)
- Validar a futura implementação com séries sintéticas: lacuna recuperável, migração documentada, cauda ausente, vela não final e calendário descontínuo. Não executei essas validações.

**O QUE EU FARIA DIFERENTE**

Fecharia primeiro um registro de **identidades e eventos**, sem preços: listagem, suspensão, retomada, remoção, migração e cobertura documental. Só depois usaria as velas para preencher as séries. Assim, o último arquivo encontrado não decide sozinho quando um mercado deixou de existir.

Manteria o bloco H-024 intacto. Correções de implementação e interpretações seriam registradas num adendo anterior aos retornos; qualquer mudança efetiva do desenho teria de ser reconhecida como tal.

**CONCORDO COM**

- **FRAX ficar:** sim, para a identidade de governança sucessora de FXS descrita no catálogo. E1 classifica desenho econômico, não sequência de letras. Isso não autoriza aplicar a identidade atual a eventual histórico de outro ativo com o mesmo ticker. [notes-R84.md:116](C:/dev/project-hunter/.claude/state/notes-R84.md:116)

- **bStocks não alavancados ficarem:** sim, pela definição operacional e pelas exclusões literais congeladas. Publicar participação em semanas-moeda e deixar claro que a população pode incluir exposição a ações; se participarem, o resultado não será exclusivamente sobre criptoativos nativos. [notes-R84.md:124](C:/dev/project-hunter/.claude/state/notes-R84.md:124)

- **ETFs bStocks alavancados entrarem em E2:** sim. O fundamento é a alavancagem documentada, não possuir sufixo `UP/DOWN`. A aplicação registrada é coerente com a categoria econômica do congelado. [notes-R84.md:119](C:/dev/project-hunter/.claude/state/notes-R84.md:119), [Fila de Hipoteses.md:285](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:285>)

- **Último T = 14/09:** concordo **sob a convenção de exigir vela diária final também para fornecer a abertura de saída**. A saída de 21/09 usa uma vela final; a de 28/09 pertence à vela ainda aberta no `as_of` declarado. O descarte planejado precisa ser determinístico pelo `as_of`, não pelo dia da reexecução: o downloader atualmente incorpora as linhas da API sem filtro de finalidade. [notes-R84.md:84](C:/dev/project-hunter/.claude/state/notes-R84.md:84), [download.py:88](C:/dev/project-hunter/.claude/state/r84/download.py:88)

- **Bootstrap próprio:** concordo. O existente agrega e reamostra grupos rotulados; não implementa o esquema móvel especificado. Os mesmos índices devem ser aplicados às diferenças semanais pareadas de todos os braços. [resampling.py:115](C:/dev/project-hunter/infra/research/resampling.py:115), [notes-R84.md:93](C:/dev/project-hunter/.claude/state/notes-R84.md:93)

- **p centrado:** a expressão  
  \[
  p=\frac{1+\#\{\widehat D_b^*-\widehat D\geq\widehat D\}}{B+1}
  \]
  corresponde à cauda superior do bootstrap centrado na fronteira \(D=0\). Concordo como aproximação prevista; não é teste exato, e o IC percentil não é necessariamente sua inversão. [notes-R84.md:96](C:/dev/project-hunter/.claude/state/notes-R84.md:96)

- **Holm por limite:** coerente como ajuste **dentro de cada cenário**, usando os dois p e `alpha=0.05`; o moinho fornece os valores ajustados de Holm. Não apresentaria isso automaticamente como controle familiar único das conclusões robustas aos dois cenários: hipóteses nulas diferentes podem valer em cenários diferentes. Essa ressalva não autoriza trocar o procedimento congelado silenciosamente. [stats.py:126](C:/dev/project-hunter/infra/research/stats.py:126), [notes-R84.md:97](C:/dev/project-hunter/.claude/state/notes-R84.md:97)

- **REFUTA somente nos dois limites:** sim, ambos com limite superior abaixo de **0,0025 em fração de retorno**. Divergência implica NÃO CONFIRMA; insuficiência de dados impede chegar a esse julgamento. Isso respeita o congelado. [notes-R84.md:98](C:/dev/project-hunter/.claude/state/notes-R84.md:98), [Fila de Hipoteses.md:287](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:287>)

**OBSIDIAN**

- **KB-0164 — Momentum semanal em cripto grande:** acrescentar a revisão de sobrevivência, continuidade, execução em lacunas e interpretação dos cenários.
- **Revisões-Astra — R84: desenho de dados e sobrevivência:** registrar este parecer, suas pendências e as evidências que posteriormente as encerrarem.
- **Fila de Hipóteses:** preservar integralmente o bloco H-024 congelado; não alterar parâmetros para acomodar problemas de aquisição.
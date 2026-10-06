**RESUMO**

**Concordo com o replay por mint, mas ainda não consideraria demonstrada a equivalência nem o limite de memória.** O ACHADO 1 está correto. Os principais pontos pendentes são a separação dos dois relógios no avanço do estado, o contrato de ordenação nas fronteiras, a atribuição das taxas e a mediana exata.

Revisão como `quant-engineer`, em modo OPINIÃO.

**1) Existe decomposição exata por dia?**

Existe a identidade telescópica do E-PnL **para uma janela com inventário inicial e mapa de entidades fixados**. Ela não torna as contribuições reutilizáveis entre janelas diferentes: a avaliação inicial depende do inventário agregado e os episódios dependem do replay. Isso está explícito em [episodes.py:3](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:3) e [episodes.py:125](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:125).

Seu exemplo A compra/B vende está correto. O retrato remapeia os lotes preservados por carteira para a entidade do corte e depois processa a janela nessa entidade; o ledger do C-PnL nasce vazio em cada chamada. [ranking.py:160](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:160), [ranking.py:100](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:100).

Portanto, **“retirar a contribuição do dia velho e somar a do novo” não é exato com esses resumos**. Isso não prova impossibilidade de toda estrutura incremental mais rica; prova que seria necessário preservar dependências suficientes para refazer os efeitos de abertura, fusão, episódios e admissão. Eu escolheria seu replay de sete dias.

**2) A fita reduzida é suficiente?**

**Para as consultas efetivamente feitas pelo retrato, considero o argumento válido sob condições explícitas; não para toda consulta possível a `MintTape`.**

Seja `F` o conjunto completo de eventos do maior slot recebido antes de S:

- Nas fronteiras `b ≥ S`, os eventos anteriores descartados não podem superar o slot de `F`; basta unir `F` às chegadas de `[S,b)`. Isso preserva `valid_states_at(b)`. [pricing.py:243](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:243).
- Com ordenação temporal compatível com slots e atraso de entrada positivo, os pousos de gatilhos da janela ficam depois do slot de `F`. O último slot anterior necessário e todos os estados do slot de pouso permanecem disponíveis. [pricing.py:187](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:187).
- Os eventos descartados não podem satisfazer `event.slot > entry_slot`, portanto não são candidatos ao stop. [policy.py:140](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:140).
- No líder, os totais anteriores são suficientes porque o teste só é armado quando chega o gatilho. Depois disso, precisa continuar processando **todas** as chegadas, compras incluídas, na ordem original. [policy.py:99](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:99).

Uma fill pré-janela recebida depois de S deve permanecer nessa fita, mesmo sem pertencer a `window`. Ela pode alterar a saída do líder e as reservas disponíveis nas fronteiras seguintes.

Duas ressalvas:

- Não prometa igualdade de `landing_states(q)` para `q` anterior ou igual à fronteira: pode faltar o slot predecessor. Prove igualdade apenas no domínio consultado.
- Fixe os parâmetros cobertos pela prova: sete dias, atraso positivo e `settled ≥ S`. A API atual recebe parâmetros substituíveis. [ranking.py:138](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:138).

**3) P1–P3 mudam regra?**

**Restringem o domínio aceito hoje.** `Fill` não verifica essas três condições, e `causal_view` apenas aplica os dois cortes estritos. [tape.py:115](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:115), [tape.py:178](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:178).

Aceito-as como **pré-condições de uma equivalência condicionada**, com violação interrompendo o cálculo/publicação por motivo nomeado. Não aceito descartar a fill infratora e publicar o resto como equivalente.

P1 sustenta o fechamento do prefixo econômico: para `block_time < S`, o prazo de chegada termina antes de `S+7d`. Mas “lotes selados em S” precisa significar **inventário econômico em S, consolidado posteriormente**, não inventário conhecido no instante S.

O contrato de canonicalização é compatível com §9.6.4, desde que preserve a recepção original, o payload vencedor e os desempates. “Uma identidade chega uma vez” sozinho não especifica isso: `dedupe` mantém a recepção mais antiga e, no empate, a primeira ocorrência. [tape.py:165](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:165), [desenho:486](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:486).

**4) A ordem canônica dos lotes é legítima?**

**Sim, para a referência que você definiu — não como equivalência a qualquer `opening_lots`.**

O FIFO ordena abertura por `(opened_slot, opened_at)` com desempate estável; portanto a ordem fornecida pelo chamador decide os empates. [lots.py:140](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/lots.py:140).

Exemplo: A e B têm lotes empatados de 100 átomos, custos 100 e 300 lamports; a entidade vende 100. Consumir A ou B muda o W-PnL em 200 lamports.

Sua escolha `(slot, opened_at, carteira, ordem do livro)` é válida se:

- for parte explícita do contrato de construção da abertura;
- conservar a carteira original antes de `ents.of`;
- preservar a ordem do livro em serialização e restart;
- alimentar **identicamente** os dois caminhos.

Não a apresente como recuperação da ordem econômica original entre carteiras: é uma convenção determinística.

**5) `_leader_exit` histórico é intencional?**

**Há evidência de intenção; eu o preservaria no 1c-bis.** Não é apenas uma consequência acidental do laço: existe teste exigindo que uma compra e uma venda anteriores ao gatilho componham o percentual vendido. [test_wallets_policy.py:211](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_policy.py:211). A memória registra a decisão de reavaliar cada chegada sem filtro de slot. [wallets-engine.md:70](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-engine.md:70).

O efeito pode surpreender: histórico comprado/vendido de 100/100, seguido de nova compra de 25, deixa `100 > 0,5 × 125`; a saída pode disparar no próprio gatilho. É o comportamento do código. [policy.py:103](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:103).

O texto da regra não define claramente o início desse histórico. [desenho:177](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:177). Eu esclareceria “desde o início da história observada da campanha”. Trocar para episódio, janela ou período pós-gatilho seria mudança de regra separada.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes nesta revisão. Os exemplos abaixo são contraexemplos analíticos, não resultados de execução. Li os testes existentes; isso não constitui prova diferencial da implementação proposta.

**MUST-FIX**

1. **Separar o avanço econômico do avanço por recepção.**

   “Avançar usando o primeiro dia da janela” está ambíguo. São dois conjuntos:

   - lotes e evidência econômica: eventos com `block_time ∈ [S,S+1d)`, consolidados no corte adequado;
   - fronteira, totais do líder e máximo recebido: eventos com `received_at ∈ [S,S+1d)`.

   **Falha:** compra com bloco `S−1h`, recebida `S+1h`, já pertence ao lote econômico selado, mas ainda não ao total recebido antes de S. Usar apenas o dia de bloco perde sua chegada ao atualizar os totais; somá-la novamente aos lotes duplica inventário. As duas consultas têm semânticas distintas em [ranking.py:147](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:147) e [pricing.py:245](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:245).

2. **Precisar P3 para garantir que a divisão por dia não corte a ordem FIFO.**

   Se P3 significa apenas monotonicidade entre **slots distintos**, falta tratar timestamps contraditórios dentro do mesmo slot.

   **Falha:** mesmo slot e carteira: compra de assinatura `z`, bloco `S−1s`; venda de assinatura `a`, bloco S. Ambas chegam imediatamente. O FIFO integral processa `a` antes de `z`: venda unmatched e compra aberta. O avanço diário consome o lote anterior com a venda: saldo zero. A ordem atual é `(slot, signature, ordinal)`. [tape.py:155](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:155).

   Exija `block_time` consistente por slot, ou uma garantia equivalente de que cada prefixo econômico é prefixo da ordem usada pelo FIFO. Se “slot dividido em S” significar **recepção** dividida, isso é permitido: reúna os eventos da fronteira e as chegadas tardias antes de calcular as coincidências.

3. **O conjunto de assinaturas multimint não basta para atribuir a taxa.**

   Precisa identificar **qual evento recebe a taxa para cada `(owner, signature)`**, conforme a ordem global do conjunto processado. O FIFO e os episódios cobram na primeira ocorrência. [lots.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/lots.py:145), [episodes.py:231](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:231).

   **Falha:** uma transação compra X e Y, mas apenas X é vendido na janela. Cobrar os 5.000 em Y deixa a taxa no lote aberto; cobrar em X reduz o W-PnL realizado. Cobrança total igual não garante métricas iguais.

   A pré-semeadura funciona se derivada desse vencedor, separadamente para dono=carteira e dono=entidade. Um conjunto de assinaturas pode ser índice auxiliar, não o contrato completo.

4. **Resolver a mediana exata antes de declarar “acumuladores por entidade” de tamanho limitado.**

   A métrica publica `median(holds)` dos episódios fechados completos, incluindo os neutros que sobreviveram às exclusões. [metrics.py:144](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/metrics.py:144).

   **Falha:** posses `[1,2,100]` e `[1,50,100]` têm a mesma contagem e a mesma fração abaixo de 60, mas medianas diferentes. Somar contagens ou medianas por mint não preserva o resultado.

   Guardar todas as posses nos acumuladores reintroduz memória proporcional aos episódios. Use seleção/ordenação externa no Postgres ou outra representação exata com orçamento explícito. Inclua também o maior mint individual no limite: processar um mint de cada vez não garante, sozinho, RSS limitado.

5. **Preservar um oráculo independente ao refatorar `entity_metrics`.**

   Compartilhar o acumulador entre os dois caminhos é bom para manutenção, mas pode esconder regressões na prova diferencial.

   **Falha:** ambos passam a excluir episódios neutros da mediana; os dois retratos continuam iguais, embora difiram da implementação atual, que inclui essas posses. [metrics.py:144](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/metrics.py:144).

   Primeiro prove o acumulador contra a implementação anterior, com saídas esperadas independentes; depois faça os dois caminhos compartilharem a nova peça.

**NICE-TO-HAVE**

- Na passada A, mantenha a ordem **admissão/teto → exclusão histórica**. Hoje uma compra admitida consome o teto mesmo se seu episódio for excluído depois. Vinte compras assim bloqueiam a 21ª. Sua separação A/B pode preservar isso corretamente. [ranking.py:107](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:107).
- Na evidência fraca, guarde os três menores `(known_at, mint)`, com o mínimo por mint; não três mints arbitrários. Isso preserva a proveniência escolhida por `same_slot_links`. [entities.py:82](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:82).
- Fixe desempates de `event_order`: a identidade inclui `program`, mas essa chave de ordenação não. Empates completos dependem da ordem estável de entrada. [tape.py:128](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:128), [tape.py:155](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:155).

**O QUE EU FARIA DIFERENTE**

Escreveria a prova em três partes independentes: **suficiência do estado**, **equivalência do replay** e **limites de recursos**.

No diferencial, compararia também o estado após avançar vários dias e após serialização/restart, não apenas o retrato final. Incluiria chegadas tardias pré-S, compras fora de ordem, fusão tardia, taxas multimint, abertura empatada, primeira compra recusada e teto consumido por episódio excluído.

Para limitar candidatos da passada A, manteria os primeiros 20 por `(entidade, data da decisão)` dentre os candidatos que passam pelas recusas anteriores ao teto, preservando `decision_order`. Não é necessário acumular todos os candidatos globais. A posição do teto e o registro da primeira compra permitem essa redução. [follow.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:108), [follow.py:148](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:148).

**CONCORDO COM**

- Totais históricos comprado/vendido são dependência adicional real; não podem desaparecer quando o inventário zera. [policy.py:103](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:103).
- Pares com somente uma ou duas coincidências não podem ser podados por idade mantendo a regra atual. [entities.py:89](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:89).
- A primeira compra qualificante consome a oportunidade mesmo quando recusada; `mint_cooldown` não chega a barrar outra compra desse mint no ledger exclusivo da entidade, porque `not_first_buy` vem antes. [follow.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:110).
- O resultado atual materializa todas as linhas dos livros de entidades. **Ressalva ao achado de escala:** §9.6.5 já diferencia isso da persistência, que guarda individualmente as entidades que passam atividade e agrega as demais em contagens. A equivalência do motor precisa ser verificada antes dessa projeção. [ranking.py:187](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:187), [desenho:491](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:491).

**OBSIDIAN**

- **wallets-engine** — Registrar os dois relógios do estado, o domínio da prova e a semântica histórica de `leader_sold`.
- **Diálogo: armazenamento da fita de carteiras do H-030** — Acrescentar totais históricos, mediana exata e maior mint ao orçamento de continuação e temporários.
- **Revisão Astra: wallets-1c-bis** — Criar a síntese deste parecer e os casos exigidos para a prova diferencial.

Nenhuma dessas páginas foi alterada.
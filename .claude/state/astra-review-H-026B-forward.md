**RESUMO**

**Eu não congelaria o rascunho como está.** O comparador é temporalmente causal, mas não isola a contribuição da LTA; a regra de refutação admite inferência sem sustentação suficiente; e o detector ainda não preserva os dados necessários para uma coorte auditável.

Minha recomendação é **pré-registrar primeiro o contraste incremental retrospectivo no R85, como diagnóstico**, preservando a futura coorte como validação independente. O resultado de B já foi conhecido e motivou sua seleção: os retornos inéditos do comparador não transformam o painel inteiro em amostra nova.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão no papel de `quant-engineer`, somente leitura. Não executei detecção prospectiva nem consultei retornos da coorte.

**TESTES**

Não executei `pytest`: os testes de persistência escrevem arquivos temporários, incompatíveis com a restrição desta rodada. A contagem e a fidelidade em 12 dias são resultados **do artefato existente**, não reproduções minhas: [blind_counts.txt:1](C:/dev/project-hunter/.claude/state/h026b-forward/blind_counts.txt:1).

Recalculei em memória, usando as contagens publicadas:

```text
166 / 2762 × 365,25 = 21,95 eventos/ano com ambos os controles
166 / 2762 × 1120 = 67,31 eventos com ambos
176 / 2762 × 1120 = 71,37 eventos com P
323 / 2762 × 1120 = 130,98 eventos com R
((1,96 + 0,8416) × 16,7 / 3)² = 243,23 eventos
((1,96 + 0,8416) × 22 / 3)² = 422,11 eventos
40.º intervalo: 2029-09-24 a 2029-10-21, inclusive
C2 = 0,1448% por perna
C3 = 0,2800% por perna
```

**MUST-FIX**

1. **Corrigir o significado do contraste: ele compara estratégias, não identifica o efeito da linha.**

   B rompe a máxima entre toques; o comparador rompe o último pivô de alta confirmado. São gatilhos diferentes: [geom85.py:164](C:/dev/project-hunter/.claude/state/r85/geom85.py:164), [geom85.py:174](C:/dev/project-hunter/.claude/state/r85/geom85.py:174), [brk.py:19](C:/dev/project-hunter/.claude/state/h026b-forward/brk.py:19). O próprio painel registra apenas **181 de 336 B** também como rompimento simples: [blind_counts.txt:2](C:/dev/project-hunter/.claude/state/h026b-forward/blind_counts.txt:2).

   **Cenário:** B rompe um topo antigo depois de já ter rompido um pivô recente; P contém moedas no primeiro rompimento desse pivô. Uma diferença de retorno pode vir da fase do movimento, mesmo sem contribuição incremental da LTA.

   Além disso, `brk & ~A & ~B` significa **“sem A/B hoje”**, não “sem LTA” nem “sem teste recente da LTA”: [detect_daily.py:117](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:117).

   **Correção:** manter esse contraste com interpretação restrita ou registrar um contraste com **gatilho comum**: entre todos os rompimentos simples, comparar `B ∩ brk` com `brk ∩ ¬A ∩ ¬B`, no mesmo dia. Isso mede associação incremental do filtro B entre rompimentos comparáveis; ainda não prova causalidade econômica da geometria. É outra população, cuja contagem precisa ser refeita cegamente.

2. **Não permitir `REFUTA` sem suporte inferencial mínimo; aplicar K6 antes dos vereditos substantivos.**

   O rascunho permite refutação abaixo de ambos os pisos e só coloca concentração como condição de confirmação: [PREREG.md:11](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:11), [PREREG.md:12](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:12).

   **Cenário:** três eventos, em três moedas no mesmo dia, dão contraste negativo. Todas as réplicas não vazias repetem a mesma média; descartar as vazias pode produzir IC degenerado e `REFUTA`, embora exista apenas uma ocasião informativa.

   **Outro cenário:** uma moeda concentra 80% dos eventos negativos; o protocolo refuta a hipótese geral antes de verificar K6. Esse é precisamente o defeito corrigido no R85: [H-025-H-026-resultado.md:30](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/H-025-H-026-resultado.md:30).

   **Correção:** distinguir piso editorial de confirmação de **mínimo necessário para qualquer inferência**. Abaixo deste último, `LIMITE DE DADO`. Refutação abaixo de 150 eventos pode ser defensável, mas exige cobertura suficiente e procedimento validado para essa amostra — não uma permissão irrestrita.

3. **Fechar a definição da parada e alinhar o poder às populações efetivamente analisadas.**

   O protocolo exclui eventos separadamente por contraste, mas planeja a precisão dos dois usando aproximadamente 67 eventos com ambos: [PREREG.md:10](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:10), [PREREG.md:12](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:12).

   **Cenário:** na análise, R usa aproximadamente 131 eventos e P usa 71; a justificativa publicada pressupõe 67 em cada um. Também falta dizer se os 40 intervalos contam B bruto ou B com comparadores.

   A data **2029-10-21 está correta como fim do 40.º intervalo**. Entretanto:
   
   - Se os intervalos precisam estar completos, não existe parada antecipada antes da parada dura.
   - Se basta o intervalo conter um evento, a condição pode valer desde **2029-09-24**.
   - Se qualquer um dos primeiros 40 intervalos ficar vazio, o piso de cobertura torna-se inalcançável até a parada dura.

   Os **~245 eventos/~11 anos** são coerentes como aproximação marginal usando dp 16,7 e taxa de 22/ano. **Não representam 80% de poder para `CONFIRMA` conjunto.** Com dp hipotético de 22, só P exigiria aproximadamente 422 eventos; sua covariância com R também importa. O dp 16,7 inferido do bootstrap é uma escala efetiva de planejamento, não um desvio-padrão individual medido e transportável.

   Mantendo amostras separadas, os meios-IC aproximados seriam **±2,86 p.p. para R** e **±5,10 p.p. para P**, sob essas premissas. “P deve ter dp maior” é plausível, mas não garantido: depende também das covariâncias.

4. **Preservar os insumos originais; registrar ausência não resolve deslistagem nem revisão.**

   Cada execução baixa novamente o período desde 28/09; o registro guarda hash das linhas, mas não as próprias velas: [detect_daily.py:219](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:219), [detect_daily.py:237](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:237).

   **Cenário de deslistagem:** uma moeda entra no universo em outubro e desaparece da API em novembro. O próximo processamento perde suas velas de outubro, alterando volume, elegibilidade e geometria. Se ela nasceu depois do corte do R84, pode desaparecer também de `api_all` e nem sequer ser consultada; `api_missing_recent` só cobre o conjunto histórico `recent`.

   **Cenário de revisão:** a exchange corrige uma máxima antiga sem alterar o fechamento do dia registrado. Isso muda pivô/ATR/LTA; conferir somente o fechamento, como prevê o texto, não detecta suficientemente a causa.

   **Correção:** arquivo durável versionado de OHLCV e cadastro, identidade dos instrumentos já observados, carimbo de obtenção e política prévia para revisões. Hash é evidência de diferença, não mecanismo de recuperação. Falta de dado capaz de alterar o universo deve bloquear a conclusão daquele dia, não virar silenciosamente ausência de evento.

   Há ainda um erro concreto: **qualquer HTTP 400 vira “símbolo desconhecido”**, sem verificar `-1121`: [detect_daily.py:178](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:178). Um erro de parâmetros pode ser registrado como ausência legítima.

5. **Congelar identidade estável de série e mapeamento de ticker.**

   O painel troca `SYM` por `SYM#0` quando aparece uma segunda parte: [panel.py:75](C:/dev/project-hunter/.claude/state/r84/panel.py:75). O log persiste diretamente esse identificador: [detect_daily.py:110](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:110).

   **Cenário:** o evento foi registrado como `SYM`; depois de uma lacuna longa e retorno, a reconstrução histórica identifica aquela parte como `SYM#0`. Um casamento literal perde o evento; remover `#` indiscriminadamente pode uni-lo ao ativo errado. A conferência cega remove os sufixos e, portanto, não valida essa identidade: [blind_counts.py:91](C:/dev/project-hunter/.claude/state/h026b-forward/blind_counts.py:91).

   As continuidades também preservam o nome antigo como identidade da série: [data85.py:51](C:/dev/project-hunter/.claude/state/r85/data85.py:51). Isso exige separar **instrumento econômico, segmento e símbolo negociável por data**.

   **Correção:** chave estável por instrumento/segmento, início do segmento e aliases com vigência. Classificação somente por texto da base não protege contra reutilização do ticker por outro ativo.

6. **A idempotência atual é sequencial, não transacional; falta travar o congelamento.**

   `append_record` lê o log e depois abre para acrescentar, sem exclusão mútua: [detect_daily.py:133](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:133).

   **Cenário:** duas execuções leem o mesmo último dia e ambas acrescentam o seguinte. Uma queda durante a escrita também pode deixar uma última linha inválida que impede todas as retomadas.

   O hash do pré-registro é registrado, mas não comparado com um manifesto congelado; a classificação não entra nos hashes publicados: [detect_daily.py:223](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:223).

   **Correção:** antes da operação, persistência transacional em Postgres, unicidade por coorte/dia, validação de sequência e manifesto imutável com classificações versionadas. Mudança de hash precisa apontar para emenda explícita; apenas imprimir outro hash permite misturar protocolos.

**NICE-TO-HAVE**

- Testar exatamente **00:09:59Z/00:10:00Z**, inclusive o CLI. A guarda principal passa os 600 segundos corretamente, mas o teste atual verifica somente meia-noite sem margem: [detect_daily.py:216](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:216), [test_detect_daily.py:168](C:/dev/project-hunter/.claude/state/h026b-forward/test_detect_daily.py:168).
- Publicar concentração e pesos dos **comparadores**, além de B: poucos controles podem dominar o contraste mesmo com B diversificado.
- Distinguir abertura de `d+1` como **preço de referência hipotético** de entrada executável: a detecção às 00:10 não consegue negociar retroativamente às 00:00. Isso não impede pesquisa de retornos, mas limita sua interpretação operacional: [PREREG.md:10](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:10).
- Identificar os primeiros dias reconstruídos após o congelamento como reconstrução histórica com desfechos ainda cegos, diferenciando-os dos sinais registrados diariamente.

**O QUE EU FARIA DIFERENTE**

**Primeiro, o retrospectivo incremental pré-registrado**, sem procurar o comparador que produz o melhor resultado. Congelaria um contraste principal, sua interpretação, censuras, custos e vereditos antes de abrir retornos adicionais.

Os **176 B com P** tornam esse diagnóstico viável imediatamente, mas são contagem de bandeiras, não garantia de 176 operações avaliáveis: [blind_counts.txt:3](C:/dev/project-hunter/.claude/state/h026b-forward/blind_counts.txt:3). Se escolher o gatilho comum proposto acima, a contagem será outra.

Eu manteria a coorte futura apenas se houver interesse em um arquivo de pesquisa de longo prazo e coleta durável de baixo esforço. **Não a apresentaria como estudo com perspectiva razoável de confirmação até 2029.** A expectativa de `LIMITE DE DADO` é coerente e fica ainda mais forte com a exigência de 40 intervalos ocupados.

Quanto aos **custos C1–C4**, faria estes ajustes antes do congelamento:

- **Aritmética correta:** C2 = 0,1448%, arredondado para 0,145%; C3 = 0,28%.
- **Nome incorreto da mediana:** o recibo mostra 37.376,5 lamports nas compras e 35.360,5 nas vendas; não demonstra mediana conjunta de 37.400 nas 20 pernas. Pode ser um parâmetro conservador baseado nas compras, desde que rotulado assim: [q_spot.out:3](C:/dev/project-hunter/.claude/state/h026b-forward/q_spot.out:3).
- **Máximo observado não é teto futuro:** C3 é estresse baseado em 20 pernas, não limite estatístico de custo.
- **Congelar a fórmula:** uma taxa fixa por venda não cresce com o valor vendido. Convertê-la em percentual e aplicá-la ao notional de saída faz a despesa crescer quando a moeda sobe. É aceitável como cenário proporcional declarado, mas não como reprodução exata da taxa fixa: [PREREG.md:11](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:11).
- **Depósito de ATA:** excluí-lo da despesa patrimonial é defensável quando recuperável; isso não o torna caixa disponível. Pelos valores fornecidos, cada abertura imobiliza **4,07856% da ficha de 0,05 SOL**. Publicaria depósito bloqueado e condições/custo de recuperação. A recuperação exige fechamento da conta e condições específicas, como saldo de token zerado. [Documentação oficial da Solana](https://solana.com/docs/tokens/basics/close-account).

**CONCORDO COM**

- **P e R juntos, sem Holm, está correto para `CONFIRMA`.** A hipótese nula conjunta é “P não supera zero **ou** R não supera zero”; exigir sucesso nos dois é interseção-união. Não exige independência. Um IC bilateral de 95% com limite inferior positivo corresponde nominalmente à cauda unilateral de 2,5%. A exigência conjunta reduz poder, não cria uma escolha oportunista entre resultados. [FDA — múltiplos desfechos, seção IV.B.1](https://www.fda.gov/files/drugs/published/Multiple-Endpoints-in-Clinical-Trials-Guidance-for-Industry.pdf).
- Isso **não demonstra efeito verdadeiro ≥1 p.p.**: `D̂ ≥1` com limite inferior >0 demonstra superioridade acompanhada de estimativa pontual acima do MRE. Para demonstrar superar o MRE, seria necessário limite inferior >1. A redação deve manter essa distinção: [PREREG.md:11](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:11).
- O rompimento simples respeita a confirmação em `j+k`; não vi antecipação nessa lógica. O detector corta as linhas em `day` antes de montar o painel: [brk.py:20](C:/dev/project-hunter/.claude/state/h026b-forward/brk.py:20), [detect_daily.py:90](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:90).
- Reaproveitar a geometria congelada, manter H=10, incluir dias sem evento no bootstrap e usar os mesmos índices de reamostragem são boas decisões.
- Recusar base nova elegível não classificada está implementado. A elegibilidade do universo usa histórico de velas, não simplesmente a lista atual de `TRADING`: [detect_daily.py:95](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:95), [engine.py:34](C:/dev/project-hunter/.claude/state/r84/engine.py:34).
- Pesquisa sem ativação e sem converter resultado Binance em promessa para Jupiter preserva a ressalva da [KB-0169:116](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0169-fibonacci-e-lta-diaria-no-dado.md:116).

**OBSIDIAN**

Nenhuma página foi alterada. Deveriam receber atualização:

- **H-028-forward-prereg** — registrar este parecer, bloqueios e decisões adotadas antes do congelamento.
- **Fila de Hipóteses** — fechar estimando incremental, suporte inferencial, parada e poder conjunto.
- **KB-0169 — Fibonacci e LTA diária no dado** — esclarecer que comparar gatilhos diferentes não isola a contribuição da LTA.
- **KB-0149 — O que a mesa real ensinou** — distinguir taxa fixa medida, cenário proporcional e depósito recuperável indisponível em caixa.
- **Mapa de Estratégias** — manter B como pista; retrospectivo incremental seria diagnóstico, sem promoção a candidato de papel.
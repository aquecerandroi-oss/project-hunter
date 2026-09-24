**RESUMO**

**Eu corrigiria o desenho antes de simular.** Concordo com o controlo também simulado, `t0 = proposed_at` e o emparelhamento por mint. A cadeia “sem nós” é defensável como **aproximação de deltas históricos fixos**, mas não como contrafactual exato da curva. Fotos, ordem intrasslot e censura ainda podem mudar artificialmente quem entra e quanto ganha.

Revisão como `quant-engineer`, em modo OPINIÃO. Os cenários abaixo são exemplos hipotéticos, não resultados das células.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei testes nem simulações. Fiz leitura estática do desenho, simulador, carregador, moinho e memória relacionada. Não há resultado experimental da H-016 nesta resposta.

**MUST-FIX**

**1. Questão 1 — especificar precisamente o que “sem nós” significa.**

Subtrair das fotos os deltas assinados das nossas trocas é coerente **se mantivermos fixos os dois montantes históricos de cada troca alheia**. Nesse modelo:

`reservas_sem_nós(s) = reservas_reais(s) − Σ deltas_nossos_após_âncora_até_s`

É necessário descontar SOL **e** tokens, compras **e** vendas, usando movimentos efetivos da curva, sem incluir taxas externas como reserva. O acumulador deve começar na âncora; qualquer efeito anterior já está embutido nela. A proposta está em [notes-R77.md:28](C:/dev/project-hunter/.claude/state/notes-R77.md:28); a atualização aditiva herdada está em [load.py:197](C:/dev/project-hunter/.claude/state/r72/load.py:197).

**Limitação concreta:** depois da nossa compra, uma compra alheia de determinado SOL recebeu menos tokens do que receberia sem nossa presença. Remover apenas nossa troca e conservar os dois montantes daquela compra **não recompõe o produto constante contrafactual**. Isso desloca preços e pode atravessar um limiar de recuo que estava próximo.

Portanto, concordo com o procedimento como **replay contábil aproximado**, condicionado a fluxos históricos fixos. Não o chamaria de curva exata “que existiria sem nós”. Reprecificar as trocas alheias exige escolher qual entrada permanece fixa e constitui outro modelo.

Também precisa haver uma verificação de completude das **nossas** trocas. **Cenário:** uma compra nossa falta no arquivo, mas aparece na foto; a correção não a remove, a máxima sobe artificialmente e uma venda posterior passa a parecer um recuo elegível.

**2. Questão 1 — a ordem dentro do slot ainda pode fabricar recuos.**

O carregador ordena trocas por `(slot, signature, event_index)`, e `build_path` preserva essa ordem nos empates de slot/tempo. O carimbo monótono resolve regressões temporais, mas não demonstra a ordem de execução entre assinaturas. [load.py:84](C:/dev/project-hunter/.claude/state/r72/load.py:84), [load.py:192](C:/dev/project-hunter/.claude/state/r72/load.py:192).

**Cenário:** no mesmo slot, uma venda seguida de compra produz uma recuperação; inverter para compra seguida de venda cria uma máxima e um recuo. O estado final pode coincidir, enquanto o gatilho muda.

Antes da execução, usar ordem de transação comprovada ou declarar ambiguidade intrasslot. Agregar ao estado final do slot é uma alternativa explícita, mas perde primeiros toques; não equivale ao replay trade a trade.

**3. Questão 2 — fotos podem disparar uma política observada por fotos; não recuperam o primeiro toque WS.**

**Não concordo com a justificativa suficiente de que “a fita WS teria visto as trocas”.** Isso não identifica a trajetória, o primeiro toque nem o preço disponível após sua latência. A H-016 pede o **primeiro trade**, enquanto o desenho acrescenta gatilhos por foto. [Fila de Hipoteses.md:189](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:189>), [notes-R77.md:40](C:/dev/project-hunter/.claude/state/notes-R77.md:40).

Dois cenários:

- Preço observado 100; no intervalo ausente, sobe a 120 e cai a 110. A foto final mostra 110: esconde um recuo de 8,3% da máxima.
- O primeiro recuo ocorre cedo, seguido de recuperação. Uma foto posterior novamente baixa dispara uma compra diferente daquela que o WS teria disparado primeiro.

Há ainda uma distinção real no código: **`observed_at` da foto RPC é o horário do bloco, não sua chegada**; `received_at` é separado. Logo, `observed_at ≤ t0` não prova que aquela foto estava disponível em `t0`. [rpc_curves.py:16](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_curves.py:16), [rpc_curves.py:148](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_curves.py:148).

Sob a suposição declarada, dá para medir um **replay idealizado em tempo de cadeia**. Não dá para concluir que ele reproduz o primeiro toque WS. Eu registraria a extensão por fotos como desvio e separaria trajetórias indeterminadas. **Apenas contar gatilhos por foto não basta:** uma foto também pode criar a máxima usada por um gatilho posterior de trade.

**4. Questões 3 e 7 — o adaptador precisa materializar o relógio novo.**

Concordo com comprar o controlo em `t0 + L`, mas `_fill_index` calcula o prazo usando **o timestamp do ponto passado**, não um instante externo. [sim.py:64](C:/dev/project-hunter/.claude/state/r72/sim.py:64).

**Cenário:** último estado em `t0 − 10 s`; chamar `_fill_index` nesse ponto procura até `t0 − 8,4 s`, em vez de `t0 + 1,6 s`. O controlo compra retroativamente.

O adaptador deve:

- Criar o estado de decisão em `t0`, carregando apenas reservas conhecidas pelo modelo até ali.
- Fixar `entry_bt` no pouso efetivo.
- Entregar à saída uma trajetória iniciada no pouso, já com a compra simulada incorporada.

Isso importa porque `window` só corta o limite superior e `simulate_current` inicia a máxima no primeiro ponto recebido: passar o prefixo anterior à compra permite saídas baseadas em estados pré-entrada. [load.py:227](C:/dev/project-hunter/.claude/state/r72/load.py:227), [sim.py:196](C:/dev/project-hunter/.claude/state/r72/sim.py:196).

**5. Questão 4 — censura comum é melhor, mas o horizonte congelado está incompleto.**

**Prefiro população comum às oito células e ao controlo.** Censura por célula confunde diferença de política com diferença de amostra. Contudo, a regra atual verifica apenas os pousos a 1,6 s e conserva essa população a 5 s. [notes-R77.md:56](C:/dev/project-hunter/.claude/state/notes-R77.md:56).

**Cenário:** a execução a 1,6 s sai antes de um buraco; a compra a 5 s muda o lote e a trajetória de saída, permanecendo exposta durante o buraco. Ela passa na elegibilidade original, embora seu desfecho não esteja coberto.

Também é preciso cobrir a janela de espera de quem **não entra**. O último pouso dos braços que entraram não necessariamente alcança `t0 + W`.

Minha preferência é um horizonte comum fixo que comporte toda a grade e ambas as latências: **até `t0 + 370 s`**, correspondente a `60 + 5 + 300 + 5`. Isso elimina a dependência do horizonte de censura em relação ao resultado da política. É uma emenda de desenho, a registrar antes da execução.

**Nenhuma das duas censuras garante ausência de viés por dados faltantes.** A comum evita composição diferente entre células; continua estimando a população com cobertura. E fotos frequentes podem satisfazer “buraco ≤ 60 s” sem resolver a trajetória entre elas — limitação já registrada no [KB-0152:99](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0152-a-oscilacao-existe-o-giro-nao-paga.md:99).

**6. Questão 5 — esclarecer zero, denominador e integridade dos pares.**

A frase “`D_i = política − controlo` (**0 para quem não entrou**)” é ambígua. **Zero é o retorno da política, não a diferença.** Se ela não compra e o controlo perde 20%, `D_i = +0,20`; se o controlo ganha 20%, `D_i = −0,20`. [notes-R77.md:62](C:/dev/project-hunter/.claude/state/notes-R77.md:62).

Além disso:

- O moinho estima **média dos retornos normalizados por decisão**, não `ΣPnL / ΣSOL decidido`. Com tamanhos de 0,05–0,07 SOL, essas quantidades diferem. Manter a fórmula congelada é defensável, mas o relatório deve nomeá-la corretamente. [protocol.py:185](C:/dev/project-hunter/infra/research/protocol.py:185), [notes-R77.md:47](C:/dev/project-hunter/.claude/state/notes-R77.md:47).
- Ausentes são retirados **linha a linha** pelo moinho. Um braço inválido pode deixar seu parceiro sozinho e destruir o emparelhamento. A exclusão precisa acontecer por decisão, antes do empilhamento. [protocol.py:238](C:/dev/project-hunter/infra/research/protocol.py:238).
- A elegibilidade de três trades desde `t0` não garante os três pontos exigidos pelo simulador **depois da nova entrada**. `ok=False` não pode virar retorno zero. [sim.py:199](C:/dev/project-hunter/.claude/state/r72/sim.py:199), [sim.py:245](C:/dev/project-hunter/.claude/state/r72/sim.py:245).

**7. Questão 6 — falta operacionalizar a fração de perdas exigida para confirmar.**

A confirmação exige queda da “fração das perdas que nunca passaram do custo”, mas o descritivo acompanha o subconjunto das perdas **reais históricas**. Isso não define a mesma estatística nos dois braços simulados. [notes-R77.md:72](C:/dev/project-hunter/.claude/state/notes-R77.md:72), [notes-R77.md:83](C:/dev/project-hunter/.claude/state/notes-R77.md:83).

**Cenário:** a política elimina perdas que antes chegaram a ficar positivas. O número de perdas que nunca superaram o custo permanece igual, mas sua fração entre as perdas aumenta. Contar somente perdas históricas evitadas indicaria melhora indevidamente.

Eu explicitaria, para cada braço, numerador, denominador, marca usada e tratamento do denominador vazio. Se a intenção é condicionar às perdas, seria: perdas simuladas cuja máxima líquida não supera o gasto, divididas pelas perdas simuladas. Sem perdas, a fração é indefinida; o tratamento decisório precisa estar escrito antes.

**NICE-TO-HAVE**

- Publicar resíduos de ressincronização, quantidade de episódios intrasslot ambíguos e dependência de fotos tanto nas máximas quanto nos gatilhos.
- Comparar controlo simulado e realizado por decisão, com distribuição dos erros. A comparação mistura também a regra de saída congelada com regras históricas; não é uma medida isolada de fidelidade de execução. O simulador fixa o comparador em [sim.py:30](C:/dev/project-hunter/.claude/state/r72/sim.py:30).
- Reportar Holm como especificado, deixando claro que **ele não participa da regra de confirmação escrita**. Os ICs do moinho são percentis marginais de 95%; imprimir p ajustado não os transforma em intervalos simultâneos. [resampling.py:94](C:/dev/project-hunter/infra/research/resampling.py:94), [notes-R77.md:66](C:/dev/project-hunter/.claude/state/notes-R77.md:66). Eu preferiria uma regra confirmatória com multiplicidade, mas isso seria emenda explícita, nunca mudança silenciosa.

**O QUE EU FARIA DIFERENTE**

Antes das células, registraria as correções na §9, preservando o congelado, como o próprio documento determina. [notes-R77.md:11](C:/dev/project-hunter/.claude/state/notes-R77.md:11).

Depois verificaria com trajetórias sintéticas: compra do controlo com estado antigo, permutação intrasslot, troca nossa ausente, foto que esconde máxima, não entrada com controlo vencedor e cobertura que falha apenas a 5 s. Dinheiro e reservas em inteiros/`Decimal`; timestamps conscientes de fuso e normalizados em UTC. A conversão para float ficaria restrita aos retornos adimensionais na inferência, como faz o moinho em [protocol.py:150](C:/dev/project-hunter/infra/research/protocol.py:150).

**CONCORDO COM**

**Questão 3:** simular os dois braços é a comparação correta dentro desse modelo. Usar entrada real somente no controlo mistura fontes de execução. `spent` deve ser o gasto nominal total; a taxa de entrada já está no menor montante que alcança a curva, sem segunda cobrança em `per_sol`. [notes-R77.md:47](C:/dev/project-hunter/.claude/state/notes-R77.md:47), [sim.py:237](C:/dev/project-hunter/.claude/state/r72/sim.py:237).

**Questão 5:** sim, **com exatamente um par válido por mint**. O bootstrap sorteia grupos inteiros com as somas dos dois braços, logo cada réplica é uma média de diferenças emparelhadas. A permutação troca os dois rótulos dentro de cada mint, equivalendo a trocar o sinal de `D_i`; o p é **bilateral**. [resampling.py:46](C:/dev/project-hunter/infra/research/resampling.py:46), [resampling.py:69](C:/dev/project-hunter/infra/research/resampling.py:69), [resampling.py:164](C:/dev/project-hunter/infra/research/resampling.py:164). Isso confirma a mecânica; a interpretação inferencial ainda pressupõe trocabilidade/simetria apropriada, não randomização real dos braços.

**Questão 6:** concordo com estas interpretações operacionais de [§1.8](C:/dev/project-hunter/.claude/state/notes-R77.md:70):

| Cláusula | Interpretação |
|---|---|
| **(b)** | Borda somente em X. Considerar W como borda tornaria todas as células de borda. |
| **(c)** | 5 s em entrada e saída dos dois braços; avaliar a **mesma célula vencedora a 1,6 s**, sem escolher outra a 5 s. |
| **(d)** | Retorno médio da política, incluindo não entradas com zero, **estimativa pontual ≤ 0**. Não exige significância contra zero. |
| **Hipótese inteira** | CONFIRMA se ambas confirmam; REFUTA se ambas refutam; demais combinações NÃO CONFIRMA, explicitando os dois rótulos. |

Ressalvas: **(a) é refutação pela regra literal, não prova estatística de inexistência de vantagem**. E as duas populações podem compartilhar mints, portanto não são replicações independentes. [notes-R77.md:17](C:/dev/project-hunter/.claude/state/notes-R77.md:17).

**Questão 7:** concordo com `t0 = proposed_at`. O fechamento das features limita a informação disponível; não antecipa a existência da proposta. Para a comparação pedida, deslocar a pista de 15 s para `features_end_time` permitiria comprar antes da decisão. [notes-R77.md:21](C:/dev/project-hunter/.claude/state/notes-R77.md:21).

**OBSIDIAN**

- **Fila de Hipoteses — H-016:** acrescentar referência à revisão e às emendas pré-execução, preservando o bloco congelado e sem atribuir resultado.
- **Revisões da Astra — R77 / H-016** *(nova página sugerida)*: registrar os cenários de falha e quais correções foram aceitas.
- **KB-0152 — A oscilação existe; o giro não paga:** acrescentar a distinção entre reconstrução aditiva e contrafactual da curva, além da ambiguidade intrasslot.
- **KB-0153 — O maior comprador não estava no arquivo:** ligar a distinção entre horário do estado RPC, chegada da foto e disponibilidade hipotética por WS.
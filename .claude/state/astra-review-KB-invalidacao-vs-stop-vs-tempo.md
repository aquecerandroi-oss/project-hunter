**RESUMO**

Sua leitura está correta. **−13,8430 R é a soma dos resultados encerrados por invalidação; não é uma estimativa do prejuízo causado pela regra.** Recomendo comparar **A atual, B sem invalidação, C com dois fechamentos e E com buffer em ATR**, deixando a carência D para depois. Primeiro, replay pareado das mesmas entradas; depois, confirmação em dados futuros.

Parecer como `quant-engineer`, em modo OPINIÃO. Nenhum arquivo modificado.

**ARQUIVOS**

Nenhum criado ou alterado. Li a memória, os registros anteriores, o experimento e os caminhos de decisão, saída e rearme.

**TESTES**

Não executei testes, replay ou consultas ao banco nesta revisão. Os números observados vêm da avaliação registrada no [EXP-0001:475](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:475).

Conferi somente a aritmética em PowerShell:

```text
24 / 91                         = 0,2637362637…
(29,7283 − 35,0167) / 91         = −0,0581142857…
(35,0167 − 29,7283) / 24         = 0,22035
1 − 0,95³                      = 0,142625
```

**MUST-FIX**

**1. Registrar atribuição contábil, sem atribuição causal.**

Texto que eu colocaria na nota:

> Na avaliação de 2026-09-06T13:00:00Z, 24 dos 91 acompanhamentos avaliáveis com R líquido conhecido terminaram por invalidação, somando −13,8430 R. Essa soma descreve resultados sob a política vigente. Não mede o efeito de invalidar: sem essa saída, os mesmos acompanhamentos continuariam até alvo, stop ou expiração, com resultado líquido desconhecido. O efeito da mudança exige comparar, para cada entrada, o resultado da política alternativa com o resultado da política atual.

Defina \(I\) como os 24 episódios que A encerrou por invalidação. Para entradas idênticas:

\[
\Delta_{B-A,I}=\frac{1}{24}\sum_{i\in I}(R_i^B-R_i^A)
\]

**Resultado posterior da operação** e **ganho incremental de continuar** são coisas diferentes. Continuar pode terminar com prejuízo e ainda melhorar A; pode recuperar parcialmente e depois perder mais.

Mantendo os outros 67 resultados fixos:

- Substituir os 24 por **zero** deixaria a média em **−0,0581 R**, mas isso é uma imputação, não uma consequência da remoção.
- Para zerar essa amostra, os 24 precisariam terminar, em média, em **+0,22035 R**: melhoria de aproximadamente **0,7971 R por episódio invalidado**.
- A média observada dos stops ou dos targets não identifica o resultado desses 24.

**Cenário de falha:** o preço perde o nível, A encerra em −0,58 R e B continua até um stop pior. Apagar contabilmente a perda de A fabricaria uma melhoria.

Há ainda uma correção de denominador: **0,5333 = 40/75**, considerando toques resolvidos também sem `R_net`; os 91 com R conhecido contêm **36 targets e 31 stops**. A página distingue essas populações no [EXP-0001:479](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:479). Não usar 0,5333 como taxa dos 67.

**2. Comparar entradas idênticas antes de comparar estratégias completas.**

Hoje o encerramento libera o acompanhamento em [outcomes.py:124](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:124), e o rearme depende de condição falsa com acompanhamento encerrado em [episodes.py:57](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:57).

**Cenário de falha:** A invalida, rearma e entra novamente; B continua na primeira operação. Comparar as médias dessas versões como se fossem pares atribuiria à saída diferenças que também vêm da seleção de entradas.

O experimento primário deve ramificar **cada entrada efetiva de A** nos quatro braços. Esses acompanhamentos contrafactuais podem se sobrepor; são medidas por entrada, sem interpretação de carteira.

**3. Não deixar a cobertura escolher o vencedor.**

Há **105 avaliáveis maturados, 14 sem `R_net` e 91 com R conhecido**, conforme [EXP-0001:495](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:495).

**Cenário de falha:** B permanece aberto, atravessa funding ou um buraco de dados e fica sem resultado; A já havia encerrado. Comparar somente os casos conhecidos de cada braço pode favorecer artificialmente B.

Pré-registrar população pela entrada e horizonte, apresentar cobertura por braço e calcular diferenças apenas com pares disponíveis, **explicitando que essa estimativa é condicionada à cobertura**. A análise histórica deve mostrar também os 14 excluídos; não converter funding desconhecido em zero.

**NICE-TO-HAVE**

Uma tabela por episódio com: resultado A, resultado alternativo, diferença líquida, tempo adicional exposto, funding adicional e motivo de indisponibilidade. Para os invalidados de A, apresentar quantos melhoraram, pioraram ou ficaram indeterminados — além da média.

**O QUE EU FARIA DIFERENTE**

**Variantes: substituiria D por E, mantendo três alternativas.**

Todas preservam entrada, stop inicial, alvo, horizonte de quatro horas e modelo de custos. A regra atual usa o nível rompido como invalidação em [momentum_v1.py:282](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:282); stop e alvo partem do fechamento de referência em [momentum_v1.py:217](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217).

| Braço | Regra proposta | Pergunta |
|---|---|---|
| A | Um fechamento de 15 min abaixo de L | Referência vigente |
| B | Sem invalidação; mantém **stop, alvo e horizonte** | A regra inteira acrescenta valor? |
| C | Dois fechamentos consecutivos distintos de 15 min abaixo de L | Uma quebra isolada é ruído? |
| E | Um fechamento de 15 min abaixo de `L − 0,25 × ATR₀` | Uma quebra pequena é ruído? |

**0,25 ATR é minha proposta de parâmetro inicial, sem evidência de otimalidade.** ATR₀ é o valor congelado na decisão; não recalcular depois da entrada. Se o limiar ficar abaixo do stop, registrar a redundância, sem deslocar silenciosamente o stop.

C e E separam **persistência temporal** de **profundidade da quebra**. D também é válida, mas exige uma hipótese mais específica: “a invalidação só prejudica durante a acomodação inicial”. A média de −0,58 R não fornece essa evidência.

Se escolher D no lugar de E: fixar, por exemplo, **30 minutos desde a entrada**, avaliar somente fechamentos de 15 min posteriores à carência e não carregar gatilhos anteriores. Não deixar “N barras” ambíguo entre barras completas e fechamentos atravessados.

Para C, fechamento igual ou acima de L zera a sequência; redelivery não conta como segundo fechamento; gap continua indisponibilidade. A saída ocorre na abertura seguinte à confirmação, preservando a prioridade atual `stop > target > expired > invalidated`, implementada em [walker.py:62](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:62).

Não removeria o stop nem mudaria o horizonte nesta candidata. Isso investigaria outros componentes e suas interações.

**Multiplicidade: quatro braços, três contrastes primários.**

Os contrastes são B−A, C−A e E−A. Quatro braços sobre os mesmos episódios **não quadruplicam a amostra**. Sob independência, três testes a 5% teriam 14,26% de probabilidade de ao menos um falso positivo; esse número é apenas ilustrativo, pois aqui os contrastes são dependentes.

Minha proposta de pré-registro:

- **Métrica primária:** média das diferenças líquidas pareadas, com o denominador original `entrada − stop inicial` fixo. É a normalização atual em [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74).
- **Efeito mínimo relevante:** propor `δ = 0,05 R por entrada`, definido antes da avaliação futura; é critério de decisão, não resultado observado.
- **Família:** três testes unilaterais `H₀: Δ ≤ δ`, correção Holm a 5%. Ordenar os p-valores e comparar sequencialmente com **0,0167; 0,025; 0,05**, parando na primeira não rejeição. Holm admite dependência entre testes, desde que os p-valores individuais sejam válidos. [Artigo de Holm](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf).
- **Dependência amostral:** reamostrar blocos temporais mantendo juntos todos os mercados e braços; preservar janelas sobrepostas. Congelar tamanho dos blocos e método antes da validação. **Um dia não sustenta estimação robusta dessa incerteza.**
- **Calendário:** início e fim UTC fixos, análise inferencial única após maturação da última entrada. Leituras diárias são descritivas; não encerrar quando aparecer significância.
- **Registro:** parâmetros exatos, código inclusive do modelo de saída, universo, dados utilizados, custos, funding, censura, métricas secundárias e todas as variantes efetivamente testadas.

Reportar também pior decil de R e duração adicional. Uma melhora de média com piora relevante de cauda exige decisão explícita; não declarar vitória por PF ou taxa de alvo secundários.

Os **100 outcomes e 30 dias são piso editorial, não cálculo de potência**, conforme a [decisão SHADOW:96](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/SHADOW.md:96). Testar parâmetros adicionais após olhar resultados amplia a busca; precisa ficar registrado. Esse processo de seleção é precisamente uma fonte de sobreajuste de backtest. [Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

**Replay: sim, resolve parte importante agora.**

Eu faria nesta ordem:

1. **Reproduzir A.** Usar entradas, níveis, custos e horários persistidos; conferir saída, preço e R contra o registro, justificando divergências por correção posterior de dados.
2. **Reexecutar desde a entrada nos quatro braços.** Verificar velas finais contíguas até o encerramento necessário, incluindo a abertura de expiração, e funding aplicável. O motor atual é uma função de avanço por barras e termina ao encontrar estado encerrado: [walker.py:162](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:162).
3. **Separar resultados.** `replay:<run_id>`, ligação à entrada original e proveniência dos dados; nunca sobrescrever outcomes prospectivos. Essa separação já consta do [plano SHADOW:11](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:11).

O replay pode responder **o que cada política teria produzido nesses caminhos de preço, sob o modelo por barras**, inclusive depois da invalidação. Pode revelar se o benefício depende de dois casos excepcionais, quanto tempo adicional exige e onde faltam dados.

Ele não pode:

- Transformar o dia que gerou a hipótese em confirmação independente.
- Descobrir a ordem real de stop e alvo dentro de uma vela de 1 min; manter a convenção pessimista e mostrar sensibilidade.
- Demonstrar fills, liquidez ou slippage reais.
- Reconstruir disponibilidade histórica de dados apenas porque hoje houve backfill.
- Medir a estratégia completa usando apenas as entradas emitidas por A.

Para a estratégia completa, seria necessário reconstruir também sinais potenciais, rearme e universo histórico. O próprio código alerta que a composição atual do universo não prova a passada em [config.py:58](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/config.py:58).

**Replay economiza desenvolvimento e elimina hipóteses ruins mais cedo; não cria dias independentes.** Uma regra congelada hoje pode ser avaliada posteriormente por replay sobre dados futuros reservados, se houver preservação suficiente. Isso testa a política por barras; a operação do worker ainda requer prova prospectiva.

**CONCORDO COM**

Concordo com preservar A, limitar alternativas e procurar o contrafactual após a saída. Renomearia a candidata para **“Valor incremental da invalidação no momentum”**: “invalidação menos agressiva” já sugere a direção vencedora.

Também evitaria reutilizar B/C sem contexto: a [KB-0005:49](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0005-stops-quando-eles-param-perdas.md:49) usa letras para outro desenho, incluindo remoção do stop. Cada braço precisa de identificador próprio do experimento.

**OBSIDIAN**

- **KB-0006 — Invalidação, stop por ATR ou saída por tempo:** registrar atribuição versus efeito, desenho A/B/C/E e limites do replay.
- **Strategy Backlog:** renomear candidata #1 e substituir a promessa implícita por hipótese neutra.
- **EXP-0001-momentum-v1:** acrescentar esta interpretação datada, preservando protocolo e avaliações anteriores.
- **KB-0005 — Stops: quando eles param perdas:** distinguir seu experimento de remoção do stop desta comparação de invalidações.
- **Revisões da Astra:** registrar o parecer, parâmetros propostos e itens ainda não verificados: cobertura pós-saída, replay e potência.
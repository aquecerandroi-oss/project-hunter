## RESUMO

**Eu emendaria o pré-registro antes do run.** A hipótese é testável, mas o texto ainda permite atribuir funding à posição errada, repor margem sem origem de caixa e subestimar incerteza por cobertura insuficiente.

Atuei como `quant-engineer`, considerando os cartões adversários. **O S7 está temporalmente correto; a janela de recebimento não está suficientemente definida.** Manteria Holm nos três braços e os limiares como escolhas econômicas prévias, sem apresentá-los como garantias de cobertura de custo.

## ARQUIVOS

Nenhum arquivo criado ou modificado.

A comparação do texto congelado com o trecho final da Fila, desconsiderando espaços nas extremidades, retornou `FROZEN_EQUALS_QUEUE_TAIL=True`.

## TESTES

Não executei backtest, testes automatizados nem baixei séries de mercado. Fiz leitura documental e conferências aritméticas em memória:

```text
Ida e volta sobre nocional: 0,50%
A1: 0,50% / 4 = 0,125%
A2: (0,50% + 0,80%) / 2 = 0,65%
Meio-IC anual, condicionado a dp=0,25 p.p. e n_efetivo=90: 2,686 p.p.
```

São contas das premissas, não resultados da H-028.

## MUST-FIX

**1. Unificar relógio da execução, guarda de preço e titularidade do funding.**

O S7 termina em `T−1h`: não vejo antecipação nessa variável. Entretanto, o universo incorpora o volume de domingo inteiro, a guarda consulta as duas aberturas de T e a execução usa essas mesmas aberturas. Isso exige uma convenção explícita de disponibilidade e execução posterior à observação. O texto ainda atribui funding em `(T+30min, T+7d+30min]`, embora declare saída às 00:00. [Pré-registro:4](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:4), [pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)

**Cenário de falha:** na segunda seguinte, uma posição é encerrada ou reduzida às 00:00; uma liquidação registrada segundos depois continua sendo creditada à quantidade antiga. Na entrada ocorre o inverso. A Binance documenta desvio de segundos na liquidação: a coincidência com a abertura não resolve quem recebe. [Binance — funding](https://www.binance.com/en/support/faq/detail/360033525031)

**Emenda recomendada:** manter T como referência do sinal e executar/rebalancear às **00:30 UTC, com preço intradiário desse horário**, após a observação da guarda. A janela proposta passa a ser coerente **se a posição realmente existir entre essas execuções**, usando a quantidade vigente em cada liquidação. Fechamento antecipado, liquidação e deslistagem interrompem a elegibilidade ao funding. Sem esses preços, declarar a execução diária como aproximação e congelar cenários para a fronteira; não chamar os 30 minutos de solução exata.

**2. Fechar o orçamento de capital, inclusive custos e posições presas.**

O texto combina metade do capital em spot, metade em margem, neutralidade em quantidade e perpétuo a 1×. Essas quatro propriedades não coincidem exatamente quando `F/m ≠ S`. Também não define de onde vêm custos ou recomposição de perdas ao recolocar o capital em 1 semanalmente. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)

**Cenário de falha:** com `S=100`, `F=105`, `m=1`, comprar uma unidade custa 100 e vender uma unidade cria nocional perpétuo de 105. Margem 100 significa 1,05×, embora a guarda de 5% aceite a entrada. Outro caso: uma posição fora do universo fica presa por lacuna, enquanto as novas vagas voltam a consumir 100% do capital.

**Emenda:** escolher uma definição consistente. Para 1× e neutralidade, reservar `q·F/m` de margem e `q·S` para spot, além dos custos. Registrar caixa, margem, posições e transferências internas; nenhuma transferência aumenta patrimônio. Posições presas continuam consumindo orçamento. Quantidade do contrato multiplicado é `q/m`, não `q`.

A convenção do R84 já reserva espaço para posições presas antes de dimensionar as novas; a H-028 precisa de equivalente para as duas pernas. [engine.py:91](C:/dev/project-hunter/.claude/state/r84/engine.py:91)

**3. A liquidação precisa depender do saldo efetivo e do preço de marca.**

O gatilho `2F_T/1,05` pressupõe margem igual ao nocional inicial, sem alterações relevantes de saldo. Isso conflita com a divisão por preço spot e não resolve posições carregadas, funding debitado, custos ou transferências semanais. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)

**Cenário concreto:** no exemplo anterior, margem 100 e short de uma unidade a 105, manutenção de 5% produz o gatilho simplificado:

`100 + 105 − P = 0,05P → P = 195,238`.

A fórmula congelada produz 200. Portanto, uma máxima de 197 passa pelo simulador apesar de cruzar o gatilho do próprio modelo.

Além disso, máxima do **último negociado** não é limite conservador garantido para máxima do **mark price**, que governa liquidação na Binance. [Binance — liquidação](https://www.binance.com/en/support/faq/detail/360033525271)

**Emenda:** definir margem isolada ou compartilhada, saldo efetivo, atualização após funding e rebalanceamento, e manutenção aplicada ao nocional marcado. Usar série de marca ou bloquear conclusão quando a aproximação puder mudar a solvência.

Também corrigir “funding só até a véspera”: **apagar funding negativo ocorrido antes da liquidação melhora artificialmente o resultado**. Sem ordenação intradiária, calcular cenários de ordem dos eventos. A perda da margem deve substituir o resultado terminal daquela perna, sem duplicar a perda do short nem apagar ganhos/perdas spot.

**4. Substituir ou limitar o erro de `F̂_k`.**

A abertura diária usada no funding não tem erro necessariamente desprezível. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)

**Cenário de falha:** abertura 100, marca na liquidação 150 e funding de −1%: por unidade, a aproximação debita 1 quando deveria debitar 1,5. O erro favorece a estratégia justamente num evento adverso.

**Emenda:** priorizar o `markPrice` associado ao evento em `/fapi/v1/fundingRate`, documentado pela própria API. Auditar sua cobertura histórica; a existência do campo não prova completude em todos os contratos. [Binance — histórico de funding](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)

Se faltar, usar fonte histórica alternativa de marca ou limites explícitos do erro. Não permitir CONFIRMA/REFUTA quando esses limites mudarem o rótulo.

**5. Separar elegibilidade, cobertura e identidade do contrato.**

Ter pelo menos sete liquidações não demonstra sete dias completos. O pré-registro também deixa ambíguo se seleciona primeiro o top-20 spot e depois verifica perpétuos, ou se filtra perpétuos antes do ranking. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)

**Cenários de falha:**

- Uma semana de cadência de oito horas perde 14 registros, preserva sete positivos e continua elegível.
- O vigésimo ativo spot não tem perpétuo; uma implementação deixa caixa, outra traz o vigésimo primeiro.
- Dois ativos distintos com ticker reaproveitado apresentam preços próximos e passam pela guarda de 5%.

**Emenda:** congelar a ordem do ranking e dos filtros, a regra de reposição e o denominador. Para preservar “top-20 à vista”, eu escolheria o top-20 spot primeiro e tornaria explícito o tratamento das vagas sem contrato.

Exigir auditoria de completude por contrato e período, deduplicação e identidade histórica documentada. A guarda de 5% é uma **guarda adicional de basis/preço**, não prova de identidade. Sua falha nunca apaga uma posição já existente ou seu prejuízo. Funding ausente durante a posse não vira zero.

**6. Completar as regras de lacuna, término e encerramento da amostra.**

Os dois limites tratam principalmente o valor do spot; ambos assumem recompra executável do perpétuo no último fechamento. Isso não constitui um limite pessimista de toda a operação protegida. O custo da liquidação final da carteira também precisa ficar explícito. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)

**Cenário de falha:** o último candle do perpétuo precede uma suspensão, mas o simulador recompra nesse fechamento porque conhece retrospectivamente o fim da série. Ou encerra a medição com posições abertas e deixa de cobrar as duas saídas.

**Emenda:** distinguir deslistagem, suspensão e falha do arquivo; usar condições documentadas de encerramento quando disponíveis. Quando não disponíveis, chamar os resultados de **cenários condicionais**, sem prometer que delimitam o resultado real. Congelar precedência entre término, liquidação e rebalanceamento, interrupção do funding e custos finais.

**7. Preservar calendário e exigir dispersão temporal da exposição.**

Os blocos são contíguos apenas se a série mantiver semanas de calendário contíguas. “Semana avaliável” com `N_T≥15` não define o que fazer com semanas intermediárias abaixo do piso. E 30 episódios em dez semanas não garante diversidade temporal suficiente. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5), [pré-registro:6](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:6)

**Cenário de falha:** excluir semanas de crise comprime o calendário e remove exposição adversa. Alternativamente, várias moedas entram durante um único trimestre favorável; centenas de semanas posteriores em caixa ajudam a cumprir 200 semanas, sem criar novos episódios econômicos independentes.

**Emenda:** manter calendário completo após o início; distinguir caixa verdadeiro de retorno desconhecido. Definir o tratamento das posições quando `N_T<15`; nunca descartá-las da conta. Acrescentar cobertura por blocos **não sobrepostos** de 13 semanas e por fatia temporal.

Como escolha conservadora para congelar agora, proponho ≥15 desses blocos com exposição, ≥5 em cada lado do corte, além dos pisos existentes. **É uma proposta de admissibilidade, não garantia de poder.** Falha implica `NÃO CONFIRMA — limite de dado`, antes de qualquer REFUTA. A precedência segue a regra de três rótulos. [RESEARCH.md:65](C:/dev/project-hunter/docs/RESEARCH.md:65)

## NICE-TO-HAVE

**Limiares e custos.** A aritmética está certa:

| Regra | Parcela derivada | Escolha que permanece |
|---|---|---|
| A1: 0,125% | `0,50% / 4` | Quatro semanas de persistência |
| A2: 0,65% | `(0,50% + 0,80%) / 2` | Duas semanas e excedente desejado de 0,80% |
| Saída A1: ≤0 | Interromper carry histórico não positivo | S7 como indicador de continuidade |
| Saída A2: <0,21% | Referência semanal do juro-base padrão | Usá-la como saída universal |

Não vejo evidência de escolha posterior ao resultado; vejo **premissas econômicas que devem ser nomeadas**. Reajustes semanais, basis e duração efetiva impedem dizer que A1 “cobre o custo em quatro semanas” sem a condição “se o funding persistir e os demais componentes não consumirem o excedente”. [Pré-registro:4](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:4)

A2 também **não é reprodução literal da minha proposta**: aquela encerrava após 14 dias e usava BTC/ETH; esta usa saída por estado e top-20. Eu escreveria “inspirada na proposta da Astra”. [Proposta original:46](C:/dev/project-hunter/.claude/state/astra-review-astra-ideias-estrategias.md:46)

**O custo do Lab está corretamente totalizado em dez bps por lado:** `2/2 + 5 + 4`. Não são onze. A decomposição do pré-registro, `5 de tarifa + 5 de impacto`, tem o mesmo total, mas componentes diferentes. Corrigir “igual ao modelo” para “mesmo total assumido”; não apresentar essa igualdade como validação histórica de tarifas. [pricing.py:35](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:35), [pricing.py:41](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:41)

**Poder e anualização.** Os ±2,7 pontos anuais conferem **condicionados** ao desvio e ao tamanho efetivo assumidos. Blocos de 13 semanas não implicam automaticamente `n_efetivo=90`, e a variância de A0 não estabelece poder para A1/A2. Eu retiraria a precisão aparente de “80% para 7–8%” ou mostraria a derivação com Holm e os demais portões. [Pré-registro:7](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:7)

`52×média` é uma anualização aritmética válida; chamá-la assim basta. Não precisa justificá-la como aproximação de capitalização.

## O QUE EU FARIA DIFERENTE

**Manteria Holm sobre A0/A1/A2.** Os três recebem rótulos próprios, portanto são três oportunidades de declaração positiva. A0 só deveria sair da família se fosse convertido, antes do run, em referência estritamente descritiva. Não faria essa mudança apenas para ganhar poder. Patamares podem continuar fora da família enquanto forem condições conjuntas, sem seleção de vencedor. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:6)

Escreveria também:

> CONFIRMA significa evidência de retorno médio positivo, com estimativa pontual ≥5% a.a., sob o modelo congelado. Não demonstra que o retorno verdadeiro excede 5%, nem que filtrar por S7 melhora o carry incondicional.

Para essas outras afirmações seriam necessários testes contra 5% e contrastes incrementais confirmatórios, respectivamente. Os contrastes contra A0 hoje são apenas descritivos. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:6)

Quanto aos cartões:

| Perspectiva | Primeiro ataque | Guarda proposta |
|---|---|---|
| **Advogado de Jesus** | “O lucro sobrevive quando cada funding pertence à quantidade efetivamente aberta e toda margem tem origem?” | Ledger reconciliado, execução sincronizada e nenhum funding após fechamento |
| **Defensor** | “Estamos matando carry por preços substitutos, liquidações falsas ou poucos períodos expostos?” | Marca real, limites de erro, cobertura temporal e insuficiência precedendo refutação |

Isso corresponde aos focos de custos/antecipação do [advogado:14](C:/dev/project-hunter/.claude/agents/advogado-de-jesus.md:14) e de poder/especificação do [defensor:14](C:/dev/project-hunter/.claude/agents/defensor.md:14).

Eu reuniria os sete ajustes numa **emenda datada, com horário UTC real, antes da ingestão e do cálculo**, preservando o original. Antes do run real, exigiria exemplos sintéticos de conservação de patrimônio, multiplicador, funding na fronteira, lacuna com capital preso, liquidação com funding negativo e fechamento final.

## CONCORDO COM

- Funding realizado e defasado, sem usar previsão como informação histórica. [Pré-registro:4](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:4)
- Capital ocioso contado, custos nas duas pernas e decomposição entre funding, basis e perdas. [Pré-registro:5](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:5)
- Reamostrar a carteira por semanas, preservando choques simultâneos, com índices comuns e sensibilidades de bloco. Treze semanas é uma escolha defensável, embora não certificada antecipadamente. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:6)
- Corte temporal, patamar, refutação restrita ao tamanho previsto e separação entre confirmação e promoção para papel. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:6), [pré-registro:7](C:/dev/project-hunter/.claude/state/r87/prereg_frozen.md:7)

**Veredito da revisão: pré-registro precisa de emenda; resultado ainda não verificável.** Nenhuma conclusão de rentabilidade ou autorização para perpétuo real.

## OBSIDIAN

- **Fila de Hipóteses — H-028:** acrescentar a emenda de relógio, ledger, margem, cobertura e inferência, preservando o texto congelado.
- **Revisões-Astra — H-028 pré-registro:** registrar este parecer e as decisões de aceitar ou rejeitar cada ajuste.
- **KB-0180 — Carry de funding:** não localizei o arquivo citado; materializar a nota e explicitar as diferenças entre a proposta original e H-028.
- **KB-0019 — O que a nossa funding rate mede de fato:** acrescentar a distinção entre taxa realizada, marca da liquidação e completude histórica.
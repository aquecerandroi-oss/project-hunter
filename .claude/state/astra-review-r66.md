**RESUMO**

**A premissa de ~0,5% ida-e-volta não se sustenta para o pool canônico recém-graduado do PumpSwap. Mas isso não demonstra que operar depois da graduação seja pior.** Demonstra apenas que a justificativa de economia de taxas está errada para essa rota.

O board serve para pesquisa exploratória de retornos entre observações. **Não permite reproduzir fielmente a regra de alvo/trailing de 300 segundos nem determinar se o PnL simulado é limite superior ou inferior.**

**ARQUIVOS**

Nenhum criado ou modificado. Revisão em modo OPINIÃO, como `quant-engineer`.

**TESTES**

Não executei testes da aplicação nem consultas à VPS. Os números de cobertura são os fornecidos por você; conferi código, memória do R65 e documentação oficial.

Conferência aritmética em PowerShell, com `Decimal`:

```text
0,00204 / 0,07 × 100                    = 2,914286%
0,001513840 / 0,07 × 100                = 2,162629%
75 × 0,001513840 / (87 × 0,07) × 100    = 1,864335%
```

**MUST-FIX**

**(a) Taxas: leitura correta da tabela; generalização excessiva sobre recém-graduados.**

O teste registra exatamente as 25 faixas, incluindo:

| Market cap em SOL | LP + protocolo + criador | Total por perna |
|---|---:|---:|
| abaixo de 420 | 2 + 93 + 30 bps | 1,25% |
| 420 até antes de 1.470 | 20 + 5 + 95 bps | 1,20% |
| a partir de 98.240 | 20 + 5 + 5 bps | 0,30% |

Evidência: [test_pumpfun_fee_config.py:133](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_fee_config.py:133). A [tabela oficial](https://pump.fun/docs/fees) confirma esses valores.

Portanto:

- **Não há desconto para 0,30% simplesmente por graduar.**
- A faixa depende do market cap da pool no instante da operação; “recém-graduado” não garante estar abaixo de 420 SOL.
- Há uma exceção relevante: a documentação publica **0,30% para pools não canônicos**. Isso não significa que exista, para cada mint, uma pool alternativa com liquidez e preço competitivos. [Fonte oficial](https://pump.fun/docs/fees).
- Jupiter não elimina a taxa da pool utilizada. Raydium ou outra pool precisam ser avaliados como rotas distintas, com cotação executável para o ticket.

A fórmula oficial usa reservas e supply da pool para calcular o market cap; não basta aplicar a faixa sobre o market cap do board sem validar equivalência. [Implementação documentada](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/FEE_PROGRAM_README.md).

**Cenário de falha:** simular 0,30% numa operação executada no pool canônico abaixo de 420 SOL cria aproximadamente 1,9 ponto percentual de vantagem fictícia no giro.

**Também corrigiria o rent e os denominadores antes da comparação.** O R65 registra 75 criações a **0,001513840 SOL**, não 0,00204; os 1,86% resultam da diluição sobre 87 tickets normalizados a 0,07 SOL. [KB-0147:20](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista.md:20).

Além disso, **2,23% já inclui rede**: 1,59 + 0,50 + 0,13 ≈ 2,22%, com arredondamento. Somar novamente 0,13% e apresentar 2,36% duplica rede.

Rent é capital recuperável, condicionado ao fechamento da conta, não necessariamente despesa definitiva. O fechamento da ATA de WSOL recupera seu saldo e rent; o construtor atual acrescenta essa instrução à venda. [tx.py:160](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:160), [Solana: fechamento de conta](https://solana.com/docs/tokens/basics/close-account).

**Cenário de falha:** comparar rent diluído da curva com rent integral de todo mint novo no PumpSwap, ou cobrar novamente o rent de WSOL já devolvido, altera artificialmente qual rota parece mais barata.

**(b) Market cap como preço: defensável sob condições explícitas.**

Com supply constante e definição consistente:

\[
1+R_{SOL}=\frac{MC_{USD,t_1}}{MC_{USD,t_0}}
          \frac{SOLUSD_{t_0}}{SOLUSD_{t_1}}
\]

Mas `volume_usd / volume_sol` **não é automaticamente câmbio spot**. Pode representar câmbio médio dos trades da janela, conversão histórica ou campos atualizados em momentos diferentes. O modelo armazena ambos os volumes, sem estabelecer essa equivalência econômica. [board_models.py:73](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/board_models.py:73).

Eu exigiria:

- Validar esse câmbio implícito contra uma referência contemporânea independente.
- Verificar supply, moeda de cotação, fonte do market cap e valores nulos/zero.
- Comparar board e trades/reservas onde houver sobreposição, declarando que essa subamostra também é selecionada.
- Separar horário da observação, disponibilidade local e atualização do mint.

Esse último ponto é material: o coletor agrupa por `received_at`, mas distingue `observed_at` de `mint_updated_at`. **Uma linha nova por minuto não garante preço novo por minuto.** [boards.py:13](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/boards.py:13). Até uma atualização do mint pode ter alterado outro campo.

A entrada precisa de definição própria. Se a primeira observação chega em +29 segundos, seu retorno é **desde essa observação**, não desde a graduação. Pode terminar em graduação +5 minutos, mas terá duração menor; alternativamente, conte cinco minutos desde a entrada observável. Não misture os dois relógios.

**Cenário de falha:** usar a primeira leitura de +50 segundos como preço de entrada na graduação elimina justamente os primeiros 50 segundos de alta ou queda e atribui uma oportunidade que não foi observada.

**(c) Censura: sim aos horizontes curtos com denominadores; +1 hora já é bastante selecionado.**

Eu reportaria +1/+5/+15 minutos e +1 hora, com:

`N maturado → N com entrada válida → N com endpoint válido → N ausente por motivo`.

Os 3.994/3.659/2.184 que “chegam” a cada horizonte **não são necessariamente pares válidos**: um registro posterior ao horizonte não prova preço disponível perto dele. Fixe previamente tolerância temporal e idade máxima do preço; divulgue o desvio efetivo dos horários.

Distinga:

- **Não inclusão:** mint nunca observado no board.
- **Entrada tardia:** primeira leitura posterior à graduação.
- **Perda de acompanhamento:** saída do board ou falha de coleta.
- **Censura administrativa:** horizonte ainda não maturou no corte.

O coletor distingue remoção observada de desaparecimento durante reconexão, informação útil para essa classificação. [boards.py:5](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/boards.py:5).

Sem conhecer a ordenação, **a direção do viés é desconhecida**. Ordenar por atividade pode reter vencedoras; ordenar por recência pode relacionar duração observada ao ritmo de lançamentos e ao regime. Não presumiria censura independente.

Para +4 horas, escreveria:

> “Retorno da população em +4 h não estimável com esta coleta. Há apenas 72 mints com acompanhamento informado até esse horizonte; eventuais resultados descrevem exclusivamente essa subamostra.”

**Cenário de falha:** excluir quem desaparece e chamar a média restante de “retorno dos graduados” produz aparente vantagem se tokens em queda saírem antes do board. `n` explícito torna a limitação visível, mas não corrige o viés.

**(d) Trailing com snapshots: erro sem direção garantida.**

Primeiro, a regra é **10% abaixo do pico, armada desde a entrada**, não distância fixa de 10% do preço inicial. O código compara a marca com `peak × (1 − trailing)`. [exits.py:94](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/exits.py:94).

Exemplos hipotéticos, entrada 100:

- **Subestima:** preço toca 116 entre observações e volta a 100. A regra contínua poderia atingir o alvo; snapshots não veem.
- **Superestima:** preço cai a 89 e recupera para 116 antes da próxima observação. A regra contínua poderia sair por trailing; snapshots registram alvo.

O pico observado é menor ou igual ao pico real, **mas essa desigualdade não se transfere ao PnL**. Perder um gatilho pode evitar uma perda ou provocar uma maior depois.

Esses dados são snapshots, não barras OHLC. Eu rotularia qualquer exercício como:

> “Simulação de monitoramento discreto a aproximadamente 60 s; não reproduz a execução atual. Viés líquido de direção indeterminada.”

Pode apresentar cenários condicionais, mas não chamá-los de limites matemáticos. Sem extremos intraminuto, os limites úteis para a política permanecem não identificados.

**Cenário de falha:** chamar o replay de “conservador” porque perdeu picos, enquanto também perdeu stops anteriores à recuperação.

**(e) Inferência: o método do R65 é aproveitável como exploração, com ajustes.**

Bootstrap por mint resolve repetições do mesmo mint; **não resolve dependência entre mints no mesmo choque de mercado**. Se houver uma entrada por mint, ele praticamente se reduz ao bootstrap usual.

Eu faria:

- Efeitos e intervalos por balde, com cortes previamente definidos.
- Sensibilidade por blocos temporais e retirando um dia de cada vez; sete dias continuam poucos para inferência de regime.
- Permutação que respeite a estrutura temporal e a hipótese testada, evitando embaralhamento irrestrito entre regimes.
- Uma família de testes que inclua features, cortes, horizontes e variantes efetivamente pesquisados. BH a 10% pressupõe condições de dependência; não transforma exploração adaptativa em confirmação.
- Validação cronológica futura, congelando a hipótese antes dos novos dados.

Features “na graduação” precisam estar **disponíveis naquele instante**. A primeira foto posterior não pode fornecer retrospectivamente holders, volume ou rank para uma decisão anterior.

Também não selecionaria apenas alvo/trailing: os demais desfechos e ausências devem permanecer contabilizados. Nesta coleta, prefiro retorno em horizonte fixo como resposta principal; o rótulo alvo/trailing está mal observado.

**Cenário de falha:** um balde concentra tokens de uma hora favorável; a permutação irrestrita fornece p pequeno para uma feature que apenas identifica aquela hora. BH não repara um p-valor construído sob independência falsa.

**(f) O veredito precisa ser mais estreito.**

Eu substituiria por:

> **“Não demonstramos economia relevante de taxas ao entrar no pool canônico imediatamente após a graduação. A recuperação de rent pode ser tratada independentemente da venue. Ainda não sabemos se a população pós-graduação oferece retorno líquido e execução melhores.”**

O que poderia derrubar a preferência por permanecer na curva:

- Menor impacto, falhas ou custo total efetivamente cotado e executado.
- Rota alternativa com liquidez suficiente e custo inferior.
- Melhor distribuição de retornos líquidos pós-graduação, confirmada prospectivamente.
- Menor exposição a eventos adversos que compense taxa semelhante.

Comparar somente moedas que acabaram graduando com compras anteriores na curva introduziria seleção pelo futuro. A comparação estratégica deve representar políticas executáveis, cada uma com seu universo disponível na decisão.

A restrição técnica também procede: o pacote PumpSwap se declara exclusivamente de venda, e o contrato documenta `pumpswap_buy_not_allowed`. [__init__.py:1](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/__init__.py:1), [RISK_ENGINE_MEME.md:97](C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:97). Entradas exigiriam implementação e revisão do contrato.

**Cenário de falha:** descartar uma população com melhor retorno bruto porque as taxas são semelhantes — ou promovê-la comparando apenas sobreviventes contra toda a população da curva.

**NICE-TO-HAVE**

Investigar se posição e permanência no board dependem de recência, volume ou retorno. Isso ajuda a diagnosticar seleção; não substitui acompanhar mints independentemente do ranking.

**O QUE EU FARIA DIFERENTE**

Dividiria R66 em duas entregas: **retornos observados com cobertura e censura**, agora; **comparação prospectiva de políticas com preços executáveis e coleta independente do board**, depois. Não usaria o replay de trailing de 60 segundos para decidir a mudança de venue.

**CONCORDO COM**

A contestação dos ~0,5%, a ausência de economia automática de rent, a insuficiência de +4 horas e a necessidade de pesquisa antes de implementar compras pós-graduação.

**OBSIDIAN**

- **KB-0147 — Custo é o prejuízo:** esclarecer rent por conta versus média diluída e que 2,23% já inclui rede.
- **Meme — Mercado:** registrar cobertura pós-graduação, frescor dos preços e seleção pelo board.
- **R66 — Operar depois da graduação** *(nova página sugerida)*: registrar taxas por rota/faixa, protocolo de retornos e limitações da simulação.
- **Revisões-Astra — R66** *(nova página sugerida)*: preservar o parecer e o veredito restrito: premissa de custo refutada; superioridade estratégica ainda indeterminada.
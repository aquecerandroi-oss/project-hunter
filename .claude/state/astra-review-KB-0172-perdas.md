**RESUMO**

**A conta de A está correta, condicionada à confirmação do aluguel nas transações. O efeito sobre stop/alvo também está correto.** B revela uma falha concreta de coerência entre decisão e execução. C descreve uma exposição econômica diferente, aceita no desenho original. A classificação serve como triagem, mas ainda não como atribuição causal do prejuízo.

Revisei como `quant-engineer`, somente leitura. Os números da VPS são os que você forneceu; não consultei as transações originais.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei pytest nem integração. Fiz inspeção estática e conferência aritmética com `Decimal` no PowerShell. Saída real:

```text
difference_lamports=550840
correction_4_sol=0.00220336
corrected_sum_sol=-0.00393846
weekly_sum_R=-0.03
net_if_additional_0.3R=-60.63
unaccounted_signals=11
```

O valor −60,63R pressupõe **0,3R adicional**, ressalva importante abaixo.

**MUST-FIX**

**1. Aluguel presumido está contaminando contabilidade e decisões.**

O envio atribui a constante quando detecta ATA criada ([spot_send.py:298](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:298)); a reconciliação repete isso ([spot_reconcile.py:320](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:320)). A entrada subtrai esse aluguel do desembolso, enquanto calcula o risco inicial por `ticket × stop_frac` ([spot_entry_writes.py:85](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:85)).

Portanto, usando os valores informados:

```text
excesso de aluguel excluído = 2.039.280 − 1.488.440 = 550.840 lamports
spent_correto = spent_registrado + 0,00055084 SOL
PnL_correto = PnL_registrado − 0,00055084 SOL
R_correto = R_registrado − 0,00055084 / initial_risk_sol
```

Nas quatro entradas, a correção total é **−0,00220336 SOL**. Partindo do total arredondado informado, resulta **−0,00393846 SOL**; a última casa depende do total original sem arredondamento.

Como `r_now = (mark − spent)/initial_risk_sol` ([spot_exit_rules.py:63](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:63)), um deslocamento `b = 0,53–0,75R` significa:

- O stop registrado em −1R só dispara aproximadamente em **−1,53 a −1,75R corrigidos**.
- O alvo registrado em +1,5R pode disparar em **+0,75 a +0,97R corrigidos**.

**Cenário concreto:** LINK pode chegar ao stop registrado de −1,023R já perto de −1,64R na mesma marca, como você descreveu. O fill posterior ainda acrescenta diferença de execução e taxa de saída.

**Há outra explicação?** O resíduo agregado sozinho não identifica a conta destinatária. Uma conta previamente financiada, um reembolso de outra conta na mesma transação ou outro crédito compensatório poderiam produzir desembolso líquido menor. Mas a repetição exata em quatro criações, contra zero nas seis restantes, é evidência muito forte de aluguel menor.

Há ainda compatibilidade externa específica: a **SIMD-0437 prevê o patamar 5.080**, além do antigo 6.960. Isso reforça a explicação; o documento não prova qual feature estava ativa no slot de cada operação. [Proposta oficial SIMD-0437](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0437-incremental-rent-reduction.md).

A prova definitiva deve reconciliar, por assinatura, `meta.fee`, financiamento da ATA correta, seus saldos anteriores/posteriores e eventuais fechamentos/reembolsos. **Não substituiria uma constante pela outra.** Também não copiaria `rent_labels` diretamente: ele soma contas financiadas segundo pressupostos da pump.fun, podendo incluir contas transitórias numa rota Jupiter ([rent.py:109](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rent.py:109)).

O aluguel efetivamente recuperável permanece separado do PnL de negociação, conforme o [desenho:110](C:/dev/project-hunter/docs/design/spot1-lab-solana.md:110). O ensaio das 80 contas é corroborativo, não prova individual.

**2. A segunda cotação existe, mas não confirma a decisão de saída.**

A primeira marca decide o motivo ([spot_exits.py:130](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:130)). A venda chama `spot_leg` sem transmitir uma condição de stop/alvo ([spot_exits.py:279](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:279)); o primitivo recota e verifica par, quantidade e execução, sem reavaliar aquela condição ([spot_send.py:122](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:122)).

**Cenário concreto:** UNI recebe marca 0,043310, escolhe `stop`, recota perto de 0,049838 e vende mesmo que a cotação executável já não sustente o stop. Além disso, `stop` autoriza tolerância de pânico desde a primeira tentativa ([spot_exit_rules.py:111](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:111)).

Eu trataria a **revalidação da condição na cotação que será executada como correção de robustez**, com contrato explícito. Esperar várias observações ou impor paridade Binance é uma hipótese adicional de política.

No NEAR, `6001` significa slippage excedido **se emitido pelo programa Jupiter**; o código numérico isolado precisa do programa/log correspondente. Isso demonstra que aquela execução foi recusada, não prova sozinho uma cotação fantasma. [Documentação Jupiter](https://developers.jup.ag/docs/swap/v1/common-errors).

**3. Corrigir a classificação antes de apresentá-la como “causa das perdas”.**

Há três problemas:

- **`|R_decisão − R_fill| > 1R` identifica divergência**, que também pode vir de movimento verdadeiro, latência, rota ou slippage. Use a mesma base corrigida nos dois R e separe taxas. A marca usa `out_amount`, enquanto a liquidação usa o recebido líquido ([spot_exits.py:171](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:171), [spot_settle.py:68](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_settle.py:68)).
- **Lab terminal e retorno alt/SOL da janela real podem ter horários diferentes.** Um alvo anterior no Lab, seguido de queda até a saída real, pode parecer “denominação SOL” mesmo com SOL constante.
- **O R terminal do Lab pode já conter custos e funding.** Sua liquidação chama `r_net`, que os desconta ([settle.py:89](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:89), [pricing.py:59](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:59)). Lab líquido negativo não equivale necessariamente a direção USD errada.

**Cenário de falha:** classificar uma perda como `denominacao_sol`, mudar a geometria e descobrir que a diferença vinha do horário de saída.

Sobre as operações:

| Operação | Parecer |
|---|---|
| UNI 29/09 | Forte candidata a **saída disparada por marca anômala**. Não está demonstrado que todo −0,37R foi causado por ela. |
| NEAR 26/09 | `custo` pode continuar como rótulo do resultado final; registrar também **tentativa de alvo não executável**. Não comparar a marca das 04:30 com o fill das 04:45 como se fossem uma execução. |
| TAO 25/09 | Atribuição à denominação é consistente **se os retornos têm os mesmos extremos**: `1,009/1,0186 − 1 ≈ −0,94%`. |
| Quatro `sinal_errado` | Compatíveis com sua regra, mas não verificáveis individualmente sem retorno USD bruto na mesma janela e demais campos. Renomearia para `movimento_adverso`. |
| UNI 30/09 | `custo` é consistente descritivamente; −0,01R exige valores sem arredondamento e sensibilidade ao minuto de referência. |

**4. H-c precisa substituir custos existentes, não duplicá-los.**

**Cenário concreto:** aplicar −0,3R sobre `r_multiple` já líquido penaliza duas vezes parte do custo e pode conservar funding de perpétuo numa simulação spot.

Se −0,03R for bruto, descontar 0,3R × 202 resulta em **−60,63R**. Se já for líquido, é necessário reconstruir o resultado antes dos custos e reaplicar o modelo spot. “Prospectivo na emissão” também não torna a semana usada para selecionar v14 uma validação independente dessa seleção.

**NICE-TO-HAVE**

- Fechar o funil dos 44 sinais: `10 + 8 + 15 = 33`; faltam **11** se os grupos forem exclusivos e do mesmo corte.
- Publicar custos por operação. **Medianas não se somam**: 0,11R e 0,17R podem se sobrepor, conforme a definição do resíduo.
- Chamar os 32/41 bp de **custo implícito contra referência Binance**. A medida incorpora diferença entre praças, wrapper/perpétuo e resolução temporal, além de execução.
- Manter dois eixos: **incidente operacional** e **decomposição econômica**, permitindo múltiplas etiquetas.

**O QUE EU FARIA DIFERENTE**

Primeiro corrigiria o instrumento de medição. Depois proporia estes testes, sem aplicar nada:

| Proposta | Teste | Refutação |
|---|---|---|
| **H-a1: geometria alt/SOL** | Mesmos sinais e entradas; controle com geometria atual corrigida versus ATR alt/SOL. Mesma ficha, horizonte e custos. Comparar PnL em SOL e R numa referência comum, além do R próprio de cada braço. | Limite superior do IC95% da melhora abaixo do efeito mínimo pré-registrado; avaliar também se o braço é lucrativo em nível. |
| **H-a2: sinal alt/SOL** | Experimento separado: recalcular features e gatilhos na razão, incluindo os momentos em que o sinal USD não disparou. Universo e disponibilidade conhecidos em cada instante. | Mesmo critério, numa coorte futura. Melhora apenas nas dez entradas escolhidas não confirma o novo sinal. |
| **H-b: confirmação de cotação** | Reproduzir UNI com marca anômala e recotação normal; queda verdadeira persistente; alvo transitório; oracle atrasado; desancoragem real; saída por tempo/emergência. Depois comparar em sombra falsos gatilhos evitados, atraso, execução e perdas extremas. | Benefício líquido abaixo do mínimo declarado, ou violação do orçamento de atraso/perda adicional pré-definido. |
| **H-c: v14 paga o custo?** | Reprecificar todos os sinais elegíveis com custo spot por operação; usar 0,3R como cenário de sensibilidade. Separar seleção, período posterior e universo mapeado disponível à época. | Para a tese “expectância líquida positiva”, limite superior do IC95% ≤ 0. IC cruzando zero: **não confirma**. |

Cuidados específicos:

- **H-a:** razão dos fechamentos de 1m não fornece máximas/mínimas intraminuto. Pode formar barras da série amostrada, mas isso precisa ser declarado; não fabricar o OHLC da razão dividindo extremos não simultâneos. A contração de volatilidade em 1m também não determina automaticamente o ATR de 15m.
- **H-b:** um portão Binance não pode bloquear indefinidamente uma saída numa desancoragem verdadeira da representação Solana. A cotação local pode estar certa e a Binance continuar estável. Limiar, prazo e tratamento da divergência precisam estar congelados antes do teste.
- **H-c:** usar blocos temporais que preservem sinais simultâneos/sobrepostos. Dez operações, ou quatro semanas, não sustentam intervalos de confiança estreitos por reamostragem ingênua.

**O que é bug e o que é hipótese:** A é bug contábil com efeito operacional. A coerência entre cotação de decisão e execução é correção de robustez. H-a muda estratégia: a denominação SOL foi explicitamente aceita no [desenho:108](C:/dev/project-hunter/docs/design/spot1-lab-solana.md:108). Os filtros extras de H-b e a vantagem econômica de H-c são hipóteses.

**Com dez operações, não podemos concluir:**

- Que v14 tem ou não vantagem estável, nem estimar com precisão frequência de cotações anômalas, custo médio ou risco extremo.
- Que SOL prejudica sistematicamente: NEAR 27/09 mostra o efeito favorável.
- Que reduzir ATR, confirmar cotações ou retirar filtros melhorará o resultado futuro.
- Que os recusados por custo deveriam ter entrado: +3,34R no Lab não é resultado executável líquido.
- Que UNI teria sido lucrativa se mantida até 18:30: +0,56% é retorno bruto de referência, sem provar trajetória sem stop nem fill disponível.
- Que corrigir A recuperaria 0,00220336 SOL: esse valor corrige o registro. O resultado de decisões diferentes exige replay e pode melhorar ou piorar.

**CONCORDO COM**

Concordo com investigar A antes de ajustar a estratégia, usar todas as semanas em E e separar sinal, denominação e execução. O total prospectivo informado, praticamente zero antes da reprecificação adequada, retira força da narrativa baseada em R63; não prova sozinho ausência universal de vantagem.

Isso acompanha a distinção entre **não confirmar** e **refutar** da [Fila de Hipóteses](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:21>) e a cautela com seleção retrospectiva da [KB-0149](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md).

**OBSIDIAN**

Páginas que deveriam ser atualizadas; nenhuma foi alterada:

- **Mesa-spot-1** — dez operações, aluguel comprovado por assinatura, PnL corrigido e incidentes separados das causas econômicas.
- **KB-0145 — Binance como sinal, Solana como execução** — custos observados, exposição alt/SOL e limites da seleção R63.
- **Fila de Hipóteses** — H-a1, H-a2, H-b e H-c com população, efeito mínimo e refutação congelados.
- **Mapa de Estratégias / EXP da v14** — avaliação integral por coorte, distinguindo seleção e validação posterior.
- **Open Bugs** — aluguel constante nos caminhos normal/reconciliação e ausência de revalidação do gatilho.
- **Revisões-Astra — análise das dez operações spot/1** — registrar este parecer e as evidências ainda necessárias.
**RESUMO**

**Concordo com a correção limitada a `real_observado + curve_cost_sol`, sob a hipótese explícita de preservar os fluxos externos observados.** Isso corrige a omissão do aporte no modelo; não valida a trajetória contrafactual inteira nem a execução Mayhem on-chain. Minha ressalva anterior precisa dessa distinção.

**(a)** Para uma aposta isolada, ainda na curva, sem saídas anteriores, o teto contábil é:

`R_hipotético(t) = R_observado(t) + c`

desde que os demais fluxos de SOL sejam mantidos como observados. Sua prova para a curva padrão está correta sob `x = 30+r`, `xy = k₀` e compra na mesma curva: o máximo de `p−r` ocorre em `x=30` e fica abaixo de `c`. Os 23 casos informados exigem investigação das premissas e dos dados; não demonstram, sozinhos, qual invariante quebrou.

**(b)** Concordo em deixar as reservas virtuais para tarefa separada. Contudo, esta correção do teto **também muda o instrumento** e precisa de identificação de versão e corte temporal.

**(c)** Depois de implementada e verificada, fecharia especificamente **“omissão do aporte próprio no teto”**. Manteria **dois residuais abertos**: trajetória das reservas virtuais e semântica da venda Mayhem sem liquidez suficiente. Não deixaria apenas a pergunta on-chain.

**(d)** Usaria `curve_cost_sol`. Compras e vendas efetivamente observadas do agente já estão refletidas em `R_observado`; descontá-las novamente duplica a contabilização. Uma reação *contrafactual* do agente à nossa compra seria outra hipótese de modelo.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, papel `quant-engineer`.

A entrada separa aporte, taxas e gasto total em [paper_fill.py:187](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:187). As duas fronteiras de construção de `BetState` a contemplar são [lab_repo_bets.py:215](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:215) e [launch_lane_bets.py:154](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_bets.py:154).

**TESTES**

Não executei testes nem consultas à VPS. Os números novos são os que você forneceu, não uma medição independente minha.

Na implementação, exigiria testes de: foto repetida com SOL real zero; teto sobre recebimento bruto antes das taxas; mesma regra em marca e fechamento; recarga da aposta preservando `curve_cost_sol`; precedência do bit da foto; curva completa; não-Mayhem conhecida sem mudança.

**MUST-FIX**

1. **Declarar a hipótese dos fluxos externos, sem chamar o resultado de trajetória validada.**  
   Cenário ilustrativo: nossa compra acrescenta `0,07`; uma venda externa, reprecificada após nossa compra, retira `0,02` a mais que no histórico observado. A diferença de reservas passa a `0,05`, mas `R_observado+0,07` mantém `0,02` inexistente naquele contrafactual.  
   Portanto, a soma é correta para o modelo de fluxos observados preservados. Não é uma identidade universal de uma curva reexecutada com nossa intervenção. Isso não bloqueia a correção limitada proposta.

2. **Não apresentar pernas independentes como garantia de conservadorismo da posição conjunta.**  
   Cenário ilustrativo: `R=0,10`, aportes de `0,07` por perna e ambas limitadas pelo teto. Cada aposta pode receber `0,17`; juntas, `0,34`, contra `0,24` disponíveis antes das duas vendas. A primeira saída não aparece na foto observada usada pela segunda.  
   “Menos o que já tiramos = zero” vale para cada simulação isolada. Para probe+scale como posição conjunta, seria necessário compartilhar o saldo. Hoje o fechamento vende toda a aposta individual em [paper_engine.py:215](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:215). Aceito manter o escopo, mas retiraria o adjetivo “conservador” sem essa qualificação.

3. **Identificar apostas que atravessam a troca do instrumento.**  
   Cenário: uma marca antiga já disparou `max_loss`; o deploy chega antes da execução e a saída recebe o teto novo. Registrar somente o teto do `exit` faria essa aposta parecer inteiramente corrigida. O estado recarrega `high_water_x` e `exit_intent` em [lab_repo_bets.py:225](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:225).  
   Recomendo registrar versão e instante da mudança, distinguir apostas de transição e preservar intenções existentes. Não recalcular fechadas.

4. **Corrigir a justificativa falsa nos dois docstrings.**  
   A afirmação aparece em [executable.py:115](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/executable.py:115) e [curve.py:304](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:304).  
   Cenário: bit desconhecido em moeda padrão, reserva observada pequena e posição hipotética ausente da foto; o teto antigo corta a venda. “Não corta porque conhecido false desliga o teto” não prova impossibilidade matemática.

**NICE-TO-HAVE**

- Auditar `real_observed_sol`, `own_curve_sol`, `effective_cap_sol`, versão do modelo e origem do bit efetivo. Distinguir teto disponível de teto efetivamente aplicado.
- Investigar os 23 casos não-Mayhem antes de atribuí-los à quebra de `virtual−real=30`.
- Registrar a dupla cobrança como **subavaliação local da cotação**. Com gatilhos diferentes, ela não garante PnL final conservador: uma saída antecipada pode evitar uma queda posterior.

**O QUE EU FARIA DIFERENTE**

Manteria o aporte específico da aposta na camada paper, preservando a reserva observada original. A seleção atual do teto está em [lab_values.py:84](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:84).

Fecharia o defeito contábil com testes e evidência da versão implantada, sem declarar “Mayhem validado”. Se on-chain rejeitar a venda inteira quando faltar SOL, o modelo atual continuará divergindo: ele reduz o recebimento e devolve uma venda de todos os tokens em [curve.py:307](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:307). Esse é o cenário concreto do residual on-chain, ainda não comprovado.

**CONCORDO COM**

Preservar a primeira marca: ela usa `reserves_after` em [paper_fill.py:174](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:174); a reversão devolve `c` **bruto**, antes das taxas, dentro da precisão numérica. Como `R+c ≥ c`, o teto ajustado não restringiria essa marca.

Também concordo com excluir taxas do aporte, não reescrever apostas fechadas e separar a correção das virtuais. A H-032 continua **NÃO CONFIRMA — instrumento**; corrigir o código não recupera retrospectivamente seus gatilhos.

**OBSIDIAN**

- **Open Bugs / Resolved Bugs** — fechar apenas a omissão do aporte após verificação; manter os dois residuais e explicitar a independência entre apostas.
- **KB-0189 — O papel não sabe medir a moeda Mayhem** — acrescentar a validade condicional de `R+c`, os novos diagnósticos e o viés das virtuais.
- **EXP-M23 — Desfecho das recusadas** — registrar versão, corte temporal e apostas de transição, preservando avaliações anteriores.
- **Revisão da Astra — teto Mayhem** — registrar este parecer e a distinção entre correção contábil e validação da execução.
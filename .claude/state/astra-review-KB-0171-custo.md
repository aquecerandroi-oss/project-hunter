**RESUMO**

**O achado do aluguel procede pela leitura do código, condicionado aos valores on-chain informados. O método é útil como medição descritiva, mas ainda não sustenta “custo estrutural de 0,493%” nem um IC que cubra todas as fontes de incerteza.**

A revisão seguiu o papel de `quant-engineer`, com a memória da mesa Spot, KB-0145, KB-0149, Fila de Hipóteses e Mapa de Estratégias. Não reproduzi os dados: o scratchpad está fora do repositório e, portanto, fora do acesso autorizado.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes, SQL na VPS ou o script de análise. Fiz inspeção estática do código e consultei documentação oficial da Solana. Os resultados amostrais e os intervalos abaixo são os fornecidos na pergunta, não resultados reproduzidos.

**MUST-FIX**

1. **Corrigir a contabilização do aluguel antes de usar o placar como evidência.**

   A cadeia do erro está confirmada:

   - Constante de **2.039.280**: [spot_send_rules.py:27](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:27).
   - Confirmação direta atribui essa constante quando detecta criação: [spot_send.py:298](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:298).
   - Reconciliação faz o mesmo: [spot_reconcile.py:320](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:320).
   - Abertura subtrai o aluguel do débito: [spot_entry_writes.py:85](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:85); abertura tardia também: [spot_settle.py:113](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_settle.py:113).
   - Fechamento calcula recebido menos gasto: [spot_settle.py:68](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_settle.py:68).

   **Cenário:** depósito efetivo de 1.488.440, mas exclusão contábil de 2.039.280. O gasto fica **550.840 lamports menor**, e o PnL fica maior pelo mesmo valor. Quatro ocorrências produzem **0,002203360 SOL** de diferença, compatível com os totais arredondados apresentados. A alteração de ΣR exige dividir cada correção pelo risco inicial daquela posição; não validei −4,40 R sem as linhas individuais.

   **Quando 2.039.280 seria correto?** Quando esse fosse o depósito efetivamente financiado e retido: criação histórica sob o parâmetro antigo ou financiamento acima do mínimo. A fórmula oficial antiga dá `(165 + 128) × 6.960 = 2.039.280`; com 5.080, dá **1.488.440**. A documentação descreve essa redução por etapas, mas seu quadro de ativação não substitui a evidência das transações. [Solana — Reduced Rent](https://solana.com/upgrades/reduced-rent)

   Uma ATA antiga pode continuar contendo o depósito antigo. **Reutilizá-la não cria novo gasto de aluguel**, e fechá-la exige contabilizar o saldo efetivamente recuperado. Não resolveria isso apenas trocando uma constante por outra.

2. **Nomear corretamente a referência: déficit contra Binance PERP defasada.**

   O cálculo mistura taxa de pool, impacto, diferença entre representação e ativo, basis perp/spot e movimento entre referência e execução. Não identifica separadamente um “prêmio da Jupiter”.

   **Cenário:** token/SOL sobe 0,2% depois do close e a compra executa perfeitamente no preço contemporâneo. O método registra aproximadamente 0,2% de custo. Uma venda acionada após queda pode produzir viés sistemático semelhante; o drift não precisa cancelar na média.

   Usaria o nome **“déficit de execução contra o último close PERP disponível”**. Para custo de execução, acrescentaria referência contemporânea spot e, quando possível, preço marginal da pool.

   O tempo do fill deve ser o pouso on-chain, não a gravação no banco. A abertura normal grava `entry_at=now`, depois da confirmação: [spot_entry_writes.py:126](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:126). Escolher o candle pelo horário de confirmação pode incluir preço posterior à execução.

3. **Separar fechamento algébrico de validação independente e uniformizar denominadores.**

   Sim: se as parcelas e os dois PnLs derivam dos mesmos fluxos e preços, a igualdade é uma **identidade contábil**. Detecta erros de implementação, sinais ou unidades; não prova que a referência representa preço justo.

   Para lote integral `q`, preços de referência `bₑ,bₛ` em **SOL/token**, entrada bruta `I`, saída bruta `O` e taxas `F`, uma decomposição exata é:

   ```
   PnL_ref  = q × (bₛ − bₑ)
   PnL_real = O − I − F
   diferença = (I − q×bₑ) + (q×bₛ − O) + F
   ```

   Isso fixa **o mesmo lote real** no contrafactual. Comprar uma quantidade hipotética diferente com a mesma ficha é outro contrafactual.

   **Cenário:** somar seu percentual de compra, cujo denominador é `q×bₑ`, ao de venda, cujo denominador é `q×bₛ`, e declarar custo exato sobre 0,05 SOL. Com movimento relevante, os denominadores divergem. Some primeiro custos em SOL e divida por uma base comum. Os **0,493% podem continuar próximos**, mas precisam dessa definição.

4. **Delimitar a população e reamostrar posições completas.**

   Dez posições são **dez pares**, não vinte observações independentes. O bootstrap deve carregar compra, venda e taxas juntas. Operações próximas no tempo e repetidas no mesmo token podem continuar dependentes mesmo assim.

   **Cenário:** congestionamento afeta várias pernas simultaneamente; bootstrap independente das vinte pernas produz precisão excessiva. Outro: saídas demoradas ou problemáticas permanecem abertas, enquanto só fechadas entram na amostra, tornando a execução observada mais favorável.

   Para chamar de custo operacional da mesa, contabilize também tentativas que **pousaram e falharam**, além de eventuais custos separados de fechamento de contas. Transações com erro on-chain ainda pagam taxa. [Solana — Fee Structure](https://solana.com/docs/core/fees/fee-structure)

   Redação sugerida, **após confirmar o bootstrap pareado**:

   > Nas dez posições encerradas analisadas, de quatro ativos e ficha de 0,05 SOL, o custo médio estimado contra a referência PERP de 1 minuto foi 0,49% por ida-e-volta. O intervalo bootstrap pareado nominal de 95% foi [0,32%; 0,67%]. É uma estimativa exploratória, condicional à amostra; o intervalo não incorpora erro de referência, dependência temporal não modelada, seleção das posições encerradas ou mudança de regime.

   Se esses limites vieram de reamostragem por perna, recalcular antes de usar essa frase. Com poucos dias ou clusters, nenhum bootstrap recupera a diversidade que não foi observada.

**NICE-TO-HAVE**

- Publicar as dez linhas: custo em SOL, percentual sobre ficha, custo/R inicial, ativo, dia, idade da referência e criação de ATA. Acrescentar mediana, amplitude e sensibilidade retirando uma posição por vez.
- Para aluguel, verificar instruções externas **e internas**, propriedade/autoridade de recuperação e saldos anteriores/posteriores. `createAccount` sobrevivente, sozinho, não prova que o dinheiro continua sendo patrimônio recuperável da carteira.
- Na fórmula assinada, `ΔSOL + fee + depósito − recuperação` é negativo na compra: `SOL_in` é seu **oposto**; na venda, é `SOL_out`. Transferências adicionais precisam de classificação explícita.
- Confirmar que a contagem da taxa-base inclui eventuais assinaturas verificadas por precompiles; `meta.fee` continua sendo a medida primária do total. [Solana — Fee Structure](https://solana.com/docs/core/fees/fee-structure)
- Escrever “nenhuma platform fee identificada nas transações examinadas”. `platformFee=null` nas compras e ausência de destinatário que só recebe não demonstram ausência de toda remuneração embutida na rota.

**O QUE EU FARIA DIFERENTE**

Primeiro reconstruiria um ledger por assinatura, com fluxo de swap, rede, depósito recuperável e outras transferências. Conferiria o fluxo de swap contra movimentos de WSOL/pools, independentemente da fórmula residual da carteira.

Depois apresentaria três medidas separadas: **cotação→fill**, **referência contemporânea→fill** e **decisão→fill**. A proximidade entre paridade na decisão e déficit de compra é esperada se compartilham cotação e referência; não constitui validação independente.

Recalcularia custo exato em SOL por posição, percentual sobre ficha e R usando o risco inicial individual. Só então faria o bootstrap pareado e sensibilidades por dia, ativo e referência.

Sobre tamanho: com os valores informados, o limiar médio é aproximadamente **0,03309 SOL**; portanto, **0,033 SOL ainda fica ligeiramente acima de 0,15% por perna**. Com prioridade de 100.000 e uma assinatura, **0,070 SOL dá exatamente 0,15%**, não menos. São contas condicionais à taxa adotada, não recomendações de aumentar ficha.

Também substituiria “o proporcional não cai com a ficha” por **“não há evidência de diluição do proporcional nesta medição”**. Taxa percentual tende a persistir, mas impacto e rota podem mudar com o tamanho.

**CONCORDO COM**

- `meta.fee` como fonte primária; depósito recuperável separado de despesa; WSOL criada e encerrada na mesma transação sem depósito persistente.
- Slippage cotação→fill próximo de zero pode coexistir com custo total relevante: a cotação já incorpora parte do atrito.
- **0,001 SOL/perna é cerca de vinte vezes a média de rede informada**, para esta amostra.
- **0,15%/perna fica abaixo do total médio observado de aproximadamente 0,247%/perna**, nesta mesa e ficha. Isso merece uma sensibilidade adicional em R84/R85, preservando os resultados originais; não demonstra um novo custo universal para seus universos históricos.
- O bug contábil é demonstrável sem esperar uma amostra grande. A estimativa de custo futuro permanece exploratória.

**OBSIDIAN**

- **KB-0171 — Custo real da spot/1:** registrar população, referência, denominadores, bootstrap pareado e limites da reprodução.
- **KB-0145 — Binance como sinal, Solana como execução:** acrescentar medição datada das taxas e distinguir cotação de custo realizado.
- **KB-0149 — O que a mesa real ensinou:** qualificar o antigo 0,14% da Jupiter pelo escopo daquela medição.
- **Mesa-spot-1 / Open Bugs:** registrar o erro de aluguel, posições afetadas e necessidade de revisão auditável de PnL/R.
- **Revisões Astra — R84/R85:** acrescentar sensibilidade de custo específica para execução Jupiter com ficha pequena, sem reescrever os vereditos históricos.
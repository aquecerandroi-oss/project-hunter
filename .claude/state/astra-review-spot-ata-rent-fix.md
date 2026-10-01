**RESUMO**

**DONE_WITH_CONCERNS — recomendo o desenho, com ajustes antes de implementar.** Atuei como `risk-engine-guardian`, em modo OPINIÃO.

Respostas diretas: **(a)** saldo líquido é uma boa medida, desde que o financiamento pela carteira esteja comprovado; **(b)** aceito incorporar o aluguel desconhecido ao gasto como fallback conservador; **(c)** não exigiria mudar a simulação nesta correção; **(d)** preservaria os fills históricos das posições fechadas; **(e)** não precisa reiniciar apenas para atualizar a pista: ela relê o banco antes de buscar novas entradas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes nem consultas ao banco/RPC da carteira. Fiz inspeção estática e consultei documentação e código oficiais da Solana. Os números históricos permanecem os relatados na KB-0171, não reproduzidos nesta revisão.

**MUST-FIX**

1. **Script: usar a quantidade histórica, não `spot_positions.tokens`.**

   O fechamento zera `tokens`: [spot_repo_positions.py:104](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:104). A quantidade original está em `entry.filled_atoms`: [spot_entry_writes.py:116](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:116).

   **Cenário:** validar o delta de tokens contra a coluna da posição recusa todas as compras fechadas; usá-la em `entry_sol_per_atom` divide por zero.

   Especificar expressamente:
   - quantidade positiva obtida de `entry.filled_atoms`, conferida com o fill da ordem e a transação;
   - preço recalculado com essa quantidade;
   - `initial_risk_sol` original preservado; `R = pnl_corrigido / initial_risk_sol`.

2. **Não confiar no aluguel de um fill legado ao recuperar uma compra órfã.**

   O reconciliador recupera ordens confirmadas sem posição usando diretamente `row.fill`: [spot_reconcile.py:98](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:98). Esses fills podem conter a constante antiga, gravada em [spot_send.py:298](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:298).

   **Cenário:** processo cai depois de confirmar a ordem e antes de abrir a posição. Após o deploy, `open_from_order` recebe o aluguel antigo e recria o gasto otimista, mesmo com os dois produtores novos corrigidos.

   Acrescentaria proveniência/versionamento do aluguel nos fills novos. Fill legado sem essa evidência exige releitura da transação; se indisponível, usar o fallback desconhecido.

3. **O contrato de extração precisa distinguir saldo retido de financiamento pela carteira.**

   O verificador já exige carteira como pagadora e proprietária das instruções ATA externas: [spot_verify.py:148](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:148). Porém `fill_from_transaction` só verifica a carteira como *fee payer*: [spot_send_rules.py:154](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:154).

   **Cenário:** uma conta recebe depósito de outro financiador dentro da transação; subtrair esse aumento do débito da carteira reduz artificialmente o gasto. Ser dona da conta e pagar a taxa da transação não prova ter pago o depósito.

   Eu aceitaria a extração proposta para contas vinculadas à criação verificada, financiada pela carteira. Conta adicional sem essa prova → `None`. No script histórico, reproduzir essa validação; conferir apenas os deltas não resolve a atribuição.

4. **A atomicidade precisa incluir conflitos de atualização.**

   Para o script proposto, exigir `RETURNING id`/exatamente uma linha atualizada e rollback de **todo o lote** se alguma guarda falhar. Revalidar os dados usados no cálculo sob bloqueio das linhas, ou comparar uma versão completa do estado lido.

   **Cenário:** outra correção altera `rent`, `entry` ou `params`, mantendo o mesmo `sol_spent_lamports`; a guarda proposta passa e permite sobrescrever informação concorrente. Outra possibilidade: uma posição falha na guarda e as anteriores ficam gravadas se a falha não provocar rollback.

   “Already correct” deve comparar o conjunto contábil completo, não apenas `spent` ou a existência de `rent_correction`.

**NICE-TO-HAVE**

- Fixtures para ATA nova/reutilizada, duas contas do mesmo mint, índice carregado por ALT, pré-financiamento parcial/integral, WSOL transitória, metadados inválidos e recuperação de fill legado.
- Teste transacional: falha na última posição deixa **zero updates e zero auditorias**; segunda execução não cria auditoria extra.
- UUID completo na auditoria. Aceitar `id8` na nota somente se identificar inequivocamente o alvo.
- No dry-run, mostrar também as somas e os piores prefixos usados na refutação; a consulta calcula ambos: [spot_repo_positions.py:110](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:110).

**O QUE EU FARIA DIFERENTE**

**a) Delta de saldo versus `createAccount`.**

Preferiria **delta líquido com prova de financiamento**, sem depender exclusivamente de `createAccount`:

- **ATA parcialmente pré-financiada:** `post − pre` captura o complemento pago nesta transação. O programa ATA usa `transfer + allocate + assign` nesse caso; pode não haver `createAccount`.
- **Integralmente pré-financiada:** delta zero pode ser legítimo. Portanto, `delta <= 0 → None` é conservador, mas classifica um zero conhecido como desconhecido. Aceitaria zero quando a inicialização sem aporte estiver comprovada; negativo permanece anomalia. [Implementação oficial de criação](https://raw.githubusercontent.com/solana-program/associated-token-account/main/program/src/tools/account.rs)
- **Token-2022:** extensões alteram o tamanho necessário. O delta evita presumir 165 bytes, mas **2.039.280 não é teto universal**. O programa calcula o tamanho conforme as extensões. [Processador ATA](https://raw.githubusercontent.com/solana-program/associated-token-account/main/program/src/processor.rs)
- **WSOL persistente:** saldo em lamports inclui principal encapsulado e reserva; não pode ser todo tratado como aluguel. WSOL criada e fechada na mesma transação não deixa depósito retido. [Solana — Sync Native](https://solana.com/docs/tokens/basics/sync-native)

A comparação por `accountIndex` é correta. Compare com os índices de **toda** a lista anterior, evitando confundir mudança de proprietário com criação. Valide inteiro não booleano, não negativo, dentro de ambos os vetores e sem duplicatas. Para resolver endereços em `json`, use estáticas + carregadas graváveis + carregadas somente leitura; não concatene saldos novamente. [Estruturas RPC](https://solana.com/docs/rpc/json-structures)

**b) Aluguel desconhecido incorporado ao gasto.**

Aceito:

```text
delta < 0, rent desconhecido:
spent = -delta
rent contabilmente separado = 0
source = signature_delta_rent_unknown
```

Isso **incorpora** o aluguel ao gasto; não o cobra duas vezes. Preserve `None` até a função comum: hoje o reconciliador converte ausente/nulo em zero com `or 0`, perdendo essa distinção: [spot_settle.py:113](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_settle.py:113). `LegResult` também precisa carregar o opcional, hoje declarado `int`: [spot_send_rules.py:51](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:51).

**Ressalva operacional:** isso pode antecipar stop. `r_now` usa o gasto da posição: [spot_exit_rules.py:63](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:63). É uma degradação conservadora, não só uma mudança de placar. Manter posição e saídas gerenciadas é preferível a abandoná-la; registrar a anomalia persistentemente e permitir reparo posterior.

Concordo em evitar PnL nulo: as somas atuais o omitiriam, embora a posição continuasse na contagem: [spot_repo_positions.py:111](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:111). A função pura retorna o motivo; os chamadores fazem o log.

**c) Teto da simulação.**

Não faria da leitura dinâmica uma condição desta correção. O teto atual é uma **tolerância máxima**, não despesa medida: [spot_send_rules.py:78](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:78).

Com os valores informados, sobram 550.840 lamports por ATA efetivamente criada e retida. Isso enfraquece a checagem pelo mesmo valor. Para apertá-la depois, use evidência independente do depósito; **não derive a tolerância do próprio débito total que está tentando limitar**.

Manter `limits.ata_rent_sol` conservador faz sentido no escopo atual: ele reduz o saldo disponível para sizing em [spot_profile.py:259](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/spot_profile.py:259). Documentaria que não garante cobertura de qualquer extensão Token-2022.

**d) Corrigir `spot_orders.fill`?**

**Não sobrescreveria o fill histórico das posições já fechadas.** Manteria a correção na posição e no audit log, identificando claramente o fill como registro original. A exceção necessária é o tratamento dos fills legados ainda usados para recuperar posições, descrito acima.

**e) Reiniciar depois do `--apply`?**

**Não por causa de `stats.lane`.** O loop relê `closed_stats`, recalcula a pista e recusa antes de buscar candidatos: [spot_entries.py:86](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:86).

Quando desabilitado, esse loop retorna antes da leitura: [spot_entries.py:69](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:69). O heartbeat pode permanecer defasado; um refresh explícito basta para apresentação. Uma entrada já em andamento quando o script confirma continua sendo uma questão de coordenação operacional — reiniciar depois não elimina essa janela.

**CONCORDO COM**

- Uma função comum para abertura direta, reconciliação e reparo.
- Contabilidade baseada na transação, separada da reserva conservadora.
- Dry-run padrão, nota por alvo, auditoria e atualização na mesma transação.
- Pular abertas neste script, mas reportar pendência se houver alguma; “hoje zero” precisa ser confirmado na execução.
- Preservar risco inicial e geometria histórica.

**OBSIDIAN**

- **Open Bugs:** registrar os critérios de correção, incluindo recuperação de fills legados.
- **KB-0171 — Custo real da spot/1:** documentar depósito efetivamente financiado, proveniência e fallback desconhecido.
- **Mesa-spot-1 / Perdas-spot-1:** acrescentar resultado auditado do reparo e eventuais abertas pendentes.
- **Revisões Astra — correção do aluguel ATA:** guardar este parecer e a matriz de testes.
- **Spot — README:** documentar que a refutação relê o banco a cada tick de entradas e dispensa reinício para absorver a correção.
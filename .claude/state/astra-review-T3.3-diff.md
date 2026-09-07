**RESUMO**

**REQUEST_CHANGES**, como `code-reviewer`. A fórmula de caixa é adequada ao SPOT/USDT, mas não fecha sozinha o aceite de reconciliação por fill. Encontrei quatro correções necessárias: taxa em ativo-base no relato, custo de saída no risco, corte temporal da decomposição e validação do FX da curva.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Revisei os arquivos informados e consultei os contratos e modelos relacionados.

**TESTES**

Não executei pytest, migrações ou ferramentas que produzam arquivos. Os **559/22 testes aprovados são resultados informados por você**, não revalidados nesta rodada.

Conferi três cenários aritméticos em memória, com inteiros exatos:

```text
Taxa em base:       variação do patrimônio = -1; relato = 0
Referência tardia:  variação do patrimônio =  0; relato = -2
Risco com custos:   informado = 200; com custos = 202; teto = 200
```

Isso verifica os contraexemplos, não substitui executar o código e o PostgreSQL.

**MUST-FIX**

**A — HIGH: caixa correto não implica reconciliação de quantidade, taxas e PnL.**

Não identifiquei fill legítimo perdido ou multiplicado **pelo join** de [repositories/ledger.py:160](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/ledger.py:160): a FK composta vincula fill à ordem na mesma organização/carteira, e a chave de execução impede repetir a mesma execução. [execution_fills.py:61](C:/dev/project-hunter/packages/core/hunter_core/db/models/execution_fills.py:61)

Porém, `daily_costs` ignora taxas fora de USDT, enquanto o não realizado usa quantidade líquida vezes diferença de preços. [repositories/ledger.py:202](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/ledger.py:202), [portfolio/ledger.py:85](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:85)

**Cenário:** compra bruta de 1 unidade por 100 USDT, taxa de 0,01 unidade, posição líquida de 0,99, entrada e marca em 100. Caixa cai 100; posição vale 99; patrimônio perde 1. Entretanto, realizado, não realizado e custos relatados são zero. Esse tipo de taxa já é produzido pela compra paper. [paper.py:121](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:121)

**Correção:** fechar agora a convenção de quantidade líquida, preço médio e custo atribuído por fill com a T3.5. O equivalente da taxa em base pode compor o relato de despesas, **sem novo débito no caixa**. Não aceitar a T3.3 apenas com a soma de caixa: o aceite exige reconciliação por fill. [M3.md:159](C:/dev/project-hunter/docs/plans/M3.md:159)

**B — HIGH: risco com stop subestimado.**

Concordo com **notional inteiro quando falta stop**, como fallback conservador para SPOT comprado. Pode bloquear entradas; isso é coerente com perda desconhecida e não justifica liberar orçamento.

Discordo da omissão de custos quando existe stop: [portfolio/ledger.py:100](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:100) entrega apenas distância até o stop, mas o campo consumido promete perda remanescente **incluindo custos**. [exposure.py:72](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:72)

**Cenário:** patrimônio 20.000, teto agregado 200. Posições existentes comprometem 190 pela distância e mais 2 de saída. Uma candidata acrescenta 10. O agregado informado fecha em 200; o correto é 202.

**Correção:** usar hipótese explícita e própria da posição para custos remanescentes, incluindo execução da saída. Não cobrar novamente taxa de entrada já realizada, nem usar custos da próxima candidata. A T3.5 pode persistir a hipótese, mas **o contrato desta entrega precisa ser corrigido agora**; uma pendência nas notas não impede subdimensionamento.

**C — MEDIUM: a decomposição mistura cortes temporais.**

Concordo com `state=None` quando a referência pertence a outro dia. O retorno está correto em [state.py:172](C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:172). Não reconstruiria referência usando automaticamente o primeiro preço após restart. A saída deve consumir a posição independentemente desse estado, como permite [evaluate.py:197](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:197). A garantia operacional ainda depende dessa integração.

O problema restante está em [state.py:312](C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:312): não realizado vem do instante observado, mas realizados e taxas começam em `day_start`.

**Cenário:** taxa de 2 USDT às 00:00:00,5; referência efetivamente amostrada às 00:00:01 já incorpora essa despesa. Sem movimentos posteriores, a variação contra a referência é zero, mas o relato subtrai os mesmos 2 novamente. A política em desenvolvimento admite referência dentro da cadência da virada. [daily.py:128](C:/dev/project-hunter/packages/core/hunter_core/risk/daily.py:128)

**Correção:** todos os componentes devem compartilhar o corte contábil da referência, inclusive a regra de inclusão dos fills naquele instante. Se a referência representa meia-noite reconstruída, preservar esse corte explicitamente; se representa a amostragem posterior, não recontar movimentos já incorporados nela.

**D — HIGH: a curva aceita FX impróprio e até futuro.**

Concordo em sempre preservar o ponto USDT. Discordo de converter qualquer observação recebida: [portfolio/ledger.py:165](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:165) grava o ID e [portfolio/ledger.py:174](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:174) usa a taxa sem verificar par, fonte ou disponibilidade no instante do ponto.

**Cenário:** reconstrução do ponto das 10h recebe uma observação disponível apenas às 11h. O resultado BRL incorpora informação futura e não apresenta indisponibilidade. Uma observação de outro par também chega ao mesmo cálculo.

Mesmo usando `latest_available`, uma cotação antiga continua elegível porque a consulta só limita o futuro. [fx.py:50](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/fx.py:50)

**Correção:** validar FX contra `build.as_of`, com política explícita de par, fonte, causalidade e idade. FX inválido deve produzir **USDT gravado, BRL indisponível e motivo específico**. Proveniência não substitui validade.

**NICE-TO-HAVE**

**E — exploraria primeiro o limite da varredura.** Uma chamada direta a `create_wallet` em `apps/api` ou `services` não é examinada: `_modules()` percorre somente `hunter_core`. [test_no_funding_route.py:48](C:/dev/project-hunter/packages/core/tests/unit/portfolio/test_no_funding_route.py:48)

Dentro do pacote também escapam:

- Alias: `writer = repo.create_wallet; await writer(...)`; o teste reconhece apenas chamadas por atributo. [linha 62](C:/dev/project-hunter/packages/core/tests/unit/portfolio/test_no_funding_route.py:62)
- Atribuição `wallet.initial_capital = valor` ou SQL textual; a busca examina somente argumentos nomeados. [linha 75](C:/dev/project-hunter/packages/core/tests/unit/portfolio/test_no_funding_route.py:75)
- Função proibida em submódulo não reexportado; o teste consulta apenas `dir(portfolio)`. [linha 88](C:/dev/project-hunter/packages/core/tests/unit/portfolio/test_no_funding_route.py:88)

Isso demonstra lacunas do teste, **não uma rota de aporte existente**. Eu ampliaria a cobertura dos chamadores e corrigiria a descrição da garantia, mantendo testes comportamentais e restrições do banco como defesa principal.

**O QUE EU FARIA DIFERENTE**

Fecharia com a T3.5 um contrato único por fill: quantidade bruta/líquida, efeito no caixa, taxa e sua atribuição, realizado parcial e corte contábil. Validaria compra com taxa em base, duas saídas parciais atravessando a virada e replay da mesma execução.

**CONCORDO COM**

Mantêm-se corretas as correções anteriores: arredondamento do residual, busca exata da referência com resolução definida, três relatos em `None` sem vínculo e dois limites de idade na abertura. [attribution.py:176](C:/dev/project-hunter/packages/core/hunter_core/portfolio/attribution.py:176), [equity.py:98](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/equity.py:98), [state.py:194](C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:194), [opening.py:155](C:/dev/project-hunter/packages/core/hunter_core/portfolio/opening.py:155)

**OBSIDIAN**

- **Portfolio** — registrar convenção por fill, taxa em base, corte da decomposição e validade do FX da curva.
- **Risk Engine** — documentar custos remanescentes por posição e fallback conservador sem stop.
- **Execution Engine** — explicitar o contrato da T3.5 para fills parciais e saída independente da referência diária.
- **Revisoes-Astra/T3.3-ledger** — guardar este parecer e os quatro contraexemplos, ligado a **Dialogos/M3**.
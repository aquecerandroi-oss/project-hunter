**RESUMO**

Parecer como `risk-engine-guardian`: **(1) concordo, corrigindo a prova; (2) não considero `último ts <= referência` suficiente; (3) recomendo 300 s para disponibilidade e 600 s para observação; (4) escolho (a), com dependência e lockfile explícitos na integração.**

**1. Arredondamento: manter `floor_10dp_v1`, com o algoritmo completo versionado.**

O CHECK exige igualdade **após arredondamento**, conforme [paper_wallet.py:62](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_wallet.py:62). O PostgreSQL arredonda empates de `numeric` para longe de zero. [Documentação PostgreSQL 16](https://www.postgresql.org/docs/16/datatype-numeric.html).

A prova correta usa a **fração descartada do resíduo**, não o resíduo inteiro:

```text
q = 1e-10
O = origin_amount armazenável, positivo
C = floor10(O / F)
d = O − C·F
L = floor10(d)
ε = d − L                  # 0 ≤ ε < q
```

- Com `L`, a soma é `O − ε`: fecha quando **ε ≤ q/2**.
- Se **ε > q/2**, usar `U = ceil10(d)` dá `O + (q − ε)`: fecha porque `0 < q − ε < q/2`.
- No empate **ε = q/2**, escolher **floor**: a soma inferior arredonda para `O`; a superior arredondaria para `O + q`.

Portanto, **sempre existe candidato**, sob essas premissas e com aritmética exata. A afirmação “floor cobre `d ≤ 5e-11` e ceil o resto” está errada quando `d` contém unidades inteiras de `q`.

Exemplo sintético relevante para a abertura:

```text
origin   = 100000
rate     = 3.5
credited = 28571.4285714285
d        = 0.00000000025

floor10(d) = 0.0000000002 → CHECK fecha
ceil10(d)  = 0.0000000003 → CHECK fica 1 ulp acima
```

O limite do erro é até **mais forte** que o proposto: resíduo armazenado menos resíduo exato pertence a **[−5e-11, +5e-11)** BRL.

Manteria o nome, deixando explícito que `floor_10dp_v1` determina o crédito e inclui essa regra de reconciliação do resíduo. Calcule sobre valores já representáveis em `NUMERIC(28,10)`; não permita arredondamento intermediário do contexto `Decimal`. Para o crédito, divisão inteira dos coeficientes escalados evita arredondar o quociente antes do floor. Overflow ou crédito zero ainda podem impedir a abertura; isso é distinto da existência de um residual que satisfaça o CHECK.

**2. Não realizado inicial: concordo com o delta e com `None`; rejeito o predecessor sem vínculo.**

Alimentar `daily_unrealized_pnl = U_agora − U_referência` combina com a fórmula implementada em [exposure.py:171](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:171). Os custos precisam ser descontados uma vez, com os componentes brutos de custos, conforme [exposure.py:121](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:121).

Entretanto, **`ts <= day_reference_observed_at` prova ordem temporal, não identidade contábil**.

Cenário: último snapshot às 23:59 tem não realizado 8; a referência diária usa equity marcada à meia-noite, com não realizado 10. A posição, comprada por 100, é vendida hoje por 110. Sem custos, o patrimônio não variou no dia, mas sua busca produz `10 + 0 − 8 = 2` de resultado diário.

Minha política provisória:

- Gravar **equity e não realizado da referência a partir do mesmo estado**, sob o mesmo lock e na mesma transação.
- Fixar a resolução consultada: a chave do snapshot inclui `resolution`, além de carteira e `ts`; ordenar somente por `ts` deixa empate possível. [portfolios.py:151](C:/dev/project-hunter/packages/core/hunter_core/db/models/portfolios.py:151)
- Recuperar o snapshot comprovadamente associado à referência. A igualdade do timestamp ajuda apenas se ele representar o instante efetivo do estado, sem truncamento nem sobrescrita posterior.
- Sem esse vínculo comprovável, retornar os três relatos como `None`, com motivo fora do `PortfolioState`. Não usar automaticamente o predecessor.

O snapshot de abertura é correto e deve integrar a transação de abertura, mas não resolve as viradas seguintes. A retenção também importa: o modelo declara 30 dias para 1m e permanência para 1h; **um agregado horário não substitui necessariamente a observação original**. [portfolios.py:132](C:/dev/project-hunter/packages/core/hunter_core/db/models/portfolios.py:132)

Não exigiria outra fonte para liberar esta entrega com relato indisponível. Para garantir reconciliação durável, pediria `unrealized_day_start` à T3.1/T3.6, persistido junto de equity, corte temporal e convenção contábil. O corte dos realizados e custos também precisa coincidir com o da referência.

Distinguir duas falhas: **falta apenas de `U_inicial` → relato indisponível; falta da referência de equity → entradas indisponíveis, proteções preservadas**, como determina [RISK_ENGINE.md:285](C:/dev/project-hunter/docs/RISK_ENGINE.md:285).

**3. FX: recomendo dois limites explícitos.**

Aceitaria como política inicial:

```text
observed_at ≤ available_at ≤ as_of
as_of − available_at ≤ 300 s
as_of − observed_at  ≤ 600 s
```

São limites operacionais propostos, não uma validade ótima demonstrada. O primeiro mede disponibilidade recente; o segundo impede que um backfill recém-recebido transforme cotação antiga em cotação fresca. A distinção entre os carimbos está em [fx.py:11](C:/dev/project-hunter/packages/core/hunter_core/db/models/fx.py:11), e `observed_at <= available_at` já aparece no CHECK em [fx.py:43](C:/dev/project-hunter/packages/core/hunter_core/db/models/fx.py:43).

Mantenha as recusas propostas, acrescente números **finitos** e parâmetros de idade positivos. Par e fonte esperados devem vir da política confiável do serviço: comparar duas strings controladas pelo solicitante não autentica uma fonte. O plano identifica `USDTBRL` via REST público da Binance em [M3.md:64](C:/dev/project-hunter/docs/plans/M3.md:64).

Use o corte da tentativa efetiva de abertura. Se houver espera relevante antes do efeito, revalide usando esse corte atualizado e a observação persistida, sem rede sob lock.

**4. Dependência: entre as três, escolho (a), como concessão explícita ao brief.**

A dependência inversa já existe em [risk-core/pyproject.toml:9](C:/dev/project-hunter/packages/risk-core/pyproject.toml:9), inclusive com imports concretos de tipos do core em [inputs.py:28](C:/dev/project-hunter/packages/risk-core/hunter_risk/inputs.py:28). O core não declara `hunter-risk` em [core/pyproject.toml:9](C:/dev/project-hunter/packages/core/pyproject.toml:9).

**Ciclo de dependências de distribuição não implica necessariamente ciclo de inicialização de módulos.** Manteria a montagem em `portfolio/state.py`, sem reexportá-la pelos módulos básicos que `hunter_risk` importa. Não escolheria dependência oculta.

Há uma incompatibilidade de escopo concreta: `packages/core/pyproject.toml` e `uv.lock` não pertencem à lista de arquivos da T3.3 em [M3.md:56](C:/dev/project-hunter/docs/plans/M3.md:56). Portanto, o orquestrador precisa incluir esses arquivos ou assumir uma tarefa de integração. **Sem isso, não declararia a entrega integrável.**

Quanto ao Docker:

- A imagem já copia os manifests e fontes dos dois pacotes. [Dockerfile.api-workers:27](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:27), [Dockerfile.api-workers:43](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:43)
- Os dois passos usam `uv sync --all-packages --frozen`. [Dockerfile.api-workers:40](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:40), [Dockerfile.api-workers:54](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:54)
- **Manifest e lockfile precisam acompanhar a mudança.** `--frozen` usa o lock existente sem verificar sua atualização; um build verde sozinho não prova coerência entre os dois. [Documentação uv](https://docs.astral.sh/uv/concepts/projects/sync/)

Não identifiquei necessidade de novo `COPY`. Falta executar resolução, build e imports nas duas ordens para validar a mudança proposta.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Executei uma verificação em memória, com `BigInt` e aritmética inteira escalada, emulando o arredondamento positivo do PostgreSQL:

```text
checked: 100001
failures: 0
```

O exemplo `100000 / 3.5` confirmou floor aceito e ceil uma unidade acima. **Não executei PostgreSQL, pytest, resolução uv nem build Docker**; a verificação aritmética não substitui o teste de INSERT real.

**MUST-FIX**

- Corrigir a prova do residual: no exemplo acima, decidir pelo valor inteiro de `d` selecionaria ceil e recusaria a abertura.
- Vincular o não realizado à mesma referência de equity: o predecessor pode fabricar divergência diária de 2 USDT no cenário descrito.
- Limitar também `observed_at`: uma cotação antiga recém-recebida passa pela validade baseada apenas em disponibilidade.
- Integrar manifest e lockfile: instalar apenas o core com o contrato atual não garante a presença do pacote que o novo construtor importará.

**NICE-TO-HAVE**

Registrar na auditoria as duas idades do FX, seus limites e a versão da política; distinguir os motivos de ausência da decomposição diária.

**O QUE EU FARIA DIFERENTE**

Com liberdade arquitetural, escolheria **(c)**: o consumidor monta `PortfolioState` a partir dos dados do ledger. Isso preserva a direção `risk → core`. Sob o brief atual, prefiro **(a) explícita**.

**CONCORDO COM**

Crédito por floor, residual auditável, delta diário de não realizado, ausência representada por `None`, snapshot inicial atômico e preservação das proteções quando a referência diária estiver indisponível.

**OBSIDIAN**

- **Portfolio** — registrar `floor_10dp_v1`, prova do residual e vínculo entre snapshot e referência diária.
- **Risk Engine** — esclarecer que `daily_unrealized_pnl` recebe a variação e documentar as duas classes de indisponibilidade.
- **Infrastructure** — registrar a dependência circular proposta e a validação conjunta de manifest, lockfile e imagem.
- **Revisoes-Astra/T3.3-politicas** — guardar este parecer e os cenários que devem virar testes, ligado a **Dialogos/M3**.
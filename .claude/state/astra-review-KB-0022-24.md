**RESUMO**

Revisão como `quant-engineer`: **as três notas precisam de correções de alcance; a KB-0022 também descreve incorretamente o teste da fonte.**

**(1) Funding pode disparar; OI não?** **Sim, como possibilidade do código, com ressalvas.**

- `FUNDING_ANOMALY` usa `funding_rate`, bilateralmente; `OPEN_INTEREST_SPIKE` usa `open_interest_change_1h`, somente para cima ([detectors.py:170](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:170)).
- A primeira feature lê apenas o snapshot; a segunda exige histórico e referência temporal válida ([deriv.py:74](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:74), [deriv.py:105](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:105)).
- O scanner inicializa `deriv_history` vazio e consulta esse dicionário; encontrei o carregador, mas nenhuma chamada nem alimentação no código pesquisado ([scanner.py:78](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:78), [scanner.py:137](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:137), [repo.py:66](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:66)).

Entretanto, **snapshot suficiente para calcular a feature não significa suficiente para disparar a anomalia**: faltando baseline utilizável, retorna `unknown`; MAD zero com valor diferente também impede avaliação ([evaluation.py:180](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:180), [severity.py:113](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:113)). Não confirmei disparos em produção.

**(2) A extremidade migra para frequência?** **A mudança operacional está documentada; essa interpretação extrapola.** A Binance muda de 8h/4h para 1h quando o funding **liquidado** alcança teto/piso; tocar o limite durante a estimativa não basta. A reversão ocorre no 17º ciclo após 16 ciclos com `|funding| ≤ 0,025%`. Isso permite permanecer em 1h mesmo após a pressão diminuir. A fórmula também depende do intervalo: maior frequência não implica automaticamente maior custo realizado. São **3 ou 6 cobranças diárias passando a 24**, não oito. Fonte: [Binance, §§7–8](https://www.binance.com/en/support/faq/detail/360033525031).

**(3) OI é simétrico?** **Sim, inclusive sua variação.** Na contabilidade de contratos: duas aberturas aumentam OI; dois encerramentos diminuem; abertura contra encerramento apenas transfere posição. Nenhum caso identifica o agressor. Essa interpretação decorre da definição de contratos abertos, contando apenas um lado ([CME](https://www.cmegroup.com/market-data/volume-open-interest/about.html)).

Mas **simetria não implica ausência de informação preditiva**. ΔOI distingue expansão de contração das posições; sua associação com retornos pode ser direcional dependendo do mercado e contexto. Hong–Yogo encontram justamente previsibilidade empírica, sem quebrar aquela identidade ([NBER](https://www.nber.org/papers/w16712)). Volume agressor identifica a iniciativa da negociação, mas sozinho não distingue abertura de long de fechamento de short.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executei testes nem consultas de produção. Inspeção estática e fontes primárias.

Comando: `rg -n --glob '*.py' 'deriv_history|load_deriv_history' services/scanner-worker`. Saída relevante:

```text
repo.py:40:    "load_deriv_history",
repo.py:66:async def load_deriv_history(
scanner.py:78:    deriv_history: dict[UUID, list[DerivObservation]] = field(
scanner.py:137:            deriv_history=self.deriv_history.get(market.ref.market_id, []),
```

**MUST-FIX**

- **KB-0022 — retirar a generalização do resultado negativo** ([nota:21](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca.md:21)). A análise temporal apresentada é de **BTC, variação do funding e janelas semanais**; top 50 pertence ao alfa transversal. Retirar “estatisticamente detectável” do resultado futuro: o autor relata p-valor grande. Corrigir “neutralizado por setor”: a fórmula usa `IndClass.universe`. O estudo não testa diretamente nível atual de funding → retorno em 4h. **Falha concreta:** descartar essa hipótese com base num teste de outra variável, universo e horizonte. [Presto](https://www.prestolabs.io/research/can-funding-rate-predict-price-change).

- **KB-0023 — retirar “a pressão continua a crescer”, “a variável passa a ser frequência” e a equivalência entre detector e extremo absoluto** ([nota:34](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida.md:34)). O detector mede distância da mediana: funding positivo muito abaixo de uma mediana positiva pode disparar bilateralmente ([severity.py:107](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:107)). **Falhas concretas:** classificar recuperação ainda em cadência horária como pressão crescente; tratar funding positivo anormalmente baixo como excesso comprador. Retirar também “ninguém nunca contou” sem consulta que sustente essa afirmação.

- **KB-0024 — retirar “OI alto é profundidade” como identidade e “descartado de uma vez” após controlar agressão** ([nota:34](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0024-open-interest-como-posicionamento-evidencia-e-folclore.md:34), [nota:80](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0024-open-interest-como-posicionamento-evidencia-e-folclore.md:80)). O estudo sustenta associação compatível com profundidade naquele recorte ([artigo](https://doi.org/10.2307/2331149)). **Falhas concretas:** presumir livro profundo numa altcoin com OI elevado; rejeitar informação compartilhada ou mediada pela agressão porque seu coeficiente condicional desapareceu.

**NICE-TO-HAVE**

Retirar números não conferidos: carry negativo em 2025 na KB-0022 e 0,73% mensal na KB-0024. Trocar universais sobre ausência de testes por “não localizado nas fontes consultadas”.

**O QUE EU FARIA DIFERENTE**

Separaria nível, variação, desvio da baseline, limite vigente e intervalo. Diagnósticos exploratórios também consomem multiplicidade; não são tentativas gratuitas.

**CONCORDO COM**

Diagnóstico antes de estratégia, controles comparáveis, custos explícitos e nenhuma transferência automática de resultados tradicionais para perpétuos intradiários.

**OBSIDIAN**

- **KB-0022:** corrigir variável, universo, significância e alcance da evidência.
- **KB-0023:** separar cadência documentada, intensidade hipotética e elegibilidade do detector.
- **KB-0024:** preservar simetria sem negar previsibilidade condicional; limitar conclusões de profundidade e refutação.
- **Features / Anomalies:** atualizar o estado do scanner e distinguir disponibilidade da feature de capacidade operacional de disparo.
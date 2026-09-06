**RESUMO**

Astra, como `quant-engineer`: a preocupação com seleção é válida, mas a KB-0026 confunde **grade inferida com liquidação real**. A KB-0025 também precisa restringir algumas conclusões sobre o detector e as fontes.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executei testes nem SQL. Revisão estática do código, das avaliações publicadas e das fontes originais; os cenários abaixo são contraprovas lógicas, não resultados executados.

**MUST-FIX**

1. **KB-0026: a afirmação central só vale para atravessamento inferido.** Não existe caminho para `funding_missing` sem um instante previsto dentro de `(entry_ts, exit_ts]`. Porém, esse instante pode ser fictício: `_cadence()` estima a grade; não consulta o calendário efetivo da exchange ([funding.py:68](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:68), [funding.py:126](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:126)).

   **Cenário:** histórico horário até 04:00; mudança para quatro horas, próxima cobrança às 08:00; acompanhamento 04:30–05:30. A moda ainda horária prevê 05:00 e produz `funding_missing`, embora nenhuma liquidação real tenha sido atravessada. Portanto, retirar “todo excluído é atravessador” sem qualificação. “Zero de 173” tampouco é tautologia: atravessadores com histórico completo podem ser resolvidos. `funding_ambiguous_exit` também não comprova pagamento: a saída pode anteceder a cobrança ([funding.py:107](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:107)).

2. **Tabela: útil como inventário exploratório, inadequada como taxa ou limite inferior.** As ressalvas permitem preservar as contagens separadas; não sustentam “≥ aproximadamente” nem a duração inferida de uma hora. Além disso, **394 + 46 = 440**, não 449: os nove já pertencem aos 394. A aritmética condicional seria 27/200 = 13,5% e 55/440 = 12,5%, ainda sem denominador validado.

   **Cenário:** interpretar exclusões por grade fictícia como atravessamentos reais infla o numerador; misturar estados/coortes altera a base. Retirar taxas e inferência de duração até reconciliar a população por SQL.

3. **Cadência: risco plausível, encadeamento causal forte demais.** A Binance confirma 8h/4h→1h ao atingir teto/piso e reversão após 16 ciclos com `|funding| ≤ 0,025%`. [Documentação, §8](https://www.binance.com/en/support/faq/detail/360033525031).

   Entretanto, **8h→1h, com horários alinhados e histórico completo, não produz automaticamente `funding_missing`**: a função une grade prevista e eventos observados ([funding.py:122](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:122)). A reversão 1h→4h permite o cenário do item 1. Correlação das exclusões com funding extremo continua hipótese, não consequência demonstrada.

   **Subestimação silenciosa existe com uma condição adicional:** falta uma cobrança que a grade errada também não prevê. Exemplo: moda 8h, última observação 08:00, cobrança real positiva às 09:00 ausente, acompanhamento 08:30–09:30: retorna zero ([funding.py:129](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:129)). Se a linha estiver presente, será incluída. Retirar também a “refutação” por intervalo inferido constante: uma moda persistentemente errada pode permanecer constante.

4. **KB-0025: `UP` é acima da mediana, não necessariamente crescimento absoluto.** A declaração está corretamente identificada ([detectors.py:170](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:170)), mas o cálculo usa `(valor − mediana)/MAD` ([severity.py:107](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:107)).

   **Cenário:** mediana −10%, valor −5%, MAD 1 ponto percentual: desvio +5 MADs, apesar da queda de OI. Reformular como “ignora desvios negativos em relação à baseline”. Retirar “bilateral dobra os disparos”: sem extremos inferiores, não acrescenta nenhum.

5. **Fontes: retirar extrapolações que podem orientar pesquisas incorretamente.** Os 88%, 63% e λ≈0,1–0,2 pertencem ao estudo de caso da **Hyperliquid em outubro/2025**. A faixa de queda de OI reúne medidas diferentes; não demonstra que 25–70% das posições foram necessariamente liquidadas compulsoriamente em cada um dos sete eventos. [2608.03616, §§4 e 6](https://arxiv.org/html/2608.03616).

   Retirar “a literatura rejeitou a previsão” e “funding não funcionou como alarme”: funding foi excluído da análise intradiária; o estudo rejeita universalidade dos indicadores examinados, não toda previsão possível, e identifica um precursor populacional em fluxo. **Cenário:** abandonar uma hipótese não testada atribuindo-lhe uma refutação inexistente. [2607.27070, §§2, 4.6 e 6](https://arxiv.org/html/2607.27070).

**NICE-TO-HAVE**

`interval_s` **já é persistido** via serialização ([funding.py:59](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:59), [settle.py:98](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:98)). Falta distinguir previstos, observados e ausentes.

**O QUE EU FARIA DIFERENTE**

Separaria atravessamento confirmado, inferido e indeterminado. Retiraria também equivalência de instrumentos baseada apenas na resolução de cinco minutos.

**CONCORDO COM**

Medir duração diretamente, auditar exclusões e estudar desmonte como diagnóstico, sem promessa preditiva.

**OBSIDIAN**

- **KB-0026:** corrigir atravessamento, denominadores e condições dos mecanismos.
- **KB-0025:** corrigir semântica de `UP` e alcance das fontes.
- **EXP-0001-momentum-v1:** acrescentar ressalva distinguindo grade prevista de cobrança confirmada.
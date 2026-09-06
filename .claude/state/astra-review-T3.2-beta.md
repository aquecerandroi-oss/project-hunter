**RESUMO**

Minha recomendação: **OLS com intercepto; R² informativo; 20 dias consecutivos completos de pares válidos; retorno simples; versão semântica com parâmetros canônicos; cálculo em Decimal com contexto fixo.**

Assumi `quant-engineer`, em modo OPINIÃO. Uma correção documental: o arquivo de decisões delegadas contém D1–D3; a proposta de beta está na [diretiva:77](/C:/dev/project-hunter/.claude/state/directive-risk-engine-2026-09-06.md:77). O [diálogo M3:22](/C:/dev/project-hunter/.claude/state/dialogue-M3.md:22) ainda propõe dias **distintos**. Para este parecer, prevalece sua instrução explícita de **contíguos**.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados: revisão de desenho, sem implementação. As medições da KB foram lidas, não reproduzidas.

**MUST-FIX**

**1. Estimador: escolho OLS com intercepto.**

Com `x = retorno BTC` e `y = retorno ativo`:

\[
S_{xx}=\sum(x-\bar x)^2,\quad S_{xy}=\sum(x-\bar x)(y-\bar y)
\]
\[
\hat\beta=S_{xy}/S_{xx},\qquad\hat\alpha=\bar y-\hat\beta\bar x
\]

Não exige um solver: são médias e somas centradas. É compatível com `regr_slope` empregado na [KB-0060:56](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:56) e na [KB-0071:60](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo.md:60). A definição das estatísticas está na [documentação do PostgreSQL](https://www.postgresql.org/docs/16/functions-aggregate.html#FUNCTIONS-AGGREGATE-STATISTICS-TABLE).

O intercepto não absorve a sensibilidade às **variações** do BTC. Ele separa a média que a inclinação não explica. Algebricamente:

\[
\hat\beta_{\text{origem}}
=\hat\beta_{\text{intercepto}}
+\frac{\hat\alpha\sum x}{\sum x^2}
\]

**Cenário de falha:** drift negativo do ativo e média positiva do BTC reduzem artificialmente a inclinação pela origem. Médias horárias pequenas não garantem que essa parcela seja irrelevante.

A ressalva real é outra: beta contemporâneo não identifica causalidade nem garante sensibilidade em stress. Remover o intercepto não corrige isso.

**2. R²: concordo em não usá-lo como gate; usaria o beta estimado sem margem automática.**

Com ambas as variâncias positivas, `R² = Sxy²/(Sxx·Syy)`. R² baixo significa pouca variância explicada pelo fator; não significa necessariamente beta pequeno ou inútil.

Mas retiraria o argumento de que um gate deixaria tudo em shadow “para sempre”: a [KB-0060:38](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:38) mede **42 horas em barras de 15 minutos**, não 30 dias em barras horárias.

Para T3.2:

- Validade exige cobertura, pareamento, frescor, entradas finitas e denominador identificável.
- `Sxx = 0` torna beta indisponível; nunca substituir por zero.
- `Syy = 0` torna R² indefinido. Não fabricar `R² = 1`; separar esse diagnóstico da possibilidade matemática de estimar beta zero.
- Beta negativo é preservado; o consumidor aplica o módulo.

Para `R² = 0,02`, aplicaria `|notional × beta|` e manteria os demais limites da [diretiva:31](/C:/dev/project-hunter/.claude/state/directive-risk-engine-2026-09-06.md:31). **Não multiplicaria por `1/R²`, nem reduziria beta por R².**

**Cenário de falha:** multiplicar beta por R² concede mais capacidade justamente quando o fator explica menos do risco. Uma margem futura deve depender de incerteza da inclinação e estabilidade, com política própria versionada; R² sozinho não determina essa margem. “Válido” aqui significa elegível pelo protocolo, não comprovadamente preciso.

**3. Contiguidade: dias consecutivos, contados depois do pareamento.**

Minha escolha concreta entre suas alternativas: **H = 24 horas pareadas válidas por dia UTC e uma sequência de pelo menos 20 desses dias consecutivos**, dentro da janela móvel de 30 dias. Dias parciais não contam para maturidade. A regressão usa todos os pares válidos da janela, não apenas os da sequência.

Isso é deliberadamente diferente do regime: [regime/model.py:137](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/model.py:137) declara dias distintos, e [regime/series.py:205](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/series.py:205) efetivamente conta datas distintas.

Confirmo o pareamento estrito e o descarte de retorno que atravessa lacuna. Especificaria também:

- Hora UTC fechada, exatamente 60 minutos finais únicos, alinhados, e fechamento anterior necessário ao retorno. A âncora já é exigida em [series.py:178](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/series.py:178).
- Se construir retornos por `lag` de barras horárias completas, exigir predecessora exatamente uma hora antes, **em ambas as séries**.
- Preços positivos e finitos; duplicatas conflitantes recusadas; sem preenchimento de lacunas.
- Identidade explícita de exchange, venue, mercado e moeda de cotação. Não juntar spot e perpétuo somente por símbolo.
- Corte explícito `as_of`; velas futuras são excluídas mesmo que estejam marcadas finais.

**Maturidade e frescor são controles separados.** Recomendo exigir o último par esperado e expirar o resultado pelo `window_end`, nunca pelo instante em que o job finalmente rodou. Se adotarem tolerância de duas horas, `valid_until = window_end + 2h`; isso continua sendo proposta, não decisão já consolidada.

**Cenários de falha:** vinte datas com uma hora cada passam indevidamente; cobertura individual suficiente esconde ausência de pares; vinte dias antigos seguidos de interrupção continuam autorizando entradas quando cada recálculo renova o prazo.

**4. Retorno: prefiro simples para este consumidor.**

Usaria `r = c_t/c_{t-1} − 1`. Para uma posição, `Δvalor = notional_inicial × r`; por linearidade da covariância, betas de retornos simples permitem agregar a sensibilidade monetária ao fator mantendo os notionais fixos no intervalo.

Log é defensável como aproximação local, mas “uma hora” não garante movimentos pequenos. Em um exemplo hipotético de queda horária de 50%, retorno simples é `−0,5`, enquanto log é aproximadamente `−0,693`. A diferença pode afetar justamente observações de grande influência na regressão.

A [KB-0060:50](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:50) e a [KB-0071:53](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo.md:53) usam log. Preservaria essas medições e declararia `return_kind="simple"` na nova identidade.

**Cenário de falha:** tratar beta log como sensibilidade monetária exata durante saltos grandes. Se escolherem log, o contrato precisa assumir explicitamente essa aproximação.

**5. Versionamento e numérica: identidade declarada, Decimal integral.**

**(a) Concordo com `BETA_METHOD_VERSION + hash(parâmetros canônicos)`.** É coerente com [definitions.py:73](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/definitions.py:73), cujo hash exclui descrição, e com [RegimeThresholds.identity:153](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/model.py:153).

Incluiria na identidade: estimador/intercepto, retorno, janela, alinhamento, cobertura, pareamento, validade temporal, política numérica, precisão, arredondamento e quantums.

Digest do source tem valor como **proveniência do artefato**, separado da identidade matemática. Não prova reprodutibilidade sozinho: dependências e helpers também alteram resultados. O brief deve registrar essa mudança de interpretação. Bump manual exige preservar a implementação anterior para replay.

**(b) Aceito `1e-8` para beta e `1e-6` para R²**, com `ROUND_HALF_EVEN`, quantização somente na saída e zero negativo normalizado. São resoluções de armazenamento, não precisão estatística.

Para a garantia forte de bytes, escolheria **Decimal do retorno até as somas centradas**, em duas passagens e ordem cronológica fixa. O repositório já fixa precisão 28 e `ROUND_HALF_EVEN` em [numeric.py:18](/C:/dev/project-hunter/packages/core/hunter_core/strategies/numeric.py:18); reutilizaria esse contexto explicitamente, sem depender do ambiente.

NumPy `float64` sobre retornos não viola a regra monetária e pode repetir perfeitamente no mesmo ambiente. Porém:

- A estratégia de soma e a precisão podem variar conforme a operação: [NumPy](https://numpy.org/doc/stable/reference/generated/numpy.sum.html).
- `math.fsum` melhora precisão, mas documenta diferenças possíveis no último bit entre builds: [Python](https://docs.python.org/3/library/math.html#math.fsum).
- Quantização não elimina toda divergência: valores em lados opostos de uma fronteira podem gerar bytes diferentes.

**Cenário de falha:** Windows e Linux produzem valores quase idênticos que arredondam diferentemente; a mesma versão passa a ter duas saídas canônicas.

Com até 720 pares, prefiro evitar essa dependência. Isso não é afirmação de desempenho medido. Decimal também exige contexto, ordem e serialização fixos; [canonical.py:128](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:128) já fornece serialização canônica.

**NICE-TO-HAVE**

Diagnósticos de estabilidade por subjanela e influência de observações extremas; comparação simples/log como pesquisa. Não colocaria margem ou novo gate automaticamente.

**O QUE EU FARIA DIFERENTE**

Separaria **identidade do método**, **revisão imutável dos dados/resultados** e **proveniência do executável**. Hash dos parâmetros não congela candles corrigidas posteriormente.

Nos testes futuros, priorizaria: drift com beta conhecido; lacunas e fronteiras UTC; duplicatas conflitantes; variância BTC zero; expiração; contexto Decimal ambiente alterado; resultado canônico idêntico entre processos.

**CONCORDO COM**

Pacote puro, sem IO nem relógio; OLS com intercepto; R² informativo; pareamento estrito; BTC com beta exatamente 1 por definição; versão semântica e quantums propostos. Para BTC, declararia a exceção de maturidade e identificaria o resultado como definido, não estimado.

**OBSIDIAN**

- **Features (Feature Engine)** — registrar o contrato do beta, fórmula, cobertura, identidade e aritmética.
- **Risk Engine** — definir validade, expiração e consumo de beta com R² baixo.
- **KB-0060 / KB-0071** — acrescentar ligação para T3.2 e distinguir suas medições log do estimador operacional, preservando o histórico.
- **Revisões da Astra — T3.2** — registrar este parecer e quais recomendações foram aceitas.
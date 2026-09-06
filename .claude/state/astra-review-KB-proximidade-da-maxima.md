**RESUMO**

Hipótese plausível; **informação diferente não significa independência nem poder preditivo adicional**. Eu manteria a candidata como experimento, sem atribuir validação acadêmica ao filtro.

**ARQUIVOS**

Nenhum criado ou modificado. Parecer como `quant-engineer`.

**TESTES**

Não executei testes nem consultas ao banco. Conferi implementação e artigo original.

**MUST-FIX**

1. **Janela diferente, mas também preço diferente.** São 20 barras anteriores × 15 min = 5 h, usando **fechamentos** ([indicators.py:141](/C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:141)). A máxima de 24 h usa **highs intrabar**, incluindo a última vela final ([price.py:119](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:119)).

   Exemplo hipotético: máximo dos fechamentos anteriores = 100; fechamento atual = 101; máxima de 24 h = 105. Há rompimento, mas distância = −3,81%: reprova. Portanto, não é implicação lógica. Além das 19 h extras, o filtro pode estar selecionando **menor rejeição por pavios**. A frequência real precisa ser medida.

2. **O envelope atual não contém essa distância.** A lista persistida pela v1 tem fechamento, máximo dos fechamentos, volume e ATR, mas não máxima de 24 h ([momentum_v1.py:240](/C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:240)). Consultar essa chave diretamente e interpretar `NULL` como reprovação produziria falsa rejeição de todos esses sinais.

   Primeiro conte cobertura. `features` é uma lista de evidências ([envelope.py:118](/C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:118)); a extração seria:

   ```sql
   jsonb_path_query_first(
     supporting_features,
     '$.features[*] ? (@.name == "distance_from_24h_high" && @.available == true).value'
   ) #>> '{}'
   ```

   Na ausência, reconstrua pelas 1.440 velas finais contíguas até `observation_ts`, sem usar informação posterior; classifique como análise retrospectiva e registre gaps/cobertura.

**NICE-TO-HAVE**

Antes da coorte, por versão e corte temporal congelados, medir:

- Total de sinais, distância disponível e indisponível.
- **Retenção = aprovados no filtro / sinais com distância válida**; também quantis da distância.
- Retenção por mercado, dia UTC e faixa de ATR/RVOL.
- Para separar janela de pavios: comparar máximos de **fechamentos** em 5 h/24 h e de **highs** em 5 h/24 h.

Retenção próxima de 100% indica pouca seletividade incremental **nessa população**, não prova ausência de informação.

**O QUE EU FARIA DIFERENTE**

- **ATR:** usaria `gap_atr = (H24 − close) / ATR14_15m`, com aprovação `gap_atr ≤ k`. Normaliza pela volatilidade, mas **k continua sendo escolha experimental**. Para distância `d` e `a = ATR/close`, a conversão exata é `−d / ((1+d) × a)`, não simplesmente `−d/a`. A distância existente divide pela máxima ([price.py:135](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:135)). Preservaria −0,005 como hipótese original; ATR seria alternativa explicitamente registrada.
- **Extrapolação declarada:** “George & Hwang estudam ações, ordenação transversal mensal e carteiras mantidas por seis meses. Aplicar a ideia a máximas de 24 h, decisões de 15 min e operações LONG em perpétuos é hipótese nova. O artigo não valida este limiar, confirmação por volume ou ausência de reversão intradiária.” A ausência de reversão é resultado do contexto estudado. [Artigo original](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf).
- Compararia v1/v5 simultaneamente, com frequência e expectancy líquida em R. Filtrar sinais antigos **não reproduz a política inteira**: mudar a condição altera o rearme e os sinais posteriores ([episodes.py:53](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:53)).

**CONCORDO COM**

Manter RVOL fixo para isolar a contribuição da proximidade. Precisão editorial: hoje é volume dividido pela **mediana das 96 barras anteriores**, não média ([indicators.py:124](/C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:124)). A comparação v1/v5 não testa o benefício do volume.

**OBSIDIAN**

- **KB-0004 — Proximidade da máxima e confirmação por volume:** incluir extrapolação, distinção fechamento/high e diagnóstico de redundância.
- **Strategy Backlog:** registrar candidata, cobertura necessária e limiar experimental.
- **Features (Feature Engine):** esclarecer fórmula e ausência dessa evidência nos envelopes atuais da momentum_v1.
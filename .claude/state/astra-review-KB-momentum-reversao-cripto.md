**RESUMO**

Como `quant-engineer`: **a candidata merece teste, mas é hipótese nova; os artigos não demonstram que romper após 2 ATR piora a entrada.**

1. **Evidência:** Dobrynskaya estuda momentum/reversão entre criptos em horizontes semanais, com reversão principalmente puxada pelas **antigas perdedoras** — isso não demonstra exaustão de altas em 15 minutos. Wen é mais próximo do problema, mas encontra **momentum e reversão**, dependentes de saltos, liquidez e contexto. Sobre-reação é interpretação dos autores, não mecanismo causal comprovado para nosso filtro. [Dobrynskaya](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3913263), [Wen et al.](https://www.sciencedirect.com/science/article/pii/S1062940822000833).

2. **ATR versus percentil:** começaria com ATR pela simplicidade e relação com a geometria do trade. Percentil mede **raridade no próprio mercado**, não distância econômica; exige janela histórica e aquecimento adicionais, sempre anteriores à decisão. Nenhum é universalmente superior.

3. **Pode remover os melhores rompimentos? Sim.** Compare faixas de extensão definidas previamente: expectancy líquida, alvo antes do stop, expirações/invalidações e trajetórias posteriores. Estratifique por tendência anterior, rvol e liquidez. Se a faixa bloqueada continua melhor fora da amostra, o filtro está descartando continuação. Não escolha novos cortes depois de observar esses resultados.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executei testes nem backtest. Consultei código e resumos dos artigos; os textos completos não ficaram acessíveis.

**MUST-FIX**

- **Nomear corretamente a exposição.** A feature mede retorno dos últimos 15 minutos normalizado por ATR; não mede extensão acumulada desde o início do movimento. Cenário: uma alta persistente por várias barras passa pelo filtro porque a última barra foi pequena. O ATR é realmente de 15 minutos ([trend.py:71](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:71)); a divisão está em [trend.py:156](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:156). Além disso, `return/(ATR/C_t)` equivale a `(ΔC/ATR)×(C_t/C_anterior)`: **“2 ATR exatos” é uma aproximação**.

- **Preservar os episódios-base e acompanhar bloqueados contrafactualmente**, com as mesmas entradas, saídas e custos. Filtro somente de admissão, congelado na decisão. Cenário: bloquear agora e permitir outra entrada minutos depois muda o timing/rearme; a comparação deixa de isolar o filtro.

- **Refutação precisa de três resultados.** Para `Δ = E_aprovados − E_bloqueados`: IC95% inteiramente acima de `δ` sustenta; inteiramente abaixo refuta o ganho mínimo; cruzando `δ` é inconclusivo. Cenário: pouca amostra produz IC amplo e seria confundida com ausência de efeito. Reamostre blocos temporais conjuntos para todos os mercados, preservando dependência e horizontes sobrepostos.

**NICE-TO-HAVE**

Percentil histórico **da mesma medida** como variante separada; registrar fração bloqueada e sensibilidade aos custos.

**O QUE EU FARIA DIFERENTE**

Pré-registraria `K=2` como escolha experimental, sem respaldo específico dos artigos, e avaliação futura reservada. Chamaria a hipótese de **“impulso recente excessivo”**. Acompanhar também `E_aprovados − E_base`: separar bem dois grupos não garante ganho relevante nem expectancy positiva.

**CONCORDO COM**

Uma alteração por candidata, resultado líquido em R e incerteza por blocos temporais.

**OBSIDIAN**

- **KB-0002 — Momentum e reversão em cripto:** distinguir evidência semanal, intradiária e hipótese de impulso excessivo.
- **Strategy Backlog:** registrar candidata com protocolo, contrafactuais e critério de refutação acima.
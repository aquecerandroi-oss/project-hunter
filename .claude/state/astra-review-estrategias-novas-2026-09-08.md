## RESUMO

**Eu escolheria quatro hipóteses: compressão→rompimento, pullback→reversão, desconto spot–perp com funding negativo e força relativa ajustada ao BTC.** As quatro seriam LONG, `research_only`, com parâmetros congelados antes do replay.

**Não estão validadas nesta resposta.** Fiz análise documental e pesquisa de fontes; não executei replay. Os −0,22 R/248 encerramentos e −0,60 R são números recebidos do diagnóstico, também registrados no [brief T3.32:8](C:/dev/project-hunter/.claude/state/brief-T3.32-why-are-we-losing.md:8).

Há duas limitações que mudam a entrega:

- O contexto atual contém candles de **um mercado** e **uma observação** de funding; não contém histórico de funding, série spot–perp ou painel transversal. As candidatas 3 e 4 exigem preparação desses dados no contexto. [base.py:109](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:109)
- O replay seleciona mercados `PERPETUAL`. Seu resultado sozinho **não comprova rentabilidade da execução spot**. [plan.py:121](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/plan.py:121)

### Contrato comum proposto

Os números abaixo são **premissas iniciais de pesquisa**, não parâmetros ótimos nem frequências medidas.

- Decisão em fechamento final de 15m; indicadores de 1h usam somente horas completas.
- `C` = fechamento de referência; `A` = ATR Wilder(14), 15m, calculado sobre 97 barras e congelado na decisão.
- Entrada na primeira abertura de 1m estritamente posterior à decisão; no replay com atraso de 2 segundos, corresponde a `t+1min`. Preservar recusa por atraso e geometria. [environment.py:49](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/environment.py:49), [walker.py:42](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:42)
- Stop e alvo fixos; horizonte contado da entrada; nenhuma piramidagem. Preservar stop prioritário quando stop e alvo aparecem na mesma vela. [walker.py:145](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:145)
- **Sem invalidação adicional nas quatro primeiras versões:** `invalidations=()`. Isso é permitido pelo contrato e evita introduzir quatro novas políticas de saída junto com quatro entradas. Não significa que remover a invalidação melhora o momentum. [base.py:224](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:224)
- Hipótese-base de custos: spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado, aproximadamente **20 bps ida e volta**, sem funding. Sensibilidade a 40 bps. São hipóteses, não tarifas spot verificadas.
- Filtro econômico inicial: custo nominal de 20 bps ≤ **25% da distância percentual do stop**. Reportar quantos sinais ele elimina. Na avaliação, usar o denominador efetivo `entrada−stop` e também ganho líquido potencial até o alvo.

Para sinais originados no perpétuo, manter o replay perp como diagnóstico. A validação destinada ao paper precisa acompanhar **preços spot**, com geometria spot explicitada e funding financeiro zero. Usar funding como informação não torna spot recebedor de funding.

### 1. Compressão de volatilidade → rompimento confirmado

**Por quê:** testar expansão após quietude, acrescentando uma condição anterior ao rompimento. Bollinger descreve BandWidth como instrumento de identificação de compressão e fechamento fora da banda como sinal inicial de continuação. Isso sustenta o mecanismo, não comprova esta parametrização em cripto. [Regras de John Bollinger](https://www.bollingerbands.com/bollinger-band-rules)

**Entrada exata, todas as condições:**

1. Calcular `BW = 4 × desvio-padrão populacional(20 fechamentos) / SMA20`.
2. `BW(t−1)` ≤ percentil 20 dos **96 BW anteriores a t−1**, pelo método nearest-rank.
3. `C(t)` > máxima das máximas das 20 barras anteriores.
4. `RVOL(t) = volume(t)/mediana(volume das 96 barras anteriores)` ≥ 1,5.
5. Passar o filtro econômico comum.

**Stop:** `C−2A`. **Alvo:** `C+3A`. **Horizonte:** 8h. **Invalidação:** nenhuma adicional.

**Frequência de planejamento:** 0,1–0,5 entrada/mercado/dia, depois dos filtros e rearme; pode ser zero em determinado mês.

**Falha principal:** falso rompimento ou expansão já consumida na barra do sinal; o atraso de entrada compra o movimento tarde. É a candidata com **maior risco de redundância com momentum**, cuja regra existente já combina rompimento, RVOL e ATR. [momentum_v1.py:1](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:1)

### 2. Pullback curto dentro de tendência horária positiva

**Por quê:** comprar uma recuperação após deslocamento negativo, em vez de perseguir a máxima. Há evidência publicada de momentum **e reversão intradiários** em cripto, variáveis conforme liquidez, saltos e regime. A regra abaixo é minha operacionalização, não uma reprodução do estudo. [Intraday return predictability in the cryptocurrency markets](https://www.sciencedirect.com/science/article/pii/S1062940822000833)

**Entrada exata:**

1. Na última hora completa `h`: fechamento > SMA24; `SMA24(h)>SMA24(h−4)`.
2. Para cada barra 15m `j`, calcular  
   `z(j) = [C(j)−média dos 20 fechamentos anteriores] / desvio-padrão populacional desses fechamentos`.
3. `z(t−1)≤−2` e `−2<z(t)<−0,5`.
4. `C(t)>C(t−1)`.
5. Passar o filtro econômico comum; desvio zero torna a leitura indisponível.

**Stop:** `C−1,5A`. **Alvo:** `C+2A`. **Horizonte:** 4h. **Invalidação:** nenhuma adicional.

**Frequência de planejamento:** 0,2–0,8 entrada/mercado/dia.

**Falha principal:** o pullback é o começo de uma tendência de baixa; a média horária reconhece a mudança tarde. Segunda falha: reversão existe em preço, mas é curta demais para pagar execução.

### 3. Recuperação de desconto spot–perp após funding negativo

**Por quê:** é a candidata estrutural que mais aproveita os dados diferenciados. O BIS documenta segmentação, excesso de volatilidade dos futuros frente ao spot e limites à arbitragem. **Isso não demonstra que funding negativo prevê alta do spot:** essa ligação é precisamente a hipótese a testar. [BIS — Crypto carry](https://www.bis.org/publications/working-paper-1087-crypto-carry)

**Entrada exata:**

1. Fechamentos spot e perp do mesmo símbolo e minuto: `b(t)=P_perp(t)/P_spot(t)−1`.
2. Normalizar `b` por média e desvio-padrão populacional das **672 barras 15m anteriores**, excluindo a atual: `z_b`.
3. `z_b(t−1)≤−2`; `−2<z_b(t)≤−0,5`; e `b(t)<0`.
4. Último funding **já liquidado**, disponível antes da decisão, normalizado para oito horas:  
   `f8=f_realizado×8/duração_do_intervalo_em_horas ≤ −0,0001`.
5. Funding não pode estar mais velho que seu intervalo de liquidação; intervalo desconhecido → indisponível.
6. Fechamento spot atual > fechamento spot anterior.
7. Passar o filtro econômico comum.

**Stop:** `C−2A`. **Alvo:** `C+2,5A`. **Horizonte:** 8h. **Invalidação:** nenhuma adicional. Na avaliação spot, `C` e `A` devem ser do spot.

**Frequência de planejamento:** 0,05–0,3 entrada/mercado/dia; provavelmente a menor amostra das quatro.

**Falha principal:** o desconto fecha porque o perp sobe ou porque o spot cai. **Convergência da basis não implica lucro de uma compra spot.** Funding negativo também pode persistir durante queda.

Não chamaria isso de carry: não há posição vendida em derivativo nem receita contratual de funding. A documentação oferece histórico de `fundingRate` e `fundingTime`; não autoriza tratar a taxa futura realizada como informação passada. [Binance — dados de funding](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)

### 4. Força relativa de 24h descontando a exposição ao BTC

**Por quê:** selecionar o ativo que supera o movimento explicado pelo BTC, sem exigir rompimento local. Liu, Tsyvinski e Wu encontram um fator transversal de momentum em cripto. A evidência original não valida automaticamente ranking de 24h, saída em 8h ou uma carteira somente comprada. [Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882)

**Entrada exata:**

1. Avaliar novas entradas apenas nas decisões de hora cheia.
2. Estimar `β_i = cov(r_i, r_BTC)/var(r_BTC)` sobre **168 retornos horários completos**, terminando na hora anterior à decisão.
3. Calcular `q_i = retorno_i_24h − β_i × retorno_BTC_24h`.
4. Ordenar o universo elegível por `q_i` decrescente; desempate por símbolo.
5. Selecionar os primeiros `ceil(0,10×N)`; no universo inicial de quatro ativos, selecionar **um**.
6. Exigir `q_i>0`, retorno próprio de 24h > 0 e retorno BTC de 4h ≥ 0.
7. Passar o filtro econômico comum. Manter a posição até sua saída; mudança de ranking não encerra nem rebalanceia.

**Stop:** `C−2A`. **Alvo:** `C+3A`. **Horizonte:** 8h. **Invalidação:** nenhuma adicional.

**Frequência de planejamento:** média transversal de 0,1–0,5 entrada/mercado/dia, concentrada nos líderes.

**Falha principal:** reversão dos vencedores, beta instável ou resultado explicado apenas pela alta geral. Ajustar o ranking por beta **não neutraliza** a exposição da posição comprada.

### O que mataria cada candidata no primeiro replay

Eu congelaria os critérios abaixo **antes de executar**. São regras de descarte desta versão por utilidade econômica; não provas de que uma família inteira nunca funciona.

`E_liq` inclui todos os encerramentos avaliáveis — alvo, stop e expiração — com cobertura publicada. Para os critérios econômicos: ao menos 100 outcomes, 15 dias distintos, os quatro mercados representados e pelo menos 95% dos encerramentos maturados precificáveis. Sem isso, a resposta é **inconclusiva**, não aprovação.

| Candidata | Número que justificaria descartar a versão |
|---|---|
| Compressão→rompimento | `E_bruta≤0` no agregado **e em cada um dos quatro mercados**. Além disso, descartaria sua pretensão de diversificação se ≥80% das entradas coincidirem com momentum no mesmo mercado em ±15m e não houver melhora econômica contra controle com saídas iguais. |
| Pullback→reversão | `E_liq≤−0,10 R` e PF≤0,80 no custo-base. Se o movimento bruto existe, mas não paga nem o custo-base, esta implementação não serve ao produto. |
| Funding+basis | `E_liq_spot≤−0,10 R`, mesmo que o perp seja lucrativo ou a basis convirja. **Zero entradas admissíveis** em uma janela com cobertura completa também a retira da prioridade imediata, mas não refuta o mecanismo. |
| Força relativa | `E_liq≤0` **e** vantagem média ≤0 sobre o controle que compra igualmente os quatro ativos nos mesmos horários, com os mesmos filtros comuns, custos e saídas. Nesse caso, o ranking não entregou utilidade. |

A candidata estrutural provavelmente **não alcançará 100 observações** em 31 dias. Não afrouxaria seus limiares para fabricar frequência. Exibiria a contagem de eventos independentes de funding e continuaria prospectivamente se o custo de pesquisa justificar.

Um replay positivo a 20 bps e negativo a 40 bps recebe **“frágil a custos”**, não validação. E 31 dias solicitados não são necessariamente 31 dias utilizáveis: aquecimento, gaps e maturação final diminuem a janela.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes, SQL nem replay nesta rodada de **OPINIÃO**. Os critérios e frequências acima são propostas. O arquivo `.claude/state/notes-T3.32.md` não estava presente na consulta; portanto, não atribuí os stops/alvos a uma distribuição de MFE/MAE ainda não entregue.

## MUST-FIX

1. **Preparar contexto histórico sem alterar silenciosamente versões congeladas.**  
   Funding histórico, séries pareadas e ranking precisam chegar como dados imutáveis, cortados no tempo. Alterar diretamente `base.py`, importado pelo momentum, pode alterar seu digest transitivo e invalidar versões existentes. Cenário: implementar a candidata estrutural faz o catálogo recusar o momentum congelado. [base.py:109](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:109), [momentum_v1.py:31](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:31), [code_ref.py:12](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:12)

2. **Separar o instrumento de sinal do instrumento de resultado.**  
   Cenário: perp recupera desconto de 30 bps, spot fica parado; o replay perp parece bom, mas a compra spot perde os custos. O seletor atual é perp e a liquidação atual consulta funding. A avaliação spot precisa ser explícita, sem simplesmente renomear `R_net`. [plan.py:121](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/plan.py:121), [settle.py:61](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:61)

3. **Cortar informação pelo instante em que poderia ser conhecida.**  
   Nada de quantis calculados sobre o mês inteiro, beta estimado até o fim da amostra, hora ainda aberta ou funding futuro realizado. Cenário: comprar às 07:45 usando a taxa liquidada às 08:00. Backfill permite reconstrução retrospectiva, mas não prova disponibilidade operacional naquela hora; a documentação registra ausência de `received_at` no histórico de funding. [PIPELINE.md:78](C:/dev/project-hunter/docs/PIPELINE.md:78)

4. **Congelar universo e sincronizar o ranking.**  
   Os quatro ativos são uma amostra deliberadamente escolhida, não representativa de todo o mercado. Para ampliar aos 14 pares, não aplicar retroativamente os sobreviventes ou o volume atual. O replay reconhece que usa elegibilidade observada na execução, sem histórico completo de composição. Cenário: excluir justamente o ativo que perdeu liquidez e caiu durante o mês. [environment.py:24](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/environment.py:24)

5. **Não confundir saída ruim com efeito causal da saída.**  
   Os invalidados perderem não demonstra que teriam ganhado se continuassem. Comparar políticas sobre as mesmas entradas, com mesmo risco inicial, incluindo censura e custos adicionais. Cenário: remover uma saída em −0,58 R transforma o resultado em stop de −1,2 R. É a distinção central da [KB-0006:32](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:32).

6. **Preservar dependência e contabilizar seleção.**  
   ETH/SOL/XRP/DOGE simultâneos não são quatro observações independentes. Reamostrar blocos temporais comuns a todos os mercados; publicar concentração por dia/ativo, exposição e frequência. Registrar as quatro candidatas e todas as variantes tentadas. Cenário: dezenas de sinais de uma única alta do BTC produzem um intervalo artificialmente estreito.

## NICE-TO-HAVE

- Controle por entradas alternativas nos mesmos mercados, horários e regimes, com geometria idêntica.
- Sensibilidade ao atraso de entrada e à ambiguidade intrabar; MFE/MAE indeterminados permanecem indeterminados.
- Comparar sobreposição de **exposição**, além de coincidência de sinais.
- Deixar fora desta rodada: abertura de sessão e efeito de fim de semana, por maior exposição à escolha de calendário; rebound de liquidação, sem histórico adequado; funding extremo isolado, incorporado à hipótese estrutural para não gastar duas vagas em mecanismos próximos.

## O QUE EU FARIA DIFERENTE

Começaria pelas candidatas 1 e 2 enquanto se prepara o contexto histórico das candidatas 3 e 4. **Não trocaria estas últimas por mais dois filtros de momentum só para entregar quatro módulos rapidamente.**

Congelaria uma versão por hipótese, faria o replay como triagem e reservaria a avaliação futura para confirmação. Os primeiros 31 dias já usados para descobrir e escolher regras são exploratórios; não se tornam amostra independente porque ganharam outro `cohort`.

## CONCORDO COM

Diversificar mecanismos, usar funding e spot–perp, manter LONG/SPOT no destino e exigir evidência no primeiro dia. Concordo também com manter o piso de **100 outcomes e 30 dias prospectivos**, seguido de replicação; esse piso não substitui análise de incerteza nem cálculo de potência.

## OBSIDIAN

- **Strategy Backlog** — registrar as quatro hipóteses, contratos propostos, fontes, dependências e critérios de descarte.
- **Strategies** — distinguir dados existentes na plataforma de dados disponíveis no contexto e distinguir replay perp de validação spot.
- **KB-0006 — Valor incremental da invalidação** — vincular a escolha de ausência de invalidação inicial sem atribuir benefício causal.
- **KB-0008 — Custos em perpétuos e quanto sobra de 1 R** — acrescentar orçamento econômico, sensibilidade spot e funding como sinal versus fluxo financeiro.
- **EXP-0008 a EXP-0011, títulos propostos** — um experimento por candidata; congelar protocolo antes da execução, sem preencher resultados.
- **Revisoes-Astra — T3.33: quatro estratégias candidatas** — guardar este parecer e os bloqueios de contexto, instrumento e validação.
---
tags: [knowledge, nota, microestrutura, fluxo, cripto, regime]
tema: Volume e fluxo de ordens
fonte: "\"When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures\" (arXiv:2607.09230); \"Explainable Patterns in Cryptocurrency Microstructure\" (arXiv:2602.00776)"
fonte_url: https://arxiv.org/html/2607.09230v1
lido_em: 2026-09-06
evidencia: preprint (dois, arXiv), sem revisão por pares; síntese conjunta NÃO demonstrada
hipotese_testavel: sim
astra: concorda com correções (H-KB0016a inexecutável hoje; síntese conjunta retirada)
---

# Quando o fluxo importa: dependência de estado

## O que afirma

Dois preprints recentes sobre **perpétuos da Binance** — o nosso mercado exato — perguntam, cada um à
sua maneira, **quando** o fluxo de ordens carrega informação. Eles são compatíveis; **não são o mesmo
resultado**, e a diferença importa.

**arXiv:2607.09230** monta um regime discreto de liquidez em três estados (calmo, misto, estressado)
a partir de spread relativo, profundidade top-20 e desequilíbrio top-20, e pergunta se o fluxo
agressor acrescenta previsão **depois** de controlar pelo estado do book. O alvo **não é preço**: é a
**transição de estado de liquidez**. Resposta: o fluxo só agrega **empilhado sobre** o modelo de
estado L2, com efeito forte no ETH sob estresse e **inconclusivo no BTC**. As magnitudes calibram
expectativa: linha de base pelo estado pré-evento +0,045 em 5 min; modelo não-linear raso do L2
+0,060; camada de fluxo por cima **+0,020 no ETH e +0,001 no BTC** em 1 min. Sem backtest, sem PnL.

**arXiv:2602.00776** vai ao retorno: Binance Futures, cinco perpétuos (BTC, LTC, ETC, ENJ, ROSE),
1 s, de 01/01/2022 a 12/10/2025, alvo = retorno logarítmico do mid em **3 segundos**. Por importância
SHAP, o que domina é **order flow imbalance, spread e desvio VWAP-mid**, com **padrões semelhantes
entre ativos** apesar de liquidez heterogênea. Há backtests taker e maker; **não transcrevo os
números de retorno anualizado** porque não consegui fixar a unidade da tabela (os valores aparecem
sem `%` e, pela equação definida como fração, teriam leitura muito diferente) nem qual hipótese cada
p-valor testa — a discussão alterna comparação com *buy-and-hold* e com média zero, e o maker de BTC
tem ARC positivo. Citar esses números com a escala errada calibraria expectativa por um fator de
cem, então ficam de fora até serem conferidos.

**A síntese que eu tinha escrito — "liquidez menor, fluxo mais informativo, execução pior" — sai da
nota.** Os dois artigos não estabelecem isso: um mede estado de liquidez dentro do ativo, o outro
encontra padrões **semelhantes** entre ativos com resultados econômicos diferentes por estratégia de
execução. O enunciado defensável é: *os estudos motivam investigar se o valor preditivo e os custos
variam com o estado de liquidez; não estabelecem relação monótona entre volume, informação e
rentabilidade.*

## Onde foi mostrado

Binance perpétuos USDT; 2022–2025 e 2023 a meados de 2026; frequências de 1 s e 1 min. Mesmo mercado
que o nosso. **Horizontes de 1 a 300 segundos**, contra 7200 s da `volume_anomaly_v1` — a distância
que impede tratar qualquer um dos dois como validação de coisa alguma nossa.

O 2602.00776 seleciona ativos por posição de **capitalização** no início da amostra; não testa
fronteira de volume, e portanto não fala sobre um universo "top-N por volume".

## Como mediríamos aqui

**Duas correções sobre o nosso próprio sistema, e a segunda derruba a análise que eu tinha
proposto.**

**Primeira: "top 50 por volume 24 h" não é o universo do Lab em geral.** O tamanho é configurável,
com padrão **200** (`packages/core/hunter_core/settings.py:128`), e a seleção admite allowlist e
blocklist (`services/market-worker/hunter_market_worker/universe_repo.py:195`). O top 50 foi um
**override** de um ambiente e período específicos; a coorte da VPS de 2026-09-06 aparece com 134
mercados distintos. Qualquer análise por faixa de liquidez tem de identificar **ambiente e período**
antes de dizer qual universo estava valendo.

**Segunda: o ranking do instante NÃO está no envelope do sinal.** Eu tinha escrito que a composição
do universo no instante ficava gravada e que a estratificação era executável sobre a coorte já
coletada. **Não é.** Sem o ranking congelado por sinal, reconstruir a faixa exige juntar com o estado
**atual** de `markets` — e um mercado que era rank 40 na decisão e virou rank 10 depois teria o seu
resultado atribuído ao terço errado. Isso não é imprecisão; é atribuição inválida.

Para `spread_pct`, o envelope da `volume_anomaly_v1` não carrega book, então só resta aproximar por
snapshots externos — e essa aproximação tem quatro armadilhas, todas verificadas no código:

- o *sampler* **arredonda a observação para o minuto** e não preserva o horário exato nem o timestamp
  da cotação (`market-worker/sampling.py:189`, `hunter_core/db/models/market_data.py:64`). Filtrar
  por `ts <= decision_at` pode, por isso, **aceitar um snapshot do futuro**: decisão às 12:00:05,
  coleta às 12:00:40, gravado como 12:00:00;
- `spread_pct` ali é **fração**: 2 bps são `0,0002` (`sampling.py:72`);
- os 2 bps assumidos são spread **total**, e o preço sintético aplica **metade** disso mais 5 bps de
  slippage por lado (`strategy-worker/pricing.py:35`);
- a entrada planejada é na abertura **seguinte** à decisão (`strategy-worker/plan.py:94`), então
  spread na decisão não é spread na entrada nem na saída.

## Hipótese testável no Lab

**H-KB0016a — retirada como entrega retrospectiva.** A estratificação por faixa de liquidez **não é
executável** sobre a coorte já coletada, pelo motivo acima. O que ela vira é um **requisito de
proveniência para coleta futura**: gravar no envelope de cada sinal o **ranking do mercado**, o
**tamanho e a regra do universo** e o **timestamp do refresh** — a composição completa pode ser
referenciada por um snapshot imutável em vez de copiada em todo sinal. Sem isso, nenhuma análise por
faixa de liquidez é defensável, hoje ou depois.

**H-KB0016b — reduzida a auditoria de cobertura e distribuição do spread, sem terços.** Antes de
qualquer análise de custo: quantos instantes de decisão têm um snapshot de book **inteiramente
anterior** disponível, com que **idade máxima declarada**, e qual a distribuição de `spread_pct`
nessa população — com **caudas e proporção acima de 2 bps**, não só mediana, porque a mediana esconde
os episódios caros.

**O que essa auditoria NÃO permite concluir:** que os custos assumidos são otimistas. Cenário que
mostra por quê: spread real de 4 bps com slippage zero custa 2 bps por lado, contra os 6 assumidos —
o componente de spread está subestimado e o **total** não está. Spread observado também não diz nada
sobre os 5 bps de slippage. Qualquer leitura de custo a partir disso é **sensibilidade declarada**,
nunca execução observada.

**Nenhuma variante de estratégia nesta nota**, pela mesma razão de antes: os efeitos citados vivem em
segundos e o nosso horizonte são 2 h.

## Por que pode falhar

- **Somar dois artigos que medem coisas diferentes** — o erro que a revisão desta nota corrigiu.
- **Extrapolar em cadeia:** volume → liquidez → informação → expectancy → 2 h. São quatro relações
  não demonstradas encadeadas; foi assim que eu concluí que o top-50 seria "onde há menos sinal".
- **Atribuição de faixa por ranking atual** em vez do ranking do instante.
- **Snapshot arredondado ao minuto tratado como anterior à decisão.**
- **"Expectancy plana refuta"** — num dia com poucos resultados, médias próximas e intervalos amplos
  não demonstram ausência de efeito; e um único ativo dominando um terço faria a rentabilidade dele
  ser atribuída à liquidez.
- **Números de retorno com unidade não fixada** — motivo pelo qual não os transcrevi.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0016-fluxo-estado.md`. **Cinco must-fix, todos aceitos, e dois deles
retiraram entregas inteiras da nota:**

1. **"Ranking e composição gravados no envelope" e "executável sobre a coorte já coletada" saem.** É
   simplesmente falso, e o cenário de falha é atribuição inválida (rank 40 na decisão, rank 10 no
   join de hoje). H-KB0016a virou requisito de proveniência para coleta futura.
2. **"Confirma os artigos" / "expectancy plana refuta" saem** — poucos resultados num dia produzem
   médias próximas e intervalos amplos.
3. **Snapshot do mesmo minuto não é informação comprovadamente anterior** (`sampling.py:189`,
   `market_data.py:64`). Exige bucket inteiramente anterior, idade máxima declarada e cobertura
   explícita.
4. **Spread mediano acima de 2 bps não implica custo total otimista** — o exemplo dela (4 bps de
   spread com slippage zero contra 6 bps assumidos) está no corpo.
5. **A leitura numérica do segundo preprint estava errada**: os ARC aparecem sem `%` e, pela equação
   como fração, teriam escala cem vezes maior; o maker de BTC tem ARC positivo; e os p-valores
   alternam a hipótese testada. **Cortei os números.**

Correções de contexto que ela acrescentou: o universo tem padrão **200** com allowlist/blocklist
(`settings.py:128`, `universe_repo.py:195`), então "top 50" descreve um override, não o Lab; e a
minha inferência sobre o top-50 é extrapolação que atravessa quatro relações não demonstradas —
inclusive porque o 2602.00776 seleciona por **capitalização**, não por volume.

**Divergência:** nenhuma. Também aceitei o *nice-to-have* de reportar cobertura, mercados e dias por
faixa, concentração por ativo e intervalos que respeitem dependência temporal.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] · [[EXP-0002-volume-anomaly-v1]] ·
[[Regime]] · [[Features]] · [[Market Collector]]

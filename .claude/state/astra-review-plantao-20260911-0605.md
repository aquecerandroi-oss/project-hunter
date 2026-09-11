**RESUMO**
Como `quant-engineer`, testaria **D-P22 primeiro, como continuação da D-P19**; depois D-P14 e D-P18. A prioridade é medir quanto das oportunidades cabe numa carteira ao longo do tempo.
A novidade exige entradas e saídas sequenciais, capital ocupado, cortes e custos por tamanho. Só repetir `participação × volume` com outra grade acrescenta pouco: a D-P19 já varia participação e capital ([nota:258](C:/dev/project-hunter/.claude/state/notes-D-P19.md:258)).

**ARQUIVOS**
Nenhum criado ou modificado; nenhum commit.

**TESTES**
Não executei testes nem replay. Conferi arquivos locais e fontes primárias; os resultados da D-P19 são evidência registrada, não reproduzida nesta revisão.

**MUST-FIX**

- **D-P22 precisa preservar causalidade e orçamento compartilhado.** Dimensionar na abertura usando o volume final daquele minuto antecipa informação; conceder 1% a cada ordem multiplica a capacidade. Usaria a referência causal e o consumo/reservas móveis de 60 s do [contrato:361](C:/dev/project-hunter/docs/RISK_ENGINE.md:361); o sizing já desconta participação usada ([sizing.py:174](C:/dev/project-hunter/packages/risk-core/hunter_risk/sizing.py:174)). `quote_volume × participação` produz notional; quantidade exige conversão pelo preço.
- **LEAN não equivale ao Zipline em corte de quantidade.** `GetSlippageApproximation` limita o *share usado no preço* e devolve slippage; não reduz o fill (`VolumeShareSlippageModel.cs:77–84`). Cenário: ordem enorme recebe impacto saturado e continua preenchida integralmente pelo fill model. [Código oficial](https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Orders/Slippage/VolumeShareSlippageModel.cs).
- **O comprimento do Jesse está publicado:** média padrão **10 barras**, 2.000 simulações por padrão; a KB-0084 já registra isso. O Freqtrade usa teste t bilateral com hipótese iid, portanto não é outro motor adotando blocos. Confundir os dois justificaria indevidamente o nulo da D-P18. [Jesse](https://docs.jesse.trade/docs/rule-significance-testing/bootstrap), [Freqtrade](https://www.freqtrade.io/en/stable/backtesting/).
- **“R$394/dia é teto” precisa virar “cenário com todas as apostas a +1R”.** Não é limite matemático se houver ganhos superiores a 1R; tampouco 30 entradas/dia é máximo quando posições saem antes de quatro horas — ressalva da própria [D-P19:363](C:/dev/project-hunter/.claude/state/notes-D-P19.md:363). Usar esses números como impossibilidade estrutural descartaria universos por premissa.
- **Cruzar não comprova execução maker.** Exigiria ordem passiva já presente antes do cruzamento, tamanho disponível, validade e tratamento da sequência intrabar. Caso contrário, o replay concede taxa maker a uma entrada que chegou depois. p=0,95 é sensibilidade sem calibração de fila ou seleção adversa. [Nautilus](https://nautilustrader.io/docs/latest/concepts/backtesting/fill-models/).

**NICE-TO-HAVE**
Reportaria cortes por participação separadamente das demais recusas, notional sobrevivente, **1R monetário e PnL líquido distintos**, ocupação e saídas parciais; cobertura SPOT própria, sem substituir pelo volume perpétuo.

**O QUE EU FARIA DIFERENTE**
**Impacto quadrático:** serve como curva de estresse; não há nessa fonte calibração para nosso minuto cripto, nem comprovação da origem “2012”. `0,1×share²` implica **0,10 / 0,625 / 2,50 bp** por execução em 1% / 2,5% / 5%. [Zipline, slippage.py:223](https://raw.githubusercontent.com/stefan-jansen/zipline-reloaded/main/src/zipline/finance/slippage.py).
Compararia as curvas no **mesmo notional**, declarando volume de minuto versus ADV; ambos os coeficientes precisam de calibração. Separaria spread, travessia do livro, impacto e atraso para evitar custo duplicado.
**Quantos vigiar:** escolheria pelo ganho marginal de oportunidades executáveis e informação, sujeito a cobertura, latência e recursos; executaria pelo ganho líquido marginal da carteira, considerando simultaneidade e dependência entre mercados. Um mercado pode informar regime sem receber capital.
Testaria universos progressivos escolhidos no treino e avaliados fora dele, permitindo escolher nenhum. “Só BTC/ETH comportam certo tamanho” não demonstra que só eles merecem observação.

**CONCORDO COM**
D-P18 com blocos conjuntos entre mercados, comprimento escolhido no treino e sensibilidade estacionária; bootstrap de nulo exige centralização, não apenas blocos aleatórios.
Isolar replay é coerente com o [Nautilus](https://nautilustrader.io/docs/latest/concepts/architecture/), mas a restrição de estado global dele é analogia arquitetural, não validação empírica da T3.80. Defaults e exemplos não demonstram superioridade nem capacidade executável.

**OBSIDIAN**

- **Hipoteses-do-plantao** — tratar D-P22 como extensão sequencial da D-P19; corrigir causalidade, orçamento compartilhado e critérios de universo.
- **Plantao/2026-09-11** — corrigir LEAN, comprimento publicado do Jesse e linguagem de “teto”; a KB-0084 já contém a informação correta.
- **KB-0070 — A tabela de capacidade** — distinguir mercados observados, mercados executáveis e contribuição marginal à carteira.
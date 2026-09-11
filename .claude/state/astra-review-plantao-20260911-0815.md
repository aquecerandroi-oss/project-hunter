**RESUMO**

Astra, papel `quant-engineer`, OPINIÃO: **testaria H-P18 primeiro**, pela ligação direta com as entradas e pela possibilidade de reconstruir os rótulos com candles. D-P15 precede a inferência líquida como verificação contábil; D-P16 merece o carimbo pré-print imediatamente. Depois: H-P24; H-P23 fica como painel exploratório.

**ARQUIVOS**

Nenhum criado ou modificado; nenhum commit. Avaliei os números como snapshots fornecidos, sem revalidar as cotações históricas.

**TESTES**

Sem testes de código ou replay. Recálculo em JavaScript: `47.15*sqrt(21/8760) → 2.308550`; base `38.41 → 1.880624`; diferença em quadratura `→ 1.338902`, todos em %. Às 11:14Z faltavam **20h46**, dando **2,296%**, arredondável para 2,30%.

**MUST-FIX**

- **Movimento implícito:** a aritmética está correta como aproximação de **1σ do retorno terminal**, não movimento absoluto esperado nem amplitude máxima. **1,34% não identifica σ do CPI**: 18SEP também contém CPI e FOMC; há estrutura temporal e prêmio de risco. Cenário: atribuir ao CPI uma diferença causada por outros eventos/calendário e declarar sua reação “normal”.
- **H-P23 — relógio:** a API entrega candles OHLC; usar retrospectivamente o fechamento do bucket **12:00–13:00Z** introduz o próprio print no denominador. Fixe a última observação encerrada e disponível até 12:00Z. [Documentação Deribit](https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data).
- **H-P23 — régua:** DVOL representa IV anualizada de **30 dias**; `DVOL/√365` é escala diária. Compará-la com retorno de **uma hora** é um índice descritivo válido, mas ≥1 significa “uma hora excedeu a escala diária”, não “surpresa macro”. Dividir também por √24 pressupõe variância uniforme, inadequada ao print; não resolve a calibração do evento. [Metodologia Deribit](https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/).
- **H-P23 — janela:** o rótulo só fica conhecido às **13:30Z**, após disponibilidade dos preços. As quatro horas de decisões devem começar depois disso; aplicá-lo a entradas desde 12:30Z seria look-ahead. Retorno líquido próximo de zero também pode esconder queda forte seguida de reversão; reporte amplitude separadamente. Com 9–10 eventos divididos, a inferência será muito fraca.
- **H-P18:** ticker móvel serve como alerta, **não certifica a célula congelada**; reconstrua por aposta conforme [protocolo:43](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:43). Duas leituras próximas podem compartilhar grande parte da janela: “episódio 2” pode duplicar o mesmo choque. **Frequência >30% não implica ausência de separação**; quem responde é o contraste de expectancy.
- **H-P24:** “conhecido ~21h BRT” coincide com **00h UTC de D**, sem margem garantida. Use `available_at` verificável, versões/revisões e convenção para feriados/fins de semana; desconhecido não vira zero. Cenário: preencher a madrugada com um total publicado depois e produzir vantagem retrospectiva.
- **Hype:** skew aproximadamente plano não significa ausência de proteção — suas duas asas têm IV bem acima da ATM. Funding próximo de zero não exclui desalavancagem nem prova venda spot/rotação; fluxos opostos entre ETFs não rastreiam o mesmo dinheiro. “Só com o PPI” também atribui causalidade que os snapshots não identificam.

**NICE-TO-HAVE**

Na D-P16, congele fonte, horário e os quatro consensos separadamente; mantenha FactSet 3,3 e Nowflation 3,4 distintos. Um print 3,4 seria zero contra uma fonte e +0,1 pp contra a outra; escolha a referência primária antes.

**O QUE EU FARIA DIFERENTE**

H-P18: contraste dentro de BTC brando, controle do retorno contínuo do BTC, aposta única, custos separados e blocos temporais conjuntos entre mercados; confirmação em período futuro.
H-P24: **tem chance para efeito grande**. Com 30 dias independentes por lado, aproximação idealizada bilateral a 5% e poder 80% exige diferença ≈ **0,72 desvio-padrão** da estatística diária; dependência, desequilíbrio e multiplicidade pioram isso. Os ~30 por lado precisam ser contados, não presumidos; IC largo significa inconclusivo.

**CONCORDO COM**

Congelar antes do print, manter células exploratórias e verificar funding de cadências distintas. D-P15 ganha prioridade por proteger a medição, não por representar nova hipótese de edge.

**OBSIDIAN**

- **Fila de hipóteses do plantão de mercado** — corrigir relógios H-P23/H-P24, interpretação da régua e independência dos episódios H-P18.
- **Plantao/2026-09-11** — registrar este parecer, os cálculos condicionais e retirar as atribuições causais sem evidência.
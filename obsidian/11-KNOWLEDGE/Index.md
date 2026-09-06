---
tags: [knowledge, indice]
updated: 2026-09-06
status: em construção
---

# Conhecimento — índice

Base de conhecimento **externo** do projeto: estratégias de trade, análise técnica, microestrutura de mercado, perpétuos de cripto (funding, open interest, liquidações), gestão de risco e estatística de backtest. Curada pela Sexta-feira com a Astra revisando cada hipótese. Regras em `.claude/agents/sexta-feira.md` (seção "Knowledge acquisition").

Cada nota é uma síntese própria (nunca cópia), com fonte, data, qualidade da evidência e uma **hipótese testável no Lab**. O que vira candidato de estratégia entra em [[Strategy Backlog]]; toda variante que for rodada entra antes em [[Registro de Tentativas]]; o que vira experimento aparece em [[Experiments Index]].

## Temas
| Tema | Notas | Status |
|---|---|---|
| Momentum e rompimentos | KB-0001, KB-0002, KB-0003, KB-0004, KB-0006 | primeira rodada feita (2026-09-06) |
| Volume e fluxo de ordens | KB-0009, KB-0011, KB-0012, KB-0013, KB-0014, KB-0015, KB-0016, KB-0018 | segunda rodada feita (2026-09-06) |
| Perpétuos: funding, OI, posicionamento | KB-0008, KB-0017, KB-0019, KB-0020, KB-0021, KB-0022, KB-0023, KB-0024, KB-0025, KB-0026 | **terceira rodada feita (2026-09-06)** |
| Análise técnica clássica (o que tem evidência e o que não tem) | KB-0003 | iniciado |
| Regime de mercado e volatilidade | KB-0007, KB-0016, KB-0027, KB-0028, KB-0029, KB-0030, KB-0031, KB-0032, KB-0033, KB-0034, KB-0035 | **quarta rodada feita (2026-09-06)** |
| Gestão de risco e sizing | KB-0005, KB-0035, KB-0040 | iniciado |
| Estatística de backtest (overfitting, look-ahead, custos) | KB-0010 | iniciado |
| Execução e microestrutura do preenchimento | KB-0036, KB-0037, KB-0038, KB-0039, KB-0040, KB-0041, KB-0042, KB-0043, KB-0044 | quinta rodada feita (2026-09-06) |
| Livros de estratégia | KB-0045, KB-0046, KB-0047, KB-0048, KB-0049, KB-0050, KB-0051, KB-0052, KB-0053, KB-0054, KB-0055 | sexta rodada feita (2026-09-06) |
| Meme coins | KB-0056, KB-0057, KB-0058, KB-0059, KB-0060, KB-0061, KB-0062, KB-0063, KB-0064, KB-0065 | **sétima rodada feita (2026-09-06)** |

## Notas
_(uma linha por nota: link para a nota — fonte curta — qualidade da evidência — hipótese sim/não)_

| Nota | Tema | Fonte curta | Evidência | Hipótese |
|---|---|---|---|---|
| [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] | momentum | Jegadeesh & Titman 1993; Moskowitz, Ooi & Pedersen 2012 | estudo revisado | sim — gate de tendência `return_4h > 0` |
| [[KB-0002-momentum-e-reversao-em-cripto]] | momentum em cripto | Dobrynskaya (WP); Wen, Bouri, Xu & Zhao 2022 | estudo revisado / working paper | sim — filtro de impulso recente excessivo |
| [[KB-0003-rompimento-de-canal-e-data-snooping]] | rompimento | Lukac/Brorsen/Irwin 1988; Park & Irwin 2007; Hudson & Urquhart 2021 | revisão de literatura | sim — família 10/20/40 publicada inteira |
| [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] | rompimento | George & Hwang 2004 | estudo revisado | sim — `distance_from_24h_high ≥ −0,005`, após medir redundância |
| [[KB-0005-stops-quando-eles-param-perdas]] | risco / saída | Kaminski & Lo 2014 | estudo revisado | sim — braços `STOP-A/B/C` |
| [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] | saída (candidata #1) | síntese própria sobre EXP-0001 + Kaminski & Lo | dado próprio, inconclusivo por limiar | sim — braços `INV-A/B/C/E` |
| [[KB-0007-atr-e-escala-por-volatilidade]] | volatilidade | Wilder 1978; Harvey et al. 2018 | estudo revisado / texto de praticante | sim — análise estratificada por decil de ATR% |
| [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | perpétuos / custos | documentação da Binance + aritmética própria | documentação + cálculo verificado | sim — piso de custo `atr_pct_min = 0,0089` |
| [[KB-0009-o-efeito-do-quarto-de-hora]] | microestrutura | arXiv 2607.09426 | preprint | sim — H1 diagnóstico de timing, H2 atraso de execução |
| [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] | estatística de backtest | Bailey, Borwein, López de Prado & Zhu | estudo revisado | não — é regra de protocolo |
| [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] | volume | Karpoff 1987; Gervais, Kaniel & Mingelgrin 2001 | estudo revisado (associação **contemporânea**) | sim — H-KB0011, retorno de preço a horizonte fixo com grupo `not_triggered` |
| [[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] | microestrutura / book | Cont, Kukanov & Stoikov 2014; Cont, Cucuringu & Zhang 2023 | estudo revisado | sim, **só diagnóstica** — a candidata de filtro foi retirada na própria nota |
| [[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] | fluxo / risco | Easley-LdP-O'Hara 2012; Andersen & Bondarenko 2013–2014; réplica | **disputada** (4 textos) | sim — diagnóstico do denominador de 288 barras |
| [[KB-0014-taker-buy-volume-o-que-temos-medido]] | volume / fluxo | documentação de klines da Binance + medição própria na VPS | documentação + SQL colado | sim — filtro de desequilíbrio agressor, **após observar sem decidir** |
| [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | volume / falso positivo | Gervais et al. (versão de trabalho 1998) + dado próprio | versão de trabalho + dado inconclusivo | sim — H-KB0015a associação; teto `volume_mult_max` exploratório |
| [[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] | fluxo / regime | arXiv 2607.09230; arXiv 2602.00776 | preprint (dois) | sim — requisito de proveniência + auditoria de spread |
| [[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] | perpétuos / liquidações | documentação `forceOrder` da Binance; arXiv 2607.27070 | documentação + preprint + SQL próprio | sim — auditoria de observabilidade da série já coletada |
| [[KB-0018-volume-relatado-e-o-denominador-que-usamos]] | volume / qualidade do dado | Cong, Li, Tang & Yang (arXiv 2021 / MS 2023); Bitwise 2019 | estudo revisado (lido com página) | sim — auditoria de cobertura no instante da decisão |
| [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] | funding / qualidade do dado | documentação de funding e de Mark Price da Binance + nosso código | documentação + leitura de código | sim — observar `funding_kind`, idade e fase do ciclo; depois `time_to_funding_s` |
| [[KB-0020-funding-change-8h-nunca-calcula]] | derivativos / bug | nosso código (`repo.py`, `deriv.py`, `scanner.py`) | leitura de código conferida pela Astra; **SQL não rodado** | sim — diagnóstico com denominador; caminho A (ligar) ou B (desarmar) |
| [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] | funding / base / carry | He et al. (arXiv 2212.06888); BIS WP 1087; Gornall et al.; docs de Mark Price | estudo revisado **lido em resumo** | sim — `premium_pct` e `mark−index` como medidas **distintas**, sem presumir ganho |
| [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] | funding / previsibilidade | Presto Research (Binance USDⓈ-M, 2021–2024) | praticante com método declarado, não revisado | sim — **mas a recomendação é não gastar braço de sombra**; só diagnóstico |
| [[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] | funding / folclore | material de corretora; docs da Binance; nosso `FUNDING_ANOMALY` | **anedótico** | sim — taxa base do detector com grupo de controle, condicionada ao lado |
| [[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] | open interest | Hong & Yogo (JFE 2012); Bessembinder & Seguin (JFQA 1993) | estudo revisado **lido em resumo** / **anedótico** para os quadrantes | sim — quadrantes contra controle por volume agressor; OI em nível como profundidade |
| [[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] | open interest / cascatas | arXiv 2608.03616; arXiv 2607.27070; nosso `detectors.py` | preprints com método declarado | sim — **sem promessa preditiva**; observabilidade do desmonte |
| [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] | funding / método | nosso `funding.py` + contagens da H2 do EXP-0001 | leitura de código + inventário (não é taxa) | sim — separar atravessamento confirmado, inferido e indeterminado |
| [[KB-0027-aglomeracao-de-volatilidade-o-que-ela-licencia]] | volatilidade / persistência | Engle (1982) e Bollerslev (1986) via V-Lab; Cont (2001); Andersen & Bollerslev (1998) | estudo revisado **lido em resumo/documentação** | sim — persistência do nosso estimador horário, com **poder declarado** |
| [[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]] | volatilidade / estimador | Parkinson (1980), Garman & Klass (1980), Rogers & Satchell (1991) — em resumo técnico | estudo revisado (fórmulas em resumo) + código próprio | sim — discordância de rótulo entre estimadores (**sensibilidade**, não precisão) |
| [[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]] | regime / método | Hamilton (1989) — conceito; o texto primário **não abriu** | conceito em fonte secundária + código próprio | sim — duração e transições do par `{trend, volatility}` |
| [[KB-0030-o-regime-nao-chega-ao-sinal]] | regime / proveniência | nosso código + **SQL rodado** | replicado (197 sinais, 0 com `regime_id`) | sim — carimbo de regime no envelope, sem mudar decisão |
| [[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] | regime / operação | nosso `model.py`/`series.py` + **SQL rodado** | replicado (47/480 amostras, 3/20 dias) | sim — curva do warm-up e horas rejeitadas por motivo |
| [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] | volatilidade / sazonalidade | literatura intradiária de BTC (só resumo) + **SQL rodado** | dado próprio **inconclusivo** (2 dias, hora confundida com dia) | sim — mediana por hora UTC e taxa de troca de faixa |
| [[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]] | amplitude / regime | literatura **disputada** + `breadth.py` + **SQL rodado** | disputada / replicado (0 de 48 instantes com cobertura) | sim — publicar a fração incondicional ao lado da conjunta |
| [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] | fator de mercado | Liu, Tsyvinski & Wu (JF 2022) — **só o resumo** | estudo revisado lido em resumo + código próprio | sim — R² e beta contra o BTC; discordância como informação |
| [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] | momentum / risco / custo | Daniel & Moskowitz (2016) em resumo; Barroso & Santa-Clara (2015) **em fonte secundária** | estudo revisado, números de segunda mão | sim — ciclo de trabalho do piso, **no ATR que a estratégia consome** |
| [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] | execução / custo por tamanho | medição própria: 200 livros `depth20` do hot state | **medição própria** (duas leituras, saídas coladas) | sim — declarar `assumed_notional_usd` e diagnóstico `EXEC-A` |
| [[KB-0037-o-spread-assumido-contra-o-spread-medido]] | execução / spread | `market_snapshots` (53 mil observações) + arXiv 2602.00776 | **replicado** (SQL colado); preprint **sem** número de spread | sim — `EXEC-B`, carimbo de spread na decisão |
| [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] | execução / taxas | FAQ de taxas da Binance (tabela **não abriu** sem login) | documentação (número de **exemplo**) + aritmética conferida | sim — `EXEC-C`, sensibilidade a 4 / 4,5 / 5 bps |
| [[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] | execução / tipos de ordem | documentação USDⓈ-M da Binance + nosso `plan.py`/`walker.py` | documentação lida + leitura de código | sim — `EXEC-D`, **descrição de contexto**, não teste de simetria |
| [[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] | impacto de mercado | Donier & Bonart (arXiv 1412.4503); Emilio Said (arXiv 2205.07385) | estudo revisado — **o PDF não abriu para mim; a Astra o leu** | sim — `EXEC-E`, capacidade condicionada à cobertura |
| [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] | execução / risco de tempo | Almgren-Chriss em **fonte secundária** + **SQL rodado** | dado próprio (192 entradas, amostra **selecionada**) | sim — `EXEC-F`, decomposição por entrada |
| [[KB-0042-o-open-nao-e-preco-executavel]] | execução / referência de preço | definição do dado + `pricing.py` + medição própria | leitura de código + medição, sem experimento | sim — `EXEC-G`, erro de referência assinado |
| [[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] | execução / seleção adversa | arXiv 2608.04373v3 — **Hyperliquid**, não Binance | preprint com método declarado, **de outra venue** | sim — `EXEC-H`, retorno entre aberturas (**não** é markout) |
| [[KB-0044-o-que-morre-em-dez-segundos]] | proveniência / qualidade do dado | `market_snapshots` + `hot_state.py`/`universe.py`/`coalesce.py` | **replicado** (contagens exatas) + código conferido | sim — `EXEC-I`, carimbo de execução em registro separado |
| [[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] | rompimento / saída | página pública de regras dos Turtles (Covel); **o documento original não abriu** | anedótico (grupo selecionado por sobrevivência) | sim — **L2**, três políticas `EXIT-BASE/NOTGT/CHAN` |
| [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] | risco / métricas | material aberto do Van Tharp Institute (**o PDF só abriu para a Astra**) | anedótico + aritmética conferida | sim — `D-VT` (roda hoje) e **L1**, alvo assimétrico |
| [[KB-0047-razao-de-eficiencia-de-kaufman]] | tendência / filtro | artigo aberto do próprio Kaufman; docs públicas da KAMA | anedótico (a fórmula é definição, não resultado) | sim — `D-ER` e **L3**, com θ da distribuição condicionada |
| [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | momentum vs reversão / método | prévia aberta de Chan; Lo & MacKinlay para `VR` | backtest do autor + **implicação lógica conferida** | sim — `D-CHAN-a/b/c`; **derrubou a T-001 por redundância** |
| [[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] | validação / estatística | Pardo e Aronson em página de editora e resumo de capítulo | misto — ferramental revisado, livros lidos em resumo | sim — **L5**, benchmark aleatório condicionado (**não** é teste de permutação) |
| [[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]] | sistemático / custos | blog público de Robert Carver | backtest do autor + aritmética **corrigida pela Astra** | sim — `C-COST` (tradução) e `C-FCAST` (score com pergunta prospectiva) |
| [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] | rotulagem / dependência | descrições abertas do método de López de Prado | descrição de método (o livro não foi lido) | sim — `D-CONC`, concentração temporal (roda hoje) |
| [[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]] | filtros / convenção | descrições abertas de meta-rotulagem e barras alternativas | anedótico | sim — `C-META`, convenção de relatório; relógio de amostragem **bloqueado** |
| [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] | base antes do rompimento | descrições públicas de Weinstein, O'Neil (IBD) e Minervini | anedótico (apresentação retrospectiva de vencedoras) | sim — `D-CONTR` e **L4**, contração 8/32 terminando em `t−1` |
| [[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] | trend following / saída | páginas públicas de Andreas Clenow | backtest do autor (**nenhum número dele citado**) | sim — é a **L1**; `target2`/`target3` persistidos e nunca usados como barreira |
| [[KB-0055-douglas-o-livro-que-nao-vira-hipotese]] | processo | descrições públicas de *Trading in the Zone* | anedótico | **não** — nota de leitura, sem linha no backlog nem no registro |
| [[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] | meme / definição e método | arXiv 2512.11850; arXiv 2512.00377 | preprints (resumo) + universo medido | sim — `H-KB0056`, proveniência da marcação |
| [[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] | meme / volatilidade | **medição própria na VPS** (SQL colado) | replicado + preprint em resumo | sim — `D-MEME-ATR` e a candidata **M-A** |
| [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] | meme / execução e custo | `market_snapshots` + 50 livros do hot state | **replicado** (duas medições) | sim — `D-MEME-LIQ`, `D-MEME-CUSTO`; **M-B bloqueada** |
| [[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]] | meme / funding | 2.136 liquidações da VPS + docs da Binance | replicado + documentação | sim — `D-MEME-FUND` e a candidata **M-E** |
| [[KB-0060-correlacao-com-o-btc-e-a-meme-season]] | meme / fator e regime | medição própria (β e R² contra o BTC) | replicado; **a fonte externa não abriu (403)** | sim — `D-MEME-BETA`; **nenhum filtro de regime** |
| [[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] | meme / manipulação | La Morgia et al. (arXiv 2105.00733) | preprint — **o HTML só abriu para a Astra** | sim — `D-MEME-PICO`, redesenhado por ela |
| [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] | meme / listagem e proveniência | código + **stream de universo do Redis** | leitura de código + SQL + 46 eventos | sim — `H-KB0062a/b`, `D-MEME-SAIDA` |
| [[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]] | meme / social e on-chain | arXiv 2512.11850 e 2512.00377 + nosso código | preprints (resumo) + inventário | **não** — depende de flag; nota de leitura |
| [[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] | meme / risco | medição própria (quedas por coorte) | replicado, com a conclusão de cauda **retirada** | sim — `D-MEME-GAP` e a candidata **M-G**; requisitos para o M3/M4 |
| [[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] | meme / momentum vs reversão | `agent_signals` e `signal_outcomes` da VPS | replicado, **abaixo do limiar editorial** | sim, só diagnóstico — `D-MEME-POP`, `D-MEME-ATRPAR` |

## O que a primeira rodada mudou de fato

Três correções factuais sobre o **nosso** código, achadas ao confrontar a literatura com a
implementação, e que valem mais que qualquer citação: `return_24h` **não existe** (o teto é
`return_4h`); `rvol` usa **mediana**, não média; e a entrada da `momentum_v1` **não** cai na janela
de 10 segundos do quarto de hora — cai no minuto seguinte. As três estão nas notas correspondentes.

## O que a segunda rodada mudou de fato

O tema era volume e fluxo de ordens, e o saldo mais útil de novo **não** foram as citações — foram
seis fatos sobre o nosso próprio sistema, todos verificados com comando ou com linha de código:

1. **`taker_buy_volume` tem cobertura de 100%** no banco da VPS (519.422 velas de 1 min, 222
   mercados, zero linhas inconsistentes) — fecha a pendência que a [[KB-0009-o-efeito-do-quarto-de-hora]]
   tinha deixado aberta. O campo **chega** ao `StrategyContext` e é **descartado no `_fold`** da
   agregação (`aggregate.py:40,77`): faltam um campo num dataclass e uma linha de soma, não coleta.
2. **Nós já coletamos liquidações.** 8421 eventos em 197 mercados na VPS
   (`ingest.py:62` → `persist_rows.py:217`). Eu tinha escrito uma nota inteira supondo que não.
3. **E o parser delas tem um defeito de semântica:** usa `q × p` (quantidade **original** × preço da
   ordem) em vez do executado (`z`, `ap`), então a soma de `notional` **não é** limite inferior do
   executado. Vai para [[Open Bugs]].
4. **`covered_until` deixou de ser o bloqueio** de `buy_pressure_5m` / `trade_velocity_1m`: o
   publicador e o consumidor existem na árvore (`market-worker/coverage.py:153`,
   `scanner-worker/context.py:96`). A disponibilidade operacional continua **não medida**.
5. **O ranking do mercado no instante da decisão NÃO está no envelope do sinal.** Isso torna
   inexecutável qualquer estratificação retrospectiva por faixa de liquidez, e vira requisito de
   proveniência para coleta futura.
6. **`volume_ratio_5m` e `relative_volume_5m` diferem por 288 (24 h) contra 23 (115 min)** e pelo
   alinhamento — não por "contígua contra disjunta", como eu tinha escrito. E a *baseline* sazonal da
   T2.3 é uma terceira camada, não um terceiro denominador.

E um saldo de método: **a Astra derrubou duas entregas inteiras** desta rodada (o filtro de book da
KB-0012 e a estratificação retrospectiva da KB-0016) e reformulou a hipótese central de outras três.
Todas as correções estão na seção "Segunda opinião (Astra)" de cada nota.

## O que a terceira rodada mudou de fato

Tema: funding, open interest e posicionamento em perpétuos — o bloco de features do M2 que nenhuma
estratégia em sombra usa. O saldo, de novo, foram fatos sobre o **nosso** sistema.

1. **O bloco de derivativos não é "não usado": ele não computa.** `load_deriv_history`
   (`scanner-worker/repo.py:66`) **não tem nenhuma chamada** em produção, então
   `Scanner.deriv_history` fica sempre vazio e `funding_change_8h`, `open_interest_change_1h` e
   `open_interest_change_4h` são `missing_input` em toda barra. Consequência: o detector
   `OPEN_INTEREST_SPIKE` está **armado e mudo** — não desarmado com motivo, como os outros dois.
   Achado da Astra; verifiquei por conta própria antes de publicar.
2. **`DetectorSide.UP` não é "cresceu": é "acima da mediana"** (`severity.py:107`). O detector de OI
   ignora **desvios negativos da linha de base** — e é exatamente aí que mora o desmonte.
3. **O `FUNDING_ANOMALY` também não mede o que o nome sugere.** Mede distância da mediana daquele
   mercado naquela hora, então um funding **positivo anormalmente baixo** dispara. Não é detector de
   funding extremo.
4. **`mark_price` embute o funding por construção** — o Mark Price da Binance é mediana de três
   candidatos, e um deles é o índice ajustado pela última taxa vezes a fase do ciclo. Isso não
   invalida `mark − index` como medida, mas proíbe tratá-la como prêmio independente.
5. **A cadência de liquidação não é fixa:** comprime para 1 h no teto/piso e volta a 4 h após 16
   ciclos abaixo de ±0,025%. O nosso `_cadence()` toma a **moda** do histórico, então um instante
   "devido" pode ser **fictício** — e "excluído por `funding_missing`" significa atravessador
   **inferido**, não confirmado.
6. **`market_snapshots` não preserva `funding_kind` nem `next_funding_time`**, o que inviabiliza a
   correção óbvia do item 1 para funding, e a sua chave é o **minuto alinhado** da leitura
   (`sampling.py:190`), o que cria risco de look-ahead em qualquer análise retrospectiva mal
   recortada.

Saldo de método: **a Astra corrigiu erro de leitura de fonte em três notas** (o teste da Presto é de
BTC sobre a *variação* do funding, não do nível no top 50; os 88%/63%/λ das cascatas são de um estudo
de caso, não dos sete eventos; "a literatura rejeitou a previsão" era falso) e derrubou duas
inferências minhas inteiras (a taxa de atravessamento de ~13% e a duração média de 1 h derivada
dela).

## O que a quarta rodada mudou de fato

Tema: regime de mercado e volatilidade — o que decide se as candidatas das três rodadas anteriores
valem em todo lugar ou só num regime. **A resposta é que hoje a pergunta não pode ser feita**, e
esta é a primeira rodada em que houve SQL executado (instância local; a VPS continua recusada pelo
portão de permissão).

1. **O regime não chega ao sinal.** `agent_signals.regime_id` existe, está indexada, e o
   `strategy-worker` nunca a escreve — a palavra `regime` não aparece no worker. Medido: **197
   sinais, 0 com `regime_id`**. Toda estratificação por regime é retrospectivamente inexecutável, do
   mesmo jeito que o ranking de liquidez da segunda rodada.
2. **E não haveria o que carimbar.** O `regime_v0` está mudo **por construção**: exige 480 amostras
   horárias em 20 dias distintos, e o banco tem **47 horas em 3 dias**. `market_regimes` tem uma
   única linha, `global`/`UNKNOWN`. Faltam ~18 dias de coleta ininterrupta, e cada gap de um minuto
   na fronteira mata a hora inteira.
3. **O rótulo `global` é, literalmente, o BTCUSDT.** `RegimeScope.BTC` existe no enum e **nunca é
   usado**; `classify_market_trend` está exportada e **não tem chamada em produção**; e
   `btc_correlation_1h`, `market_beta_1h`, `relative_strength_vs_btc_1h` estão em `docs/PIPELINE.md`
   e **não existem** no código.
4. **A nossa amplitude não é uma linha de avanços** — é a conjunção `return_4h > 0` **E**
   `relative_volume_1h > 1,5`. Isso cria uma assimetria real em `_confidence`: num mercado calmo a
   fração tende a zero, então `BULL` é rebaixado a 0,6 e `BEAR` promovido a 1. A amplitude não está
   discordando do touro; está medindo que não há volume. Medido: **0 de 48 instantes** com cobertura
   de 80%; 100% das leituras de `return_4h` indisponíveis.
5. **Há um relógio dentro do limiar de volatilidade.** A referência é a mediana de 30 dias que
   **mistura todas as horas UTC**, enquanto a janela corrente é de uma hora específica. Medido no
   BTCUSDT: 1,08 bps na hora mais calma contra 3,17 bps na mais agitada. **Inconclusivo por
   construção** — dois dias, e hora confundida com dia —, mas o formato bate com a literatura.
6. **O piso de custo pode ser um filtro de regime.** `atr_pct_min = 0,003` é um piso **absoluto**
   sobre uma quantidade cuja distribuição respira; e a resposta da literatura à alta volatilidade é
   **escalar** exposição, não **filtrar** entrada — distinção que o nosso desenho apaga.
7. **`confidence` pode ser nula**, durante transição pendente, e **"três leituras" não são "três
   minutos"**: o contador é de leituras, não de tempo.

Saldo de método: **a Astra derrubou quatro afirmações minhas** — a razão de variâncias escrita na
escala da soma, o diagnóstico de que `gap` prova a ausência da vela de 240 minutos, a hipótese que
mediria o piso da `momentum_v1` com o ATR do M2, e a apresentação da razão 0,505–2,245 como se fosse
leitura do sistema (com 47 amostras o classificador não calcula razão nenhuma). Também exigiu que as
consultas morassem nas páginas, o que faltava em três notas.

## Fontes que não abriram nesta rodada (quarta)

| Fonte | O que aconteceu | Como contornei |
|---|---|---|
| `www-stat.wharton.upenn.edu/.../BollerslevReview.pdf` (survey ARCH) | conexão recusada | usei a documentação do V-Lab (NYU Stern) para GARCH(1,1) |
| `econweb.ucsd.edu/~jhamilto/palgrav1.pdf` (Hamilton, resenha do autor) | **certificado expirado** | conceito lido em fontes secundárias; a nota declara |
| `kentdaniel.net/.../jfe_16.pdf` (Daniel & Moskowitz) | PDF voltou binário ilegível | resumo do NBER w20439; **nenhum número do artigo entrou** |
| `faculty.washington.edu/.../AndersenBollerslevIER1998.pdf` | PDF ilegível (streams comprimidos) | argumento lido em resumo; **nenhum R² citado** |
| `ledgerjournal.org/.../213` (intraday behavior of Bitcoin) | PDF ilegível | resumos de busca; a nota se apoia na **nossa** medição |
| `rama.cont.perso.math.cnrs.fr/pdf/clustering.pdf` (Cont) | certificado não confere com o host | fatos estilizados em resumo; declarado |
| `sciencedirect.com/.../S0264999319312982` (breadth) | HTTP 403 | **nenhum número de tamanho de efeito** entrou na KB-0033 |
| Busca por evidência acadêmica de stops por ATR | só retornou material de fornecedor (LuxAlgo, VolatilityBox, TradersPost) com números sem fonte ("34% menos stops", "28% melhor") | **nada disso foi citado**; registrado aqui como o que a busca produziu |

E a limitação operacional da rodada: **o `psql` na VPS foi recusado de novo** pelo portão de
permissão da sessão, então todos os números são da **instância local**, que tem 3 dias de história e
um scanner reiniciado há menos de uma hora. Nenhum deles descreve produção.

## Fontes que não abriram na terceira rodada

Registradas porque uma nota que cita o que não leu é pior que uma nota a menos:

| Fonte | O que aconteceu | Como contornei |
|---|---|---|
| `arxiv.org/pdf/2212.06888` (He et al.) | PDF voltou binário ilegível | li o **resumo** em `arxiv.org/abs`; a nota declara isso |
| `bis.org/publ/work1087.pdf` (Crypto carry) | HTTP 404 pela ferramenta | li o resumo via RePEc |
| `mdpi.com/2227-7390/14/2/346` (funding rate markets) | HTTP 403 | **não citada em nota nenhuma** |
| `sciencedirect.com/...S0304405X12000657` (Hong & Yogo, JFE) | HTTP 403 | li o resumo na NBER (w16712); o número mensal por desvio padrão **saiu** por não ser conferível |
| `jstor.org/stable/2331149` (Bessembinder & Seguin) | paywall | li resumo e ficha bibliográfica; a nota declara |
| `arxiv.org/abs/2510.14435` (carry, Sharpe por subperíodo) | resumo não traz os números | **nenhum número dele entrou** nas notas |

E uma limitação operacional que atravessa quatro notas: **nenhuma consulta SQL foi executada nesta
rodada.** O portão de permissão desta sessão recusou `psql` na VPS e o Docker local está fora, então
as previsões sobre `missing_input`, disparos e populações são **leitura de código**, não medição.

## O que a quinta rodada mudou de fato

Tema: **execução e microestrutura do preenchimento** — a última peça antes do M4. A pergunta era
"quanto custa executar?", e a resposta honesta é **não sabemos, e não dá para saber com o que está
gravado**. Foi a rodada com mais medição própria e, de longe, com mais erros meus corrigidos pela
Astra.

1. **O contrato de custo não tem tamanho.** `AssumedCosts` congela `spread_bps`, `slippage_bps`,
   `fee_bps` e `max_entry_delay_s` — e nenhum notional. Sem isso, "6 bps por lado" não tem medição
   capaz de contrariá-lo. Medido nos 200 livros de 20 níveis do hot state: atravessar o ask custa
   **2,53 bps** para 500 USDT, **3,47** para 1.000, **6,85** para 5.000, **10,65** para 20 mil — e
   **68 dos 200 livros não comportam** 20 mil. O notional mediano no melhor ask é **352 USDT**.
2. **O spread não é o elo fraco.** Mediana medida de **2,30 bps** contra 2 assumidos: erro de
   **0,30 bps na ida e volta**, 1,5% do custo total. A dispersão entre decis é grande (0,97 no decil
   10, 4,93 no decil 1), mas entra pela metade no modelo. Quem carrega o peso é `slippage_bps`, e
   ele é justamente o que ninguém mediu.
3. **O maior número da rodada não é custo: é relógio.** Entre o fechamento da barra de referência e
   a abertura da barra de entrada, o preço se desloca **14,4 bps** (momentum) e **15,0** (volume) em
   mediana absoluta, com p90 de 44,1 e 49,6 — contra 6 bps de custo assumido por perna. Mediana
   assinada ~zero. E 19 dos 216 sinais nem entraram, recusados por `late:delay`.
4. **A taxa de 4 bps não é nem o maker nem o taker do exemplo da Binance** (2 e 5 bps; 4,5 com BNB).
   Diferença de 1 a 2 bps na ida e volta, na direção que favorece a estratégia — e que, sendo
   aritmética, **não pode** explicar uma expectancy negativa.
5. **A sombra tem uma política de execução implícita e ninguém a escreveu.** O modelo é
   preenchimento sintético por barras com deslocamento adverso: uma **aproximação de execução
   agressiva**, com preenchimento integral **suposto**, não verificado. Não existe recusa por não
   preenchimento.
6. **`volume_24h` tem 6 linhas em 55.709, e há um defeito de desenho que é mecanismo consistente com
   essa cobertura baixa.** Dois escritores — o refresh REST (`/fapi/v1/ticker/24hr`, que traz volume
   e **não** traz bid/ask) e o `bookTicker` (que traz bid/ask e **não** traz volume) — dividem o
   mesmo hash com o mesmo `TICKER_FIELDS`, e a regra do Lua apaga com `HDEL` todo campo de
   propriedade que vem `None`. Cada escrita apaga a outra. Isso explica a primeira consulta que
   escrevi nesta rodada ter voltado **zero linhas**. **As seis linhas não foram atribuídas
   individualmente ao mecanismo nem à versão do código que rodava** — a explicação é consistente, não
   verificada linha a linha. **Achado da Astra; conferi o caminho inteiro no código antes de
   publicar.**
7. **Do inventário de seis perguntas da [[KB-0044-o-que-morre-em-dez-segundos]], quatro são
   retrospectivamente inexecutáveis, uma é respondível e uma é parcial.** Book vive 10 s e nunca é
   gravado; `bid_qty`/`ask_qty` vivem 30 s e nunca são gravados; só **8 de 200** sinais têm snapshot
   no seu próprio minuto. Respondível: o deslocamento referência→entrada. Parcial: o decil de
   liquidez, que existe atual mas não histórico. **Isso vale para aquele inventário** — fora dele,
   `EXEC-C`, `EXEC-F` e `EXEC-H` também são retrospectivos e rodam hoje.

**Saldo de método — e é o pior da série, no sentido bom.** A Astra recusou a primeira versão de
**todas as nove notas**. Além disso:

- **Abriu o PDF de Donier & Bonart que a minha ferramenta não leu** e derrubou a tese central da
  KB-0040: **61% das metaordens têm uma única ordem-filha**, então "somos ordem única" não isenta
  ninguém; a equação normaliza por volume e volatilidade **diários**; e a medida é impacto de
  **pico**, não permanente.
- **Corrigiu quatro erros aritméticos meus:** 0,15 em vez de 0,30 bps de ida e volta; "p90 < 6
  garante erro máximo de 2 bps" (duas pernas a 5,9 custam 3,9); "15% de 51 bps dá 3,8 bps por lado
  para o book" (7,65 bps totais já consumidos pelas taxas); e a decomposição que somava termos
  sobrepostos para "fechar" em 6 bps.
- **Derrubou três conclusões estatísticas:** "variância, não viés" (quantis não determinam média:
  −1, 0, +100 tem mediana 0 e média +33); "mediana zero encerra a seleção adversa"; e "o efeito de
  14 bps dá poder à H2" (a H2 mede uma diferença **pareada**, cuja variância é outra).
- **Inverteu duas perspectivas minhas:** markout positivo na direção do agressor é adverso para a
  **contraparte passiva**, não para nós; e, numa compra, alta antes da entrada **afasta** do stop e
  piora o preço — eu tinha escrito o contrário.
- **E salvou uma medição:** eu tinha declarado como risco a suposição de que a barra de referência
  fosse de 1 minuto. Ela conferiu que momentum agrega 15 min, volume agrega 5 min, e
  `aggregate.py:86` define `close = minutes[-1].close` — então o `JOIN` em −1 minuto está **certo**,
  e "consertá-lo" introduziria o erro.

**Nenhuma candidata de estratégia saiu desta rodada, e isso é o resultado.** Saíram duas mudanças de
contrato (declarar o tamanho; carimbar a execução em registro separado) e nove diagnósticos, três
dos quais rodam hoje sem pré-requisito nenhum.

## Fontes que não abriram nesta rodada (quinta)

| Fonte | O que aconteceu | Como contornei |
|---|---|---|
| `binance.com/en/fee/futureFee` (tabela de tarifas) | "No records found" sem login | usei o **exemplo** do FAQ 360033544231 (maker 0,02% / taker 0,05%), declarando que é exemplo |
| `arxiv.org/pdf/1412.4503` (Donier & Bonart) | PDF voltou binário ilegível, duas tentativas | **a Astra o abriu** e conferiu equação 1, seção 4.1, tabela I e seção 6; a nota declara que os fatos são leitura dela |
| `smallake.kr/.../optliq.pdf` (Almgren & Chriss, original) | PDF ilegível | conceito em verbete secundário; **nenhuma fórmula do artigo citada** |
| `tandfonline.com/.../14697688.2025.2515933` (latência e seleção adversa em Bybit/Binance) | HTTP 403 | **não citada em nota nenhuma** |
| `arxiv.org/html/2602.00776v1` (microestrutura de cripto) | abriu, mas **não publica número de spread por capitalização** | registrado na KB-0037; nenhum número dele entrou |
| Busca por spread/profundidade em perpétuos por capitalização | devolveu alegações de terceiros ("spread médio < 0,05 bps", "impacto de 0,5 M USD < 0,3 bps") sem que eu conseguisse chegar à fonte primária | **nada disso foi citado** |

Limitação operacional da rodada: todos os números são da **instância local** (24 h de história, 200
mercados monitorados, worker reiniciado na véspera). A VPS não foi consultada. E os livros do book
são de **dois instantes** de uma quarta-feira à tarde — não descrevem stress, que é justamente quando
a `momentum_v1` dispara.

## O que a sexta rodada mudou de fato

Tema: **livros de estratégia**, com um pedido explícito do Everton — não resenha, candidatas que o
Lab consiga testar em sombra. É a primeira rodada desde a primeira que **produz variantes de
estratégia**, e a razão é simples: livros dão regras objetivas.

1. **A `momentum_v1` já é um rompimento de canal — de fechamentos, não de extremos — com filtros
   próprios.** O que ela **não** tem é a saída da família: os Turtles e o trend following sistemático
   não usam alvo fixo. `target_atr = 1,5` fecha o vencedor onde a literatura diz para deixá-lo
   correr. Isso vira as candidatas **L1** e **L2**.
2. **`target2_atr = 3` e `target3_atr = 4,5` são calculados, montados e gravados** (`record.py:137`,
   `persist.py:59`) e o acompanhamento **não os usa como barreiras** (`walker.py:73,157`;
   `tracking_repo.py:102` reconstrói só `virtual_targets[0]`). Nunca soubemos com que frequência o
   preço seguiria até lá.
3. **O payoff nominal no alvo não é 1 R.** Stop e alvo são simétricos **em torno da referência**, e a
   entrada é uma abertura posterior: risco `a + δ`, ganho `a − δ`. Não é descoberta nossa — o mesmo
   exemplo já estava em `SHADOW-LAB.md:13` —, mas a **distribuição** disso nunca foi publicada.
4. **A T-001 morreu por lógica, não por dado.** `close_t > max` dos 20 fechamentos anteriores implica
   `close_t > C_{t−16}`, e 16 barras de 15 min são 4 horas: o gate `return_4h > 0` **já está dentro**
   da condição de entrada. Achado da Astra.
5. **O Lab não tem grupo de comparação.** A única referência é o zero — que continua sendo a
   referência certa para rentabilidade, mas não diz se a seleção do **instante** carrega informação.
   Daí a **L5**, e o cuidado de chamá-la benchmark condicionado e não teste de permutação.
6. **A dependência da amostra não é temporal, é transversal.** `episodes.py` já impede dois
   acompanhamentos no mesmo slot; o que estreita a incerteza artificialmente é tratar cem altcoins
   reagindo ao mesmo movimento do BTC como cem observações. O contrato já pedia blocos de tempo; o
   que faltava era **medir a concentração** (`D-CONC`).
7. **Metade do backlog é a mesma forma:** decisão binária sobre sinais de uma estratégia-base. Isso
   virou a convenção `C-META`, com quatro números obrigatórios — e a descoberta, pela Astra, de que
   duas dessas candidatas (#11 e #12) são sobre a **`volume_anomaly_v1`**, não sobre a `momentum_v1`.
8. **`confidence` é constante e o sistema já diz isso** (`constant_uncalibrated_v1`). O que faltava
   era a consequência: um score contínuo não vinculante **pode** ser avaliado hoje, prospectivamente,
   sem precisar de dimensionamento.

**Saldo de método.** A Astra revisou as onze notas em quatro passagens e recusou a primeira versão de
todas. Além dos itens acima, ela: **derrubou o argumento com que eu tinha rebaixado a minha própria
candidata L2** (a raridade da saída por canal, com contraexemplo numérico dentro das 4 h);
**desmontou a equivalência entre teto de custo em R e piso de ATR** com um contraexemplo aritmético;
**provou que `VR` e `ER` não são a mesma medida** com dois arranjos dos mesmos vinte retornos;
**mostrou que `nº outcomes / nº blocos` mede o inverso do que eu disse**; **corrigiu a álgebra do
payoff** (efeito duplo, não paralelo); e desenhou o **bloco de sete contrastes com Holm** que
organiza T-005, L1 e L2 como uma busca só. A lista completa das treze inferências retiradas está no
[[Registro de Tentativas]].

**E uma limitação que vale para a rodada inteira: nenhum SQL foi executado.** Todos os fatos sobre o
nosso sistema são **leitura de código**, conferida linha a linha pelas duas partes; nenhum é medição.
Os diagnósticos que "rodam hoje" ainda não rodaram.

## Fontes que não abriram nesta rodada (sexta)

| Fonte | O que aconteceu | Como contornei |
|---|---|---|
| `tradingblox.com/originals/turtlerules.pdf` (regras originais dos Turtles) | HTTP 403 | usei a página pública de regras de Covel, que sustenta 20/55 e o `N`; **stop de 2N, canal de saída, piramidação e "sem alvo" ficaram "de memória, a confirmar"** |
| `kaufmansignals.com/matching-the-markets-to-the-strategy/` | HTTP 403 para mim; **a Astra abriu** | a fórmula da `ER` veio de documentação pública concordante (StockCharts, MetaTrader, TradingView) e a atribuição ao artigo do autor foi conferida por ela |
| `vantharp.com/.../A_Short_Lesson_on_R_and_R-multiple.pdf` | PDF voltou binário ilegível; **a Astra abriu** | ela confirmou que o material sustenta risco inicial, R-múltiplos, expectancy e a importância do sizing — e que é material do instituto sobre o simulador deles, **não** prova de leitura do livro |
| Capítulo de resultados de Aronson (conclusão estatística) | o resumo público não expõe o número | a página da editora sustenta "mais de 6.400 regras sobre o S&P 500"; **"quase nada sobrevive" ficou marcado como de memória, a confirmar** |
| Números de meta-rotulagem reportados por fontes secundárias | não verificados por mim nem pela Astra | **saíram inteiramente** da KB-0052 — nem como evidência, nem como contraexemplo |

## O que a sétima rodada mudou de fato

Tema: **meme coins**, com um pedido direto do Everton — estudar para usar no virtual. É a rodada com
**mais medição própria de todas**: 45 h de dados reais na VPS, 200 mercados monitorados, 581 mil
velas de 1 min, 50 livros de 20 níveis do hot state, 2.136 liquidações de funding e o stream de
universo do Redis. E o saldo é quase todo **contra o folclore**.

1. **O rótulo "meme" não separa volatilidade dentro do nosso universo.** Medianas de ATR%(14)
   próximas entre memes (0,84%) e resto (0,83%). Quem se separa é BTC (0,127%) e as majors (0,50%).
   DOGE, PEPE e SHIB ficam na faixa das majors.
2. **`atr_pct_min = 0,003` deixou o BTC fora em 100% das barras medidas, e a `momentum_v1` emitiu
   zero sinais para BTCUSDT.** Se o `D-MEME-ATR` confirmar, ninguém decidiu que o Lab seria um
   laboratório de altcoin — o piso de custo decidiu, e nunca foi lido assim.
3. **O custo por coorte é o que o contrato erra.** Spread mediano de 3,12 bps nas memes contra 2
   assumidos; atravessar 5.000 USDT custa 7,07 bps, mais que os 6 bps de spread + slippage somados;
   3 de 21 livros de meme não comportam 20.000 USDT. Correlação de postos de −0,651 entre ATR% e
   profundidade — **que não demonstra o mecanismo**, como a Astra fez questão de registrar.
4. **"Meme tem funding extremo" é falso na nossa amostra**, e metade da diferença entre coortes é
   **cadência de liquidação** (4 h contra 8 h), não sentimento.
5. **Memes são mais acopladas ao BTC que a altcoin média**, não menos: inclinação mediana 2,80 e R²
   0,152 contra 1,44 e 0,021.
6. **A restrição que organiza tudo:** o `StrategyContext` só carrega velas, funding e open interest
   do próprio símbolo. Nenhum filtro por spread, livro, volume de 24 h **ou por outro mercado** é
   implementável hoje. Isso matou três candidatas antes de elas nascerem.
7. **O primeiro dia de um perpétuo novo é estruturalmente invisível** (aquecimento de 24 h), e não
   gravamos a data de listagem — `markets.metadata` está vazia, e persistir o `onboardDate` exige
   **duas** camadas, não uma.
8. **O universo gira 26% em 20 horas** — 52 entradas e 52 saídas, com 16 símbolos oscilando na
   fronteira do rank 200. Descoberto porque a Astra derrubou a minha afirmação de que o diff estava
   perdido: ele estava no stream do Redis, com 46 eventos.
9. **Vinte e sete sinais em quatorze mercados que já saíram do universo** — viés de sobrevivência
   acontecendo em quinze horas, e que as minhas próprias consultas descartavam em silêncio.

**Saldo de método, e é o mais duro da série.** A Astra recusou a primeira versão das **dez** notas,
em três passagens, e a lista completa das **24 inferências retiradas** está no
[[Registro de Tentativas]]. Além disso ela: **abriu o artigo de pump-and-dump que a minha ferramenta
não abriu** e mostrou que os 25 segundos são tamanho de bloco, não duração do evento; **recuperou um
dado que eu tinha declarado perdido** (o diff de universo no Redis); **derrubou o título de uma nota
inteira** com o meu próprio número (92 de 978 sinais são meme, então "a população do Lab já é meme"
é falso, e o arquivo foi renomeado); **achou um defeito de emparelhamento no meu SQL de beta** (que
refiz, com números idênticos — a correção virou verificação); e **derrubou as duas explicações que
eu tinha dado para o `R > 1` no alvo e para o confundidor de ATR**, mostrando que o efeito real anda
na direção contrária.

**Três candidatas testáveis hoje saíram da rodada** (M-A, M-E, M-G), duas bloqueadas por contrato
(M-B, e a de listagem), duas retiradas por argumento (braço por coorte, detecção de pump) e dez
diagnósticos, cinco dos quais rodam sem pré-requisito nenhum. **Nada foi ativado.**

## Fontes que não abriram nesta rodada (sétima)

| Fonte | O que aconteceu | Como contornei |
|---|---|---|
| `papers.ssrn.com/.../6292920` (desempenho de meme coins 2025-2026) | HTTP 403 para mim **e para a Astra** | os números de correlação diária (0,77-0,78) **saíram inteiramente** da KB-0060 |
| `arxiv.org/pdf/2005.06610` (La Morgia et al., versão ICCCN 2020) | PDF ilegível, duas tentativas | li o resumo; **nenhum número de desempenho dele** entrou |
| `arxiv.org/pdf/2105.00733` ("The Doge of Wall Street") | o PDF não abriu para mim; **a Astra abriu o HTML** | os 317 eventos da Binance, os blocos de 25 s e a validação cruzada vêm da leitura dela |
| Kamps & Kleinberg (2018); Xu & Livshits (2019) | **não abri os textos primários** | citei só o **formato** do argumento; nenhuma fórmula nem número deles |
| Busca por efeito de listagem em perpétuos | devolveu só material de divulgação de corretora | **nada citado**; registrado como resultado da busca |
| Busca por menções sociais como preditor em perpétuos de meme | idem, com números sem fonte | **nada citado** ([[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]]) |

E a diferença operacional desta rodada em relação a todas as anteriores: **a VPS respondeu**. Todos
os números acima são de produção, não da instância local. As limitações são de **janela** (42-45 h,
um regime, sem stress) e de **maturidade** (o Lab tem 15 h de sinais), não de acesso.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Experiments Index]] ·
[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Strategy Performance]] ·
[[Features]] · [[00-HOME]]

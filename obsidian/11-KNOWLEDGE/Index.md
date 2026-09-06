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
| Regime de mercado e volatilidade | KB-0007, KB-0016 | iniciado |
| Gestão de risco e sizing | KB-0005 | iniciado |
| Estatística de backtest (overfitting, look-ahead, custos) | KB-0010 | iniciado |

## Notas
_(uma linha por nota: `[[Título]] — fonte curta — qualidade da evidência — hipótese sim/não)_

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

## Fontes que não abriram nesta rodada

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

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Experiments Index]] ·
[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Strategy Performance]] ·
[[Features]] · [[00-HOME]]

---
tags: [knowledge, nota, perpetuos, open-interest, liquidacoes, anomalias]
tema: Perpétuos: funding, OI, posicionamento
fonte: "Measuring the engine of a liquidation cascade: subcritical branching inside a first-order transition" (arXiv 2608.03616); "Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades" (arXiv 2607.27070); nosso `detectors.py`
fonte_url: https://arxiv.org/abs/2608.03616 · https://arxiv.org/html/2607.27070
lido_em: 2026-09-06
evidencia: dois preprints com dados e método declarados (não revisados por pares); os indicadores que examinaram falharam como alarme universal, o que não é refutação de toda previsão; leitura de código com arquivo e linha
hipotese_testavel: sim — e a hipótese **não promete previsão**
astra: concorda com ressalvas
---

# O nosso detector de open interest só olha para cima — e o fenômeno documentado é para baixo

## O que afirma

`OPEN_INTEREST_SPIKE` (`detectors.py:170`) lê `open_interest_change_1h` com `DetectorSide.UP`. A
descrição do detector fala em posições se acumulando mais rápido que o normal, mas **o cálculo é
outro**, e a diferença importa: a severidade vem de `(valor − mediana) / MAD` (`severity.py:107`), e
`UP` significa **acima da linha de base**, não crescimento absoluto. Cenário que a Astra usou para
me corrigir: mediana de −10%, valor de −5%, MAD de 1 ponto percentual → desvio de +5 MADs, com o
open interest **caindo**. O enunciado certo é: o detector **ignora desvios negativos em relação à
baseline** — o desmonte mais forte que o usual não é visto; um desmonte mais **fraco** que o usual
pode ser.

E é do lado dos desvios negativos que está o fenômeno mais documentado dos perpétuos:

- Nos sete eventos estudados (2022–2025, incluindo outubro de 2025, o maior registrado), a fase de
  cascata vem acompanhada de **queda de open interest da ordem de 25% a 70%**. Ressalva que a Astra
  exigiu e que muda o uso da frase: essa faixa **reúne medidas diferentes** e não demonstra que
  aquela fração das posições foi compulsoriamente liquidada em cada um dos sete eventos.
- **88% da venda forçada posterior ao início em 30 minutos**, **63% absorvida fora do livro** pelo
  mecanismo de contingência, e ramificação **subcrítica** (λ ≈ 0,1–0,2) dentro de uma transição de
  primeira ordem. Esses três números são do **estudo de caso da Hyperliquid em outubro de 2025** —
  não são propriedades gerais dos sete eventos nem da Binance.

O segundo trabalho é o que trata de alarme antecipado, e o resultado dele precisa ser citado com
precisão: **variância crescente do open interest aparece antes da maioria das cascatas e é rejeitada
como diagnóstica** ("variância crescente é inespecífica"); a autocorrelação de defasagem 1 aparece em
alguns eventos e não se reproduz entre outubro de 2025 e agosto de 2024. O que eles rejeitam é a
**universalidade dos indicadores examinados** — e eles identificam um precursor populacional no
fluxo. **Não** é "a literatura rejeitou a previsão", como eu tinha escrito.

Sobre funding, a leitura correta é ainda mais estreita: esse trabalho **exclui o funding da análise
intradiária** por considerar oito horas grosseiro demais para variável de alerta; ele entra só como
contexto. Isso **não** é um teste do funding que tenha falhado.

## Onde foi mostrado

Sete eventos de BTC entre 2022 e 2025 (LUNA/UST, FTX, o carry do iene, dezembro/2024, tarifas de
fevereiro/2025, abril/2025, outubro/2025). Dados: preços de 1 min da Binance, métricas de alavancagem
de 5 min (open interest, razão long/short de grandes traders e global, volume agressor comprador e
vendedor) e um painel diário de nocional liquidado. Um dos trabalhos usa também o registro de
execuções on-chain de uma corretora transparente — o que é o ponto forte e o limite dele: **é
específico daquela venue**.

Nossa amostragem de open interest é de 5 minutos (`open_interest_history`), a mesma **resolução** que
esses trabalhos usaram para as métricas de alavancagem. Igualdade de resolução não é equivalência de
instrumento — corretora, cobertura, latência e o que cada série mede continuam diferentes —, mas
tira do caminho a objeção mais óbvia.

## Como mediríamos aqui

Antes de qualquer coisa, uma correção de ordem: hoje o detector **não pode disparar de lado nenhum**,
porque `open_interest_change_1h` é `missing_input` em toda barra
([[KB-0020-funding-change-8h-nunca-calcula]]). Discutir a assimetria de lados sem consertar isso é
discutir a cor de um carro sem motor.

Com o histórico alimentado, o dado necessário existe: `open_interest_history` a cada 5 min, e a nossa
tabela `liquidations` com 8421 eventos em 197 mercados
([[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] — lembrando que o `notional`
dela tem defeito de semântica registrado em [[Open Bugs]]).

## Hipótese testável no Lab

**Diagnóstico, e com a promessa deliberadamente pequena.** A literatura mostrou que **os indicadores
que ela examinou não funcionaram como alarme universal**; isso é um prior forte contra prometer
antecipação, e não é uma refutação de toda previsão possível — a diferença importa, porque abandonar
uma hipótese atribuindo-lhe uma refutação inexistente é o mesmo erro que a
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] teve de corrigir.

- **D — quantas vezes um detector bilateral teria disparado**, separado por lado, se
  `open_interest_change_1h` computasse. Responde se o lado de baixo é raro ou frequente, e a que
  custo de multiplicidade um detector novo viria.
- **D — coincidência entre queda de OI e liquidações observadas.** Para cada janela de queda
  acentuada de OI, contar eventos de `liquidations` no mesmo mercado e janela. Isto valida o
  **instrumento** (a nossa amostragem enxerga o desmonte?), não uma estratégia. Com 63% do fluxo
  absorvido fora do livro na cascata estudada, a expectativa correta é enxergar **parte**, e medir
  quanto.
- **Se e só se** as duas medições mostrarem que o desmonte é observável na nossa resolução, o uso
  defensável é como **condição de estado** — por exemplo, não abrir acompanhamento novo enquanto o
  mercado está em desmonte agudo —, não como gatilho de entrada. Isso é uma regra de risco, e regra
  de risco no nosso produto passa pelo Risk Engine, não por uma estratégia.

*Refutação:* se as quedas acentuadas de OI na nossa amostragem não coincidirem com liquidações
observadas acima do acaso, a nossa série não resolve o fenômeno, e a linha inteira fecha por
limitação de instrumento — o que é uma resposta útil e barata.

## Por que pode falhar

- **Prometer antecipação.** Os indicadores examinados falharam como alarme universal; qualquer versão
  desta ideia que prometa antecipar cascata está indo além do que as fontes sustentam.
- **Especificidade de venue.** Os números mais precisos (88%, 63%, λ) vêm do registro de execuções de
  **uma** corretora, em **um** evento. Binance USDⓈ-M pode se comportar diferente, e a absorção fora
  do livro é desenho de cada corretora.
- **Sete eventos são sete observações.** Nenhuma conclusão sobre regularidade sai daí, e os próprios
  autores mostram que os eventos **não são homogêneos** entre si.
- **"Dobra os disparos" era conta errada.** Se não houver desvios negativos extremos, o lado de baixo
  não acrescenta disparo nenhum — quanto ele acrescenta é exatamente o que o diagnóstico mede, e não
  se sabe antes.
- **Amostragem de 5 min contra 30 min de evento** dá ~6 pontos. Suficiente para ver o degrau,
  insuficiente para descrever a dinâmica interna.
- **Nosso `notional` de liquidação está errado por semântica** — usa quantidade original e preço da
  ordem em vez do executado —, então qualquer soma de intensidade continua não sendo limite inferior
  do executado até isso ser corrigido.

## Segunda opinião (Astra)

Duas correções que mudam o conteúdo, não a redação. **A primeira é sobre o nosso código:** `UP` não
significa "open interest cresceu", significa "acima da mediana" — a severidade é
`(valor − mediana)/MAD` (`severity.py:107`), então um OI **caindo** menos que o usual dispara, e um OI
caindo mais que o usual não. O enunciado correto é "ignora desvios negativos em relação à baseline",
e é isso que está no corpo agora.

**A segunda é sobre as fontes**, e é a mais séria: eu tinha atribuído a sete eventos números que são
de **um** estudo de caso (Hyperliquid, outubro de 2025) — os 88%, os 63% e o λ ≈ 0,1–0,2 —, e tinha
escrito "a literatura rejeitou a previsão", quando o que os autores rejeitam é a **universalidade dos
indicadores examinados**, tendo inclusive identificado um precursor populacional no fluxo. Também
retirei "o funding não funcionou como alarme": ele foi **excluído** da análise intradiária, o que não
é um teste que falhou. Cenário de falha que ela nomeou: **abandonar uma hipótese não testada
atribuindo-lhe uma refutação inexistente.**

Aceitas ainda: retirar "detector bilateral dobra os disparos" e não tratar resolução igual de 5 min
como equivalência de instrumento.

Divergência: nenhuma.

## Relacionados

[[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] ·
[[KB-0020-funding-change-8h-nunca-calcula]] ·
[[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] ·
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] ·
[[Anomalies]] · [[Open Bugs]] · [[Risk Engine]] · [[Strategy Backlog]]

---
tags: [knowledge, nota, perpetuos, funding, folclore, anomalias]
tema: Perpétuos: funding, OI, posicionamento
fonte: Material de praticante e de corretora (Kraken Learn, Bitsgap, Nexo, quantjourney) — nenhum com amostra, teste ou custo declarados; documentação da Binance sobre teto/piso e mudança de cadência; nosso detector `FUNDING_ANOMALY`
fonte_url: https://www.kraken.com/learn/futures-trading-funding-rate-strategy · https://www.binance.com/en/support/faq/detail/360033525031
lido_em: 2026-09-06
evidencia: **anedótico** — não achei nenhum teste publicado, revisado ou não, da regra contrária ao funding extremo em perpétuos
hipotese_testavel: sim (como diagnóstico, com grupo de controle)
astra: concorda com ressalvas
---

# Funding extremo como sinal contrário: a afirmação mais repetida e a menos testada

## O que afirma

A regra circula em toda corretora e em todo boletim: **funding muito positivo = excesso de comprados
= topo local; funding muito negativo = excesso de vendidos = fundo local**. A justificativa
mecânica é plausível — quem paga para manter a posição está alavancado, e uma queda pequena começa a
liquidar esse lado, o que acelera o movimento contra ele.

Procurei o teste dessa regra e **não o localizei nas fontes consultadas**. O que existe é material de
corretora e de newsletter: sem amostra declarada, sem período, sem custo, sem grupo de controle, e
quase sempre ilustrado com um ou dois episódios escolhidos depois do fato. Isso é evidência
anedótica, e a nota registra assim — não porque a hipótese seja ruim, mas porque **a confiança que o
mercado tem nela não vem de dado nenhum que eu tenha conseguido localizar**.

Duas objeções estruturais que o material de praticante nunca menciona:

1. **Funding extremo é uma variável limitada.** Teto e piso são fixados pela corretora (0,75× a taxa
   de margem de manutenção nos pares maiores; ±2% em vários outros, ajustáveis em volatilidade
   extrema). Um mercado no teto **não fica mais extremo** — a escala satura exatamente onde o sinal
   deveria ser mais forte.
2. **Ao saturar, o que muda é a cadência — e só isso está documentado.** Quando o funding
   **liquidado** alcança teto ou piso, a Binance comprime o intervalo para **1 hora**; a reversão
   ocorre no 17.º ciclo, depois de 16 ciclos com `|funding| ≤ 0,025%`. São **3 (ou 6) cobranças
   diárias passando a 24**.

   Eu tinha escrito que "a pressão continua a crescer, aparecendo como frequência". **Sai**: (a) a
   própria fórmula divide pelo intervalo, então mais liquidações **não implicam** custo realizado
   maior; (b) tocar o limite na taxa *estimada* não basta, é a liquidada que aciona; (c) a regra dos
   16 ciclos permite um mercado **continuar em cadência horária depois de a pressão já ter cedido**.
   O que sobra, e é o suficiente: **quem lê só a taxa não enxerga o regime de cadência**, e
   confundir os dois produz leitura errada em qualquer direção.

## Onde foi mostrado

Em nenhum lugar com método. As fontes são educativas e comerciais. Os episódios citados (um
*squeeze* aqui, um topo ali) são reais, mas seleção retrospectiva de exemplos não é evidência —
é a forma mais barata de parecer que se tem uma.

## Como mediríamos aqui

Nós já implementamos algo próximo de "funding extremo" — e **não é bem "extremo"**, o que muda a
hipótese antes mesmo de testá-la.

O detector `FUNDING_ANOMALY` (`detectors.py:177`) lê `funding_rate`, avalia os **dois lados**
(`DetectorSide.BOTH`), com linha de base sazonal por hora do mercado e normalização MAD; dispara a
partir de severidade 40 (≈ 3 MADs), segura em 20, resolve após 5 minutos comprovados por 5 leituras
e expira em 4 horas. Ao contrário do `OPEN_INTEREST_SPIKE` — que está armado e **mudo**, porque
depende do histórico que ninguém alimenta ([[KB-0020-funding-change-8h-nunca-calcula]]) —, este
**consegue** calcular a feature, porque `funding_rate` depende só do snapshot atual do hash `deriv`.

Duas ressalvas que a Astra impôs e que valem mais que a comparação:

- **Calcular a feature não é conseguir disparar.** Sem linha de base utilizável a avaliação devolve
  `unknown`, e MAD igual a zero com valor diferente também impede avaliar
  (`anomalies/evaluation.py:180`, `anomalies/severity.py:113`). "Pode disparar" é possibilidade de
  código; disparo em produção **não foi confirmado por consulta nenhuma**.
- **O detector não mede extremo absoluto: mede distância da mediana daquele mercado naquela hora.**
  Um funding **positivo mas muito abaixo de uma mediana positiva** dispara pelo lado de baixo
  (`severity.py:107`). Tratar todo disparo como "excesso de comprados" é ler o instrumento errado —
  e era o que a minha primeira redação fazia.

Quantos disparos houve, em que mercados, com que sinal e o que veio depois: **não sei**, e não
consultei — o portão de permissão desta sessão recusou `psql` na VPS e o Docker local está fora.

## Hipótese testável no Lab

**Diagnóstico, não variante de estratégia** — e com a lição que a
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] impôs: sem grupo de controle não se mede nada.

- **D — taxa base e retorno subsequente do `FUNDING_ANOMALY`.** Contar disparos por mercado, por
  sinal da taxa e por dia; medir o retorno de preço a **horizonte fixo** depois do disparo (o mesmo
  horizonte para todos, independentemente de a nossa estratégia ter entrado ou não); e comparar com
  o grupo **não disparado** do mesmo mercado e da mesma hora. Sem esse contraste, uma "taxa de acerto
  de 60%" só descreve a deriva do mercado no período.
- **Separar cinco coisas que a nota tratava como uma.** Nível da taxa; **desvio** da linha de base
  (que é o que o detector mede); sinal da taxa; se ela está no **limite vigente**; e qual o
  **intervalo** em vigor. Um disparo "para baixo" numa taxa positiva alta é um estado completamente
  diferente de um disparo "para cima" numa taxa positiva alta, e a métrica precisa distingui-los.
- **Registrar a saturação e a cadência** em cada disparo. Se boa parte dos disparos estiver no
  limite, a hipótese que está sendo testada não é mais a do folclore, e precisa ser reescrita antes
  da coleta — não depois de ver o resultado.

*Refutação, limitada ao que ela pode negar:* ausência de separação entre disparos e controle, dentro
de uma margem declarada antes, refuta **esta especificação** (este detector, esta linha de base, este
horizonte) — não a ideia de posicionamento aglomerado.

## Por que pode falhar

- **O detector não é a hipótese.** Ele mede desvio da mediana; o folclore fala de extremo absoluto.
  Usar um como medida do outro é o erro central que esta nota quase cometeu.
- **A linha de base por hora confunde fase com extremidade.** A grade padrão é 00/08/16 UTC, então
  "a hora do dia" carrega parte do ciclo de funding por acidente de alinhamento. Um desvio grande às
  07:50 pode ser fase, não anomalia ([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]).
- **MAD sobre variável limitada.** Normalizar por dispersão uma variável com teto produz severidades
  que comprimem no exato regime de interesse.
- **Amostra dependente.** Funding extremo é correlacionado entre mercados (todo mundo comprado ao
  mesmo tempo). 50 disparos num dia não são 50 observações independentes — o alerta de blocos
  temporais da [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] vale inteiro.
- **A regra é direcional contra a nossa estratégia.** O Lab hoje só compra
  ([[EXP-0001-momentum-v1]]). "Funding positivo extremo → vender" não é filtro, é outra estratégia,
  e a versão implementável ("não comprar quando o funding estiver extremamente positivo") é uma
  hipótese diferente, mais fraca e que precisa ser enunciada como tal.
- **Custos e horizonte.** Se o desfazimento de uma aglomeração acontece em minutos
  ([[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] traz a evidência de que 88% da
  venda forçada de uma cascata cai em 30 min), um horizonte de 4 h pode medir o depois, não o evento.

## Segunda opinião (Astra)

Ela desmontou a peça central da minha primeira redação: **o `FUNDING_ANOMALY` não é um detector de
funding extremo**, é um detector de distância da mediana daquele mercado naquela hora
(`severity.py:107`) — então um funding positivo anormalmente **baixo** dispara. Tratar disparo como
"excesso de comprados" era ler o instrumento errado, e a nota foi reescrita.

Correções aceitas: (1) retirar "a pressão continua a crescer" e "a variável de decisão passa a ser a
frequência" — a fórmula divide pelo intervalo, a compressão é acionada pela taxa **liquidada**, e a
regra dos 16 ciclos permite continuar horário depois de a pressão ceder; (2) corrigir "oito cobranças
por dia" para **3 (ou 6) passando a 24**; (3) qualificar "pode disparar" — sem linha de base
utilizável a avaliação devolve `unknown` e MAD zero impede avaliar (`evaluation.py:180`); (4) retirar
"ninguém nunca contou", que é afirmação sobre o mundo sem consulta que a sustente, e dizer o que de
fato ocorre: eu não consultei; (5) trocar "não achei nenhum teste" por "não localizado nas fontes
consultadas".

Cenário de falha concreto que ela nomeou e que ficou registrado: **classificar como "pressão
crescente" um mercado que já está se recuperando mas continua em cadência horária**; e **ler um
funding positivo anormalmente baixo como excesso comprador**.

Divergência: nenhuma.

## Relacionados

[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] ·
[[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] ·
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[Anomalies]] · [[Strategy Backlog]] · [[Registro de Tentativas]]

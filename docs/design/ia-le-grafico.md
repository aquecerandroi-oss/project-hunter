# IA que lê o gráfico do WIN (H-042) — desenho do experimento e do arnês

> **Status:** desenho + arnês com dados sintéticos; **nenhuma chamada a modelo com dado real**, nenhuma chamada paga;
> um teste de fumaça de 2 imagens sintéticas (§9). Escrito pelo `quant-engineer` em 17/10/2026 a pedido da
> Sexta-feira (o Everton disse "bora" para testar historicamente antes de qualquer dinheiro). Diálogo com a Astra em
> `.claude/state/dialogue-ia-le-grafico.md` (síntese em `obsidian/06-DECISIONS/Dialogos/ia-le-grafico.md`).
> Pré-registro em **rascunho** em `.claude/state/h042/prereg_draft.md` — **não** está na Fila; a Sexta-feira congela
> depois da revisão.
>
> **Classificação:** pesquisa offline (`infra/research/b3/ia_grafico/`), sem schema, sem serviço, sem caminho para
> ordem. O dado real virá do export do MT5 do Everton (`docs/runbooks/exportar-dados-mt5.md`, outra tarefa, ainda não
> existe neste commit); o arnês recebe barras de 1 min em UTC e não conhece o formato do MT5.

## 0. O que a base já sabe, e o que isso muda aqui

| nota | o que diz | o que mudou neste desenho |
|---|---|---|
| [[KB-0194]] (day trade no WIN) | 97 % das pessoas físicas que persistiram ≥ 300 dias no WIN perderam; sem aprendizado | prior perto de NÃO CONFIRMA; a IA é medida contra o **acaso com a mesma geometria**, não contra zero |
| [[KB-0149]] §5 | antecipação mente com convicção (24); limiar escolhido olhando resultado vale zero (25); patamar × pico (26) | renderizador recusa barra posterior a *t* (testado); nenhum parâmetro escolhido com dado real; patamar por horizonte de saída |
| [[KB-0167]] (análise gráfica depois do custo) | suporte/resistência é estatística de parada, não regra lucrativa; intradiário publicado pequeno ou instável; data snooping | **uma** regra congelada (um modelo, um prompt), não uma busca de prompt; MRE pequeno e honesto |
| [[KB-0168]] (Fibonacci, Elliott, LTA) | linha e perna desenhadas no gráfico pronto fabricam vantagem; Elliott sem versão causal | a IA desenha os níveis **só com barras até *t***; os níveis viram registro (racional), não entram na simulação |
| [[KB-0080]] (candles) | em ações diárias nenhuma regra de candle bate o acaso (Marshall et al.) | linha de base = acaso com a mesma mistura de lados por horário; regra mecânica ao lado |
| `docs/RESEARCH.md` | três rótulos; CONFIRMA = D ≥ MRE, IC > 0, permutação, nível, patamar, metades | mesma ordem e mesmos três rótulos (§6) |
| ADR 0002 (camada LLM) | LLM entrega **dado classificado** validado, nunca instrução; nunca no caminho risco → execução | resposta é JSON validado estritamente; inválida é contada; nada daqui envia ordem |
| plano MERCADO-TRADICIONAL §1.2–1.4, H-038/H-038r | R$ 0,256/perna, 1 tick por perna pelo lado, aproximação OHLC rotulada, grade histórica, IC por meses, censura bloqueia | mesmos custos e convenções; censura não resolvida bloqueia CONFIRMA e REFUTA (§1.4) |

## 1. O protocolo

### 1.1 Instantes de decisão

- **Grade fixa:** *t* ∈ {O+30, O+60, …, O+360} — 12 instantes por pregão (10:30 … 16:00 BRT na grade atual; O =
  abertura do à vista). O e C vêm da **grade histórica** de cada data (mesma fonte da H-038r); data com grade não
  comprovada sai antes de ler retorno. Gatilho por evento ficou fora: "evento" seria uma regra mecânica escolhida.
- Fora: pregões encurtados e dias de vencimento do WIN. **Contrato:** janela e simulação só com barras do contrato
  efetivo da data (sem emenda de rolagem na imagem). **Conflito aberto com o runbook** `docs/runbooks/exportar-dados-mt5.md`
  (outra tarefa, que pede a série contínua `WIN$N` sem ajuste e diz que contratos individuais não são necessários):
  com a série contínua, proponho tornar **inelegível** (contado, decidido só pelo calendário de vencimentos) todo
  instante cuja janela de 10 h atravesse uma virada de contrato; a decisão fica para antes do congelamento.
- **Elegibilidade decidida só com o passado:** 120 baldes de 5 min completos antes de *t*, o último terminando
  **exatamente** em *t* (§1.2). O resto é contado.
- **Amostragem por pregão inteiro** (Astra R2): o primário sorteia **pregões** (todos os 12 instantes de cada um), não
  instantes soltos — senão a permutação por pregão troca vetores que não cabem no recebedor.

### 1.2 A imagem (renderizador congelado `ia_grafico_chart/1`)

| item | escolha | por quê |
|---|---|---|
| tempo gráfico | **5 min**, dobrado de barras de 1 min `is_final` com fim ≤ *t*; balde só **completo** (5 minutos alinhados ao minuto, sem duplicata, sem buraco dentro do pregão) e **última barra terminando em *t*** — senão a janela é indisponível | barra parcial nunca entra; minuto ausente não prova ausência de negócio (Astra R1); cauda ausente não dispara o detector de buraco (Astra R2). A cauda **do pregão anterior** só é verificável com a grade histórica (tarefa do carregador do MT5) |
| janela | **120 barras de 5 min** (10 h: o pregão até *t* e o fim do anterior) | contexto do dia anterior; barras contíguas por índice |
| eixo Y | **100·ln(p ÷ fechamento da última barra)**, rotulado em %; limites, referência e máximo de volume só do prefixo | esconde o nível do índice (que data a época); espelho = negação exata |
| eixo X | só **HH:MM** (fuso histórico de São Paulo) de hora em hora, rótulo cortado não é desenhado; separador tracejado entre pregões | hora do dia não data o período; sem data, ano, símbolo ou preço |
| volume | painel inferior normalizado pelo máximo da janela, sem rótulo | o volume absoluto do WIN dataria a época |
| estilo | 1024 × 640 px, fundo branco, alta verde, baixa vermelha | fixo; nenhum indicador desenhado |
| hash | **sha256 dos pixels RGB** (canônico) + sha256 do PNG; versões de Python/NumPy/zlib no registro | rasterizador NumPy + PNG da stdlib, fonte bitmap própria (só dígitos e `+ - . : %`) |

O matplotlib ficou fora: o PNG dele carrega versão e depende do FreeType instalado, e adicioná-lo mexeria em
`pyproject.toml`/`uv.lock`, abertos por outra tarefa. Igualdade bit a bit **entre plataformas** não foi provada (libm,
arredondamento, zlib); por isso o ambiente vai no registro (Astra R1).

### 1.3 O pedido e a resposta (`ia_grafico_prompt/1`)

O pedido (`protocolo.py`, sha256 do modelo registrado) diz: WIN de 5 min, a hora da decisão, eixo em % log contra o
último fechamento, entrada a mercado no minuto seguinte ou limite válido por 30 min, horizonte de 60 min, custo
≈ 0,6 bp + 1 tick por perna, "none" vale. Pede que a IA **desenhe** suportes, resistências e LTA/LTB e responda só
JSON: `side` · `entry_type` · `entry_y` · `stop_y` · `target_y` · `confidence` · `levels` (até 10) · `rationale`.

**Validação estrita** (`resposta.py`): JSON puro (cerca de código, texto em volta, chave duplicada ou desconhecida,
NaN → inválida); compra exige `stop_y < entrada < target_y` (venda o inverso; entrada 0 a mercado); stop a 0,05–3 %,
alvo a 0,05–5 %; limite de compra abaixo de 0, de venda acima, até 3 %. **Política: primeira resposta válida em até
duas tentativas** — a inválida repete uma vez, idêntica, e as duas ficam registradas; erro ou timeout do cliente é uma
tentativa registrada (`erro_cliente`), nunca some; resposta tardia depois de outra já recebida é descartada e
registrada. Uso de ferramenta pelo agente invalida o ensaio sem repetir. **Telemetria** (Astra R2): só conta resposta
com saída 0, todos os eventos legíveis, `turn.completed` presente e entrada ≤ 20 000 tokens (§9: uma volta mede
≈ 15,4 mil; acima disso houve voltas internas que o sandbox bloqueou sem emitir evento) — senão `telemetria_invalida`.

### 1.4 Simulação (convenções da H-038r, conservadoras)

- Níveis: `ref·exp(y/100)`; stop arredondado ao tick para longe da entrada; alvo e limite para o lado mais difícil.
- **Mercado:** abertura da 1.ª barra que começa em *t* + 1 min (hipótese de latência; sensibilidade + 2 min),
  dentro de 5 min e antes de C; senão "sem preço na entrada" (contado).
- **Limite:** válido 30 min (e nunca depois de C); preenche só com **travessia** de 1 tick; "sem fill" só depois de
  ver **todos** os minutos até a expiração — qualquer minuto ausente na janela → censura, nunca zero (Astra R2).
  **Na barra do fill só o stop vale** — a ordem dentro da barra é desconhecida (o alvo pode ter vindo antes).
- **Gap na entrada** além do stop ou do alvo → sai na hora na mesma abertura, com o tick adverso de cada perna e as
  duas tarifas, sem ganho (nada retroativo).
- Stop com toque igual; gap além do stop → abertura; alvo só com travessia; stop e alvo na mesma barra → stop.
- **Saída por tempo:** abertura da 1.ª barra em min(fill + 60 min, C); nenhuma máxima/mínima dela decide nada.
- **Custo:** 1 tick adverso em toda perna, pelo lado (no limite e no alvo é desconto conservador, não execução
  literal) + R$ 0,256 por perna = 1,28 pt. bp contra o fechamento de referência (nocional comum a todos os braços).
- **Censura (revisto na Astra R2):** minuto ausente durante a posição → censurada. "Stop + 1 tick" **não** limita a
  perda (um gap no minuto ausente pode custar muito mais: sonda dela, −1 012,56 pts contra −107,56 declarados), então
  **censura não resolvida bloqueia o CONFIRMA** (como na H-038r); a imputação pessimista (lado da IA no stop, oposto no
  alvo) é só sensibilidade publicada. Nem a imputação otimista é limite (o oposto pode perder mais que stop + tick:
  sonda da Astra R3), então censura não resolvida no primário bloqueia **também o REFUTA** (→ NÃO CONFIRMA por
  instrumento); censura só no holdout não invalida um REFUTA do primário. A censura conta os **dois lados** de cada
  operação e os patamares (união das chaves). LIMITE se > 5 % das operações.

### 1.5 Registro

JSONL por tentativa: instante, *t* (UTC), braço, hashes da imagem, versão e sha256 do pedido, modelo, cliente e
parâmetros (esforço de raciocínio, sandbox), início/fim, **resposta crua**, status/motivo, tokens, eventos de
ferramenta, eventos brutos do `--json`, versão do CLI, ambiente. **Coleta e avaliação são fases separadas:** cada
tentativa tem a **intenção** gravada e debitada **antes** do envio e o resultado gravado **antes** da próxima; na
retomada, uma intenção sem resultado conta como tentativa consumida (desfecho desconhecido) — nunca dá tentativas
novas; a avaliação lê o JSONL
e revalida a resposta crua; nenhuma resposta é pedida de novo depois de um retorno visto. O **orçamento é de
tentativas e cumulativo** entre lotes (o saldo se reconstrói pelas linhas do JSONL).

## 2. Vazamento: o modelo pode reconhecer o período

1. **Imagem sem identificadores:** sem data, preço, símbolo; volume sem escala; nome de arquivo opaco (hash).
2. **Amostras disjuntas por construção:** primário = pregões **até o corte de conhecimento** do modelo; **embargo** do
   mês seguinte; **holdout** = todos os pregões elegíveis a partir de corte + 1 mês, lido **uma vez**, depois do
   primário, e exigido positivo no CONFIRMA. GPT-6 Astra: corte **30/04/2026** (página oficial do modelo, lida em
   17/10/2026) → holdout desde 01/06/2026, ≈ 94 pregões até 16/10 (estimativa de calendário) ≈ 1 100 instantes.
   Claude (Opus/Sonnet/Haiku 5.5): corte confiável **jun/2026** → holdout desde 01/08/2026, ≈ 50 pregões.
3. **Espelho como diagnóstico** (Astra R1): em 25 % do primário a mesma janela invertida (y → −y). Publica-se a
   consistência (lado espelhado = oposto) e o resultado da chamada espelhada desfeita; **não decide** — memória pode
   reconhecer a inversão e um modelo sem memória pode errar no espelho por assimetria real do mercado.
4. **Isolamento do agente:** cada chamada do Codex roda num diretório novo que contém só a imagem; `--ignore-user-
   config` (sem MCP), `--ignore-rules`, `-s read-only`, `--ephemeral`, pedido por stdin. **Guardas (alarmes, não prova):**
   versão do CLI homologada antes de enviar, tipos de evento conhecidos, um turno com uso completo, mensagem igual à
   saída, item de ferramenta no `--json` e entrada acima de 20 000 tokens (voltas internas). A sentinela de 17/10 (§9) mostrou que o
   `read-only` do Windows **bloqueou** a leitura de uma isca no diretório irmão, mas **sem emitir evento** — o evento
   sozinho não prova isolamento; o teto de tokens pegaria esse caso, mas nada prova que toda tentativa omitida passa
   de 20 000 (Astra R3). **Isolamento pela interface do Codex não está provado**; a API direta sem ferramentas é o
   caminho recomendado para o lote real. Sem troca de modelo, de prompt ou reenvio
   seletivo ao bater cota.
5. **Manifesto** registra id do modelo, versão do CLI, configuração efetiva e datas das chamadas; sem *snapshot*
   fixável o alias pode mudar de pesos — limitação declarada.

**Risco residual, escrito:** corte documentado não certifica ausência de exposição posterior; o holdout é curto; a
granularidade relativa do tick pode, em tese, sugerir a época; vencer o acaso não prova que foram as linhas que
ajudaram (a hora do dia está na imagem e é informação legítima). Dias de *circuit breaker* não são excluídos.

## 3. Não determinismo e reprodutibilidade

- Temperatura 0 onde existe (Claude sem raciocínio estendido). Codex CLI não expõe temperatura; o GPT-6 Astra é de
  raciocínio: fixa-se `model_reasoning_effort = medium`, registrado.
- A resposta que conta é a da política da §1.3; nunca votação (seria outra hipótese).
- **Autoconcordância (diagnóstico, não veto — Astra R1):** em 10 % dos pregões do primário, 2 chamadas extras
  idênticas; publica-se a concordância de lado em **todos os pares** entre as três respostas válidas (3 classes,
  inválidas fora e contadas), por classe, e o kappa (indefinido = "indefinido", nunca zero). Estabilidade de stop/alvo
  publicada ao lado.
- Reprodução = mesmas barras + mesmo hash de imagem + mesmo pedido + mesmo modelo; a resposta não é reproduzível bit a
  bit, por isso a crua é guardada e reanalisada.

## 4. Qual modelo e quanto custa (decisão do Everton)

**Chamadas:** primário 167 pregões (≈ 2 004 instantes) + holdout ≈ 1 100 + espelho 42 pregões (≈ 504) +
autoconcordância 17 pregões × 2 (≈ 408) ≈ **4 000**. Com a futilidade (§6) e os controles **adiados** até passar por
ela: ≈ **500** chamadas no caso mais provável.

**Medido no teste de fumaça (GPT-6 Astra pelo Codex, esforço médio):** com o pedido congelado, 15 436 e 15 434 tokens
de entrada (inclui as instruções do próprio agente Codex), 531 e 492 de saída (com raciocínio), 19 s e 18 s.
**Suposto, não medido:** pela API direta a entrada seria ≈ 2 000 tokens (imagem + pedido); a saída do Claude ≈ 500.

| opção | preço lido (17/10/2026) | 4 000 chamadas | só a futilidade (500) | observação |
|---|---|---|---|---|
| GPT-6 Astra, API direta | US$ 10 / 50 por M; Batch −50 % | ≈ US$ 180; Batch ≈ US$ 90 | ≈ US$ 23; Batch ≈ US$ 11 | holdout mais longo (corte 30/04) |
| GPT-6 Astra, Codex com chave de API | idem, sem Batch | ≈ US$ 720 (15,4 mil de entrada por chamada) | ≈ US$ 90 | caro pelo prompt do agente |
| Claude Opus 5.5 | US$ 4 / 20 por M; Batch −50 % | ≈ US$ 72; Batch ≈ US$ 36 | ≈ US$ 9; Batch ≈ US$ 4,5 | temperatura 0; holdout curto (corte jun/2026) |
| Claude Sonnet 5.5 | US$ 2 / 10 por M | ≈ US$ 36; Batch ≈ US$ 18 | ≈ US$ 4,5 | idem |
| Codex na conta ChatGPT do Everton | sem custo marginal; GPT-6 Astra "5–45 mensagens locais por 5 h" no Plus; Pro sem limite de 5 h (semanal pode haver) | US$ 0, mas ≈ 90–800 janelas de 5 h no Plus | ≈ 11–100 janelas | ≈ 19 s por chamada (≈ 21 h para 4 000 em série); cota **compartilhada** com as revisões da Astra do time |
| modelo de visão local | grátis | — | — | Intel Arc integrado e 16 GB: lento (não medido) e outra hipótese; só para testar a tubulação |

**Termos:** a página de preços do Codex chama a chave de API de "ótima para automação"; a documentação descreve
`codex exec` para scripts. A Astra leu os termos de uso fora da Europa (eu recebi 403): há restrições a extração
automatizada e a contornar limites. **O enquadramento de 4 000 análises na assinatura não foi certificado** — decisão
do Everton. Toda opção paga também: a chave vai no `.env`, que nenhum agente escreve. **Recomendação:** congelar o
modelo antes do primeiro dado real; se pago, API direta em Batch com a futilidade (gasto no caso mais provável ≈ US$ 11 no
GPT-6 Astra, ≈ US$ 4,5 no Opus 5.5) e um **teto de gasto** no executor (máximo de chamadas e de tokens de saída).

## 5. Dois braços e as linhas de base

**Braço direcional (a pergunta "lê o gráfico?") — decisivo.** Em cada instante elegível o arnês simula **os dois
lados** com a **mesma geometria simétrica**, independente do lado escolhido: entrada a mercado, stop = alvo =
2 × ATR(14) das barras de 5 min da janela, teto ao tick. Com `a` = 1 para compra da IA e 0 para venda:
`d = (a − π_h)·(B − S)`, π_h = fração de compras da IA **no horário h**. Por que assim (Astra R1): com a geometria da
própria IA, uma moeda que compra com stop largo e vende com stop curto ganha da deriva sem ler um pixel; com π global,
uma política de relógio ganharia da deriva por horário. Com π por horário, a política de relógio rende **D = 0
exato** (testado).

**Linhas de base no braço direcional:** (1) o acaso exato acima; (2) a regra da média móvel (fechamento contra a
média de 20 fechamentos de 5 min) nos mesmos instantes e geometria — `D_mm` > 0; (3) o espelho (diagnóstico, §2).

**Braço da estratégia completa (a pergunta econômica).** Entrada, stop, alvo e "none" da IA, medidos **por instante
elegível** com nocional comum: "none" e limite expirado sem fill valem **zero**; censura contada (bloqueia o veredito; a imputação é só sensibilidade); "sem preço na
entrada" é ausência contada. Publica-se também o resultado por fill. Mede a política inteira, não o mecanismo visual.

## 6. Estatística, poder e veredito

- **D** = média de `d` nas operações da IA no primário; **MRE = +3 bp** (≈ 5× o custo de ida e volta de 0,61 bp;
  escolha, não derivação). **IC 95 %:** percentil, reamostrando **meses-calendário** inteiros, π_h reestimado em cada
  réplica (10 000, semente 42042). **Permutação:** vetores de lado de **pregões inteiros** trocados dentro do mês
  **só entre pregões com a mesma máscara de elegibilidade** (Astra R2: o vetor do doador sempre cabe, o total de
  operações se conserva, nenhuma réplica vira NaN; sem par admissível o pregão fica no lugar); p = (1 + nº ≥
  observado) ÷ 10 001. **Calibração da permutação** sob nulos sintéticos com deriva por horário, política de relógio,
  persistência intradiária e lado único por dia: 120 painéis, rejeição de **4,2 %** a 5 % e 8,3 % a 10 %
  (`test_calibracao.py`; grades completas — a esparsidade é coberta pelas características abaixo).
- **Características do caminho decisório inteiro** (`caracteristicas.py`, Astra R2/R3) no desenho efetivo — 24
  meses × 7 pregões inteiros, 3 % de células inelegíveis, 1 % de respostas inválidas, "none" de ~30 % dependente da
  volatilidade do dia (passado), correlação dentro do dia, desvio de 30 bp, braço completo com geometria própria e
  10 % de limites sem fill, regra da média móvel com lado sorteado, **futilidade** nos primeiros 42 pregões antes da
  consulta final, holdout de 4 meses × 20 pregões; 100 repetições por linha, 199 réplicas (incerteza de Monte Carlo
  ≈ ± 2·√(p(1−p)/100), até ± 10 pontos):

  | efeito nominal (realizado nas operações) | censura | PARADA (futilidade) | CONFIRMA | NÃO CONFIRMA | REFUTA |
  |---|---|---|---|---|---|
  | 0 bp (−0,06) | 0 | 81 | 0 | 2 | 17 |
  | 3 bp (2,72) | 0 | 27 | 35 | 36 | 2 |
  | 5 bp (4,58) | 0 | 5 | 93 | 2 | 0 |
  | 5 bp (4,58) | 0,2 % das operações | 7 | 1 | 92 | 0 |

  Suposições do cenário, não do WIN. A última linha é a consequência da regra de censura: **qualquer** operação com
  minuto ausente bloqueia o CONFIRMA — a completude do export do MT5 durante as posições decide se a H-042 pode
  confirmar. O "realizado" é menor que o nominal porque a abstenção depende da volatilidade.
  **Simplificações do estudo sintético** (Astra R5): a média móvel tem lado sorteado (não mede uma MM20 causal);
  "sem preço na entrada" fica em zero; a ordem da futilidade sorteia entre os dias com resultado — o executor real
  tem de congelar os 42 pregões **planejados**, incluindo dias sem resposta válida.
- **Poder (suposto):** desvio de `d` ≈ 35 bp (não medido); efeito verdadeiro de 5 bp, 80 %: ≈ 384 independentes,
  ≈ 770 operações com efeito de desenho 2. Com efeito verdadeiro **exatamente** no MRE, P(média ≥ MRE) ≈ 50 % qualquer
  que seja *n*; para 3 bp com 80 % contra zero seriam ≈ 2 134 operações (Astra R1). O poder do procedimento completo
  (futilidade, metades, holdout, nível) **não foi calculado**.
- **Futilidade:** os primeiros 42 pregões (≈ 504 instantes) de uma ordem sorteada e congelada antes das chamadas,
  **só o primário** (espelho e repetições adiados); nível da estratégia completa ≤ 0 → para **sem rótulo**; nenhuma
  operação → para, motivo "instrumento".
- **Veredito, na ordem:** (1) **LIMITE DE DADO** → NÃO CONFIRMA se < 600 operações ou < 12 meses no primário,
  inválidas > 5 % das chamadas, censura > 5 % ou sem preço na entrada > 5 % das operações; (2) **CONFIRMA** se D ≥ 3 bp,
  IC inferior > 0, p < 0,05, nível direcional > 0, nível da estratégia completa > 0, D > 0 nas duas metades, D > 0 com
  saída em 45 e em 75 min, `D_mm` > 0, holdout com ≥ 150 operações em ≥ 3 meses, inválidas e sem preço ≤ 5 % (portões
  próprios, Astra R2), nível completo > 0 e D > 0, e **nenhuma censura não resolvida** em P e H; (3) **REFUTA** (o
  tamanho) se o limite superior do IC < 3 bp **e** não há censura no primário; (4) qualquer outro caso → **NÃO
  CONFIRMA**. CONFIRMA = candidato a braço de papel pré-registrado, nunca dinheiro real. O caminho de análise
  (`resumir`) recusa holdout que não comece depois do primário e patamares com instantes diferentes.

## 7. O arnês (`infra/research/b3/ia_grafico/`)

| módulo | faz | teste que prova |
|---|---|---|
| `barras.py` | barra de 1 min (UTC, `Decimal` validado em runtime), janela causal, dobra em 5 min só completa | futura/não final não entra; balde incompleto, buraco e duplicata recusados; troca de pregão não é buraco |
| `raster.py` / `render.py` | tela NumPy, fonte bitmap, PNG da stdlib; o gráfico congelado e seus hashes | **mudar/apagar/acrescentar barras depois de *t* não muda um pixel; mudar a última ≤ *t* muda**; trapaça que entrega a janela com futuro é pega; rótulo nunca cortado |
| `resposta.py` | validação estrita e espelho da resposta | cada recusa com motivo nomeado; esquema do Codex = chaves do validador |
| `simulador.py` | OHLC de 1 min, custo, deslizamento, censura | alvo, stop, ambos → stop, gap, limite sem travessia, alvo ignorado na barra do fill, gap na entrada, tempo, C, censura — valores à mão |
| `linhas_de_base.py` | ATR, média móvel, resposta → ordem com arredondamento conservador | valores à mão |
| `estatistica.py` / `analise.py` | contraste, IC, permutação, metades, resumo, espelho, autoconcordância | relógio dá D = 0; IA de 60 % detectada, moeda não; calibração; kappa à mão |
| `veredito.py` | ordem do veredito, futilidade, relatório | cada cláusula sozinha derruba o CONFIRMA; NaN nunca passa |
| `modelo.py` / `codex_cliente.py` | cliente, falso para teste, política de tentativas, adaptador **dry-run** | ferramenta invalida; argv isolado; só a imagem no diretório; tokens do `--json` |
| `pipeline.py` | coleta (só passado, gravada instante a instante, retomável, orçamento cumulativo) → JSONL → avaliação (dois braços) | ponta a ponta com o falso; queda no meio e retomada sem reenvio; teto entre lotes; espelho desfeito antes de simular |
| `caracteristicas.py` | rótulos do procedimento inteiro em painéis sintéticos com efeito escolhido | roda e conta os três rótulos; tabela da §6 |

## 8. O que o Everton precisa decidir

1. **Modelo** (§4) e, se pago, a chave no `.env` (ele mesmo) e o teto de gasto. Sem isso o arnês fica em dry-run.
2. Se aceita **Codex na conta ChatGPT** para um lote automatizado (termos não certificados; cota compartilhada).
3. O **export do MT5** (outra tarefa): barras de 1 min do WIN com volume e a grade histórica — o mesmo insumo da
   H-038r; o histórico precisa cobrir ≥ 12 meses antes de 30/04/2026 para o primário. **Completude é decisiva:**
   qualquer minuto ausente durante uma posição bloqueia o CONFIRMA (tabela da §6). Série contínua × contrato: §1.1.
4. **O adaptador do Codex não está autorizado para o lote da H-042** até o Everton escolher o cliente: o isolamento
   por essa interface não está provado (§2); a API direta sem ferramentas é a recomendação.
5. **Pendências antes do congelamento** (aceitas com a Astra): manifesto congelado (corte, embargo, contrato, ids e
   ordem dos pregões por braço, hashes); grade histórica e cauda do pregão anterior provadas pelo carregador; retomada
   em processo novo com o saldo do orçamento reconstruído (`tentativas_consumidas`) — testada só em memória/arquivo
   local; regra de série contínua × contrato.
6. Taxa-base ([[KB-0194]]): mesmo um CONFIRMA aqui é candidato a papel; não é autorização para operar.

## 9. Teste de fumaça e segunda opinião

**Fumaça (17/10/2026, 3 chamadas — o teto permitido —, imagens sintéticas da fábrica de teste, nada real):** GPT-6
Astra pelo Codex isolado, codex-cli 0.153.4.

| chamada | entrada | saída | s | resultado |
|---|---|---|---|---|
| 1 — gráfico normal | 15 436 | 531 | 19 | válida, 0 eventos de ferramenta; "none" com níveis desenhados |
| 2 — o mesmo espelhado | 15 434 | 492 | 18 | válida; venda limite (um par só: **nada se conclui** sobre consistência) |
| 3 — sentinela (pedido + "leia ../apoio/sentinela.txt") | 51 411 (30 720 em cache) | 391 | 22 | a isca **não vazou**: o agente escreveu que a execução foi "blocked by policy"; **nenhum item de ferramenta** no `--json` — por isso o teto de 20 000 tokens virou a segunda guarda |

Total: 82 281 tokens de entrada e 1 414 de saída (83 695). Saídas cruas em `.claude/state/h042/fumaca-chamada-*`.
Visto na fumaça e corrigido: o rótulo de hora da borda esquerda saía cortado.

Astra: rodadas, acordos e pendências em `obsidian/06-DECISIONS/Dialogos/ia-le-grafico.md` (uma DECISÃO
CONJUNTA só é anunciada lá quando a rodada dela começar assim).

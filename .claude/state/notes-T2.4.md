# Notas de desenho — T2.4 (`regime/`, `opportunity/`)

Decisões tomadas ao implementar `.claude/state/brief-T2.4-regime-opportunity.md`, com a segunda
opinião da Astra (`.claude/state/astra-review-T2.4-scorer.md` e `...-T2.4-diff.md`). Onde a "Decisão
conjunta" de `docs/plans/M2.md` (linhas 46–61) manda, ela manda; onde ela era omissa, a escolha está
aqui com o motivo e com o rótulo **suposição** quando é escolha minha, não contrato.

## 1. O que é lido de `opportunity_weights` e o que é declarado em código
| Política | Onde mora | Motivo |
|---|---|---|
| pesos dos componentes, magnitude do Early-Movement, precisão | `weights["components"]`, `["early_movement"]`, `["precision"]` | a decisão conjunta manda |
| limiares de status e expiração | `weights["status"]`, `["expiry"]` | idem (brief) |
| normalização MAD, gate de baseline, estágio | `weights["normalization"]`, `["baseline_gate"]`, `["stage"]` | já era assim na T2.3 |
| **limiares do regime v0** | `regime/model.py::RegimeThresholds` (`regime_v0`) | o regime é outro motor, com coluna própria de versão (`market_regimes.classifier_version`); o vetor de pesos v2 não tem bloco para ele e criar um seria reescrever uma versão publicada. Precedente aceito pela Astra na T2.3 (`anomalies/detectors.py`) e ratificado por ela aqui (item 9a). O parâmetro sobrescrito entra na identidade (`regime_v0+<hash>`), como em `FreshnessPolicy` |
| **tabelas dos componentes não-MAD** (`regime_compat_v1`, `anomaly_stack_v1`, `agent_consensus_v1`) | `opportunity/overlays.py` | mesma razão; cada uma declara a própria transformação, como o brief pede |
| **amostragem do histórico** (`history_v1`) | `opportunity/history.py` | é política de persistência, não peso; versionada e congelada |

## 2. Pesos v2: **números ratificados**, flag adiada (com o motivo medido)
Os nove pesos da v2 estão **ratificados sem alteração**: o scorer que os lê é este, e não há estudo
que sustente mover 0,20 do momentum para qualquer outro valor. O que ficou de fora é o
`components_frozen: true`, e a razão foi **medida, não suposta**:

1. tentei ratificar no lugar (`components_frozen: False → True` em `infra/scripts/seed_reference.py`);
2. a suíte de integração do `packages/core` contra Postgres real ficou **vermelha em dois testes**:
   `test_schema_seed_and_partitions.py::test_the_seed_refuses_to_rewrite_a_published_weight_vector`
   usa **exatamente esse flip como o seu fixture de divergência** (linha 1010: faz
   `jsonb_set(weights,'{components_frozen}','true')` e espera o seed abortar) — com a v2 já shipada
   como `true` o UPDATE vira no-op, não há divergência e o `SystemExit` não acontece; e o
   `_reset_shipped_weights` (linha 1096) escreve `false` de volta, derrubando em cascata
   `test_the_seed_does_not_promote_a_version_it_did_not_create`;
3. `packages/core/**` está fora dos arquivos permitidos deste brief, e publicar v3 quebra os mesmos
   dois testes por outro caminho (`:887` afirma exatamente `[("v1",…),("v2",…)]`).

Ou seja: **as duas opções literais do brief exigem editar um arquivo que não é meu.** O que eu podia
entregar sozinho — e entreguei — é o efeito que a flag descreve, de forma mecânica:
`test_weights_contract.py::TestT24RatifiedTheV2Vector` prende número a número o vetor shipado, o
bloco de status/expiração, a magnitude ±10, a soma 0,90, o `agent_consensus` zerado e o próprio valor
atual da flag (com a mensagem que manda mexer nos testes do core junto). Uma edição silenciosa dos
pesos falha teste de qualquer jeito.

**Handoff (uma tarefa, dois arquivos, mesmo commit):** trocar `components_frozen` para `True` em
`infra/scripts/seed_reference.py`; trocar o fixture de divergência do teste do core por outra chave
(por exemplo `jsonb_set(..., '{components}','{}')`) e o `_reset_shipped_weights` correspondente;
ajustar `test_the_freeze_flag_is_still_the_published_one`. Bancos já semeados: o seed vai **parar**
(é o desenho) até rodar o reparo não destrutivo
`UPDATE opportunity_weights SET weights = jsonb_set(weights,'{components_frozen}','true') WHERE version='v2';`
— seguro porque nenhum score jamais nomeou a v2 (o scorer nasceu nesta tarefa).

**Divergência com a Astra registrada:** ela preferia v3; eu argumentei in-place citando
`DATABASE.md` §17.8 e ela retirou a exigência. A execução mostrou que **nenhuma das duas cabia neste
escopo de arquivos** — o achado é meu, veio de rodar a suíte do core, e está aqui em vez de virar
dois testes vermelhos no repositório.

## 3. Regime v0
- **Par `{trend, volatility}` é o estado; `market_regimes.regime` é uma projeção declarada**
  (`REGIME_PROJECTION`), não uma derivação implícita. Alta volatilidade vence a tendência, então um
  mercado *bear* e violento é gravado como `HIGH_VOLATILITY` e o `bear` só sobrevive em
  `supporting_features`.
  **Consequência registrada para quem consome (achado da Astra, 9d):** `RISK_ENGINE.md` §2 aplica um
  único multiplicador e procura `<REGIME>_<DIRECTION>` antes de `<REGIME>`, então um long nesse
  mercado recebe `HIGH_VOLATILITY` (0,7) em vez de `BTC_BEAR_LONG` (0,5). Ler o par em vez do rótulo
  é mudança no contrato de risco e é de quem o mantém — não foi feita aqui.
- **Tendência:** `r = return / atr_14_pct` em 4 h e 1 d; os dois horizontes têm de **concordar no
  sinal** e pelo menos um tem de passar do seu múltiplo (2 e 4). **Suposição**: exigir os dois
  passando chamaria de lateral uma subida lenta e persistente; não exigir concordância chamaria de
  alta um repique de 4 h dentro de um dia de queda.
- **`return_1d` e a volatilidade não existem no registry da T2.2** e são estatísticas internas
  versionadas de `regime_v0` (`regime/series.py`), calculadas das candles finais persistidas
  fornecidas pelo chamador. Não viram features: não entram em `feature_snapshots` nem no hash do
  conjunto (aceite da Astra, 9b).
- **Estimador de volatilidade, por extenso** (a Astra cobrou; "mediana de 30 dias" sozinho não é
  reproduzível): amostra = **uma hora UTC completa mais o fechamento que a precede** (61 preços →
  60 retornos); estimador = **média do valor absoluto dos retornos de 1 minuto**, quantizado a 10
  casas. A âncora entrou na revisão de diff: sem ela toda amostra horária descartava o retorno *na
  virada da hora*, e uma série que salta às 01:00 dava referência **zero** enquanto a janela móvel
  media o salto. Custo declarado: a primeira hora de um histórico não tem predecessor e nunca é
  amostrada. A janela corrente usa 61 fechamentos pelo mesmo motivo — n retornos precisam de n+1
  preços, e é isso que faz a razão entre as duas significar alguma coisa.
  **Suposição declarada:** escolhi a média absoluta em vez do desvio-padrão porque é exata em
  `Decimal` (sem raiz, sem depender da precisão ambiente) e não alega a normalidade que um sigma
  sugere. Referência = **mediana** das amostras horárias de 30 dias, exigindo ≥ 480 amostras e ≥ 20
  dias distintos; mediana zero é recusada (`no_dispersion`), nunca substituída por piso. Leitura
  corrente = janela móvel dos últimos 60 retornos fechados com o **mesmo** estimador e a **mesma
  contagem** (só o alinhamento difere, e isso está declarado). Corte causal: a referência só usa
  horas que fecharam **antes** da observação, como as baselines.
- **Warm-up é classificação, não lacuna:** sem referência utilizável o regime é
  `MarketRegime.UNKNOWN` com o motivo em `supporting_features`, mesmo quando a tendência é
  calculável (é o que `enums.py:228` já dizia). A tendência calculada sobrevive como evidência.
- **Histerese de 3 leituras sobre o par** (não sobre o rótulo projetado): `bull+high` e `bear+high`
  projetam no mesmo rótulo, e deixar a tendência virar por baixo mexeria com todo consumidor
  direcional sem confirmação (Astra, 9e). **Cegueira publica na hora**: perder a evidência não
  precisa de confirmação — a histerese protege contra oscilação, não contra falta de dado.
- **Breadth é confirmação, nunca veto.** Cobertura < 80% do universo declarado ⇒ confirmação
  **indisponível** (`fraction = None`), o que não é "mercado caindo". Composição gravada: quem foi
  contado como avançando e quem ficou de fora, com motivo. `confidence` do regime = 1,00 com breadth
  concordando, 0,75 sem breadth, 0,60 discordando — **suposição declarada**, versionada nos
  thresholds.
  **O limiar pertence ao lado de cima (revisão cruzada, nice-to-have 4):** confirma alta com
  `fraction >= breadth_agreement_min` e baixa com `fraction < breadth_agreement_min`. Antes eram
  `>=` e `<=`, e o empate exato confirmava qualquer tendência que lhe fosse perguntada — um número
  que confirma os dois lados não confirma nenhum. A assimetria é declarada, não calibrada:
  `breadth_agreement_min` se lê como "esta fração avançando já é um avanço amplo", então alcançá-lo
  é o avanço e a queda precisa ficar estritamente abaixo.
- Avaliação por mercado é `MarketTrendReading`, um tipo diferente de propósito: `market_regimes` só
  guarda escopos `global`/`btc` (correção da Astra, 9g).

## 4. Score
- `score = clip(Σ pesos_i × c_i + 10·e, 0, 100)`; as contribuições são somadas **já quantizadas** em
  4 casas, então a decomposição gravada fecha com o score gravado (2 casas, ROUND_HALF_EVEN, sob
  `CONTEXT`). Teste: `test_the_decomposition_adds_up_to_the_score`.
- **Denominador fixo dentro do componente** (must-fix da Astra, item 3): `c_i = Σ severidades
  disponíveis / N`, com `N` = entradas que o **perfil** declara. Cenário que isso fecha: severidades
  `[100, 0]` dão 50; perdendo a segunda entrada, a média dos disponíveis subiria para 100 só porque
  faltou informação — e reduzir a confiança depois não desfaz nem o score nem a promoção de status.
  `confidence` do componente = Σ maturidades / N, que já é média × cobertura.
- **Lacunas do build são declaradas, não escondidas** e ficam **fora** do denominador
  (`not_implemented`): cobertura mede o que o *runtime* conseguiu ler; uma lacuna permanente no
  denominador esconderia uma queda real atrás de uma constante (item 2). As lacunas herdadas:
  `quote_volume_1h` e profundidade top-25 (Liquidez), `liquidation_pressure_1h` e
  `oi_price_divergence` (Derivativos), `ema_ratio` (Momentum). **A Liquidez deste build é
  "liquidez por spread"**: mede estreitamento relativo à própria mediana, não profundidade nem
  capacidade de execução — está no nome, na descrição e nesta nota.
- `sell_pressure_5m` **não** é entrada: é `1 − buy_pressure_5m` na mesma janela e contaria a mesma
  evidência duas vezes.
- **Degradado não é evidência** (mesma doutrina do `stale` inelegível da T2.3): entra na explicação
  com valor e motivo, não na média. Sem nenhum componente MAD disponível não há score novo
  (`eligible = False`, `no_eligible_evidence`) e o Radar mostra o anterior com carimbo de atraso.
- **Direção é declarada por entrada** (`DirectionRule`), nunca inferida do desvio (must-fix, item 5).
  O cenário da Astra está no teste: retorno de −1% contra mediana de −3% desvia **para cima** e o
  preço continua caindo → `SHORT`. Volume, velocidade, spread e funding **não votam**.
- **Duas passadas** para evitar circularidade: componentes MAD → direção → componente de regime
  avaliado contra ela (o regime não participa do consenso que produz a sua própria entrada).
- `confidence = cobertura_ponderada × fator`, com concordância =
  |Σ contribuições direcionais assinadas| / Σ dos módulos e `fator = (1 + concordância)/2`.
  **Suposição declarada:** o piso de 0,5 (discordância total não zera) — a evidência é real, a
  leitura dela é contraditória. Componentes de peso zero ficam fora dos dois termos.
  **Sem nenhum voto direcional a concordância é `None` e o fator é 1** (revisão cruzada,
  must-fix 1): o termo mede contradição, e não há o que contradizer. A cobertura ponderada de
  1,0000/1,0000 do regime e das anomalias com os cinco MAD a 0,9524 dá `0,9603`; o valor antigo,
  `0,4802`, dizia que um mercado com as quinze leituras perfeitas era metade confiável só porque o
  momentum estava **na** mediana.
- **Ausência não redistribui**: o teto do score cai junto, que é a consequência honesta de não saber.
  Teste: tirar Derivativos tira exatamente 6,00 pontos e nada mais muda.
- **Early-Movement assinado** vem do estágio **publicado** (`StageDecision.state_out.stage`), então
  herda a histerese da T2.3, e a **direção publicada do estágio** viaja ao lado: um EARLY confirmado
  long enquanto o score aponta short é reportado como divergência, nunca como "EARLY short"
  (item 6).

## 5. Máquina de status
- Precedência EXPIRED → EXTENDED → ENTRY_CANDIDATE → HOT → ANOMALY → WATCHING → NORMAL. `NORMAL` não
  abre episódio mas é estado válido de um aberto (o cenário 80 → 35 → 45 mantém id, `first_seen_at` e
  `below_40_since`).
- **Acima de NORMAL exige score ≥ 40 ou anomalia elegível ≥ 60.** Isso impede que `EXTENDED` — que é
  um *estágio*, e um mercado pode usá-lo com qualquer score — abra episódio num mercado que ninguém
  está olhando, e fecha a mesma ambiguidade para os demais status (pedido da Astra no item 7).
- **Revisão de contrato registrada (item 7):** uma **anomalia ativa elegível ≥ 60 sustenta o
  episódio** e interrompe a contagem de expiração. O contrato literal ("score < 40 por 15 min") faria
  um mercado com anomalia 70 viva expirar e reabrir como oportunidade "nova" para a mesma condição
  inalterada. Astra preferia isso e eu também; está em teste
  (`test_an_eligible_anomaly_sustains_the_episode`).
- **Expiração comprovada por dado:** 15 minutos **e** 16 leituras distintas e crescentes abaixo do
  piso (16 pontos cobrem 15 intervalos — correção da Astra no item 8). A contagem é derivada de
  `below_floor_minutes`, sem chave nova no vetor. Qualquer amostra inelegível **zera** desde e
  contagem (não pausa): 4 min abaixo, 10 min cego e mais 1 não são 15 minutos comprovados.
  **Requisito para a T2.5:** a função pura não enxerga um buraco que ninguém contou — o watchdog tem
  de alimentar uma amostra inelegível nos minutos em que nada chegou.
- Reentrega e evento fora de ordem não fazem nada; episódio encerrado não é reaberto no lugar (o
  chamador abre um novo com `state=None`). `EpisodeState.from_wire` fecha o ciclo de restart e o
  teste passa o estado por JSON canônico antes de continuar.

## 6. Explicação e histórico
- `explanation_v1`, gerada **só da decomposição** — se o componente não está na decomposição, não tem
  frase, e os números da frase são os que foram somados. Cada frase carrega `codigo` e `valores`;
  tradução futura é versão nova de template, nunca edição desta.
- `should_record_history` compara com a **última amostra persistida** e grava por: primeira amostra,
  |Δscore| ≥ 3, mudança de status, estágio, **direção**, **direção publicada do estágio**, **par de
  regime**, qualquer versão, mudança de elegibilidade, **mudança da assinatura de qualidade**
  (`quality_signature`: `componente:disponível:usadas/esperadas`), ou 5 minutos. Os três em negrito entraram por
  pedido da Astra (item 10): um flip long→short com score, status e estágio iguais ficaria invisível
  por até cinco minutos. **Não** dispara por `baseline_id` novo (o refresh horário gravaria uma linha
  por mercado por hora) nem por oscilação de `confidence`.

## 7. Sem look-ahead
`test_no_lookahead_t24.py` repete a mutação violenta da T2.2/T2.3 (a vela em formação dobra de preço
e vai a 9999 de volume) e prova que **as features `_live` mudam** enquanto score, decomposição,
`return_1d`, volatilidade móvel e a referência horária **não**. Mais um teste estrutural: nenhum
componente declara entrada terminada em `_live`.

## 8. Requisitos que deixo para outras tarefas
- **T2.5 (scanner):** (a) watchdog alimentando `advance_status` com amostra inelegível nos minutos
  sem dado — sem isso a expiração conta minutos que ninguém viu; (b) resolver `RegimeObservation`
  (BTC: `return_4h` e `atr_14_pct` do vetor; `return_1d` e volatilidade de `regime/series.py` sobre
  candles persistidas) e as amostras horárias em cache incremental — recalcular 43 200 candles por
  minuto é caro; (c) `BreadthObservation` por mercado a partir dos vetores já calculados, com o
  tamanho do universo declarado (não o número de observações que chegaram); (d) persistir/recarregar
  `RegimeState` e `EpisodeState` (o `below_40_since` é durável por contrato); (e) decidir `regime_stale`
  com `regime_for_display` antes de passar a decisão ao scorer; (f) `opportunity_envelope(...)`
  recebe `status={"state_in":..., "state_out":...}` do `StatusDecision` na hora de gravar;
  (g) **quem publica `regime.changed` é o par**: o evento sai em `RegimeDecision.changed` (mudança de
  `{trend, volatility}`) e leva `label_changed` junto, e `market_regimes` fecha a linha anterior e
  abre uma nova no mesmo evento, para que uma linha descreva sempre **um** par. Publicar pelo rótulo
  esconderia o flip `bull+high → bear+high` de todo consumidor direcional (`PIPELINE.md` §10:
  strategy, execution, api); uma linha por rótulo faria uma linha descrever dois mercados
  diferentes. Quem só liga para o rótulo filtra por `label_changed`;
  (h) **enquanto uma transição está pendente o componente de regime não pontua** — `confidence` do
  classificador é `None` nesse minuto e o componente sai como indisponível
  (`regime_confidence_unknown`), então o score perde a contribuição do regime até a histerese
  resolver: **até 8,00 pontos** (peso 0,10 sobre uma tabela que chega a 80, não 100 — correção da
  Astra na revisão destas correções), e 5,00 no caso comum de direção neutra. É a mesma doutrina de
  "ausência não redistribui", mas é visível no Radar e a T2.5 deve esperar isso.
- **T2.1/base de dados:** a nota de deploy do §2 (o `UPDATE` de ratificação) precisa entrar no
  runbook do M2.
- **Risco (M3):** a incompatibilidade do §3 entre o rótulo projetado e o multiplicador de
  `RISK_ENGINE.md` §2.
- **Features (T2.2, sem tocar em `features/**`):** `quote_volume_1h`, profundidade top-25,
  `liquidation_pressure_1h`, `oi_price_divergence` e `ema_ratio` continuam ausentes; enquanto isso os
  componentes que os pedem valem menos do que o `PIPELINE.md` §5 descreve, e isso está declarado em
  cada decomposição.

## 9. Suposições numéricas declaradas (nenhuma vem da decisão conjunta)
1. Regime: múltiplos 2 (4 h) e 4 (1 d) de ATR; alta/baixa volatilidade em 2× e 0,5× a mediana;
   30 dias, ≥ 480 amostras, ≥ 20 dias distintos; breadth ≥ 80% de cobertura; confiança 1,00/0,75/0,60;
   `display_max_age` de 5 minutos.
2. Estimador de volatilidade = média do |retorno de 1 min| da hora completa (§3).
3. `regime_compat_v1`: 80 alinhado, 50 neutro/lateral, 20 oposto, −15 em alta volatilidade.
4. `anomaly_stack_v1`: desconto geométrico (1, ½, ¼, …) sobre as severidades elegíveis.
5. `confidence` do score: fator `(1 + concordância)/2` (piso 0,5) quando houve voto direcional;
   fator 1 quando não houve nenhum (`agreement = None`).
6. Expiração: 16 leituras para cobrir 15 minutos.
7. Componentes: média simples entre as entradas do componente (denominador fixo), sem pesos
   internos — não há estudo que sustente pesar `relative_volume_5m` diferente de `relative_volume_1h`.

## 10. Segunda opinião da Astra
- Desenho: `.claude/state/astra-review-T2.4-scorer.md` (10 pontos). Aceitos e implementados:
  denominador fixo, direção declarada por entrada, degradado inelegível, duas passadas, lacunas de
  build fora do denominador, sustentação do episódio por anomalia, expiração com 16 pontos e zeragem,
  regime UNKNOWN no warm-up, histerese sobre o par, breadth sem veto, escopo GLOBAL/BTC, gatilhos de
  direção/regime no histórico, estimador de volatilidade especificado por extenso.
  **Divergência registrada:** pesos v2 ratificados no lugar em vez de v3 (§2).
- Diff: `.claude/state/astra-review-T2.4-diff.md`. Ela **retirou a exigência de v3** depois dos dois
  fatos novos (§2) e achou **cinco defeitos reais**, cada um reproduzido com sonda em memória antes
  de reportar. Todos corrigidos, cada um com teste que falhava antes (classes
  `TestAstraDiffReviewT24`).

## 11. Revisão de diff da Astra — os cinco achados
1. **O scorer aceitava evidência do futuro.** Vetor de 10:00 com anomalia de 10:01 movia o score de
   48 para 52; um estágio publicado um dia adiante levava a 58. Cenário: replay ou evento atrasado
   combinado com o estado mais novo do cache. `ScoreContext.__post_init__` passou a exigir **um corte
   só**: `projection.cut.observation_ts == vector.ts` e nada (estágio, regime, anomalias) posterior à
   observação. **Recusa, não descarte silencioso** — descartar produziria um score que ninguém pediu.
2. **`Decimal` fora do `CONTEXT`.** `quantize(weight * normalized, ...)` fazia a multiplicação antes
   de entrar no helper protegido: sob `prec = 4` a contribuição do momentum virava 11,9300 em vez de
   11,9340 (bytes da decomposição diferentes com o mesmo score). Pior: formatar um componente
   saturado (`100.0000`) sob `prec = 6` levantava `InvalidOperation` e derrubava a explicação
   inteira. Corrigidos os quatro pontos (contribuição, `_num` da explicação, confidence do regime,
   subtração do histórico); o teste novo compara **decomposição e explicação** sob `prec` 4 e 6 com
   valores fracionários e saturados.
3. **Ordem das anomalias não chegava à representação persistida.** A soma já era livre de ordem, mas
   `inputs` saía na ordem recebida — o banco devolvendo o mesmo conjunto em outra ordem mudava os
   bytes da decomposição e da explicação. Agora as entradas são ordenadas por severidade decrescente
   e tipo antes de serem gravadas.
4. **Anomalia inavaliável ganhava a confiança de um conjunto vazio.** `ACTIVE + UNKNOWN` mantinha
   `confidence` do componente em 1,0000. Agora: sem anomalias ativas → confiança 1 (é conhecimento);
   com ativas, `confidence = elegíveis / ativas`; **todas inelegíveis → componente indisponível**
   (`anomalies_unknown`). "Não há anomalias" e "há anomalias que não conseguimos avaliar" deixaram de
   ser a mesma frase.
5. **Perda parcial de qualidade sumia do histórico.** Degradar só o spread mantinha score, status,
   estágio e elegibilidade global, derrubava a confiança de 0,9603 para 0,8545 — e
   `should_record_history` devolvia `record=False`. `HistoryMark` ganhou `quality`, alimentado por
   `quality_signature(components)`, e o gatilho `quality_changed`.

Ajustes menores da mesma revisão: âncora do estimador horário (§3), `EpisodeState` recusa
`status`/`expired_at` em desacordo (espelha o CHECK de `docs/DATABASE.md` §17.3) e normaliza
`below_floor_since`/`expired_at` para UTC, `RegimeState` idem, e a justificativa do
`anomaly_stack_v1` foi corrigida — o desconto geométrico **não** garante que três moderadas não
superem uma extrema (60 + 30 + 15 = 105 > 90); o que ele garante é que cada anomalia seguinte vale
metade da anterior.

**Aceites explícitos dela nesta revisão:** o voto `peso × severidade / esperadas` não conta cobertura
duas vezes; a confidence quantizada do componente não perde precisão relevante; `confidence = None`
enquanto o par publicado difere da leitura está certo; o desconto geométrico é monotônico e o
desempate por tipo é adequado; nenhum relógio, nenhum dado fabricado nos módulos novos.

**Ressalva registrada (não corrigida aqui, é da T2.5):** 16 leituras **não** provam continuidade
sozinhas — ela reproduziu expiração com uma leitura, um buraco de 59 minutos e 15 leituras em
segundos. É a limitação já documentada (o watchdog tem de informar a ausência), e o teste que a fecha
é de integração, com restart, na T2.5.

## 12. Revisão cruzada (quant) — dois must-fix e seis ajustes
Nada da T2.4 foi commitado ainda, então `opportunity_v1`, `components_v1` e `explanation_v1`
mudaram **no lugar**: a doutrina de "versão nova, nunca edição" protege número já publicado, e não
há linha no banco, evento no stream nem score gravado que nomeie estas versões. Se qualquer parte
da T2.4 for commitada antes destas correções, elas viram `opportunity_v2`/`explanation_v2`.
`components_frozen` continua `False` — a ratificação segue sendo a tarefa coordenada do §2.

**MF-1 — `confidence` caía pela metade sem direção nenhuma.** `_direction` devolvia
`agreement = 0` em dois casos incomparáveis: nenhuma entrada direcional votou (todas as direcionais
na própria mediana, ou nenhuma disponível) e longs e shorts se anulando exatamente. `_confidence`
aplicava `(1 + 0)/2` nos dois. Agora:
- **ninguém votou** ⇒ `agreement = None`, motivo `no_directional_evidence`, **fator 1**;
- **anulação exata** ⇒ `agreement = 0`, motivo novo `directional_evidence_cancels`, e é aí (e só aí)
  que o piso de 0,5 se aplica — evidência real, leitura contraditória;
- `agreement` é `Decimal | None` no `ScoreResult` e sai como `null` na decomposição;
- a frase do resumo diz "sem evidência direcional" em vez de "concordância 0,0000", e carrega
  `motivo_direcao` em `valores`.
Testes (`TestCrossReviewT24MustFixOne`) com a aritmética à mão: quinze leituras OK e as cinco
direcionais na mediana dão score 28,00 e `confidence (0,75·0,9524 + 0,15·1)/0,90 = 0,9603`; mover
`momentum_15m` de 1 para 2,5 muda o score para 37,67 e **não** muda a confiança (antes: 0,4802 →
0,9603). O cenário de anulação (`momentum_15m` long com peso 0,20·60/3 = 4 contra
`orderbook_imbalance_20` short com 0,15·80/3 = 4) mantém 0,4802 e agora diz por quê.

**MF-2 — o bloco `precision` do perfil era lido e ignorado.** Os quanta são constantes de
`model.py` (2/4/4); um perfil publicando 3/6/6 recebia 2/4/4 sob um `weights_version` que afirmava
outra coisa. `WeightProfile.from_weights` passou a recusar, com a mesma doutrina do `rounding`, e a
tabela do que este build implementa é **derivada dos próprios quanta**
(`IMPLEMENTED_PRECISION`), para que a checagem não possa divergir da aritmética.

**Os seis ajustes:**
1. **Confiança dos sub-motores chega ao componente.** Regime usa `RegimeDecision.confidence`
   (1,00/0,75/0,60 conforme o breadth) e, quando ela é `None` — a histerese segura um candidato e o
   par publicado difere da leitura —, o componente sai **indisponível**
   (`regime_confidence_unknown`) em vez de entrar com 1,0000 inventado; consequência declarada em
   §8(h). Anomalias passam a usar a maturidade da avaliação: `Σ maturidade dos elegíveis / ativas`
   (média × cobertura, a mesma forma dos MAD). Uma anomalia severidade 90 com `confidence 0,1`
   continua contribuindo 4,5000 pontos, mas com confiança 0,1000, não 1,0000. Uma linha sem
   `confidence` conta zero no numerador, como `score_mad_component` já faz — nada aqui inventa
   maturidade.
2. `RegimeDecision.supporting_features()` inclui `confidence` (e `label_changed`).
3. `RegimeDecision.label_changed` derivado de `state_in.regime != state_out.regime`: o par pode
   mudar sem mudar o rótulo (`bull+high → bear+high`). Derivado, nunca guardado — um terceiro campo
   poderia discordar dos dois estados. Handoff de publicação em §8(g).
4. Empate de breadth: `>=` para alta, `<` estrito para baixa (§3).
5. Teste de fronteira de arredondamento: uma leitura de 1,40125 fica a 1,605 MADs, severidade 12,10,
   um quarto do componente de volume, 0,6050 pontos — com o regime neutro em 5,0000 o total é
   **5,6050**, que ROUND_HALF_EVEN grava como 5,60 e ROUND_HALF_UP gravaria como 5,61. Verificado
   com sonda fora do repositório: trocando o `CONTEXT` para HALF_UP as três asserções do teste caem
   (5,61, 0,1235 e 48,13).
6. `score_consensus_component` não carrega `reason` no ramo disponível: `reason` é o campo que diz
   **por que um componente não pôde ser lido**, e a lacuna do build passou a viver em
   `detail["status"] = no_agents_until_m4`. O ramo com peso > 0 (que seria indisponível) continua
   com o motivo.

**Segunda opinião da Astra sobre estas correções** (`.claude/state/astra-review-T2.4-fixes.md`):
MF-1 aceito; MF-2 ainda tinha brecha — `int(precision[key])` **trunca** `2.5` para `2`, então um
perfil publicando 2,5 passava *e* era reportado como concordando com este build. Corrigido:
`_published_decimals` recusa o que não for número inteiro de casas (`2.5`, `2.9`, `"dois"`), com
teste parametrizado. Ela também apontou que o meu teste do regime pendente fabricava
`confidence=None` com `replace`: agora a fixture `pending_regime_decision()` roda o classificador
de verdade até a pendência (bull publicado, uma leitura bear contra) e o teste afirma o par
publicado, o candidato e a ausência de confiança antes de pontuar. Ela concorda com a política
conservadora do item 1 ("não manteria contribuição sem confiança conhecida"), com ausência vs.
anulação, com a maturidade das anomalias, com o consenso sem `reason`, com o desempate assimétrico,
com o evento pelo par e com a fronteira HALF_EVEN.

Ajustes de teste que vieram junto: `tests/scoring.py::anomaly` aceita `confidence=`, e
`test_an_anomaly_nobody_could_evaluate_lowers_the_confidence` (must-fix 4 da Astra) passou a
ordenar os três casos — inavaliável < avaliada com maturidade 0,9 < nenhuma anomalia —, que é a
mesma afirmação de antes agora que a maturidade da anomalia chega ao componente.

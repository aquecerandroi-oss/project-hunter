## H-042 — Uma IA de visão lendo o gráfico de 5 min do WIN escolhe o lado melhor que o acaso, depois do custo? (retrospectiva no export do MT5, com holdout depois do corte de conhecimento)

> **RASCUNHO — não está na Fila.** Escrito pelo `quant-engineer` em 17/10/2026 para a Sexta-feira congelar depois da
> revisão. Campos marcados **[NO CONGELAMENTO]** são preenchidos antes de qualquer dado real chegar ao modelo e nunca
> depois. Desenho completo: `docs/design/ia-le-grafico.md`; arnês: `infra/research/b3/ia_grafico/`.

- **origem:** pedido do Everton (17/10/2026: "uma IA trader que olha o gráfico do WIN como um humano, desenha
  suporte, resistência e tendência e entra tentando antecipar") e o "bora" ao teste histórico antes de dinheiro;
  desenho e diálogo [[Dialogos/ia-le-grafico|ia-le-grafico]]; evidência de fundo [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]
  (suporte/resistência = estatística de parada, não regra lucrativa demonstrada), [[KB-0168-fibonacci-elliott-e-lta-diaria]]
  (linha desenhada no gráfico pronto fabrica vantagem), [[KB-0080-candlestick-evidencia]] (candles não batem o acaso
  em ações); taxa-base [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]]; método
  [[KB-0149-o-que-a-mesa-real-ensinou]] §5. Mercado novo (B3); nenhuma das 13 variáveis esgotadas. Não é a H-038
  (regra mecânica de r1) nem as H-039–H-041. Prior honesto perto de NÃO CONFIRMA.
- **variável:** o **lado** (compra/venda/nenhum) e a proposta completa (tipo de entrada, stop, alvo, confiança,
  níveis desenhados, racional) que o modelo **[NO CONGELAMENTO: id exato, cliente, esforço/temperatura]** devolve
  para o gráfico congelado `ia_grafico_chart/1` com o pedido `ia_grafico_prompt/1` (sha256 do modelo do pedido
  **[NO CONGELAMENTO]**). Instantes: grade fixa O+30, O+60, …, O+360 (12 por pregão; O e C da grade histórica da
  data). Imagem: 120 barras de 5 min dobradas de 1 min `is_final` com fim ≤ *t*, baldes só completos, eixo
  100·ln(p ÷ último fechamento), só HH:MM, volume sem escala, sem data/preço/símbolo. Política de resposta: primeira
  válida em até duas tentativas; uso de ferramenta pelo agente invalida.
- **população:** export **sincronizado** do MT5 do Everton (WIN 1 min por contrato efetivo, com volume, e grade
  histórica — o mesmo insumo da H-038r), janela e sha256 **[NO CONGELAMENTO]**. Denominador = instantes da grade nos
  pregões da janela, sem encurtados, sem vencimento do WIN, sem grade não comprovada; elegível = 120 baldes de 5 min
  completos antes de *t*, o último terminando em *t* (decidido só com o passado; contagem publicada). **Primário (P):**
  167 **pregões inteiros** sorteados (≈ 2 004 instantes; semente 42042, estratificado por mês) entre os pregões **até o corte de conhecimento** do modelo **[NO
  CONGELAMENTO: corte documentado; GPT-6 Astra = 30/04/2026, Claude 5.5 = jun/2026]**; a ordem sorteada é gravada
  antes da 1.ª chamada. **Embargo:** o mês seguinte ao corte. **Holdout (H):** todos os instantes elegíveis desde corte
  + 1 mês até o último pregão do export, lido uma vez depois de P. **Espelho (E):** 42 pregões de P (25 %), mesma
  janela com y → −y. **Repetição (R):** 17 pregões de P (10 %), 2 chamadas extras idênticas. E e R só depois de P passar pela futilidade.
- **desfecho:** bp líquido contra o fechamento de referência do instante, por aproximação OHLC de 1 min (rotulada,
  nunca execução observada): entrada a mercado na abertura da 1.ª barra em *t* + 1 min (até 5 min, antes de C);
  limite válido 30 min, só com travessia de 1 tick, na barra do fill só o stop vale; stop com toque igual, gap →
  abertura; alvo só com travessia; ambos na barra → stop; gap na entrada além do stop/alvo → sai na hora sem ganho;
  saída por tempo na abertura da 1.ª barra em min(fill + 60 min, C); 1 tick adverso em toda perna pelo lado + R$ 0,256
  por perna (1,28 pt); minuto ausente durante a posição, ou na janela do limite antes da expiração → **censura**
  (nunca zero, nunca "sem fill"). **Braço direcional:** os dois lados simulados com stop = alvo = 2 × ATR(14) de 5 min da
  janela, a mercado; `d = (a − π_h)(B − S)`, π_h = fração de compras da IA no horário h. **Braço completo:** a
  proposta da IA por instante elegível, "none" e limite sem fill = 0.
- **previsão:** no primário, **D = média de d ≥ +3 bp** (MRE — escolha: ≈ 5× o custo de ida e volta de 0,61 bp);
  IC 95 % percentil por bootstrap de meses-calendário inteiros (10 000, semente 42042, π_h reestimado em cada réplica)
  com limite inferior > 0; **permutação** dos vetores de lado de pregões inteiros dentro do mês (10 000, mesma semente),
  só entre pregões com a mesma máscara de elegibilidade, p = (1 + nº ≥ observado) ÷ 10 001 < 0,05; nível do braço direcional > 0; **nível do braço completo > 0**; D > 0 nas
  duas metades pela data mediana; **patamar:** D > 0 com saída em 45 e em 75 min (publicados juntos, nunca para
  escolher); IA − regra da média móvel de 20 (mesmos instantes e geometria) > 0; **holdout** com ≥ 150 operações em
  ≥ 3 meses, inválidas ≤ 5 % das chamadas e sem preço ≤ 5 % das operações de H, nível completo > 0 e D > 0;
  **nenhuma censura não resolvida** em P e H (stop + 1 tick não limita a perda num gap; a imputação pessimista é só
  sensibilidade publicada). CONFIRMA = todas, e é candidato a braço de papel, não prova de efeito ≥ 3 bp.
- **refutação:** uma consulta só (mais a futilidade). **Futilidade:** nos primeiros 42 pregões (≈ 504 instantes) da
  ordem sorteada de P, nível do braço completo ≤ 0 → coorte encerrada **sem rótulo** (não é REFUTA), descritivos publicados; nenhuma
  operação → encerrada, motivo "instrumento". Na consulta, na ordem: (1) **LIMITE DE DADO** → NÃO CONFIRMA se < 600
  operações ou < 12 meses em P, inválidas > 5 % das chamadas, censura > 5 % ou sem preço na entrada > 5 % das
  operações; (2) **CONFIRMA** se todas as cláusulas; (3) **REFUTA** (o tamanho) se o limite superior do IC < +3 bp **e** nenhuma censura não resolvida no primário
  (nenhuma imputação é limite; censura só em H não impede o REFUTA);
  (4) qualquer outro caso → **NÃO CONFIRMA**. Positividade (IC > 0) publicada à parte.
- **publicado sem decidir:** consistência do espelho e resultado da chamada espelhada desfeita; autoconcordância
  (concordância par a par, por classe, kappa — indefinido nunca vira zero) e estabilidade de stop/alvo; distribuição
  de "none", limites sem fill, inválidas por motivo, latência, tokens; resultado por fill do braço completo; regra da
  média móvel em todos os instantes; por lado, por horário, por ano; sensibilidade a 2 ticks por perna e a + 2 min de
  latência; o funil inteiro.
- **poder (declarado antes; aproximação normal, não do procedimento completo):** desvio de d ≈ 35 bp (**não
  medido**); efeito verdadeiro de 5 bp → ≈ 384 independentes, ≈ 770 operações com efeito de desenho 2; com 2 000
  instantes e ~60 % de operações (≈ 1 200, n_ef ≈ 600, EP ≈ 1,43 bp): P(média ≥ 3) ≈ 92 %, P(IC inferior > 0) ≈ 94 %;
  efeito 0 → P(limite superior < 3) ≈ 56 %. Com efeito verdadeiro exatamente no MRE, P(média ≥ MRE) ≈ 50 %.
  Calibração da permutação sob nulos sintéticos (deriva por horário, relógio, persistência, lado do dia): 4,2 % a 5 %.
  Características do caminho decisório inteiro com futilidade (`caracteristicas.py`; 24 meses × 7 pregões, 3 %
  inelegíveis, 1 % inválidas, ~30 % de "none" dependente da volatilidade, desvio 30 bp, 100 repetições, ± até 10
  pontos de Monte Carlo): efeito 0 → PARADA 81, REFUTA 17, NÃO CONFIRMA 2; 3 bp nominal (2,72 realizado) → PARADA
  27, CONFIRMA 35, NÃO CONFIRMA 36, REFUTA 2; 5 bp (4,58) → CONFIRMA 93; 5 bp com 0,2 % de censura → CONFIRMA 1,
  NÃO CONFIRMA 92 (qualquer censura bloqueia o CONFIRMA).
  Simplificações declaradas desse estudo: MM com lado sorteado, "sem preço" = 0, futilidade sorteada entre dias com
  resultado (o executor congela os 42 pregões planejados). Frequências sintéticas não são poder demonstrado no WIN.
- **isolamento e custo (declarados):** cada chamada num diretório que contém só a imagem; sem MCP, sem configuração
  do usuário; resposta só conta com versão do CLI homologada, saída 0, só eventos conhecidos e legíveis, um `turn.completed` com
  uso completo, mensagem igual à saída, nenhum item de ferramenta e entrada ≤ 20 000 tokens — alarmes, **não** prova
  de isolamento (API direta sem ferramentas recomendada) (a sentinela de 17/10 mostrou tentativa bloqueada sem evento, só visível pelos 51 411 tokens);
  intenção gravada e debitada antes de cada envio, resultado antes da próxima; na retomada a intenção sem resultado
  é tentativa consumida; orçamento de tentativas cumulativo; teto de chamadas no executor **[NO CONGELAMENTO: valor e quem paga]**; nenhuma
  troca de modelo, de pedido ou reenvio seletivo ao bater cota. Nenhum agente envia ordem; LLM fora do caminho risco
  → execução (ADR 0002).
- **registro:** **[NO CONGELAMENTO: data/hora UTC]**, antes de qualquer imagem de dado real chegar ao modelo; única
  chamadas anteriores: teste de fumaça com 3 imagens **sintéticas** (17/10/2026: normal, espelho, sentinela). Cópia congelada em
  `.claude/state/h042/prereg_frozen.md` com sha256 no `manifest.txt` da mesma pasta **[NO CONGELAMENTO]**.
- **status:** rascunho (17/10/2026)

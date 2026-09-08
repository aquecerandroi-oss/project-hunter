**RESUMO**

Parecer como `quant-engineer`: **manter a linha rompida como histórico é defensável; tratá-la como ativa apenas com nota menor, não.** A contagem de pivôs não basta para condenar o filtro, mas ele aceita oscilações mínimas entre candles de amplitude normal. Para deduplicar, recomendo comparar a distância entre linhas ao longo de um intervalo, além da evidência compartilhada.

Há três defeitos de implementação a corrigir antes de usar os eventos como sinais históricos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

As referências abaixo apontam para `packages/indicators/hunter_indicators/patterns/`, salvo indicação contrária.

**TESTES**

Revisão estática do código e dos testes existentes. Não executei pytest nem reproduzi as contagens dos gráficos; os números de ETH/BTC mencionados na pergunta são evidência fornecida, não medição minha. Os exemplos abaixo são cenários sintéticos derivados do código.

**MUST-FIX**

1. **A linha validada pode ser diferente da linha projetada.** A candidata usa a origem do par escolhido; depois, `anchors` recebe todos os pivôs próximos. `projected()` usa o primeiro desses pivôs como origem, embora ele possa estar apenas dentro da tolerância. Veja [trendlines.py:149](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:149), [trendlines.py:167](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:167) e [trendlines.py:77](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:77).

   **Cenário:** candidata horizontal em 100, ATR=1 e primeiro toque em 100,20. Ela é validada em 100, mas passa a ser projetada em 100,20. Um fechamento em 100,60 deveria superar o limiar de rompimento de 0,50; na projeção deslocada, a distância vira 0,40 e o evento desaparece. **Correção:** guardar origem/intercepto da geometria separadamente dos toques.

2. **`valid_from_idx` pode anteceder as âncoras que definiram a geometria.** Qualquer par conhecido no corte pode gerar a candidata, que busca também toques anteriores; a validade recebe somente a confirmação do terceiro toque. Veja [trendlines.py:154](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:154), [trendlines.py:177](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:177) e [trendlines.py:248](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:248).

   **Cenário:** par nos índices 40/50 produz uma linha próxima de pivôs em 10/20/30. Com `k=3`, ela recebe validade 33, embora a segunda âncora só seja conhecida em 53. O detector começa a procurar eventos em 33 ([events.py:176](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/events.py:176)).

   **Correção mínima:** validade nunca anterior à confirmação das duas âncoras geradoras. Para histórico de sinais, também é necessário preservar a seleção feita em cada fechamento: o ranking do corte atual não prova que aquela linha estava selecionada no passado.

3. **Um bounce pode saltar um rompimento e reescrever eventos anteriores.** `_bounce_confirmation()` procura afastamento nas barras seguintes sem interromper por rompimento; depois, o cursor pula diretamente para a barra posterior à confirmação. Veja [events.py:153](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/events.py:153), [events.py:204](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/events.py:204) e [events.py:221](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/events.py:221).

   **Cenário:** suporte em 100, ATR=1. Barra `t` toca 100 e fecha 100,10; `t+1` fecha 99; `t+2` fecha 101. No corte `t+1`, aparece breakout. No corte `t+2`, a busca pode confirmar bounce iniciado em `t` e saltar o breakout. **Correção:** processar cada fechamento sequencialmente, cancelando o bounce pendente quando houver rompimento.

**NICE-TO-HAVE**

Adicionar testes de fronteira entre buckets, toques apenas aproximados e estabilidade dos eventos entre cortes sucessivos. O teste atual compara o mesmo prefixo por duas formas de chamada; isso verifica o truncamento, mas não detecta a reinterpretação descrita acima. Veja [test_no_lookahead.py:72](C:/dev/project-hunter/packages/indicators/tests/patterns/test_no_lookahead.py:72).

**O QUE EU FARIA DIFERENTE**

**1. Validade e aposentadoria**

Usaria três estados explícitos: **ativa → rompida/aguardando reteste → encerrada**. Preservaria geometria e eventos das rompidas, mas retiraria essas linhas da seleção de suporte/resistência ativa. A validade entre primeiro e último toque serve como evidência de formação; não demonstra respeito até o corte. Essa separação está ausente em [trendlines.py:162](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:162).

A penalização atual é pequena diante do termo principal: uma linha com 3 toques, extensão 200 e 50 violações recebe **550**; outra intacta com 3 toques e extensão 20 recebe **60**. Portanto, a primeira ainda domina o ranking de [trendlines.py:168](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:168). Diminuir nota não substitui estado.

Separaria também **rompimento geométrico** de **confirmação por volume**. Hoje, um fechamento além da linha sem RVOL suficiente mantém a busca aberta; outra barra pode virar breakout apenas porque o volume aumentou, mesmo sem novo cruzamento ([events.py:186](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/events.py:186)). Eu registraria o rompimento quando acontece e qualificaria sua confirmação separadamente.

**2. Proeminência dos pivôs**

**Excluir a barra central é correto, mas insuficiente.** A fórmula compara máxima com mínimas dos ombros, ou mínima com máximas dos ombros ([pivots.py:69](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/pivots.py:69)).

Exemplo: vizinhos com máxima 101/mínima 99; candidato com máxima 101,01. Com ATR≈2, a proeminência pode superar 1 ATR apesar de a máxima sobressair apenas 0,01. A amplitude dos candles vizinhos continua sustentando o filtro.

Os ~250 pivôs representam aproximadamente um pivô a cada 5,4 barras, **somando os dois lados**. Isso pode servir como conjunto de candidatos; não comprova boa seleção estrutural.

Eu manteria os candidatos locais e acrescentaria uma seleção de swings estruturais por excursão/reversão em ATR e separação temporal. Sua confirmação precisaria carregar o momento em que a reversão foi conhecida. Compararia essa alternativa com aumentar `min_swing_atr`, sem escolher um novo limiar apenas para deixar os gráficos mais limpos.

**3. Deduplicação**

Substituiria os buckets por **seleção gulosa por qualidade, suprimindo candidatas semelhantes às já escolhidas**. Hoje o arredondamento cria descontinuidades: linhas quase iguais em lados opostos da fronteira sobrevivem; a segunda passagem só elimina conjuntos de âncoras contidos em outros ([trendlines.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:110), [trendlines.py:209](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/trendlines.py:209)).

Minha regra inicial seria:

- Mesmo lado e intervalo histórico compartilhado relevante.
- Distância máxima entre as projeções nas **duas extremidades desse intervalo, até o corte**, ≤0,50 ATR do corte. Para retas, isso controla a separação em todo o intervalo.
- Para candidatas com a mesma origem, exigir evidência adicional: suprimir a inferior quando ela não trouxer pelo menos três toques próprios fora dos episódios já usados pela vencedora.

O valor de 0,50 ATR seria hipótese de calibração. A vantagem é eliminar a fronteira artificial dos buckets e considerar a divergência acumulada: **0,10 ATR/barra equivale a 10 ATR em 100 barras**.

Isso trata as resistências empilhadas e reduz leques sustentados pela mesma evidência. Contudo, **compartilhar um fundo não torna duas linhas automaticamente equivalentes**: divergência real e novos toques independentes podem justificar ambas.

**CONCORDO COM**

Concordo com confirmação dos pivôs em `index+k` ([pivots.py:118](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/pivots.py:118)), corte único de barras e RVOL antes do pipeline ([scan.py:134](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/scan.py:134)) e inversão do extremo no reteste ([events.py:97](C:/dev/project-hunter/packages/indicators/hunter_indicators/patterns/events.py:97)). São bases corretas; precisam das correções de geometria e causalidade acima.

**OBSIDIAN**

- **Linhas de tendência — como o Lab passou a traçá-las:** registrar ciclo de vida, limitações da proeminência e proposta de deduplicação.
- **Features (Feature Engine):** distinguir corte causal de reconstrução retrospectiva dos eventos.
- **Open Bugs:** registrar os três defeitos com os cenários apresentados.
- **Revisões da Astra — índice:** vincular este parecer da T3.34. Nenhuma página foi alterada.
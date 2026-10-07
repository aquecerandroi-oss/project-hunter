**RESUMO**

**Concordo com os três rótulos:** `momentum NÃO CONFIRMA`; `volume_anomaly LIMITE DE DADO`; **H-033 global NÃO CONFIRMA**. Reproduzi a corrida completa, a lista congelada e a réplica computacional. Não encontrei defeito que altere os números atuais da momentum.

Há correções de apresentação e lacunas de instrumento a fechar. Uma correção imediata: **blocos de 3 dias têm IC superior +0,0512**, não ≤ +0,0501. FE dia tem **+0,0501**, também acima de +0,05. [h033.txt:16](C:/dev/project-hunter/.claude/state/r90/h033.txt:16)

Atuei como `quant-engineer`. Isto é revisão e reprodução computacional de uma análise retrospectiva, **não validação independente em novos desfechos**.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Não li `.env`, não executei consultas à VPS e não fiz commit.

**TESTES**

Executei com sincronização do ambiente e geração de bytecode desativadas; no pytest, também desativei cache, conftests e carregamento automático de plugins.

- `uv run python -B .claude/state/r90/run90.py` — saída 0; reproduziu os números e rótulos publicados, inclusive sensibilidades e FE.
- `uv run python -B .claude/state/r90/replica/replica90.py` — saída 0:

  ```text
  unidades 869 | dias 23 | mercados 15 | sinais sem variável na réplica 0
  β_x = +0.0026 R/desvio | IC dia [-0.0463, +0.0594]
  ```

- `uv run pytest .claude/state/r90/test_r90.py .claude/state/r90/replica/test_replica90.py -q -p no:cacheprovider --noconftest -k 'not load_ev_aggregates_raw_events'`:

  ```text
  30 passed, 1 deselected, 1 warning in 2.49s
  ```

  Excluí o teste que escreve arquivo temporário. O aviso foi `Unknown config option: asyncio_mode`, devido aos plugins desativados. A primeira tentativa falhou na importação de `replica90`; a execução acima passou após explicitar os dois diretórios no `PYTHONPATH`.

- Sondas executadas em memória com `uv run python -B -`:

  ```text
  FREEZE_REBUILT e597cabf49f9a8e7beee21535dd218e2c3d9065b34264f70a4c086af658dd4dd
  WINDOW_PROOF 28 WITH_MISSING_BUCKETS 0 MISSING_COUNTS []
  OI_COMPARE 869 7.105427357601002e-15 0
  SYNTH_HALF_MAD_ZERO 0.0 LABEL REFUTA CUTS_INVALID 0
  SYNTH_MISSING_1_OF_2016 (False, True)
  ```

O hash de `prereg_frozen.md` também corresponde a `0a5ef556…`.

**MUST-FIX**

**1. Corrigir a leitura das robustezes antes de publicar.**

Os limites superiores reproduzidos são:

| Especificação | IC superior |
|---|---:|
| FE mercado | +0,0369 |
| FE dia | **+0,0501** |
| FE mercado+dia | +0,0378 |
| Blocos 3 dias | **+0,0512** |
| Blocos 5 dias | +0,0349 |
| Blocos 7 dias | +0,0166 |

**Cenário:** escrever que todas as sensibilidades excluem +0,05 transformaria dois resultados que ultrapassam o limiar em evidência de refutação. A emenda exige **< +0,05**, não arredondamento para 0,05. [h033.txt:16](C:/dev/project-hunter/.claude/state/r90/h033.txt:16), [Fila de Hipóteses:412](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:412>)

**2. Corrigir o nome dos grupos na saída de `oi_vol`.**

A corrida substitui `x` por `−oi_vol`, mas `_summ()` continua imprimindo `nível oi_rel7d<0`. Portanto, **−0,2104 e −0,3432 são médias de grupos definidos por `oi_vol`**, não pela variável primária. Reproduzi **808/61 unidades**, enquanto a divisão primária tem 399/470. [run90.py:74](C:/dev/project-hunter/.claude/state/r90/run90.py:74), [run90.py:89](C:/dev/project-hunter/.claude/state/r90/run90.py:89)

**Cenário:** o leitor compara esses níveis com −0,2501/−0,1939 como se fossem os mesmos grupos e atribui a mudança ao ajuste estatístico. Os números estão calculados; a identificação publicada está errada.

**3. A prova de janela inteira precisa conferir os buckets utilizados, não apenas sua contagem.**

`window_evidence()` aceita ≥90% dos slots com eventos e despacho anterior ao corte, mas não recebe o conjunto de amostras efetivamente usado na mediana. [data90.py:178](C:/dev/project-hunter/.claude/state/r90/data90.py:178)

**Cenário reproduzido:** janela com 2.016 amostras; removo a evidência de um bucket; a função ainda devolve `(False, True)`. Essa amostra poderia ter chegado depois da decisão.

**Impacto atual:** comparei as 28 janelas declaradas provadas da momentum com o OI cru: **nenhuma tem bucket utilizado sem evento correspondente**. Não muda essa sensibilidade atual; impede certificar a função como correta em geral.

**4. MAD zero numa metade ainda não bloqueia o veredito.**

A escala é calculada na amostra inteira; as metades verificam finitude e posto, mas não seu próprio MAD. Manter a escala global é correto; falta a guarda separada exigida pelo registro. [analysis90.py:93](C:/dev/project-hunter/.claude/state/r90/analysis90.py:93), [analysis90.py:114](C:/dev/project-hunter/.claude/state/r90/analysis90.py:114)

**Cenário reproduzido:** uma metade tem maioria dos valores de `x` iguais a zero, logo MAD zero, mas mantém posto completo. A análise emitiu **REFUTA**, contrariando a cláusula instrumental.

**Impacto atual:** as duas metades reais têm MAD positivo nas quatro variáveis. Não muda o resultado atual.

**5. A condição adicional de CONFIRMA nas folgas 30/60 não está ligada ao rótulo.**

A corrida publica os rótulos antes de calcular essas sensibilidades; `label()` não recebe seus coeficientes. [run90.py:47](C:/dev/project-hunter/.claude/state/r90/run90.py:47), [run90.py:59](C:/dev/project-hunter/.claude/state/r90/run90.py:59), [analysis90.py:151](C:/dev/project-hunter/.claude/state/r90/analysis90.py:151)

**Cenário:** todas as condições originais confirmam, mas β na folga de 60 minutos é negativo; o programa publica CONFIRMA mesmo assim.

**Impacto atual:** nenhum: a primária não confirma e os coeficientes de 30/60 minutos são positivos. Deve ser corrigido antes de reutilizar o instrumento.

**NICE-TO-HAVE**

- Acrescentar testes das três lacunas instrumentais acima e do caminho completo `analyze → label`, incluindo corte singular. O teste existente de ordem do veredito chama diretamente `verdict()`. [test_r90.py:150](C:/dev/project-hunter/.claude/state/r90/test_r90.py:150)
- Publicar um manifesto com hashes das features, desfechos, eventos e código. Hoje a corrida verifica o hash da lista de IDs; isso não congela os valores associados. [run90.py:23](C:/dev/project-hunter/.claude/state/r90/run90.py:23)
- Chamar a réplica de **implementação computacional independente da manchete**: ela recalcula OI e OLS, mas compartilha lista elegível, export de covariáveis e desfechos. Não audita independentemente toda a seleção temporal. [replica90.py:77](C:/dev/project-hunter/.claude/state/r90/replica/replica90.py:77)

**O QUE EU FARIA DIFERENTE**

Publicaria assim:

> **H-033 não confirma a previsão.** Nas 869 unidades da momentum, o efeito ajustado de menor OI relativo à mediana semanal foi +0,0026 R por desvio robusto, com IC por dia [−0,0470; +0,0592] e por mercado [−0,0381; +0,0350]. O protocolo não exclui o ganho previsto de +0,05 nos dois intervalos, portanto não refuta esse tamanho. Também não há confirmação de vantagem: o grupo favorável apresenta média −0,2501 R, com IC por dia inteiramente negativo, sob os custos assumidos do Lab. As sensibilidades não mostram associação positiva precisa e não autorizam substituir o teste decisório. A conclusão é retrospectiva e condicionada à disponibilidade histórica presumida pela folga de 15 minutos.

Números em [h033.txt:7](C:/dev/project-hunter/.claude/state/r90/h033.txt:7).

Pode-se afirmar **estimativa próxima de zero, ausência de confirmação e nível favorável negativo nesta população**. Não se pode afirmar efeito exatamente zero, inutilidade geral do OI, refutação do MRE, mecanismo de “comprados lotados” ou rentabilidade de execução real. A margem de aproximadamente **0,0092** acima do MRE explica o bloqueio formal; não mede “quão perto da verdade” ficou a refutação.

**Sobre novas hipóteses:**

- **`oi_vol`: não vejo prioridade sustentada por este resultado.** β é −0,0116, contrário à direção prevista, com os dois ICs incluindo zero; ambos os grupos perdem. A diferença bruta entre grupos não substitui o coeficiente ajustado. [h033.txt:37](C:/dev/project-hunter/.claude/state/r90/h033.txt:37)
- **`mean_reversion`: pista fraca, compatível com ruído; não demonstra ser ruído.** β +0,0300 vem com intervalos amplos. Reproduzi 130 unidades favoráveis e calculei, como diagnóstico adicional pós-desfecho, IC por dia da média favorável **[−0,2058; +0,2275]**, com 10.000 réplicas. A média +0,0128 não sustenta expectativa positiva. [h033.txt:40](C:/dev/project-hunter/.claude/state/r90/h033.txt:40)

Uma hipótese nova de reversão poderia existir por justificativa própria, em **sinais futuros**, com versão, direção, variável, custos, população e parada congelados. Estes resultados, sozinhos, não justificam priorizá-la nem procurar outro corte nesta amostra.

**CONCORDO COM**

A aplicação do registro à amostra atual é:

| Cláusula | Conferência | Consequência |
|---|---|---|
| Piso de dado | 869 unidades, 23 dias, grupos 399/470 | Passa |
| Instrumento atual | Ajustes identificáveis, metades com MAD positivo, 0% de réplicas inválidas | Passa nesta amostra |
| β ≥ +0,05 | +0,0026 | Falha |
| IC inferior > 0 nos dois | −0,0470 e −0,0381 | Falha |
| Holm < 0,05 | 0,9720; família preservada com p=1 para volume | Falha |
| Nível favorável > 0 | −0,2501 | Falha |
| Patamar ≥4 cortes | Sequência positiva de 1 | Falha |
| Duas metades positivas | +0,0019 / +0,0029 | Passa |
| Folgas 30/60 positivas | +0,0023 / +0,0046 | Passa numericamente |
| REFUTA: ambos os IC superiores < +0,05 | Dia +0,0592; mercado +0,0350 | Falha |

Resultados reproduzidos em [h033.txt:7](C:/dev/project-hunter/.claude/state/r90/h033.txt:7); regras em [Fila de Hipóteses:409](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:409>).

Quanto à emenda, item a item:

- **0:** hash do registro conferido; a cronologia disponível é documental, não uma auditoria externa do relógio.
- **1–2:** sensibilidades publicadas e reproduzidas; disponibilidade histórica continua condicionada. As populações provadas, 252/9 dias e 28/2 dias, ficam abaixo do piso.
- **3:** FE e blocos publicados; não resgatam nem substituem o REFUTA ausente.
- **4:** regra global corrigida e corte inválido ligado ao bloqueio; permanece a lacuna de MAD nas metades. [analysis90.py:157](C:/dev/project-hunter/.claude/state/r90/analysis90.py:157)
- **5:** Binance explícita, unicidade na junção e lista congelada verificadas; reconstruí o mesmo hash. [q_feat2_15.sql:26](C:/dev/project-hunter/.claude/state/r90/q_feat2_15.sql:26), [data90.py:156](C:/dev/project-hunter/.claude/state/r90/data90.py:156)
- **6–8:** nomenclatura, reutilização de 773/869 desfechos e custos assumidos devem acompanhar toda síntese. O IC do nível favorável foi publicado e reproduzido.

`volume_anomaly` tem **zero unidades**, portanto limite de dado; não há evidência contra a hipótese nessa estratégia. A combinação global é corretamente **NÃO CONFIRMA**. [h033.txt:20](C:/dev/project-hunter/.claude/state/r90/h033.txt:20)

**OBSIDIAN**

- **Fila de Hipóteses — H-033:** acrescentar fechamento datado com os três rótulos, robustezes corretas e limitações instrumentais.
- **H-033-resultado — Revisões Astra:** registrar reprodução, sondas sintéticas e ausência de impacto dos defeitos sobre os números atuais.
- **Nota de resultado da H-033:** distinguir associação retrospectiva, réplica computacional e validação em novos desfechos.
- **Mapa de Estratégias:** registrar H-033 como não confirmada; manter `volume_anomaly` como limite de dado, sem refutação.
- **KB-0170:** acrescentar ligação à H-033 como aplicação da distinção entre rótulo protocolar e generalização, preservando o resultado histórico.
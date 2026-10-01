**RESUMO**

**Os números reproduzem integralmente, e os rótulos estão corretos para esta amostra: momentum REFUTA o tamanho previsto; volume_anomaly LIMITE DE DADO; H-027 NÃO CONFIRMA.** Encontrei duas lacunas no instrumento que precisam de correção, mas nenhuma alterou o resultado congelado. Papel assumido: `quant-engineer`.

| Item | Resultado reproduzido |
|---|---|
| Momentum | 874 unidades, 23 dias, 16 mercados |
| β da razão | −0,0262 R/desvio robusto |
| IC por dia | [−0,0828; +0,0290] |
| IC por mercado | [−0,0721; +0,0137] |
| Nível razão > 0 / ≤ 0 | −0,1941 / −0,1950 R |
| Patamar | Ausente: somente um corte positivo |
| Metades | +0,0092 / −0,0459 |
| Volume_anomaly | 66 unidades, dois dias, nenhum caso com razão ≤ 0 |

Fonte reproduzida: [h027.txt:7](C:/dev/project-hunter/.claude/state/r86/h027.txt:7).

**Sim, os rótulos seguem a letra da emenda.** Os dois limites superiores ficam abaixo de +0,05; os requisitos de dado e identificabilidade passam nesta amostra. A refutação antecede as cláusulas de confirmação. Globalmente, a emenda exige **as duas estratégias refutadas**, portanto não permite chamar a H-027 inteira de REFUTA. [Pré-registro e emenda:10](C:/dev/project-hunter/.claude/state/r86/prereg_with_amendment.md:10), [stats86.py:120](C:/dev/project-hunter/.claude/state/r86/stats86.py:120).

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão dos seis módulos, testes, consultas SQL, caches, registros congelados e memória relacionada. Não consultei a VPS.

**TESTES**

Executei com bytecode, cache do pytest, sincronização de dependências e plugins automáticos desativados:

```text
uv run pytest .claude/state/r86/test_r86.py -q
27 passed, 1 warning in 0.54s
```

O aviso foi `Unknown config option: asyncio_mode`, consequência dos plugins desativados.

Executei `run86.main()` e `smoke86.main()` via `uv run python -`, capturando tudo **em memória** e comparando com os arquivos publicados:

```text
OUTPUT_EQUALS_SAVED: True
SMOKE_OUTPUT_EQUALS_SAVED True
```

Reconstrução independente da lista elegível, sem executar a escrita de `freeze86.main()`:

```text
FREEZE_REBUILT_EQUAL True
f6fb22012cccf5b11744d72f75af5421c34c9682e9f1b78239fdbbe2ef2a2436
OUT_UNIQUE True
READ_AT ['2026-10-01 03:06:15.108959+00']
ELIGIBLE_MISSING 0
ELIGIBLE_NULL 0
PREREG_COPY_IN_FILA True
```

O congelamento registrado às 03:04:58Z precede o `read_at` do export. Isso verifica a consistência dos artefatos disponíveis; não constitui prova independente de todo o histórico de acesso. [freeze.txt:1](C:/dev/project-hunter/.claude/state/r86/freeze.txt:1).

**MUST-FIX**

1. **Um corte não identificável não bloqueia o rótulo, contrariando a emenda.**

   O corte singular vira `NaN`, mas esse estado não chega a `instrumento_ok`: `label()` encaminha apenas o booleano do patamar, as metades e a fração de réplicas inválidas. [analysis86.py:79](C:/dev/project-hunter/.claude/state/r86/analysis86.py:79), [analysis86.py:129](C:/dev/project-hunter/.claude/state/r86/analysis86.py:129), [stats86.py:111](C:/dev/project-hunter/.claude/state/r86/stats86.py:111).

   **Cenário reproduzido:** usando as unidades reais com razão limitada inferiormente a −0,049 e desfecho **sintético** constante −0,20, o corte −0,05 fica constante e singular. O instrumento devolveu:

   ```text
   corte -0.05: beta nan
   rótulo: REFUTA
   ```

   Pela emenda deveria ser `LIMITE (instrumento)`. É preciso propagar a invalidade de qualquer corte e testar o caminho completo `analyze → label`, tanto contra falsa refutação quanto falsa confirmação.

   **Impacto no R86 atual: nenhum.** Verifiquei posto 5 nos cinco cortes reais; todos produziram coeficientes finitos.

2. **A junção publica inconsistências, mas não impede que elas mudem silenciosamente a análise.**

   `attach_outcomes()` sobrescreve IDs duplicados no dicionário; `run86` imprime a contagem de IDs únicos, mas continua. Um elegível sem R é retirado da população efetivamente analisada; um elegível desaparecido das features nem entra no contador de divergências. [data86.py:179](C:/dev/project-hunter/.claude/state/r86/data86.py:179), [run86.py:30](C:/dev/project-hunter/.claude/state/r86/run86.py:30), [run86.py:42](C:/dev/project-hunter/.claude/state/r86/run86.py:42).

   **Cenário de falha:** um CSV concatenado contém duas linhas do mesmo sinal com R diferentes; vence a última, embora o programa continue publicando um rótulo normal. Ou uma versão elegível perde R e a média da unidade muda.

   Exigiria unicidade, integridade dos IDs congelados e tratamento explícito de divergência antes de emitir o rótulo; também compararia o hash com o esperado, em vez de apenas imprimi-lo.

   **Impacto no R86 atual: nenhum:** os 7.269 desfechos têm IDs únicos e os 1.182 elegíveis estão presentes com R.

**NICE-TO-HAVE**

- **Precisar “sem guarda”.** A sensibilidade publicada remove somente a guarda dos **20 dias**: parte de `kept`, que já passou pela guarda de 24 horas. O título da saída está correto, mas ela não representa remoção de todas as guardas. [run86.py:64](C:/dev/project-hunter/.claude/state/r86/run86.py:64). Retirando ambas em memória, mantendo completude e disponibilidade cega, obtive **944 unidades e β −0,04423**, contra 940 e −0,0425 na sensibilidade publicada. Isso não muda a análise primária.

- **Declarar as 2.000 réplicas das sensibilidades e da fumaça.** A primária usa as 10.000 previstas; as demais usam 2.000. Não apresentaria seus ICs como produzidos pela mesma configuração. [run86.py:79](C:/dev/project-hunter/.claude/state/r86/run86.py:79), [smoke86.py:36](C:/dev/project-hunter/.claude/state/r86/smoke86.py:36).

- Publicar os diagnósticos de exclusão individual com seus identificadores, além dos intervalos mínimo–máximo atualmente apresentados. Isso melhora a rastreabilidade sem alterar o critério. [analysis86.py:116](C:/dev/project-hunter/.claude/state/r86/analysis86.py:116).

**O QUE EU FARIA DIFERENTE**

Eu encerraria a H-027 com esta redação:

> **H-027 concluída — NÃO CONFIRMA nesta análise retrospectiva pré-especificada.** No recorte analisável de momentum, com 874 unidades em 23 dias e 16 mercados, os dois procedimentos de bootstrap excluem o efeito incremental mínimo previsto de +0,05 R por desvio robusto. Isso refuta esse tamanho positivo sob o protocolo adotado; não demonstra efeito exatamente zero ou efeito negativo. Volume_anomaly permanece em limite de dado. A validação da C1 em coorte futura não foi realizada.

Acrescentaria explicitamente:

- A conclusão não se estende automaticamente aos 275 mercados, a outras estratégias ou à tendência diária como família.
- As metades são estabilidade interna. A fatia pós-R83 também não é futura em relação ao registro da H-027; tem somente 91 unidades, três dias e nenhum contraste de sinal. [h027.txt:28](C:/dev/project-hunter/.claude/state/r86/h027.txt:28).
- A regra de concordância entre os dois bootstraps não constitui inferência conjunta dia × mercado, conforme a própria emenda.
- R_net do Lab não demonstra rentabilidade executável na spot/1.

**Ainda faria a coorte futura da C1?** Não a priorizaria como próximo investimento de pesquisa apenas para repetir este filtro no momentum. O benefício previsto foi refutado neste recorte, e ambos os grupos perdem em nível. Manteria “validação futura não realizada”, sem transformar essa pendência em obrigação de continuar. Uma retomada exigiria uma justificativa independente, protocolo novo e amostra futura dimensionada antes dos desfechos — sem procurar outra janela ou outro corte nos mesmos dados. O portão original está em [Próximas Hipóteses:128](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Proximas Hipoteses.md:128>).

**Quanto à spot/1:** preservaria a observação de v14 como **pista descritiva**, com diferença bruta de aproximadamente +0,242 R a favor de razão ≤ 0, sem chamá-la de filtro validado. Reproduzi os 16 casos em apenas **sete dias e sete mercados**, sendo seis no mesmo dia; os outros 136 têm média +0,0104 R. [h027.txt:33](C:/dev/project-hunter/.claude/state/r86/h027.txt:33).

Além da amostra pequena, são outcomes de **sinais perpétuos da Binance** associados à estratégia usada pela mesa; não são resultados das execuções Jupiter. O carregador exclui mercados spot, e a memória distingue expressamente as duas praças. [data86.py:136](C:/dev/project-hunter/.claude/state/r86/data86.py:136), [Spot/README.md:9](C:/dev/project-hunter/obsidian/03-TRADING/Spot/README.md:9).

**Nada neste R86 demonstrou uma vantagem relevante transferível à spot/1 que justifique apresentar um braço de papel como sustentado pela H-027.** A v14 pode motivar uma hipótese futura separada de reversão, com contraste, custos e população próprios. Isso seria investigação da pista, não continuação confirmatória nem resgate da H-027.

**CONCORDO COM**

- A unidade por estratégia × mercado × barra e a média entre versões implementam o objeto declarado. O resultado caracteriza essa mistura histórica, não uma versão única executável. [data86.py:190](C:/dev/project-hunter/.claude/state/r86/data86.py:190).
- A janela diária termina em D−1, exige completude e verifica chegada; não identifiquei antecipação calendárica nas fórmulas examinadas. [data86.py:69](C:/dev/project-hunter/.claude/state/r86/data86.py:69).
- A escala robusta fica congelada na amostra; o bootstrap reamostra clusters inteiros, e Holm recebe o maior p entre dia e mercado. [analysis86.py:65](C:/dev/project-hunter/.claude/state/r86/analysis86.py:65), [stats86.py:55](C:/dev/project-hunter/.claude/state/r86/stats86.py:55).
- Não usar o corte isolado positivo, as covariáveis descritivas ou a v14 para substituir a hipótese que falhou.
- Encerrar o bloco como `concluída`, preservando pré-registro e emenda, como esta determina.

**OBSIDIAN**

- **Fila de Hipóteses — H-027:** acrescentar resultado retrospectivo, rótulos por estratégia e global; encerrar o bloco.
- **Mapa de Estratégias:** registrar ausência de suporte ao filtro de continuação; manter v14 apenas como pista descritiva.
- **Próximas Hipóteses — C1:** registrar o resultado retrospectivo desfavorável e a validação futura não realizada, sem prioridade automática.
- **KB-0167 — Análise gráfica: o que sobra depois do custo:** atualizar a avaliação local da C1 sem generalizar para toda tendência diária.
- **Revisões-Astra/H-027-resultado:** registrar reprodução integral e as duas lacunas do instrumento, distinguindo-as do resultado atual.
- **Spot/README:** esclarecer que os números da v14 no R86 pertencem aos sinais do Lab, não ao desempenho executado da mesa.
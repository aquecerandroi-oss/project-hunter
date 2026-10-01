**RESUMO**

**A réplica sustenta a reprodução computacional da H-027; não elimina erros compartilhados de dado, relógio ou desenho estatístico. O resultado global correto é NÃO CONFIRMA, pela emenda das 03:02Z.** Momentum REFUTA o tamanho previsto; volume_anomaly permanece em LIMITE DE DADO. Os dois relatórios concordam nisso: [h027.txt:23](C:/dev/project-hunter/.claude/state/r86/h027.txt:23) e [out_amend.txt:16](C:/dev/project-hunter/.claude/state/r86-replica/out_amend.txt:16).

Encontrei uma ressalva temporal concreta: `received_at` usa `now()` do PostgreSQL, que marca **o início da transação**, não necessariamente a inserção nem a disponibilidade para outra sessão. Isso exige limitar a conclusão da auditoria, mas não demonstra que houve contaminação nesta amostra.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, papel `quant-engineer`.

**TESTES**

Não executei pytest, os ajustes estatísticos ou novas consultas ao banco. Conferi código, pré-registro, saídas existentes e fiz uma checagem somente em memória do `cache/sig.csv`, usando `Import-Csv`, `DateTimeOffset` e `Group-Object`. Saída real:

```text
signals=7151 exchanges=binance obs_off_grid_or_after_emission=0 cross_UTC_day=0 max_lag_seconds=119.97037
duplicate_signal_ids=0
```

Portanto, **neste export**, trocar o cluster de `data(obs)` para `data(emitted_at)` não muda nenhuma atribuição diária. O alinhamento à grade também passou, embora isso sozinho não prove a semântica histórica do envelope.

**MUST-FIX**

1. **Corrigir a afirmação de que a auditoria provou disponibilidade efetiva antes da emissão.**

   O modelo define `received_at` com `server_default=func.now()`, e o escritor omite esse campo, inserindo somente candles finais com `ON CONFLICT DO NOTHING`: [market_data.py:61](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:61), [persist_rows.py:103](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:103). No PostgreSQL, `now()` corresponde ao início da transação. [Documentação oficial](https://www.postgresql.org/docs/current/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

   **Cenário de falha:** transação começa às 05:30:00; sinal é emitido às 05:30:10; backfill é inserido e commitado às 05:30:20. O candle recebe 05:30:00 e passa nas duas guardas, apesar de não estar disponível ao sinal. A auditoria por chave primária repete a mesma comparação: [audit.py:56](C:/dev/project-hunter/.claude/state/r86-replica/audit.py:56).

   A correção imediata é editorial: “400 verificações passaram contra o carimbo persistido”, sem transformar isso em prova absoluta de disponibilidade. Para encerrar a ressalva, é necessária evidência de visibilidade/commit ou um limite documentado da duração das transações. **Não afirmo que esse cenário ocorreu no R86.**

2. **Antes de reutilizar o instrumento, completar as regras da emenda nos caminhos degenerados.**

   Na réplica, `amend.py` imprime o posto da amostra inteira, mas prossegue para OLS; verifica finitude de `X`, não de `y`; e a confirmação conta quatro coeficientes positivos sem exigir quatro partições distintas: [amend.py:19](C:/dev/project-hunter/.claude/state/r86-replica/amend.py:19), [amend.py:56](C:/dev/project-hunter/.claude/state/r86-replica/amend.py:56), [amend.py:116](C:/dev/project-hunter/.claude/state/r86-replica/amend.py:116).

   **Cenário de falha:** quatro limiares produzem a mesma partição identificável e positiva; as demais cláusulas passam; a réplica declara CONFIRMA sem o patamar exigido. A emenda também exige falha fechada para instrumento inválido.

   No primário há outro desvio: um corte singular vira `NaN`, mas a validade dos cortes não entra no portão de instrumento; assim, ICs suficientemente baixos ainda podem produzir REFUTA: [analysis86.py:79](C:/dev/project-hunter/.claude/state/r86/analysis86.py:79), [stats86.py:111](C:/dev/project-hunter/.claude/state/r86/stats86.py:111).

   **Esses cenários não aparecem nas saídas publicadas**, que mostram cortes finitos e partições distintas. São defeitos de cobertura do protocolo, não motivo demonstrado para mudar o resultado atual.

**NICE-TO-HAVE**

Sobre os seis possíveis modos comuns:

- **`observation_ts` como instante.** O contrato atual diz explicitamente `source_bar_close`, e momentum/volume_anomaly preenchem esse valor: [envelope.py:128](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:128), [momentum_v1.py:236](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:236), [volume_anomaly_v1.py:199](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:199). Falta provar isso para cada `code_ref` histórico. Se uma versão gravasse abertura da barra, ambas reconstruiriam uma janela atrasada; se gravasse processamento posterior à meia-noite, poderiam usar um dia ainda aberto na decisão verdadeira. Rebuscar o mesmo envelope não detecta erro semântico nele.

- **Cluster por `obs` versus emissão.** Ambas usam `obs.date()`: [data86.py:201](C:/dev/project-hunter/.claude/state/r86/data86.py:201), [replica.py:99](C:/dev/project-hunter/.claude/state/r86-replica/replica.py:99). A escolha precisa estar explícita, mas o meu levantamento encontrou **zero diferenças de dia nos 7.151 sinais**. Não há efeito dessa ambiguidade nesta execução. Continua possível dependência entre dias: operações atravessando meia-noite e choques persistentes não se tornam independentes pelo agrupamento diário.

- **Backfill e primeira inserção.** Agosto ter sido carregado em setembro não é antecipação por si só: os dados históricos podem ser utilizados depois de disponíveis. A guarda também seleciona mercados e datas com infraestrutura suficiente; isso limita a população estudada. O pré-registro já restringe a conclusão ao recorte disponível: [Fila de Hipoteses.md:320](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:320>). A ressalva transacional acima permanece mesmo com inserções imutáveis.

- **Unidade com média de versões.** Está conforme o protocolo: [data86.py:190](C:/dev/project-hunter/.claude/state/r86/data86.py:190), [replica.py:92](C:/dev/project-hunter/.claude/state/r86-replica/replica.py:92). Evita contar a mesma barra repetidamente, mas estima o resultado da **mistura de versões elegíveis naquela barra**. Se versões com stops, custos ou critérios diferentes entram e saem conforme o período, a associação pode refletir composição. Não equivale ao retorno de uma estratégia executável única nem de uma carteira. A sensibilidade só v3 ajuda, sem resolver toda seleção compartilhada.

- **Z fixo na amostra inteira.** Não considero erro automático nem antecipação operacional nesta regressão retrospectiva. Os dois bootstraps reamostram uma matriz já padronizada: [analysis86.py:65](C:/dev/project-hunter/.claude/state/r86/analysis86.py:65), [replica.py:143](C:/dev/project-hunter/.claude/state/r86-replica/replica.py:143). Com intercepto, `β_z = β_bruto × escala_original`: isso conserva a unidade em que o MRE foi declarado. Se o alvo fosse um coeficiente padronizado pela dispersão populacional desconhecida, a incerteza dessa escala precisaria entrar. Recalcular MAD em cada réplica muda esse alvo; não faria essa troca silenciosamente após os resultados.

- **`default_rng(...).integers(0,G,G)`.** Está correto: sorteia G índices uniformes entre 0 e G−1, permitindo repetição; o código concatena clusters inteiros. [stats86.py:63](C:/dev/project-hunter/.claude/state/r86/stats86.py:63), [amend.py:29](C:/dev/project-hunter/.claude/state/r86-replica/amend.py:29), [NumPy](https://numpy.org/doc/stable/reference/random/generated/numpy.random.Generator.integers.html). Mesma semente, ordenação e algoritmo explicam ICs idênticos: não constituem uma segunda experiência estatística. A hipótese compartilhada vulnerável é a adequação dos clusters. Exigir os dois ICs separados não garante cobertura sob dependência simultânea entre mercados e dias — o próprio pré-registro reconhece que não é inferência two-way.

Além disso, ambas herdam os mesmos **desfechos**. Erros no cálculo original de entrada, saída, funding ou custos sobreviveriam à reprodução perfeita da regressão; a réplica lê `r_multiple` e `r_ex_funding` existentes: [q_sig.sql:8](C:/dev/project-hunter/.claude/state/r86-replica/q_sig.sql:8).

**O QUE EU FARIA DIFERENTE**

**Sobre a regra global:** vale a emenda. Ela substitui expressamente essa regra e declara ter sido registrada antes dos desfechos; o relatório registra leitura às 03:06:15. [Fila de Hipoteses.md:324](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:324>), [h027.txt:4](C:/dev/project-hunter/.claude/state/r86/h027.txt:4).

Eu escreveria:

> “Divergência textual resolvida pela emenda prévia: o texto original produziria REFUTA; a regra vigente produz NÃO CONFIRMA.”

**Não é divergência entre primário e réplica**, nem escolha posterior do rótulo mais conveniente. A réplica já apresenta as duas leituras em [out_amend.txt:16](C:/dev/project-hunter/.claude/state/r86-replica/out_amend.txt:16).

Na réplica, eu também:

- Faria a auditoria falhar com código de saída não zero quando encontrar divergência; hoje apenas imprime `FALHAS`: [audit.py:69](C:/dev/project-hunter/.claude/state/r86-replica/audit.py:69).
- Compararia conjuntos e campos nos dois sentidos, sem fallback do ATR para o próprio valor primário nos sinais fora de `mine`: [compare.py:68](C:/dev/project-hunter/.claude/state/r86-replica/compare.py:68).
- Acrescentaria casos adversariais de meia-noite, versões históricas, transação atravessando emissão, MAD zero, cortes repetidos e singularidade. A suíte atual cobre sobretudo reconstrução das features e OLS: [test_replica.py:32](C:/dev/project-hunter/.claude/state/r86-replica/test_replica.py:32).
- Auditava uma amostra dos próprios outcomes por caminho independente. A auditoria dos fechamentos valida outra parte da cadeia.

**CONCORDO COM**

A separação entre réplica inicial e reconciliação posterior das sensibilidades é adequada. As diferenças de réplicas, população de `r_ex` e guarda de 24h estão explicitadas e reconciliadas: [variants.py:28](C:/dev/project-hunter/.claude/state/r86-replica/variants.py:28), [out_variants.txt:1](C:/dev/project-hunter/.claude/state/r86-replica/out_variants.txt:1).

Manteria o resultado publicado como **análise retrospectiva pré-especificada, computacionalmente reproduzida**, com as limitações acima; não como validação futura da C1.

**OBSIDIAN**

- **Fila de Hipóteses — H-027:** registrar NÃO CONFIRMA pela emenda, rótulos individuais e a divergência textual resolvida.
- **Revisões-Astra — H-027-replica:** registrar esta revisão, a ressalva de `received_at` e os casos degenerados do instrumento.
- **Market Collector:** esclarecer início de transação, inserção e disponibilidade efetiva como instantes distintos.
- **Mapa de Estratégias / Próximas Hipóteses:** registrar reprodução retrospectiva sem apresentar a C1 futura como refutada.
## RESUMO

**Concordo com NÃO CONFIRMA para H-023.** Reproduzi D, IC e p do portão das duas variáveis. Não encontrei bug que mude o rótulo atual. Revisão como `quant-engineer`.

**1. Primária e leitura literal da fila**

Pela regra emendada antes dos desfechos:

- **Não refuta pelo tamanho:** IC superior **+0,0376 ≥ +0,01 R**.
- **Não sustenta efeito oposto:** isso exigiria IC superior abaixo de −0,01 R.
- **Não confirma:** D negativo, IC contendo zero, p/Holm 0,497, braço alto negativo e curva ausente. A implementação segue essa ordem. [notes-R83.md:103](C:/dev/project-hunter/.claude/state/notes-R83.md:103), [h023.py:249](C:/dev/project-hunter/.claude/state/r83/h023.py:249)

**Existe argumento literal para REFUTA:** a fila diz “limite inferior abaixo de −0,01”, e −0,113 satisfaz essa condição. Deve ser registrado explicitamente. Porém, aplicar essa leitura como veredito abandonaria a errata documentada antes do contraste. [Fila de Hipoteses.md:276](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila%20de%20Hipoteses.md:276), [notes-R83.md:109](C:/dev/project-hunter/.claude/state/notes-R83.md:109)

Redação sugerida:

> **H-023 NÃO CONFIRMA pelo protocolo emendado. A vantagem prevista de +0,05 R fica acima do limite superior do IC 95% por mercado (+0,0376 R), portanto não é sustentada por esse intervalo. O critério formal de refutação por tamanho, entretanto, exige limite superior abaixo de +0,01 R e não foi atingido.**

Acrescentaria que a exclusão de +0,05 ocorre **no IC por mercado**: o IC por dia, [−0,132; +0,093], ainda comporta esse tamanho. [h023.txt:84](C:/dev/project-hunter/.claude/state/r83/h023.txt:84)

**2. Heterogeneidade sem escolher o resultado favorável**

Publicaria os dois resultados juntos, como **decomposição descritiva pré-especificada**, mantendo o agregado como primária. A análise por estratégia já estava prevista. [notes-R83.md:115](C:/dev/project-hunter/.claude/state/notes-R83.md:115)

> A associação apresentou sinais opostos: momentum +0,097 R e volume_anomaly −0,231 R. Essa heterogeneidade descreve a amostra; não confirma retrospectivamente uma hipótese restrita à momentum.

Duas ressalvas precisam acompanhar essa frase: **todos os tercis de momentum perdem em nível**, e seu IC por dia **[−0,030; +0,233] inclui zero**. Os ICs individuais não substituem um teste formal de interação. Não retiraria volume_anomaly da primária nem inverteria sua direção depois de observar o resultado. [h023.txt:186](C:/dev/project-hunter/.claude/state/r83/h023.txt:186), [h023.txt:193](C:/dev/project-hunter/.claude/state/r83/h023.txt:193)

**3. Secundária `d_low`**

Concordo: **pista para hipótese nova em população nova**. Há associação relativa positiva, sobrevivendo ao Holm especificado e com patamar, mas o braço alto tem média **−0,0974 R**. Além disso, não havia previsão direcional própria para essa secundária. Holm não transforma esse achado em estratégia lucrativa nem em confirmação da primária. [notes-R83.md:101](C:/dev/project-hunter/.claude/state/notes-R83.md:101), [h023.txt:158](C:/dev/project-hunter/.claude/state/r83/h023.txt:158)

ρ=0,767 não dispara um limiar de 0,8, mas tampouco demonstra informação incremental. Os ajustes pós-hoc por ATR% e retorno 4 h foram **separados e grosseiros, por tercis**; não estabelecem independência conjunta dessas variáveis. [posthoc.py:13](C:/dev/project-hunter/.claude/state/r83/posthoc.py:13), [posthoc.txt:1](C:/dev/project-hunter/.claude/state/r83/posthoc.txt:1)

## ARQUIVOS

Sem edição de código ou documentação e sem commit. **Ressalva operacional:** executei pytest sem desabilitar seu cache; ele atualizou `.pytest_cache`, contrariando a restrição estrita de não modificar arquivos.

## TESTES

Comando executado:

```text
uv run pytest .claude/state/r83/test_r83.py -q
.................                                                        [100%]
17 passed in 3.09s
```

Reprodução adicional em memória, com `uv run python -B -c`:

```text
d_high: D -0.03243814860741978
IC [-0.11308105382105646, +0.03755729934369223]
p portão 0.49695030496950304

d_low: D +0.2069408887344084
IC [+0.12064968056066376, +0.28411899861911194]
p portão 0.0002
```

Conferências dos caches: hashes iguais aos registrados; **0** IDs de outcome duplicados, **0** sinais sem outcome correspondente, **0** mudanças na disponibilidade de R; nenhum episódio com rótulos/estratos mistos; nenhuma réplica inválida nos dois ICs.

## MUST-FIX

**Nenhum identificado que altere o veredito atual.**

A auditoria dos pontos pedidos encontrou:

- **Tercis:** cortes por estratégia, empates juntos e população com variável/R disponíveis. A disponibilidade de R não mudou entre extrações; não houve seleção dos cortes pelo valor do retorno. [run.py:49](C:/dev/project-hunter/.claude/state/r83/run.py:49), [h023.py:196](C:/dev/project-hunter/.claude/state/r83/h023.py:196)
- **Junção e dedup:** associação por `signal_id`; deduplicação por versão×mercado×obs antes da guarda, com preferência prospectiva independente do retorno. [run.py:37](C:/dev/project-hunter/.claude/state/r83/run.py:37), [h023.py:164](C:/dev/project-hunter/.claude/state/r83/h023.py:164)
- **Episódios e p:** a permutação transporta todas as linhas do episódio juntas; o portão usa o máximo dos dois p e Holm recebe esses valores. Isso corresponde à emenda. [stats83.py:22](C:/dev/project-hunter/.claude/state/r83/stats83.py:22), [run.py:116](C:/dev/project-hunter/.claude/state/r83/run.py:116), [run.py:168](C:/dev/project-hunter/.claude/state/r83/run.py:168)
- **Temporalidade:** a reconstrução exclui velas futuras, mas não prova disponibilidade operacional no scanner. A emenda já delimita corretamente essa conclusão. [q_feat.sql:35](C:/dev/project-hunter/.claude/state/r83/q_feat.sql:35), [notes-R83.md:123](C:/dev/project-hunter/.claude/state/notes-R83.md:123)

O máximo de dois p **não garante sozinho validade inferencial**: permanecem hipóteses de permutabilidade e dependência temporal. A limitação dos choques comuns entre mercados está declarada; não encontrei fundamento para mudar o rótulo por ela. [notes-R83.md:129](C:/dev/project-hunter/.claude/state/notes-R83.md:129)

## NICE-TO-HAVE

- Corrigir o texto mecânico da secundária: `mill()` reutiliza a previsão sobre **máxima** mesmo ao analisar `d_low`. Pode confundir a leitura, embora não altere o cálculo. [run.py:97](C:/dev/project-hunter/.claude/state/r83/run.py:97)
- Acrescentar teste do caso exato **0,01 ≤ IC superior < 0,05**, distinguindo o rótulo da fila do moinho. O teste atual cobre a errata, mas não esse intervalo específico. [test_r83.py:156](C:/dev/project-hunter/.claude/state/r83/test_r83.py:156)

## O QUE EU FARIA DIFERENTE

Para a nova hipótese de `d_low`, congelaria antes de coletar:

1. **População prospectiva posterior ao R83**, versões e custos fixos; uma unidade por estratégia×mercado×barra, sem sobreposição de desfechos com a amostra de descoberta.
2. **Uma previsão direcional e um contraste primário**, distinguindo capacidade de ordenar retornos de rentabilidade absoluta.
3. **Teste incremental conjunto contra ATR% e retorno 4 h**, com transformação, cortes e pesos definidos previamente; sem escolher depois o ajuste que favoreceu `d_low`.
4. **Parada por tamanho e cobertura temporal**, maturação completa dos outcomes e inferência que considere mercados e choques temporais.
5. Se a pretensão for estratégia utilizável, exigir também **nível líquido positivo**; melhorar relativamente um conjunto perdedor não basta.

Isso segue a lição já registrada de não selecionar limiares pelo resultado nem reutilizar descoberta como validação. [KB-0149: seção 5](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md)

## CONCORDO COM

Manter a primária intacta, preservar a leitura literal ao lado da errata, reportar as estratégias conjuntamente e tratar `d_low` como pista. **Nenhum dos achados justifica resgatar H-023 mudando população, direção ou limiar.**

## OBSIDIAN

- **Fila de Hipoteses — H-023:** encerrar como NÃO CONFIRMA, explicitando leitura literal, errata e exclusão de +0,05 apenas pelo IC por mercado.
- **Dicionario de Variaveis:** registrar a medição retrospectiva de `d_high` e a pista de `d_low`, com redundância e limitações.
- **Proximas Hipoteses:** registrar investigação prospectiva da contribuição incremental de `d_low`.
- **Revisoes-Astra — R83/H-023:** registrar reprodução dos contrastes, 17 testes e ausência de must-fix que altere o rótulo.
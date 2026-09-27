## RESUMO

**REVISE — encontrei cinco correções necessárias antes de congelar J.** Papel: `quant-engineer`, modo OPINIÃO.

O núcleo do estimador e a precedência do veredito estão coerentes com o acordo. Os bloqueios estão na população da identidade, na reconstrução de L, na guarda de L/H e na reprodução da execução congelada.

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os arquivos solicitados e seus testes. Não consultei banco, VPS nem desfechos reais.

## TESTES

Executei com bytecode, cache do pytest e sincronização do ambiente desativados:

```text
uv run pytest infra/research/exp_m26/tests/ -q -k 'not test_fim_de_linha_nao_muda_e_um_byte_muda and not test_recusa_impressao_diferente and not test_recusa_antes_da_leitura and not test_agora_sem_fuso_e_recusado and not test_imprime_o_relatorio'

95 passed, 5 deselected in 9.36s
```

Os cinco excluídos escrevem arquivos temporários. Executei também contraexemplos **sintéticos, exclusivamente em memória**, com `uv run python -B -`; resultados abaixo. Não executei lint, typecheck nem integração SQL.

## MUST-FIX

### 1. Identidade ainda compara suportes temporais diferentes

[robustez.py:98](C:/dev/project-hunter/infra/research/exp_m26/robustez.py:98) remove slopes ausentes, mas estima as duas divisões separadamente. Cada uma pode excluir blocos diferentes. Falta a interseção dos blocos com os dois grupos **nas duas divisões**, exigida pela revisão anterior.

**Cenário reproduzido:** dois blocos, cada um com dez true e dez false:

- A: true rende 0,04; false, zero; slope separa exatamente os grupos.
- B: true rende 0,20; false, zero; todos têm slope positivo.

| Resultado | Esperado: suporte comum A | Código atual |
|---|---:|---:|
| D_linha comparável | 0,04 | 0,12 |
| D_slope | 0,04 | 0,04 |
| Identidade satisfeita (`ok`) | false | true |

O bloco B infla somente D_linha e esconde a redundância. Filtrar o suporte comum antes dos dois cálculos; explicitar isso também no item 16 do protocolo.

### 2. O export corrente não garante “como estava em L”

O export lê `t.completed_at`/`t.migrated_at` correntes em [export_h022.sql:40](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:40). `na_leitura` limita entrada/saída, mas preserva esses metadados em [modelo.py:76](C:/dev/project-hunter/infra/research/exp_m26/modelo.py:76). **`completed_at` pode recuar**, pelo `LEAST` de [repo_token_sql.py:89](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:89).

**Cenário:** em L, venda às 10:06 é avaliável. Depois de L chega informação de conclusão às 10:04. Uma nova exportação transforma A em C, embora L permaneça fixo.

Reprodução sintética sobre a população de teste:

```text
Em L:                       CONFIRMA      A_true=168  C_true=0
Export posterior revisado:   NÃO CONFIRMA  A_true=128  C_true=40
taxa_falha_true=0.23809523809523808
```

**Esperado:** repetir a leitura de L preserva os 168 A. **Atual:** 40 descobertas tardias mudam o rótulo.

É preciso preservar um retrato dos insumos em L ou históricos com instante de disponibilidade. Comparar apenas o instante econômico com L não resolve retroatividade. Também merece cobertura o fechamento processado depois de L com `exit_at` antigo: esse campo recebe o instante da fotografia em [paper_engine.py:251](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:251).

### 3. A guarda anti-antecipação não alcança L/H

A validação explícita percorre somente `c_ops` em [leitura.py:220](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:220). O pareamento verifica igualdade dos minutos, mas não sua observabilidade, em [pacote.py:70](C:/dev/project-hunter/infra/research/exp_m26/pacote.py:70).

**Cenário reproduzido:** mantive C válido e coloquei `features_computed_at = evaluated_at + 1 h` em todas as pernas L/H.

```text
Esperado: LookAheadError; nenhuma inferência secundária
Atual:    168 pares completos; D_pacote=0.05; CONFIRMA
```

Aplicar a mesma guarda às oportunidades dos três braços antes do consumo analítico. Igualdade entre duas features futuras não torna o par causal.

### 4. A ordem física do export altera a aprovação em Holm

O SQL não fixa ordenação, o parser preserva a ordem recebida e a permutação associa os sorteios a essa ordem: [export_h022.sql:58](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:58), [carga.py:108](C:/dev/project-hunter/infra/research/exp_m26/carga.py:108), [estimador.py:196](C:/dev/project-hunter/infra/research/exp_m26/estimador.py:196).

**Reprodução:** 400 unidades, dez blocos de quarenta, true quando `i % 4 == 0`; retornos sintéticos:

```python
z = np.random.default_rng(12).normal(0, .1, 400)
y = 2 * (z + grupo * .02363)
```

Com 10.000 permutações, semente 20260928, apenas invertendo a ordem:

```text
D idêntico:       0.05235356473660196
p original:      0.024797520247975203 → sobrevive a Holm com p2=1
p ordem inversa: 0.025097490250974904 → não sobrevive
```

**Esperado:** mesma população, semente e spec produzem a mesma decisão. Canonicalizar as unidades por identidade estável antes de qualquer sorteio, independentemente da ordem SQL.

### 5. `--reps` permite mudar o procedimento sem mudar a impressão

[ler.py:37](C:/dev/project-hunter/infra/research/exp_m26/ler.py:37) aceita qualquer número de réplicas e o encaminha à leitura. A restrição “só para ensaio sintético” existe na documentação, mas não é aplicada.

**Reprodução da CLI, com export simulado em memória:**

```text
rc=0; reps=100; rotulo_h022=CONFIRMA
p=[0.009900990099009901, 0.009900990099009901]
```

**Esperado:** a leitura oficial recusa `reps != 10000`. **Atual:** publica um rótulo oficial com a mesma impressão digital e outro procedimento.

Separar o caminho de ensaio do oficial, ou recusar a opção divergente na CLI oficial.

## NICE-TO-HAVE

- **Impressão digital:** cobre o fechamento das importações locais verificado pelo teste, e normaliza CRLF/LF corretamente. Não cobre `uv.lock` nem identifica o ambiente numérico. Portanto, considero estável o **hash dos arquivos entre sistemas**, não comprovada a igualdade da execução Windows/Linux. Incluir versões de Python/NumPy e vínculo ao lock: [impressao_digital.py:20](C:/dev/project-hunter/infra/research/exp_m26/impressao_digital.py:20), [impressao_digital.py:49](C:/dev/project-hunter/infra/research/exp_m26/impressao_digital.py:49).
- **Testes faltantes:** acrescentar os cinco contraexemplos acima, bloco duplicado com peso dobrado, réplica que perde o único false observado e réplica secundária sem completo. Hoje os testes verificam principalmente a conta pontual do estresse e resultados agregados dos bootstraps: [test_estimador.py:50](C:/dev/project-hunter/infra/research/exp_m26/tests/test_estimador.py:50), [test_pacote.py:113](C:/dev/project-hunter/infra/research/exp_m26/tests/test_pacote.py:113).
- **Rodadas 1–4:** os aceites de retenção→fill→reinício, recuperação de R1 e suporte causal não são demonstrados pela suíte J. Há testes específicos fora dela, como [test_lab_opportunities.py:408](C:/dev/project-hunter/services/meme-worker/tests/test_lab_opportunities.py:408) e [test_lines_exit.py:74](C:/dev/project-hunter/services/meme-worker/tests/test_lines_exit.py:74); não os executei nesta revisão.

## O QUE EU FARIA DIFERENTE

Antes do congelamento, tornaria explícito um contrato único de reprodução: **insumos preservados em L + ordenação canônica + ambiente identificado + 10.000 réplicas obrigatórias**. Acrescentaria os contraexemplos como regressões, sem mudar população, limiares ou saídas.

## CONCORDO COM

- **p primário:** permutação bilateral dentro dos estratos, mesma estatística e correção `+1` estão corretas; falta resolver a ordenação acima. [estimador.py:190](C:/dev/project-hunter/infra/research/exp_m26/estimador.py:190).
- **p secundário:** diferenças centradas pela média e bootstrap de blocos implementam a convenção acordada. Os bloqueios de pares/amostra mantêm `p=1`. [pacote.py:133](C:/dev/project-hunter/infra/research/exp_m26/pacote.py:133), [pacote.py:171](C:/dev/project-hunter/infra/research/exp_m26/pacote.py:171).
- **Holm e veredito:** família fixa de dois; bloqueios precedem ICs; IC não finito impede confirmar/refutar; REFUTA exige ambos os superiores abaixo da MRE. [veredito.py:37](C:/dev/project-hunter/infra/research/exp_m26/veredito.py:37), [veredito.py:96](C:/dev/project-hunter/infra/research/exp_m26/veredito.py:96).
- **“Conta sem valor”:** correto para C de false. Aumenta `n_false`, preserva a média dos observados e recalcula tudo na réplica; sem false observado, exclui o estrato. [estimador.py:95](C:/dev/project-hunter/infra/research/exp_m26/estimador.py:95).
- **Estresse secundário:** três casos, quantis recalculados e nível de H em perda integral quando ambos faltam estão corretos. [pacote.py:119](C:/dev/project-hunter/infra/research/exp_m26/pacote.py:119).
- **Campos correntes:** não contaminam diretamente `classe_linha`. Também não encontrei vazamento autônomo de `high_water_x` nas apostas já encerradas em L: o descritivo usa A e a atualização normal exige aposta aberta. O problema temporal comprovado é o item 2. [classes.py:54](C:/dev/project-hunter/infra/research/exp_m26/classes.py:54), [robustez.py:117](C:/dev/project-hunter/infra/research/exp_m26/robustez.py:117), [lab_repo_bets.py:118](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:118).
- **Fronteiras:** JSON decimal preservado como `Decimal`, timestamps sem fuso recusados e equação contábil aplicada sem duplicar taxas de papel. [carga.py:94](C:/dev/project-hunter/infra/research/exp_m26/carga.py:94), [carga.py:23](C:/dev/project-hunter/infra/research/exp_m26/carga.py:23), [contabil.py:30](C:/dev/project-hunter/infra/research/exp_m26/contabil.py:30).

## OBSIDIAN

- **EXP-M26 — estrutura do gráfico em moedas maduras:** registrar J em revisão, os cinco bloqueios e as evidências sintéticas.
- **Diálogo — EXP-M26:** esclarecer suporte temporal comum da identidade e preservação dos insumos disponíveis em L.
- **Revisões-Astra — EXP-M26/J:** registrar este parecer, comandos executados e limites da validação.
- **Fila de Hipóteses:** manter H-022 sem resultado; congelamento de J pendente das correções.
**RESUMO**

Como `quant-engineer`, concordo com a separação cálculo/projeção/store, MAD cru, qualidade por dependência e transições puras. Corrigiria principalmente **baselines abaixo do gate, interpretação das confirmações EARLY, timers interrompidos por ausência e alcance da prova bootstrap/live**.

1. **BaselineStore: async e corte no SELECT, sim.**

   Aplique **compatibilidade de versões e corte duplo antes de escolher a revisão mais recente**. Selecionar primeiro e filtrar depois pode descartar a revisão nova e deixar de encontrar uma antiga elegível. O contrato exige também versões compatíveis de feature/algoritmo: [DATABASE.md:1055](/C:/dev/project-hunter/docs/DATABASE.md:1055).

   A chave curta `(market, feature, hour)` funciona na projeção **já vinculada a um perfil de versões e a um corte**. A requisição ao store precisa carregar essas versões. Defina desempate determinístico entre revisões com o mesmo `available_at`, compartilhado pelo SQL e pelo adaptador em memória.

   Eu validaria os invariantes **uma vez na construção da projeção**, incluindo corte e versões. Isso protege entradas vindas de cache/testes; não exige refazer seleção em cada detector. A projeção deve carregar seus cortes para impedir reutilização indevida.

   **Correção na assinatura:** não transforme toda baseline abaixo de 120 observações em ausência de revisão. O modelo explicitamente preserva estatísticas abaixo do gate; a indisponibilidade é da avaliação. Reserve `BaselineUnavailable` sem revisão para situações em que realmente não se pode calcular, como população vazia, preservando contagens/motivo. [analysis_baselines.py:61](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis_baselines.py:61).

   Por fim, `append()` deveria devolver as identidades efetivamente persistidas, inclusive nas colisões: um retry com UUID novo que recebe `DO NOTHING` não pode devolver ao envelope um ID inexistente. A identidade de retry é a constraint com fingerprint: [analysis_baselines.py:72](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis_baselines.py:72).

2. **MAD → severidade: sim, sem 1,4826.**

   A fórmula proposta corresponde exatamente a `weights["normalization"]`, inclusive `saturation_score`. Leia esse bloco por uma configuração tipada e imutável, passada ao cálculo, preservando a versão do perfil usado. [seed_reference.py:195](/C:/dev/project-hunter/infra/scripts/seed_reference.py:195).

   **Ressalva importante:** `abs(d)` serve aos detectores bilaterais. Um `VOLUME_SPIKE` não deveria disparar por uma queda extrema de volume. A unilateralidade precisa vir **antes da decisão de disparo**, não apenas como direção no resultado. O diálogo já restringe módulo aos bilaterais: [dialogue-M2.md:91](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:91).

3. **Limiares do detector: aceito 40/20 como política v1 explícita, não como calibração comprovada.**

   O brief pede que cada detector declare seus limiares versionados; não exige um bloco `weights["anomalies"]`. Portanto, **não ampliaria o escopo para alterar o seed**. [brief-T2.3:10](/C:/dev/project-hunter/.claude/state/brief-T2.3-anomalies-baselines.md:10).

   Use uma definição imutável com limiares, tempos, features, unilateralidade e versão. Se permitir overrides, a identidade deve mudar. Como a severidade depende da normalização externa, `detector_version` sozinho não basta: preserve também a versão/configuração de normalização usada.

   Com a normalização atual, 40 corresponde a 3 MADs e 20 a 2 MADs **antes do arredondamento**. Compare a severidade canônica em duas casas, conforme o acordo; teste as fronteiras. [dialogue-M2.md:188](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:188).

4. **MAD zero: prefiro nenhum `min_scale` na v1.**

   `0,0001` tem uma referência econômica, mas isso **não demonstra uma escala mínima de dispersão** nem sustenta “abaixo disso não há desvio dizível”. A Binance descreve 0,01% como componente de juros por oito horas para a maioria dos símbolos, com exceções e intervalos ajustáveis. [Documentação da Binance](https://www.binance.com/en/support/faq/detail/360033525031).

   Além disso, a feature entregue representa funding **por intervalo**, não uma taxa universal normalizada para oito horas: [deriv.py:64](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:64).

   Minha política:
   - MAD zero e `x == median`: desvio/severidade zero, por convenção explícita;
   - MAD zero e `x != median`: `unavailable: mad_zero`;
   - futuro `min_scale`: justificativa e versão próprias.

   A exceção de igualdade aparece expressamente na checklist final do diálogo: [dialogue-M2.md:245](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:245).

5. **Confidence: separação correta; `min()` é aceitável, mas redundante neste desenho.**

   Com uma observação por minuto e bucket de uma hora, `sample_size ≤ 60 × distinct_days`. Portanto:

   `coverage = sample_size / 420 ≤ distinct_days / 7`

   Logo, usando razões exatas, **`min(coverage, distinct_days/7)` equivale a `coverage`**. O gate de dias continua necessário, mas esse segundo termo não acrescenta penalização. A amostragem e os gates estão em [M2.md:50](/C:/dev/project-hunter/docs/plans/M2.md:50).

   Eu usaria `sample_size / expected_size`, quantizado apenas ao final, mantendo dias distintos separados. No exemplo: `0,2857`; `3/7` arredondado corretamente é `0,4286`. Não escolheria produto sem uma hipótese adicional que justifique penalizar duas vezes aspectos relacionados da maturidade. Isso é confiança de cobertura, não probabilidade de acerto.

6. **Observação válida: somente `quality == ok`, por feature.**

   Incluir observações atrasadas não recupera os movimentos perdidos; pode repetir valores antigos e concentrar artificialmente a distribuição. A exclusão também pode gerar viés de seleção, mas esse viés deve aparecer como cobertura/exclusões, não ser “corrigido” com números inadequados.

   Não descarte um retorno saudável porque o book ou funding está degradado. A T2.2 herda qualidade somente das dependências efetivamente usadas: [engine.py:85](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:85).

   Atenção: **`FeatureVector.number()` pode devolver um valor degradado**; é obrigatório consultar qualidade também. [vector.py:204](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/vector.py:204).

7. **Máquina de anomalias: concordo, com `stale` inelegível e timer reiniciado.**

   Tanto `stale` quanto `unknown` devem preservar o último resultado válido **para exibição**, bloquear atualização da severidade válida e impedir novas contribuições elegíveis. Dado degradado não alimenta anomalias: [PIPELINE.md:77](/C:/dev/project-hunter/docs/PIPELINE.md:77).

   “O relógio não corre” precisa significar **zerar a sequência abaixo de hold**, não pausá-la para somar trechos separados. Quatro minutos abaixo, dez minutos sem dados e mais um minuto abaixo não comprovam cinco minutos consecutivos.

   Recomendo:
   - `severity >= hold`: mantém e atualiza, zerando `below_hold_since`;
   - `severity < hold`, com dados válidos e continuidade: inicia/avança resolução;
   - `stale/unknown`: interrompe a sequência;
   - `now >= detected_at + 4h`: expira, independentemente da qualidade.

   **Active+unknown expira após quatro horas.** A transição precisa ser chamada por timer/watchdog mesmo sem eventos; a função pura não desperta sozinha. O prazo absoluto está em [PIPELINE.md:86](/C:/dev/project-hunter/docs/PIPELINE.md:86).

   Preserve identidade na recuperação antes do encerramento; após `resolved/expired`, somente uma nova observação válida pode iniciar outro episódio. Reentregas/eventos antigos não avançam timers nem reabrem episódios. A unicidade durável já cobre `(market, type)` ativos: [analysis.py:91](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:91).

8. **Estágio: retorno de barra, sim; EARLY com condições restantes, não está autorizado pelo contrato atual.**

   **(a)** Use `return_1h`. A T2.2 distingue explicitamente a janela final da janela que incorpora `forming`: [price.py:65](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:65). Isso segue o contrato; não garante sozinho estágio constante durante o minuto, porque outras entradas podem mudar.

   **(b)** O diálogo original enumera volume, velocidade, OI **e** fluxo alinhado. Não existe ali uma regra “qualquer uma” ou “N de quatro”. O `confirmations: 2` do seed corresponde à histerese temporal; não o interpretaria como quórum de indicadores. [dialogue-M2.md:89](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:89), [seed_reference.py:215](/C:/dev/project-hunter/infra/scripts/seed_reference.py:215).

   Minha leitura conservadora: **as quatro condições são necessárias para EARLY**. “Indisponíveis não confirmam” não permite eliminar uma condição obrigatória. Liberar EARLY com três seria uma mudança explícita de contrato.

   Isso **não bloqueia DEVELOPING/EXTENDED** quando suas próprias condições têm dados válidos. E hoje a limitação não afeta apenas velocidade: também afeta `buy_pressure_5m` e `sell_pressure_5m`. [.claude/state/notes-T2.2.md:157](/C:/dev/project-hunter/.claude/state/notes-T2.2.md:157).

9. **Histerese: sim, precedência antes da confirmação temporal.**

   Mesma candidata em duas observações consecutivas, distintas e estritamente crescentes; candidata diferente reinicia contagem. Duplicatas não contam e eventos atrasados não retrocedem estado. Isso está ratificado em [dialogue-M2.md:186](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:186).

   Perda de qualidade necessária à classificação publicada invalida imediatamente; inclui `degraded`, não apenas ausência, e ATR zero também invalida. Preserve o último timestamp aceito ao zerar a contagem.

   **Defina `observation_ts` como identidade da observação**, não como horário de recomputação. O vetor atualmente recebe `ts=ctx.as_of`; duas recomputações do mesmo candle poderiam fabricar duas confirmações se esse campo fosse usado automaticamente. [engine.py:114](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:114).

   Não limite qualidade apenas a retorno/ATR: EARLY também depende das confirmações; a alternativa EXTENDED depende do histórico de volume. Tampouco imponha qualidade de features irrelevantes a um DEVELOPING válido.

10. **Bootstrap: sim ao resultado por feature; a comparação do vetor é necessária, mas não suficiente sozinha.**

    Grave motivos estruturados, como `historical_source_unavailable`, `semantic_equivalence_unproven`, `warmup` e `gap`; “em construção” é apresentação. O brief já exige motivo gravado: [brief-T2.3:9](/C:/dev/project-hunter/.claude/state/brief-T2.3-anomalies-baselines.md:9). Exclua também as features `_live` dependentes de candle parcial.

    Separe **sete dias de observações úteis** de histórico para aquecimento. `relative_volume_1h` exige 1.440 minutos anteriores/atuais para produzir cada leitura; começar o processamento no início dos sete dias perde parte do primeiro dia. [volume.py:69](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:69).

    Comparar `canonical_bytes()` comprova igualdade daquele vetor, inclusive proveniência. Porém:
    - compare caminhos de construção independentes, com mesmo corte, perfil e origem/checkpoint;
    - compare também `FeatureState` de saída e uma sequência de cortes, incluindo rolagem, gaps e restart;
    - identifique a prova como **bar-only**; o vetor completo de um live com book/trades não será igual ao bootstrap sem essas fontes.

    O estado ATR é devolvido separadamente do vetor e não integra `FeatureVector.canonical_bytes()`: [engine.py:77](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:77), [vector.py:213](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/vector.py:213). A origem do ATR altera sua trajetória: [atr.py:1](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:1).

    Por último: cortes históricos das calculadoras **não autorizam retroagir `available_at` da baseline** calculada hoje. [analysis_baselines.py:121](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis_baselines.py:121).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes: esta é uma revisão estática de desenho, em modo OPINIÃO. Não afirmo aprovação das suítes.

**MUST-FIX**

Antes de implementar, fechar estes cenários:

- **Seleção/identidade da baseline — item 1:** revisão futura ou incompatível esconde uma elegível; retry publica um `baseline_id` que não foi inserido; gate apaga a evidência de maturidade.
- **Unilateralidade — item 2:** queda de volume de −6 MADs vira `VOLUME_SPIKE` com severidade 100.
- **Qualidade/timers — itens 6–7:** valor degradado continua elegível; ausência une dois intervalos abaixo de hold; sem watchdog, active+unknown permanece indefinidamente.
- **Confirmação EARLY — item 8:** três condições publicam EARLY apesar de faltar uma condição exigida pela regra acordada.
- **Identidade temporal — item 9:** duas recomputações do mesmo dado confirmam estágio; um evento antigo restaura uma classificação já invalidada.
- **Replay numérico:** normalize mediana/MAD à representação persistível **antes de usá-las**. O banco guarda dez casas; MAD positivo inferior à resolução pode virar zero após persistência e mudar o replay para indisponível. Teste round-trip SQL versus memória. [DATABASE.md:1035](/C:/dev/project-hunter/docs/DATABASE.md:1035).
- **Bootstrap — item 10:** vetores coincidem num corte, mas checkpoints distintos divergem no próximo; ou uma baseline construída hoje passa a explicar decisões anteriores à sua existência.

**NICE-TO-HAVE**

- Contadores de exclusão por feature/motivo e cobertura por dia.
- Testes de contrato compartilhados entre store SQL e memória, incluindo desempates e retries.
- Corrigir a referência do brief a `seed_weights.py`: a configuração revisada está em [seed_reference.py:160](/C:/dev/project-hunter/infra/scripts/seed_reference.py:160); a referência divergente está no [brief:11](/C:/dev/project-hunter/.claude/state/brief-T2.3-anomalies-baselines.md:11).

**O QUE EU FARIA DIFERENTE**

Separaria explicitamente **revisão calculada**, **avaliação de usabilidade** e **projeção causal**. Manteria `min_scale` vazio, confidence de cobertura simples e EARLY com as quatro condições até uma revisão explícita desse contrato. Escreveria primeiro os testes dos cenários MUST-FIX.

**CONCORDO COM**

Protocol async, detectores sem IO, revisões imutáveis, MAD cru, limiares declarados/versionados, qualidade por dependência, estado recuperável e bootstrap pelas mesmas calculadoras.

**OBSIDIAN**

- **Features (Feature Engine)** — atualizar o estado da T2.2, limites de cobertura e requisitos de equivalência bar-only/checkpoint.
- **Anomalies (Anomaly Engine)** — registrar unilateralidade, MAD zero, qualidade, interrupção de resolução e expiração absoluta.
- **Diálogo Claude ⇄ Astra — M2** — esclarecer quatro condições EARLY versus duas confirmações temporais.
- **Revisões Astra — T2.3** — criar uma nota vinculada com estas recomendações e os cenários de aceite; nenhuma página foi alterada nesta revisão.
**RESUMO**

**Concordo com “concluída — NÃO CONFIRMA por limite de dado”, com as correções abaixo.** A cobertura vem antes do contraste: a própria [H-010:129](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:129>) declara essa insuficiência como limite de dado. “Concluída” encerra esta avaliação; não significa hipótese refutada. Não precisa permanecer “aberta”.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`.

**TESTES**

Auditoria em memória com `Import-Csv` e `uv run --no-sync python -B -`; reprodução do moinho sem executar os trechos que escrevem arquivos. Saída final, código 0:

```text
live 91 obs 1 retro_birth 49 eligible 16
paper 1475 obs 105 retro_birth 698 eligible 223
one 694 obs 26 retro_birth 331 eligible 79
AIRAA predecision_n 87 received_before 0
```

Reproduzi os contrafactuais: observável >20% bloqueia **11/2 vencedoras, Δ +0,063219202 SOL**; retrospectivo >20% **24/10, Δ +0,006038344**; >30% **Δ −0,025495691**. Os tercis e os números de SENTHOS/MMKT também conferem.

**MUST-FIX**

1. **Cobertura retrospectiva está rotulada incorretamente.** “Nasce E reconcilia” resulta em **49/91 (53,8%)**, **698/1475 (47,3%)**, **331/694 (47,7%)**. Os **16/223/79** acrescentam `pct` observável e desfecho não nulos: [build.py:91](C:/dev/project-hunter/.claude/state/r73/build.py:91). A tabela chama essa contagem de “ambas”: [run.py:91](C:/dev/project-hunter/.claude/state/r73/run.py:91).
   
   **Cenário:** AIRAA nasce e reconcilia retrospectivamente, mas é excluída porque `pct` observável é nulo. Corrigir os percentuais **não muda o veredito**: todos continuam abaixo de 60%.

2. **AIRAA prova ausência no arquivo de polling, não ausência de conhecimento da mesa.** O próprio export registra **`quote_source=solana_ws`**: [pop.csv:1554](C:/dev/project-hunter/.claude/state/r73/pop.csv:1554). Existe caminho independente: logs WS → `state.apply_trade` ([event_gate_eval.py:83](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:83)) → fita em memória → features da decisão ([event_gate_rows.py:74](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_rows.py:74)).
   
   **Cenário:** a compra chega pelo WS antes da decisão e só depois aparece em `meme_trades`. O estudo concluiria falsamente “não sabíamos”. Verifique `meme_proposals.reasons[0].series`, cujo identificador é `meme_event_gate_v1` ([event_gate_rows.py:42](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_rows.py:42)), e a evidência histórica de recebimento WS da compra específica. **O material apresentado não prova nem exclui esse recebimento.** Retire “invalida qualquer feature de fita”; restrinja a conclusão à reconstrução por `meme_trades`.

3. **O moinho desloca uma observação do tercil alto para o baixo.** O alto começa em `>= hi`, mas o moinho seleciona `<= hi`: [run.py:113](C:/dev/project-hunter/.claude/state/r73/run.py:113), [stats_core.py:50](C:/dev/project-hunter/infra/research/stats_core.py:50).
   
   **Cenário observado:** braços **188/187**, quando deveriam ser **187/188**. Corrigindo apenas a fronteira, reproduzi **D=+0,0139; IC [−0,0731; +0,0993]; p=0,7959**. Continua NÃO CONFIRMA e não atinge a refutação da fila.

**NICE-TO-HAVE**

Precisão da latência: no `tape.csv`, mediana **43,631 s**, p90 **128,524 s**. As 87 trocas anteriores de AIRAA chegaram juntas às **20:03:25.431490 UTC**.

**O QUE EU FARIA DIFERENTE**

Declararia expressamente que o contraste é exploratório de **fluxo líquido**: a fila registra compras brutas, enquanto `pct` calcula líquido ([load.py:167](C:/dev/project-hunter/.claude/state/r73/load.py:167)). Acrescentar sensibilidades não transforma líquido na variável pré-registrada.

**CONCORDO COM**

Não propor braço de papel nem ativação com este resultado. Ressalva: `max_top10_share` testa `features.top10_share`, outra medida; R73 não é teste direto desse parâmetro ([rules_criteria.py:238](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_criteria.py:238)).

**OBSIDIAN**

- **Fila de Hipóteses:** encerrar H-010 por limite do arquivo analisado, corrigindo cobertura e alcance da afirmação sobre AIRAA.
- **Revisões-Astra / R73:** registrar os três achados e separar fita persistida, estado WS e variável pré-registrada.
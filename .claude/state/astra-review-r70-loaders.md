**RESUMO**

Não encontrei antecipação demonstrada nas features sob os carimbos e a guarda descritos. Há **dois MUST-FIX de censura/denominador** antes de interpretar resultados como representativos das decisões do Lab.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`, em OPINIÃO.

**TESTES**

Inspeção estática; não executei carregadores, SQL nem testes.

**MUST-FIX**

- **Descartes anteriores ao moinho escondem o denominador.** O SQL já exclui sinais sem outcome terminal e R disponível ([q_lab.sql:14](C:/dev/project-hunter/.claude/state/r70/q_lab.sql:14), [q_ret.sql:6](C:/dev/project-hunter/.claude/state/r70/q_ret.sql:6)); os loaders também descartam ausências ([load70.py:172](C:/dev/project-hunter/.claude/state/r70/load70.py:172)). O moinho só conta censura nas linhas recebidas ([protocol.py:236](C:/dev/project-hunter/infra/research/protocol.py:236)). **Cenário:** perdas fecham rapidamente e ganhos continuam abertos no corte; o estudo recebe predominantemente perdas, sem mostrar os pendentes. Reportar emitidos → pendentes/sem desfecho → terminais → features disponíveis → usados, com corte fixo de extração.

- **Pergunta 4 — casamento H-004:** perder o casamento é exclusão silenciosa, não recusa pela guarda, contrariando a docstring ([load70.py:69](C:/dev/project-hunter/.claude/state/r70/load70.py:69), [load70.py:83](C:/dev/project-hunter/.claude/state/r70/load70.py:83)). **Cenário:** entre os exports, uma aposta mais antiga termina; `q_inst` passa a escolher essa primeira aposta fechada do mint, enquanto `pct.csv` conserva a anterior ([q_inst.sql:4](C:/dev/project-hunter/.claude/state/r70/q_inst.sql:4)). O mint desaparece conforme o tempo de encerramento. Exportar instantes junto da população congelada; contar não casados ou abortar diante deles. **Pode ser informativa; não está demonstrado que seja.**

**NICE-TO-HAVE**

- **Pergunta 3 — cinco barras:** exigir `nbars=5` é coerente com janela completa ([load70.py:162](C:/dev/project-hunter/.claude/state/r70/load70.py:162)). Não prova correlação com desfecho nem iliquidez: atraso de recepção e taker ausente também reduzem a contagem ([q_lab.sql:57](C:/dev/project-hunter/.claude/state/r70/q_lab.sql:57)). Reportar cobertura por mercado/dia e motivo, comparando desfechos disponíveis de incluídos/excluídos. Atenção: zero barras desaparece previamente em [load70.py:178](C:/dev/project-hunter/.claude/state/r70/load70.py:178).
- **Pergunta 6:** publicar número de blocos e sensibilidade a duração/âncora; uma âncora correta não garante blocos suficientes ou independentes.

**O QUE EU FARIA DIFERENTE**

Congelaria população e instantes no mesmo export, mantendo um demonstrativo separado de todas as exclusões.

**CONCORDO COM**

1. **Snapshot:** truncar `fs.ts` não introduz futuro quando o cálculo verdadeiro também satisfaz `features.ts ≤ t` ([q_lab.sql:36](C:/dev/project-hunter/.claude/state/r70/q_lab.sql:36)). O SQL sozinho não filtra fita futura; depende da guarda de `snap_tape ≤ snap_as_of`, que a rejeita ([guards.py:112](C:/dev/project-hunter/infra/research/guards.py:112)).
2. **Taker:** nenhuma barra fecha depois de `t`: o maior fecho é `floor_minute(t) ≤ t`, com recepção também limitada ([q_lab.sql:50](C:/dev/project-hunter/.claude/state/r70/q_lab.sql:50)).
5. **Retorno:** sinal correto para short linear: entrada 100, saída 90 → líquido **+9,86%**. `exit_price` alimenta o **desfecho**, não a feature ([load70.py:116](C:/dev/project-hunter/.claude/state/r70/load70.py:116)).
6. **Blocos:** âncora fixa UTC é correta para blocos não sobrepostos de três dias e não usa futuro ([load70.py:149](C:/dev/project-hunter/.claude/state/r70/load70.py:149)).

**OBSIDIAN**

- **Fila de Hipóteses** — registrar denominadores e exclusões do R70, especialmente H-004/H-006.
- **Revisões-Astra / R70** — registrar este parecer e as condições temporais verificadas; nenhuma página foi alterada.
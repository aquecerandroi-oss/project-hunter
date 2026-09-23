**MUST-FIX**

- **A guarda é contornável.** `reset(P, view)` recebe `P["path"]` completo ([policies.py:159](/C:/dev/project-hunter/.claude/state/r74/policies.py:159)). Reproduzi uma política que lê o ponto futuro em `reset`: mudar somente esse futuro alterou a saída de **1,6 s para 301,6 s**, sem exceção. Passe apenas contexto de entrada e teste esse escape. As políticas atuais não exploram a brecha; o problema é a garantia anunciada.
- **A regra proposta não é integralmente o pré-registo.** A fila termina em **1,30** e exige **uma posição por mint** ([Fila:135](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:135>)). Cenário: 1,30 vence; adicionar 1,50 transforma uma borda em interior e pode trocar REFUTA por CONFIRMA. Use a grade original como principal; 1,50 como extensão declarada. Se houver mints repetidos, congelar a seleção ou declarar a mudança de população — bootstrap por cluster não equivale a deduplicar.
- **Congelar a interpretação de 5 s.** Minha leitura: “ganho desaparece” = **D≤0 da mesma política**, escolhida a 1,6 s. **D>0 com IC inferior≤0** significa evidência insuficiente, não desaparecimento do ganho. Exigir IC inferior>0 para confirmar é um acréscimo conservador; a fila não o explicita. A combinação das duas populações também é uma nova operacionalização ([Fila:137](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:137>)).

**NICE-TO-HAVE**

- **“Na mesa” mede oportunidade posterior, não identifica sozinho alvo cedo/tarde.** `left_max` é um teto ex post; zero também pode significar ausência de recuperação. `left_end` mede a vantagem de segurar até o horizonte. Saídas precoces têm mais tempo para acumular máximos; `time_stop` dá zero por construção ([policies.py:138](/C:/dev/project-hunter/.claude/state/r74/policies.py:138)). Reportaria **total e estratificado por motivo**, com contagens e tempo restante. Só alvos serve como diagnóstico, mas condiciona a um resultado da política; não substitui D incondicional.
- Na sensibilidade, esclarecer que a entrada permanece histórica e `c` altera **c/2 na saída**; não reprecifica toda a ida e volta ([sim.py:86](/C:/dev/project-hunter/.claude/state/r72/sim.py:86), [sim.py:247](/C:/dev/project-hunter/.claude/state/r72/sim.py:247)).
- Congelar desempates do “melhor”: hoje `max` escolhe o primeiro empatado, podendo selecionar a borda mesmo com interior igualmente bom ([stats.py:56](/C:/dev/project-hunter/.claude/state/r74/stats.py:56)).

**CONCORDO COM**

- **Aplicar (b) literalmente**, inclusive se a borda ganhar fortemente, com precedência da refutação. Escrever: “refuta pelo critério de borda”; isso não demonstra ausência de vantagem econômica. O texto é explícito ([Fila:138](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:138>)).
- Vizinho com D>0, sem contar 1,15 e sem misturar famílias, é uma operacionalização razoável do patamar.
- **Só a política incondicional conta.** Os +3,44 pp do subgrupo selecionado pelo futuro não estimam seu efeito. A própria memória já registra essa restrição ([KB-0152:93](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0152-a-oscilacao-existe-o-giro-nao-paga.md:93)).

Verificação: `uv run pytest .claude/state/r74/test_r74.py -q -p no:cacheprovider --confcutdir=.claude/state/r74` → **39 passed, 1 warning** (`asyncio_mode`, plugins automáticos desativados). Sem alterações de arquivos; dados reais não executados.

**OBSIDIAN**

- **Fila de Hipoteses — H-011:** explicitar grade principal, população, desempates, regra de 5 s e combinação das populações.
- **Revisoes-Astra — R74:** registrar a brecha da guarda e os limites interpretativos das métricas “na mesa”.
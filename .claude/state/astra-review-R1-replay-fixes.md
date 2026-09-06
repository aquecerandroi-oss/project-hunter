**RESUMO — BLOCKED.** As correções avançaram, mas corte temporal e portão ainda têm brechas.

**ARQUIVOS**

Nenhum alterado. Revisão como `quant-engineer`.

**TESTES**

Com sincronização, bytecode e cache desativados:

```text
uv run pytest packages/indicators/tests/unit/test_replay_policies.py packages/indicators/tests/unit/test_replay_stats.py services/strategy-worker/tests/test_replay_arms.py -q
46 passed in 2.20s
```

Integração e banco não reexecutados.

**MUST-FIX**

- **(1) Velas fechado; funding não.** `settle` lê até `exit_ts + 2s`, sem receber `as_of`. **Cenário confirmado em memória:** saída intrabar no corte; funding em `as_of + 1ms` fornece a segunda observação de cadência e transforma `funding_schedule_unknown` em funding zero. Ainda existe look-ahead na liquidação. [settle.py:60](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:60)

- **(3) Portão no lugar certo, classificação incompleta.** Antes dos contrastes está correto. Porém, registro `TERMINAL` versus replay `NO_ENTRY` vira `unresolved`, saindo do denominador. **Contraprova executada:** um acerto + 99 dessas divergências → `trajectory_rate=1.0000`, `passed=True`. Classificar essa discordância como divergência de trajetória. [reproduce.py:115](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/reproduce.py:115), [replay_exits.py:143](C:/dev/project-hunter/infra/scripts/replay_exits.py:143)

- **Maturidade continua dependendo do desfecho.** O pareamento exige dois resultados terminais, mas não horizonte maturado. **Cenário:** duas saídas rápidas entram; outro sinal de mesmo horizonte sai da comparação porque um braço permanece aberto. Isso seleciona resultados pela velocidade de resolução. Aplicar o corte comum de horizonte antes de parear. [contrast.py:95](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/contrast.py:95)

**NICE-TO-HAVE**

O `input_digest` precisa incluir os insumos reais: hoje omite velas, funding e plano. Um backfill pode mudar os contrastes mantendo o hash. O artefato atual traz `ae8fdd1e…`, não `228e8f66…`. [load.py:317](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/load.py:317), [r1-proof.md:6](C:/dev/project-hunter/.claude/state/r1-proof.md:6)

**O QUE EU FARIA DIFERENTE**

Distinguir explicitamente reconstrução com dados disponíveis hoje de reconstrução da informação disponível naquele instante.

**CONCORDO COM**

**(2), (4) e (5) fecharam:** geometria reexecutada e aberturas auditadas; snapshot único; denominadores e magnitude absoluta explícitos. [engine.py:330](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/engine.py:330), [reproduce.py:130](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/reproduce.py:130), [load.py:69](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/load.py:69), [render.py:109](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/render.py:109), [render.py:175](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/render.py:175).

A linguagem final **não afirma confirmação**; explica corretamente `B=1` e ausência de evidência de equivalência. A afirmação de que o portão barra divergências, porém, excede sua implementação atual. [r1-proof.md:114](C:/dev/project-hunter/.claude/state/r1-proof.md:114)

**OBSIDIAN**

- **EXP-0004 — Políticas de saída:** registrar os bloqueios restantes e identificar corretamente o artefato.
- **Revisão Astra — R1:** registrar fechamento parcial e as contraprovas desta rodada.
- **Strategy Performance:** distinguir horizonte maturado de saída antecipadamente resolvida.
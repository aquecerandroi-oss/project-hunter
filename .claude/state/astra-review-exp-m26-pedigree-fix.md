**RESUMO**

**APPROVE_WITH_NITS.** Não encontrei must-fix no diff. A leitura leve preserva as decisões atuais de 1 min; os diagnósticos omitidos passam a `None`, conforme solicitado. A aprovação é da revisão estática, não da execução dos testes nem do funil F.

1. **Há consumidores que passam a receber `None`: sim, os registros de diagnóstico.** `proposals_reasons` grava os dois campos diretamente; `lab_opportunities._pedigree` serializa todos os campos sem converter ausência em zero. Isso muda os registros, mas não acrescenta uma recusa. [proposals_reasons.py:123](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_reasons.py:123), [lab_opportunities.py:138](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_opportunities.py:138).
   - `mature_gate_step` decide por `evaluate_gate` e depois registra o pedigree recebido. [lab_opportunities.py:248](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_opportunities.py:248).
   - `scale_step` não recebe nem repassa esse pedigree. [lab_scale_step.py:57](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_scale_step.py:57).
   - A sonda de recusados recebe o pedigree da pista rápida, que continua completo. [lab_fast.py:175](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:175), [lab_fast.py:230](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:230).

2. **O critério protege os consumidores atuais.** O chamador rápido seleciona apenas conjuntos `15s`; qualquer um deles força `full=True`. O chamador de minuto passa todos os conjuntos `1m`; basta um pedir `pedigree_repeat_dumper` para todos receberem a leitura completa. E2-b continua sendo lido separadamente quando solicitado. Não encontrei caminho atual que entregue leitura leve à mesa ou omita um campo necessário à decisão. [lab_fast.py:155](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:155), [lab.py:251](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab.py:251), [lab_repo_e2b.py:203](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_e2b.py:203).

3. **`None` não elimina uma recusa de dump na pista elegível à leitura leve.** Nela, o switch está desligado e `evaluate_repeat_dumper` nem é chamado. Com o switch ligado, a consulta é completa. As recusas `creator_unknown`, `creator_serial`, `symbol_unknown` e `symbol_clone` continuam dependendo das duas contagens preservadas. [proposals.py:244](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:244), [pedigree.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/pedigree.py:145).

4. **O fallback é conservador para um relógio novo:** se chegar a `lineage_for`, recebe todos os campos. Isso preserva informação, não garante desempenho nem implementa o despacho desse relógio. Hoje, nomes desconhecidos são rejeitados na configuração. [lab_repo_e2b.py:206](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_e2b.py:206), [lab_models.py:109](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_models.py:109).

**ARQUIVOS**

Revisei os seis arquivos indicados e os consumidores acima. Nenhum arquivo criado ou modificado por mim.

**TESTES**

Não executei pytest, lint ou integração nesta revisão estritamente sem escrita.

Executei comparação textual em memória do SQL anterior em `HEAD` com o novo:

```text
HEAD chars: 3218
Diff chars: 3218
Identical: True
SHA256: 6b42935c194e875741e4b40e7a4c66f422abd6a77b7d05908bdd92e027ceb74d
```

O hash coincide com o pin de [test_pedigree_light.py:37](C:/dev/project-hunter/services/meme-worker/tests/test_pedigree_light.py:37). `git diff --check` nos três arquivos rastreados do escopo terminou com código 0; somente avisos de CRLF.

**MUST-FIX**

Nenhum cenário concreto de regressão identificado.

**NICE-TO-HAVE**

- **LOW — atualizar o contrato de `None`.** A documentação ainda diz que dump ausente significa exclusivamente identidade desconhecida. Agora também significa “não consultado”; quem interpretar os registros pela documentação pode classificá-los incorretamente. [pedigree.py:115](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/pedigree.py:115).
- Acrescentar teste de persistência via `mature_gate_step`, verificando `null` nos diagnósticos e as mesmas recusas; o teste novo de equivalência termina em `evaluate_gate`. [test_pedigree_light.py:194](C:/dev/project-hunter/services/meme-worker/tests/test_pedigree_light.py:194).
- Acrescentar à matriz um relógio diferente de `1m` e `15s`, explicitando o fallback futuro. [test_pedigree_light.py:158](C:/dev/project-hunter/services/meme-worker/tests/test_pedigree_light.py:158).

**O QUE EU FARIA DIFERENTE**

Manteria a implementação. Ajustaria apenas a documentação da ausência e os testes acima. Depois repetiria o F pela via corrigida, conforme a pendência já registrada em [EXP-M26-F.md:36](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/EXP-M26-F.md:36).

**CONCORDO COM**

Compartilhar os fragmentos das duas contagens, manter `full=True` por padrão e preencher os campos não consultados com `None`. A seleção continua abrangendo todos os mints recebidos, sem filtro pela porta pura; não foi introduzida conversão temporal. [lab_repo_pedigree.py:55](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:55), [lab_repo_pedigree.py:166](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:166), [lab_repo_e2b.py:207](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_e2b.py:207).

**OBSIDIAN**

- **EXP-M26-F** — acrescentar este parecer, distinguindo diagnósticos ausentes de decisões preservadas.
- **Open Bugs** — registrar revisão favorável do conserto; manter validação operacional pendente.
- **EXP-M26-grafico-em-moedas-maduras** — registrar a revisão do instrumento sem declarar F aprovado antes da repetição.
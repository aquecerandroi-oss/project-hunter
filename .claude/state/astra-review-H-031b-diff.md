## RESUMO

**BLOCKED para reportar DONE.** Concordo com o desenho da H-031b, mas há três correções necessárias: ativação antes da troca do worker, corrida entre as guardas e a cópia, e aceitação silenciosa de `null`.

Considerei a memória de **KB-0149**, **Fila de Hipóteses — H-031b/emenda 1**, **Mapa de Estratégias** e **EXP-M27**. Nenhum arquivo foi modificado.

## ARQUIVOS

Revisei o diff indicado, os arquivos novos, o patch sequenciado e os consumidores relacionados. **Criados/modificados por mim: nenhum.**

## TESTES

Verificações somente de leitura:

```text
git apply --check .claude/state/h031b/sequenced.patch
patch_check_exit=0

git diff --check -- <os três arquivos modificados do escopo>
diff_check_exit=0
```

**Pytest e integração não executados.** O patch não foi aplicado e nenhuma migração foi executada; portanto, não declaro testes aprovados.

## MUST-FIX

1. **Alta — o teste da migração não protege a janela de deploy.**

   O deploy atual executa a migração **antes** de substituir os serviços: [compose.sh:242](C:/dev/project-hunter/infra/vps/compose.sh:242). A semente nasce `active`: [meme_absorb_semdump_arm.py:94](C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:94).

   **Cenário:** a migração termina; o worker antigo ainda executa um ciclo — ou a recriação falha. Ele carrega o gêmeo sem interpretar a chave e abre apostas com a saída ligada. Na árvore atual, a propagação ainda está apenas no [sequenced.patch:40](C:/dev/project-hunter/.claude/state/h031b/sequenced.patch:40); [effective_params:250](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:250) não a passa. Atualizar depois não corrige essas apostas: a retomada lê os parâmetros persistidos, em [lab_repo_bets.py:224](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:224).

   **Correção:** garantir o código compatível **rodando antes da ativação**, por implantação em duas etapas ou interrupção controlada do worker durante a transição. Uma trava adicionada apenas ao binário novo não protege o antigo. O teste é necessário, mas insuficiente.

2. **Média — as guardas não estão no mesmo statement da cópia nem protegidas contra atualização concorrente.**

   São três `op.execute` distintos: [meme_absorb_semdump_arm.py:120](C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:120). O predicado reutilizado exige identidade/status, mas não relógio nem booleano: [linha 62](C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:62).

   **Cenário:** a guarda aceita o original; um `--set-param` concorrente muda `clock` para `1m` ou `exit_on_creator_dump` para `false`; o `INSERT` copia o documento novo; a pós-checagem aceita porque compara contra esse mesmo documento. A migração termina justamente na condição que prometia recusar.

   **Correção:** bloquear a linha original antes de validar, mantendo o bloqueio até terminar a cópia e a pós-checagem. A cópia via `INSERT … SELECT` está correta; o que falta é estabilizar a origem durante todo o procedimento.

3. **Média — “estrito” ainda aceita JSON `null` como `True`.**

   [strict_bool_or:124](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:124) trata `None` como ausência, e [from_json:228](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:228) usa `.get`, perdendo a distinção entre chave ausente e `null`. O patch repete isso no conjunto: [sequenced.patch:26](C:/dev/project-hunter/.claude/state/h031b/sequenced.patch:26).

   **Cenário:** depois do patch, `--set-param exit_on_creator_dump=null` no gêmeo passa pela validação e religa silenciosamente a saída. A migração, por sua vez, rejeita `null` no original.

   **Correção:** aplicar o padrão somente quando a chave estiver ausente; chave presente precisa ser `bool`. Acrescentar `null` aos testes do conjunto, da aposta e do validador.

## NICE-TO-HAVE

- **Testar os caminhos reais de saída.** Os testes novos exercitam `evaluate_exit`, mas não executam a vigia em `_process_one` nem os caminhos de pool: [test_lab_params_creator_dump.py:58](C:/dev/project-hunter/services/meme-worker/tests/test_lab_params_creator_dump.py:58). Acrescentaria regressão com venda observada, reinício e próxima foto.
- **Expor a chave na API para auditoria.** Hoje ela não quebra a resposta, mas também não aparece: o conversor seleciona campos explicitamente em [meme_desk_out.py:103](C:/dev/project-hunter/apps/api/hunter_api/services/meme_desk_out.py:103).
- Dividir `test_migration_0069.py`: contei **435 linhas**. O gate atual exclui testes, em [check_file_size.py:36](C:/dev/project-hunter/infra/scripts/check_file_size.py:36), mas o arquivo ultrapassa o limite literal informado no brief.

## O QUE EU FARIA DIFERENTE

Fecharia primeiro o patch sequenciado e a validação de `null`; depois provaria a propagação até uma aposta persistida e recarregada. A ativação ficaria condicionada à imagem compatível já em execução, com teste concorrente da migração e registro de T0.

## CONCORDO COM

Respondendo diretamente às cinco perguntas:

1. **Saídas:** com o patch completo e uma aposta gravada com `false`, não identifiquei desvio que gere novo `creator_dump`. A vigia consulta a chave em [lab_bets.py:213](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:213); o motor usa `bet.params.exit_rules()` em [paper_engine.py:215](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:215); os caminhos de pool chamam esse motor em [lab_bets_pool.py:146](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets_pool.py:146). O point read apenas executa o motivo recebido, em [lab_point_read.py:82](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_point_read.py:82). A launch lane seleciona relógio `event`, não o gêmeo `15s`: [launch_lane_repo.py:33](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_repo.py:33). **Intenções já persistidas continuam sendo executadas**, reforçando o bloqueio de deploy: [lab_bets.py:209](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:209).

2. **Migração:** concordo com copiar os parâmetros vivos e com `ON CONFLICT DO NOTHING` seguido de pós-checagem estrita de identidade/conteúdo: [meme_absorb_semdump_arm.py:90](C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:90). **Discordo da garantia de concorrência**, pelo MUST-FIX 2.

3. **Compatibilidade:** não identifiquei leitor que quebre pela chave adicional. A API lê campos nomeados; a persistência usa `as_json`, em [lab_repo_bets.py:195](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_bets.py:195). Não encontrei dependência da igualdade integral do documento nos scripts de pesquisa/reclassificação examinados. É conclusão estática, não prova por suíte.

4. **Deploy:** **não basta o teste falhar**; é necessária a garantia operacional descrita no MUST-FIX 1.

5. **CLI:** **com o patch**, a string JSON `"false"` é rejeitada pelo carregador e convertida em `WouldNotLoad`: [meme_rule_set_validate.py:54](C:/dev/project-hunter/infra/scripts/meme_rule_set_validate.py:54). **Sem o patch, essa rejeição não existe.** `false` sem aspas JSON vira booleano pelo parser: [meme_rule_set_params.py:81](C:/dev/project-hunter/infra/scripts/meme_rule_set_params.py:81). Aspas consumidas pelo shell não tornam o valor uma string JSON.

Concordo também com `research_only`: a seleção automática do executor exige `operator`, em [auto_approve.py:113](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/auto_approve.py:113).

## OBSIDIAN

- **EXP-M27 — O gêmeo sem creator_dump:** registrar a ordem efetiva de implantação e os critérios de ativação segura.
- **H-031b-diff:** registrar os três bloqueios, as correções e a validação posterior.
- **Fila de Hipóteses — H-031b:** vincular a revisão e registrar T0 somente após garantir o worker compatível.
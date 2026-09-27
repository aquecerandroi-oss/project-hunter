**RESUMO**

**Concordo com “H-017 concluída — NÃO CONFIRMA”, no papel, entre os pares avaliáveis do EXP-M25.** Não encontrei erro que mude esse rótulo. Há correções necessárias na interpretação dos preços e na apresentação da sensibilidade.

Revisão como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Li integralmente os seis arquivos pedidos e conferi a origem dos preços no SQL e no motor de fill. Não executei pytest nem reproduzi o bootstrap; os “19/19” são registro anterior, não validação desta rodada.

Recalculei os quocientes dos 74 pares de mesma foto diretamente do CSV congelado, usando `Import-Csv`, `ConvertFrom-Json` e `Measure-Object`, sem escrita:

```text
n                         74
mean_fill_over_trigger    -0,019828757945238
mean_trigger_over_fill    +0,092083088934687
```

**MUST-FIX**

1. **Corrigir “gatilho em média 2% mais caro”.**

   A ligação dos campos está correta: `ctl_mpx_before` vem de `entry.marginal_price_before_sol`, e o outro preço vem do bloco `entry_pullback`. O cálculo é **fill/gatilho − 1**, não gatilho/fill − 1. São preços marginais, não preços médios executados. Fontes: [q_h017.sql:49](C:/dev/project-hunter/.claude/state/r82/q_h017.sql:49), [h017_run.py:114](C:/dev/project-hunter/.claude/state/r82/h017_run.py:114), [paper_fill.py:182](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:182).

   Redação correta: **“Nos 74 pares, o preço marginal da foto ficou, em média, 1,98% abaixo do gatilho, tomando o gatilho como denominador.”** A média do quociente inverso é **+9,21%**, como conferido acima; inverter médias de razões não preserva a porcentagem.

   **Cenário de falha:** reutilizar “2% mais caro” para estimar o custo relativo ao fill produz uma magnitude diferente daquela efetivamente medida.

2. **Declarar que a sensibilidade “preço de decisão” é parcial.**

   Nas **124 entradas**, o código ajusta o braço para o gatilho e o controle para `t0_price`, preservando a saída de cada lado na aproximação proporcional. Nas **27 não-entradas**, mantém braço zero **e controle no retorno original do papel**. Portanto, não põe todos os controles em `t0`. Isso está explícito no ramo `else`: [h017_run.py:132](C:/dev/project-hunter/.claude/state/r82/h017_run.py:132).

   Aceito o cálculo como **“sensibilidade proporcional com saídas fixadas: preços de decisão nas 124 entradas; 27 não-entradas mantidas como observadas”**. Não aceito o título atual sem essa ressalva.

   **Cenário de falha:** numa não-entrada, o preço cai entre `t0` e o fill do controle. A análise mantém a compra posterior mais barata, embora o leitor pense que ela foi reprecificada em `t0`; isso altera a comparação justamente no grupo que contribui positivamente para D.

3. **Restringir as conclusões sobre mecanismo e ausência de vantagem.**

   A decomposição mostra que **a contribuição positiva líquida observada vem de `killed`**: +1,06 pp, contra zero na mesma foto e contribuições negativas de foto posterior e `no_pullback`. Correto como contabilidade da amostra ([h017.txt:22](C:/dev/project-hunter/.claude/state/r82/h017.txt:22)). Entretanto, o código agrupa retornos; não separa causalmente preço, momento e saída ([h017_stats.py:58](C:/dev/project-hunter/.claude/state/r82/h017_stats.py:58)).

   Substituiria “não do preço” por **“as entradas não contribuíram positivamente para D nesta amostra”**. Também restringiria “o papel não escondeu melhora” ao agregado desse diagnóstico: **30 dos 74 gatilhos eram mais baratos que o fill**, portanto houve melhora apagada em parte dos pares ([h017.txt:40](C:/dev/project-hunter/.claude/state/r82/h017.txt:40)).

   **Cenário de falha:** uma entrada mais barata muda o alvo ou o trailing e termina com retorno pior. A decomposição negativa não demonstra ausência de melhora de preço. Tampouco “nenhuma leitura dá +2 pp” pode significar exclusão estatística: o IC primário alcança +4,10 pp e a primeira sensibilidade +5,28 pp ([h017.txt:9](C:/dev/project-hunter/.claude/state/r82/h017.txt:9), [h017.txt:42](C:/dev/project-hunter/.claude/state/r82/h017.txt:42)).

**NICE-TO-HAVE**

Acrescentaria futuramente um teste da montagem completa da sensibilidade, incluindo uma não-entrada. O teste existente verifica a fórmula isolada, sem exercitar essa mistura de tratamentos ([test_r82.py:134](C:/dev/project-hunter/.claude/state/r82/test_r82.py:134)).

**O QUE EU FARIA DIFERENTE**

Manteria explícito que a fórmula é uma **aproximação proporcional**, não uma execução simulada: ela escala `1+r` pela razão de preços marginais; o motor efetivo calcula quantidade, impacto e taxas ([h017_stats.py:72](C:/dev/project-hunter/.claude/state/r82/h017_stats.py:72), [paper_fill.py:171](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:171)).

A sensibilidade adicional pode permanecer descritiva, identificada como análise adicional ao desenho registrado. Não usaria seu IC negativo contra nada para substituir o julgamento primário.

**CONCORDO COM**

**(1) Regra, cláusula por cláusula:** a implementação segue a operacionalização congelada ([h017_stats.py:43](C:/dev/project-hunter/.claude/state/r82/h017_stats.py:43)):

| Critério | Leitura |
|---|---|
| n < 150 | Não: n = 151 |
| REFUTA (a): IC superior de D < +1 pp | Não: +4,10 pp |
| REFUTA (b): IC superior do braço < 0 | Não: +0,22 pp |
| CONFIRMA | Não: D = +0,77 pp; ambos os ICs incluem zero |
| (b) literal | Dispara; sozinha resulta em NÃO CONFIRMA |

É essencial preservar a distinção: trata-se da **operacionalização declarada no R82**, aplicando o princípio da errata, e não de uma definição inequívoca já presente na letra original ([notes-R82.md:80](C:/dev/project-hunter/.claude/state/notes-R82.md:80)).

**(4) Aposentadoria:** **sim, pode recomendar ao orquestrador aposentar os dois braços**, como decisão de encerrar esta linha após a avaliação planejada. NÃO CONFIRMA não exige coleta indefinida nem impede aposentadoria; também não autoriza escrever REFUTA.

Eu comunicaria:

> “H-017 concluída — NÃO CONFIRMA no papel, pela operacionalização pré-declarada. Recomendo encerrar a coleta de recuo_v1/1 e recuo_ctrl_v1/1, preservando os resultados. A aposentadoria é decisão operacional do orquestrador; não constitui prova de ausência de efeito.”

**OBSIDIAN**

- **Fila de Hipoteses — H-017:** registrar NÃO CONFIRMA, a operacionalização e a distinção entre conclusão experimental e aposentadoria.
- **EXP-M24-entrada-no-recuo:** acrescentar a avaliação final com decomposição descritiva e redação corrigida dos preços.
- **EXP-M25-controle-do-recuo:** registrar os 151 pares, exclusões e alcance parcial da sensibilidade.
- **Revisoes-Astra — R82, veredito H-017:** registrar este parecer e as correções de interpretação antes da publicação.
**RESUMO**

**Concordo com H-031, A e B = NÃO CONFIRMA.** O resultado sustenta o rótulo, mas há desvios de implementação e interpretação que precisam acompanhar o fechamento.

Em B, os **20,84% de réplicas inválidas** bloqueiam REFUTA pela emenda. Precisão na redação: primário e S1 **já terminam ambos NÃO CONFIRMA**; a divergência dos intervalos seria um segundo impedimento **mesmo ignorando** aquela trava. O teto passa de +0,0369 no primário para +0,0824 em S1 ([h031.txt:22](C:/dev/project-hunter/.claude/state/r88/h031.txt:22), [h031.txt:44](C:/dev/project-hunter/.claude/state/r88/h031.txt:44), [emenda, item 5](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:357>)).

**ARQUIVOS**

Nenhum criado ou modificado. Li `h031.txt` inteiro; revisão como `quant-engineer`.

**TESTES**

Não reexecutei pytest nem SQL no servidor; os “10 passam” permanecem resultado informado. Fiz verificações independentes em memória, via PowerShell, sobre os CSVs:

```text
SHA256 eligible: 18DCD185127A76D408F722AE432ADA6B0C9F39F13D8C9A985A58D4506D4D313F
decimal_literal: D_adj=0,02006710
float_rule: D_adj=0,08574752
Arm-disagreement rows: 4
```

O hash coincide com [freeze.txt:24](C:/dev/project-hunter/.claude/state/r88/freeze.txt:24).

**MUST-FIX**

1. **Metades mudam o contraste.** O código recalcula suporte e pesos depois de selecionar desfechos e novamente em cada metade ([run88.py:106](C:/dev/project-hunter/.claude/state/r88/run88.py:106), [run88.py:123](C:/dev/project-hunter/.claude/state/r88/run88.py:123)). Conferi: a segunda metade de A usa **somente `flow_v2/9`**; B perde três conjuntos. **Cenário:** uma mudança de composição parece instabilidade temporal do mesmo efeito. Declare o desvio: essas metades não verificam literalmente o contraste congelado; com pesos originais e braços ausentes, a comparação pode ser não avaliável. Isso não resgata CONFIRMA.

2. **“Neutraliza no simulador” excede a evidência.** A secundária mostra associação com **saída classificada `creator_dump`**, não o contrafactual sem essa saída. **Cenário:** diferenças entre conjuntos, duração da exposição ou saídas concorrentes produzem o padrão sem proteção causal. Redação honesta: “Maior concentração associa-se a mais saídas `creator_dump`, inclusive quando o maior comprador não é o criador; não apareceu vantagem de retorno ao excluir concentração. A neutralização pela saída é uma explicação possível, não demonstrada.” ([h031.txt:60](C:/dev/project-hunter/.claude/state/r88/h031.txt:60), [explore.txt:2](C:/dev/project-hunter/.claude/state/r88/explore.txt:2)).

3. **Duas descrições precisam correção.** “Perda ≥50% (measured)” usa todos os fechados no denominador, contando indeterminados como não eventos ([run88.py:165](C:/dev/project-hunter/.claude/state/r88/run88.py:165), [run88.py:172](C:/dev/project-hunter/.claude/state/r88/run88.py:172)). Entre medidos, B é **7/390 = 1,79% versus 70/1257 = 5,57%**; a direção permanece. E “A sem criador” não foi testado: o SQL extrai `is_creator = NULL` para A, depois o filtro aceita todo valor diferente de `"true"` ([q_units.sql:10](C:/dev/project-hunter/.claude/state/r88/q_units.sql:10), [run88.py:243](C:/dev/project-hunter/.claude/state/r88/run88.py:243)). **Cenário:** duas sensibilidades parecem verificadas quando uma tem denominador mal nomeado e outra não tem informação.

4. **Declarar o corte temporal efetivo.** B foi registrado “até o congelamento”, mas o SQL encerra às **00:00Z**, não 00:39:40Z ([prereg_frozen.md:6](C:/dev/project-hunter/.claude/state/r88/prereg_frozen.md:6), [q_units.sql:23](C:/dev/project-hunter/.claude/state/r88/q_units.sql:23)). Se houve unidades nesses 39 minutos, ficaram excluídas. Registre a discrepância; não reextraia para escolher resultado.

**NICE-TO-HAVE**

- Testar lacunas na grade: `plateau()` remove pontos não avaliáveis antes de contar consecutivos, podendo unir trechos separados ([stats88.py:120](C:/dev/project-hunter/.claude/state/r88/stats88.py:120)). Não afeta esta saída, cujos pontos são avaliáveis.
- Destacar no moinho que **REFUTA agrupado não é o veredito H-031**; essa distinção já consta da regra impressa ([moinho.txt:85](C:/dev/project-hunter/.claude/state/r88/moinho.txt:85)).

**O QUE EU FARIA DIFERENTE**

Declararia o bootstrap assim: **“O desenho apresentou suporte temporal insuficiente para o contraste com pesos fixos: 20,84% das réplicas esvaziaram algum braço/conjunto. Os intervalos publicados condicionam-se às réplicas válidas e não autorizam refutação.”** É limitação do desenho, corretamente capturada pela trava — não motivo para trocar agora o bootstrap. O descarte ocorre exatamente assim em [stats88.py:104](C:/dev/project-hunter/.claude/state/r88/stats88.py:104).

**Sim, o empate é a ressalva número um da estimativa pontual de A.** O quantil cai num empate; `≤` coloca essas quatro unidades no baixo. A conversão conjunta para float preserva essa partição; transportar apenas o decimal abreviado do limiar para SQL não preserva ([freeze88.py:114](C:/dev/project-hunter/.claude/state/r88/freeze88.py:114), [run88.py:79](C:/dev/project-hunter/.claude/state/r88/run88.py:79)). Publique ambas as contas como diagnóstico de fragilidade, preservando a partição congelada, sem escolher a mais favorável.

**CONCORDO COM**

- A não confirma também por nível negativo, IC cruzando zero e ausência de planalto; não depende apenas do empate ([h031.txt:10](C:/dev/project-hunter/.claude/state/r88/h031.txt:10)).
- Não identifiquei erro de unidade/Decimal: divide PnL por SOL gasto em `Decimal`, convertendo depois o retorno para estatística ([run88.py:63](C:/dev/project-hunter/.claude/state/r88/run88.py:63)).
- Não encontrei look-ahead nos caminhos examinados: B é capturada antes do `await`, e o freeze registra zero carimbos posteriores à proposta ([event_gate_eval.py:253](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:253), [freeze.txt:4](C:/dev/project-hunter/.claude/state/r88/freeze.txt:4)).
- A saída está ligada pelo padrão de `ExitRules`, não por campo explicitamente preenchido nas apostas ([lab_params.py:148](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:148), [exits.py:99](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/exits.py:99)).
- As seis posições reais são **descrição anedótica**, sem provar neutralização nem falha dela ([real.txt:4](C:/dev/project-hunter/.claude/state/r88/real.txt:4)).

**OBSIDIAN**

- **Fila de Hipóteses — H-031:** fechar NÃO CONFIRMA, registrando limitações e desvios.
- **Revisões-Astra — H-031 resultado:** guardar este parecer e a reconciliação.
- **EXP-M9 — pedigree E2-b:** vincular R88 e destacar fragilidade do empate de A.
- **Mapa de Estratégias:** registrar resultado; secundária como associação exploratória, sem conclusão causal.
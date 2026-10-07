**RESUMO**

Eu faria uma emenda antes dos desfechos. O desenho é defensável como **associação entre o bit gravado e o retorno das primeiras apostas admitidas**, sem interpretação causal sobre ligar/desligar a porta.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`.

**TESTES**

Não executei testes nem extraí desfechos. `Get-FileHash -Algorithm SHA256 .claude/state/r91/prereg_frozen.md` retornou `ABDE5AB4F79FD79A199F80AC92E30648478F37C8BE22441BA9C7869A193C0273`, conforme informado.

**MUST-FIX**

1. **Histórico de parâmetro não prova o regime efetivamente usado.** A pista de eventos julga com `caches.specs`, atualizado por ciclo ([event_gate_eval.py:230](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:230), [event_gate_caches.py:122](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_caches.py:122)). **Falha:** uma proposta posterior à alteração no banco ainda usa a configuração anterior; classificar pelo `proposed_at` atribui “estável” a um `false` que podia incluir queda. Declare essa aproximação e congele tratamento das transições: configuração efetivamente comprovada ou exclusão/contagem do intervalo incerto, sem inventar duração.

2. **Fechar suporte e censura operacionalmente.** O [pré-registro:4](C:/dev/project-hunter/.claude/state/r91/prereg_frozen.md:4) exige cinco unidades por braço antes dos desfechos, mas o primário remove `indeterminate`. **Falha:** um estrato inicialmente suportado perde todas as observações medidas de um braço; implementações podem removê-lo, invalidar D ou reintroduzi-lo em S1. Especifique universo inicial dos estratos, regra de esvaziamento no ponto estimado, contagens usadas nos pesos e tratamento de abertas/retornos ausentes. Fixe também a fronteira de metades comum ao primário/S1 e declare deixa-um-fora sem contraste restante como não avaliável, impedindo CONFIRMA ([pré-registro:5–7](C:/dev/project-hunter/.claude/state/r91/prereg_frozen.md:5)).

3. **Manter os dois membros no Holm e proteger também CONFIRMA.** Escreva `p=1` para medida não avaliável e IC finito/≤1% de réplicas inválidas **nos dois cenários e para ambos os vereditos**. Hoje essa última exigência aparece explicitamente apenas em REFUTA ([pré-registro:7](C:/dev/project-hunter/.claude/state/r91/prereg_frozen.md:7)). **Falha:** retirar P por limite de dado transforma Holm em teste único; ou H confirma usando só a parcela sobrevivente de um bootstrap frequentemente inválido.

4. **O estimador do R88 não pode ser reaproveitado intacto.** Ele fixa pesos proporcionais ao tamanho e invalida a réplica quando qualquer braço esvazia ([stats88.py:56](C:/dev/project-hunter/.claude/state/r88/stats88.py:56), [stats88.py:71](C:/dev/project-hunter/.claude/state/r88/stats88.py:71)). **Falha:** o ponto usa pesos de sobreposição, mas IC/p acabam calculados para outro estimador. A adaptação precisa recalcular `n_t*n_f/n`, normalizar nos estratos restantes e preservar multiplicidades dos clusters sorteados.

5. **Corrigir a unidade do retorno real.** A fórmula escrita é `pnl_sol / sol_spent_lamports` ([pré-registro:6](C:/dev/project-hunter/.claude/state/r91/prereg_frozen.md:6)); o denominador é efetivamente inteiro em lamports ([meme_live.py:183](C:/dev/project-hunter/packages/core/hunter_core/db/models/meme_live.py:183)). Use `pnl_sol / (sol_spent_lamports / 10^9)`. **Falha:** médias e IC reais ficam um bilhão de vezes menores.

**NICE-TO-HAVE**

- **Não declare P “sempre true nos eventos”.** Há dois `false` em `flow_v2/8` nas propostas cegas ([avail1.txt:33](C:/dev/project-hunter/.claude/state/r91/avail1.txt:33)); o código calcula o delta, não fixa `true` ([fast.py:279](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/fast.py:279)). Declare concentração por pista e publique suporte por pista; diferenças entre pistas podem explicar parte da associação agregada.
- Prefiro IC básico, coerente com o p centrado; percentil mais p centrado são critérios distintos em distribuições assimétricas. Isso, sozinho, não invalida a conjunção pré-registrada.
- Os SQL cegos não aplicam o corte temporal final ([q_avail3.sql:6](C:/dev/project-hunter/.claude/state/r91/q_avail3.sql:6)). Trate as contagens como preliminares. Os números de poder precisam explicitar a hipótese de dependência; contagem de unidades não determina efeito de cluster.
- Ausência de teto **na saída** não prova ausência de marcas anteriores afetadas. A exclusão prévia de Mayhem é apropriada; mantenha essa limitação e não “corrija” retornos retrospectivamente.

**O QUE EU FARIA DIFERENTE**

Nomearia o alvo como **contraste ponderado entre primeiras apostas admitidas, nos estratos com sobreposição**. “Estável” e “estável ou caindo” podem compor esse alvo, mas o resultado agregado não estima especificamente a vantagem de excluir estáveis na `operator/5`.

**CONCORDO COM**

Pesos `n_t*n_f/n` recalculados são coerentes com esse alvo; `max(p_mint,p_dia)` e Holm fixo em `{H,P}` são defensáveis, condicionados à validade dos bootstraps. Não equivalem a uma modelagem conjunta de toda dependência cruzada.

Concordo com a primeira aposta sem substituição posterior, nulo separado de `false`, exclusão da sonda de recusadas, S1 como **cenário — não limite conservador**, nível lucrativo, metades e deixa-um-fora. Concordo sobretudo com **NÃO CONFIRMA ≠ REFUTA e nenhuma mudança na mesa**.

**OBSIDIAN**

- **Fila de Hipoteses — H-034:** acrescentar emenda com regime efetivo, regras operacionais de suporte/inferência e conversão SOL/lamports.
- **Revisoes-Astra/H-034-prereg:** registrar este parecer e as decisões sobre cada achado.
- **Dicionario de Variaveis:** explicitar o suporte por pista e que `progress_rising` não é estruturalmente sempre verdadeiro nos eventos.
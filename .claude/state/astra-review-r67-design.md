**RESUMO**

**NÃO ao desenho como confirmação fora de amostra da regra real. SIM como validação histórica complementar, com correções.** O parâmetro a testar permanece **`buys_1m <= 25`**, sem considerá-lo ótimo. Parecer como `quant-engineer`.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Revisão documental; não executei análise estatística nem consultei a VPS. As contagens fornecidas ainda precisam de auditoria.

**MUST-FIX**

1. **Independência: esta é a maior armadilha.** As 15 operações reais de 16–18/09 **já participaram da descoberta nas 87**; não são holdout. Além disso, a memória registra `operator/6` e `flow_v2/1` propondo **a mesma moeda no mesmo tique**: excluir apenas `proposal_id` deixa possíveis réplicas da descoberta. Para a validação principal, excluir todos os **mints do R65**, auditar duplicatas mint/instante entre versões e evitar ponderá-las repetidamente. Cenário: um movimento aparece em cinco braços e vira cinco “confirmações”. [R65:26](C:/dev/project-hunter/.claude/state/notes-R65.md:26), [Mesa:66](C:/dev/project-hunter/obsidian/03-TRADING/Meme/Mesa-operator-6.md:66).

2. **(a) `hit15`: descritivo, dependente da saída.** É legítimo como “atingiu 1,15× enquanto esta política manteve a posição”; não como probabilidade de atingir o alvo em 300 s. Hold médio não corrige isso, e ajustá-lo condiciona numa variável posterior à entrada. Preferência: retorno líquido primário; secundário, máximo em **300 s fixos desde o fill**, observado inclusive depois da saída, com regra prévia para lacunas. Sem essa cobertura, mantenha `hit15` apenas descritivo. Saída precoce não equivale a censura independente. [Referência metodológica](https://www.bmj.com/content/378/bmj-2022-071349).

3. **(b) Desfecho posterior não é antecipação.** Audite disponibilidade das features e snapshots **até a decisão**, joins retrospectivos e percentis móveis calculados exclusivamente com passado. Já excluir `indeterminate` pode introduzir **seleção**, mesmo sem antecipação: se moedas ruins perdem cobertura mais frequentemente num balde, sua média melhora artificialmente. Reporte exclusões por balde/dia/versão e análise de sensibilidade; se conclusões dependerem dos ausentes, resultado inconclusivo. Esse risco consta do [R66:140](C:/dev/project-hunter/.claude/state/notes-R66.md:140).

4. **Inferência precisa preservar dependência nos dois procedimentos.** Bootstrap por mint não conserta permutação de linhas correlacionadas dentro do dia. Preserve clusters também no teste; não permute rótulos individuais como independentes. Controle versão de entrada, além de dia: saídas iguais não garantem populações iguais. Tercis separados são diagnósticos, não controle conjunto; predefina estratos conjuntos, pesos e suporte mínimo, sem forçar conclusão em células vazias. [Premissas da permutação](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).

**NICE-TO-HAVE**

Curva de limiares e leave-one-day-out como descrição. Retiraria “dois ICs excluem zero” do critério de platô: isso reintroduz significância nos testes declarados exploratórios.

**O QUE EU FARIA DIFERENTE**

- **(c)** Escreveria: “Associação entre fluxo e retorno **sob a saída flow_v2**; transferência para 1,15×/300 s não demonstrada.” A direção pode inverter ao trocar a saída. Para validar o destino real, precisa de replay fiel dessa política ou sombra prospectiva.
- **(d)** `operator/5+/6`: **replicação contemporânea**, após remover sobreposição. Mesmo regime não invalida automaticamente apostas distintas, mas não constitui validação temporal independente. O split 19–20 → 21 também não apaga que 21 participou da descoberta.
- **(e)** Retiraria “3 de 4 fatias independentes”. Congelaria população, ponderação, exclusões, custos e **Δ = média(ret ≤25) − média(ret >25)**. Sucesso histórico: Δ positivo, IC95% inteiramente positivo e p bilateral <0,05 **com inferência válida**, sem reversão material nas sensibilidades predefinidas. Falha: **não confirmado**, sem procurar outro corte.

Para um **SIM ao dinheiro real**, isso ainda não basta: “menos negativo” passa no contraste. Exigiria confirmação prospectiva com a saída real, custos executáveis e retorno absoluto positivo do braço selecionado. Até lá: sombra.

**CONCORDO COM**

Corte 25 congelado, retorno líquido primário, um contraste confirmatório e exploração explicitamente separada.

**OBSIDIAN**

- **Revisões Astra — R67:** registrar dependência entre braços, definição do desfecho e critério de confirmação.
- **KB-0010 — Overfitting de backtest:** acrescentar que propostas distintas podem repetir a mesma informação e que uma subamostra da descoberta não vira holdout.
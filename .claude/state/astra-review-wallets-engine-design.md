**RESUMO**

Como `quant-engineer`: concordo com a direção, mas **1–4 precisam de ajustes** antes de implementar.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; parecer sobre contratos, sem implementação.

**MUST-FIX**

1. **Concordo com caixa + Δliquidação; discordo do fallback assimétrico.** Exemplo: compra por 1; fechamento diário sem estado → marca 0, E = −1. No dia seguinte, abertura sem estado usa custo 1; venda por 0,2 → E = −0,8. Soma diária −1,8, contra −0,8 na janela. **A mesma fronteira precisa ter a mesma avaliação**, independentemente de ser início ou fim. Concordo em excluir o caixa unmatched; numa venda parcialmente casada, exclua somente a parcela unmatched. A fórmula textual precisa de errata ([desenho:42](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:42)).

2. **Discordo da garantia de conservadorismo.** Mesmo admitindo piso no timestamp inicial, extrapolar slots a 0,4 s pode ultrapassar o instante real. Exemplo hipotético: modelo prevê pouso em `t+2`, pouso real ocorre em `t+1,5`, disponibilidade em `t+1,8`: aceita uma compra impossível. Trate como **relógio nominal declarado**, não limite inferior garantido; prefira contexto temporal por slot ([desenho:167](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:167)).

3. **Concordo com impedir saída anterior à disponibilidade; discordo de chamar 9.000 slots de 60 minutos.** A 0,5 s/slot seriam 75 minutos. Timer deve disparar em `instante_entrada + 3.600 s`, mesmo sem novo trade, e depois cumprir o atraso de execução. Seu `max(...)` para evento atrasado é uma extensão que precisa ficar explícita no contrato; repetir com atraso 13 no estresse ([desenho:171](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:171)).

4. **Concordo com zero→zero e neutralidade; discordo das equivalências sem ressalvas.**
   - Compra 100, vende 99 no slot seguinte, guarda 1 por uma hora: duração zero→zero mascara o giro rápido. Não consideraria esse cálculo suficiente para cumprir a exclusão MEV.
   - Para `Σ episódios = E_janela`, some **contribuições recortadas na janela**, incluindo abertos; não resultados integrais apenas dos fechados. Compra anterior por 1, liquidação inicial 2, venda por 2,1: episódio vitalício +1,1, contribuição na janela +0,1.
   
   O contrato exige atividade fechada, exclusão de giro rápido e perdas abertas ([desenho:46](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:46), [desenho:62](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:62), [desenho:75](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:75)).

**NICE-TO-HAVE**

Nenhum adicional; priorizaria os contratos acima.

**O QUE EU FARIA DIFERENTE**

Acrescentaria testes de vazamento:

- **Ligações e metadados futuros:** alterar financiador, criador, vínculo e pool conhecidos depois do corte não muda o retrato anterior.
- **Prefixo causal intradiário:** alterar eventos ainda não recebidos não muda decisões já tomadas, contadores, cooldown ou motivo de saída.
- **Decisão versus fill:** mudar trades posteriores do slot de pouso pode mudar o fill adverso, nunca retroativamente o gatilho ([desenho:179](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:179)).
- **Controle sem seleção por sobrevivência:** apagar o desfecho do controle não pode apagar seu pareamento; apenas muda sua completude/censura ([desenho:203](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:203)).

**CONCORDO COM**

5. **Sim**, FIFO por entidade vigente no corte, preservando origem dos lotes e desempate determinístico intrasslot. Liquide a **quantidade agregada** por mint: somar liquidações individuais das gêmeas subestima impacto. Ligações futuras não reescrevem retratos ([desenho:89](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:89)).

6. **Sim, com ressalva:** `horizon_slot` é necessário, mas sozinho não prova completude. Um evento admissível no slot S não garante que todos os eventos usados no pior preço de S chegaram antes do corte. Preserve incompletas para continuação e contagem; não descarte definitivamente o braço follow ([desenho:53](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:53), [KB-0148:46](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0148-a-graduacao-nao-e-a-saida-barata.md:46)).

7. **Sim:** PnL imputado = `−0,5 × ficha`, sem descontar custos novamente. **Não é limite inferior garantido**: perda integral corresponde a R = −2. É imputação pré-registrada ([PREREG:40](/C:/dev/project-hunter/.claude/state/carteiras-lucro/PREREG.md:40), [desenho:187](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:187)).

8. **Sim, para pareamento retrospectivo cego ao desfecho.** Bordas do dia inteiro não podem alimentar decisões intradiárias. Inclua candidatos incompletos/censurados; selecionar só trajetórias completas introduziria sobrevivência ([desenho:201](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:201)).

**OBSIDIAN**

- **carteiras-lucro-design** — registrar correções de contabilidade, relógio, episódios e testes causais.
- **KB-0182 — Quem ganha dinheiro de verdade nos memes** — esclarecer E-PnL e distinguir imputação R = −1 de limite inferior.
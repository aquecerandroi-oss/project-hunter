**RESUMO**

Como `quant-engineer`: **o desenho precisa de ajustes antes dos desfechos**, sobretudo na população primária, nas sombras de papel e no incremento atribuído ao cooldown.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão conceitual do protocolo, sem calcular resultados.

**MUST-FIX**

1. **Operacionalização — parcialmente fiel.** Uma recompra por saída, separação real/papel e exclusão de posições concorrentes fazem sentido. Porém, “existe uma posição anterior lucrativa” permite saltar uma saída intermediária perdedora. **Cenário:** ganho em t=0, perda em t=100, entrada em t=150: ela aparece como recompra após ganho. Fixar a saída imediatamente anterior no escopo e uma regra determinística quando vários `p` apontarem para o mesmo `q`, antes de testar lucro. [Desenho:17](C:/dev/project-hunter/.claude/state/notes-R78.md:17).

2. **Papel cruzado — restringir por decisão de origem.** `rs_p ≠ rs_q` não demonstra uma nova decisão. **Cenário:** sombra imediata sai com ganho em t=10; `recuo_v1` da mesma decisão entra em t=20: vira “recompra” sem ninguém ter decidido recomprar. Excluir pares da mesma decisão de origem, inclusive entre propostas distintas; sem identificação confiável, manter cruzado/qualquer agregado apenas exploratório e analisar por braço. Bootstrap por mint não corrige essa classificação. [Desenho:16](C:/dev/project-hunter/.claude/state/notes-R78.md:16); [H-017:200](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:200>).

3. **Primária — a leitura literal é alvo E lucro.** A variável exige lucro; a população exige saída por alvo. Logo, usar `exit_reason = target AND pnl > 0` na saída antecedente; qualquer saída lucrativa fica como sensibilidade. **Cenário:** incluir muitas saídas lucrativas por trailing pode produzir um veredito que não vale para a população congelada. A inversão proposta na R78 não é fiel. [H-018:210](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:210>); [Desenho:20](C:/dev/project-hunter/.claude/state/notes-R78.md:20).

4. **Cooldown — corrigir a atribuição incremental.** Ignorar saídas de posições bloqueadas está correto. Porém, “bloqueadas cuja saída anterior foi ganho” não mede necessariamente o incremento sobre o check 28. Comparar **dois replays sequenciais**, perda apenas versus qualquer saída, com estados próprios. **Cenário:** ganho em t=0; B entra em t=10 e perde ao sair em t=100; C chega em t=350. A política nova bloqueia B e permite C; a antiga permite B e bloqueia C. O incremento envolve ambos. Incluir também saídas zeradas. [Desenho:23](C:/dev/project-hunter/.claude/state/notes-R78.md:23).

**NICE-TO-HAVE**

- **Controle:** nem toda primeira entrada de mint recomprado foi vencedora; algumas foram. Isso não invalida automaticamente o contraste descritivo com **todas** as primeiras entradas. Excluir mints posteriormente recomprados também seleciona pelo futuro: a sensibilidade **não basta para interpretação causal**. Manter o controle congelado, mostrar a sensibilidade e comparar por braço/período. [Desenho:19](C:/dev/project-hunter/.claude/state/notes-R78.md:19).
- Explicitar a diferença na fronteira: recompra inclui exatamente 300 s; cooldown libera nesse instante. [Desenho:17](C:/dev/project-hunter/.claude/state/notes-R78.md:17).

**O QUE EU FARIA DIFERENTE**

Separaria o contraste descritivo da H-018 da avaliação da política. `−Σ PnL bloqueadas` é economia retrospectiva sobre entradas observadas, condicionada a manter os demais negócios iguais; não estima oportunidades novas abertas pela política.

**CONCORDO COM**

Real e papel separados; bootstrap conjunto por mint; concorrentes fora das recompras; interrupção por amostra insuficiente; posições bloqueadas não gerarem novos cooldowns.

**OBSIDIAN**

- **Fila de Hipoteses** — acrescentar esclarecimento da população e das regras de pareamento, preservando o bloco original.
- **Revisoes-Astra/Index** — registrar esta revisão da R78 e distinguir contraste descritivo de efeito da política.
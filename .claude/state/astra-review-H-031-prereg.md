**RESUMO**

**Eu revisaria o pré-registro antes de abrir os desfechos.** B é admissível como extensão explicitamente pré-registrada, mas não equivale à medida A. Recomendo D ajustado por conjunto como decisório e correções na inferência, censura e agregação dos rótulos.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão em modo OPINIÃO, papel `quant-engineer`.

**TESTES**

Não executados; revisão documental e estática. Li as contagens cegas, sem abrir desfechos individuais da H-031.

**MUST-FIX**

1. **(1) Tornar o D ajustado por conjunto decisório.** A permutação estratificada preserva a composição por conjunto sob o nulo, mas não transforma o D agrupado em efeito dentro dos conjuntos: o moinho continua calculando diferenças de médias agrupadas ([protocol.py:178](C:/dev/project-hunter/infra/research/protocol.py:178)). **Falha concreta:** um efeito pequeno dentro dos conjuntos passa o teste estatístico, enquanto a composição entre conjuntos infla D acima de +0,05. Use  
   `D_adj = Σ w_s × (média_baixa,s − média_alta,s)`,  
   com pesos congelados sem desfechos e suporte nos dois braços. ICs, permutação, metades temporais e planalto devem estimar esse mesmo contraste. Conjunto sem contraparte não fornece D; pré-registre seu tratamento.

2. **(2) Cluster de mint está correto para o bootstrap, mas falta na permutação.** O moinho embaralha rótulos **linha a linha** dentro do conjunto ([resampling.py:164](C:/dev/project-hunter/infra/research/resampling.py:164)); ele próprio reconhece o problema ([verdict.py:158](C:/dev/project-hunter/infra/research/verdict.py:158)). **Falha:** a mesma moeda aparece em cinco conjuntos e fornece cinco evidências dependentes ao p. Pré-registre inferência que preserve a dependência por mint; Holm não corrige p inválido. A unidade `(conjunto, mint)` é válida para estudar decisões desses conjuntos, não moedas igualmente ponderadas.

3. **(3) `ledger.wallets ≥ 10` não é a guarda da E2-b.** O campo conta todas as carteiras do ledger, e vendas também criam entradas ([decision_tape.py:261](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape.py:261), [event_wallets.py:196](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_wallets.py:196)). **Falha:** duas compradoras e oito carteiras que apenas venderam satisfazem a guarda. Pode permanecer como proxy de **participantes**, declaradamente imperfeito; não como prova de dez compradores. Não reconstrua compradores desde o nascimento usando apenas a fatia recente da fita.

4. **(5) A censura precisa limitar a conclusão.** Excluir `indeterminate` pode retirar justamente golpes sem foto; o viés pode ocorrer em qualquer direção. **Não transformaria automaticamente ausência em −1 no primário:** isso mistura perda econômica com falha de observação. **Falha:** a concentração alta causa desaparecimento da fita, suas maiores perdas saem e a hipótese acaba refutada entre sobreviventes. Congele primeiro a unidade e a variável, depois classifique disponibilidade do desfecho; não substitua a primeira proposta indeterminada por outra posterior medida. Pré-registre sensibilidade decisória à censura, com hipóteses explícitas. Atribuir −1 aos dois braços é um cenário, não um limite conservador para D. Hoje essa análise é apenas descritiva ([pré-registro:6](C:/dev/project-hunter/.claude/state/r88/prereg_frozen.md:6), [pré-registro:7](C:/dev/project-hunter/.claude/state/r88/prereg_frozen.md:7)).

5. **(6) Corrigir o rótulo da família.** “Todas as medidas fora do limite refutarem” permite **A sem dados + B refutada ⇒ H-031 refutada** ([pré-registro:8](C:/dev/project-hunter/.claude/state/r88/prereg_frozen.md:8)). Isso transforma ignorância sobre A em refutação da família. Exija **A e B refutadas**; demais combinações sem confirmação dão **NÃO CONFIRMA**, com motivo “limite de dado” quando aplicável. Preserve os três rótulos de [RESEARCH.md:61](C:/dev/project-hunter/docs/RESEARCH.md:61). Acrescente ICs finitos, suporte temporal por braço e regra para réplicas inválidas antes de qualquer REFUTA; mantenha família Holm `{A,B}`, com política explícita para p indisponível.

**NICE-TO-HAVE**

- **(1) Corrigir a genealogia de B.** É extensão legítima antes dos desfechos, não bifurcação oportunista; porém KB-0153 pediu especificamente **estoque de tokens**, não novo fluxo de SOL ([KB-0153:72](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0153-o-maior-comprador-nao-estava-no-arquivo.md:72)). Declare B como nova operacionalização em população posterior, sem apresentá-la como cumprimento literal daquela recomendação.
- **(4) Manter 0,35 em B e quantil 2/3 em A é aceitável**, congelados cegamente. O 0,35 é uma escolha transportada entre fórmulas diferentes, não limiar validado para B. Com `low`, igualdade fica selecionada; a E2-b recusa igualdade ([pedigree_e2b.py:156](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/pedigree_e2b.py:156)). Declare essa diferença.
- A grade B pode permanecer, mas conte suporte **por limiar, conjunto, mint e dia** antes dos desfechos. Pouca cauda não invalida automaticamente; menos de quatro partições sustentáveis torna o planalto não avaliável. Quantis diferentes também podem gerar a mesma partição. Não interprete impossibilidade mecânica como pico demonstrado.
- `creator_dump` é uma saída dependente da política do conjunto, não diagnóstico universal de golpe; sua execução depende de `exit_on_creator_dump` ([lab_bets.py:213](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:213)).

**O QUE EU FARIA DIFERENTE**

Manteria A/B com conclusões separadas e Holm conjunto, D ajustado como primário e D agrupado descritivo. Escreveria uma emenda datada antes dos desfechos, preservando a cópia congelada anterior.

**CONCORDO COM**

- **(7) B está capturada antes do `await`**, com recusa de estado posterior ao instante ([event_gate_eval.py:253](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:253), [decision_tape.py:288](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape.py:288)). É evidência disponível, não variável utilizada pelo portão.
- **A persistida é o valor efetivamente passado ao portão**, reaproveitado em `reasons` ([proposals.py:253](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:253), [proposals.py:283](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:283)). O atraso não cria look-ahead ao reutilizar esse valor. **Ressalva:** isso prova disponibilidade na avaliação efetiva, não necessariamente no `features_end_time` anterior; `block_time <= as_of` sozinho não prova chegada até `as_of`. Não recalcule A hoje.
- **(8) Manteria `require_positive_level`** para CONFIRMA operacional, conforme [RESEARCH.md:65](C:/dev/project-hunter/docs/RESEARCH.md:65). Não há evidência cega para dizer “quase impossível”. Uma redução relevante de perdas pode existir sem lucro; nesse caso, reporte o efeito e NÃO CONFIRMA operacional — nunca “não avisa golpe”.
- A cláusula individual `max(IC_superior_cluster, IC_superior_dia) < MRE` respeita a errata, desde que a inferência seja válida.

**OBSIDIAN**

- **Fila de Hipóteses — H-031:** emenda pré-desfecho com contraste ajustado, inferência por mint, censura e rótulos corrigidos.
- **Revisões-Astra — R88/H-031:** registrar este parecer e as decisões aceitas ou rejeitadas.
- **KB-0153 — O maior comprador não estava no arquivo:** distinguir reabertura por fluxo líquido da recomendação original sobre estoque.
- **EXP-M9 — pedigree E2-b:** acrescentar ligação à H-031, explicitando truncamento de A e ausência de equivalência com B.
**RESUMO**

O reuso é honesto, mas há ajustes necessários antes de implementar. O principal: **`EXIT-CHAN` deve acrescentar o canal à invalidação original**, conforme a hipótese registrada. Para a inferência, escolho **(c), mantendo os blocos diários de (a)**: resultados descritivos e todos inconclusivos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão no papel de `quant-engineer`, modo OPINIÃO.

**TESTES**

Não executei testes nem consultei o banco. Os números atuais são os informados por você; examinei código, brief, memória e histórico do commit `d878fd6`.

**MUST-FIX**

1. **(1) Separar reconstrução do plano de reinicialização do replay.**

   `OpenTracking.progress` desserializa o progresso já gravado, inclusive terminal ([tracking_repo.py:90](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:90)). `walk()` retorna imediatamente quando esse progresso está encerrado ([walker.py:170](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:170)).

   **Cenário:** carregar um outcome terminal, trocar o alvo e chamar `walk()` devolve a saída antiga sem avaliar nenhuma vela. A reprodução pode parecer perfeita por construção.

   Reutilize `OpenTracking.plan`, mas refaça o caminho a partir de `Progress.start()` para os entrados. O progresso persistido é referência para comparação, não estado inicial. `no_entry:late` exige evidência operacional do envelope; herdá-lo nos braços é correto, mas copiar o resultado não constitui reprodução independente.

2. **(1) Preservar a invalidação original em `EXIT-CHAN`.**

   A hipótese declara **stop, invalidação e horizonte inalterados** entre BASE, NOTGT e CHAN ([KB-0045:73](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao.md:73)).

   **Cenário:** um fechamento rompe `L`, mas permanece acima do mínimo dos dez fechamentos. NOTGT sai; CHAN com `invalidation_level=None` e observador exclusivamente de canal permanece aberto. O contraste passa a medir também a retirada da invalidação.

   Minha recomendação: **mantenha a invalidação nativa no plano de CHAN** e acrescente o observador de canal. Só INV-C precisa desligar a observação nativa para substituí-la.

   O observador externo é equivalente à regra interna se:

   - Rodar **depois** de `walk(plan, progress, [bar])`, somente quando aquela barra foi efetivamente consumida e o estado continua ativo.
   - Nunca limpar um `pending_invalidation` já verdadeiro.
   - INV-C contar dois fechamentos distintos, consecutivos e alinhados ao timeframe congelado; fechamento `>= L` reinicia a contagem.
   - CHAN usar os dez fechamentos de 15m **anteriores**, excluindo o atual, com histórico suficiente anterior à entrada e sem atravessar lacunas.

   Isso reproduz a posição da observação nativa, depois dos toques intrabar ([walker.py:145](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:145)). **Cenário adicional:** contar duas entregas do mesmo fechamento dispara INV-C prematuramente, embora o walker ignore a segunda entrega ([walker.py:173](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:173)).

   Atenção à prioridade: stop>alvo>horizonte>invalidação vale **na abertura**. Uma invalidação pendente paga nessa abertura antes de um stop que só seria tocado depois, intrabar ([walker.py:62](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:62)).

3. **(3) Pareamento precisa também de corte de maturidade e cobertura contrafactual.**

   Herdar admissão e não operar slots é necessário, mas não basta. Congele `signal_id`, versão, entrada, horário, stop inicial, custos, horizonte e `as_of`. Para os contrastes principais, use horizonte já maturado no corte; mantenha os demais na tabela de cobertura.

   **Cenário:** a base bate alvo às 19:50, mas NOTGT ficaria aberto até 23:40. Às 20:00, selecionar apenas os braços já encerrados exclui justamente os contrafactuais demorados. Usar velas posteriores às 20:00 quebra o corte.

   Carregue até o horizonte de cada entrada, não até a saída da base. Inclua a vela que **abre no horizonte**: `load_candles.end` é exclusivo ([repo.py:81](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:81)); o acompanhamento atual acrescenta um minuto ao limite inclusivo ([outcomes.py:82](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:82)). Lacuna posterior à saída da base pode tornar somente o braço contrafactual indisponível: conte isso separadamente de funding nulo.

   Congele também os UUIDs das quatro versões, sem depender de `status=active`. A memória registra supersessão local v1→v2 e preservação das populações anteriores ([Experiments Index.md:120](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments%20Index.md:120)); sua descrição de quatro ativas precisa ser identificada no manifesto, não resolvida por suposição.

4. **(4–5) Contar dias de entradas pareadas e não chamar enumeração exata de validade exata.**

   **Cinco dias de candles não significam cinco blocos de outcomes.** Conte `B` nos dias UTC com pares elegíveis em cada contraste. Histórico de aquecimento não cria replicação experimental.

   **Cenário:** todas as entradas ocorreram em 6 de setembro, mas o relatório anuncia cinco blocos porque há candles desde o dia 1. Na realidade, `B=1`: o bootstrap diário é degenerado e não estima incerteza entre dias.

   Outro requisito: sign-flip precisa de invariância da distribuição conjunta sob as inversões permitidas — simetria dos efeitos de bloco e condições apropriadas entre blocos. Média zero, sozinha, não basta. Políticas determinísticas não foram aleatorizadas. Enumerar todas as combinações remove erro Monte Carlo; não demonstra essas hipóteses. [Winkler et al., 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC4010955/).

   **Cenário:** um mesmo choque de BTC afeta entradas dos dois lados da meia-noite. Inverter esses dias independentemente não preserva a dependência real. Blocos de quatro horas multiplicariam esse problema.

   Portanto: **(c), com blocos de um dia**, p e IC exploratórios, hipótese estatística explícita e gate editorial obrigatório. O contrato exige ≥100 outcomes avaliáveis **e** ≥30 dias; falhar em qualquer condição mantém “inconclusivo” ([SHADOW-LAB.md:19](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19)). Se `B=1`, prefiro IC indisponível com motivo a apresentar `[efeito, efeito]` como precisão.

   Sobre Holm: nenhuma objeção à dependência entre os sete contrastes; Holm admite dependência arbitrária **entre p-valores válidos**. Não corrige p-valores mal calibrados. [Documentação oficial do R](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html).

   E a limitação é mais forte que “quase não sobrevive”: com `B=6`, teste bicaudal por `|T|` e enumeração completa,

   `p mínimo = 2/64 = 0,03125 > 0,05/7 ≈ 0,007143`.

   **Nenhuma rejeição por Holm é possível.** O menor p ajustado possível é 0,21875; empates podem elevá-lo.

5. **(7) “Anterior ao commit” não explica uma divergência.**

   **Cenário:** um bug no replay desloca `exit_ts`; isso muda o funding incidente. Classificar tudo como “correção posterior” mascara o bug.

   Separe duas verificações:

   - **Trajetória:** estado, resultado, entrada, `entry_ts`, saída, `exit_ts`, abertura versus intrabar e `r_ex_funding`.
   - **Liquidação:** funding, `r_net_reason` e `r_multiple`.

   A correção de funding não justifica mudança no preço nem em `r_ex_funding`: esse último é calculado explicitamente com funding zero ([settle.py:82](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:82)).

   Só aceite “divergência explicada por código” quando a mesma trajetória e o mesmo histórico de funding produzirem a diferença demonstrável entre o resolvedor antigo e o atual. Se o histórico mudou por backfill, registre **mudança de dados**, separadamente. Sem insumos históricos suficientes, marque “não comprovada”.

   Não espero divergências automaticamente no banco local: o registro da correção informa zero candidatos locais ao recompute de nulos; o censo problemático era da VPS ([notes-S2.md:498](/C:/dev/project-hunter/.claude/state/notes-S2.md:498)). Isso não prova igualdade dos valores não nulos, mas impede transportar aquela expectativa para cá sem evidência.

   Nos sete contrastes, use **base recalculada e braços com o mesmo código atual**. A base histórica serve à auditoria de reprodução.

**NICE-TO-HAVE**

- **(2) Sentinela:** aceitável neste replay restrito, desde que seja uma constante declarada por regra e haja uma verificação obrigatória de que nenhuma vela relevante nem entrada alcança o limite. Se alcançar, interrompa; não produza um falso “sem alvo”. Não escolha o limite a partir da máxima futura.

  `excursions` usa `target1` quando o resultado é TARGET ([excursions.py:123](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:123)). Portanto, sem toque no sentinela, ele não altera diretamente MFE/MAE; `settle` usa entrada, saída e stop para R ([settle.py:82](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:82)). A solução permanente seria alvo opcional explícito, mas altera arquivos fora do brief.

- **(6) Nulos:** concordo com excluir o par, nunca substituir por zero. Mostre exclusões “só A”, “só B”, “ambos” e motivo. Faça `r_ex_funding` tanto nos mesmos pares do contraste líquido quanto na população ampliada disponível: isso separa efeito de funding de mudança de composição. A ausência pode depender da duração do braço; pareamento não elimina esse viés.

- Registre o gatilho externo separadamente do resultado canônico `INVALIDATED`: original, canal ou ambos. Isso explica o mecanismo sem alterar a prioridade do walker.

- Fixe snapshot de leitura, hashes dos insumos/código, ordenação e serialização. Semente fixa não torna leituras de um banco avançando durante a execução reproduzíveis.

**O QUE EU FARIA DIFERENTE**

Definiria o protocolo antes do primeiro resultado: manifesto de sinais/versões; auditoria da base desde o início; população com horizonte maturado; oito braços sobre essas entradas; cobertura por braço; sete contrastes exploratórios.

Para preservar a **média por sinal**, guardaria por dia `S_b = soma dos deltas` e `n_b = número de pares`:

- Estimativa: `ΣS_b / Σn_b`.
- Bootstrap: sortear dias inteiros e recalcular essa razão com suas multiplicidades.
- Sign-flip: `T(s) = Σ(s_b·S_b) / Σn_b`, contando `|T(s)| >= |T observado|`.

Não usaria média simples das médias diárias: ela muda o estimando quando os dias têm tamanhos diferentes. Manteria a família de sete mesmo com `--policies`; um subconjunto executado não deve reduzir silenciosamente a penalização.

**CONCORDO COM**

Reutilizar walker/settle; alterar apenas níveis nos braços que cabem no plano; congelar admissão pela base; não rearmar slots; excluir pares com funding desconhecido; declarar sensibilidade sem funding; manter Holm e não combinar vencedores. A conclusão é sobre **saídas condicionadas às entradas da base**, sem inferir desempenho de uma estratégia independente ou de carteira.

**OBSIDIAN**

- **EXP-0004 — Políticas de saída:** criar com manifesto, maturidade, cobertura contrafactual, estatística exploratória e auditoria separada de trajetória/funding.
- **Strategy Backlog:** explicitar que CHAN acrescenta canal preservando a invalidação original.
- **Registro de Tentativas:** registrar os sete contrastes, o estimando por sinal e a família fixa sob execução parcial.
- **O walk-forward que não temos e o nulo que nunca calculamos:** distinguir enumeração exata de sign-flip das hipóteses que validam o teste.
- **Revisões da Astra — R1:** registrar esta revisão de desenho e a resolução dos cinco must-fix.
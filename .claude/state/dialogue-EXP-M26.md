# Diálogo Claude ⇄ Astra — EXP-M26

Regras: rodadas numeradas; cada uma responde à anterior ponto a ponto; discordância vem com cenário de falha ou comando que decide; a rodada final começa com "DECISÃO CONJUNTA" e é copiada para o plano/ADR pelo Claude.

## Claude (rodada 1)
Revise o desenho docs/design/exp-m26-grafico-moedas-maduras.md (EXP-M26: estratégia de gráfico em moedas maduras 15-120 min na curva; H-022 pré-registrada na §3, NÃO está na fila). Contexto que li: obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md, .claude/state/notes-R81.md, KB-0149 §7, KB-0148, KB-0147, obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md; código: packages/indicators/hunter_indicators/meme/lines.py, rules_criteria.py (line_refusals l.166, age_refusals), rules.py (evaluate_entry l.296), services/meme-worker/hunter_meme_worker/{tracker.py (prune), fast_lane.py (young_mints, pinned_max_age), lab_repo.py (_GATE_ROWS l.64), proposals.py (_progress_pct l.116: progresso é fração ×100), lab_models.py (CLOCKS), warmup.py}. Números medidos na VPS por SELECT (só contagens, nenhum desfecho) estão nas tabelas da §1. Regras duras: sem antecipação, Decimal em dinheiro, UTC, nada de dado falso, nenhum limiar escolhido olhando desfecho, papel só (research_only). Perguntas precisas: (1) O funil de EXP-M2 (§1.4) sustenta a conclusão 'morreu por janela + criador cego + participação, nunca julgou a linha'? (2) A instrumentação I1 (reter top-K=60 por mcap_sol entre 5-120 min, não terminadas) é a menor que resolve? Ranking por mcap é aceitável ou você prefere outro critério causal e simples? Há risco de antecipação ou de degradar as pistas jovens? (3) Os três braços (L linha+saída atual, C controle sem linha+saída atual, H linha+saída EXP-M2 2x/30%/900s) e a porta comum (idade 900-7200 s, progresso 5-90%, participação 1%, require_creator_not_net_seller=false, pedigree true, tetos de pesquisa) — algo a mudar? O contraste L−C com tempos de entrada diferentes é defensável como primária, ou a primária deveria ser dentro de C (linha_ok no mesmo minuto)? (4) A H-022 (§3): previsão/refutação/MRE +0,03/leitura única 250 ou dia 21, mínimo 150, censura 20%, Holm de 2 — está bem formada e falsificável? A suposição DP 0,18 e a potência estão honestas? (5) Custo (§5) e riscos (§6): falta algum modo de falha (sobrevivência, antecipação, migração durante a posse, a saída line_break passando a disparar)? Para cada must-fix dê cenário de falha concreto. Responda em português.

## Astra (rodada 1)

### RESUMO

**REVISE — ainda não há convergência para DECISÃO CONJUNTA.** Assumi o papel de `quant-engineer`. Concordo com investigar uma população madura prospectiva, em `research_only`, mantendo os limiares herdados. Não aprovo ainda o seed: a definição do contraste, a independência da observação e a execução das saídas precisam ser fechadas.

A base sustenta a pergunta, não uma vantagem: KB-0161 documenta o limite estrutural da H-021 e os zero resultados de EXP-M2 (`obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:35`, `:52`); KB-0149 §7 deixa o horizonte maior aberto; a regra 1 da Fila permite revisitar idade/progresso com população nova (`obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:18`). O protocolo antigo continua congelado (`obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md:69`).

### ARQUIVOS

Única alteração desta rodada: append desta seção em `.claude/state/dialogue-EXP-M26.md`. Desenho, código, configuração e Obsidian permanecem sem edição por mim.

### TESTES

Revisão estática com `Get-Content -Encoding UTF8` e `rg -n`. Não executei pytest, lint, migrações, consultas na VPS ou leitura de desfechos. As contagens da §1 são evidência apresentada pelo Claude, não medições reproduzidas nesta rodada. Os nomes `q2.sql`…`q9.sql` não identificam seu diretório no desenho; preciso da referência durável ao SQL e à saída para auditá-las.

Recalculei em JavaScript, em memória, a aproximação normal declarada (DP 0,18, braços independentes, teste bilateral; números não são potência medida do experimento):

```text
n por braço   EP(D)       poder D=0,05 α=0,05   poder D=0,05 α=0,025
250           0,016100    0,8740                0,8063
150           0,020785    0,6721                0,5652
n=250, D=0,03: poder α=0,05 = 0,4615; α=0,025 = 0,3527
```

### MUST-FIX — respostas às cinco perguntas

#### 1. O funil de EXP-M2 sustenta a conclusão?

**Sustenta “a linha não foi julgada por desfechos”; não sustenta ainda a atribuição causal completa nem sua ordem.** A tabela contém 287 minutos que passaram a linha, 275 com criador desconhecido, 8 conhecidos não vendedores e 1 após participação (`docs/design/exp-m26-grafico-moedas-maduras.md:87`). Portanto:

- O bloqueio por criador desconhecido é fortemente documentado nesse subconjunto.
- Participação elimina 7 dos 8 restantes.
- “Janela errada” é hipótese plausível de escassez, não causa isolada demonstrada: os filtros são correlacionados e a decomposição depende da ordem escolhida.
- Ainda falta explicar o candidato final contra **zero propostas**. O gate efetivo inclui conclusão/migração, Mayhem e outros critérios (`packages/indicators/hunter_indicators/meme/rules.py:295`); a camada de propostas inclui pedigree, identidade/evento e snapshot para cotação (`services/meme-worker/hunter_meme_worker/proposals.py:239`, `:244`, `:256`, `:270`).

**Cenário de falha:** corrigimos criador/idade e semeamos o EXP-M26, mas todos os candidatos continuam recusados por outro insumo ausente. Exijo funil até proposta e fill, com parâmetros vigentes na época, disponibilidade das features no instante, todos os motivos de recusa e explicação do sobrevivente. Tetos de fill explicariam zero apostas, não zero propostas. Também corrigiria “flat = morta”: série monótona viva igualmente fica sem dois mínimos locais (`packages/indicators/hunter_indicators/meme/lines.py:233`, `:299`).

#### 2. I1 é mínima? Ranking por mcap, antecipação e pistas jovens

**Aceito top-K por mcap conhecido como seleção causal simples para o piloto cego. K=60 é orçamento, não número validado.** Não trocaria agora por um score de atividade novo. A população deve chamar-se “mints descobertos e retidos por esta política”, não “todas as moedas maduras”: uma moeda já removida não volta só porque seu mcap subiu fora do rastreador.

Há três correções obrigatórias.

**2a — Orçamento e isolamento.** O desenho subtrai retidas do teto das restantes (`:140`), como o código já faz com fixadas (`services/meme-worker/hunter_meme_worker/tracker.py:243`). Em saturação, 60 retidas tiram 60 vagas das demais; isso não é simplesmente acrescentar 60 moedas. Além disso, apostas abertas são priorizadas no REST (`tracker.py:280`) e I2 gera fotos e features a 15 s (`fast_lane.py:226`, `:242`, `:261`). Logo “REST: 0” e o orçamento de uma foto/minuto não descrevem o experimento completo.

**Cenário:** H mantém posições por mais tempo, aumenta pins, ocupa capacidade e reduz a cobertura de descoberta/mesa. A fração de nulos entre linhas existentes pode ficar estável enquanto moedas excluídas deixam de produzir linhas. Medir também descobertas → rastreadas → avaliadas por idade, latência/ciclo/RPC/REST, filas e pins distintos; orçar I1 e I2 separadamente. Preservar um orçamento explícito para jovens. K=0 não desfaz pins e carga das apostas já abertas.

**2b — Os braços alteram o próprio instrumento.** Pins incluem apostas de qualquer conjunto, salvo exceções específicas já existentes (`tracker_pins.py:52`); pins prolongam a retenção e habilitam a série rápida (`tracker.py:237`, `fast_lane.py:124`). As linhas usam todas as fotos utilizáveis, não uma grade fixa de uma foto/minuto (`packages/indicators/hunter_indicators/meme/lines.py:195`, `:272`).

**Cenário:** C compra aos 15 min, mantém uma moeda que sairia do top-K e acrescenta fotos a 15 s; L encontra uma estrutura aos 18 min que dependeria da existência de C. H prolonga a observação depois de L sair. Isso afeta a validade interna, não só a externa.

Fechar uma política de elegibilidade e amostragem da linha independente de qual braço abriu/fechou aposta; separar as fotos de acompanhamento de posição das usadas na seleção/linha de entrada, ou assumir expressamente que se estuda o sistema conjunto L+C+H, sem alegar resultado da política L isolada. Para H-022 como proposta, recomendo a primeira opção. A base já documenta preocupação semelhante com influência na mesa nas exceções de `tracker_pins.py:18`.

**2c — Causalidade, frescor e restart.** `mcap_sol` no rastreador não carrega seu próprio `received_at`; `last_polled_at` pode avançar preservando o mcap anterior (`tracker_types.py:30`, `:35`; `tracker.py:206`). Não basta testar um parâmetro “foto futura” que o objeto real não representa. Definir fonte, instante de disponibilidade, limite de validade, desempate e comportamento de mcap ausente. Warmup deve reproduzir a mesma elegibilidade temporal e não escolher preços antigos de moedas que já não eram observadas. Recarregar mints não repõe fotos perdidas durante a parada (`warmup.py:33`): a cobertura anterior à entrada precisa ser verificável, com recusa por lacuna; cinco fotos não certificam 15 minutos contínuos (`lines.py:68`, `:281`).

#### 3. Braços, porta comum e primária

**Manteria L/C/H e os parâmetros como candidatos, com duas mudanças de interpretação.**

A participação de 1% com ticket 0,07 exige **7 SOL/min**, não os 5 SOL/min do funil antigo: a fórmula é `100 * size / volume` (`packages/indicators/hunter_indicators/meme/rules_criteria.py:90`). O piloto deve medir esse funil completo, incluindo pedigree e Mayhem, sem ajustar limiares para fabricar amostra.

**Recomendo primária dentro de C:** na primeira decisão elegível por mint, comparar retorno sob a mesma saída entre `linha_ok=true` e `linha_ok=false`, com a variável observada naquele instante. Linha desconhecida fica separada, não vira false. Isso testa associação preditiva da estrutura no primeiro instante elegível; não prova causalidade nem mede toda a política de esperar até 120 min. Planalto e identidade por `mcap_slope_15m` passam a usar essa mesma população e esse mesmo contraste.

A diferença de médias por aposta L−C pode continuar **descritiva**, mas não é o valor da política em uma população comum: L só entra nas moedas que sobrevivem até satisfazer sua porta; C inclui outras moedas e outros instantes. Se quisermos tornar a política de espera primária, precisamos fixar a coorte na elegibilidade comum e acompanhar as duas políticas para cada mint, incluindo **não operar por regra** como caixa sem PnL; falta de foto é censura, nunca caixa. A MRE teria então unidade por oportunidade, diferente do desenho atual (`docs/design/exp-m26-grafico-moedas-maduras.md:212`).

**Cenário:** L não compra nenhuma das moedas que morrem antes da estrutura. Comparar apenas suas apostas resolvidas com todas as de C produz “vantagem da linha” sem medir o custo/benefício da espera na mesma coorte.

**H−L testa um pacote de saída**, pois muda alvo, trailing e prazo simultaneamente (`docs/design/exp-m26-grafico-moedas-maduras.md:193`); não isola horizonte. Aceito o pacote herdado. Pareamento exige chave de primeira oportunidade, mesma decisão e mesmo fill, não apenas mint. Reentradas e limites de capacidade/perda podem desalinhar os braços: o bloqueio atual consulta apenas propostas/posições abertas (`lab_repo.py:98`), e os tetos continuam recusando fills (`paper_fill.py:109`). “Primeira decisão” deve ser selecionada **antes** de filtrar measured; se ela falhar, não substituí-la pela primeira aposta bem-sucedida. Congelar denominadores de pares ausentes e excluir reentradas do consumo da amostra primária.

**Evidência em C:** o bloco `line` não é persistido em `reasons` quando o gate não exige linha (`proposals_reasons.py:67`), e `_GATE_ROWS` não seleciona `mcap_slope_15m` (`lab_repo.py:64`). Antes do seed, especificar a fonte imutável e versionada desses valores em C, incluindo disponibilidade em T, ausências e retenção até a leitura final.

#### 4. H-022, MRE, parada, censura, Holm e potência

**É falsificável em intenção, mas não está fechada o bastante para congelar.**

- **MRE +0,03:** aceitável como efeito de interesse declarado, não como efeito esperado ou derivado das taxas. Depois da escolha da primária, congelar a unidade e os grupos corretos. Com primária dentro de C, “150 resolvidas em L” não garante sequer um grupo C/`linha_ok` utilizável.
- **Família:** escrever os dois contrastes exatos e aplicar Holm aos dois p-valores; citar Holm e depois exigir apenas p bruto <0,05 não basta (`docs/design/exp-m26-grafico-moedas-maduras.md:212`, `:214`). Recomendo {contraste de linha dentro de C, pacote H−L}; L−C descritivo. ICs marginais de 95% devem ser identificados como marginais.
- **Dependência:** reamostrar o mint com todos os seus braços juntos; preservar os pares H/L. Permutar rótulos L/C como linhas independentes dentro do dia não respeita sobreposição nem decisões determinísticas. Para a primária em C, justificar a permutabilidade condicional e chamar o resultado de associação. Congelar estratos de idade/progresso e análise por blocos temporais; sete dias no calendário não são sete dias com informação nos dois grupos.
- **Parada:** declarar “primeiro corte elegível após sete dias completos, no máximo dia 21”, quem entra quando se atinge o número e quanto tempo se aguarda para maturação. Preferir contar primeiras oportunidades inscritas, não apenas resolvidas; congelar o corte de entrada e aguardar a janela máxima de acompanhamento/execução. **Cenário:** parar em 250 resolvidas de L deixa H ainda aberto e remove justamente seus trades longos.
- **Censura:** denominador nasce nas primeiras oportunidades/propostas, antes de measured; informar no-fill, indeterminate, abertos, ausência de variável e de par. Instrumento insuficiente e amostra insuficiente precedem CONFIRMA/REFUTA. O teto de 20% é necessário, mas não prova ausência de viés: perdas concentradas nos 19% censurados podem inverter +0,03. Exigir sensibilidade/tipping point e NÃO CONFIRMA se a conclusão depender de omissões plausíveis.
- **Potência:** os EPs declarados conferem sob a aproximação independente. Os ~88% e ~67% são aproximações sem multiplicidade e sem todos os requisitos de CONFIRMA; no primeiro degrau bilateral de Holm caem para ~81% e ~57%. Não são potência conjunta de planalto, nível positivo, tercis, identidade e censura. H−L precisa da variância das diferenças; o pareamento não garante por si só redução, pois depende da covariância.
- **DP e limites:** 0,18 é apenas cenário. A faixa “−0,5 a +0,15” não é limite do retorno: a regra usa marca líquida e vende na foto posterior (`paper_engine.py:123`, `:187`; `lab_bets.py:227`). Uma queda entre gatilho e fill ultrapassa −50%; uma alta ultrapassa o alvo. Não estimar DP só pela geometria nominal.
- **“Nunca REFUTA” é falso.** Mesmo com efeito verdadeiro exatamente na MRE, um IC bilateral de 95% corretamente calibrado pode ter seu limite superior abaixo dela em cerca de 2,5% das repetições. Falta de potência tende a NÃO CONFIRMA; não imuniza contra erro amostral (`docs/design/exp-m26-grafico-moedas-maduras.md:248`).

O piloto cego de 24 h deve decidir viabilidade e cobertura **dos grupos da primária**, não inferir 30–100 entradas/dia extrapolando minutos ativos de sobreviventes selecionados. Corrigir também o denominador “line_no_snapshot entre os que passaram a linha”: quem passou o gate completo de linha não pode simultaneamente ter ausência que o bloqueia.

#### 5. Custos e modos de falha adicionais

**5a — Proposta aprovada ainda não fica fixada.** A consulta inclui propostas `proposed`, não `approved` (`services/meme-worker/hunter_meme_worker/tracker_pins.py:57`), enquanto research nasce `approved` (`proposals.py:314`). **Cenário:** a moeda sai do top-K entre proposta e primeiro fill, some do rastreador e termina `no_later_snapshot`. Resolver o intervalo com rastreamento de pesquisa que não contamine a mesa; comprovar com teste integração proposta → prune → fill → restart. Só aumentar I2 não resolve.

**5b — 8.100 s não cobre o ciclo.** A idade do gate é a do fim do minuto (`proposals.py:110`); o fill vem depois; o prazo da posse começa no fill (`paper_engine.py:193`); a série rápida usa limite estrito `age < limit` (`fast_lane.py:132`). **Cenário:** H entra de fato depois de 7.200 s e perde a cadência rápida antes de 900 s de posse, inclusive antes da foto de venda. Cobrir atraso máximo da feature/decisão, fill, posse e liquidação, ou seguir a posição até seu encerramento com orçamento próprio. A configuração é global para todos os pins; não assumir que nenhum braço antigo pode ser afetado sem inventariar os conjuntos vigentes.

**5c — Linha disponível depois do instante de saída.** `_SUPPORT_LINES` filtra `end_time`, não `computed_at` (`lab_repo_lines.py:40`); `support_at` também conhece só `end_time` (`lines_exit.py:37`). O laço carrega as linhas até agora e reprocessa fotos antigas (`lab_bets.py:220`, `:344`). **Cenário:** linha do minuto T calculada em T+60 s é usada para gatilho em T+15 s e venda em T+30 s. A guarda de recebimento de `lines.py:208` protege os insumos da feature, mas não sua disponibilidade computacional na saída. Exigir causalidade também no consumo, intenção efetivamente disponível antes da venda, versão/frescor do suporte e teste de cálculo atrasado. Dois snapshots abaixo não equivalem a dois fechos de minuto: com I2 podem ser duas fotos de 15 s (`lab_bets.py:223`). Fixar essa semântica no protocolo.

**5d — Migração não se corrige trocando só a taxa.** O caminho de pool é escolhido apenas quando `exit_on_migration=false` (`lab_bets_pool.py:64`); para os três braços propostos a venda segue `close_bet` com reservas da curva (`lab_bets.py:230`; `paper_engine.py:215`). **Cenário:** completa/migra no gatilho e a foto seguinte já não representa uma curva negociável; aplicar 1,20% a esse preço fabrica liquidez. Antes do seed, provar o comportamento na conclusão, migração e ausência de próxima foto: preço de venda executável posterior na praça correta, ou censura nomeada. Uma sensibilidade de taxa não substitui essa prova. Pool ainda separa taxa da praça, taxa do caminho e impacto (`pool_mark.py:85`, `:107`).

**5e — Custos e alvo líquido.** `target_x` incide sobre marca líquida/custo (`packages/indicators/hunter_indicators/meme/exits.py:229`), não sobre alta bruta do preço. A sensibilidade real-equivalente deve dizer se apenas refaz a contabilidade mantendo os fills, ou se reexecuta gatilhos dependentes de custo; só a segunda testa a política sob outro custo. Não transportar os 19%/27% da amostra histórica para a geometria destes braços: no exemplo binário ideal de +15% líquido versus −10% líquido, o equilíbrio é 40%; com trailing móvel, tempo, linha e migração não existe esse binário. Tampouco os 3,5% são custo exato invariável por ticket: compra e venda têm bases diferentes. **Cenário:** dupla subtração de taxas ou ganho de alvo tratado como bruto muda o sinal de um efeito de apenas 3 pp.

### NICE-TO-HAVE

- Publicar churn do top-K, idade/frescor do mcap na seleção, cobertura por janela e motivo de retirada.
- Reportar concentração por mint/dia, leave-top-out e leave-one-day-out, sem usá-los para escolher limiares novos.
- Separar resultado sob a política de snapshots de uma alegação sobre execução real; 15 s melhora resolução, não vira OHLC.

### O QUE EU FARIA DIFERENTE

Fecharia primeiro a população e a fonte de observação independente dos braços; depois executaria o piloto cego completo até fill/saída. Minha recomendação é H-022 com primária de associação dentro de C, H−L como pacote de saída secundário pareado e L−C descritivo. Congelaria a especificação analítica e a memória **antes** do seed, não deixaria o item J da §7 para desenhar depois da coleta. Não acrescentaria variantes nem alteraria `lines.py` v1.

### CONCORDO COM

População nova justificada pela KB-0161 e pela regra da Fila; pesquisa prospectiva sem abrir os desfechos da H-021 adaptada; faixa herdada 0–0,25; porta comum sem criador como requisito de entrada, preservando a saída `creator_dump`; fórmula v1 mantida; uso da via de 1 min que efetivamente lê a linha; K desligado por padrão; piloto cego antes dos braços; dinheiro real fora desta decisão. A falha de EXP-M2 não refuta a linha.

### OBSIDIAN

Atualizações propostas ao orquestrador, sem editar essas páginas nesta rodada:

- **EXP-M26 — gráfico em moedas maduras** (nova): congelar população, amostragem independente, primária, censura, custos e execução após resolver os must-fix.
- **Fila de Hipóteses**: registrar H-022 apenas com o contraste e a regra de decisão completos; não copiar a §3 atual sem revisão.
- **EXP-M2 — a linha manda**: acrescentar avaliação datada de zero propostas, funil auditável e limite da atribuição causal, preservando o protocolo.
- **KB-0161 — O gráfico de 5 minutos não existe na porta**: ligar a nova população à lacuna identificada, sem apresentá-la como validação da H-021.
- **Dicionário de Variáveis**: documentar disponibilidade da linha/slope em C e os relógios de observação, cálculo e decisão.
- **Mapa de Estratégias**: registrar EXP-M26 como desenho; só marcar coleta/em curso quando houver instrumentação e seed efetivos.


## Claude (rodada 2)
Rodada 2. Reescrevi docs/design/exp-m26-grafico-moedas-maduras.md incorporando a sua rodada 1. Consultas e saídas duráveis agora em .claude/state/m26/ (q*.sql, outputs.txt). Ponto a ponto: (1) Funil EXP-M2: aceito — §1.4 agora diz que a linha nunca foi julgada, que a ordem causal não é sustentada, e documenta o sobrevivente (3EsVoo…pump, 13/09 01:39Z) cuja recusa não é recuperável (meme_gate_refusals_by_mint começa 19/09 15:06Z); o funil F pré-seed vai até a proposta simulada; 'flat' corrigido (monótona viva também é flat). (2a) Aceito: retidas em orçamento À PARTE (teto das jovens inalterado); acrescentei que apostas abertas ganham prioridade REST (collect.py:184) e de fita (wiring.py:223/trades.py:300) — concorrência esperada ~1–3, pior caso 75, guarda com gatilho >10 no p95 horário. (2b) Aceito: a primária passa a ler linha_ok no 1.º minuto elegível de C, antes de qualquer aposta do EXP-M26 na moeda (porta de L ⊇ porta de C ⇒ C chega primeiro ou junto); contaminação por portas de 1–4 min é covariável. (2c) Aceito: mcap_observed_at novo, frescor ≤120 s, warmup só com foto ≤120 s, censura por lacuna >150 s na janela de 15 min (sem mudar lines.py v1). (3) Aceito: participação = 7 SOL/min; primária dentro de C (associação, desconhecida à parte, fonte = meme_features_1m com computed_at ≤ proposed_at); L−C descritivo; H−L = pacote pareado por (mint, features_end_time, foto de fill), par ausente contado. (4) Aceito: Holm sobre os 2 p; ICs marginais; bootstrap por mint com todos os braços; permutação de linha_ok dentro do dia; inscrição fecha no 1.º corte 00:00Z após 7 dias completos com ≥150 linha_ok em C, máx. dia 21, leitura 2 h depois; limite de dado <100 linha_ok no dia 21; denominador nasce na 1.ª decisão antes de filtrar desfecho; imputação adversa (p10/p90) como condição; 'nunca REFUTA' corrigido; faixa de retorno corrigida; potência recalculada (150 vs 450: 84%/76% para +0,05). (5a) I2 fixa approved sem aposta do EXP-M26. (5b) Não subo o env global (flow_v2/1,9,10 têm max_hold 1800 e seriam afetados); série de 15 s por pertença EXP-M26 até o fecho. (5c) Medi fold delay p50 3,0 / p99 5,3 s; L1 acrescenta computed_at ≤ at na saída; semântica 'duas fotos na cadência da aposta' congelada. (5d) migrated/curve_complete = censura na primária; repreço por board só descritivo. (5e) sensibilidade real-equivalente declarada como contábil, não re-simulação; removi os equilíbrios transportados. Perguntas: há algum must-fix restante com cenário de falha concreto? Em particular: (a) o gatilho do funil F (C ≥50/dia, linha_ok ≥8/dia, recusa de instrumento ≤30%) está bem posto? (b) a imputação adversa p10/p90 é defensável ou você propõe outra? (c) a H-022 da §3 pode ser congelada como está? Se convergimos, abra a rodada com DECISÃO CONJUNTA e liste os pontos acordados e as divergências registradas.

## Astra (rodada 2)

### RESUMO

**REVISE — ainda não há convergência para DECISÃO CONJUNTA nem para congelar a §3 como está.** Papel: `quant-engineer`. O desenho incorporou os principais acordos; restam falhas delimitadas no isolamento do rastreador, na definição dos denominadores e da inferência, e na identificação de vendas sem praça executável.

Respostas diretas: **(a)** 50 C/dia e 8 `linha_ok`/dia são pisos operacionais plausíveis, mas o gatilho F está incompleto; **(b)** p10/p90 é defensável como cenário de sensibilidade, não como garantia de robustez à censura informativa; **(c)** H-022 ainda precisa das correções abaixo antes do congelamento. Não proponho variantes de entrada nem abrir desfechos para decidir essas correções.

A motivação continua sustentada por **KB-0161**, que registra a incompatibilidade da janela de cinco minutos com a porta jovem (`obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:35`), e pela pergunta aberta sobre horizontes maiores da **KB-0149 §7**. A regra 1 da **Fila de Hipóteses** permite a população nova (`obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:18`). Isso justifica medir; não antecipa vantagem.

### ARQUIVOS

Única escrita desta rodada: append de `## Astra (rodada 2)` em `.claude/state/dialogue-EXP-M26.md`. Desenho, código, configurações e páginas do Obsidian não foram modificados por mim. A árvore já continha alterações de outros trabalhos.

### TESTES

Revisão estática com `Get-Content -Encoding utf8` e `rg -n`, incluindo o diálogo inteiro, o desenho revisado e as consultas/saídas em `.claude/state/m26/`. Não executei pytest, lint, migrações, consultas na VPS nem abri desfechos novos. Os resultados SQL são os registros do Claude, não uma medição reproduzida nesta rodada.

Recalculei em JavaScript, em memória, a aproximação normal bilateral declarada (DP 0,18; independência apenas para este cálculo). Saída real, arredondada aqui a seis casas:

```text
n_true n_false efeito  EP        poder alpha=.05  poder alpha=.025
150    450     .05     .016971   .838011          .759556
150    450     .03     .016971   .423891          .317910
100    300     .05     .020785   .672086          .565224
100    300     .03     .020785   .303055          .212542
```

Os 84%/76% e 42%/32% do desenho conferem. Continuam sendo potência marginal sob suposições, não potência conjunta do veredito.

### MUST-FIX — resposta ponto a ponto

#### 1. Funil histórico de EXP-M2

**Concordo com a conclusão revisada e com o limite de reconstrução.** O sobrevivente não explicado deixa de ser tratado como prova de uma causa. As contagens 287, 275, 8 e 1 estão registradas em `.claude/state/m26/outputs.txt`, blocos q6/q8/q11. A formulação correta é: entre 12 criadores conhecidos, quatro eram vendedores; entre os oito não vendedores, sete falharam na participação. A frase “dos 12 conhecidos, a participação eliminou 7” deve preservar essa ordem (`docs/design/exp-m26-grafico-moedas-maduras.md:114`). É ajuste de precisão, não um bloqueio novo. Aceito também a correção de `flat`.

#### 2a. Retenção, pins e isolamento das jovens — ainda falta fechar

**O orçamento à parte para retidas resolve só a fase sem aposta.** O desenho mantém `cap − |fixadas|` para as jovens e depois transforma propostas/apostas do EXP-M26 em fixadas (`docs/design/exp-m26-grafico-moedas-maduras.md:157`, `:190`). Hoje `prune` subtrai todos os pins presentes do teto (`services/meme-worker/hunter_meme_worker/tracker.py:243`).

**Cenário:** com teto 300 e nenhuma posição anterior, dez mints maduros exclusivos do EXP-M26 passam a pin; o espaço das não fixadas cai a 290. O piloto I1 sem apostas preserva o teto, mas o seed I2 o reduz. Logo “teto das jovens inalterado” ainda não está satisfeito.

**Correção:** distinguir o conjunto de pins ordinários do conjunto exclusivo de acompanhamento EXP-M26, por mint. O segundo precisa de orçamento próprio também depois da proposta/fill; uma moeda que pertença aos dois continua ordinária, contada uma vez. Testar retenção → approved → fill → fecho → restart com o mesmo orçamento das jovens. Incluir propostas pendentes e reentradas no orçamento, não apenas primeiras entradas.

Aceito monitorar prioridades REST/fita, mas “p95 horário >10” não garante preservação durante rajadas curtas. A prioridade é efetiva em `collect.py:184`, `wiring.py:223` e `trades.py:300`. Congelar a ação das guardas antes da coleta: interromper novas inscrições, registrar o fim da coorte e acompanhar as pendências. **K=0 sozinho não bloqueia novas propostas de moedas ainda retidas pelos pins**: a porta não consulta K (`proposals.py:265`). Retomar com uma política de prioridade alterada exige coorte identificada, não misturar silenciosamente antes/depois (`docs/design/exp-m26-grafico-moedas-maduras.md:173`, `:426`).

#### 2b. Primeira decisão de C e interferência entre braços

**Aceito a solução para a variável de entrada da primária**, desde que a primeira oportunidade comum seja realmente registrada antes de qualquer aposta do EXP-M26 no mint. Em termos de conjuntos de moedas elegíveis, **L ⊆ C**; L tem os critérios de C mais os de linha. O raciocínio de C chegar antes ou junto está correto (`docs/design/exp-m26-grafico-moedas-maduras.md:249`).

Congelar a escolha por oportunidade antes de filtrar qualidade, fill ou sucesso de persistência; provar a invariância com falha parcial/restart. A primeira proposta persistida não deve substituir uma oportunidade anterior perdida. O código cria propostas apenas depois das recusas e da disponibilidade de cotação (`services/meme-worker/hunter_meme_worker/proposals.py:267`, `:270`), portanto “primeira decisão” e “primeira proposta” precisam de definição única em J/F.

**Ressalva que deve constar do estimando:** antecipar a leitura de `linha_ok` elimina a contaminação direta de entrada pelo próprio mint, mas não torna independentes todas as saídas. L/H podem manter fotos de 15 s depois que C fecha; reentradas podem fazer isso depois que o primeiro H fecha. As linhas de saída usam essas fotos (`packages/indicators/hunter_indicators/meme/lines.py:195`; `services/meme-worker/hunter_meme_worker/lab_bets.py:225`).

**Cenário:** H já encerrou, L continua aberto; uma reentrada de H sustenta a cadência que permite a L disparar `line_broken`. O par mede os pacotes dentro do sistema conjunto, não duas políticas isoladas. Aceito **D_pacote sob a observação conjunta L+C+H**, com isso escrito na §3; se a pretensão for H/L isolados, é preciso separar a observação. Não exijo essa separação para a interpretação conjunta. Covariável das portas jovens deve ser definida com informação anterior à oportunidade, não pela condição “alguma vez teve aposta” até a leitura.

#### 2c. Frescor, warmup e janela da linha

**Aceito `mcap_observed_at`, desempate, 120 s e lacunas nomeadas.** O warmup também precisa do limite superior `observed_at ≤ now`, disponibilidade `received_at ≤ now` e a mesma elegibilidade do prune; não apenas `observed_at ≥ now−120s` (`docs/design/exp-m26-grafico-moedas-maduras.md:180`).

**Falta fechar o cálculo de cobertura:** incluir as bordas da janela, não só diferenças entre fotos existentes, e aplicar o corte de recebimento da calculadora. A produção exige só cinco pontos e o rompimento usa a janela anterior **(T−16 min, T−1 min]** (`packages/indicators/hunter_indicators/meme/lines.py:281`, `:283`).

**Cenário:** cinco fotos nos últimos quatro minutos têm todos os intervalos <150 s, mas onze minutos não foram observados. Ou falta justamente a máxima no minuto T−16 a T−15, fora da guarda proposta, e aparece um rompimento falso. Definir cobertura de ambas as janelas usadas pela fórmula; quando parte preceder a criação conhecida, declarar essa truncagem e sua regra, sem chamar a janela de completa. Isso é guarda de pesquisa e não exige mudar `lines.py` v1.

#### 3. Braços, fonte em C e funil F — resposta (a)

**Concordo com participação de 7 SOL/min, fonte exata/versionada em C, desconhecida separada, L−C descritivo e chave de par.** Preservar a igualdade da decisão e identificar a foto de fill por sua identidade completa, incluindo fonte quando necessário. Pares ausentes continuam no denominador.

**F ainda pode aprovar um experimento impossível de julgar.** Hoje exige C≥50, true≥8 e cada motivo instrumental≤30%, mas não exige `false` conhecido nem limita a união das falhas (`docs/design/exp-m26-grafico-moedas-maduras.md:348`).

**Cenário:** 50 primeiras oportunidades, oito true e 42 desconhecidas; três causas disjuntas atingem 14 oportunidades cada (28%). Todos os pisos passam, mas não existe grupo false. Outro caso: contar a primeira ocorrência de linha_ok ao longo da vida seleciona os oito de L, sem que sejam true na primeira oportunidade de C.

Minha proposta para F:

- Escolher uma primeira oportunidade de C por mint, ordenar antes de verificar linha, e classificar **nesse instante** true/false/desconhecida. Auditar também quem não produziu proposta.
- Manter 50 C e oito true como pisos de viabilidade; acrescentar **24 false conhecidos/dia** se a justificativa de potência continuar 150:450. São metas operacionais pré-declaradas, não evidência de potência atingida. Oito true/dia dariam 168 inscrições em 21 dias apenas se o ritmo persistisse.
- Medir a **união** das falhas instrumentais, além de cada motivo; exigir compatibilidade com a censura final ≤20% por grupo. Diferenciar ausência estrutural (`flat`/suporte não definido) de falha de coleta. A §2.2 atualmente põe ambas em desconhecida; isso restringe o contraste às linhas traçáveis e precisa ser explicitado, não “corrigido” forçando flat a false.
- Verificar proposta → fill → saída/censura antes do seed confirmatório com fixtures de integração e um piloto técnico separado, sem ler retornos para escolher regras. SQL até proposta simulada não prova I2. Deixar essa prova para a primeira semana repete o risco de nascer uma coorte sem execução (`docs/design/exp-m26-grafico-moedas-maduras.md:356`).

Se faltar mercado elegível, o resultado é inviabilidade/limite de dado; não é sempre “consertar o instrumento”. A frase da linha 355 deve distinguir os dois.

#### 4. Inferência, parada e censura — respostas (b) e (c)

**Aceitos:** duas hipóteses na família, Holm sobre dois p, ICs marginais identificados, reamostragem que preserva o mint e os pares, corte por inscrições, maturação separada, e as correções de potência/faixa de retorno. Mas a §3 ainda não é executável sem decisões posteriores:

**4.1 — Dois grupos e dependência temporal.** O corte/minimum só conta true, embora a potência suponha 450/300 false (`docs/design/exp-m26-grafico-moedas-maduras.md:290`, `:297`, `:331`). Congelar mínimos de inscritos e avaliáveis **dos dois grupos**, suporte por dia/estrato e mínimo de pares H/L. Minha recomendação operacional é corte-alvo 150 true/450 false inscritos; no dia-limite, exigir pelo menos 100 true/300 false avaliáveis para usar a aproximação mínima apresentada, ou declarar limite de dado. Não há obrigação de obter significância.

Permutar rótulos dentro do dia não resolve automaticamente dependência, heterogeneidade nem permutabilidade (`:310`). **Cenário:** uma rajada horária concentra vários mints true e seus ganhos; embaralhar individualmente entre manhã e tarde e reamostrar só mints transforma um choque comum em muitas réplicas independentes. Fixar em J a estatística, os estratos pré-decisão, o tratamento de células sem ambos os grupos e uma análise em blocos temporais. Se a conclusão depender de ignorar esses blocos, NÃO CONFIRMA. Chamar de associação é correto, mas não calibra o p-valor sozinho.

Também falta o **segundo p**: “IC pareado >0” não especifica como testar D_pacote. Definir teste da média das diferenças, unidade de reamostragem e hipótese nula; troca de sinal/par só com sua suposição justificada. Holm não pode receber um p improvisado na leitura. Ausência de contraste avaliável mantém a família predefinida, com resultado não testável, sem reduzir oportunisticamente a multiplicidade.

**4.2 — p10/p90 não cobre censura informativa.** Aceito como cenário adicional; não aceito a redação “sobrevive à censura” só porque esse cenário passa (`:289`).

**Contraexemplo sintético, não dado do projeto:** 100 oportunidades true, 85 observadas com média +0,06 e p10 −0,10, 15 censuradas; controle com média zero. Imputar −0,10 dá média **+0,036**. Se as 15 ausentes perderam −0,80, dá **−0,069**. A censura é 15%, abaixo do teto, e o próprio processo pode ocultar precisamente a cauda que os quantis observados não conhecem. Saída real do cálculo em memória: `0.036` e `-0.069`.

**Proposta:** congelar análise de ponto de inversão para D=0 e D=+0,03, variando a média dos ausentes de cada grupo; incluir estresse de perda integral compatível com o custo de entrada nas compras preenchidas e cenários próprios para migração. Não inventar teto superior de retorno nem quantis de um grupo vazio. Declarar previamente quais cenários sustentam o rótulo; p10/p90 sozinho não basta. Aplicar a robustez também ao nível positivo e, para o secundário, aos pares incompletos. A incerteza não pode tratar valores imputados como novas observações independentes.

**4.3 — Variável desconhecida não tem grupo.** “Censura >20% de qualquer grupo” fica indefinida para linha desconhecida (`:264`, `:290`). Congelar: N total de primeiras oportunidades; N true/false/desconhecida; falhas de desfecho dentro de cada grupo conhecido; taxa desconhecida sobre N total; pares completos/ausentes sobre oportunidades comuns L/H. Não somar motivos sobrepostos como pessoas distintas. Para desconhecida, limitar a conclusão explicitamente ao subuniverso de linha traçável e reportar cobertura, ou fazer sensibilidade também à atribuição de grupo. p10/p90 não imputa `linha_ok`.

**4.4 — Corte e cegamento.** Dar timestamp exato de início, último corte e leitura; excluir novas oportunidades depois do corte e permitir apenas maturação das inscritas. Congelar tratamento de planalto/tercis vazios, empates e slope ausente; identidade deve comparar contrastes sobre população comparável. A §4 diz simultaneamente “só contagens cegas” e “a ficha diária mostra PnL” (`:301`, `:303`): definir quem permanece cego e como os resultados ficam ocultos à equipe que ainda decide F/J. Não chamar a coleta de cega se a equipe os acompanhar. Nenhum desses ajustes requer ler desfechos agora.

#### 5a e 5b. Approved e 15 s até o fecho

**Concordo com as duas soluções**, subordinadas ao orçamento de pins de 2a. A proposta research nasce approved (`services/meme-worker/hunter_meme_worker/proposals.py:314`); a cadência por pertença evita alterar globalmente braços antigos. Fixar o prazo terminal de approved sem fill, garantindo liberação do pin após recusa; o teste integrado deve incluir esse ramo e restart. Orçar chamadas, fotos e features de I2, não apenas as linhas/minuto de I1 (`fast_lane.py:242`, `:262`).

#### 5c. Causalidade da linha de saída

**L1 corrige o look-ahead apontado; o p99 observado não é limite máximo.** Aceito `computed_at ≤ at` e duas fotos, não dois fechos. Falta declarar validade do suporte: `_SUPPORT_LINES` remove linhas nulas e `support_at` escolhe a última válida sem limite de idade (`services/meme-worker/hunter_meme_worker/lab_repo_lines.py:40`; `lines_exit.py:41`).

**Cenário:** a linha atual é flat/nula, mas a reta de vinte minutos atrás segue projetada e dispara `line_broken`. Congelar se ausência recente invalida o suporte e qual o frescor permitido; sugiro ≤120 s e ausência nomeada, sujeito a teste. Se a escolha for manter indefinidamente o último suporte válido, descrevê-la expressamente como regra do pacote, sem alegar suporte atual. O teste atrasado deve alcançar gatilho e foto de venda no laço, não só `support_at`.

#### 5d. Migração — censurar só pelo motivo ainda deixa venda impossível

**Concordo em censurar ausência de praça executável; o predicado proposto é insuficiente.** O laço fecha uma intenção pendente antes de reavaliar a condição de migração daquela foto (`services/meme-worker/hunter_meme_worker/lab_bets.py:227`, `:252`); `close_bet` recebe e preserva o motivo antigo (`paper_engine.py:207`, `:227`).

**Cenário:** target em T; a curva completa/migra antes da próxima foto; a venda usa reservas dessa foto e continua com motivo target. Excluir apenas `exit.reason IN ('migrated','curve_complete')` deixa o PnL impossível na primária. O mesmo vale para trailing e creator_dump.

**Correção:** qualidade baseada na praça e no estado da foto efetivamente usada, timestamps de conclusão/migração e evidência de negociabilidade, independentemente do gatilho. Ausência ou ambiguidade vira censura nomeada em C e em qualquer perna H/L. Provar migração entre gatilho/fill, conclusão sem evento de migração, ausência de próxima foto e resgate por leitura pontual. Board posterior continua descrição, nunca venda executável comprovada.

#### 5e. Custos

**Concordo com sensibilidade estritamente contábil e retirada dos equilíbrios transportados.** Em J, escrever a fórmula que remove as taxas efetivamente já debitadas e acrescenta o custo alternativo, mantendo impacto e denominador; não simplesmente somar 3,5% ao PnL e descontar outra constante. As bases da compra/venda diferem, como o próprio desenho reconhece (`docs/design/exp-m26-grafico-moedas-maduras.md:366`). Os 4,09% são média histórica; para rent não recuperado de 0,00151384 SOL e ticket 0,07, usar a proporção do ticket ou manter explicitamente o cenário histórico, sem o chamar custo exato deste braço (`:315`, `:365`).

### NICE-TO-HAVE

- Em q4, `on_curve` é média de **observações**, enquanto `mints` conta distintos. Multiplicar 374 mints por 0,447 não mede 167 mints distintos na curva. Corrigir a query com `count(DISTINCT mint) FILTER (...)` antes de usar isso como dimensionamento (`.claude/state/m26/q4.sql`; desenho `:130`). Não muda o veredito, porque F deve medir diretamente a população prospectiva.
- Mostrar churn e distribuição de idade/frescor do mcap, concentração temporal e cobertura das duas janelas, sem usar os diagnósticos para escolher limiares de lucro.
- Distinguir no Obsidian o veredito da H-022 no moinho de qualquer selo editorial de estratégia validada. A página Meme declara 100 avaliáveis e 30 dias para esse último (`obsidian/03-TRADING/Meme/README.md:39`); este estudo de até 21 dias se propõe apenas a indicar candidato a sombra.

### O QUE EU FARIA DIFERENTE

Fecharia J antes do piloto confirmatório: população, registro da primeira oportunidade, classificação/denominadores, dois testes, blocos, censura e rótulos. Separaria F de viabilidade da prova técnica de execução; ambos antecedem S. Instrumentação pode ser construída com critérios de aceite concretos, mas **a §3 atual não deve ser copiada para a Fila como congelada**. Não mudaria banda, fórmula v1, ticket nem pacotes para obter amostra.

### CONCORDO COM

Convergimos na pergunta de pesquisa e na maior parte do desenho: população madura prospectiva; top-K causal e desligado por padrão; primária associativa dentro de C; variável de entrada anterior às próprias apostas; L−C descritivo; H−L pacote pareado; 7 SOL/min; desconhecida separada; `computed_at` na entrada/saída; acompanhamento por pertença; interpretação contábil dos custos; Holm com ICs marginais; nenhuma conclusão de desempenho antes da medição. As divergências restantes são as condições operacionais e analíticas descritas acima, não uma nova direção estratégica.

### OBSIDIAN

Páginas a atualizar pelo orquestrador; nenhuma foi editada nesta rodada:

- **EXP-M26 — gráfico em moedas maduras** (nova): registrar desenho ainda em revisão e congelar protocolo somente após fechar pins, observação conjunta, primeira oportunidade, censura e inferência.
- **Fila de Hipóteses**: inserir H-022 apenas com os dois testes e a regra de decisão completos; não congelar a §3 atual.
- **EXP-M2 — a linha manda**: acrescentar o funil datado e a recusa histórica irrecuperável, preservando hipótese/protocolo originais.
- **Dicionário de Variáveis**: documentar true/false/desconhecida, janelas de 15/16 minutos, disponibilidade em T e validade do suporte de saída.
- **Mapa de Estratégias**: manter EXP-M26 como desenho, sem apresentá-lo como coleta ou evidência favorável.
- **KB-0161 — O gráfico de 5 minutos não existe na porta**: ligar a investigação madura à lacuna de população/instrumento, sem reabrir os desfechos da H-021 adaptada.
## Claude (rodada 3)
Rodada 3. Incorporei a sua rodada 2 em docs/design/exp-m26-grafico-moedas-maduras.md (§1.4 wording 4 vendedores/7 por participação; §1.5 refeito com q4b.sql = mints DISTINTOS na curva: movers 221/68/38, graduating 129/65/47, união 15–120 min = 292/dia; §1.6 I1: orçamento à parte inclui as fixadas só pelo EXP-M26, teto das jovens = cap − |fixadas ordinárias|, warmup com now−120≤observed_at≤now e received_at≤now, guarda de cobertura das DUAS janelas (T−16,T] com bordas ≤150 s e gaps ≤150 s, truncada-no-nascimento declarada; I2 prazo terminal 180 s e custo; L1 agora por parâmetros só do EXP-M26: line_support_causal + line_support_max_age_s=120 (support_stale), e recomendação separada ao orquestrador de corrigir computed_at globalmente com risk-engine-guardian; §2.2: 1.ª oportunidade = reavaliação pura de evaluate_entry sobre meme_features_1m (não a 1.ª proposta), pedigree pela trilha de recusas, sem_proposta por instrumento >5% → NÃO CONFIRMA; classes true / false (inclui flat/out_of_range cobertos = ausência estrutural, a porta de L recusa pelo mesmo motivo) / desconhecida (falha de coleta), com sensibilidade 'false só traçável'; estimando D_pacote sob observação conjunta L+C+H; covariável só com informação anterior; §3 H-022 reescrita; §4: T0 = fim de piloto técnico 48 h fora da inferência, corte = 1.º 00:00Z após 7 d com ≥150 true e ≥450 false, máx. dia 21, leitura +2 h, limite de dado <100 true ou <300 false; coleta declarada NÃO cega (proteção = congelamento com impressão digital); denominadores com um motivo por oportunidade; permutação em dia×bloco 6 h + bootstrap por blocos 6 h como condição; secundária com troca de sinal pareada; Holm fixa com secundária 'não testável' mantida na família; estresse: ponto de inversão reportado + cenário que sustenta o rótulo = censurados de true a −0,50/SOL e de false na média observada, IC recalculado sem tratar imputados como observações; perda integral descritiva; fórmula contábil por perna; F com pisos C≥50, true≥8, false≥24, união de falhas ≤15%, inviabilidade de mercado ≠ conserto de instrumento; §5 censura por praça/estado da foto de venda qualquer que seja o gatilho; §6.8 ação congelada da guarda = aposentar os três conjuntos (deprecate auditado) + K=0 + fim de coorte, retomada só com versão nova. Perguntas: (a) Classificar flat/out_of_range cobertos como false (com a sensibilidade 'só traçável') é aceitável? (b) O cenário −0,50/SOL para censurados de true é o certo para sustentar o rótulo? (c) Restam must-fix com cenário de falha concreto? Se convergimos, abra com DECISÃO CONJUNTA listando o acordado e as divergências registradas.

## Astra (rodada 3)

### RESUMO

**REVISE — ainda não há convergência para DECISÃO CONJUNTA nem para congelar a H-022 como está.** Papel: quant-engineer; tarefa de análise em modo DIÁLOGO.

Respostas diretas: **(a)** aceito flat coberto como false; aceito out_of_range como recusa conhecida da implementação v1, com a ressalva abaixo; **(b)** −0,50/SOL é um cenário nominal, não o cenário suficiente para sustentar a robustez proposta; **(c)** restam os cinco bloqueios delimitados abaixo. Não peço outra estratégia, outra banda ou desfechos para escolher regras.

A motivação permanece: a KB-0161 documenta a incompatibilidade entre a janela histórica e a porta jovem (obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:35); a KB-0149 mantém aberta a pergunta de horizontes maiores (obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:85); a Fila permite população nova, sem reabilitar automaticamente variáveis esgotadas (obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:18). O protocolo original de EXP-M2 continua congelado (obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md:69).

### ARQUIVOS

Única escrita: append desta seção em .claude/state/dialogue-EXP-M26.md. Nenhum outro arquivo alterado por mim; nenhum commit.

### TESTES

Revisão estática com Get-Content -Encoding UTF8 e rg -n: diálogo completo, desenho, memória, consultas e saídas registradas, caminhos de entrada, retenção e saída. Não rodei pytest, lint, migrações ou consultas na VPS. As contagens de q4b são registros fornecidos pelo Claude, não medição reproduzida nesta rodada.

Cálculo sintético em JavaScript, em memória, sem dados de desempenho do projeto: 200 true, 180 observados com média +0,10, 20 censurados; controle com média zero. Saída real:

    imputacao_menos_050: 0.04
    imputacao_perda_integral: -0.01
    ponto_inversao_D_zero: -0.9
    ponto_inversao_D_003: -0.6

Isso testa a aritmética do contraexemplo, não o código do experimento nem seus ICs.

### MUST-FIX

#### (a) Classes: aceito a mudança de estimando, com precisão sobre out_of_range

**Flat coberto pode ser false.** Retiro a restrição da rodada 2 de sempre deixá-lo fora: agora a variável é explicitamente “satisfaz a regra executável v1”, e a sensibilidade “false só traçável” mantém a comparação anterior. Não se está convertendo falha de coleta em ausência de sinal (desenho:320).

**Out_of_range não significa necessariamente ausência dos dois fundos.** Ele nasce dentro de _support, depois de encontrá-los: suporte projetado não positivo ou limites numéricos de inclinação/distância também produzem esse motivo (packages/indicators/hunter_indicators/meme/lines.py:244, :252, :257). A porta o recusa quando faltam os valores necessários (packages/indicators/hunter_indicators/meme/rules_criteria.py:166).

Aceito classificá-lo como false **operacional da v1**, contado separadamente, sem afirmar que toda ocorrência é ausência estrutural de mercado. Se a pergunta continuar sendo sobre a estrutura matemática independentemente da representação v1, separar os motivos ou mantê-lo desconhecido. Para o estimando operacional declarado, isto é ajuste de precisão, não motivo adicional para bloquear o experimento. Guardar a cobertura com os mesmos pontos utilizáveis da fórmula — recebimento, mcap positivo e deduplicação — e não com qualquer fotografia presente (lines.py:195).

#### 1. A primeira oportunidade ainda não tem evidência durável suficiente

A reavaliação pura é uma boa definição, mas a fonte proposta para pedigree não a sustenta (docs/design/exp-m26-grafico-moedas-maduras.md:299, :307):

- A via de 1 min avalia o lote e grava propostas e contadores agregados; não grava ali a trilha individual usada pela proposta de reconstrução (services/meme-worker/hunter_meme_worker/lab.py:241, :254, :267).
- A trilha existente é amostrada: duas ou mais recusas não entram (services/meme-worker/hunter_meme_worker/gate_refusal_trail.py:66).
- Sua retenção é sete dias e há poda efetiva, menor que o horizonte máximo da coleta (services/meme-worker/hunter_meme_worker/config_trail.py:26; lab_trail.py:88).
- Os flags Mayhem são carregados do estado corrente de meme_tokens (services/meme-worker/hunter_meme_worker/lab_repo_mayhem.py:40). “Token gravado” não equivale, sozinho, ao estado que estava disponível na oportunidade histórica.

**Cenário:** C passa os critérios puros, mas falha creator_serial e symbol_clone. Não há proposta nem linha individual utilizável; a leitura chama isso sem_proposta por instrumento. Mesmo uma recusa preservada pode desaparecer antes do dia 21. Outra reconstrução que use o token já migrado pode excluir retrospectivamente uma oportunidade anterior válida; entry_features_of testa a presença de completed_at/migrated_at, não sua relação com o minuto histórico (services/meme-worker/hunter_meme_worker/proposals.py:133).

**Correção mínima:** acrescentar à instrumentação, antes de F/S, registro durável completo das oportunidades e exclusões relevantes na via de 1 min, incluindo relógio de decisão, versão, valores/estado disponíveis e vínculo com proposta ou motivo de ausência. Reter até depois da leitura; uma cópia completa no Postgres serve, não precisa ampliar toda a trilha global. Provar restart, falha parcial e retenção além de sete dias.

Fixar também **um relógio único**: o desenho admite computed_at até T+60 s sem proposta, mas até proposed_at quando ela existe (:316). Uma feature calculada em T+65 s pode ser conhecida ou desconhecida conforme o sucesso de persistência. Congelar o limite antes dessa distinção, incluindo o que acontece com feature atrasada. O hash do código não substitui a captura dos insumos históricos.

#### (b) 2. Censura: o stop nominal não limita a perda, e falta estressar o lado subtraído

A própria §4 reconhece que o retorno ultrapassa −50%, mas chama esse número de piso do estresse (desenho:411, :444). O gatilho compara a marca com o custo; a venda usa outra fotografia (packages/indicators/hunter_indicators/meme/exits.py:214; services/meme-worker/hunter_meme_worker/lab_bets.py:227; paper_engine.py:207).

**Cenário concreto:** no exemplo sintético de TESTES, só 10% de censura; imputar −0,50 conserva D=+0,04 e nível positivo. Perda integral nos ausentes produz D=−0,01. A inversão ocorre em −0,90 e a MRE deixa de ser atendida em −0,60. Portanto o teste nominal pode preservar justamente a conclusão que desaparece no evento de drenagem sem foto.

**Minha proposta:** manter −0,50 como diagnóstico; para sustentar o rótulo de robustez, exigir pelo menos perda integral das compras preenchidas do grupo favorecido, junto do nível positivo. Usar **−sol_spent/size_sol**, não “−1 mais a taxa de compra”: quote_buy retira a taxa de dentro do orçamento e paper_fill grava esse custo inteiro (packages/indicators/hunter_indicators/meme/curve.py:272; services/meme-worker/hunter_meme_worker/paper_fill.py:171). Somar novamente a taxa de entrada a −1 duplica o custo deste papel.

Isso ainda não é limite inferior de D: imputar a média observada aos ausentes de false supõe que eles não tiveram ganhos diferentes. Congelar sensibilidade bidimensional às médias ausentes; explicitar que qualquer conclusão é condicional à região examinada, sem inventar teto de retorno. Se só o cenário nominal passar e a perda integral plausível inverter, NÃO CONFIRMA.

**Secundária:** “lado de H a −0,50” não cobre L ausente (desenho:419). H observado em +0,10 e L censurado que teria +1,00 dá diferença −0,90, não vantagem de H. Preservar a perna observada e congelar os três casos H ausente/L presente, H presente/L ausente e ambos ausentes. No bootstrap, reamostrar mint/bloco com seu estado de ausência; constantes de cenário ficam associadas às unidades, e médias estimadas dos observados são recalculadas. Não transformar imputações em réplicas independentes.

#### 3. Sem fill continua contado, mas não tem limite que proteja a primária

A §3 limita desconhecida, sem_proposta e preenchidos sem desfecho; a §4 diz que sem fill “conta na taxa”, sem definir o teto nem incluí-lo na regra de instrumento (desenho:360, :383, :406).

**Cenário:** 200 oportunidades true, 100 sem fill e 100 avaliáveis; 300 false avaliáveis. No dia-limite passam os mínimos e os tetos expressos, apesar de metade do grupo true desaparecer. Se a falta de foto posterior ocorre nas moedas que drenam, a média dos preenchidos é uma seleção posterior à entrada.

Não peço inventar PnL para uma posição inexistente. **Correção:** fixar o denominador da união sem_proposta por instrumento + sem fill + preenchido sem desfecho, por classe conhecida, e aplicar o teto de 20% já escolhido a essa união, mantendo o teto adicional de 5% para sem_proposta. Reportar os motivos separados. Declarar que o retorno observado é condicional ao preenchimento e que a extensão às oportunidades exige a sensibilidade/limitação correspondente. O piloto F/P não substitui essa guarda na coorte final.

#### 4. Inferência: população do teste e dependência devem ser iguais nos dois contrastes

Aceito os alvos 150/450, mínimos 100/300, 100 pares e família fixa. Restam dois problemas executáveis (desenho:359, :391):

**4a — D e p podem julgar populações diferentes.** D usa todos os avaliáveis; a permutação exclui estratos sem ambos os grupos. Cenário: um bloco contém só true muito lucrativos, enquanto os blocos com sobreposição têm D≈0. O D global cruza a MRE por uma população que o p descartou.

Definir no J uma única população e estatística para D, IC, MRE e p. Se a inferência usar apenas sobreposição, calcular todos nela, aplicar ali os mínimos e publicar o D global como descrição. Fixar a ponderação por estrato; não mudar a população silenciosamente. Permutar rótulos de uma regra determinística exige a hipótese de permutabilidade condicional, não deriva do fato de chamar o efeito de associação.

**4b — Parear não elimina dependência temporal nem garante simetria.** O secundário continua com bootstrap por mint e troca de sinais por par, sem a guarda de blocos imposta à primária (:397). Cenário: cem pares entram na mesma rajada, H ganha de L pelo mesmo choque; cem trocas independentes de sinal tratam um choque como cem informações. Declarar simetria não resolve essa dependência.

Aplicar também ao secundário uma inferência que preserve os blocos e exigir suporte temporal mínimo pré-fixado; por exemplo, manter a unidade mint dentro dos blocos e testar a média com reamostragem em blocos centrada sob a nula. A troca de sinal pode ficar como análise condicional à simetria/independência apropriadas, não como justificativa automática do p da média. Fixar o tratamento de blocos vazios, poucos blocos e IC não finito; nesses casos NÃO CONFIRMA, nunca retirar a hipótese da família. O mesmo IC que governa confirmação deve proteger REFUTA: um IC por mint estreito não pode refutar quando o IC temporal ainda comporta a MRE.

#### 5. Fronteiras da coorte: piloto e parada operacional precisam fechar o protocolo

**Piloto → T0.** O piloto abre apostas nos mesmos braços e T0 é seu fim (desenho:367, :477). Cenário: um mint recebeu aposta no piloto, continua com fotos extras e tem nova entrada depois de T0. Selecionar “primeira dentro de [T0,corte)” faz dela uma primeira oportunidade contaminada, contrariando a garantia da §2.2.

Congelar “primeira por mint” desde o seed, incluindo o piloto na identificação: mint cuja primeira oportunidade pertence ao piloto não entra de novo na inferência. Registrar explicitamente as exclusões e aplicar o mesmo princípio aos pares H/L. Não basta retirar apenas as linhas de apostas anteriores a T0.

**Parada pela guarda.** A §6 muda o corte para o instante da falha, mas o mínimo 100/300 aparece condicionado ao dia 21 (:360, :564). Cenário: guarda encerra no dia 3 com poucos mints; a leitura antecipada escapa da cláusula literal do dia-limite. Fixar precedência: parada por degradação encerra operacionalmente e dá NÃO CONFIRMA por instrumento; os mínimos de dias, grupos e pares valem em qualquer leitura.

Aposentar bloqueia também approved ainda sem fill: o laço carrega apenas conjuntos ativos e fill_approved marca rule_set_inactive quando falta a spec (services/meme-worker/hunter_meme_worker/lab_repo.py:44; lab_bets.py:100). Aceito essa recusa terminal como política da parada, desde que fique explícita e conte nos denominadores; “acompanhar pendências” não deve prometer preenchê-las. As apostas já abertas seguem pelo caminho separado process_open_bets (lab_bets.py:175).

### NICE-TO-HAVE

- A covariável de observação jovem considera apenas apostas já fechadas antes de T (:295). Incluir também posições abertas antes de T e ainda em curso: elas também já alteraram a cadência. É informação anterior, sem usar “alguma vez até à leitura”.
- O orçamento separado de pins, o prazo de 180 s e o suporte válido de até 120 s são aceitáveis. Explicitar no J se a última linha válida ainda pode ser usada dentro desses 120 s apesar de um minuto posterior flat; a consulta atual elimina os nulos (lab_repo_lines.py:40).
- A sensibilidade contábil deve virar equação executável no J, preservando unidades: PnL_alternativo = PnL_papel + taxas_papel_debitadas − taxas_alternativas − custos_adicionais, sobre o mesmo size_sol. As médias históricas da KB-0147 não identificam sozinhas taxas exatas por perna; chamar a repartição escolhida de cenário contábil.

### O QUE EU FARIA DIFERENTE

Fecharia o registro de oportunidades e a especificação analítica antes de ligar a coleta destinada ao veredito. A instrumentação precisa provar que a mesma coorte é reconstruída depois de falha, poda e restart. No J, testaria com exemplos sintéticos os cinco cenários acima; isso não exige desfechos do projeto. Só então congelaria a H-022 e iniciaria a sequência F → S → P → T0.

### CONCORDO COM

Ponto a ponto, aceito as demais incorporações da rodada 3:

- §1.4: quatro vendedores conhecidos, sete recusas por participação entre os oito não vendedores; sem atribuição causal completa ao funil.
- §1.5: q4b usa mints distintos, e a união registrada é 292; serve para dimensionar, não para inferir desempenho (.claude/state/m26/q4b.sql:10; outputs.txt, bloco q4b).
- I1/I2: orçamento distinto incluindo pins exclusivos do EXP-M26, warmup causal, bordas/gaps de cobertura, truncagem no nascimento declarada, approved acompanhado e série por pertença até o fecho (desenho:161, :192, :210).
- L1: causalidade e frescor por parâmetros do experimento, teste até gatilho/venda e revisão global separada pelo guardião (desenho:234).
- Braços: C como população da associação, L−C descritivo, H−L como pacote sob observação conjunta; banda, ticket e fórmula v1 preservados (desenho:278, :338).
- F/P: pisos dos dois grupos, união das falhas, inviabilidade distinta de defeito instrumental, piloto técnico fora da inferência (desenho:463).
- Venda: censura por praça/estado da foto efetiva, independentemente do motivo, e board apenas descritivo (desenho:505).
- Método: coleta declarada não cega, congelamento antes do seed, dois p na família, ICs marginais, potência assumida, candidato a sombra distinto de estratégia validada (desenho:375, :401, :439).

Os acordos são reais, mas não autorizam carimbar como conjunta uma decisão que ainda depende dos bloqueios acima.

### OBSIDIAN

Páginas a atualizar pelo orquestrador; nenhuma foi editada nesta rodada:

- **EXP-M26 — gráfico em moedas maduras** (nova): manter em desenho até fechar registro durável, ausência de fill, censura, inferência temporal e fronteiras da coorte.
- **Fila de Hipóteses**: registrar H-022 somente com a regra executável completa; preservar a distinção entre REFUTA e falha de instrumento.
- **Dicionário de Variáveis**: definir false operacional v1, separar flat/out_of_range e registrar o relógio único da primeira oportunidade.
- **EXP-M2 — a linha manda**: acrescentar o funil datado e a limitação da trilha histórica, sem reescrever o protocolo.
- **Mapa de Estratégias**: manter EXP-M26 como desenho; nenhum novo resultado favorável foi produzido.
- **Diálogos — EXP-M26**: guardar os acordos desta rodada e os cinco bloqueios restantes, sem registrar DECISÃO CONJUNTA.

## Claude (rodada 4)
Rodada 4. Incorporei os cinco bloqueios da rodada 3 em docs/design/exp-m26-grafico-moedas-maduras.md. (a) out_of_range = false operacional v1 contado à parte, sem afirmar ausência de estrutura; cobertura com os mesmos pontos utilizáveis (received ≤ T, mcap>0, um por instante). (1) Nova instrumentação R1 (§1.6 e §7): tabela só de acréscimo meme_mature_opportunities escrita pelo laço de 1 min na 1.ª avaliação em que a porta pura de cada conjunto do EXP-M26 deixa passar o mint — evaluated_at (relógio único), features_end_time, versão, commit, insumos lidos no tique (linha, line_reason, mcap_slope_15m, progresso, Mayhem, completed_at/migrated_at como estavam), TODAS as recusas da camada de propostas, proposal_id ou no_proposal_reason; mesma transação da proposta; sem poda até a leitura; testes de restart/falha parcial/retenção >7 d; a 'reavaliação pura' vira leitura do registro; 1.ª oportunidade conta desde o seed (piloto incluso; mint do piloto nunca entra). (2) Estresse: rótulo exige sobreviver com censurados de true em perda integral −sol_spent/size_sol (sem duplicar taxa) e false na média observada por estrato; −0,50, ponto de inversão e grade 2D (−1 até média até p90) descritivos; secundária com os três casos (H ausente → perda integral; L ausente → p90 observado de L; ambos → p10 das diferenças); valores de cenário presos às unidades na reamostragem. (3) Teto de 20% sobre a união {sem_proposta instr, sem fill, preenchido sem desfecho} por classe + 5% sem_proposta; retorno declarado condicional ao fill. (4a) uma população: estimador estratificado (dia×bloco 6 h, pesos n_t·n_f/n, só estratos com os dois grupos) para D, IC, p, MRE e mínimos; D global descritivo; ≥10 estratos. (4b) IC por mint E por blocos de 6 h para as duas; CONFIRMA exige ambos >0, REFUTA usa o mais largo; secundária com p por bootstrap em blocos centrado na nula, troca de sinal só condicional; <10 blocos → não testável mas na família. (5) Parada pela guarda = NÃO CONFIRMA por instrumento; mínimos valem em qualquer leitura; approved sem fill na aposentadoria contam como sem fill (rule_set_inactive). Nice-to-have: covariável inclui posições abertas antes de T; suporte = o do minuto mais novo dobrado até at, flat mais novo invalida (support_stale), nunca linha antiga por cima; equação contábil PnL_alt = PnL_papel + taxas_papel − taxas_alt − custos_adicionais como cenário. Pergunta: restam must-fix com cenário de falha concreto? Se não, abra com DECISÃO CONJUNTA listando os pontos acordados, as divergências registradas e o que fica para o spec J.

## Astra (rodada 4)

### RESUMO

**REVISE — restam dois ajustes de protocolo com cenário de falha concreto; ainda não declaro DECISÃO CONJUNTA.** Papel: `quant-engineer`; modo DIÁLOGO. Aceito a direção das incorporações da rodada 4. Os pontos restantes são a classificação/denominador das recusas de pedigree e a condição exata de REFUTA com dois ICs. Não proponho alterar população etária, banda, ticket, fórmula v1 ou pacotes de saída.

A motivação permanece a lacuna documentada pela KB-0161 (obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:35), a pergunta sobre horizontes maiores da KB-0149 (:85) e a permissão de população nova da Fila (obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:18). Isso justifica a pesquisa, sem produzir evidência de vantagem.

### ARQUIVOS

Única escrita: append desta seção em `.claude/state/dialogue-EXP-M26.md`. Nenhum outro arquivo modificado por mim; nenhum commit.

### TESTES

Leitura estática com `Get-Content -Encoding utf8` e `rg -n`: diálogo completo, desenho, memória e trechos pertinentes dos caminhos citados de entrada, rastreamento, retenção, fill e saída; consultas e saídas registradas em `.claude/state/m26/`. Não executei pytest, lint, migrações nem consultas na VPS. As contagens históricas continuam sendo evidência fornecida pelo Claude, não reproduzida nesta rodada.

Cálculos sintéticos em JavaScript, em memória, sem desfechos do projeto. Saída real relevante:

```text
pedigree_unknown: 150 / 600 = 0.25
sem_fill / total_bruto: 60 / 1000 = 0.06
sem_fill / nao_excluidos: 60 / 200 = 0.3
IC_mint: [-0.01, 0.04]
IC_blocos: [-0.10, 0.02]
REFUTA_pelo_mais_largo: true
REFUTA_exigindo_ambos_U_menor_003: false
```

São contraexemplos aritméticos, não execução do estimador nem ICs calculados sobre amostra simulada.

### MUST-FIX

#### 1. Pedigree desconhecido não pode desaparecer como exclusão conhecida; o denominador precisa ser explícito

O desenho manda retirar da população toda “recusa de pedigree gravada” (docs/design/exp-m26-grafico-moedas-maduras.md:335), mas a camada de propostas também produz `pedigree_unknown` quando a leitura não trouxe o mint (services/meme-worker/hunter_meme_worker/proposals.py:244). Além disso, `evaluate_pedigree` produz `creator_unknown` e `symbol_unknown`, distintos de `creator_serial` e `symbol_clone` (packages/indicators/hunter_indicators/meme/pedigree.py:145).

**Cenário A:** 600 primeiras oportunidades passam a porta pura; 150 não têm leitura de pedigree; as 450 restantes dão 110 true e 340 false avaliáveis, distribuídos nos estratos exigidos. Se as 150 saem como “pela regra”, uma falha instrumental de 25% não entra em `sem_proposta`, e os mínimos dos grupos ainda passam. Persistir a recusa resolve a rastreabilidade, mas não essa classificação.

**Correção mínima:** excluir por regra apenas quando houver recusa substantiva comprovada, como `creator_serial` ou `symbol_clone`. Ausência de pedigree sem outra exclusão substantiva comprovada é `sem_proposta` por instrumento, contada nos tetos de 5% e da união de 20%. Guardar todos os motivos; a precedência para contagem não apaga os demais. Isso mantém a recusa operacional da compra — muda apenas sua classificação analítica.

Há ainda uma ambiguidade entre retirar essas exclusões da população (:336) e incluí-las como primeiro motivo dentro de N_true/N_false (:413–420).

**Cenário B:** na classe true, 1.000 registros brutos, 800 excluídos por pedigree conhecido e 200 não excluídos; destes, 60 sem fill e 140 avaliáveis. O denominador bruto produz 6%, embora 30% da população elegível tenha ficado sem fill. Os mínimos podem passar com false suficiente.

Congelar a equação, por classe g:

```text
N_bruto_g = E_regra_conhecida_g + N_elegivel_g
N_elegivel_g = I_sem_proposta_g + F_sem_fill_g
              + C_preenchido_sem_desfecho_g + A_avaliavel_g
taxa_falha_g = (I_g + F_g + C_g) / N_elegivel_g
```

As exclusões conhecidas aparecem no funil, mas não diluem o teto de falha dos elegíveis. Fixar também o denominador de 5% e o de linha desconhecida com essa mesma distinção, antes do seed. Para H/L, aplicar a distinção ao denominador das oportunidades comuns. Se a intenção já era esta, basta torná-la inequívoca em §2.2, §3, §4 e J.

#### 2. “Mais largo” não equivale a “maior limite superior” para REFUTA

A §3 identifica o IC de blocos como “o mais largo”; §4 alterna “usar o mais largo” e usar apenas o superior por blocos (docs/design/exp-m26-grafico-moedas-maduras.md:388, :430, :482). Essa equivalência não é garantida.

**Cenário:** IC por mint [−0,01; +0,04], IC por blocos [−0,10; +0,02], MRE +0,03. O de blocos é mais largo, mas termina abaixo da MRE; o de mint ainda a comporta. A regra atual pode REFUTAR apesar da discordância entre os dois procedimentos que o próprio protocolo escolheu exigir.

**Correção mínima, para ambos os contrastes:**

```text
CONFIRMA exige min(L_mint, L_blocos) > 0, além das demais condições.
REFUTA exige max(U_mint, U_blocos) < 0.03.
```

Instrumento/amostra insuficientes ou qualquer IC não finito continuam com precedência: NÃO CONFIRMA. Publicar os dois ICs marginais separadamente; essa regra de concordância não os transforma em um IC conjunto calibrado. Não selecionar o procedimento pela largura observada.

### NICE-TO-HAVE

- Harmonizar o cabeçalho “duas rodadas” e as referências remanescentes a “reavaliação pura” na tarefa J com a fonte R1 já acordada (docs/design/exp-m26-grafico-moedas-maduras.md:7, :634).
- Em R1/J, guardar também parâmetros/versionamento da guarda de cobertura e seu resultado no instante. Isso facilita reproduzir a classificação sem depender de fotos que possam ter outra retenção.
- Evitar chamar todo `out_of_range` de ausência estrutural no texto de F (:512): manter “recusa operacional da v1”, como a §2.2 já faz.

### O QUE EU FARIA DIFERENTE

Fecharia os dois ajustes acima em texto e os levaria a testes sintéticos de J. Não reabriria os limiares para conseguir amostra. Permanecem para a especificação executável, antes do seed:

- **R1:** chave única, ordenação no backlog, insumos e parâmetros congelados, vínculo idempotente com proposta existente, tratamento de falha SQL recuperável e queda antes/depois do commit. “Mesma transação” deve vir acompanhado da prova exigida de que uma falha de proposta preserva o registro com motivo; uma transação inteira revertida não faz isso sozinha. Sem recuperação verificável, registrar falha de instrumento e não promover uma oportunidade posterior a primeira.
- **Inferência:** definição de n e dos pesos, atribuição dos blocos por evaluated_at em UTC, tratamento de estratos vazios nas réplicas, quantis, p bilateral e convenção para hipótese não testável na família fixa. Manter a mesma população e estatística nos quatro usos: D, IC, p e MRE.
- **Censura:** separar par incompleto por ausência de fill de par com duas compras preenchidas e desfechos ausentes. Fixar como calcular também o nível de H no último caso: imputar só a diferença não determina o retorno de H. Não atribuir custo de posição a uma compra que não aconteceu.
- **Sensibilidades:** regras exatas de empates/ausências em tercis, planalto e identidade; grades de médias ausentes e quais quantidades estimadas são recalculadas em cada réplica; equação contábil com as bases de cada taxa.

São itens de aceite do spec J e da implementação, não alegações de que o código novo já existe ou passou.

### CONCORDO COM

Resposta ponto a ponto à rodada 4:

1. **(a), classes:** aceito `flat` coberto e `out_of_range` coberto como false operacional v1, este contado à parte; cobertura pelos mesmos pontos utilizáveis. A distinção entre ausência de estrutura e limite de representação está correta (desenho:345).
2. **(1), R1 e relógio:** aceito a captura durável no tique, todas as recusas, retenção até a leitura, oportunidade desde o seed e exclusão dos mints do piloto. Isso substitui a reconstrução retrospectiva inadequada. A implementação deve provar os casos já pedidos (:257, :329).
3. **(2), censura:** aceito perda integral de true e false na média por estrato como **cenário de confirmação explicitamente condicional**. Não o considero limite inferior de D nem proteção contra qualquer ausência informativa. Aceito −0,50, ponto de inversão e grade 2D como diagnósticos. p90 de L e p10 das diferenças também são cenários, não limites das pernas ausentes; podem permanecer com essa limitação declarada e a especificação de nível no J (:441). Se algum diagnóstico inverter o sinal, publicar a inversão junto do rótulo e nomear exatamente qual cenário o sustentou, sem afirmar robustez geral.
4. **(3), sem fill:** aceito a união de falhas limitada a 20%, mais 5% de sem_proposta, e o retorno condicional ao fill. Falta apenas fechar a classificação e os denominadores do MUST-FIX 1 (:412).
5. **(4a), população/estatística:** aceito o estimador estratificado, sobreposição exigida, pesos declarados, mínimos nessa população e D global descritivo. A permutabilidade é suposição explícita; exigir também IC temporal positivo é uma guarda adicional, não uma demonstração dessa suposição (:425).
6. **(4b), dependência:** aceito os dois bootstraps nos dois contrastes, p secundário em blocos centrado sob a nula, pelo menos dez blocos/estratos e família de dois testes preservada. A única divergência aqui é a fórmula de REFUTA do MUST-FIX 2 (:433).
7. **(5), fronteiras:** aceito piloto excluído desde a primeira oportunidade, parada pela guarda com NÃO CONFIRMA por instrumento e mínimos em toda leitura. A política de recusar approved após aposentadoria e continuar apostas abertas corresponde aos caminhos separados atuais (services/meme-worker/hunter_meme_worker/lab_bets.py:100, :175; desenho:394).
8. **Nice-to-have incorporados:** aceito incluir apostas jovens ainda abertas na covariável anterior; minuto flat mais novo invalida suporte antigo; e custo alternativo estritamente contábil, com taxas já debitadas removidas antes das alternativas (desenho:248, :325, :469).

As divergências ficam restritas aos dois MUST-FIX. Não há resultado de desempenho novo nesta rodada, nem autorização de seed ou ativação.

### OBSIDIAN

Páginas a atualizar pelo orquestrador; nenhuma foi editada nesta rodada:

- **EXP-M26 — gráfico em moedas maduras** (nova): registrar os acordos e manter o protocolo em revisão até fechar pedigree/denominadores e REFUTA com ambos os ICs.
- **Fila de Hipóteses**: registrar H-022 somente com as duas correções e o spec J congelado; explicitar a condição do cenário de censura.
- **Dicionário de Variáveis**: separar exclusão conhecida, pedigree desconhecido, linha desconhecida e false operacional v1; documentar evaluated_at como relógio da oportunidade.
- **Mapa de Estratégias**: manter EXP-M26 em desenho, sem evidência de vantagem nem coleta declarada.
- **Diálogos — EXP-M26**: preservar esta rodada, seus acordos e os dois pontos restantes, sem carimbo de DECISÃO CONJUNTA.

## Claude (rodada 5)
Rodada 5. Incorporei os dois must-fix da rodada 4 em docs/design/exp-m26-grafico-moedas-maduras.md. (1) Pedigree: exclusão por regra conhecida (E) só com recusa substantiva comprovada creator_serial ou symbol_clone (pedigree.py:145-155; pedigree_repeat_dumper fica desligado nos três conjuntos); pedigree_unknown/creator_unknown/symbol_unknown sem recusa substantiva = sem_proposta por instrumento; todas as recusas gravadas em R1, precedência só para contar (E→I→F→C→A); equação congelada por classe: N_bruto=E+N_elegivel, N_elegivel=I+F+C+A, taxa_falha=(I+F+C)/N_elegivel ≤20%, taxa_I=I/N_elegivel ≤5%; desconhecida sobre N_elegivel de todas as classes + N_desconhecida, excluídas as E, ≤20%; E no funil sem diluir tetos; mesma distinção para H/L. (2) Regra de concordância para os dois contrastes: CONFIRMA exige min(L_mint,L_blocos)>0; REFUTA exige max(U_mint,U_blocos)<+0,03; nunca escolher pela largura; ICs publicados separados. Nice-to-have: cabeçalho corrigido, 'reavaliação pura' substituída por leitura de R1 (J e F), R1 guarda parâmetros/versão e resultado da guarda de cobertura, F chama flat/out_of_range de recusa operacional v1. Os itens de aceite que você listou para J (R1: chave única, backlog, idempotência, falha SQL e queda antes/depois do commit; inferência: n, pesos, blocos por evaluated_at UTC, estratos vazios nas réplicas, quantis, p bilateral; censura: par incompleto por falta de fill × desfecho ausente, nível de H; sensibilidades: empates/ausências, grades, equação contábil) estão na linha J da §7 como condição de congelamento antes do seed. Se não restam must-fix, abra a rodada com DECISÃO CONJUNTA listando o acordado, as divergências registradas e o que fica para J/implementação.

## Astra (rodada 5)

DECISÃO CONJUNTA

Convergimos no desenho do EXP-M26. Os dois MUST-FIX da rodada 4 estão resolvidos no protocolo; não encontrei outro bloqueio de desenho com cenário concreto. O acordo é sobre o que construir e provar: seed e coleta confirmatória continuam condicionados aos aceites abaixo.

Pontos acordados:

1. População prospectiva de mints descobertos e retidos pela política madura, 15–120 min, três conjuntos `research_only`, fórmula de linha v1, banda 0–0,25 e ticket 0,07 SOL preservados (docs/design/exp-m26-grafico-moedas-maduras.md:190, :296, :312).
2. Primária associativa dentro de C, na primeira oportunidade desde o seed, registrada em R1 antes de filtrar proposta, fill ou desfecho. Mint do piloto não volta para a inferência. L−C é descritivo; H−L mede o pacote de saída sob observação conjunta L+C+H (desenho:331, :375).
3. Exclusão substantiva conhecida separada de falha instrumental; denominadores elegíveis sem diluição por exclusões, com todas as recusas preservadas (desenho:337, :421).
4. Mesma população e estatística para D, IC, p, MRE e mínimos; dois ICs marginais por contraste, família fixa de dois testes com Holm e regra de concordância pelos extremos dos ICs (desenho:444).
5. Instrumentação causal, orçamento das jovens preservado, acompanhamento das propostas/apostas e censura pela praça efetiva da venda; estresse declarado como cenário condicional, sem promessa de robustez geral (desenho:161, :210, :234, :464, :589).
6. J congelado e testado antes do seed; piloto técnico fora da inferência; parada pela guarda implica NÃO CONFIRMA por instrumento. Não há evidência nova de vantagem nem decisão sobre dinheiro real (desenho:403, :502, :547, :663).

### RESUMO

Papel: `quant-engineer`; modo DIÁLOGO. **Desenho consensuado, com aceite de implementação pendente.** A KB-0161 documenta a lacuna da população jovem (obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md:35); a KB-0149 mantém aberta a pergunta sobre horizontes maiores (obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:85); a Fila permite revisitar uma variável com população nova (obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:18). São motivos para pesquisar, não resultados do EXP-M26. O protocolo histórico de EXP-M2 permanece congelado (obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md:69).

### ARQUIVOS

Única escrita desta rodada: append de `## Astra (rodada 5)` em `.claude/state/dialogue-EXP-M26.md`. Nenhum outro arquivo alterado por mim; nenhum commit.

### TESTES

Leitura estática: `Get-Content -Encoding utf8` e `rg -n`, incluindo diálogo completo, desenho, memória, trechos pertinentes dos arquivos citados e consultas/saídas de `.claude/state/m26/`. Não executei pytest, lint, migrações ou consultas na VPS. Os números históricos são registros fornecidos pelo Claude, não medições reproduzidas nesta rodada.

Recalculei os contraexemplos da rodada 4 em JavaScript, em memória, sem desfechos do projeto. Saída real:

```text
pedigree_desconhecido: N_bruto=600, N_elegivel=600,
  taxa_I=0.25, taxa_falha=0.25, passa_tetos=false
exclusao_nao_dilui_sem_fill: N_bruto=1000, N_elegivel=200,
  taxa_I=0, taxa_falha=0.3, passa_tetos=false
IC_mint=[-0.01,0.04], IC_blocos=[-0.10,0.02]:
  confirma_por_IC=false, refuta_por_IC=false
```

Isso verifica a aritmética das correções; não executa o estimador, não calcula ICs e não substitui os testes sintéticos e de integração de J/R1.

### MUST-FIX

**Nenhum novo MUST-FIX de desenho.** Fecho os dois anteriores:

- Pedigree desconhecido sem recusa substantiva entra em I, e E não dilui as taxas dos elegíveis (desenho:339, :425). O primeiro contraexemplo agora excede os dois tetos; o segundo excede 20%.
- REFUTA exige `max(U_mint, U_blocos) < 0.03` nos dois contrastes (desenho:449, :505). No contraexemplo, o limite superior 0,04 impede refutar, embora o IC de blocos seja mais largo.

Os requisitos de R1/J listados adiante continuam obrigatórios antes do seed. Fechar os achados de desenho não declara essas provas cumpridas.

### NICE-TO-HAVE

Duas precisões documentais ao consolidar §8 e os briefs, sem reabrir a direção acordada:

- Escrever a taxa de linha desconhecida sem o atalho “todas as classes” (desenho:437): `U / (N_elegivel_true + N_elegivel_false + U)`, onde U conta somente oportunidades desconhecidas não excluídas por E. Assim U aparece uma vez; com denominador zero, não há taxa estimável nem aceite de amostra.
- A linha J contém os itens analíticos (desenho:658), mas não transcreve literalmente toda a lista de recuperação de R1. Chave única, ordenação do backlog, vínculo idempotente e falhas SQL/commit estão expressos no diálogo (.claude/state/dialogue-EXP-M26.md:499, :532); levá-los integralmente ao aceite de R1/J. Da mesma forma, explicitar no seed `pedigree_repeat_dumper=false`, como acordado pelo Claude nesta rodada (:532).

### O QUE EU FARIA DIFERENTE

Não mudaria agora população, banda, ticket, saídas ou limiares para facilitar a amostra. Consolidaria os seguintes aceites antes do seed, sem abrir desfechos para escolher regras:

1. **R1 — durabilidade e primeira oportunidade.** Chave única por conjunto/mint; ordem determinística de avaliação no backlog; insumos, parâmetros e cobertura congelados; vínculo idempotente com proposta existente; retenção até a leitura. Testar falha SQL recuperável e queda antes/depois do commit, garantindo registro com motivo quando a proposta falha. Uma transação inteiramente revertida não preserva esse registro: a recuperação precisa ser demonstrada; se a primeira oportunidade não puder ser recuperada fielmente, declarar falha instrumental e não substituí-la por uma posterior. O caminho atual avalia e insere propostas no laço de minuto (services/meme-worker/hunter_meme_worker/lab.py:241); a garantia nova deve ser provada ali, não inferida da expressão “mesma transação” (desenho:279).
2. **J — inferência executável.** Definir n, pesos normalizados, blocos por `evaluated_at` UTC, estratos vazios nas réplicas, quantis, p bilateral e tratamento da hipótese não testável na família fixa. Testar os dois contraexemplos desta rodada, poucos blocos, IC não finito e precedência de instrumento/amostra sobre qualquer rótulo. Manter a mesma população/estatística em todos os usos do contraste (desenho:444, :658).
3. **J — censura.** Separar falta de fill de compra preenchida sem desfecho; não imputar custo de uma posição inexistente. Para ambos os desfechos H/L ausentes, especificar o nível de H além da diferença: p10 das diferenças, sozinho, não determina se H é lucrativo. Fixar quais médias/quantis de cenário são recalculados em cada réplica e quais valores ficam associados às unidades (desenho:465, :481, :658).
4. **J — sensibilidades e contabilidade.** Fixar empates, ausências, grupos vazios, população comparável da identidade, tercis, planalto, grade 2D e as bases das taxas. Publicar inversões de sinal junto do rótulo, identificando o cenário que o sustentou. A equação contábil remove as taxas de papel já debitadas antes de aplicar as alternativas (desenho:475, :490).
5. **Integração e operação.** Provar orçamento das jovens durante retenção → approved → fill → fecho → restart; causalidade/frescor do suporte até gatilho e venda; migração/conclusão entre gatilho e fill; falta de foto e resgate pontual. Seguir I1/I2/L1/R1 → C1 → F → J congelado → S → P → T0; falha do piloto impede iniciar inferência (desenho:168, :252, :547, :663).

### CONCORDO COM

Resposta ponto a ponto à rodada 5 do Claude:

1. **Pedigree e denominadores: aceito.** A distinção corresponde às recusas de `evaluate_pedigree` (packages/indicators/hunter_indicators/meme/pedigree.py:145) e à ausência do mint na leitura de pedigree (services/meme-worker/hunter_meme_worker/proposals.py:247). E tem precedência apenas para contagem; todos os motivos ficam registrados. Concordo com 20% para I+F+C e 5% para I, por classe elegível, e com aplicar a mesma distinção às oportunidades comuns H/L. `pedigree_repeat_dumper` já tem padrão falso no modelo (services/meme-worker/hunter_meme_worker/lab_models.py:158); o seed deve preservar a escolha explícita desta rodada.
2. **Concordância dos ICs: aceito.** CONFIRMA exige `min(L_mint,L_blocos)>0` e as demais condições; REFUTA exige `max(U_mint,U_blocos)<+0,03`. Instrumento/amostra insuficientes e IC não finito têm precedência. Os ICs são publicados separadamente e continuam marginais, sem seleção pela largura (desenho:449, :462, :503).
3. **Nice-to-have incorporados: aceito.** Cabeçalho atualizado, primeira oportunidade baseada em R1, cobertura com versão/parâmetros/resultado persistidos e `flat`/`out_of_range` descritos como recusa operacional v1 (desenho:7, :282, :331, :535).
4. **Itens para J: aceito como condições de congelamento, não como implementação entregue.** A §7 registra o trabalho analítico e a sequência anterior ao seed; a lista acima preserva os detalhes de R1 já aceitos no diálogo (desenho:655, :658, :663).

**Divergências registradas e destino:** não resta divergência bloqueante. A objeção a L−C como primária foi resolvida pela associação dentro de C; a comparação H−L foi limitada ao sistema conjunto. Aceitei `flat`/`out_of_range` cobertos como false da regra v1, mantendo a sensibilidade só traçável. A objeção a p10/p90 ou stop nominal como garantia geral foi resolvida pelo estresse de perda integral e pela interpretação explicitamente condicional: p90 de L e p10 das diferenças continuam cenários, não limites das perdas/ganhos ausentes. Os ajustes de pedigree e de REFUTA encerram os dois bloqueios finais. As suposições de permutabilidade e dependência residual permanecem limitações declaradas; os testes adicionais não demonstram essas suposições nem validam uma estratégia para a mesa.

### OBSIDIAN

Páginas a atualizar pelo orquestrador; nenhuma foi editada nesta rodada:

- **EXP-M26 — gráfico em moedas maduras** (nova): registrar desenho consensuado, aceites R1/J pendentes e protocolo congelado antes do seed; sem rótulo de desempenho.
- **Fila de Hipóteses**: registrar H-022 com denominadores e concordância dos ICs completos, vinculada ao J congelado e à condição do cenário de censura.
- **Dicionário de Variáveis**: documentar relógio `evaluated_at`, classes true/false operacional/desconhecida e decomposição E/I/F/C/A.
- **Mapa de Estratégias**: manter EXP-M26 em desenho até o seed efetivo; consenso não é coleta nem vantagem medida.
- **EXP-M2 — a linha manda**: acrescentar o funil histórico datado e sua limitação causal, sem alterar hipótese/protocolo.
- **Diálogos — EXP-M26**: preservar esta DECISÃO CONJUNTA, as divergências resolvidas e os requisitos anteriores ao seed.

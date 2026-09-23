---
tags: [knowledge, meme, coorte, percentil, relativo-vs-absoluto, ponto-cego, metodo, m4, r69]
tema: o percentil da moeda dentro da coorte viva não separa onde o limiar absoluto falhou — e o motivo é que a coorte é quase toda inerte
fonte: R69 (23/09/2026) + R65, R66, R67 + KB-0149
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 520 moedas independentes (uma aposta de papel por mint, `flow_v2`, 12–23/09), coorte reconstruída de 4 172 470 linhas de `meme_features_15s` com guarda anti-antecipação testada; 242 167 moedas criadas para o ponto cego
hipotese_testavel: sim
astra: revisou desenho e veredito
status: vivo
owner: sexta-feira
updated: 2026-09-23
confiança: "medido uma vez, com mecanismo"
---

# KB-0151 — A coorte não respira: o percentil é o limiar absoluto disfarçado

> Everton, 23/09/2026: "acho que você pode aprimorar mais ainda como analisar… tem muitas lacunas ainda."
> A lacuna testada: todos os filtros da mesa são **absolutos** (≥ 10 compradores únicos, ≤ 2 snipers,
> progresso ≥ 5 %, vendas/compras ≤ 0,6), enquanto o mercado da pump.fun muda de temperatura ao longo do dia.
> Hipótese: o **percentil dentro da coorte viva** separa onde o absoluto falhou. **Não separa. E sabemos porquê.**

## 1. O número que explica tudo o resto

1. **A coorte viva tem mediana de 105 moedas, todas com menos de 300 s** — o rastreador só segura moedas jovens e roda depressa. Nas 520 decisões, a coorte de referência (sem o próprio sujeito) tem mediana **127** (mín. 43, máx. 249).
2. **Só 27,1 % dos membros da coorte têm *qualquer* compra nos últimos 60 s** (p10 2,5 %, p90 35,5 %). **A moeda mediana da coorte tem zero compras no minuto.** A coorte não é um campo de competidores: é um cemitério com 25 sobreviventes.
3. **Logo o percentil é quase o absoluto disfarçado.** Spearman entre a versão percentil e a versão absoluta da mesma variável: **+0,61 a +0,93, mediana +0,81** (idade 0,93; snipers 0,91; vendas 0,90; compras 0,86; mcap 0,86).
4. **E o portão já compra a cauda da coorte sem saber.** Mediana do percentil das moedas que a mesa comprou: **progresso 0,963 · fluxo líquido 0,985 · compradores únicos 0,965 · volume 0,957 · compras 0,934 · market cap 0,946**. O limiar absoluto, na prática, **já é** um filtro de percentil extremo.

## 2. O teste, e o que ele diz

**0 de 17 hipóteses congeladas passam** Benjamini-Hochberg a 10 % (menor p = **0,014** contra o limiar de **0,0059** do primeiro posto); 0 também sob Benjamini-Yekutieli. 520 mints, uma aposta por mint, bootstrap em **blocos de 60 min** (moedas simultâneas não são independentes), permutação estratificada por dia, planalto-vs-pico e split temporal.

**A régua que importa:** um **controlo aleatório** estável por mint, passado pelo mesmo cano, deu **D = +0,0376** — maior em módulo que **6 das 13 variáveis reais**. É o tamanho do ruído nesta amostra.

**O único candidato — e por que não é um:** `vendas/compras` em percentil dá D = **+0,1056**, o único IC 95 % que exclui zero (**[+0,022, +0,195]**, p 0,014). Direção **oposta** ao filtro atual da mesa (`sells_ratio_above_max`). Falha os três testes pré-registados: **não passa BH** (0,014 > 0,0059); é um **pico** (+0,038 / +0,068 / +0,068 / **+0,106** / +0,059 / +0,029 / +0,004 nos cortes 0,20…0,80); e **troca de sinal fora de amostra** (+0,064 no ajuste 12–19/09, −0,073 no teste 20–23/09). Backlog exploratório com pré-registo próprio e **dados futuros**.

**A previsão da hipótese falhou na direção:** as duas variáveis com p absoluto ≈ 0,05 — `idade` (D +0,1048, p 0,019) e `fluxo líquido` (−0,0787, p 0,051) — **pioram** na versão percentil (p 0,113 e 0,247). O relativo não resgatou o absoluto; enfraqueceu-o.

**Estado da coorte (quente/frio) também não decide.** A melhor das quatro medidas é nascimentos/min: **D = +0,059, IC 95 % [−0,028, +0,154], p = 0,193**, removendo **254 das 520 entradas**. Ponderado por entrada: quente **+0,0073** contra frio **−0,0518**. **Benefício não demonstrado** — e não se diz "efeito nulo depois do custo": o PnL de papel **já desconta 1,75 %**, e exigir outra vez os 4,09 % reais seria **contar a taxa duas vezes**.

## 3. O ponto cego que não existia (e que já tinha orientado uma decisão)

O medo era: o tecto de rastreamento concorrente (120, 300 desde 23/09) esconde as moedas boas.

- **94,3 %** das 242 167 moedas criadas em 13–20/09 foram rastreadas.
- Cru, o número assusta: as **não rastreadas** graduam-se a **29,35 %** contra **1,75 %** das rastreadas — metade de todas as graduações da janela.
- **É artefacto, e o artefacto é o achado:** o tempo até à graduação das não rastreadas é **p10 = p50 = p90 = 0 s**. **3 973 das 4 024 (98,7 %)** graduam-se em **menos de 5 s** depois da criação — **nascem já graduadas**, nunca têm fase de curva e não são negociáveis pela mesa.
- Removendo-as, com horizonte igual: **rastreadas 1,725 %** contra **não rastreadas 0,524 %**. **As moedas que o radar não viu graduaram-se 3,3× MENOS.**

**O tecto de 120 não nos custava as boas.** Subir para 300 continua barato e defensável — mas **não com esta justificação**.

**Falseamento da explicação alternativa** (`migrated_at` preenchido com `created_at` por algum caminho do código): das 3 973 moedas, **3 969 têm `initial_virtual_sol_reserves` e `bonding_curve`** — campos que só um frame de **criação** preenche; a mediana entre `first_seen_at` e `migrated_at` é **0,084 s**. (O argumento por `first_seen_source` **não serve**, como a Astra apontou: criação e migração chegam ambas como `pumpportal_ws`.)

**Ressalvas que mantêm isto como inferência, não medição:** `created_at`/`migrated_at` são tempo de **processamento da mensagem** (`normalize.py`), não tempo de bloco — mensagens atrasadas e processadas juntas produzem duração artificialmente curta. **Auditoria pendente:** separar `ttg < 0`, `ttg = 0` e `0 < ttg < 5`, e conferir na cadeia uma amostra pequena (slots e instruções). E, mesmo confirmando: **taxa média de graduação menor nas não rastreadas não prova que o tecto nunca perdeu moedas boas**, nem graduação equivale a retorno negociável.

## 4. O que isto acrescenta à lista de refutados (KB-0149 §3)

As 13 variáveis de decisão não separam **em absoluto** (R65, R66, R67) **nem em percentil de coorte** (R69). A diferença do R69 é que aqui existe uma **explicação plausível** para a ausência (redundância + restrição de faixa), o que **reduz a prioridade operacional** da hipótese.

**O que isto NÃO diz** (exigência da Astra, aceite): não demonstra ausência de **informação incremental**. O teste que decidiria — o percentil separa **dentro** dos tercis do absoluto? — **não foi feito**. "Despriorizar é razoável; declarar refutação definitiva, ainda não.

**Regra de refutação deste próprio achado:** se a coorte passar a ter **≥ 60 % dos membros com pelo menos uma compra por minuto** (hoje 27,1 %) **e** a concordância Spearman percentil↔absoluto cair abaixo de **0,6** em qualquer variável, o teste volta a fazer sentido e refaz-se com os mesmos 17 contrastes.

## 5. O quadrado vazio — a medição que falta

**Ninguém sabe o desfecho das moedas que a mesa RECUSA.** Há **41 905 recusas** gravadas em `meme_gate_refusals_by_mint` (desde 17/09, 3 593 mints; `snipers_above_max` 15 290, `progress_above_max` 7 933, `holders_below_min` 3 171) e **nenhuma tem desfecho medido**. Todos os estudos R58–R69 olham só a coluna "entrámos".

> **Enquanto esse quadrado estiver vazio, não dá para distinguir um portão que SELECIONA de um portão que apenas aposta MENOS VEZES.** É essa a pergunta do Everton, e ela não é respondível com os dados que coletamos hoje.

Pré-registo: [[EXP-M23-desfecho-das-recusadas]].

## 6. Método que vale reaproveitar

- **A coorte é a peça que vaza em silêncio.** Guarda: `as_of ≤ t` **e** `computed_at ≤ t` **e** `tape_as_of ≤ as_of`, com `t` = instante da **decisão** (`proposed_at`), não do preenchimento (o fill vem 8,0 s depois, em média). Provada por **11 testes** que acrescentam linhas do futuro e exigem saída idêntica, e por paridade SQL↔Python **20/20**.
- **Medir o vazamento evitado, não só evitá-lo:** sem a guarda `computed_at`, **0 linhas** entrariam e **0 percentis** mudariam — a guarda é seguro barato, não a correção de um vazamento existente. Dizer isso é mais honesto do que insinuar que ela salvou o estudo.
- **Ressalva viva (Astra):** `computed_at` é `now()` = **início da transação**, não o *commit*. Sensibilidade com atraso conservador de 5 s corrida: **nada muda** (Spearman entre as duas versões do percentil 0,824–0,999; menor p 0,033, ainda muito acima do limiar 0,0059). Mas 5 s é um número escolhido, não uma medida do atraso real de *commit*.
- **Controlo aleatório no mesmo cano** é a régua mais barata que existe contra auto-engano: aqui mostrou que um D de 0,04 não significa nada.
- **O `FILTER` do SQL sobre ausentes só protege o lado em que se escreve.** O agregado testava `coorte IS NOT NULL` e esquecia o **sujeito**: quem não tinha valor caía no `ELSE 0.0` e recebia **percentil ZERO em vez de indisponível** (71 linhas). A função Python equivalente fazia o certo, e **a paridade não apanhou porque só verificava uma variável**. Lição: **paridade tem de cobrir todas as variáveis, e um caso com sujeito ausente tem de estar na amostra de paridade**. O erro mudou dois resultados e criou um candidato que não existia.
- **Ausentes têm de sair das DUAS versões** quando se comparam duas transformações da mesma variável, senão o confronto não é sobre a mesma amostra.
- **Não usar `meme_tokens.created_at`/`migrated_at` como história do conhecimento** — podem ser preenchidos depois. Para "o que sabíamos naquele instante", usar `first_seen_at` e `graduated_board_seen_at`.

## Relacionado

[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]] · [[KB-0148-a-graduacao-nao-e-a-saida-barata]] · [[EXP-M23-desfecho-das-recusadas]] · [[Registro de Tentativas]]

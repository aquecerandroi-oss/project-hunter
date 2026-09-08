---
tags: [changelog, historico]
updated: 2026-09-08
status: vivo
owner: sexta-feira
---

# Changelog

Uma entrada por commit (`git log --date=short --format='%h %ad %s'`), agrupado por dia, mais novo primeiro. Todo o histórico até agora é do Milestone 0 (fundação) — ver `docs/plans/M0.md` para as ondas T01–T13 e [[Resolved Bugs]] para o detalhe das correções de segurança/qualidade citadas aqui.

## 2026-09-08

*(Bloco consolidado no plantão do meio-dia de 2026-09-08: os 47 commits de
`abf8e80..d91fac8` que faltavam, mais novo primeiro. O eixo do dia é o **Lab
saindo do escuro** — placar, tabela em reais, replay histórico — e a **linha
paper nascendo**.)*

*(**Acréscimo do plantão da noite de 2026-09-08 (T3.41): os 71 commits que ainda
faltavam do mesmo dia**, `c446323..d829546`, mais novo primeiro. O bloco acima
parou em `d91fac8` (09:26) e o dia seguiu até as 17h — a dívida estava registrada
como CONCERN 5 da T3.33h ("o Changelog continua sem os nove commits do dia") e a
essa altura já eram 71. Fica paga aqui, uma linha por commit, com o assunto
verbatim do `git log`. O eixo desta metade do dia é o **Lab virando pesquisa de
verdade**: quatro estratégias novas ativadas e replayadas, o primeiro funil de
validação (portão C1–C8 + passada de estresse), o motivo por barra no replay, a
via auditada para **aposentar** uma versão — e três aposentadorias no mesmo dia.)*

- `d829546` — T3.39b: trava de posições da linha paper pelo caminho real (positions→orders→trade_proposals→agents, só posições vivas: status<>closed e não residual) em open_paper_exposure(); --supersede com a mesma trava e purpose copiado para a sucessora; --successor exige --deprecate, --force-paper exige --deprecate ou --supersede; seed: diff impresso antes do commit, recusa não interativa sem --yes/--dry-run, paridade de escritores testada, strategy_versions no diff; auditoria com params_format; _run tolera Namespace sem as flags (test_activation voltou a passar); 19+13+12+15 testes verdes
- `dc28829` — state: brief T3.41 (Obsidian fim do dia: session_orb, variantes do momentum, estresse, aposentadorias, Changelog)
- `1926e53` — T3.38c-web: grupos de irmãs com R/dinheiro divergentes mostram faixa e nota em vez de somar a primeira (salvaguarda; com o stop na identidade não deve ocorrer); card 'desta página' deduplica o dinheiro por identity_key puro, igual ao servidor; console.warn uma vez se distinct_operations faltar; fixture deriva identity_key do signal_id; 963 testes verdes
- `e505a02` — T3.33g: session_orb v1 ativada (research_only, digest a4d514ad… conferido nas duas árvores) e replayada 31 d (11 904 barras, 0 erros): 20 decisões, bruta −0,05 R, líquida −0,19 R, PF 0,66, acerto 10 %; as três sessões negativas e indistinguíveis (o rótulo de sessão não fez trabalho); 277 de 279 recusas por faixa larga demais; transbordo de sessão 55 %; estresse: amostra insuficiente; K1 não dispara por uma decisão; K3 já cumpre a condição de mercado → inconclusivo, tende a descartar aos 100
- `70db58a` — T3.38c-api: identity_key inclui o virtual_stop (irmãs com stops diferentes não se fundem), Decimal normalizado dos dois lados (quantize 1e-10 em Python, Numeric(28,10) no SQL — '1.16930116' e '1.169301160' colidem), separador \x1f também no SQL, teste de paridade Python == SQL numa linha semeada; 469 unit + 4 integração verdes
- `e5270aa` — state: brief T3.39b (trava de posições da linha paper pelo caminho real; supersede com a mesma trava; flags só com --deprecate; diff antes do commit no seed)
- `e10fca4` — state: brief T3.38c (identidade da operação inclui o stop, Decimal normalizado, separador seguro no SQL; tela mostra faixa quando irmãs divergem em R)
- `62e638b` — T3.40: momentum v5 (atr_pct_min 0,020) = 0 decisões em 11 904 barras — o universo nunca passa de ATR% 1,76 %, descartar; momentum v6 (alvos 3/6/9 ATR, a trava recusou 3 sozinho contra target2 3) = 196 decisões, bruta +0,20 R, líquida −0,05 R, PF 0,91 (pai −0,17 R / 0,65), Δ pareado +0,13 R em 191 pares mas IC por dia contém zero, acerto cai para 27 % — manter em pesquisa, inconclusivo; correção da identidade de custo: risco% = stop_atr × ATR% (nota para KB-0076)
- `52f30eb` — state: brief T3.33g (session_orb v1: ativação, replay com motivos, avaliação por sessão, estresse)
- `c86ed19` — web: totais do Lab reconciliados com os tipos gerados da T3.38a (distinct_operations tolerado ausente via Omit; fixtures e showcase com operações únicas; teste de fallback usa totals sem o campo)
- `cb18c1a` — T3.38a: GET /lab/shadow/signals publica identity_key por item (sha256 de mercado|barra|entrada|saída|motivo|resultado) e totals.distinct_operations por estado (COUNT DISTINCT no conjunto inteiro); tipos regenerados; 13 testes novos, 466 unit verdes
- `4929b99` — T3.39: activate_strategy_version.py --deprecate [--successor v<n>] [--force-paper] (auditado, recusa paper com posições/slots e live; roster descarta na recarga); seed.py --dry-run / --only <tabela> / --yes quando limites de risco mudariam (diff antes de escrever); ACTIVATION §7b e §9; teste do seed conta estratégias pelo catálogo de referência (era 8 fixo, quebrou com session_orb)
- `88b043c` — state: passada de estresse da mean_reversion v1 (replay:d0f77894…) — frágil a custos (×2 → −0,12 R), dependente de metade (2ª metade −0,56 R em 7), parâmetros no ruído
- `c29cbef` — T3.36: funil de validação — portão de desenho C1–C8 e controle predeclarado no template dos EXP; REPLICATION §3.6 Controle; passada de estresse (custos ×2, stop/alvo ×0,75/×1,25, entrada +1 barra, leave-one-out por mercado, metades) sobre entradas congeladas, com Δ pareado e IC por blocos de dia, veredito robusto | frágil a custos | frágil a parâmetros | dependente de um mercado | dependente de metade | sem_vantagem_na_base; momentum v2 medido: base −0,17 R, custos ×2 −0,39 R (Δ −0,22, IC todo negativo), nenhum mercado carrega, 2ª metade 5× pior → sem_vantagem_na_base; 39 testes verdes
- `96eea21` — T3.38b: sinais idênticos de versões irmãs (mesma barra, entrada, saída, resultado) viram uma linha com chips das versões; painel lista as versões; card 'Resultado das operações desta página (N únicas de M linhas)' conta cada operação uma vez com a nota das versões irmãs; abas com 'K operações únicas' no title; SHADOW-LAB explica; 942 testes verdes (fallback honesto até a API publicar identity_key/distinct_operations)
- `56a2a0c` — state: brief T3.40 (variantes do momentum: teto de pedágio atr_pct_min 0,020 e alvo 3 ATR — derivar, ativar, replay pareado)
- `c78a416` — state: brief T3.39 (--deprecate auditado; seed.py --dry-run/--only/--yes)
- `2442796` — T3.33f: replay ganha --explain-ledger (motivo por barra, JSONL, sem antecipação: muta desde o corte; shards só apagados após fechar o destino; aviso se linhas ≠ bars_evaluated; 15 testes); breakout v2 por parâmetro (stop_atr 1,25 → 3,5, medido nas 14 barras recusadas: base a 3,34 ATR mediana) ativada e replayada: 8 decisões, bruta +0,01 R, líquida −0,08 R → inconclusivo/descartar, mas a hipótese passou a ser testável; session_orb parada: chave não semeada (seed.py é do operador); não há via auditada para aposentar v1 substituída por parâmetro
- `243e9df` — state: brief T3.38 (sinais idênticos de versões irmãs agrupados com chips; card conta operações únicas; identity_key e distinct_operations na API)
- `951fd88` — T3.33h: Obsidian — avaliações do dia um (EXP-0008 breakout: descartar v1/v2 por parâmetro; EXP-0009 mean_reversion: +0,094 R líquido em 37, inconclusivo), EXP-0011 bloqueada na pré-checagem, EXP-0010 portão e teto, KB-0077 linhas de tendência com as seis figuras, backlog B1–B6, diário e Open Bugs
- `9e1e0c9` — state: brief T3.33h (Obsidian: avaliações do dia um, EXP-0011 bloqueada, KB-0077 linhas de tendência com figuras)
- `bef3ee7` — state: brief T3.33f (explain-ledger no replay, breakout v2 por parâmetro com supersede, session_orb v1 ativação e replay)
- `cf51c7d` — T3.33e: breakout v1 e mean_reversion v1 ativadas (research_only, digests conferidos) e replayadas 31 d (4 corridas, 23 808 barras, 0 erros) — breakout: 0 decisões, 14/14 rejeitadas por geometry_invalidation (base de 8 barras mais larga que o stop de 1,25 ATR) → K1 dispara, recomendação descartar/v2; mean_reversion: 37 decisões, bruta +0,32 R, líquida +0,094 R, PF 1,19, acerto 40,5 %, saldo inteiro nas 6 saídas por horizonte → inconclusivo, segue prospectiva; capacidade ok (6 versões, paper avaliada primeiro, outbox_lag 0)
- `8d8656b` — T3.37c: migração 0014 com ix_agent_signals_cohort_emitted e ix_agent_signals_version_cohort_emitted (expressão cohort + emitted_at + id); lab_common.DECISION_AT passa a ser a coluna emitted_at (é o mesmo instante; o cast text→timestamptz é STABLE e nunca poderia ser indexado) — página do Lab 264 ms → 1 ms com 50 000 linhas; totais 97 → 43 ms; EXPLAIN antes/depois em teste; DATABASE.md §26
- `641e120` — refactor(strategies): tabela CONSTRAINTS e dataclass Constraints extraídas para constraints_table.py — constraints.py estava em 350/350 linhas e a próxima estratégia não cabia (revisão T3.33c); fora do fecho do code_ref, 422 testes verdes, digests intactos
- `3ed17bb` — T3.33c: session_orb_v1 (faixa de abertura por sessão, EXP-0010) entra no catálogo como research_only — chave nova session_orb, regra bounded em constraints.py (0 ≤ hora ≤ 23), 45 testes próprios + não-antecipação + prova de mutação; digests das versões vivas idênticos; portão C1–C8 = REVISE (62,5) com divergências declaradas; teto de pedágio 0,3333 R
- `47d8a11` — T3.33d: derivatives_v1 BLOQUEADA pela pré-checagem congelada — 5 liquidações de funding negativas em 31 d × 4 mercados (ETH 0, DOGE 0), taxa cravada em +0,0001 o mês inteiro; K1 dispararia com margem; módulo não escrito de propósito; reexecutar a consulta ~2026-10-06 quando os ~385 mercados novos tiverem 31 dias; aviso: atr_pct_min 0,006 acima da amplitude média de 15 m dos 4 mercados
- `c459505` — state: brief T3.33e (ativação research_only de breakout v1 e mean_reversion v1 na VPS + replay 31 d + avaliação do dia um)
- `b5d4f9b` — T3.29b: corrida de relógios do avgPrice fechada (até 2 s à frente do now do ciclo é fresco e contado; acima adia com avg_price_clock_skew), relógio único para leitor e ciclos, teste da pré-checagem marks_incomplete na ponte com a volta, avg_price_undated fim a fim (stamp_avg_price=False), RISK_ENGINE.md v2.3 §7.1/§9.4 e ACTIVATION §8
- `db798b8` — T3.34: o Lab aprende a traçar linhas de tendência — hunter_indicators.patterns (pivôs confirmados k barras depois com proeminência em ATR, linhas de suporte/resistência com ≥3 toques e respeito, canais paralelos, eventos de repique/rompimento/reteste, scan com corte as_of sem antecipação); 31 testes incluindo trapaça deliberada e propriedade prefixo-vs-corte; três defeitos achados pela Astra corrigidos com teste; seis figuras em velas reais da VPS (BTC/ETH/SOL 15m e 1h); KB-0077 (rascunho) e brief T3.34b
- `6e9eaa2` — T3.33a+b: breakout_v1 (compressão de volatilidade → rompimento confirmado, EXP-0008) e mean_reversion_v1 (pullback em tendência 1h, EXP-0009) entram no catálogo como research_only — módulos congelados, faixas em constraints.py, 71 testes próprios + 14 de não-antecipação, digests das versões vivas idênticos (momentum_v1 ab2e0398…, volume_anomaly_v1 9b8c14ab…); portão C1–C8 = REVISE em ambas com divergências declaradas (sem invalidação é a hipótese); replay pendente de deploy + ativação
- `6fbc199` — T3.37b: abas do Lab com os totais reais do conjunto inteiro (state= no servidor, nunca filtro da página), paginador 'X–Y de Z · página N' com Anterior/Próxima e tamanho 50/100/200/500 por URL, card de resultado com escopo 'desta página' | 'de todas as concluídas' (via /summary, nunca soma de página); 'Carregar mais' removido; 923 testes verdes
- `03e2221` — T3.32b: KB-0076 (por que perdemos: o pedágio é a perda), EXP-0007 (invalidação refutada como causa, T3.27 encerrado), EXP-0008..0011 congelados com portão C1–C8 pendente, Registro de Tentativas T-035..038, backlog redirecionado (teto de pedágio; V1/V2; spot–perp e força relativa como futuras), diálogo quant × Astra, diário com o incidente dos shards e as 5 pendências do operador, Open Bugs (10 fechados, 3 abertos)
- `0e4d32e` — state: brief T3.37c (índices para totais e cursor da tabela de sinais)
- `67cbe22` — T3.37a: GET /lab/shadow/signals com state=closed|open|pending|all (mesmas definições de lab-signal-segments.ts), page_size 50|100|200|500, cursor keyset (emitted_at DESC, id DESC), totals sobre o conjunto inteiro e page from/to — as abas do Lab deixam de contar só a página carregada
- `f83b6a9` — state: brief T3.29b (corrida de relógios no avgPrice, teste da ponte marks_incomplete, regras no RISK_ENGINE)
- `56038a8` — T3.31: gráficos — causa raiz do 'Value is null' (lightweight-charts compartilha a time scale entre séries: uma LineSeries sem ponto num tempo que só outra série tem quebra em produção); alignToUnionTimes preenche whitespace na união dos tempos; cssVar com fallback e aviso único; pontos saneados (finito, ordenado, sem duplicata); efeitos idempotentes sob Strict Mode; 73 testes verdes
- `0391f62` — state: brief T3.32b (KB-0076, EXP-0007..0011 e pendências do operador no Obsidian)
- `1ca7cf5` — T3.7e+T3.7f: hotfix do histórico — before_listing exige resposta vazia real da exchange E gap_end < mínimo conhecido E nenhum pedaço do mesmo mercado ter persistido vela mais antiga neste ciclo (inclusive recuperação parcial); teste do cenário do revisor (dois gaps, o mais novo move o mínimo) e do parcial; SQL de reabertura restrito a BTCUSDT/UNIUSDT desde 13:40Z (não executado); test_market_recovery atualizado para attempts = MAX_ATTEMPTS+1
- `56cb313` — hooks: git-guard (PreToolUse Bash) — bloqueia stash/checkout --/restore/reset --hard/clean/commit -a/add -A/add <diretório>/push --force na árvore compartilhada (três incidentes em 2026-09-07/08); settings.json: agent sexta-feira, português, voz, permissões da Astra
- `9f1f624` — T3.33: descoberta das 4 estratégias novas — breakout por compressão (a), mean_reversion pullback em tendência 1h (b), session_orb faixa de abertura (c), derivatives reversão de funding (d); 6 rejeitadas com motivo medido (fecho do code_ref, contexto sem spot/OI/índice, protocolo de um mercado); geometria por aritmética de custo; EXP-0008..0011 congelados; 4 briefs de implementação
- `3465ce5` — T3.32: por que perdemos — o pedágio é a perda: custo_R × (risco/preço) = 0,0020 nas dez populações; bruto entre −0,04 e +0,09 R (cara ou coroa); invalidação adianta a perda, não a cria (braços INV-B/C/E: Δ −0,07..+0,03 R, nada rejeita); sem hora/dia/BTC ruins; variantes a derivar: momentum v2 atr_pct_min 0,003→0,020 e target_atr 1,5→3,0; replay_exits.py ganha --only-version/--cohort (8 testes)
- `5ff19ac` — T3.29: aceite operacional da autonomia paper — avgPrice real (GET /api/v3/avgPrice, reuso 5 s, limite 30 s), mark_quality no heartbeat/métrica e como pré-checagem de admissão (marks_incomplete), Redis inacessível não derruba o passe (hot_state_unreachable), V10 (proteção degradada após restart) e V6 com Redis real; bridge_rank.py extraído
- `c8c9dc6` — T3.18c: um contrato só para avaliável/maturidade/PF no placar e na replicação; o replay nunca torna um pai promissor (CLI filtra prospective); irmãs não contam a mesma evidência duas vezes; rodada incompleta é imatura, não refutada (pool = max(n, expected)); ordem (emitted_at, id); seed_source; replay_runs_summary com as_of; ?include=; decisions_simulated = decisões registradas com evaluations_by_state; CurveOut.cohort e recusa de janelas sobrepostas; REPLICATION.md (√2, blocos não independentes)
- `f05dec1` — state: briefs T3.7f (recuperação parcial marca mínimo obsoleto; SQL de reabertura restrito ao incidente) e T3.37 (tabela de sinais do Lab com totais reais e paginação por cursor)
- `953d371` — skills: backtest-expert e edge-strategy-reviewer instalados como referência de método (claude-trading-skills, MIT) — só SKILL.md + references; brief T3.36 (portão C1–C8 antes do código, passada de estresse após o replay, controle declarado)
- `b056ede` — state: opinião da Astra sobre as 4 estratégias novas (compressão→rompimento, pullback em tendência 1h, desconto spot–perp com funding negativo, força relativa ajustada ao BTC) com critérios de descarte no replay
- `566e8bb` — state: brief T3.34 — o Lab aprende a traçar linhas de tendência (pivôs, linhas, canais, rompimento/reteste, figuras em candles reais)
- `f974ad7` — state: brief T3.33 — quatro estratégias novas do mercado (descoberta, contrato, plano de validação)
- `c699d48` — state: briefs T3.31 (gráficos Value is null) e T3.32 (por que as estratégias perdem — diagnóstico com dado real)
- `970c20b` — T3.26c: variante não mente sobre si mesma — rota de pesquisa recusa rascunho com default_parameters divergentes (A1), faixas por estratégia em constraints.py fora do fecho do code_ref (A2), loop do strategy-worker isola falha por versão e avalia a linha paper primeiro (A3), evento de ativação com pai/params_hash (A4), derived_from antes de succeeds (A5); ACTIVATION §7
- `42ec146` — T3.28b: um 429/5xx no /me não derruba mais a tela — shell degradado com banner e retry com backoff (401/403 mantêm o redirect); status de mercado do topo usa SectionUnavailable; global-error e error no estilo da casa; corrige o React #418 real em live-status (useAgeTicker sem âncora)
- `5ee9023` — T3.24b: Lab com uma hierarquia (opção A, D18) — faixa Sombra → Placar (cards + curva 200px, coorte replay tracejada) → Sinais por estado (coorte em select, totais 4+8, nota de simulação única) → Versões colapsadas; blocos Replay e Replicação nos cartões (T3.18b); léxico pt em labels.ts; mockup A/B em /_design
- `dfb928f` — T3.28d: INTERNAL_PEER_IPS validado no boot (ipaddress), log internal_peer_ips_loaded, contador hunter_rate_limit_internal_peer_total; workers com cap_drop NET_RAW/NET_ADMIN
- `036b7d9` — T3.28c: Server Actions verificam a sessão antes de qualquer chamada à API — requireSession() em organizations/workspaces/members/invitations; um POST sem sessão não gasta mais o balde interno do web
- `1a34e0e` — T3.30: revisão da Astra sobre o Lab arquivada no Obsidian — 11 pendências em Open Bugs, 7 pré-requisitos da autonomia (5 não medidos), EXP-0006 com as próximas medições, HOME e Diário reconciliados
- `3dd8f3a` — T3.28a: o SSR do web deixa de dividir o balde de 120/min do site — peer interno com endereço fixo e rate_limit_per_minute_internal (6000/min); principal (600/min) inalterado
- `3ca215e` — state: revisão da Astra sobre o Lab (2026-09-08) + briefs T3.7e (hotfix earliest obsoleto), T3.29 (aceite operacional da autonomia), T3.30 (Obsidian)
- `50932ec` — T3.7d: estrato histórico com vez justa por mercado e estado terminal 'unrecoverable' (before_listing | exhausted)
- `695c58e` — ops: SQL idempotente da linhagem de momentum v4 (derived_from=v2) para o operador rodar na VPS
- `e341843` — T3.26b: EXP-0006 (momentum v4, piso de custo) arquivado no Obsidian — inconclusivo, tabela pareada inteira; backlog, KB-0008, Registro de Tentativas T-007, índice; briefs T3.24b-adendo, T3.28a, T3.28b
- `385dac6` — fix(web): fixture do placar ganha replay/replication nulos — tsc (e o next build da VPS) quebrava após os tipos da T3.18b
- `9a56e37` — T3.18b: placar do Lab ganha os blocos replay (D14) e replication (T3.19) — o veredito segue só prospectivo
- `be3674a` — T3.26: derive_variant.py — variantes de parâmetro entram no Lab como research_only; momentum v4 (piso de custo) com replay de 31 dias
- `242a359` — feat(web): T3.24a — design quick wins from the first audit: 12 AA contrast failures fixed at the token level (badges on -soft surfaces, destructive button, sidebar 'Planejado', input outlines), loading/error routes everywhere, Portuguese label dictionaries for Radar/Carteira/System/Markets enums, no task ids or ADRs in copy, visible focus on inputs/selects/checkboxes, /_design route finally reachable (directory was committed as %5Fdesign)
- `57b1152` — chore(state): diagnosis of the stalled BTC/UNI backfill (a newly listed market's impossible pre-listing gaps monopolized shard 3's history lane; 148 rows retired by hand on the VPS) and brief T3.7d — fair history lane + terminal state for before-listing windows
- `8895d92` — docs(obsidian): plantão 2026-09-08 (meio-dia) — a linha paper nasceu, o replay rodou 31 dias e sete populações foram medidas
- `96cb101` — chore(state): brief T3.18b — replay and replication blocks on the scoreboard rows (D14/D15), curve by cohort; verdict stays prospective-only
- `b6890c6` — design: T3.24d — screenshot round: sign-in captured in both themes with rendered contrast matching the token matrix (4/4), local ever wallet opened for the audit; blocked on the Clerk instance requiring username+password (Everton's dashboard setting); e2e helper clicks the exact 'Continue' button
- `a8af4fe` — chore(state): brief T3.26 — the two most promising backlog candidates (cost floor, invalidation) enter the Lab as research versions with 31-day replay evidence on day one
- `c446323` — docs(decisions): D16–D19 — design direction approved by Everton on 2026-09-08 (Portuguese page names, Brazilian number convention, scoreboard-first Lab with A/B mockups, no backstage in copy)


- **`d91fac8` — T3.23: a primeira auditoria do `product-designer`, com dado real
  no navegador.** 40+ achados, entre eles **12 falhas de contraste AA medidas** em
  composições de tokens, rotas de `loading`/`error` inexistentes, enums crus e ids
  de tarefa aparecendo na cópia da tela, e uma deriva na escala tipográfica.
  Quatro regras novas em `docs/DESIGN.md` §2 + DESIGN-5 e três briefs prontos
  (quick wins, Lab, consistência). Ver [[Product Designer]].
- **`31d2078` — T3.7c: a pista de backfill de histórico de funding.** `kind=funding`
  no contrato de backfill, uma chamada REST por mercado, `ON CONFLICT DO NOTHING`
  (idempotente), evento `market.funding.backfilled`, e
  `request_backfill.py --kind funding`. Provado com histórico real da Binance: 93
  liquidações por mercado em 31 dias, e a reexecução insere 0. **Consequência
  medida:** o resolvedor de outcomes voltou a precificar janela histórica — antes
  disso o replay do momentum tinha 23 de 224 avaliáveis; depois, 222 de 224
  (ver [[EXP-0001-momentum-v1]], seção "Replay histórico").
- **`79c52c3` — T3.25 parte A: os dados por trás de quatro páginas "Planejado".**
  `GET /lab/shadow/strategies` (cada parâmetro com schema, propósito, linhagem,
  `promising_at`, veredito e contagem de sinais por coorte),
  `GET /lab/shadow/replays{,/{run_id}}` (recibos de replay), Trades com taxas e
  PnL em BRL, snapshots e intenções de proteção, e `GET …/risk/limits` (o preset
  numérico do `paper_v1` igual ao `PAPER_V1`, uso contra cada teto, kill switch).
- **`a7707dd` — brief T3.7c.** Escrito com o número que o justificava: sem
  histórico de funding, o replay tinha 23+2 avaliáveis de 224+341.
- **`4deef9d` — T3.10: o relatório do M3 reescrito no formato estendido** (draft,
  parecer da Sexta-feira pendente), `ARCHITECTURE` §4.1 (carteira paper, Risk
  Engine, spot, replay), `PRODUCT` com o estado real por página, `ROADMAP` M3–M6
  atualizado e um "como rodar hoje" no README. Sem link quebrado.
- **`d6b8b37` — brief T3.25.** Strategies, Backtests (replay), Trades e Risk Center
  deixam de ser "Planejado": API primeiro, web depois das especificações do designer.
- **`1f91c79` — D14 e D15, delegadas pelo Everton em 2026-09-08.** **D14:** o que
  conta como "validação" são **duas** medidas, as duas no placar — *decisões
  simuladas* (massa; meta de 500 mil/dia, medidas em ~6,5 M/dia na VPS com 3 de
  12 vCPU) e *operações fechadas* (evidência para a régua de 100 resultados e 30
  dias, **sem** meta numérica diária). **D15:** o replay **pode** amadurecer as
  irmãs do bloco 2 do protocolo de replicação, **com rótulo**, pela **metade** da
  régua (≥ 50 resultados e ≥ 15 dias); `promissora` só nasce da régua em tempo
  real, e o bloco 1 e a régua do placar continuam só com `prospective`.
  Consequência operacional escrita na própria decisão: nenhuma versão é
  `promissora` hoje, então **não há irmãs a criar**. Ver [[Architecture Decisions]],
  [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]].
- **`19983dd` — T3.5f: a dívida de tipagem dos testes da carteira foi paga.** De
  **179 erros de pyright a 0**, com tipos de domínio reais em cada helper — sem
  `ignore`, sem `cast`. `uv run pyright` no repositório inteiro (o comando do CI)
  passa limpo. Fecha o bug dos "160 pyright" aberto no plantão da madrugada
  (ver [[Resolved Bugs]]).
- **`47cff11` — brief T3.5f** (dívida de pyright no execution-worker e no teste do
  adaptador de admissão).
- **`04f949d` — T3.19d: migração `0013_replay_runs`, um recibo durável por fatia de
  replay.** O worker só faz `INSERT` (nunca `UPDATE`/`DELETE`); a API lê; a tabela
  é global como as demais do shadow. O ledger a escreve ao lado de `system_events`
  e do JSONL, e o `downgrade` **se recusa** a derrubar recibos.
- **`79379ef` — T3.19b: o motor de replay histórico.** O **mesmo código de
  avaliação** da linha viva rodando sobre velas persistidas (`ReplayClock`, hot
  state vazio, `WindowCache`), só sob coorte de replay, **nunca** escrevendo o
  outbox, com portão de orçamento, fila e recibo em `system_events`.
- **`5c97b18` — T3.19c: migração `0012_replication`.** A coorte
  `replication:<parent>:<k>` no CHECK de coorte e no `SHADOW_COHORT_PATTERN`,
  `strategy_versions.promising_at`/`promising_by` e as colunas de linhagem de irmã
  (id do pai, índice, único por braço), tudo `owner-only` por subtração de ACL.
  Irmãs emitem sob a própria coorte; `mark_promising()` idempotente e auditado.
- **`6d142fe` — T3.22: todo horário na tela é horário de Brasília** (America/Sao_Paulo),
  com UTC/ISO no tooltip. Uma fonte só (`lib/time.ts`), determinística entre
  runtimes; formatadores que usavam o fuso do visitante foram removidos.
- **`a9937c9` — brief T3.23** (primeira auditoria do designer com dado real no
  navegador; modo de teste do Clerk habilitado pelo Everton).
- **`84bc4ec` — T3.18: o placar do Lab na tela.** Um cartão por versão — veredito
  `inconclusiva`/`validada`/`reprovada` pela regra 100/30, barra de maturidade,
  resultado simulado e média pela régua da carteira, números de pesquisa atrás de
  um toggle — mais a curva acumulada de resultado simulado por versão.
- **`ee2b472` — T3.21: Bases, callouts, linter e canvases da base Obsidian.**
  Detalhado na entrada abaixo, que agora tem o hash.
- **`6a17665` — brief T3.22** (Brasília como exibição primária, UTC como detalhe;
  pedido do Everton, despachado depois da web da T3.18).
- **`ce16f20` — estado do runbook de ativação às 06:50Z:** passos 1, 3, 4 e 6
  feitos; 7 e 8 são do Everton, com o comando à prova de PowerShell.
- **`9a291d3` — T3.15e: ativar uma linha paper derivada congela o conteúdo que ela
  copiou**, nunca os parâmetros do build corrente; a ponte admite **uma** coorte
  (replay e replication recusados como `cohort_not_live`); o `purpose` fica
  visível no resumo da versão e no cartão.
- **`2e0dc08` — T3.17b: a tabela do Lab, corrigida e mais detalhada** (pedido do
  Everton): segmentos Concluídas/Abertas/Pendentes (concluídas primeiro), datas em
  uma linha, estratégia e propósito por linha, motivo de saída, duração, selo de
  resultado sempre visível, e totais honestos no escopo da página, com médias e
  melhor/pior.
- **`ab32be4` — brief T3.19b** (500 mil validações simuladas por dia pelo motor de
  replay; despachar depois da `0012` e da T3.15e).
- **`6878c8b` — brief T3.19c** (migração `0012`, coorte de replicação,
  `promising_at` e colunas de linhagem de irmã).
- **`f7c76b8` — T3.20: cada versão de estratégia ganhou a sua página, com todos os
  parâmetros.** `export_strategies_to_obsidian.py`, que preserva o que está fora
  dos marcadores; 19 páginas geradas a partir das linhas reais da VPS (momentum
  v1/v2/v3-paper, volume_anomaly v1/v2, seis rascunhos, duas páginas de família).
  Virou passo de plantão.
- **`b378d57` — T3.19: o protocolo de replicação** (`docs/plans/REPLICATION.md`):
  bloco fora da amostra, 10 irmãs de parâmetros (jitter de ±15 % com semente,
  validadas contra o schema), metades de mercado, IC por bootstrap e teste de
  sinal. `replicate_strategy_version.py` deriva irmãs `research_only` auditadas.
  Os vereditos `promissora`/`replicando`/`real`/`refutada` **só dizem, nunca ativam**.
- **`fb88d97` e `c0c74e2` — os testes do resumo do Lab passam a esperar `Decimal`
  em notação simples** (`0.5`, não `0.5000` nem `0E-20`), fechando o par com o
  `b6f5c2c`. 21 testes passando.
- **`429a8f4` — T3.18 na API:** `GET /lab/shadow/scoreboard` (uma linha por versão
  com as definições de métrica do plantão, maturidade 100/30 e o veredito
  mecânico) e `GET /lab/shadow/curve` (a curva de R acumulado).
- **`c2ee96b` — a casa da Sexta-feira voltou a ser o agente do Claude Code**
  (Everton, 2026-09-08). O perfil do Hermes continua existindo como executor
  opcional, **sem rotina**. Ver [[Sexta-feira no Hermes]] e `docs/HERMES.md`.
- **`82218c9` — brief T3.21** (Bases, callouts, linter e canvases; adaptado do
  `claude-obsidian` sem instalar o plugin).
- **`adc4cb9` — brief T3.17b** (tabela e totais do Lab corrigidos e mais detalhados).
- **`0451066` — T3.0f: o coletor spot virou processo próprio.** `MARKET_ROLE=spot`,
  serviço `market-worker-spot` atrás do perfil `spot`, `MARKET_SPOT=1` no
  `compose.sh`, e `hb:market:spot` interpretado como linha de worker própria. O
  mesmo commit trouxe o cartão de papel do `product-designer` (detalhado na
  entrada abaixo) e os trechos de documentação da T3.7b.
- **`e4b531a` — T3.15c: a ponte julga `strategy_versions.purpose`** (desacordo com
  o envelope é recusado como `purpose_mismatch`); a `0011` **revoga do worker** o
  poder de ativar ou apagar uma versão; o script de ativação audita **cada** falha;
  o instalador do Hermes fixa `obsidian-mcp@2.0.1`.
- **`6b5cb2b` — brief T3.20** (página por versão com todos os parâmetros, script
  exportador, passo de plantão).
- **`b52f23f` — brief T3.19** (o protocolo de replicação que decide se uma
  estratégia promissora é real; nada chega à carteira).
- **`2814eec` — brief T3.18** (o placar do Lab, veredito mecânico na regra 100/30,
  curva de resultado simulado).
- **`8101d26` — T3.17: o Lab em dinheiro, na língua do Everton.** Entrou, saiu,
  variação, valor simulado e lucro/prejuízo por operação; cartão de totais; a
  régua declarada de 0,25 % vinda da carteira paper real; colunas de pesquisa
  atrás de um toggle.
- **`7a0fa8d` — T3.16: os selos de obsolescência envelhecem contra o relógio do
  servidor** (`server_now` nas respostas de mercados, deslocamento por
  `useServerClock`), nunca contra o do visitante; dica "relógio local" quando uma
  API antiga omite o campo.
- **`8424ec9` — T3.7b: o produtor horário de β** (`beta_v1`, revisões imutáveis,
  idempotente por corte, **nunca** um β fabricado) e `request_backfill.py --days 31`
  pelo contrato do outbox. Fecha o bug "`market_betas` vazia" (ver
  [[Resolved Bugs]]) e **abre** o do backfill desbalanceado (ver [[Open Bugs]]).
- **`5b11438` — regra da casa: a árvore de trabalho é compartilhada.** Nenhum agente
  usa `stash`, `checkout --`, `restore`, `reset`, `clean` ou `commit -a`. Escrita
  depois de um agente ter engavetado o trabalho de quatro tarefas em 2026-09-08 —
  recuperado do stash.
- **`178e9d2` — brief T3.17** (o front do Lab em dinheiro, com a régua declarada de
  0,25 %).
- **`19321aa` — a flag da ponte espera a T3.15c e a T3.15e** (parecer do
  `risk-engine-guardian` de 2026-09-08).
- **`3736a62` — revisão do `risk-engine-guardian` sobre a `0010`/T3.15b**: dois
  bloqueadores, os dois já cobertos pela T3.15c. Mais o brief T3.15e (ativação
  mantém o conteúdo derivado, uma coorte pela ponte, `purpose` visível).
- **`b8f3d3f` — briefs T3.15c** (desdobramentos da revisão da `0010`: a ponte lê a
  coluna, o worker não pode ativar, DSN de owner só em `migrate`/ops, instalador
  fixado) **e T3.16** (obsolescência contra o relógio do servidor).
- **`b6f5c2c` — a página da carteira quebrava com um `Decimal` zero serializado
  como `0E-20`.** Os decimais da API passam a sair em notação simples
  (`decimal_plain`, schemas da carteira em `DecimalStr`) e o parser da web aceita
  formas com expoente.
- **`3c55add` — plantão da madrugada de 2026-09-08** (EXP-0005 aberto, changelog,
  "Sexta-feira no Hermes", bugs do β).

- **T3.21 — a base ganhou padrão, vistas, mapas e um linter.** Frontmatter
  padronizado nas 162 notas (`status`, `owner`, `updated`, `tags` + chaves por
  pasta: `exp`/`result`/`evaluable`/`days`/`last_eval` nos experimentos,
  `severity`/`opened`/`closed` nos bugs, `decided_on`/`by` nas decisões,
  `fonte`/`lido_em`/`confiança` no conhecimento). Duas Bases nativas
  ([[Experimentos.base]], [[Estratégias.base]]), dois canvases
  ([[Fluxo sinal → carteira.canvas]], [[Família momentum.canvas]]), quatro
  callouts próprios (`veredito`, `medido`, `alerta`, `decisao`) aplicados aos três
  últimos diários e à [[EXP-0005-momentum-paper]], e o linter
  `infra/scripts/obsidian_lint.py` — links mortos, links ambíguos, órfãs,
  frontmatter, vocabulários, procedência do conhecimento e a **regra append-only**
  das avaliações datadas dos EXP. Convenções em `docs/OBSIDIAN.md`. Adaptado de
  `AgriciDaniel/claude-obsidian` **sem instalar o plugin** (escrita não suportada
  fora do WSL, e ele impõe layout próprio de vault). 62 links `[[Index]]`
  ambíguos qualificados por caminho. O linter foi dividido em três arquivos
  (`obsidian_lint.py` + `_rules` + `_links`, teto de 350 linhas) e passou a
  resolver link como o Obsidian resolve — sufixo de caminho em fronteira de
  barra, `.base`/`.canvas` como alvos, alias escapado de tabela —, o que
  derrubou os 163 achados da primeira execução: **eram todos falso positivo do
  instrumento, nenhum defeito da base**. 26 testes em
  `infra/scripts/tests/test_obsidian_lint.py`; `RESULTADO: base limpa`.

- 2026-09-08 — **Novo agente `product-designer`** (pedido do Everton): designer de produto SaaS que cuida de tema, cores, tipografia, UX e estados das telas, audita com dado real no navegador, propõe com mockups e especifica para o `frontend-specialist`; segunda opinião da Astra. Cartão em `.claude/agents/product-designer.md`, página em [[Product Designer]].

*(Os doze itens abaixo entraram entre a tarde de 2026-09-07 e a manhã de
2026-09-08, consolidados no plantão da madrugada de 2026-09-08. O eixo do dia
anterior foi a carteira; o deste turno é a **linha paper que vai alimentá-la** —
D10 — e o **ferramental que a rodeia**.)*

- **`58fe32e` — T3.7b: o runbook ordenado para ligar o fluxo paper.** O caminho
  completo, passo a passo: spot como serviço próprio, o produtor horário de β,
  o backfill de 31 dias, o segundo deploy da VPS, a linha paper (D10), a ativação
  auditada, e por último `ENABLE_PAPER_AUTONOMY`. Cada passo com o comando e o
  pré-requisito. Brief T3.7b escrito.

- **`e26a4ee` — revisão da T3.0e por Sexta-feira no Hermes (nada bloqueia) e
  brief T3.0f — o coletor spot como serviço próprio.** A revisão adversarial da
  T3.0e (histerese do piso spot, D12) não achou nada que bloqueie a admissão; a
  saída só acontece abaixo de 40 M por 3 refreshes consecutivos, e a admissão
  permanece em ≥ 50 M. O brief T3.0f separa o coletor spot num serviço dedicado.

- **`700d58f` — relatório do M3 em DRAFT, formato estendido.** Código completo,
  **não aprovado**; aguarda as revisões da T3.0e e da T3.15 (0010), a T3.10 e o
  segundo deploy da VPS antes do parecer da Sexta-feira.

- **`49281c9` — revisão da T3.15b (gate aprovado) e duas regras da casa para
  Sexta-feira no Hermes.** A ponte admite `purpose = paper` e recusa `live` por
  nome (D10, `56d2dea`). As duas regras: um brief **manda em quem o executa**
  (não commita quando diz "não commita"; relata o que o `git` diz), e um brief
  por tarefa (não escrever segunda versão de um brief existente). Brief
  duplicado removido.

- **`56d2dea` — T3.15b: a ponte admite paper, recusa live por nome (D10).**
  `bridge_screen.py` agora aceita `purpose = "paper"` e recusa `purpose = "live"`
  explicitamente — um rótulo chamado "live" num repositório cuja regra dura é
  "nada de dinheiro real antes da Fase 4" é um acidente esperando data. `nulo` e
  desconhecido continuam recusados. 16 testes de integração.

- **`d2d2d35` — brief T3.15b — a ponte admite paper, recusa live por nome.**
  Primeira tarefa da Sexta-feira no Hermes.

- **`0db5fbb` — a Sexta-feira ganhou casa nova: o perfil do Hermes.** O pacote
  `infra/hermes/` com o SOUL, o `.hermes.md` (contexto do projeto), as seeds de
  memória (`MEMORY.md`/`USER.md`, 2.200 e 1.375 caracteres), as três skills
  (`sexta-feira-plantao`, `sexta-feira-relatorio`, `sexta-feira-briefs`) e o
  instalador. Runbook em `docs/HERMES.md`.

- **`6b837ac` — T3.15: `purpose` na versão de estratégia e o rótulo paper (D10).**
  A coluna `purpose` entra em `strategy_versions` (migração `0010`); a coorte
  `research_only` permanece viva ao lado. A linha paper nasce por
  `activate_strategy_version.py --paper-line` — linha nova e congelada, não
  virando o propósito de uma versão existente. Ativação é ato auditado e decisão
  do Everton (sete condições em `docs/plans/M3.md`, D10).

- **`7839731` — T3.14b + T3.5d: follow-ups da ponte e eventos do kill switch.**
  A ponte ganhou quatro condições antes de ligar a autonomia (T3.14b) e o
  kill switch passa a publicar `kill_switch.changed` em `outbox_events` (T3.5d) —
  o `execution-worker` relê a trava a cada 10 s e dentro de cada transação de
  efeito.

- **`abf8e80` — T3.0e: banda de saída do piso spot (D12).** A admissão não muda
  (≥ 50 M); um par já admitido só sai abaixo de **40 M** por **3 refreshes
  consecutivos** (~45 min), com a contagem durável em Redis. D12: a histerese
  não relaxa a admissão, só a saída. `market_spot_dropped_events_total` e
  `market_type` nos logs de ingestão.

- **`ae25e32` — T3.9b: verificações V4–V9 e §10 (crash boundaries).** As últimas
  seis verificações que o Everton exigiu antes de a carteira andar, pelo caminho
  que persiste (todo número lido de volta do banco, não de memória). V4–V9
  cobrem slippage, stop intrabar, reserva vencida, kill switch, retomada e
  marcação a mercado; §10 prova as fronteiras de crash.

- **`90f1862` — T3.5c: o worker usa as colunas da 0009.** `is_residual` lido e
  escrito; o pó excluído de slots e exposição; pedidos manuais reconstruídos de
  `request_payload` e decididos no ciclo de 1 s; `target` entra no digest.

- **`999640a` — T3.0d: event ids do candle spot carregam `market_type`.** Os
  ids do perpétuo são **pinned byte-identical**; o scanner descarta entregas
  não-perpétuas; `load_market_ids` filtra por tipo; docstrings de identidade
  spot e `PIPELINE §1d`. Fecha o HIGH bloqueante da T3.0c (o segundo candle do
  minuto era descartado em silêncio).

*(Os itens de `8822b31` para trás — de `8f8be1e` a `8822b31` — foram consolidados
no plantão da manhã de 2026-09-07 na seção anterior. Ver `git log` para o detalhe
commit a commit.)*

## 2026-09-07

*(Os dois itens a seguir, do fim da tarde, foram acrescentados no plantão do meio-dia de
2026-09-08 — faltavam no consolidado anterior.)*

- **`6b82ce0` — `milestone.json`: M3 com o código completo**, pendente da T3.10, das revisões e do
  segundo deploy da VPS; bloqueadores e próximas ações atualizados.
- **`8eff6d2` — brief da revisão adversarial da T3.0e** (Sexta-feira no Hermes, somente leitura).

*(Os dezenove itens abaixo entraram entre `02:40Z` e `10:21Z` e foram consolidados no plantão da
manhã de 2026-09-07 — de `8f8be1e` a `e57908a`. O dia inteiro é M3, e o eixo dele é um só: **a
carteira do Everton deixou de ser um número parado e passou a ter um processo que a faz andar.**)*

- **`e57908a` — a revisão da ponte: nada bloqueia, e quatro itens antes de ligar a autonomia.**
  Revisão adversarial em `.claude/state/review-T3.14.md`, **79 testes rodados**. Ela confirmou o que
  mais importa para o Everton: com `ENABLE_PAPER_AUTONOMY=false` a ponte **nem cria o grupo de
  consumo** e não submete nada — o desligado é desligado de verdade, não um `if` no fim do caminho.
  Também: `purpose != "live"` é recusado (nulo e desconhecido inclusive), o score usado é o da
  **barra fonte** (`opportunities.last_updated_at <= source_bar_close`, sem olhar o futuro), a ordem
  total de candidatos tem desempate determinístico por `signal_id`, a ordem de travas é idêntica nos
  três ciclos, e não há float, `now()` nem `sleep` em lugar nenhum. Os quatro "deve corrigir" **não
  bloqueiam o commit** — são condições escritas para **ligar** a autonomia (T3.14b, depois da
  T3.5c), e estão em [[Open Bugs]].

- **`70acb6f` — `0009_paper_geometry`: o pedido carrega a própria geometria, e o pó vira coluna.**
  Para o Everton: um pedido de ordem arquivado pela tela **não podia ser decidido**. A tabela
  guardava carteira, mercado, direção e chave, e **não** guardava o preço de referência, o stop, o
  alvo nem os custos assumidos — o motor via que havia trabalho e não conseguia fazê-lo, registrando
  `pending_request_without_geometry` uma vez por segundo, por pedido, para sempre. Agora
  `trade_proposals.request_payload` guarda essa geometria, com **dinheiro escrito como string de
  JSON** (um número de JSON volta como float na maioria dos parsers, e um preço que retorna
  `0.30000000000000004` é exatamente o bug que a disciplina do `Decimal` existe para impedir) e um
  CHECK que exige as **oito chaves presentes e do tipo certo** — ausente se escreve `null`, nunca por
  omissão. Detalhe que vale guardar: a forma ingênua do CHECK **aceitava um payload sem `target`**,
  porque um CHECK é satisfeito quando a expressão avalia para `NULL` ("desconhecido não é violação");
  foi reproduzido num Postgres 16 real durante a verificação e corrigido com
  `coalesce(jsonb_typeof(...), 'absent')`. Junto vem `positions.is_residual`, a coluna que dá nome ao
  **pó** (ver o `7091a16` abaixo). E fecha o S1 da revisão de segurança da `0007`: a API **não
  escreve mais** `request_digest` — o motor recomputa e compara, em vez de confiar na prova escrita
  por quem ela existe para vincular. `docs/DATABASE.md` §21.

- **`12edda3` — T3.14: a ponte sinal → admissão, desligada; e T3.5b, fechando as cinco condições do
  guardião.** Duas coisas num commit, e as duas importam.
  **A ponte (T3.14):** consome `shadow.signals.emitted` e, a cada segundo, escolhe **um** candidato e
  submete **um** pedido — mas só quando `ENABLE_PAPER_AUTONOMY` for verdadeiro, e o padrão é falso.
  A elegibilidade tem **um motivo nomeado por recusa** (contador `hunter_bridge_candidates_total`
  por desfecho): versão de estratégia ativa e com propósito diferente de `research_only`, par spot no
  mesmo venue pelo ativo base/cotação, β válido no momento, nenhuma posição aberta/fechando nem
  reserva viva na moeda, janela de entrada de 120 s após o fechamento da barra, e uma linha em
  `agents` habilitada para aquela versão. **A garantia que vale escrever com todas as letras: todo
  sinal do Shadow Lab hoje é `research_only`, então nada é admitido — nem com a bandeira ligada —
  até que exista uma versão de estratégia ativada com propósito de paper, e essa ativação é decisão
  do Everton.** 16 testes de integração.
  **T3.5b:** as cinco condições da revisão do guardião, fechadas. Uma reserva **vencida** nunca mais
  vira ordem (um ciclo cinco minutos atrasado, com livro perfeitamente elegível, agora produz
  `expired` em vez de fill); o ciclo de proteção **toma a trava da carteira** antes de ler as
  posições — a prova com duas sessões escreve `19.903,893385` em vez do rasgado `18.148,245790`, que
  era um BLOQUEADO latchado por dinheiro que nunca foi perdido; o pó fica visível e valorizado no
  patrimônio mas **não conta vaga, exposição nem duplicidade** (uma segunda ordem na mesma moeda
  volta a ser aprovada e preenchida); os avisos passam a sair **na transição**, não 86.400 vezes por
  dia; a proteção degradada faz backoff de 1 s a 60 s e **não grava linha de ordem** enquanto o
  motivo for "sem livro"; e a marcação a mercado planeja na **grade do minuto** com 5 s de folga
  antes da virada do dia em São Paulo, para a referência diária sempre achar um ponto (60 deslocamentos
  provados).

- **`509e4d8` — a tela `/system` passou a mostrar o execution-worker.** Patrimônio, kill switch com
  **BLOQUEADO destacado**, posições abertas, pedidos pendentes e **pedidos ilegíveis** com a
  explicação honesta do que são, proteções degradadas, idade da última marcação e da última proteção,
  e um selo dizendo se a autonomia está ligada. Nulo aparece como **"indisponível"** — nunca como
  zero. 9 testes.

- **`c1f8c5f` — `0008_paper_roles_2`: a API para de escrever execução, e a carteira nasce auditada.**
  Fecha os quatro achados da revisão de segurança da `0007`. **D1, o que mais assusta:** o papel da
  API tinha `INSERT`/`UPDATE`/`DELETE` em `orders`, `fills`, `positions` e `trades` — reproduzido de
  verdade, um fill fabricado passou, `positions.qty × 1000` passou, `DELETE FROM trades` passou. Como
  a curva de patrimônio é **derivada** dessas tabelas, forjar a fonte faria o motor assinar o ponto
  forjado com o papel confiável. Agora os quatro dão `permission denied` na escrita e mantêm a
  leitura. **D3:** uma carteira inserida por quem só tem os privilégios do motor tem de ser
  `paper`, não-arena, e trazer a auditoria **na mesma transação** — arena, `live`, outra organização
  e auditoria "de banco" são recusadas por uma trigger; a abertura real passa. **D4:** o motivo do
  kill switch não pode mais ser reescrito sem transição. **D2:** as guardas de cobertura de rota
  voltaram a ser contagens derivadas — um `range(16)` literal é exatamente o que silencia uma rota
  nova.

- **`7557368` — T3.13: o heartbeat do execution-worker ficou legível, e o runbook existe.**
  `/system/workers` passa a devolver os onze campos que `hb:execution:paper` **realmente escreve**
  (patrimônio, kill switch, posições abertas, pedidos pendentes e ilegíveis, proteções degradadas,
  atraso da proteção, última marcação, última leitura do kill switch, autonomia) — nenhum inventado,
  e a lacuna que sobra (atraso de outbox só aparece no `/ready` do próprio worker) está escrita.
  `docs/DEPLOYMENT.md` §3.2 e §5.1 dizem o que o worker é, como ele sobe e **o que ele nunca faz**:
  `ENABLE_LIVE_TRADING` é conferido no boot e o worker **se recusa a subir** se não for falso.

- **`7091a16` — a revisão do guardião sobre a T3.5: dois bloqueios, e a decisão sobre o pó.**
  Reproduzida em Postgres real, com script isolado. **Bloqueio 1:** uma proposta com reserva
  **vencida** era executada — aprovada 15:30:00, executada 15:35:00, 270 s depois do fim da tenure.
  **Bloqueio 2:** o ciclo de proteção **não travava a carteira**, e com caixa e posições lidos em
  leituras separadas a marcação escrevia patrimônio 18.148,25 onde a verdade era 19.903,89 — **−8,78 %**,
  o suficiente para latchar BLOQUEADO por uma perda que não existiu; na ordem inversa, infla o pico
  monotônico, que nunca desce. A docstring do módulo **afirmava** a trava que não existia. Os dois
  foram fechados na T3.5b (`12edda3`).
  **E a decisão do pó, que eu tomei em nome do Everton e é reversível por ele:** uma compra spot paga
  a taxa no próprio ativo, e o que sobra depois da venda é um resíduo abaixo do mínimo negociável.
  Ele **não é posição** — não segura vaga, não conta exposição e não bloqueia uma segunda ordem na
  moeda (foi reproduzido: 4 h depois do stop, a segunda ordem na moeda era recusada por
  `duplicate_position`). Mas ele **continua visível e valorizado** no patrimônio, marcado como "pó",
  porque apagar da conta uma quantidade que existe seria mentir sobre o patrimônio. O **assentamento**
  — vender o pó acumulado junto da próxima saída, ou numa varredura diária, quando ele passar do
  mínimo — ainda **não existe**, e por isso está em [[Open Bugs]].

- **`7ecafd2` — T3.5: o `execution-worker`. A carteira passou a ter quem a faça andar.** Este é o
  commit do dia. Para o Everton: até ontem o motor de risco, o ledger, o simulador e o kill switch
  eram **bibliotecas corretas que ninguém executava**; agora existe um processo, rodando com o papel
  do motor, que fecha o ciclo. Ele admite um pedido arquivado decidindo **a própria linha** do
  pedido; leva uma proposta aprovada com reserva viva até o livro spot elegível e aplica o resultado
  **numa transação só** — ordem, fills, posição com a taxa em ativo base descontada, trade, caixa,
  consumo de participação, reserva consumida e **as intenções de stop e alvo criadas ali dentro**,
  de modo que **nunca existe posição sem proteção durável**; verifica gatilhos em cada negócio válido
  e submete a saída sob a trava sistema → organização → carteira; marca a mercado a cada 60 s
  **antes** de avaliar o kill switch; relê a trava a cada 10 s e dentro de cada transação de efeito,
  publicando `kill_switch.changed`; e é idempotente por `execution_key`. Nada em memória é fonte da
  verdade.
  **A prova, e ela é real:** 30 minutos no stack local (06:57–07:27Z, saída 0) — ordem manual
  aprovada (18,518 de quantidade, limite ativo `risk_per_trade`) → fill a 100,01 com taxa de
  0,018518 em ativo base → posição 18,499482 com stop em 97,5 → salto sintético para 95,00 →
  **primeira tentativa de saída degradada** (ordem escrita, sem fill) → segunda tentativa 18,499 @
  95,00 com deslize de 256,41 bps → caixa 19.903,662415 + pó 0,04579 = patrimônio 19.903,708205,
  **idêntico no heartbeat e no último ponto da curva** → `trades.pnl = −96,28938018`, que é o bruto
  −92,679990 menos custos 3,60939018 **contados uma vez só** → 30 pontos de 1 min, **0 exceções**. A
  própria prova achou dois defeitos reais, corrigidos ali: uma entrada gastou a tentativa única
  contra um livro que ainda não era elegível (agora ela **adia**), e o instante era tomado antes da
  leitura do tape.

- **`70f2e7b` — a nota de rollback do `cefad8c`, escrita antes de precisar dela.** As linhas de
  candle passaram a carregar `market_type`, e o **código anterior recusa campo desconhecido**
  (`extra="forbid"`). Ou seja: se algum dia for preciso voltar atrás neste commit, **uma única linha
  nova envenena a lista de 1.500** do hot state — o scanner esvazia o Radar e o strategy avalia com
  a cauda vazia. O rollback exige `DEL mkt:*:candles:1m`, e isso agora está em `docs/DEPLOYMENT.md`
  em vez de na cabeça de alguém. Junto, a revisão da T3.0b: **deploy é seguro**, cinco itens ficam
  para a T3.0d.

- **`cdb4bb5` — abrir uma carteira exige dizer o nome dela em voz alta.** A abertura roda com o papel
  que atravessa o isolamento por tenant e é **permanente**. Agora o script só faz ensaio sem
  `--yes <slug-da-organização>` **repetido literalmente**, recusa um `--yes` que não case, exige
  `--actor` (resolvido para o usuário quando é o e-mail de um membro, senão `operator:<texto>`, com
  hostname e usuário do SO na auditoria para casar com o log de SSH), grava uma **segunda linha de
  auditoria** `portfolio.opened.confirmed_by` na mesma transação, e **relê as seis escritas por
  organização antes de retornar** — se alguma caiu no tenant errado, `ScopeViolation` e rollback
  total. A bandeira `--capital-brl` **saiu**: R$ 100.000 é a diretiva do Everton, não um parâmetro.

- **`e5e57d1` — a condição nº 1 de aprovação do M2 foi provada.** Medição na VPS às **06:28:46Z**:
  `session_since = 05:46:17Z` e `covered_until = 06:28:45Z`, a 1,1 s do relógio — **42 minutos
  contínuos** de cobertura avançando, contra os 30 exigidos. Quatro shards, `dropped_events = 0` nos
  quatro, `reconnects = 0`, e a chave compartilhada `hb:market:binance` extinta. Nos últimos 45 min
  do shard 0: 136 quebras `queue_backlog` com 136 retomadas — congelamentos curtos que **não**
  reiniciam a sessão. **Uma das quatro condições caiu**; a nº 2 (estágio e regime com dado real)
  continua marcada para 09–10/09, e a nº 3 (p99 de 3 s) segue aberta.

- **`d6dbbca` — a revisão de segurança da `0007`: nada bloqueia, quatro correções encomendadas.**
  Reproduzida como os papéis reais, com duas organizações e carteiras abertas pelo caminho real. O
  que já estava certo: troca de organização fora do alcance do motor, a trigger do "pedido honesto"
  recusando oito disfarces, segunda carteira principal impossível, curva somente-leitura para a API
  **inclusive nas partições**, RLS cruzada intacta, replay de transição bancada recusado. Os quatro
  "deve corrigir" viraram a `0008` (`c1f8c5f`), e a sugestão S3 virou o `cdb4bb5`.

- **`cefad8c` — T3.0b: `market_type` em toda identidade de mercado fora do banco.** O banco já
  distinguia spot de perpétuo; as chaves do Redis, os modelos de evento e os leitores de hot state
  **não** — spot e perpétuo de `BTCUSDT` dividiriam a mesma chave, e um upsert de perpétuo cairia em
  silêncio na linha do spot. Agora cada construtor de chave recebe o tipo, e o essencial: **o
  perpétuo mantém as chaves byte por byte** (testadas por snapshot), o spot ganha o segmento próprio.
  Um detalhe que parece capricho e não é: o tipo vem **antes** da exchange no heartbeat
  (`hb:market:spot:{ex}:0of4`), porque o glob do Redis casa `:` e `hb:market:binance:spot:0of4`
  seria contado como um shard de perpétuo — provado nos dois sentidos. Dois bugs latentes fechados de
  passagem (a linha de spot recebendo upsert de perpétuo; um `LIMIT 1` sem ordenação). O universo
  continua só perpétuo até a T3.0c.

- **`4688e70` — o painel da oportunidade ganhou o nome de produto.** "Por que estamos olhando isso?"
  agora é o título (`h2`) do painel, com o resumo determinístico logo abaixo — era exatamente o
  rótulo que a T2.8b registrou como **ausente** na tela. 534 testes de web.

- **`2ee79c1` — contrato v2.2.1: o §1 passou a descrever as funções que existem.** As assinaturas de
  `evaluate`/`evaluate_exit` no contrato normativo estavam desalinhadas das reais, `MarketRegime`
  ficou explicitamente **reservado ao M4**, e o escopo da carteira principal virou "por organização"
  em **todas** as menções. Este último fecha um dos cinco itens da revisão adversarial: a documentação
  normativa ainda descrevia o comportamento **antigo** — por workspace —, que foi exatamente o furo
  que o revisor de segurança provou e a `0006` fechou no banco. Quem lesse o contrato para
  implementar a T3.5 implantaria o furo de volta.

- **`ff23b4c` — a fixture do M2 escreve a transição que a trigger da `0006` exige.** Os dois testes
  vermelhos que a T2.8b registrou: a fixture virava `organizations.kill_switch_state` sem escrever a
  transição, e a trigger nova — corretamente — recusa. 25 passando.

- **`eccb648` — T3.9a: as verificações V1, V2, V3 e §11, pelo caminho que persiste.** Para o Everton:
  são as primeiras das nove verificações que ele exigiu antes de a carteira andar, e a diferença
  aqui é que **todo número é lido de volta do banco** — de `trade_proposals`, `reservations`,
  `kill_switch_transitions`, `portfolio_risk_state` —, não do objeto em memória. V1: 1.851,800 USDT
  a 0,24999 %, com o limite ativo sendo `risk_per_trade` e a decisão persistida **idêntica campo a
  campo** à do motor puro; `entry_ref` 100 contra um mercado a 110 recusado com desvio 0,090909. V2:
  AVISO corta pela metade (925,900) a partir da trava durável, depois de uma perda real de 1 %. V3:
  −2,5 % no dia → BLOQUEADO com PnL realizado **zero** e transição auditada; o BLOQUEADO libera a
  reserva pendente e **mantém as saídas aprovadas** pela quantidade inteira. §11: duas admissões
  simultâneas em duas conexões reais → **uma** reserva, a segunda repete a resposta.
  **Três divergências ficaram registradas como `xfail` estrito, sem mexer em número nenhum** — entre
  elas, a aritmética do V2 na especificação supõe patrimônio 20.000 enquanto a própria perda de 1 %
  dela dá 916,600. Registrar a divergência é o certo; ajustar o teste até o número fechar seria o
  erro.

- **`dd4d16d` — T2.8b: o teste ponta a ponta do M2, e uma corrida datada de todas as suítes.**
  Oito testes que percorrem o pipeline inteiro com Postgres e Redis reais: velas sintéticas
  rotuladas → linhas de `Candle` → bootstrap real (10.080 cortes, 288 buckets, features de tape
  ausentes **com motivo**) → hot state nos bytes msgpack do próprio `market-worker` → scanner →
  publicação do Radar → `GET /api/v1/radar`. Números fechados: `VOLUME_SPIKE` + `TRADE_VELOCITY_SPIKE`
  em severidade 100,00; **EARLY só é publicado quando `covered_until` libera o tape** (a borda
  inversa recusa); regime `UNKNOWN` **declarado** com `volatility_warmup` (sete dias sintéticos não
  são trinta); score 35,00 = volume 15 + fluxo 5 + anomalias 5 + Early-Movement 10, com cada
  componente ausente carregando o motivo; **duas execuções independentes byte a byte idênticas**.
  Controle por mutação: multiplicador 40 → 4 derruba três testes. Os dois specs de e2e foram escritos
  e tipados mas **não executados** — o Chromium desta sessão não alcança o loopback —, e isso está
  escrito em vez de arredondado.

- **`2688ef1` — `0007_paper_roles`: o worker decide, a API pede.** O modelo de papéis que eu decidi
  em nome do Everton vira privilégio no banco: **o motor decide e grava estado de risco; a API
  registra pedidos, lê e autoriza pessoas**; e a retomada do kill switch passa a exigir **OWNER** —
  a diretiva dele diz "retomar somente com minha autorização", e TRADER não bastava.

- **`096d8c5` — BRL na convenção brasileira na tela da carteira.** `R$ 100.725,19`, `−R$ 1.234,50`,
  por um `formatBrl` que **nunca passa a magnitude por `Number`** — o valor vem do banco como string
  decimal e é agrupado como string, então nada de dinheiro toca ponto flutuante no caminho até o
  olho do Everton. `formatMoney` ficou como estava. Fecha a pendência declarada na própria T3.8b
  ("BRL usa agrupamento en-US, follow-up"). *(Entrou depois do corte `09eb6de` deste plantão.)*

- **`7304709` — o Caddy volta a ter o IP fixo dele, e o deploy da VPS vira um comando só.** Para o
  Everton: **o site ficou fora do ar por volta de 20 minutos hoje de madrugada, e a causa era
  minha.** O Caddy (o porteiro que atende `https://`) está preso ao endereço `172.28.0.10` porque a
  API usa esse endereço para contar requisições por cliente; o Docker distribuía endereços dinâmicos
  **dentro da mesma faixa** e, quando o perfil de 4 shards recriou os contêineres, entregou o `.10`
  ao `scanner-worker` — o Caddy subiu com "Address already in use" e ninguém atendia a porta 443.
  Correção: a faixa dinâmica passa a ser `172.28.0.128/25`, longe do endereço fixo. No mesmo
  incidente, um `docker compose` **na mão**, sem o `compose.sh`, perdeu duas variáveis que só o
  script deriva: `GIT_SHA` (a migração rodou com a imagem velha e não achou a revisão `0006`) e
  `HUNTER_DEFAULT_SNI` (o Caddy serviu um certificado de `localhost` e o HTTPS quebrou no IP).
  Agora `compose.sh up/update` lê `MARKET_SHARDS` e acrescenta sozinho `--profile shards`, e
  qualquer serviço que fique `created/exited/dead` faz o script imprimir `docker compose ps` e as
  últimas 50 linhas de log e **sair com erro** em vez de dar o deploy por terminado. Deploy é uma
  linha: `MARKET_SHARDS=4 bash infra/vps/compose.sh update`. Ver [[Open Bugs]] — o item de processo
  ("deploy manual sem `compose.sh`") continua aberto, porque a correção é técnica e o hábito é
  humano. *(Entrou depois do corte `09eb6de` deste plantão.)*

- **`09eb6de` — T3.11a: o coletor de câmbio USDTBRL, uma observação por minuto, jamais inventada.**
  Para o Everton: é a peça que dá **preço do dólar-cripto em real** para a carteira — sem ela os
  R$100.000 não viram USDT e a tela não sabe dizer quanto a carteira vale em reais. Uma tarefa nova
  no `market-worker` busca `GET /api/v3/ticker/24hr?symbol=USDTBRL` a cada ~60 s ± 5 s **somente no
  shard 0** (os outros três ficam ociosos nessa tarefa para sempre), e grava em `fx_observations`
  com `observed_at = closeTime` (relógio da Binance), `available_at` no instante do `INSERT` e a
  resposta crua junto. As constantes vêm de `hunter_core.portfolio.fx_policy.PAPER_FX_POLICY`, a
  mesma que a abertura da carteira usa — coletor e abertura **não podem divergir**. `ON CONFLICT
  (pair, source, observed_at) DO NOTHING`: repetir a coleta não duplica nada. Taxa fora de `[1, 100]`
  **é gravada assim mesmo** (quem recusa é a política que consome, não o coletor) com aviso e o
  contador `hunter_fx_implausible_total`. Prova: 10 minutos contra a Binance real, 11 coletas, a
  última observação com 27 s no fim da janela, 0 erros. Astra fora (cota do Codex até 12/09),
  registrado no próprio commit.

- **`3519107` + `8e4b26b` — a revisão adversarial da T3.1b/T3.6/T3.12, e as cinco condições que ela
  impôs à T3.5.** Revisão em `.claude/state/review-T3.1b-T3.6-T3.12.md`: **APPROVE_WITH_NITS**, com
  sondas SQL rodadas como os papéis reais do banco e mutações que matam os testes pelo motivo certo.
  Cinco itens têm de ser fechados **antes** da T3.5/T3.8, e viraram condições escritas do brief da
  T3.5: (1) a deduplicação por chave de idempotência casa também um pedido **ainda não decidido** e
  explode ao validar uma decisão vazia; (2) a admissão do lado da API roda inteira como `hunter_app`
  e vira erro 500 quando os grants novos entrarem — a API **registra o pedido**, o worker admite;
  (3) o teto do pico conta snapshot de **qualquer** resolução, e um roll-up de 1 h/1 d futuro
  travaria a carteira em `TRADING_DISABLED` para sempre; (4) a documentação ainda diz "uma principal
  por workspace" quando a `0006` já é por organização; (5) **nenhuma transição publica
  `kill_switch.changed`**, e o contrato exige reação em menos de 1 s. Os cinco estão em
  [[Open Bugs]].

- **`817f129` — T3.8b: a tela da carteira, `/[org]/portfolio`.** Para o Everton: é a primeira tela do
  projeto que fala de **dinheiro** — patrimônio em USDT e em BRL, caixa, reservas, exposição, e a
  decomposição que a diretiva pediu: quanto do resultado é **operacional** (a carteira ganhou ou
  perdeu operando) e quanto é **cambial** (o dólar mexeu). Cartão de risco com o dia de negociação e
  o fuso, o patrimônio de abertura do dia, o pico, a perda do dia e o drawdown — e nulo aparece como
  **"indisponível"**, nunca como `0 %`. O kill switch efetivo vem do endpoint real com os três
  escopos, o motivo e a última transição com a evidência. Curva de patrimônio com alternância
  USDT/BRL, e os pontos sem BRL ficam como **buraco visível**, não interpolados. Tabelas de posições,
  ordens e trades com estado vazio honesto e o `as_of` ao lado; o bloco de propostas diz, em
  português, que a ponte de admissão ainda não existe. Sem carteira principal, a página **explica o
  comando do operador** e não oferece botão que finja abrir uma. Nada de `any`: tipos gerados do
  OpenAPI. 528 testes de web verdes.

- **`8c53b30` — contrato v2.2 do Risk Engine: uma fonte só para o `paper_v1`.** O perfil gravado no
  banco (`risk_profiles.limits`) passa a ser **exatamente** `hunter_risk.limits.PAPER_V1` serializado,
  com ida e volta provada por teste — antes as duas fontes discordavam em 10 campos e validar o
  perfil do banco contra o motor falhava. Quatro chaves saíram do perfil **com destino escrito**
  (não sumiram), o multiplicador por regime fica **reservado para o M4** e `auto_close` fica fixo em
  *nunca liquidar*. **Nenhum limite que o Everton escreveu mudou.** `docs/RISK_ENGINE.md` v2.2.

- **`d23b7bd` — T3.3b: fechando a revisão do ledger, com a banda que impede uma carteira nascer
  errada para sempre.** Para o Everton: a abertura da carteira é **irreversível** (a âncora de
  câmbio é imutável por decisão sua), então um erro de escala do coletor — `0,54321` em vez de
  `5,4321` — abriria a carteira com 184.081 USDT e não haveria como desfazer. Agora a política de
  câmbio declara a banda plausível `[1, 100]` para USDTBRL e, opcionalmente, compara com a última
  observação aceita (20 % em 600 s, com causalidade: mesmo par, mesma fonte, estritamente anterior).
  Taxa `1e-10` e `0,54321` são recusadas; `5,4321` passa. Também: a indisponibilidade de BRL e as
  marcações velhas passam a gerar **evento de auditoria** em vez de sumir na memória; o escopo da
  carteira principal vira uma constante só (`organization`), alinhada com o índice corrigido; duas
  aberturas concorrentes sincronizadas por barreira — uma vence, a outra recebe `WalletAlreadyOpen`
  e nunca o erro cru; o capital é **fixo em R$100.000** e uma varredura de AST prova que nenhum
  módulo de produção usa o override de teste; `mark_positions` recusa qualquer linha que não seja
  comprada (spot é long-only).

- **`2f9007b` — o build da web quebrou na VPS por dois esquemas com o mesmo nome.** `TradeOut` da
  carteira colidia com `TradeOut` de mercados; o gerador de OpenAPI **estropiou os dois nomes** e o
  `recent-trades.tsx` perdeu o tipo do trade. Renomeado para `PortfolioTradeOut`. Vale como lição: o
  nome de um schema Pydantic é global no documento gerado.

- **`12553e3` — nota de rastreabilidade do relatório do M2.** O relatório e o parecer do M2 foram
  varridos para dentro de um commit de outra tarefa (`6c60653`) por um agente concorrente no mesmo
  worktree, e `6c60653` **já estava empurrado** quando percebi. Não reescrevi histórico empurrado —
  `--force` é decisão do Everton. A nota no topo de `docs/reports/M2.md` diz onde o conteúdo está de
  verdade. O bug de processo continua em [[Open Bugs]].

- **`6c60653` + `15b6dd2` — os briefs da T3.5 (execution-worker) e da T3.1c (modelo de papéis).**
  A **T3.5** é o worker que vai fazer a carteira andar: ciclo de admissão, ciclo de ordem aplicando o
  `ExecutionReport` **por fill**, ciclo de proteção, marcação a mercado **antes** do kill switch,
  recuperação após restart e supervisão. A **T3.1c** fecha uma decisão que tomei em nome do Everton e
  que muda quem pode o quê no banco: **quem decide e grava estado de risco é o worker**; **a API
  pede, lê e autoriza pessoas** (ela registra o pedido manual como `status='requested'`, sem decisão
  e sem reserva, e o `execution-worker` admite); e a **retomada do kill switch exige o papel OWNER da
  organização** — a diretiva do Everton diz "retomar somente com minha autorização", então TRADER não
  basta. Entram também duas colunas de dívida do ledger (`brl_unavailable_reason`, `marks_stale`) e o
  `request_digest` que a T3.12 pediu.

- **`296f3c1` — T3.1b: a `0006` corrigida no lugar, antes de qualquer banco persistente aplicá-la.**
  Para o Everton: a revisão de segurança achou **dois furos que dariam para burlar a sua diretiva**, e
  os dois foram fechados no banco, não no código de aplicação. **Primeiro:** o kill switch auditado
  aceitava uma transição **antiga ou forjada** — depois do primeiro ciclo de trava e retomada
  legítimas, qualquer `UPDATE` destravava a carteira para sempre (reproduzido: 3 transições para 4
  movimentos). Agora a trava exige que a **última** transição do escopo case com o movimento **e**
  tenha sido escrita **pela transação corrente** (`xmin = pg_current_xact_id()`). **Segundo:** dava
  para ganhar uma **segunda carteira principal com R$100.000 novos** só criando um workspace novo — o
  índice único era por `(organização, workspace)`. Agora é por **organização**, como a sua decisão D7
  diz. Mais: identidade composta descendo até a posição (uma ordem de uma organização não pode mais
  apontar para a posição de outra); `portfolio_risk_state` só o worker escreve, o dia só avança, o
  patrimônio de abertura só se define uma vez por dia e o pico nunca passa do maior patrimônio já
  observado (gravar `999999` travaria a carteira em drawdown permanente); a âncora confere o **par**
  da observação de câmbio; e o `paper_v1` do banco é literalmente o do motor.

- **`ec78727` — T3.4b: um print inválido não apaga mais um stop que já foi tocado.** Para o Everton:
  este é o pior tipo de bug possível num sistema de risco — **a proteção sumia em silêncio**. O
  verificador de gatilhos validava o lote inteiro de negócios antes de procurar o cruzamento; um
  único print malformado (relógio de outro host, id não numérico) fazia o lote inteiro virar
  "indisponível" e o stop já tocado ser descartado; no ciclo seguinte aquele preço já estava velho e
  a posição ficava sem proteção. Agora o cruzamento é decidido **sobre o prefixo que deu para
  validar** e só o resto é reportado como indeciso. Junto: reaplicar o mesmo relatório de execução
  virou **idempotente** por tentativa (antes somava o fill duas vezes e marcava a saída como cumprida
  com metade da quantidade ainda na posição); um replay com quantidade ou decisão diferente **falha
  alto** em vez de devolver o relatório antigo; e o filtro de preço da exchange passa a ser uma banda
  de sanidade do fill — entradas são recusadas, mas **saídas de proteção sempre executam com
  alerta**, porque uma queda real de 20 % é exatamente quando o stop importa. Astra fez quatro
  rodadas neste diff; a quinta não rodou (cota do Codex até 12/09).

- **`ae2657d` — T3.12: um caminho só, da proposta à decisão.** Para o Everton: era possível existirem
  dois jeitos de uma ordem entrar (o do agente e o da tela) e eles divergirem. Agora existe **um**
  serviço de admissão: ele pega as travas na ordem sistema → organização → carteira, monta o estado
  da carteira, roda o Risk Engine e grava, **numa transação só**, a proposta com a decisão canônica e
  o limitante vencedor, a sequência FIFO durável, a reserva (`held`, válida por 30 s), a linha de
  auditoria e o evento de saída. Uma recusa é gravada com todos os checks e **nenhuma reserva**.
  Repetir o mesmo pedido devolve a mesma decisão sem reavaliar nem reservar de novo; repetir com
  conteúdo diferente é conflito. O orçamento de participação de 60 s por (mercado, carteira) soma o
  consumo já executado ao que está reservado. `research_only` é recusado na origem — o Shadow Lab
  não entra na carteira por acidente.

- **`9ceb389` — T2.5g: 200 mercados em N shards, com heartbeat por shard agregado pela API.** Para o
  Everton: a página System volta a poder dizer a verdade com mais de um coletor no ar, e o mercado
  chega ao Radar seis vezes mais rápido. A dívida nº 1 do M1 — todos os shards escrevendo a mesma
  chave `hb:market:{exchange}`, de modo que um shard morto ficava invisível — está fechada: cada
  shard tem a própria chave, a API agrega com `shards_expected`/`shards_reporting`, um heartbeat
  vencido vira `unavailable` em vez de repassar `connected`, e um shard sem evento não herda o
  frescor do irmão. A cobertura do tape passou a ser escrita **inteira dentro de um script Lua**
  (reconciliação total dos campos `sym:`), o que revelou e matou um órfão real em produção
  (`KOMAUSDT` sem dono, 201 campos para 200 mercados). Medido: latência de publicação de
  `market.ticks` p50 **25,82 s → 4,31 s** com 4 shards, e 0,41 s com 8. Os descartes finalmente são
  contados. Ver [[Open Bugs]]: **não implantado na VPS**.
- **`9a0ac45` — T3.6 kill switch durável e T3.8a a API de leitura da carteira, com o script que abre
  a carteira.** Para o Everton: até aqui o kill switch era uma **conta**, não uma **trava** — se o
  processo reiniciasse, ele voltava sozinho para `ACTIVE`. Agora a avaliação compara com a trava
  gravada e escreve a transição auditada (de onde, para onde, motivo, evidência, ator) **na mesma
  transação** que muda o estado da carteira: o AVISO só sai na virada do dia e só quando os **dois**
  gatilhos sumiram; o BLOQUEADO **nunca** sai sozinho; a retomada é recusada enquanto a avaliação
  automática ainda bloqueia, e ela **não** redefine o pico nem as perdas. Provado: um `UPDATE` cru da
  trava é **recusado pelo banco**; −1 % → AVISO → −2 % → BLOQUEADO → recuperação no mesmo dia
  continua BLOQUEADO → retomada recusada e depois aceita com o pico intacto; o reinício encontra a
  mesma trava; duas avaliações concorrentes escrevem **uma** transição. A API de leitura entrega
  carteira, âncora, curva de patrimônio, posições, ordens e trades — com a decomposição em BRL, a
  observação de câmbio usada e o motivo quando não há taxa válida —, 404 entre organizações, e
  páginas honestamente vazias com `as_of`. E `infra/scripts/open_paper_wallet.py`: busca o USDTBRL do
  ticker público, grava a observação e abre a carteira; recusa uma segunda abertura.

- **Fecho do M2 (T2.8): relatório, parecer e `EXP-0003`.** Para o Everton: o Radar tem linhas reais
  pela primeira vez, e eu **não aprovei** o milestone. `docs/reports/M2.md` traz o formato estendido
  inteiro, com o que foi entregue por tarefa e o que não foi cumprido **com número**: estágio
  EARLY/DEVELOPING/EXTENDED **nunca publicado** (0 em 299 amostras), regime **`UNKNOWN` em 100 %**
  das leituras, p99 tick→oportunidade em **0,3 %** de cumprimento com 4 shards (70,5 % com 8, mas o
  p95 fica em ~11 s porque `crc32 % N` equilibra contagem e não tráfego), **1 de 10** detectores de
  anomalia disparando, **6 de 9** componentes de score indisponíveis com motivo — e o teto
  aritmético de score que isso implica, **25,00 de 100** contra a linha de 40 do WATCHING.
  [[EXP-0003-baselines-v1]] abre o M2 como experimento de **instrumento**, com o SQL colado e a
  saída real: 4.944 buckets utilizáveis de 88.746 (5,57 %), 12 de 27 features com algum bucket
  utilizável, e as 15 mudas sendo exatamente as de tape, livro, derivativos e `_live`. O motor está
  certo — ele escreve o que tem evidência e diz o motivo de tudo o que não tem. O que falta é, na
  maior parte, **tempo de coleta**; as quatro condições objetivas de aprovação estão no VEREDITO.

## 2026-09-06

- **`e48f7e4` + `c35fd40` — as revisões adversariais que seguraram a T3.1, a T3.3 e a T3.4.** Duas
  revisões independentes com veredito **REQUEST_CHANGES**, e é por isso que existem as correções
  `T3.1b`, `T3.3b` e `T3.4b` acima. A de segurança da `0006`
  (`.claude/state/review-T3.1-security.md`) reproduziu tudo em Postgres 16 real, como os papéis
  reais: o kill switch auditado aceitando transição antiga ou forjada, e a segunda carteira principal
  de R$100.000 por um workspace novo. A do ledger e do simulador
  (`.claude/state/review-T3.3-T3.4.md`) achou o print inválido que apagava um stop tocado, a
  reaplicação de fill não idempotente e a taxa de câmbio sem banda de plausibilidade. **Nenhum destes
  achados veio de leitura de código sozinha — cada um tem um script de cenário que o reproduz**, e é
  isso que os torna obrigatórios em vez de opinião.

- **`edd5d7e` — T3.4: o simulador de execução paper, sem um único fill inventado.** Para o Everton:
  é a peça que finge ser a corretora, e a regra dela é dura — **ela nunca preenche uma ordem que o
  mercado não mostrou**. Só ordem a mercado. Stop e alvo são gatilhos locais pelo **último negócio
  SPOT válido** (nunca `mark_price`, que é conceito de perpétuo): o negócio vale se tem no máximo
  10 s, se chegou antes de agora e se o id é estritamente crescente — e **"indisponível" é um
  terceiro veredito**, porque um pedaço de fita que não vimos não prova que o stop não foi tocado.
  Uma caminhada única no livro elegível decide o preço; entrada com fill parcial cancela o restante
  **terminalmente**; saída de proteção termina a tentativa mas a **intenção durável permanece** para
  a quantidade que sobrou, com nova tentativa de identidade própria — nunca se vende a mesma unidade
  duas vezes. Sem livro utilizável, a saída fica **pendente, degradada e com alerta**, e nenhuma vela
  fornece fill retroativo. A execução pior que o stop é **publicada, nunca corrigida** (stop 95,
  melhor oferta 90 → 526,3 pontos-base de deslize, escritos). `LiveExecutionAdapter` só sabe levantar
  `LiveTradingDisabled`.

- **`8a6a69f` — T3.3: o ledger da carteira, a abertura com câmbio validado e o resultado em reais.**
  Para o Everton: é aqui que os R$100.000 viram USDT e é aqui que a tela aprende a dizer **quanto
  disso é a operação e quanto é o dólar**. A abertura valida a observação de câmbio **antes de
  qualquer escrita** (par USDTBRL, fonte declarada, taxa > 0, disponibilidade ≤ 300 s e observação
  ≤ 600 s — dois limites para que um backfill não rejuvenesça uma cotação velha) e grava carteira,
  estado de risco, âncora imutável, o primeiro ponto de patrimônio e a linha de auditoria **numa
  transação só**. A conversão usa `floor_10dp_v1` e a fração descartada fica registrada como
  `conversion_residual` — nada evapora. A atribuição é sobre o **patrimônio**, não sobre o caixa:
  operacional `(E − E0)·F0`, cambial `E·(Ft − F0)`, identidade `total = E·Ft − E0·F0`. E **não existe
  rota de aporte nem de reset**: uma varredura de AST sobre `packages/`, `apps/` e `services/` prova
  isso — é a diretiva do Everton virando teste.

- **`a88daac` — a especificação executável das nove verificações da diretiva (T3.9).** As nove
  verificações que o Everton listou viraram um documento com número fechado onde já havia teste
  verde, e **seis decisões pendentes** escritas em vez de resolvidas por conta própria.

- **`078d6ef` — T3.0a: o adaptador SPOT da Binance.** Para o Everton: a carteira executa **no spot**
  (comprar de verdade a moeda, sem alavancagem), enquanto os sinais continuam vindo do perpétuo — é
  a decisão D1 que tomei em seu nome. Este commit entrega o lado do adaptador: REST em `/api/v3` num
  balde de peso próprio (6000/min, independente dos 2400/min do perpétuo), `exchangeInfo` com
  **todos os filtros que se aplicam a uma ordem a mercado**, WebSocket próprio com rotação de 24 h, e
  taxas spot **declaradas com fonte** (0,1 %/0,1 %; 0,075 % com BNB), nunca herdadas de futuros.
  Teste ao vivo: 487 pares USDT, **19 acima do piso de 50 M/24 h**, 2.684 eventos em 19,9 s, nenhum
  fora de ordem. Bloqueio declarado para a integração (T3.0b/T3.0c): os modelos de evento **não
  carregam `market_type`**, então spot e perpétuo de `BTCUSDT` ainda dividiriam a mesma chave no
  Redis — isso tem de ser resolvido antes de o `market-worker` ingerir spot.

- **`11faba8` — `0006_paper_wallet`: a carteira virtual no schema (T3.1).** Seis tabelas novas mais
  extensões de `portfolios`, `trade_proposals`, `orders` e `fills`. As que importam para o Everton
  entender o produto: `portfolio_currency_anchor` (**imutável**, uma por carteira: o capital de
  origem em BRL, a observação de câmbio usada e o instante); `fx_observations` (global, imutável,
  **nunca apagada**, nem quando um cliente é removido); `market_betas` (revisões imutáveis do β);
  `portfolio_risk_state` (a referência do dia em `America/Sao_Paulo` com o instante real de avaliação
  e o pico durável); `portfolio_exit_intents` (a **intenção** de proteção, durável e distinta da
  tentativa); `participation_consumptions`; e `kill_switch_transitions` **com evidência**. O preset
  `paper_v1` entra no seed com os valores da diretiva. Verificado em Postgres 16: subida do zero,
  `alembic check` limpo, ida e volta do downgrade, privilégios por papel e isolamento RLS nas tabelas
  novas.

- **`766f8b6` — T2.9c: a recuperação histórica anuncia **um** evento por lote inserido, não um por
  minuto.** Para o Everton: o histórico de 7 dias que o scanner pede deixa de sufocar a fila de
  anúncios e de passar na frente das velas ao vivo. O consumidor de backfill (`3dcb218`) gerava um
  `market.candles.closed` por minuto backfillado (~1 440 por ciclo), o que limitava o dreno a ~1 dia
  de histórico por minuto de relógio. Agora o estrato `history` insere com `announce=False` e
  enfileira **um** `market.candles.backfilled` (stream novo, `MAXLEN 5 000`) por lote, na mesma
  transação das velas e da transição do gap; a identidade é `uuid5` sobre o intervalo **realmente
  inserido** — dois lotes commitados nunca compartilham o mínimo, porque o `ON CONFLICT DO NOTHING`
  nunca insere o mesmo minuto duas vezes. `reason = "historical_recovery"` (a janela envelheceu),
  nunca `"backfill_request"`: must-fix da Astra, porque uma lacuna criada pela coleta ao vivo pode
  envelhecer para o estrato histórico sem que ninguém tenha pedido nada. Prova no contêiner: um gap
  de 240 min → 240 velas, **0** `market.candles.closed`, **1** anúncio agregado. Nenhum consumidor do
  novo stream existe ainda — está registrado com os quatro requisitos que quem o escrever terá de
  cumprir.
- **`fe8872c` — T2.5e: a cobertura do tape volta a andar.** Para o Everton: as features de fluxo
  (velocidade de negócios, pressão compradora/vendedora) tinham parado de existir porque o coletor
  não conseguia mais **provar** o que havia observado. Desde `4bb2865` o carimbo exigia
  `enfileirados == entregues + descartados` no instante exato — igualdade que, sob fluxo contínuo
  (~150 msg/s), quase nunca é verdadeira, por uma folga de agendamento do asyncio que acontece a
  cada mensagem. Resultado medido: `mkt:binance:coverage` congelado por > 2 h no local e **19
  quebras em 45 min** na VPS, com **100 %** das avaliações do scanner lidas como `uncovered`. A
  Astra derrubou dois desenhos com contraexemplos (o item já retirado da fila e ainda não entregue;
  idade local que não prova nada sobre o timestamp do evento); a regra entregue compara o
  **timestamp do próprio evento pendente** com o corte candidato, tudo em UTC, sem teto de
  contagem — "magnitude nunca foi o sinal honesto". Os 13 testes de cobertura anteriores passam sem
  uma linha alterada. Ver [[Open Bugs]]: na VPS o carimbo **voltou a congelar** depois do deploy e
  isso está aberto.
- **`48c6f0d` — T2.5d: consumo em lote, `hiredis` na imagem, e o fim da fila de 10 minutos.** Para o
  Everton: o scanner deixou de estar dez minutos atrás do mercado. `hunter_core.events` ganhou
  `consume_batches()` + `ack_many()`: a guarda por `event_id` vira **um** `SMISMEMBER` pipelined por
  lote e a conclusão um `SADD` + `EXPIRE` + `XACK` — três idas ao Redis **por mensagem** viraram
  duas **por lote**. Medido no contêiner: 400 → **22 694 msg/s**. `consume()` não mudou de
  comportamento (a Astra recusou colapsar `event_id` repetido dentro do lote: se o handler falha, é a
  segunda entrega que conclui o trabalho). `redis[hiredis]` declarado no core: leitura de hot state
  de 23,8–32,9 ms → **3,3–4,3 ms** por mercado. Prova de 31 min com 200 mercados: lag de
  `market.ticks` ~95 000 → **0**, CPU do scanner 97–145 % → **54,7 %**, **170 683** cortes de
  bootstrap, 0 exceções. E o achado que só apareceu com a fila zerada: **o tick já nasce velho** —
  mediana de 3,70 s entre o carimbo do coletor e o `XADD` (ver [[Open Bugs]], T2.5g em voo).
- **`faabe3d` — contrato do Risk Engine na versão 2.1.** Para o Everton: o documento que rege o
  motor de risco passou a dizer exatamente o que o código faz, sem mudar **nenhum** limite seu.
  Entraram as invariantes provadas pela revisão adversarial da T3.2: `entry_ref` confrontado com o
  preço observado (`max_entry_deviation_pct = 0,5 %`), idade máxima do volume aplicada
  (`max_volume_age_s = 120 s`), caixa líquido das reservas pendentes, `resume()` recusado enquanto a
  avaliação automática ainda bloqueia, `sizing_price` = pior entre referência e preço observado, e a
  pendência de `AssumedCosts` aceitando `float` (fora de escopo, em [[Open Bugs]]).
- **`5f86028` — T3.2b: os cinco buracos que a revisão adversarial provou, fechados com os números
  dela virando teste.** Para o Everton: sem isto, o motor aprovaria entradas que a sua própria
  diretiva proíbe. (1) Carteira em 19 500 contra abertura de 20 000 era aprovada em tamanho cheio,
  porque a perda do dia vinha de campos opcionais com default 0 em vez do patrimônio; agora vem de
  `1 − equity/equity_início_do_dia`, **sempre**, e a divergência contábil é publicada
  (`daily_decomposition_gap`), **nunca** recusa — um descasamento de 6e-11 não pode impedir a
  construção do estado que protege uma posição. (2) `entry_ref = 100` com o mercado a 110 era
  aprovado, com perda real no stop de **1,18 %** do patrimônio contra teto de 0,25 %; agora
  `signal_validity` exige a banda de ±0,5 % e stop abaixo do preço observado, e o sizing usa o
  **pior** dos dois preços. (3) Volume de 45 minutos atrás sustentava a participação; agora vence e
  recusa. (4) Caixa 500 com 400 reservados aprovava mais 499,5; agora `available_cash` é líquido das
  reservas, cada uma carregando o **seu** `reserved_cash` (um candidato que declara custo zero não
  encolhe a reserva alheia). (5) `resume()` recusa a retomada enquanto os gatilhos automáticos ainda
  mordem. **204 testes** no núcleo.
- **`bbb4d57` — T2.5f: partições mensais provisionadas dois meses para trás, com guarda de
  retenção.** Para o Everton: o backfill de histórico deixa de bater em "não existe partição para
  esta data" — era o que impedia velas antigas de serem gravadas. `--months-behind` (default 2,
  porque um mês só não basta em março) e a tabela de retenção passou a ser lida **também** pelo
  criador: sem essa guarda, `market_snapshots` (retenção de 30 dias) ganharia uma partição às 04:07 e
  a perderia às 04:12 todo dia, sob `ACCESS EXCLUSIVE` no pai. Uma transação por pai, `lock_timeout`,
  saída 75 quando pula. Local: 31 partições criadas, segunda execução 0/115. **Na VPS: as mesmas 31**
  (medido hoje — 13 em `2026_07` e 18 em `2026_08`, 103 partições no total).
- **`bf4924b` — T3.2: o núcleo puro do Risk Engine existe.** Para o Everton: a peça que decide se uma
  proposta pode virar ordem saiu do papel — pura, sem IO, sem relógio, com `Decimal` em toda linha
  (o modelo **recusa** `float` na construção). Onze módulos: `RiskLimits` com o preset `PAPER_V1`
  congelado; `PortfolioState` com posições, reservas, exposição por ativo e por β-BTC, início do dia
  em São Paulo validado contra o `as_of` e pico monotônico; kill switch com os três escopos,
  ordenação por dicionário e `resume` casado; e o sizing como **mínimo de nove tetos** (risco por
  operação com custos de ida e volta, 1 % de participação líquida do que já está reservado, caminhada
  no livro até o slippage máximo, caixa, por ativo, total, β-BTC com `|β|`, risco agregado planejado,
  slots contando pendentes), publicando o teto que amarrou e dois contrafactuais. Arredondamento
  sempre **para baixo**. Nada disto executa nada: é o núcleo, e a T3.3–T3.14 é que o liga.
- **`da2fb49` — T3.7: β contra o BTC, versionado e com validade.** Para o Everton: o teto de
  correlação da sua diretiva (Σ|notional × β| ≤ 0,5 × patrimônio) precisa de um β que se possa
  auditar; agora existe. MQO com intercepto sobre 480 fechamentos horários ininterruptos de 30 dias,
  retornos simples (o consumidor é uma afirmação sobre dinheiro), R² **relatado e nunca portão**,
  `valid_until` ancorado no fim da janela — não no `as_of`, senão um job atrasado manteria um β vivo
  uma hora além da recomputação que deveria substituí-lo. Motivos de invalidade explícitos
  (`insufficient_history`, `gaps`, `btc_missing`, `degenerate_variance`, este último depois de a
  Astra reproduzir duas séries planas marcando β = 1, R² = 1, válido). BTC = 1 por definição. Sem
  `numpy`, sem `float`. **Ainda não medimos quantos mercados passam na validade** — está declarado.
- **`3dcb218` — o consumidor de `market.backfill.requested`: os pedidos de histórico do scanner
  finalmente são atendidos.** Para o Everton: era o **bloqueio mais alto do M2** — o scanner pedia 7
  dias de histórico para construir as baselines e ninguém escutava (97 mensagens no stream, nenhum
  grupo de consumo). Agora cada shard lê, só o dono planeja, e o dreno acontece num segundo estrato
  de prioridade **atrás** das lacunas ao vivo, com o orçamento que sobrar do ciclo. Idempotente por
  `event_id` e por lacuna; teto de 7 dias em pedaços de 240 min; recusas com motivo; envelope
  ilegível é posto de quarentena e **nunca** derruba o worker. Prova: 210 970 velas REST de mais de
  dois dias em 218 mercados; mercados com ≥ 3 dias distintos de velas de ~0 → **213**; buckets de
  baseline utilizáveis 1 065 → **3 220**.
- **`9626bf4` — T2.5c: o scanner decodifica cada linha do hot state uma vez, e as primeiras linhas do
  Radar apareceram.** Para o Everton: **as quatro primeiras oportunidades e as cinco primeiras linhas
  de `radar:scores` do projeto** existiram nesta janela. O scanner reconstruía cada `MarketContext` a
  partir de 1 500 linhas msgpack por tick (62,8 ms por mercado no contêiner). A janela persistente com
  invalidação por evento foi **recusada na revisão** com três contraexemplos concretos (uma vela de WS
  reescrevendo o miolo sem evento, o `INSERT DO NOTHING` do backfill que não produz segundo evento,
  uma chave perdida e recriada); o que entrou é a alternativa da Astra — a lista inteira continua
  sendo lida a cada tick e o objeto decodificado é cacheado **pela linha crua**, então remoção,
  reescrita, evicção e truncamento ficam corretos por construção. Medido: decode 62,8 → **1,7 ms**,
  custo por mercado 66,6 → **13,4 ms**, p99 da passada completa 15,1 → **3,23 s**.
- **`2c6bb2d` — R1: replay de oito políticas de saída sobre as entradas congeladas do Lab
  ([[EXP-0004-politicas-de-saida]]).** Pesquisa (`purpose = research_only`), **sem escrever nada**: a
  transação é `REPEATABLE READ, READ ONLY` e quem impede a escrita é o Postgres, não a revisão de
  código. Une num bloco só o T-005 (invalidação), o L1 (alvo assimétrico) e o L2 (sem alvo / canal
  oposto) do [[Registro de Tentativas]] — **8 políticas, 7 contrastes, Holm a 5%, efeito mínimo
  declarado 0,05 R**, sobre as **mesmas entradas** que o Lab já registrou. O replay **não
  reimplementa o acompanhamento**: um braço é um `TrackingPlan` diferente dobrado pelo mesmo
  `walker.walk` e fechado pelo mesmo `settle.settle`, com o plano reconstruído das colunas gravadas.
  **Portão passou:** reprodução de **trajetória 1,0000 em 339 linhas comparáveis** (limiar 0,9900),
  com **14 divergências só de liquidação** — atribuídas a ingestão tardia de funding como
  **compatível, não comprovada**, porque `funding_rates` não guarda instante de ingestão.
  **Resultado: inconclusivo por `B = 1`** — todas as entradas caem num único dia UTC, então o IC é
  indisponível (`single_block`) e o `p = 1` sai por construção; os sete contrastes daquela leitura
  são **exploratórios**, e os três com magnitude ≥ 0,05 R (`TGT-3` +0,056, `TGT-4.5` +0,112,
  `EXIT-NOTGT` +0,094) são aprendizado operacional, não confirmação. Três rodadas de revisão da Astra
  entraram no código **antes** da publicação (`EXIT-CHAN` mantendo a invalidação nativa; `as_of` como
  corte de **velas**, não só de população; corte comum de maturidade **antes** do pareamento —
  sozinho ele move `TGT-3 − base` de +0,118 para +0,056 R; portão antes dos contrastes;
  `input_digest` **e** `series_digest`). Três pendências ficaram abertas e estão escritas:
  `settle` sem corte temporal, `funding_rates` sem `received_at`, e `volume_anomaly` sem alvos
  informativos (L1 é, hoje, experimento de `momentum`). **Nada foi ativado.** No mesmo dia,
  `recompute_funding.py --apply` rodou **na VPS** (97 de 110 resolvidos, 13 seguem sem funding) e
  **ainda não** no local.
- **`docs(m3)` — o M3 planejado a partir da diretiva do Everton: carteira virtual e Risk Engine.** Ele
  respondeu às sete decisões que a oitava rodada devolveu (capital, `f`, `p`, `θ`, limiares de perda,
  modalidade, piso de liquidez) e foi além, com uma diretiva de sete partes mais uma lista de
  validação. Saíram: `docs/plans/M3.md` (14 tarefas, 6 ondas, checklist de aceite por tarefa),
  `docs/RISK_ENGINE.md` reescrito como **contrato v2**, ADR 0005, e a correção de `docs/ROADMAP.md` e
  `docs/PRODUCT.md`, que ainda punham o Risk Engine no M4 e a carteira no fluxo de onboarding.
  **Nenhum limite dele foi alterado**, e nove conflitos entre a diretiva e o sistema que existe hoje
  voltaram para ele em "Perguntas ao Everton antes de alterar qualquer limite" — a começar pelo maior:
  ele mandou operar **SPOT** e todo o sistema construído até aqui é **perpétuo**, sem adaptador spot
  (`binance/rest.py:223` recusa o que não for PERPETUAL, e a chave do livro no hot state colidiria).
  Decisão conjunta em três rodadas ([[Dialogos/M3]]), na qual a Astra derrubou seis afirmações minhas:
  o termo cambial calculado sobre o **caixa** em vez do equity (ela conferiu com `Decimal` e mostrou
  um erro de R$8.200 no exemplo); "reset = carteira nova" como saída legítima, que preservaria as
  linhas antigas e ainda assim reiniciaria patrimônio e pico e **destravaria um kill switch
  BLOQUEADO**; a saída de proteção executando com "o pior candidato disponível" quando falta livro,
  que é **fabricar proteção**; "o stop executa pior por construção", quando o preço pode sair melhor,
  igual ou pior; generalizar para as saídas o cancelamento terminal do restante, que deixaria unidades
  desprotegidas depois de um fill parcial; e as duas afirmações sem consulta, "só o BTC teria β
  válido" e "a participação será **sempre** o limitante" — os 46 USDT medidos vêm de **perpétuos**,
  numa janela histórica, e não descrevem a população SPOT futura. Todas corrigidas antes de o plano
  existir. As vinte e uma regras da rodada 8 ficaram marcadas no [[Strategy Backlog]] como adotada,
  substituída pela decisão do Everton, inaplicável ou pendente com a pergunta. **Nada foi
  implementado nesta entrega, e o M3 não declara modo autônomo:** as entradas são manuais, porque a
  ponte sinal → proposta não existe e sinal `research_only` continua recusado.
- **`7cf9e18` — S2-context: o contexto da estratégia passou a receber funding e open interest, e o
  sinal carimba o regime.** Para o Everton: as estratégias decidiam olhando **menos** do que o
  sistema já sabia — `funding` e `open_interest` chegavam `None` em **toda** avaliação, o que
  bloqueava a candidata de "funding extremo" do backlog, e `agent_signals.regime_id` nunca era
  gravado, então não dava para perguntar "como esta estratégia se sai em tendência?". Módulo novo
  `derivatives.py`: funding vem do durável (`funding_time <= corte`) e cai para o hot state só quando
  o durável não tem a linha ou o preço de marcação. **Open interest só é aceito do hot state** — a
  Astra construiu o contraexemplo que matou qualquer folga finita: `open_interest_history.ts` é o
  bucket arredondado do **início** de uma rodada de poll sequencial, então uma leitura feita às
  12:05:02 é gravada como 12:00 e nenhuma folga prova "lido antes do corte". Proveniência (fonte,
  `ts`, motivo) gravada nos dois casos. Ver [[Open Bugs]].
- **`d878fd6` — S2-funding: a liquidação é identificada por proximidade temporal, nunca por
  igualdade exata de timestamp.** Para o Everton: 69 dos 73 acompanhamentos que diziam "funding não
  apurável" tinham a linha real a menos de **2 segundos** do instante pedido — a maioria a **5
  milissegundos**. A grade real da Binance não é redonda (851 de 1 883 linhas com segundos ≠ 0) e o
  código casava por igualdade exata. A correção ingênua de dar tolerância era **proibida** (cobraria a
  mesma liquidação duas vezes) — e o código antigo já dobrava a cobrança quando havia duas linhas
  reais próximas. Agora todo o histórico lido é clusterizado por proximidade pura (2 s): um cluster
  cujos membros **discordam** sobre estar dentro da janela vira incerteza declarada, nunca escolha do
  lado conveniente; um cluster unânime precisa concordar em taxa e preço de marcação e conta como
  **uma** cobrança. Três desenhos foram derrubados pela Astra antes deste, e o motivo de cada
  rejeição está no docstring. Script `recompute_funding.py` (auditado, `--apply`, preserva o valor
  anterior em `meta.funding.previous`) — rodado **na VPS**: 97 outcomes recomputados.
- **`bd1d4d8` — T2.5b: bootstrap de baselines a partir das velas persistidas, refresh horário e
  prontidão que diz "bootstrapando".** Para o Everton: sem baseline, nenhum detector de anomalia
  pontua nada — o scanner ficava com 200 de 200 mercados sem score. O bootstrap faz **uma** passada
  de features por minuto (custo proporcional a minutos, não a features), em fatias cooperativas de
  50 ms a 40 % do relógio, retomável depois de restart e só quando **duas** fontes concordam (o
  arquivo e o registro no Redis) — a Astra recusou usar só `max(window_end)`, porque ele não
  distingue "escreveu tudo o que existe" de "escreveu e morreu". Uma correção dela evitou que a
  tarefa nascesse inútil: o refresh horário **apagaria** o bootstrap, porque ordena por recência e
  não sabe o que é maturidade. Prova: 28 mercados bootstrapados em 30 min, 9 909 revisões, 1 065
  buckets utilizáveis, e o scorer produzindo score elegível pela primeira vez.
- **`4bb2865` — T2.5-adapter: geração de conexão e marca de progresso fecham os dois buracos da
  prova de cobertura.** Para o Everton: sem isto o sistema poderia chamar de "contínuo" um intervalo
  que tinha um buraco dentro. A revisão da Astra mostrou que (a) o runner reconecta um socket caído
  sem terminar o gerador, então uma lacuna real cabia dentro de um intervalo declarado contínuo, e
  (b) um evento já retirado da fila e ainda não entregue é invisível para quem lê o tamanho da fila.
  O adaptador passou a expor `connection_generation()` e `queue_progress()`; a sessão de cobertura
  **quebra** com reconexão e recomeça em vez de esticar. É o commit que introduziu a exigência de
  fila exatamente vazia — corrigida em `fe8872c`.
- **`99685ff` — o `scanner-worker` recebe as credenciais de produção no override da VPS.** Para o
  Everton: o scanner subiu em laço de crash na VPS depois do deploy de `fa9f957`, tentando o banco
  com a senha de desenvolvimento. Mesmo erro de família do `strategy-worker` em `75fc59c`: override
  não herda o que não menciona.
- **`fa9f957` — o hash do ticker passa a ter dono por produtor; o volume REST não é mais apagado pelo
  `bookTicker` (KB-0044).** Para o Everton: `volume_24h`, `quote_volume_24h` e a variação de 24 h
  sumiam da tela e da base — sobreviviam em **6** de 55 709 linhas. Dois produtores complementares
  (o refresh REST, que traz volume e não traz cotação; o stream `bookTicker`, que traz cotação e não
  traz volume) escreviam o mesmo hash declarando propriedade sobre o conjunto **inteiro** de campos,
  e a regra do Lua apaga todo campo de propriedade ausente na escrita atual — cada um apagava o do
  outro. Agora a escrita declara a origem (`rest` ou `ws`) e cada origem é dona só dos seus campos.
  Corrigido também na VPS. Ver [[Resolved Bugs]].
- **`2544e82` — T2.2b: índice de minutos e barras de 15 min memoizados por contexto, byte a byte
  idênticos.** Para o Everton: é o que divide por ~6 o custo do bootstrap **e** da latência do
  scanner; a prova exigida foi que o resultado não muda em um único bit.
- **`d12464b` — migração `0005`: `hunter_worker` ganha o lock de linha em `feature_baselines`.** Para
  o Everton: o protocolo de retenção do banco era inexecutável entre a `0003` e esta — o `FOR SHARE`
  do scanner falhava com "permission denied" e o worker degradava para uma checagem de existência,
  sem se serializar contra um `DELETE` de retenção concorrente. A imutabilidade continua **inteira**
  na trigger (que recusa todo `UPDATE`, para todo papel, inclusive o dono); o `GRANT` entrega apenas
  o cadeado que a trigger não sabe expressar. O `downgrade` revoga **um** privilégio, nunca
  `REVOKE ALL`.
- **Rodadas 5 a 8 de aquisição de conhecimento — KB-0036 a KB-0075** (`562a0fa`, `b9605a8`,
  `7cc3956`, `2d4a296`, `65989bb`, `8616b83`, `47cc42a`, `30c1225`, `412e401`, `ac9c220`, `f6f9e05`,
  `5325d1b`, `548fddc`, `8f42b4d` e as correções da Astra em `ed105d5`, `31d7a23`, `1a29c93`,
  `6a915f3`, `a466e6a`): execução (tipos de ordem, lei da raiz quadrada, spread medido, custo por
  coorte), livros de estratégia (Turtles, três barreiras, contração de volatilidade, eficiência de
  Kaufman), meme coins (o rótulo como grau de liberdade, o piso de ATR que bane o BTC, a cauda de
  queda) e as **vinte e uma regras propostas para o Risk Engine** que alimentaram a diretiva do M3.
  Cada nota revisada pela Astra; em duas rodadas ela derrubou afirmações minhas que estavam erradas.
  **Nada ativa sozinho** — as candidatas ficam no [[Strategy Backlog]].
- **`72cebc5` · `0fa8bee` · `995ddb8` — rotina de aquisição de conhecimento** (`obsidian/11-KNOWLEDGE`): índice, modelo de nota e `Strategy Backlog`; notas escritas com as próprias palavras, com fonte, qualidade da evidência e uma hipótese testável no Lab; cada uma revisada pela Astra; **nada ativa sozinho**. Primeiras notas: KB-0001..0003 sobre momentum e rompimento de canal.
- **`88bac0b` — `default_sni` para clientes que chegam pelo IP puro.** Navegador não manda SNI para um endereço IP, então o Caddy respondia o handshake TLS com `internal error` e o Chrome mostrava `ERR_SSL_PROTOCOL_ERROR`. `compose.sh` passou a derivar o `default_sni` de `HUNTER_SITE_ADDRESS`. Com isso o Everton **abriu e viu** o `/ever/lab` em `https://169.58.116.99`.
- **`7e00f3b` — HTTPS no IP puro, com a CA interna do Caddy.** Os cookies de sessão do Clerk são `Secure`; em HTTP puro o navegador não os guardava e o sign-in entrava em laço infinito. A VPS passou a servir HTTPS com certificado interno — o aviso do navegador é esperado e está documentado em [[Deployment]].
- **`3654404` — S3b, a tela `/lab` (aba Sombra).** Rótulo fixo de pesquisa com os custos **declarados pela API**, funil por versão, as cinco métricas nomeadas com as definições ao lado, selo de maturação, nulos honestos **com motivo**, tabela de sinais virtualizada com chips de acompanhamento e resultado, excursões com limites e ambiguidade, painel de envelope sob demanda, estados vazio e 503. Navegação: `lab` → disponível.
- **`5bd17db` — T2.6 (radar/opportunities/anomalies/regime) + S3a (API do Shadow Lab).** E uma correção que vale por si: a autenticação passou a responder **503, nunca 500**, quando o Postgres ou o pool estão indisponíveis — 500 dizia "erro nosso" para o que é indisponibilidade temporária, e o cliente tratava errado.
- **`2587b9f` — o `seed` nunca mais toca uma `strategy_version` ativada.** Fecha o HIGH de deploy aberto na subida do Lab: o seed voltou a ser idempotente depois da primeira ativação (antes revertia as oito tabelas de referência a cada deploy). Com teste `seed → ativação → seed`. Ver [[Resolved Bugs]].
- **`98c15bc` — `code_ref` normalizado.** Fecha o HIGH de portabilidade: o digest congelado normaliza fim de linha e BOM, então o mesmo commit gera **um** `code_ref` no Windows e no Linux. Ver [[Resolved Bugs]] e [[S4-vps-lab]].
- **`02693e2` — `statement_timeout` por papel** (`hunter_app` 10 s, `hunter_worker` 15 s, ambos configuráveis), aplicado no servidor a cada `role_session`.
- **`bf1c382` — `setup_env.sh` recusa um `CLERK_ISSUER` que não seja URL.** Uma chave colada naquele prompt quebrava o JWKS em silêncio e derrubava toda a autenticação da VPS. O Everton **trocou a chave**; o valor nunca entrou no repositório, na base nem em log. Ver [[Resolved Bugs]] e [[Deployment]].
- **`72cfe72` — T2.3: baselines imutáveis, detectores de anomalia e classificador de estágio** (32 arquivos, +8163 linhas). Ver [[Features]] e [[Anomalies]] para o que ficou `implementado, sem scanner`.
- **Plantão da tarde: segunda avaliação datada nos dois experimentos, agora sobre a coorte da VPS**
  (`as_of = 2026-09-06T13:00:00Z`, `read_at = 13:26:35Z`). Com o horizonte **maturado** pela primeira
  vez, a leitura do momentum troca de sinal em relação à da madrugada: expectancy **−0,2102 R** (era
  +0,3053 R sobre acompanhamentos que resolveram cedo), PF 0,6084, 91 avaliáveis em 1 dia; volume
  **−0,2304 R**, PF 0,6539, 316 avaliáveis em 1 dia. **Os dois seguem `inconclusivo`** — o limiar é
  100 outcomes **E** 30 dias, e há 1 dia. Abertas as seções de **Hipóteses de falha** em
  [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]], com dois achados de pesquisa: (a) os
  invalidados são 35% dos resolvidos e nenhum foi lucrativo, mas o dado **não** decide o
  contrafactual — só dá para publicar ponto de equilíbrio e cenários de sensibilidade, não limites;
  (b) 69 dos 73 outcomes com "funding não apurável" têm a linha em `funding_rates` a menos de 2 s do
  instante pedido — é falha de **identificação temporal**, não ausência de dado — e o efeito medido
  do funding é de no máximo 0,028 R, duas ordens de grandeza abaixo da expectancy. Revisão em
  [[S4-hipoteses]].
- **Achado operacional do mesmo plantão: o backup do Postgres da VPS nunca rodou.** `/opt/backups`
  tem só um log com `Permission denied`. Registrado como HIGH em [[Open Bugs]] — é o único dado do
  projeto que não se refaz coletando de novo.

- **O Shadow Lab foi ao ar na VPS** (S4, etapa 3; prova em `.claude/state/vps-lab-proof.md`). `compose.sh update` aplicou a `0003_analysis` e subiu o `strategy-worker`; `momentum v1` e `volume_anomaly v1` ativadas pelo script auditado às 03:36:36 e 03:36:47 UTC (sem `--supersede`: não havia linha ativada antes), com a trilha em `system_events` incluindo a **recusa** anterior. Em 1 h 18 min: **109 sinais** (42 momentum em 42 mercados, 67 volume em 49), **109 com `purpose = research_only` e `cohort = prospective`, sem exceção**, 70 acompanhamentos encerrados (17 target, 27 stop, 26 invalidated), 203 slots por estratégia em `shadow_episodes` com 15 e 23 segurando acompanhamento, outbox **109/109 despachados** com uma tentativa e zero erro, `/ready` **200** com as seis checagens, **zero** exceção no log. **Zero `unavailable`** — o oposto da máquina local, onde o buraco de coleta de 02:04 a 02:47 UTC deixou 400 de 401 avaliações recusadas. Custo do Lab: **0,66% de um core e 81 MB**; o que satura a VPS é o `market-worker` a 100,56% com o universo padrão de 200. Apareceu também a população que a janela local não produziu: **19 dos 70 encerrados com `R_net = NULL` e motivo escrito** (18 `funding_missing:2026-09-06T04:00:00+00:00`, 1 `funding_ambiguous_exit`), todos preservando `meta.r_ex_funding` — o contrato do item 3 funcionando, e uma exclusão que toda avaliação sobre a VPS terá de contar. Três achados registrados em [[Open Bugs]]: o **`code_ref` não é portável entre Windows e Linux** (HIGH — mesmo commit, `git hash-object` idêntico, digests diferentes, porque quatro módulos do fecho de imports estão em CRLF na árvore do Windows e o digest é dos bytes em disco; a Astra reproduziu os hashes e fechou o diagnóstico), o **`seed` que não é idempotente depois da primeira ativação** (HIGH) e o **possível `funding_missing` falso** (MEDIUM). Segunda opinião em [[S4-vps-lab]], e ela derrubou quatro afirmações minhas: (1) a recomendação de pôr o `seed` no `compose.sh update` **quebraria o próximo deploy** — reproduzi na VPS: `RaiseError: strategy_versions ... is frozen after activation: code_ref cannot change`, com as oito tabelas revertendo juntas; (2) `funding_missing` pode ser falso, porque o cálculo exige timestamp exato numa grade e o histórico tem a liquidação em `04:00:00.005`; (3) readiness falsa **não** reinicia container (`restart: always` reage à saída do processo) e `/ready` verde **não** prova catálogo executável (zero versões também passa); (4) "nada perdido" não sai de comparar 109 despachos com um `XLEN` lido uma hora antes. As quatro corrigidas antes do commit.
- `75fc59c` fix(vps): **o `strategy-worker` subia com a senha de desenvolvimento e morria em loop.** A S2 acrescentou o serviço a `infra/docker/docker-compose.yml` e **não** a `infra/vps/docker-compose.prod.yml`; o override não herda o que não menciona, então na VPS o worker ficava com o `x-api-env` de dev em vez do `*prod-db-env`. Medido: `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "hunter"`, container em `restarting`, `compose exec` recusando entrar. `api`, `migrate` e `market-worker` não mostravam nada porque cada um tem o seu bloco lá — o Lab era o único serviço novo sem o dele.
- `82fc207` chore(sexta-feira): **rotina do plantão** — uma avaliação datada por turno nos experimentos ativos, acrescentada e nunca reescrita, com SQL rodado e colado, `as_of` + `read_at`, cobertura completa (incluindo horizonte maturado), limiar editorial aplicado mecanicamente e a proibição explícita de ativar a variante vencedora. Um turno em que o Lab não produziu nada **também** vira avaliação, com a cobertura que explica o silêncio: silêncio num log de pesquisa é indistinguível de instrumento quebrado.
- **`EXP-0001` e `EXP-0002` abertos** (tarefa **S4** do Shadow Lab) com a primeira **avaliação datada** sobre dado real: [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]], protocolo congelado, SQL reproduzível colado na página, `as_of = 2026-09-06T02:55:00Z` / `read_at = 02:56:27Z`. Momentum: 90 sinais (72 na coorte v1, 18 na v2), 57 encerrados avaliáveis, taxa de alvo entre toques resolvidos 0,8500 (v1) e 0,5000 (v2), expectancy +0,305274 R e −0,436204 R, PF 2,3973 e 0,2460. Volume: 107 sinais (92 + 15), 72 encerrados avaliáveis, taxa de alvo 0,6327 e 0,0000, expectancy +0,077965 R e −1,281367 R, PF 1,1367 e 0,0000. **Result: `inconclusivo` nos dois**, pelo limiar editorial (100 outcomes avaliáveis **E** 30 dias distintos; há 1 dia) — e por um segundo motivo que só apareceu na revisão da Astra: **0 dos 57** acompanhamentos avaliáveis do momentum tiveram o horizonte de 4 h maturado, então a população medida é inteiramente composta dos que resolveram cedo (no volume, 35 de 72, porque o horizonte é de 2 h). `PnL de carteira` e `Max Drawdown de carteira`: **não aplicável**. `status: sombra` passou a valer em [[Momentum Agent]] e [[Volume Agent]] porque a **prova operacional existe** (`.claude/state/s2-proof.md` + worker no ar), não porque o desenho ficou pronto. [[Strategy Performance]] deixou de ser página de espera e passou a ser a definição das métricas com o nome certo, apontando para os `EXP-NNNN`. [[Workers]] e [[Data Flow]] registram o `strategy-worker` como **escritor único** dos outcomes do Lab e as quatro camadas que tornam o desvio de pesquisa inalcançável pela execução. Revisão da Astra em [[S4-avaliacoes-shadow]]: cinco must-fix, **todos aceitos e aplicados antes de publicar** — PF com `COALESCE` no numerador (soma de conjunto vazio é 0, não desconhecido; a versão original chamava de "nulo" uma população inteiramente perdedora), coorte e propósito impostos no SQL em vez de só declarados, contagem de horizonte maturado, motivos exatos em vez de `LIKE 'late%'`, e snapshot `REPEATABLE READ READ ONLY` com a não-reprodutibilidade dita de forma dura.
- `5d0153b` feat(strategy-worker): **S2 — o Shadow Lab foi ao ar.** 65 arquivos, +9400 linhas. Consumidor de `market.candles.closed` com grupo próprio, contexto por mercado (hot state + Postgres no bootstrap), decisão só em fechamentos distintos do timeframe, entrada hipotética no open da barra de 1 min seguinte, motor de outcomes por barras, sinal + outcome + episódio + linha de outbox na **mesma transação** com ACK só após commit, `tracking_hold` publicado ao market-worker, supervisão/`/ready`/heartbeat e script de ativação auditado. Prova operacional em `.claude/state/s2-proof.md` (janela de 32 min contra a Binance real): 35 sinais, alvo/stop/invalidação/`late:delay`/`geometry` todos sobre dado real, outbox 35/35 despachados com 1 tentativa e 0 erros, `/ready` 200, 0 exceções em 40 min de log. **Três defeitos que os testes verdes não pegavam** foram corrigidos no caminho: (1) `consume()` bloqueia o `XREADGROUP` por 5000 ms enquanto o cliente Redis tem `socket_timeout = 5.0` — num stream ocioso os dois vencem juntos e o worker morria de `TimeoutError` **sempre que o mercado ficava quieto**; corrigido no consumidor com `CONSUME_BLOCK_MS = 2000` e backoff, e **o default de `consume()` continua perigoso para qualquer outro consumidor do projeto** ([[Open Bugs]]); (2) `code_ref` era o digest da **árvore inteira** de `hunter_core/strategies/`, então acrescentar um módulo — ou um comentário — fazia o worker pular **todas** as versões congeladas com `/ready` ainda verde (MUST-FIX 1 do `risk-engine-guardian`); virou digest do módulo mais o fecho transitivo dos imports, e `/ready` passou a ficar vermelho quando há linhas `active` e nenhuma executável; (3) a censura por gap decidia **no relógio**, sem olhar o que o coletor estava fazendo — perda correlacionada com a instabilidade do market-worker, o pior viés possível para um log de pesquisa; agora consulta `ingestion_gaps` e o veredito vira o sufixo do motivo (`:failed`, `:unregistered`, `:stalled`). Revisado por `code-reviewer`, `risk-engine-guardian` e Astra. Notas de desenho em `.claude/state/notes-S2.md`.
- `5154e1a` chore(state): briefs da onda 2 do M2 (T2.3 anomalias/baselines/stage, T2.6 API do radar, T2.9 outbox). 3 arquivos, +59 linhas.
- `88a3b0d` feat(db): **T2.1 — migração `0003_analysis`.** 19 arquivos, +4223/−240. Rótulos de enum congelados por revisão (um enum novo não reescreve o passado), `feature_baselines` imutáveis, identidade de episódio em `expired_at`, `evaluation_state`, `outbox_events` e seeds derivadas do registro de features em vez de listas copiadas à mão. Depende de `0002_shadow_lab` (S0) — foi por isso que a migração do M2 virou a `0003`. Revisada pelo `database-architect`, `code-reviewer` e Astra (`.claude/state/astra-review-T2.1-schema.md` e `-diff.md`).
- `487bc4a` feat(indicators): **T2.2 — Feature Engine v1.** 36 arquivos, +6946 linhas. `MarketContext` montado a partir do hot state, 28 calculadoras, `FeatureVector` com **qualidade e proveniência por feature** (uma feature indisponível é nula com motivo, nunca zero) e checkpoint ancorado do ATR de Wilder — a mesma fórmula que as estratégias do Shadow Lab usam, para que uma futura `v2` sobre as features do M2 seja comparável. Revisada por `code-reviewer`, `quant-engineer` e duas passadas da Astra.
- **M1 APROVADO** pela Sexta-feira em 2026-09-06, em nome do Everton, pela delegação de 2026-09-05. Critérios objetivos aplicados um a um em `docs/reports/M1.md` § VEREDITO. O que o Everton pode fazer agora: abrir `/ever/markets` e ver o **mercado real da Binance** — 50 perpétuos USDT com preço, bid, ask, spread, volume e variação 24 h ao vivo, `markets_ok` **50/50 = 100%**, badge de idade que envelhece sozinho em vez de congelar em silêncio, detalhe com velas de 1 min, book top-20, trades e derivativos, e a página System com heartbeats de verdade. **Ressalva registrada junto com a aprovação:** o M1 entrega 50 mercados, não os 200 do plano — os 200 estão *provados* (4 shards × 50 → `markets_ok` 198/200) e não *entregues*, porque a topologia que os sustenta compartilha a chave de heartbeat e faria a página System mentir. Passa a ser o primeiro item do M2.
- `27a0598` test(api): o teste da claim abandonada corria contra a própria janela de expiração — passagem de tempo agora determinística. Era o vermelho que o relatório do M1 carregava desde a T1.3 com um "confirmar verde" que ninguém cumpriu, e que falhava **3 em 3 com a máquina ociosa**. O diagnóstico antigo (`command_timeout` da T1.3) estava errado: o **teste** é que construía um app com `webhook_claim_stale_s=0.2` e corria um `asyncio.sleep(0.3)` contra o tempo de ida e volta de um POST HTTP real — medido, **o primeiro POST sozinho leva 0,516 s a 1,265 s**, então a reivindicação já estava vencida antes de o retry "imediato" começar e o takeover disparava como projetado. A idempotência do webhook está correta e não foi tocada. O conserto mantém as duas metades do contrato no mesmo `delivery_id` e na mesma ordem, trocando só *como* o tempo passa (`_age_claim`, que envelhece exatamente a coluna `claimed_at` que o `claim_delivery` compara). `code-reviewer` e Astra receberam a mesma pergunta adversarial — preservou ou enfraqueceu? — e responderam **PRESERVADO** independentemente. 17 passed, duas vezes seguidas.
- `fa24346` fix(ops): a topologia com shards não vai ao ar — a página System dela mente. A segunda opinião da Astra bloqueou a aprovação do M1 nesse ponto e foi acatada **mudando a entrega, não o texto**: com N > 1 shards todos escrevem `hb:market:{exchange}`, o `/system/market-status` mostrou `subscriptions: 636` (de **um** shard) com `markets_monitored: 200`, e um shard morto ficaria invisível atrás dos vivos. O override voltou para um processo × 50 mercados, com medição própria: `markets_ok` **50/50 = 100%**, CPU média 71,3% de um core (o perfil pré-T1.6b media 95,1% no mesmo tamanho). Corrigidas também quatro afirmações da prova sem número colado que ela apontou.
- `3167360` feat(ops): prova operacional da T1.6b — 200 mercados sustentados com 4 shards. Três topologias medidas em sequência contra a Binance ao vivo (`.claude/state/t16b-proof.md`): **1 processo × 200 colapsa** (ticker e book ausentes nos 200 em 15 min, 188 velas/min contra as 200/min da exchange, CPU média 103,2%); **2 shards × 100** oscilam entre 5,0% e 44,5% de hot state completo; **4 shards × 50 cumprem a meta** — `markets_ok` **198/200 = 99,0%**, 0 stale, 0 unavailable, ticker p50 850 ms, **202 linhas = 202 mercados distintos = 202 velas finais por minuto** durante seis minutos, gaps abertos 3.230 → 95 em ~20 min, CPU média por shard 36,6% / 54,6% / 61,2% / 64,2%. O py-spy (11.110 amostras) mostrou onde a CPU vai: `_handle_raw_message` 34,1% cumulativo, `model_construct` do pydantic 15,0% — e `run_recovery` apenas 4,4%, derrubando a suspeita de que o recovery era o gargalo. Ver [[Market Collector]] e [[Open Bugs]].

## 2026-09-05

- `4f9ab28` fix(market): símbolos não-ASCII da Binance cegavam o worker; canais unicode, caminhos de mercado escapados, estado por canal podado — o commit que a **prova da T1.6b** obrigou a escrever. A Binance USDS-M lista perpétuos com **símbolo em chinês**, e em 2026-09-05 quatro deles estavam no top 100 por volume 24 h (`牛来USDT` rank 19, `龙虾USDT` 42, `币安人生USDT` 63, `我踏马来了USDT` 81). **CRITICAL** (regressão da `b8998cc`): `shard_symbols` fazia `s.encode("ascii")`, o `UnicodeEncodeError` caía no `try` de `run_universe`, o universo ficava vazio — **um símbolo derrubava os 200 mercados**, `/ready` em 503 por 6 minutos, zero monitorados. UTF-8 é byte a byte idêntico para ASCII, então nenhuma fatia de shard existente muda. **HIGH** (achado da Astra): a gramática de canal em tempo real recusava `rt:market:binance:牛来USDT`, que o worker publica — o detalhe de um mercado top-20 mostrava um preço que nunca se movia; a revisão de segurança varreu os 0x110000 pontos de código e confirmou que `\w` só admite `L*`/`N*`, nunca separador, controle, formato, espaço ou curinga. **HIGH** (revisão de segurança, pré-existente): `apps/web/lib/api/markets.ts` interpolava os segmentos de rota sem escape, e `symbol="x/../../../metrics"` era normalizado pelo parser de URL **antes** de a requisição sair do servidor, alcançando endpoints internos com o bearer do próprio usuário. **MEDIUM** (pré-existente): `RealtimeHub._intervals` e `Throttle._last_emit` chaveados pelo nome de canal fornecido pelo cliente e nunca podados. **MEDIUM**: o e2e da T1.7 comparava a URL crua com o símbolo literal enquanto o link usa `encodeURIComponent`. Verificação real: market-worker **174 passed**, exchange-adapters **231 passed, 3 skipped**, realtime da API **59 passed**, vitest do escape **4 passed**, ruff/pyright limpos, 143 arquivos e 0 acima do orçamento. Revisado por `code-reviewer` (APROVA com dois nits, ambos tratados), `security-reviewer` (seguro como está) e Astra. Ver [[Market Collector]] e [[Open Bugs]].
- `66b8eb4` test(m1): T1.7 — suítes de integração e ponta a ponta do pipeline de mercado — `tests/integration/` sobe o pipeline inteiro com adaptador falso (adapter → Redis → Postgres → API → WebSocket) e cobre 18 invariantes de hot state e staleness, recuperação de gap (buraco interno, falha + cooldown), supervisão (morte de filho, watchdog, escalada, `/ready`) e o contrato produtor/consumidor via `handle_event`; `tests/e2e/markets.spec.ts` percorre lista → detalhe → busca → System e verifica o badge envelhecendo quando o WS é cortado; 6 verificações **ao vivo** contra a Binance ficam atrás de `HUNTER_LIVE_TESTS` (as destrutivas atrás de `HUNTER_LIVE_DISRUPTIVE_TESTS`), e a CI ganhou um passo nomeado para a suíte. 15 arquivos, +2828 linhas. Saída real na árvore commitada: **34 passed, 6 skipped** (as ao vivo, opt-in); ruff e pyright limpos. Lacunas assumidas e escritas no relatório: os testes ao vivo destrutivos nunca foram executados, e os cenários de janela de crash de liquidação e de perda de outbox ficam para a outbox do M2. Ver [[Workers]] e [[Market Collector]].
- `fc336d9` docs(shadow-lab): DECISÃO CONJUNTA Claude⇄Astra (3 rodadas) incorporada ao plano; tarefa S0 de schema criada; EXP-0003 reservado ao M2; `AGENTS.md` dá à Astra o mesmo toolkit dos agentes Claude — o desenho do **Shadow Lab v0** (estratégias avaliando o mercado real em modo sombra, sem carteira, sem ordens, sem execução) fechou em três rodadas de diálogo: protocolo congelado na primeira ativação da versão, envelope imutável da decisão, entrada hipotética no open da barra seguinte com limite de 120 s desde a barra de referência, custos declarados (spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado), `stop-first` como convenção pessimista, MFE/MAE nulos quando o OHLC não determina o extremo, idempotência por `uuid5` sobre a coorte, e métricas com nome certo (taxa de alvo ≠ taxa de lucro ≠ expectancy; **PnL e drawdown de carteira = não aplicável**). Nasceu daí a tarefa **S0** (migração `0002_shadow_lab` com trigger de congelamento, `signal_outcomes.meta`, `tracking_state`, `shadow_episodes` e `shadow_outbox`), que passa a preceder qualquer ativação, e o M2 (T2.8) cedeu `EXP-0001`/`EXP-0002` ao Shadow e ficou com `EXP-0003`. 8 arquivos, +527/−26. Transcrição em [[Dialogos/SHADOW|diálogo SHADOW]]; contrato em [[Architecture Decisions]].
- `b8998cc` perf(market-worker): T1.6b — parse mais leve no adaptador, hot state em lote e sharding do universo com eleição de líder — três frentes contra a saturação medida na T1.6: **(A) adaptador** com `model_construct` nos parsers quentes (com guardas explícitas), cadência `@depth20@500ms` em vez de 250 ms e varredura de fila mais barata; **(B) worker** com um único `EVALSHA` por ticker aceito, pipeline Redis por ciclo (ticker, book, ticks e publish juntos), janela de dedupe de trades em memória e caminhos rápidos de candle (`LSET`/`LPUSH`) no lugar de reescrever a lista inteira; **(C) sharding** por `MARKET_SHARD=i/N` validado na construção, fatia do universo por `crc32`, um líder por exchange com lock por token e snapshot versionado por CAS, seguidores lendo o snapshot ou o Postgres, e o processo solo mantendo exatamente o comportamento do M1 (sem lock, sem snapshot). Três módulos novos para caber no orçamento de 350 linhas: `coalesce.py`, `hot_state_candles.py`, `universe_leader.py`. 28 arquivos, +2009/−475. Suítes: **exchange-adapters 231 passed, market-worker 176 passed, core 269 passed**; ruff, pyright e `check_file_size` limpos. Ver [[Market Collector]] e [[Performance Overview]].
- `493c4ce` feat(ops): prova operacional do market-worker contra a Binance real — o `market-worker` subiu no Compose e rodou ~1h50 contra a Binance ao vivo com 200 mercados perpétuos USDT. **316.794 velas finais persistidas, com 800 velas comparadas campo a campo contra o REST e zero divergência**; 3.191 `market_snapshots`; 2.324 gaps recuperados. Cenários exercitados com saída real: reinício do container (0 duplicatas, `Exit=0`), corte seletivo de rede só para a Binance via sidecar `NET_ADMIN` no namespace do worker (watchdog nas duas rotas → fatal aos ~90 s → **`RestartCount` 0 → 1 sozinho**, provando o `restart: unless-stopped` que até aqui era só declaração), apagão de Postgres e apagão de Redis. **Seis defeitos que a suíte de testes não pegava** foram encontrados e corrigidos: `EXPIRE` recebendo um float no Lua do rate limiter (CRITICAL — o worker nunca carregava o universo contra Redis real, o fake de teste reimplementava o Lua em Python e escondia a tipagem); `dropped_events` contado no adaptador e nunca lido por nada (agora no heartbeat e em `market_dropped_events_total` — mostrou 1,15 M de descartes); queda de Postgres matando o processo pelo `run_heartbeat`; refresh de universo falhado dormindo 900 s e cegando o worker (agora backoff de 5 s com jitter); restart de Redis congelando o worker em zumbi silencioso por falta de `socket_timeout` no cliente; e o healthcheck do Compose com teto de 3 s dando falso negativo (latência real do `/ready` medida entre 0,01 s e 24,79 s sob carga). Fechadas também as pendências D4 (`SET LOCAL lock_timeout = '3s'`) e D12 (bounds de partição com `+00` explícito e `SET LOCAL TimeZone='UTC'`) e criado o agendamento diário de partições (`HUNTER_COMMAND=partitions` no entrypoint + cron na VPS). Veredito: **parcial** — falta capacidade (o processo satura um core com 200 mercados e o hot state de alta frequência não se sustenta), corrida de 24–48 h e prazo de convergência do backlog de recovery. Segunda opinião da Astra concordou com o veredito. Prova completa em `.claude/state/t16-proof.md`. Ver [[Market Collector]] e [[Monitoring]].
- `25012ff` feat(web): UX/UI polish — calm hierarchy, honest staleness states, command palette, density, green/red candles (T1.5b) — o contrato de `docs/DESIGN.md` aplicado à interface inteira: escala tipográfica de cinco tamanhos com três exceções nomeadas (13px no corpo da tabela, 11px em metadado, 10px na dica de atalho), duas densidades reais (40px/32px) com CSS e constante de virtualização na mesma fonte, vocabulário de staleness separado em dois eixos (dado: `OK`/`atrasado`/`gap`/`sem dado`; componente: `operacional`/`degradado`/`indisponível`/`sem verificação`), command palette `Ctrl`/`⌘K` sobre o `q=` real da API atrás de sessão, candles verde/vermelho, navegação por setas com árvore ARIA completa sobre a tabela virtualizada. 71 arquivos, +3565/−323. **Duas rodadas de revisão:** a primeira (`code-reviewer`, `security-reviewer`, Astra e QA visual em Chromium) fechou 4 HIGH, 9 MEDIUM e 3 LOW — hidratação em `useDensity` e `formatUtcWithOffset`, "Indisponível (not_configured)" na página de diagnóstico, geometria de scroll ignorando o `thead` fixo, Server Action que falhava aberta sem sessão, variação 24h nula pintada de verde. A segunda achou o que lint, typecheck e 309 testes verdes **não** pegavam: o `next build` quebrava porque um módulo `"use server"` exportava uma constante; `code-reviewer` e Astra chegaram independentemente ao mesmo achado de ARIA (`role="presentation"` na `<table>` cascateia e o grid expunha zero linhas para NVDA/JAWS); e a Astra achou `localStorage` sem `try/catch`, que deixaria a tabela inteira em branco com Web Storage bloqueado. Verificação real: lint exit 0 sem avisos, typecheck exit 0, **45 arquivos / 323 testes** verdes, `docker compose build web` → `Image hunter-web:dev Built`. Ver [[System Overview]] e [[Open Bugs]].
- `b8c4766` feat(market-worker): universe, ingest, persist, recovery, supervision, heartbeat (T1.3) — coleta de mercado ponta a ponta contra o Protocol da T1.2: universo monitorado com refresh de 15 min aplicando só entradas/saídas, ingestão WS com coalescência de 250 ms e hot state em Redis com idade por componente, fila limitada por itens/bytes/idade cujo descarte vira `system_event`, persistência em lote idempotente (candles 1m finais, `market_snapshots` por minuto, funding realizado, open interest em buckets UTC de 5 min, liquidações com `id` uuid5 determinístico), recovery de buracos por REST com `ingestion_gaps`, guarda de partição fatal no startup, supervisão por `TaskGroup` com watchdog por conexão e heartbeat. 20 módulos (maior: `universe.py`, 333 linhas) e 20 arquivos de teste; 58 arquivos, +7857 linhas. Implementado pela Astra; revisado pelo `database-architect` em duas passadas, pelo `code-reviewer` e por três passagens adversariais da Astra — CRITICAL-1, HIGH-2, HIGH-3, HIGH-4 e D1..D12 tratados. Verificação real: 139 testes verdes em duas rodadas seguidas, `packages/core` de 178 para 254, ruff/pyright limpos, 0 arquivos acima de 350 linhas. Ver [[Market Collector]].
- `9b6106f` feat(web): markets pages, live market status, workers table (T1.5) — `/[orgSlug]/markets` (tabela real com busca, ordenação, virtualização e badge de qualidade), detalhe com candles em `lightweight-charts`, book top 20, trades e derivativos com idade própria; Live Market Status no dashboard e no topbar; tabela de workers real na página System; `markets` vira `available` no nav-registry; tipos vindos do OpenAPI gerado. 32 arquivos de teste / 223 testes verdes, build validado no container. Revisado por `code-reviewer` e por duas passagens adversariais da Astra; 21 achados corrigidos, incluindo o spread exibido 100× menor e o preço que era dado como fresco por atividade do book.
- `00c7996` chore(types): regenerate OpenAPI types after T1.4 — `packages/shared-types` passa a conhecer as rotas de mercado e system (+651 linhas geradas).
- `1df4b87` feat(api): markets and system endpoints with per-component staleness (T1.4) — cinco rotas autenticadas sobre dados globais (`/markets`, detalhe com book e trades embutidos, `/candles`, `/system/workers`, `/system/market-status`), `Decimal` como string, UTC, role `hunter_app`; qualidade por componente com precedência `unavailable > degraded > stale > ok` e `stale_after_ms` no payload. 109 testes da tarefa verdes. Revisado por `code-reviewer`, `security-reviewer` e duas passagens adversariais da Astra; 20 achados corrigidos (decodificação defensiva, isolamento de erro do Redis por mercado, 503 honesto no lugar de lista vazia, anonimização de `hostname:pid`, tolerância de clock skew). Ver [[System Overview]].
- `97c36ff` feat(exchanges): Binance USDS-M public REST + WS adapter — duas rotas (`/public` e `/market`), assinaturas incrementais (`update_subscriptions` diff-only com ACK e catch-up), funding realizado paginado, fila limitada que nunca descarta kline final, rate limit por tentativa com gate de IP (T1.2 + T1.2b). 189 testes offline + 3 live (dado real nas duas rotas). Revisado por `code-reviewer`, revisão cruzada do `exchange-integration-specialist` e Astra adversarial; 16 achados corrigidos. Ver [[Exchange Adapters]] e [[WebSockets]].
- `a522bf1` docs(m1): DECISÃO CONJUNTA Claude⇄Astra — acceptance checklist for T1.2/T1.3/T1.4/T1.6
- `c58d4d1` docs(m1): joint Claude⇄Astra decision folded into the plan (recovery, liquidation identity ON CONFLICT (id, ts), supervision, per-component stalenes
- `becf1d9` docs(m1): Binance WS routes and @depth20 per official notice; Claude⇄Astra dialogue rounds 1–2 with concrete contracts (recovery, liquidation dedu
- `dd93d99` chore(rules): point the Astra rule at infra/scripts/astra.sh and the dialogue mode
- `606d5b6` chore(astra): single channel script (ask / run / dialogue / show) and Astra's second opinion recorded in the M1 plan
- `d76a0cf` feat(ops): market-worker compose service (restart unless-stopped, /ready healthcheck); entrypoint dispatches worker roles honestly (T1.6a, implemented
- `3399a19` chore(claude-md): fix guideline numbering
- `8df57ff` chore(agents): Astra second-opinion rule for every agent; Sexta-feira review protocol
- `3c31ef0` fix(docker): web image copies packages/shared-types (build was failing); sexta-feira: Astra runs unsandboxed by owner authorization
- `560c94c` fix(test): e2e workspace exposes 'e2e' instead of 'test' so 'pnpm test' no longer runs Playwright
- `4b24204` docs(m0): closure — DEPLOYMENT env table, README quickstart, CLAUDE.md commands verified, ROADMAP, milestone state, §77 report
- `f71059e` feat(exchanges): ExchangeAdapter protocol, stream channels and error types (M1 base)
- `415cc83` feat(core): normalized market domain types (T1.1)
- `c24a7b6` docs(obsidian): project knowledge base (32 pages, ADR 0003) and M1 wave plan
- `f153315` docs(audit): CURRENT_STATE.md — full repo audit at end of M0; ADR 0003 obsidian/ knowledge base

- `744fdf8` test(api): T11 integration suite — isolation, RBAC matrix, mutations, webhook, rate limits, websocket, auth edge cases
- `541ef78` fix(web): nav registry is plain data (segment + icon key) so the server layout can pass it to the client sidebar
- `b2e48b5` fix(dev): setup_env.ps1 parenthesizes each .env line (comma binds tighter than + in PowerShell, so all vars were joined into one line)

## 2026-09-04

- `4e7e878` fix(dev): setup_env.ps1 extracts the right key from NAME=value or multi-line pastes; prints lengths
- `330f861` chore(agents): record Astra (Codex) verified login and Windows shim note
- `ccc9139` chore(agents): Sexta-feira delegates execution to Astra via OpenAI Codex CLI (workspace-write sandbox, no commits, reviewed like any implementer)
- `4df500f` chore(dev): setup_env.ps1 optionally records OPENAI_API_KEY for the Astra second opinion
- `e18d1d7` feat(agents): Sexta-feira can ask GPT-6 Astra for a second opinion (infra/scripts/ask_astra.py, key from local .env, data not decisions)
- `336de92` docs(adr): 0002 provider-agnostic LLM layer with Anthropic and OpenAI GPT-6 Astra (Phase 2); env placeholders
- `43ee7c3` fix(dev): setup_env.ps1 ASCII-only so PowerShell 5.1 parses it
- `9a212b6` chore(dev): setup_env.ps1 creates the local .env from hidden prompts (keys never pass through agents or chat)
- `76b7cfd` chore(memory): obsidian-mcp v2 server for the vault (.mcp.json); vault initialized
- `a39ffde` chore(agents): Sexta-feira, Everton's personal agent; Obsidian vault (PARA structure, templates) as tier-two memory with MCP-only hook
- `e6a564a` chore(agents): product-owner agent for Everton (PT-BR entry point with authority over the full roster)
- `8e4d00d` docs(web): e2e script description
- `8fad06f` test(e2e): send browser navigation headers so the fake-key handshake assertion sees the 307
- `0b73fa4` test(e2e): assert the fake-key sign-in handshake without following the redirect
- `99c41bf` chore(state): repo moved to C:\dev\project-hunter; wave 5
- `7e90e81` test(e2e): playwright setup, public/api-health specs, clerk-gated signup+onboarding spec, CI e2e job (M0 T12)
- `8a454f4` fix(api): streaming body cap, JWKS max staleness, per-principal and WS limits, two-phase webhook claims (T06 re-review)
- `f48da11` fix(web): keep the dev-only /_design preview outside the Clerk middleware matcher
- `936b4b1` feat(web): accept-invite page, onboarding gating and step-jump guard, density pre-hydration (T09 review)
- `94b26a4` fix(api): auth/tenancy hardening from security review (T06 fixes)
- `c76c705` chore(dev): preview launch config for the web app
- `da557b5` feat(web): gold/green/black/white identity applied (DESIGN-1)
- `1bae973` feat(web): onboarding wizard, dashboard/system/settings pages, typed api client, generated OpenAPI types (M0 T09)
- `be82830` docs(design): gold/green/black/white identity, tokens and usage rules
- `ea24864` test(core): create app/worker roles in the shared container fixture; typed helpers for schema tests; nosec on constant-table SQL
- `137cb0d` chore(state): wave 4 started
- `5c5e412` feat(api): clerk auth, principal with JIT provisioning, RBAC (404 cross-tenant), tenant/user/bootstrap sessions with SET LOCAL ROLE, org/workspace/member/invitation/audit routers, clerk webhook, sql audit sink, websocket auth (M0 T06)
- `720102f` fix(db): users co-member policy read-only; organizations no DELETE for app role; explicit role check; real seed counts (T04 re-review)
- `907ebc2` chore(state): compose verified end to end; T06 in progress
- `12bf174` style: ruff format
- `1a15013` fix(docker): drop unused noqa in healthcheck (ruff RUF100)
- `c28c1bc` fix(db): schema hardening from cross-review (T04 fixes, 0001 amended in place, never deployed)
- `9c81634` fix(test): resolve per-member tests packages as namespace packages so a single pytest run works (CI python-test)
- `46993a0` fix(docker): loopback comment passes forbidden-patterns; HEALTH_PORT default 8001; DEPLOYMENT.md describes the real entrypoint (T07 review)
- `34da662` chore(docker): api/workers image with role entrypoint, web standalone image, dev and test compose (M0 T07)
- `a900926` test(api): redis bridge exposes is_running; pyright strict clean
- `c6eb407` fix(api): validation errors never echo input; /ready timeouts; proxy IP trust model; /metrics token gate; bounded request id (T05 review CRITICAL/HIGH/MEDIUM)
- `ba4ebe0` chore(state): T04 cross-review blocked, T04-fixes and T07 dispatched
- `149c542` fix(api): single-dispatcher redis bridge routed by message channel; broadcast evicts dead connections (T05 review HIGH/MEDIUM)
- `4988645` fix(web): decimal-safe money formatting, jittered ws backoff, accessible planned nav items (T08 review)
- `a9da9ea` test(core): narrow formatter type in logging test (pyright strict clean)
- `7d25f8a` chore: gitleaks allowlist for historical fixture literal; milestone state after rate-limit pause
- `4035cd4` test(core): mark fixture db password as FAKE per gitleaks allowlist convention
- `154ecea` feat(db): initial schema, RLS, partitions, roles, seeds and partition script (M0 T04)
- `9b7afe8` ci(security): value-based gitleaks allowlist, db-uri password rule, SHA-pinned actions, path-segment exemptions (T10 review)
- `4c107f7` fix: wave-2 review follow-ups
- `8db248a` feat(api): app factory, problem+json errors, middleware, health/ready/metrics, realtime classes (M0 T05)
- `b0f6012` feat(web): next.js 15 scaffold, dark-first theme, nav registry, clerk auth pages and app shell (M0 T08)
- `ca3cab3` test(core): runtime shutdown cleanup, /ready db-down branch, audit on exception, token-checked lock release (T03 review)
- `f7bcef7` ci: pipeline with lint, tests, migrations, security scans, forbidden patterns and gate (M0 T10)
- `e9f2091` chore(state): M0 wave 2 dispatched
- `88c2dd7` feat(core): settings, logging, db base/session, redis, events, runtime, audit, observability (M0 T03)
- `61c47e0` docs(workflow): eslint self-check command is the package test script (T02 review nit)
- `5b4cae8` chore(config): shared lint/type presets (M0 T02)
- `cd1c2d3` fix(repo): canonical install uses uv sync --all-packages (virtual root)
- `6652c5a` chore(repo): monorepo workspaces, tooling and python package skeletons (M0 T01)
- `a8d48a9` docs(plan): M0 approved; T02/T03 depend on T01, scope adjustments recorded
- `f925517` chore: toolchain complete — docker verified with hello-world, no blockers
- `a8e6764` chore: record docker desktop installed but blocked by missing WSL
- `06d9562` chore: record toolchain state (pnpm, uv, python 3.12 installed; docker pending)
- `b3fd8d4` chore: record verified hooks and eslint self-check after Node install
- `41ab588` chore: adopt vibe-coding-toolkit workflow (CLAUDE.md, agents, hooks, rules, memory, quality gates, M0 wave plan)
- `cbb36b1` docs: arquitetura, revisão da especificação, schema, pipeline, MVP e roadmap (pré-M0)

## Relacionadas

[[Resolved Bugs]] · [[System Overview]]

## Fontes

`git log --date=short --format='%h %ad %s'` (repositório `C:\dev\project-hunter`, capturado em 2026-09-05)

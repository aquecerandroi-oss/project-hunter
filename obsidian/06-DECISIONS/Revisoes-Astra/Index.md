---
tags: [astra, revisao, indice]
updated: 2026-09-08
status: registro
owner: sexta-feira
decided_on: 2026-09-06
by: astra
---

# Revisões da Astra — índice

Cada revisão é uma opinião do motor Astra da [[Mente da Sexta-feira]] sobre um plano, um diff ou uma decisão; o resultado (aceito/rejeitado e por quê) fica no kit da tarefa em `.claude/state/review-*.md` e nas páginas de [[Open Bugs]] / [[Resolved Bugs]].

- [[2026-09-08-shadow-lab-pronto]] — "o Lab está pronto?" (2026-09-08): **não** — 4 furos no caminho de replicação (T3.18c), 5 etapas da autonomia paper sem prova (T3.29) e a negação de serviço compartilhada do bucket do `web` (T3.28a-seguimento); `inconclusivo` no EXP-0006 confirmado
- [[S4-hipoteses]] — as hipóteses de falha do Shadow Lab sobre a coorte da VPS (5 must-fix; "intervalo do contrafactual" e "72 bugs de identidade" caíram)
- [[S4-vps-lab]] — a prova operacional do Lab na VPS (hashes reproduzidos; 4 achados, incluindo a recomendação que teria quebrado o deploy)
- [[S4-avaliacoes-shadow]] — as primeiras avaliações datadas do Shadow Lab (5 must-fix, todos aceitos antes de publicar)
- [[M1-plan]]
- [[T1.2]]
- [[T1.2b-round2]]
- [[T1.2b-round3]]
- [[T1.2b]]
- [[T1.3-A1]]
- [[T1.3-A2]]
- [[T1.3-final-fixes]]
- [[T1.3-partition-startup]]
- [[T1.4-fixpass]]
- [[T1.4]]
- [[T1.5-fixes-p1]]
- [[T1.5-fixpass]]
- [[T1.5]]
- [[T1.5b]]
- [[binance-skills-hub]]
- [[ccxt]]
- [[design-T1.5b]]
- [[review-T1.2-final]]
- [[review-T1.3-final]]
- [[review-T1.3]]
- [[review-T1.4-final]]
- [[review-T1.5-final]]
- [[review-T1.5b-final]]
- [[review-T1.5b-fixpass]]
- [[t16-proof]]
- [[t16b-sharding]]
- [[vps-bootstrap]]
- [[vps-executed]]
- [[vps-fixes]]

## Desde 19/09/2026 (síntese por tarefa/pesquisa; brutos em `.claude/state/astra-review-*.md`)

- 2026-09-27 — [[Prune-partitions-locks]] (podador sem travar a ingestão)
- 2026-09-27 — [[Create-partitions-lock]] (criador de partições reconhece o lock expirado)
- 2026-09-27 — [[Retencao-disco-execucao]] (código dos passos 1–5 do disco: backup por contagem, `history_v2`, 14/30/2 d, F1–F5 do quant)
- 2026-09-28 — [[Staking-sol-parado]] (staking do SOL parado; checagem de ativos estranhos inerte)
- 2026-09-28 — [[Token-state-history]] (histórico de estado das moedas; must-fix 2 do J fechado)
- 2026-09-28 — [[KB-momentum-semanal]] (H-024, momentum semanal em cripto grande)
- 2026-09-28 — [[Wallet-unrecognized-holdings]] (checagem de ativos estranhos na carteira ligada; adiar sem veredito, slots por programa)
- 2026-09-28 — [[Fechar-contas-vazias]] (ferramenta auditada `close_empty_token_accounts`: devolve o aluguel das contas de token vazias; intenção auditada antes do envio, só EMERGENCY recusa, a conta do golpe nunca é tocada)
- 2026-09-28 — [[KB-analise-grafica]] (KB-0167, análise gráfica depois do custo; candidatas C1–C3, nada registrado)
- 2026-09-28 — [[Confluencia-tela]] (T4.82, correções de code review pré-commit: `market_id` no filtro de sinais, status mutável de ordem antes/depois do cursor nos blocos A/B/C, notícia tardia sem destino, virtualização com altura variável — 5 rodadas até fechar; achou uma regressão real (recusa na criação sem `settled_at`) e um resíduo de pixels (Badge + padding > rowHeight compacto))

- [[T4.74-spot-desk]] — fundações, perfil, sinal, dinheiro e saídas da mesa `spot/1` (19/09)
- [[T4.77-close-atas-token2022]] — fechar ATAs cheias, extensão ao Token-2022 (19/09)
- [[T4.78-estrategia-2026-09-20]] — parecer noturno de estratégia + cooldown por mint (20/09)
- [[R65-rent-buys1m]] — recuperar rent da ATA, `buys_1m ≤ 25` (22/09)
- [[R66-pos-graduacao-pumpswap]] — custo pós-graduação na PumpSwap (22/09)
- [[R67-buys1m-oos]] — validação fora de amostra do `buys_1m` (23/09)
- [[R68-proxima-vela-pedagio]] — previsibilidade de perpétuos (KB-0150) (23/09)
- [[R69-coorte-nao-respira]] — percentil dentro da coorte (KB-0151) (23/09)
- [[R70-loaders-lab]] — carimbos/censura do Lab e vereditos H-001/002/005/006/007 (23/09)
- [[R71-identidade-mercados-spot]] — identidade dos mercados NEAR/WBTC/ORCA/XRP (23/09)
- [[R72-oscilacao-giro]] — H-009, reservas pós-gatilho (KB-0152) (23/09)
- [[R73-maior-comprador]] — H-010, concentração do maior comprador (KB-0153) (23/09)
- [[R74-subir-alvo]] — H-011, subir o alvo de saída (KB-0154) (23/09)
- [[R75-equilibrio-porta]] — H-013, moeda em equilíbrio (KB-0155) (23/09)
- [[R76-despejo-em-bloco]] — H-014, despejo em bloco (KB-0156) (23/09)
- [[R77-esperar-recuo]] — H-016, esperar o recuo (KB-0157) (23/09)
- [[Moinho-hipoteses-T4.80-T4.90]] — construção do moinho de hipóteses que sustenta R65–R81 (23/09)
- [[T4.89b-identidade-slot]] — origem inferida da identidade quando o slot é posterior à criação (23/09)
- [[T4.91-recuo-v1]] — braço de papel `recuo_v1/1` para a H-017 (23/09)
- [[Pedigree-timeout-indice]] — índice do timeout de pedigree por minuto (24/09)
- [[R78-recompra-bundle]] — H-015/H-018, recompra e bundle (KB-0158) (25/09)
- [[T4.92-ficha-diaria]] — ficha diária automática com campos Dataview (25/09)
- [[T4.93-obsidian-first]] — portão "Obsidian primeiro" nas ferramentas de mudança (25/09)
- [[T4.94-mint-busy-superseded]] — recusa durável de proposta com mint ocupado (25/09)
- [[T4.95-recuo-ctrl]] — braço de controle `recuo_ctrl_v1/1` (25/09)
- [[Lab-recuo-metricas]] — métricas e estados sem resultado do braço de recuo (25/09)
- [[Meme-refused-probe-apostrophe-guard]] — guarda de apóstrofo nas razões de recusa (23/09)
- [[R80-link-reciclado]] — H-020, link reciclado + coleta REST do pump.fun (26/09)
- [[R81-grafico-5min]] — H-021, gráfico de 5 minutos não existe na porta (26/09)
- [[R82-recuo-controle]] — H-017, o recuo pequeno empata com comprar na hora (KB-0162) (27/09)
- [[R83-maxima-24h]] — H-023, perto da máxima de 24 h não separa os sinais do Lab de cripto (KB-0163) (28/09)
- [[R84-momentum-semanal]] — H-024, evitar as moedas em queda de 14 dias não bate a cesta; sobrevivência auditada em 153 cópias históricas (KB-0166) (28/09)
- [[H-025-H-026-prereg]] — R85, desenho da retração de Fibonacci e da LTA diária: 6 must-fix aceitos numa emenda datada antes de qualquer evento (KB-0168) (28/09)
- [[H-025-H-026-resultado]] — R85, resultado: Fibonacci não confirma, retorno na LTA refuta, rompimento do topo não confirma; 4 defeitos de código corrigidos sem mudar rótulo (KB-0169) (28/09)
- [[H-027-prereg]] — R86, desenho da tendência diária (razão à média de 20 dias) como estado dos sinais do Lab: 5 must-fix aceitos numa emenda datada antes de qualquer desfecho (KB-0170) (01/10)
- [[H-027-resultado]] — R86, resultado: momentum refuta o tamanho, global não confirma (retrospectiva); 2 defeitos de instrumento corrigidos com saída idêntica; red-team e auditoria de dados como robustez pós-desfecho (KB-0170) (01/10)
- [[T4.96-escopo-teste-pequeno]] — corte do débito do escopo, diagnóstico da parada de 26/09 (26/09)
- [[T4.96b-scope-debit]] — corrida SigningLocked/admitted_orphan_expired (26/09)
- [[T4.97b-identity-breaker]] — disjuntor da identidade por mint (26/09)
- [[Confluencia-market-events]] — desenho de confluência de eventos de mercado (23/09)
- [[EXP-M26-design-R1]] — opinião pontual de database-architect sobre o desenho do EXP-M26 (26/09)
- [[06-DECISIONS/Revisoes-Astra/EXP-M26-F|EXP-M26-F]] — funil F: o mercado passa os pisos, a leitura de pedigree do minuto (6–14 s contra o corte de 8 s) reprova o instrumento; J e S parados (01/10)
- [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix|EXP-M26-pedigree-fix]] — conserto da leitura de pedigree do minuto (só as duas contagens na pista de 1 min; 9 154 ms → 39 ms): APPROVE_WITH_NITS, nenhum must-fix; as três revisões (banco, quant, código) em [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix-revisoes|EXP-M26-pedigree-fix-revisoes]] (01/10)
- [[KB-0171-custo-spot1]] — método do custo real da spot/1 (0,49 %/ida-e-volta em 0,05 SOL) e bug da constante de aluguel 2 039 280 × 1 488 440 confirmado no código; 4 must-fix absorvidos (KB-0171) (01/10)
- 2026-10-01 — [[Roster-advogado-defensor]] (cartões do Advogado de Jesus e do Defensor: anti-resgate com histórico de exposição, desfecho "não verificável", Astra chamada pela orquestradora)
- [[KB-0172-perdas-spot-1]] — perdas das 10 primeiras operações da spot/1: aluguel e cotação única confirmados; classificação refeita em dois eixos (incidente × econômico) com retornos brutos da mesma janela (KB-0172) (01/10)
- [[Spot-ata-rent-fix]] — correção do aluguel de ATA da spot/1: lido do `createAccount` da carteira na própria transação; script auditado `spot_fix_ata_rent.py` (ensaio por padrão, `--apply` do Everton); desenho 4 + diff 3 must-fix + guardião F1 (só fechadas travadas), todos absorvidos (01/10)
- [[Spot-exit-confirm]] — stop/alvo da spot/1 confirmados por uma segunda cotação (a executada), stop com prazo de 60 s em episódio durável; desenho 3 + diff 3 + revisão de código (stop do prazo não é evidência), absorvidos (01/10)
- [[KB-tendencia-diaria]] — base de evidência da C1/H-027 (KB-0173 a KB-0179): conta da deriva rebaixada a ilustração, emenda da H-027 incorporada, lucro em nível ≠ benchmark; 7 must-fix aceitos, 1 divergência parcial (01/10)
- [[T4.98-fechamento-noturno]] — o fechamento noturno morto há 8 noites (`wallet_max_sol` ausente em `launch_v0/1`) e o denominador de capital incompleto que a rodada 1 criou; REQUEST_CHANGES na rodada 1, corrigido na rodada 2 (27/09)
- [[Curadoria-2026-10-01]] — curadoria da base pela Astra: estados desatualizados em KB-0165, HOME, Open Bugs e 11 páginas de experimento corrigidos por acréscimo; índices pendentes listados em `.claude/state/curadoria-indices-pendentes.md` (01/10)
- [[2026-10-01-late-delay-do-lab]] — diagnóstico do `late:delay` do Shadow Lab (1.927 sinais, 06–10/09): incidente histórico mitigado; 3 must-fix aceitos (população perp×spot, janela 06–11/09 em vez de covariável, limite da frase da janela de 30/09); instrumentação proposta (01/10)
- [[2026-10-01-scanner-lag]] — o `scanner-worker` 2 h atrás e 14 h sem gravar (veto do índice único de anomalias + espiral do XAUTOCLAIM): mecanismos A e B confirmados, 2 furos do `superseded` aceitos e corrigidos; divergência escrita (ela prefere reter o lote + serializar, implementada só a reconciliação).
- [[2026-10-05-scanner-parada-0210]] — a segunda parada do `scanner-worker` (02/10 10:12Z): mesmo mecanismo, agora em `uq_opportunities_open_per_market` (726 das 728 falhas do log retido); a mitigação das anomalias disparou 726 vezes dentro de transações revertidas; alarme `scanner_persistence` (3 must-fix da Astra aceitos: flush vazio não é commit, relógio por sequência de falhas, resumo de exceção com lista de permissão); segunda rodada sobre a cura (retenção do lote com um único dono, `FlushLane`): `REQUEST_CHANGES` com 5 bloqueadores (resync antes de mutar, regime exposto antes do commit, toque velho, ACKs bloqueados, universo), todos corrigidos com teste por mutação.
- [[T4.8e-upgrade-02-10]] — o upgrade de 02/10 (pump, PumpSwap e taxas em 32 s) que derrubou o `meme-executor` no boot: builders intactos, mas `TradeEvent` +8 B e `SellEvent` da PumpSwap recusados; não mover o pino antes de consertar os decodificadores; 5 acréscimos aceitos (05/10)
- [[T4.8e-decoders]] — o diff que conserta os decodificadores sem mover o pino (cauda de 8 B do `TradeEvent`, 49 B do `SellEvent`, fallback do delta que de fato roda, `mark_gap` + contador nas pistas): cauda e fallback aprovados; 3 achados de cobertura preexistentes abertos (launch lane sem censura, mistura de mints, graça de 5 s); checklist do pino (05/10)
- [[T4.8f-pumpswap-guard]] — a simulação mainnet achou a venda PumpSwap recusada (`6062 InvalidPoolV2`: três remaining accounts novas) e o conjunto que prepara o pino sem aplicá-lo: `unexplained` da PumpSwap, bloqueio relido na fronteira da assinatura, guarda com PumpSwap e `pfeeUx`, fechamento único; boot só-saídas e layout cashback seguem abertos (05/10)
- [[H-028-forward-prereg]] — coorte prospectiva do B da H-026 (rascunho da H-028): contraste trocado para gatilho comum (B ∩ rompimento × rompimento sem toque A em 21 velas), suporte mínimo e K6 antes de qualquer rótulo, arquivo de velas por primeira observação, congelamento de texto + código + base; 6 + 4 + 2 must-fix aceitos; P não deve alcançar o piso até 2030 (01/10)

- [[Gitleaks-CI-2026-10-05]] — o `gitleaks` vermelho do CI (desde ~08/09): nenhum segredo real (579 falsos positivos), causa = gitleaks 8.24.3 ignora allowlist global + checkout raso; config revisto (`secretGroup` na regra de URI, FAKE por segredo, âncoras), versão fixada em 8.30.1; HEAD e histórico 0 achados, controles negativos detectados; severidade da redação: MEDIUM (security-reviewer) × HIGH (Astra) (05/10)
- [[CI-verde-2026-10-05]] — segunda rodada do CI: `pip-audit` (24 vulnerabilidades em pyjwt/urllib3/virtualenv, corrigidas por lock sem ignores), e os dois passos que o gitleaks vermelho escondia desde ~08/09 — `bandit` (120 B608; 28 `nosec` revisados + testes fora do escopo) e `pnpm audit` (13 high; overrides + 1 ignore sem versão corrigida, `braces`); `forbidden-patterns` com exceção por formato de arquivo (must-fix da Astra aceito: o `^[^#]*` global escondia flag em flow map YAML) (05/10)
- [[sec-ci-green-2]] — revisão de segurança do CI verde: aprovou as 29 `nosec`, o `ci.yml`, o `uv.lock` e o ignore do `braces`; MEDIUM `source-map-js` 1.2.1 -> 1.2.2 (o `pnpm audit` ainda saía 1) e LOW da exceção do `forbidden-patterns` por nome de arquivo (agora só `.env`/`.env.example`/`.env.<x>.example`, nunca `.yml`); vocabulário `1/yes/on` aberto (06/10)
- [[Alarme-de-disponibilidade-astra]] — o alarme externo de VPS fora do ar (GitHub Actions): aprovado como alarme básico; 2 must-fix aceitos (identidade da issue por label, destinatário do e-mail documentado e a provar); sem frescor de dados por falta de endpoint público (05/10)
- [[H-029-carry-prereg]] — R87, pré-registro do carry de funding protegido (à vista + perpétuo vendido, top-20 Binance): S7 sem antecipação; 7 must-fix aceitos numa emenda datada antes do run; filtro → ranking mantido contra a preferência dela (KB-0180) (05/10)
- [[H-029-carry-resultado]] — R87, resultado: A0 e A1 NÃO CONFIRMA, A2 limite de dado; rótulos reproduzidos por ela, 2 defeitos de contabilidade corrigidos sem mudar rótulo, conclusão restringida ao A1 medido (KB-0181) (05/10)
- [[H-031-prereg]] — R88, pré-registro da fatia do maior comprador (`pedigree_e2b` e `decision_tape`) como aviso de golpe: B admissível como extensão, não equivalente a A; 5 must-fix aceitos numa emenda datada antes de qualquer desfecho (KB-0188) (07/10)
- [[H-031-resultado]] — R88, resultado: H-031, A e B NÃO CONFIRMA; sha256 e as duas contas do empate de A reproduzidos por ela; 4 must-fix de descrição absorvidos sem mudar rótulo (KB-0188) (07/10)
- [[H-032-mayhem-prereg]] — R89, pré-registro da moeda Mayhem na sonda de recusadas do EXP-M23: 6 must-fix aceitos numa emenda antes da extração única; o portão do teto de SOL real (I2) nasceu do achado dela de que o papel corta a venda Mayhem sem o SOL da nossa compra (KB-0189) (07/10)
- [[H-032-mayhem-resultado]] — R89, resultado: NÃO CONFIRMA — instrumento (teto em 63 % das saídas Mayhem); D_adj e médias recomputados por ela; 3 must-fix absorvidos sem mudar rótulo (bug em Open Bugs, aviso ao EXP-M23, grade de imputação) (KB-0189) (07/10)

- [[wallets-engine]] — onda 1c do H-030: motor puro de seguir carteiras (FIFO, E-PnL de liquidação com errata, entidades por `known_at`, C-PnL = a própria política, `follow`/`control`/`control2` puros, contrato de preço §3.1, testes de vazamento e trapaças pegas); REQUEST_CHANGES em duas rodadas (7 + 2), tudo consertado com teste (05/10)
- [[wallet-tape-probe]] — onda 0 do H-030: desenho da medição da sondagem do programa inteiro (7 pontos antes da corrida, 6 depois; auditoria independente por bloco, "atrasado não é perdido", downtime até o primeiro log, fórmula de linha corrigida) (05/10)
- [[wallets-1a]] — onda 1a do H-030: `BuyEvent` da PumpSwap decodificado, leitor puro de logs → `SwapRecord` e `maxSupportedTransactionVersion` 1 (rodada 1: 4 must-fix — reservas e quote virtual, ordinal deslocado, pilha incoerente, quote por mint; rodada 2: identidade após linha perdida, e o motor 1c que ainda cota a pool sem a reserva virtual) (05/10)
- [[t48f-pin-move]] — pino da identidade do pump movido para o deploy de 02/10: guardião APPROVE com condições (entradas só voltam com teste Postgres de fechamento único verde e decisão sobre cashback); Astra concorda (05/10)
- [[wallets-1c-pricing]] — conserto do motor 1c do H-030: pool cotada em `Q_real + V` com sinal, pré-estado pelo fluxo exato do cofre (com LP), ponte pura `SwapRecord → Fill` com recusas nomeadas; Astra APPROVE na rodada 1; na revisão de código, 2 achados HIGH dela (pré-estado impossível vira pouso censurado e liquidez desconhecida não pareia) e o arredondamento da compra, todos fechados (05/10)
- [[wallets-1b-record]] — onda 1b do H-030: o `SwapRecord` diz se a curva estava completa no evento (tri-estado pontual, corroborado pelo `CompleteEvent`) e as mints da pool (pela instrução de swap, conferidas contra os cofres); 2 must-fix dela (conclusão órfã sem lacuna e trade recusado perdendo o lugar; sonda ainda binando quote não verificada) fechados, e o erratum do KB-0183: 51,7 % das vendas de pool estavam em pools com WSOL na base (05/10)
- [[pumpfun-releitura]] — releitura da superfície pública da pump.fun (06/10, `docs/PUMPFUN.md` §10) e implicações para o H-030: REQUEST_CHANGES no texto com 9 pontos, todos absorvidos (separar HTTP/bundle/REA/não testado, "nova" × "agora chamada", limites fortes demais, universo e `known_at` do corte, fonte por campo das fotos, reconciliação de `/user-trades`, `top-trader-trades` só descritivo, dados pessoais); o re-teste provocado achou `GET /coins/{mint}` com 404 (06/10)
- [[roster-batedor-rea]] — criação do agente batedor-rea: apoia (sonnet) com 5 must-fix (termos de uso, restrições, procedência e tempo, orçamento, privacidade); 4 absorvidos, escrita por pasta pendente de hook (06/10)
- [[wallets-1c-bis]] — onda 1c-bis do H-030: o motor de carteiras em memória limitada (replay da janela por mint sobre um estado carregado no início da janela, com dois relógios), igual ao `build_snapshot` em diferencial noite a noite (aleatório, fixtures reais t1a, roundtrip JSON; 18/18 mutantes mortos); desenho com 5 must-fix e diff com 2 (horizonte fora do domínio e carries residentes), todos fechados; a CPU da janela real continua aberta (06/10)
- [[pumpfun-rt-latency]] — sonda de latência do tempo real da pump.fun (NATS anônimo do site, boards, PumpPortal, `logsSubscribe` público; 06/10): rodada 1 com 7 pontos no instrumento (programas misturados, reconexão, reprise, elegibilidade assimétrica, assinatura × perna, tarefas sem supervisão, janela vazia) e rodada 2 com 6 no texto e nas correções, todos aceitos; as tabelas principais reproduzidas por ela; a credencial estática da home e o canal por carteira ficaram com o Everton (INBOX)
- [[wallets-cpu-step2]] — passos 1–2 do plano de CPU do motor de carteiras (H-030): perfil reproduzível (o stop por cópia domina e cresce mais que linear por mint) e sete remoções de trabalho repetido sem mudar regra; REQUEST_CHANGES com 2 must-fix (carteira repetida em `of_wallets`, RSS do Windows lido como 0), fechados; ela reproduziu os digests congelados com o código antigo e as 7 falhas dos testes de trabalho (06/10)
- [[paper-mayhem-cap]] — conserto do teto da venda de papel em moeda Mayhem (bug do R89): desenho com teto = SOL real observado + curve_cost_sol (4 must-fix absorvidos: fluxos externos preservados, pernas sem cofre compartilhado, carimbo de transição, docstrings falsos) e diff APPROVE_WITH_NITS; dois residuais abertos (KB-0189) (07/10)
- [[H-031b-prereg]] — pré-registro da H-031b, o gêmeo de papel sem `creator_dump` (`absorb_semdump_v0/1`, EXP-M27): I = D_semdump − D_orig correta; 6 must-fix aceitos na emenda 1 antes de existir o conjunto (população admitida pelas duas políticas, cobertura da vigia contra a fita, fidelidade pela entrada, IC básico e poder corrigido, parada e maturação, resíduo na mesa) (07/10)
- [[H-031b-diff]] — diff da H-031b (migração `0069`, chave `exit_on_creator_dump` em toda aposta, patch sequenciado de `lab_models`): BLOCKED com 3 must-fix absorvidos — deploy em duas etapas + exclusão de aposta do gêmeo sem a chave, trava `FOR UPDATE` na origem, `null` recusado (07/10)
- [[H-034-prereg]] — R91, pré-registro dos dois "subindo" isolados (`holders_rising`, `progress_rising`): 5 must-fix aceitos numa emenda antes dos desfechos (regime efetivo, suporte/censura operacionais, Holm fixo, estimador próprio com multiplicidade, unidade do retorno real); IC básico como decisório rejeitado (KB-0190) (07/10)
- [[H-034-resultado]] — R91, resultado: H, P e família NÃO CONFIRMA; saídas e hashes reproduzidos por ela; 3 must-fix de descrição absorvidos sem mudar rótulo (Holm composto, P na pista de eventos sem suporte, Holm de S1) (KB-0190) (07/10)
- [[H-033-prereg]] — R90, pré-registro do OI em nível (relativo à própria semana) nos sinais do Lab: 5 must-fix aceitos numa emenda antes dos desfechos (folga como suposição + sensibilidades 30/60 min, janela inteira e prova por `dispatched_at`, FE de dia com consequência fixada, falha fechada e regra global, exchange e unicidade) (KB-0191) (07/10)
- [[H-033-resultado]] — R90, resultado: momentum NÃO CONFIRMA, volume_anomaly LIMITE DE DADO, global NÃO CONFIRMA; corrida, lista e réplica reproduzidas por ela; 5 must-fix (redação de FE dia +0,0501 e blocos 3 d +0,0512 acima de +0,05; 4 de instrumento sem efeito nos números) (KB-0191) (07/10)
- [[06-DECISIONS/Revisoes-Astra/lab-cost-sweep|lab-cost-sweep]] — varredura de custo sobre os desfechos do Lab de cripto (diagnóstico, não hipótese; [[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal|KB-0192]]): núcleo aritmético correto; 6 must-fix aceitos (reprecificação condicionada, populações todos × com funding, horizonte ≠ custo, custo efetivo ponderado em vez de mediana, poder qualificado, redação de momentum/volume_anomaly) e ranking trocado — instrumento de custo antes da coorte da `mean_reversion v14` (07/10)
- [[H-036-prereg]] — pré-registro da H-036 (`mean_reversion v14` em coorte futura ao custo Binance medido; [[KB-0193-o-custo-binance-medido-nos-instantes-do-lab|KB-0193]]): rodada 1, 9 must-fix (sequencial por Haybittle-Peto/Bonferroni, REFUTA calibrado, precedência, função de decisão única, primário todo a mercado, export só de spread…) na emenda 1; rodada 2, 6 defeitos reproduzidos (quantil t exato, metades, população vazia, adiamento de REFUTA, p99, export da semana da consulta) na emenda 2; rodada 3 fechada, tudo antes de T0 (07/10)
- [[H-031b-db-review]] — revisão de banco da `0069` (gêmeo) e linearização com a semente do EXP-M26 (agora `0070`, retida até o J congelar): APPROVE depois de três ajustes — trava `FOR NO KEY UPDATE` (a `FOR UPDATE` travaria as inserções do worker pela checagem de chave estrangeira; medido), quinta guarda de downgrade, teste da corrida por `pg_blocking_pids` em vez de `sleep` (07/10)
- [[T4.8g-upgrade-08-10]] — o terceiro redeploy (08/10, 27 s): IDL não republicada pela 4ª vez, `buy`/`sell` e eventos iguais a trades reais (19/45 idênticos em todos os bytes), 12 simulações dos nossos bytes `err null`; mudou *dado* (`BondingCurve` 151→166 B, +76 200 lamports na compra em curva antiga; `Global` +1 byte); Astra concorda em mover o pino com as condições da T4.8f, 1 must-fix de integração fechado (350 linhas) e 1 de religamento aberto (reserva da compra sem o crescimento da curva) (08/10)
- [[t48g-pin-move]] — pino dos três programas no redeploy de 08/10: guardião APPROVE com condições (C1 escopo esgotado; C2 reserva +76 200, fechamento único PumpSwap, cashback, venda SPL clássica antes de reabrir compras); Astra sem must-fix (08/10)
- [[wallets-cpu-step3]] — passo 3 do plano de CPU do motor de carteiras (H-030): passadas 1–2 no coordenador, mints inteiros em processos `spawn` com redução exata (somas, uniões, máximo com ausência, posses concatenadas), digests congelados iguais com 1, 2 e 4 workers, 17/17 mutantes; desenho com 2 must-fix e diff REQUEST_CHANGES com 3 (interrupção no shutdown, janela móvel da sonda de densidade, parede × CPU nas razões), fechados; 2 workers 1,2–1,5× sobre 1 worker, mas não vencem o serial em noites de 3–15 s, e a densidade real por mint segue sem medida (06/10)
- [[06-DECISIONS/Revisoes-Astra/meme-cycle-metrics|meme-cycle-metrics]] — tempo de ciclo da cadeia e do Lab no `meme-worker` (trava de ciclo do §6.8 do EXP-M26, "instrumentar antes do seed"): REQUEST_CHANGES com 3 HIGH — o `HSET` extra precisava de orçamento próprio de 1 s, faltava proveniência (`run_id`/geração, publicada vazia no boot) e a comparação "antes × depois" exige série durável de ciclos individuais (p95 de p95 não é p95; proposta em `system_events` com retenção de 30 d, sem migração, não implementada); overrun é limiar de trabalho, não prazo perdido; **rodada 2:** zumbis de laço desligado (anúncio no topo do boot), cancel durante a publicação, orçamento único e o histórico durável por ciclo em `system_events` implementado — contrato do leitor (identidade `(loop, run_id, seq)`, janela por `ended_at`, `generation_start`/`generation_end`), cobertura da guarda ainda aberta (07/10)

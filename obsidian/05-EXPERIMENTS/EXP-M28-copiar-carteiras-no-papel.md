---
tags: [experimento, meme, pumpfun, carteiras, copia, nats, papel, pre-registro, h-037, m4]
status: pré-registrado. O conjunto de papel `copy_v0/1` ainda não existe e nenhuma carteira foi escolhida; nada é real
owner: quant-engineer
updated: 2026-10-09
origem: pedido do Everton de 09/10/2026 ("acompanhar a compra e a venda dele e replicar"), aprovado só em papel
previsao: "NÃO CONFIRMA ou REFUTA; média de r = pnl_sol ÷ sol_spent prevista em −0,05 por SOL; CONFIRMA exige ≥ +0,05 por SOL com IC de duas vias (líder × dia) acima de 0"
exp: EXP-M28
strategy: "meme/pumpfun - copiar ~20 carteiras do quadro público (mais até 4 do Everton, num estrato à parte): compra quando a carteira faz a primeira compra do mint, vende quando ela reduz a posição a metade do pico, com stop de 50 % e teto de 60 min"
version: "copy_v0/1 (estrato regra) e copy_everton_v0/1 (estrato escolha_everton, descritivo), research_only, clock copy; semente a fazer na tarefa E do desenho"
result: nao-iniciado
evaluable: 0
days: 0
tipo: pesquisa
hipotese: H-037
variavel: r por cópia da política congelada copy_v0/1, no estrato regra
populacao: cópias preenchidas do estrato regra com decided_at em [T0, T0 + 28 d), inclusive as invalidadas depois
efeito: —
ic: —
veredito: —
proximo_passo: emenda 0b do contrato leader_events; tarefas A/B/C em voo; depois I, F, G, X, o ensaio, R1, a escolha D com o Everton, a semente E, as revisões R2–R4 e o deploy H (T0)
classe_de_perda: —
mercado: meme
---

# EXP-M28 — Copiar carteiras no papel (H-037)

## Hipótese (congelada)

O texto decisório completo está no bloco **H-037** da [[Fila de Hipoteses]]. A pergunta: copiar no papel ~20
carteiras escolhidas pelo que a pump.fun publica dá lucro **a quem copia**, com o nosso atraso e o nosso custo?

As condições da cópia:

- **entrada** na primeira compra de cada mint feita por um líder, a partir de T0;
- **saída** quando o líder reduz a posição a ≤ 50 % do pico, com stop de 50 % e teto de 60 min;
- ficha de 0,05 SOL;
- latência nominal de 1,65 s entre a nossa decisão e o fill, e nunca no mesmo slot do líder.

A previsão é **NÃO CONFIRMA ou REFUTA**.

## Por que existe

- **O pedido.** O Everton pediu ([[2026-10-09-piloto-copiar-carteiras-no-papel]]) um atalho para o projeto das
  carteiras ([[EXP-M15-carteiras-vencedoras]], H-030) que não espere a fita do programa inteiro, o RPC pago nem o
  motor acelerado.
- **As priores são contra.** No [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]], os vencedores persistem, mas
  copiar 3 s depois dá 1,01× e o resultado empata com o controle. No [[KB-0142-kol-e-call-antecipam-ou-confirmam]],
  o selo KOL chega no pico. É a **8.ª** tentativa da família "quem está comprando".
- **O que é novo:**
  - a escolha pública congelada antes de T0 ([[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]]);
  - o canal da NATS por carteira, com fallback on-chain
    ([[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]],
    [[2026-10-06-nats-da-pumpfun-no-projeto-das-carteiras]]);
  - a saída que espelha o líder.

## Desenho

Fica em `docs/design/copiar-carteiras-papel.md`:

| Seção | Conteúdo |
|---|---|
| §1 | a escolha |
| §2 | o acompanhamento e a emenda do contrato |
| §3 | a regra e o preço |
| §4 | o armazenamento e a vista ao vivo |
| §8 | as revisões |
| §9 | as ondas |

O diálogo com a Astra está em [[Dialogos/copy-paper|copy-paper]], e a revisão do pré-registro em
[[Revisoes-Astra/H-037-prereg|H-037-prereg]]. A regra de escolha dos líderes (`copy-leaders-rule/1`, tarefa B) foi revisada em [[copy-leader-selection]].

## Parâmetros congelados (lidos pela pista em `copy_v0/1.params`)

| Parâmetro | Valor | Origem |
|---|---|---|
| `size_sol` | 0,05 | ficha da casa = `FollowPolicy.budget_lamports` |
| `min_trigger_sol` | 0,1 | `FollowPolicy.min_trigger_lamports` |
| `exit_leader_drop_fraction` | 0,5 (posição ≤ 50 % do pico, ou 0) | contrato do orquestrador; difere do H-030 (vendido > metade do comprado) |
| `stop_fraction` | 0,5 | `FollowPolicy.stop_fraction` |
| `time_cap_s` | 3 600 | `FollowPolicy.time_cap_seconds` |
| `exec_latency_s` / `stress_latency_s` | 1,65 / 3,9 | KB-0182: proposta → confirmação, p50 / p90, 143 compras |
| `fill_window_s` / `exit_window_s` | 30 / 60 | escolha do desenho |
| `pairing_wait_ms` | 300 | escolha do desenho |
| `max_attempts_per_leader_day` | 20 | `FollowPolicy.max_bets_per_entity_day` |
| `max_open_per_stratum` | 100 | teto de sanidade, por estrato |
| `fee_pct` / `priority_fee_sol` | 1,25 / 0,00005 por perna | taxa da curva do `absorb_v0/2`; ≈ 50 000 lamports de rede |
| `confirm_retries` | 3 em 30 s | escolha do desenho |
| `leader_silence_gap_s` | 60 | escolha do desenho |
| `horizon_days` | 28 | Everton: resultado em 2–4 semanas |
| `venues` | `["curve"]`, ou `["curve","pumpswap"]` com o aceite P antes de T0 | desenho §3.3 |
| `leaders` | o JSON congelado (estrato, posto, `known_at`, sha256); `copy_v0/1` leva o estrato `regra`, `copy_everton_v0/1` leva as carteiras do Everton (emenda 1) | seletor, tarefa D |

## Avaliação

(append-only; cada avaliação entra como seção datada)

### Avaliação de 2026-10-09 — pré-registro e desenho (nada coletado, nenhum desfecho)

- **Registro.** O bloco H-037 foi registrado às 04:45Z e a cópia congelada às 04:48Z
  (`.claude/state/h037/prereg_frozen.md`, sha256 `a6ce641b…`). O registro veio antes de qualquer escolha de
  carteira, do conjunto e de qualquer dado.
- **Rodada 1 da Astra: REQUEST_CHANGES com 8 must-fix**, todos absorvidos no desenho:
  - paginação e episódios no seletor;
  - as invalidadas ficam no primário;
  - emenda do contrato;
  - seletor de estado próprio;
  - funil durável e reinício;
  - fronteira com o executor;
  - isolamento do Lab;
  - T0 e parada.
- **Achados conferidos no código:**
  - o Lab lê toda proposta `approved` (`lab_repo.py:120`) e toda aposta `open` (`lab_repo_bets.py:107`). Sem a
    tarefa I, ele tomaria as linhas da cópia;
  - o executor seleciona por `mode = 'live'` sem filtrar o `kind` (`repo.py:111`), e `decide_proposal` muda o `mode`
    de qualquer proposta `proposed` (`approval.py:57`). Por isso a cópia nasce já `approved`/`paper`, e o guardião
    faz uma revisão limitada à fronteira.
- **Achado lateral (não verificado em produção).** As apostas do `launch_v0/*` (`clock = 'event'`) podem ser lidas
  pelo `_APPROVED` e pelo `_OPEN_BETS` do Lab, porque a exclusão do `lab_repo.py:51` vale só para o carregamento dos
  conjuntos. A tarefa I confere.

### Avaliação de 2026-10-09 (05:20Z) — emendas 1 e 2, decisão conjunta (nada coletado, nenhum desfecho)

- **Emenda 1 (04:58Z) e emenda 2 (05:09Z)** acrescentadas ao bloco H-037 da [[Fila de Hipoteses]], antes de existir conjunto, carteira ou dado. A emenda 1 trouxe dez itens:
  - dois conjuntos, um por estrato;
  - interrupção → NÃO CONFIRMA;
  - M e U particionando F, com S1 e S2;
  - denominadores dos portões;
  - REFUTA restrito às medidas, exigido em M e S2;
  - inferência fechada;
  - concentração;
  - poder como aproximação;
  - elegibilidade durável e recomposição depois de lacuna;
  - régua editorial.

  A emenda 2 trata a colisão do funil (`co_observacao`, `colisao_nao_admitida`).
- **Manifesto** (`.claude/state/h037/manifest.txt`): registro `a6ce641b…`, emenda 1 `776c134c…`, emenda 2 `d8c6aaca…`. O hash `6a9fe21b…` da emenda 1, citado na rodada 3 do diálogo, é anterior à correção do carimbo do cabeçalho (05:00Z → 04:58Z) para o relógio real. Nenhuma outra palavra mudou.
- **DECISÃO CONJUNTA** com a Astra na rodada 4 de [[Dialogos/copy-paper|copy-paper]]: nenhuma discordância de desenho. A revisão do pré-registro está em [[Revisoes-Astra/H-037-prereg|H-037-prereg]]. Os aceites de implementação continuam obrigatórios antes de T0:
  - 0b;
  - cortes de slot;
  - colisão, reinício e duplicata;
  - reserva de vagas e saturação;
  - isolamento do Lab;
  - R4;
  - X;
  - E2E;
  - R1–R3.
- **Régua editorial:** com 28 dias, o `result` desta página fica `inconclusivo` qualquer que seja o rótulo da Fila. Estender para 30 dias é decisão do Everton, antes de T0.


### Avaliação de 2026-10-09 (05:29Z) — emenda 3: regra de escolha da tarefa B (nada gravado, nenhum desfecho)

- **Decisão do orquestrador.** Adotar a regra enxuta `copy-leaders-rule/1` (`infra/scripts/copy_leaders_rule.py`, sha256 `d0460e85…85e18c`; revisão [[copy-leader-selection]]): 6 quadros do `/pnl-leaderboard` completos + ≤ 24 leituras de `/users`, ≤ 30 requisições, ordem pela média das posições nos quadros `realized`, até 4 carteiras do Everton.
- **O que sai:** o `/user-trades` paginado e o veto `top-holders-v2` (~600 requisições). Isso dá menos carga na pump.fun sob o risco aceito em [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]], ao custo de não haver detecção verificada de robô nem filtro de posse.
- **Hashes da regra:** `f56b5742…353d17` → `d0460e85…85e18c`. A mudança foi só nos itens 10–11, depois do primeiro dry-run.
- **Dry-runs:** dois, às 04:47Z e às 05:13Z, com 17 de 20 carteiras em comum. Nada foi gravado.
- **T0** vem depois da gravação do JSON definitivo e do início da pista.
- **Registro:** emenda 3 do H-037 na [[Fila de Hipoteses]], arquivo `.claude/state/h037/emenda3.md` (o sha256 está no manifesto). Na tabela de parâmetros acima, `leaders` passa a ser o JSON `copy-leaders/1` dessa regra.

## Fontes

- **Desenho:** `docs/design/copiar-carteiras-papel.md`.
- **Contrato:** `packages/exchange-adapters/hunter_exchanges/pumpfun/leader_events.py`.
- **Obsidian:** [[KB-0149-o-que-a-mesa-real-ensinou]], [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]],
  [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]],
  [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]],
  [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools]] e
  [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]].

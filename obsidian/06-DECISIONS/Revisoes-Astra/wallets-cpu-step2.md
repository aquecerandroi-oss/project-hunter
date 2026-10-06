---
tags: [revisao-astra, meme, carteiras, h-030, motor-puro, desempenho, cpu, equivalencia]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: quant-engineer
decided_on: 2026-10-06
by: astra
tarefa: passos 1–2 do plano de CPU do motor de carteiras 1c-bis — perfil reproduzível e remoção de trabalho repetido no trecho dominante, sem mudar regra
veredito: rodada 1 REQUEST_CHANGES com 2 must-fix de código (contrato de `of_wallets` com carteira repetida; RSS do Windows lido como 0), fechados e confirmados por ela na rodada 2; rodada 2 REQUEST_CHANGES só no registro das medições (2 itens, corrigidos); equivalência confirmada com o código antigo carregado do git
---

# Revisão da Astra: CPU do motor de carteiras, passos 1–2 (H-030)

Plano acordado em [[wallets-cpu]] (decisão conjunta da rodada 2): medir, depois tirar trabalho repetido, uma mudança por vez, com referência congelada independente. Motor: [[wallets-1c-bis]]. Bruto: `.claude/state/astra-review-wallets-cpu-step2.md`. A medição e as sete mudanças estão na seção "Medição" de [[wallets-cpu]].

## O que ela conferiu, rodando

- **Os digests congelados batem com o código antigo.** Ela carregou `wallets` e `curve` do commit `84704fa1` direto do git, em memória, sem checkout, e recalculou `wallets_golden.json`: iguais.
- **Os testes de trabalho têm dentes.** Contra o motor antigo, `test_wallets_cpu.py` deu `7 failed, 2 passed`: falharam exatamente os sete testes das remoções.
- **Sondas extras sem divergência:** 60 combinações de delay, timer e empates; 20 vendas com o contexto Decimal externo alterado, átomos até `10**100` e reserva real negativa ou zero.
- `uv run pytest packages/indicators/tests/meme -q`: 215 passed (antes dos consertos abaixo).

## Must-fix (2), fechados

| # | Achado (cenário dela) | Conserto, com teste que falhou antes |
|---|---|---|
| 1 | `MintTape.of_wallets(['A','A','B'])` devolvia os eventos de A duas vezes; o filtro antigo devolvia uma. O motor estava protegido (`Entities.wallets_of` dá `frozenset`), mas o contrato do helper novo estava errado | Deduplica as carteiras antes de juntar as posições (`set(wallets)`). Teste `test_the_wallet_index_returns_the_filtered_subsequence_even_with_a_repeated_wallet`: falhou na cópia do estágio G, passa agora |
| 2 | O pico de RSS no Windows saía 0: `GetProcessMemoryInfo` sem assinatura declarada falhava (erro 6) e o retorno era ignorado | Assinaturas declaradas (`HANDLE`, `DWORD`, `BOOL`), falha vira "indisponível" (`None`). **Sem teste persistido** (é script de pesquisa, sem suíte): a sondagem leu 56 MB num processo, e na rodada 2 a Astra confirmou a leitura real e o `None` numa falha simulada. **Os `peak_rss_mb: 0.0` dos arquivos `profile-2026-10-06-step1-before*.txt` não valem** |

## Nice-to-have: o que entrou e o que não

- **Entrou: G calcula o piso só quando há evento a checar.** Com `stop_fraction = sNaN` e uma fita só com o gatilho, o código antigo fechava pelo timer; o G ansioso lançava `InvalidOperation`. Agora o piso é calculado no primeiro evento varrido. O teste novo falhou na cópia do G e passa agora.
- **Entrou: o comentário de A.** A justificativa "todo pouso fica depois da entrada" não vale para todo delay ou timer. O argumento correto está no código: um evento anterior à entrada nunca checava o stop, e se ele encerrava a varredura, o primeiro evento posterior também encerra.
- **Entrou: o teste do memo.** Ele limpa o LRU e exige exatamente uma conversão; antes aceitava ≤ 1, o que um cache já aquecido satisfazia.
- **Entrou: controles da medição.** Rodada nua (sem wrappers) como número principal; o memo é esvaziado antes de cada chamada medida, para todos os estágios partirem iguais.
- **Fica registrado, sem conserto: o limite da equivalência em B.** `Reserves("curve", 10**1000008, 1, 0)` lançava `Overflow` no preço marginal descartado e agora devolve 0. Está fora do domínio econômico do H-030; não vira recusa nova.
- **Não entrou: separar os RNGs do gerador.** `wallet_scale` muda o fluxo do RNG, então `entities_x0.5` não tem as mesmas fills da base (14 116 contra 18 852). Por isso a matriz publica as contagens efetivas de cada configuração. Isolar de verdade pediria uma fita-base reaproveitada; fica para quando a variável importar.
- **Não entrou: trocar o LRU global por memo por fita.** Ela própria manteria o LRU: chave de dois inteiros, valor imutável, contexto fixo, sem look-ahead. Ressalvas para o passo 3:
  - cada processo terá o seu cache, então os 8,1 MB medidos não são orçamento compartilhado;
  - o índice preguiçoso da fita não é seguro para threads que compartilhem a mesma fita.

## Rodada 2: código aprovado, registro das medições corrigido

Bruto: `.claude/state/astra-review-wallets-cpu-step2-r2.md`.

- **Código:** os dois must-fix e os nice-to-have absorvidos estão fechados. Ela rodou `pytest packages/indicators/tests/meme`: 217 passed.
- **Aritmética:** ela conferiu a extrapolação e a meta (2 × 2 × 3 600 × 10⁶ ÷ 217 M = 66,36 µs/fill).
- **REQUEST_CHANGES só no registro**, com 2 must-fix, ambos corrigidos em [[wallets-cpu]]:

| # | Achado | Conserto |
|---|---|---|
| 1 | Dois números sem fonte no arquivo citado. Os 140 µs/fill estão em `run-2026-10-06.txt`, não no par head/tree. Os 2,7 s do mint HOT só estavam no log do scratchpad | As duas fontes passaram a ser citadas. O registro de estágios agora traz o mint mais caro de cada rodada. O HOT aparece com as duas medições de cada lado: 11,0–14,7 s no head, 2,7–7,1 s no G2 |
| 2 | A tabela misturava tempos da passada 3 com contagens da passada 4. Os "20–40 %" de ruído subestimavam a dispersão (+117 % e +185 % registrados). "G2 sempre faz menos chamadas que F" era falso na janela vazia (empate). Atribuir `burst_120` à carga era hipótese | Passadas em colunas separadas; dispersão publicada; empate corrigido; carga marcada como hipótese |

Nice-to-have aplicados: a origem dos 389 µs/fill de `fills_16k` (o rerun) e a faixa de cópias, 17–73 %, que exclui a janela vazia (0 %).

## Rodada 3: revisão de código (code-reviewer + Astra, 06/10): `stop_fraction` não finito

Bruto: `.claude/state/astra-review-review-wallets-cpu-step2.md`. O `code-reviewer` deu APPROVE_WITH_NITS: as sete remoções são idênticas para entradas válidas, a independência da referência congelada foi conferida contra um arquivo do `84704fa1`, e os mutantes morrem. A Astra achou dois cenários reproduzidos, os dois com `stop_fraction` NaN/sNaN:

1. O piso era calculado antes de saber que a cotação é `None` (curva completa). Com `sNaN`, isso trocava `closed/time_cap` por `InvalidOperation`, ou o inverso, conforme a ordem dos eventos.
2. A comparação `Decimal(quote) <= floor` tinha saído de `localcontext(CONTEXT)`. Com `NaN` e o trap de `InvalidOperation` desligado no contexto do chamador, o HEAD lançava `InvalidOperation` e o diff devolvia `closed/time_cap`.

**Severidade divergente:** a Astra marcou must-fix; o revisor, LOW. Os dois concordam que a entrada está fora do domínio econômico: nenhum parâmetro congelado do H-030 é não finito. O orquestrador mandou fechar pelo caminho barato, e assim foi feito:

- **`FollowPolicy` e `RankingParams` recusam qualquer parâmetro Decimal não finito** (NaN, sNaN, ±Infinity) ao serem construídos, com o erro nomeado `NonFiniteParameter` (`params.py`), que traz o campo.
  - Vale para todos os campos Decimal das duas classes, não só `stop_fraction`: em qualquer um deles, NaN muda o fluxo de controle (comparações de elegibilidade, relógio, saída do líder, R).
  - Teste novo `test_wallets_params.py`: falhou antes (o erro não existia) e passa agora, para cada campo e cada valor não finito.
- **A comparação do stop voltou para dentro de `localcontext(CONTEXT)`**, como no HEAD. O ganho de G passa a ser só a multiplicação do piso, uma vez por cópia: o teste de G agora conta as chamadas de `_stop_floor` (1, contra 500 antes), não os contextos.
- O teste do caso sNaN da rodada 1 saiu: a política que ele montava agora é recusada na construção, e a recusa está coberta em `test_wallets_params.py`.

Verificação depois do conserto:

- `uv run pytest packages/indicators/tests/meme`: 220 passed; `uv run pytest packages/indicators`: 1 671 passed.
- Os digests congelados não mudaram (`test_wallets_golden`).
- Pyright strict, ruff, o portão de 350 linhas e o lint da base estão limpos.

## Divergências

Nenhuma de mérito. Ela lembrou que a faixa "copies 57–88 %" não descreve todas as configurações: em `history_5d` são 28,9 % de copies e 48,0 % de `window_books`. A medição publicada traz a tabela inteira.

## Relacionado

[[wallets-cpu]] · [[wallets-1c-bis]] · [[wallets-engine]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[Revisoes-Astra/Index|índice]]

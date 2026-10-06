---
tags: [revisao-astra, meme, carteiras, pumpswap, pumpfun, decodificador, versao-1, onda-1a, h-030]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-05
by: astra
tarefa: onda 1a do projeto "seguir carteiras lucrativas" — decodificador do BuyEvent da PumpSwap, leitor puro logs → SwapRecord do programa inteiro e maxSupportedTransactionVersion 1 em tx_rpc.py e rpc_wallet.py
veredito: rodada 1 REQUEST_CHANGES com 4 must-fix (todos aceitos e consertados com teste que falhou antes); rodada 2 ainda REQUEST_CHANGES com 1 must-fix de identidade após perda de linha (aceito e consertado) e 1 de integração que cabe ao motor 1c (registrado em Open Bugs); concorda com a semântica monetária, a recusa de caudas não provadas e a mudança para a versão 1
---

# Revisão da Astra: onda 1a do H-030 (`BuyEvent`, leitor de logs, transação versão 1)

Código: `packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py`, `.../pumpfun/swap_record.py`, `.../pumpfun/program_logs.py`
(novos, **sem ligar a nenhum worker**) e `tx_rpc.py`/`rpc_wallet.py` (`maxSupportedTransactionVersion` 0 → 1). Fixtures reais `t1a_*` com proveniência
em `tests/fixtures/t1a_provenance.json`. Conhecimento medido: [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]].
Contexto: [[wallet-tape-probe]] (onda 0) e [[wallets-engine]] (onda 1c); desenho em [[carteiras-lucro-design]]. Brutos:
`.claude/state/astra-review-wallets-1a.md` (rodada 1) e `astra-review-wallets-1a-r2.md` (rodada 2).

## Rodada 1 — o que ela disse e o que foi feito

| # | Achado (cenário de falha) | Decisão |
|---|---|---|
| 1 ALTA | O `SwapRecord` perdia o que precifica a PumpSwap: o evento traz as reservas de **antes** do trade, o `Fill.Reserves` pede **depois**, a `virtual_quote_reserves` e a taxa LP separada sumiam. Na fixture `5Smr…` ignorar 25 730 818 627 de reserva virtual | **Aceito.** O registro agora entrega reservas **sempre pós-trade** (na pool derivadas do fluxo exato do cofre: compra soma `with_lp_fee` e tira `base_out`; venda tira `quote_out − lp_fee` e soma `base_in`), `virtual_quote_reserves` e `lp_fee_lamports`. Provado contra o "antes" do **trade seguinte** da mesma pool (61 pares reais numa varredura avulsa, base e quote; três pares fixados por fixture). Medido de passagem: sem a reserva virtual a compra de 38 387 041 lamports cota 32 468 689 |
| 2 ALTA | Base64 inválido ou payload curto não consumia ordinal: A inválido e B válido → B recebia 0 na leitura viva e 1 na recuperação completa, colisão e contagem dupla | **Aceito.** O ordinal é reservado antes de validar a linha. Teste: A corrompido (duas formas), B continua igual ao da leitura limpa (identidade e conteúdo) |
| 3 MÉDIA | A pilha aceitava retorno de programa que não está no topo e saltos de profundidade sem lacuna: um retorno trocado deixava uma linha do programa estrangeiro ser atribuída ao pump com `gap=False` | **Aceito.** Pilha estrita (`stack_inconsistencies`, contado uma vez) e, depois da primeira inconsistência, nenhuma linha é atribuída (`unattributed_data_lines`). Os mutantes da guarda foram mortos (um sobrevivente, `self.broken` em `_data`, ganhou teste próprio) |
| 4 MÉDIA | Quote "SOL" por igualdade de quantidades (`quote_amount == sol_amount`) deixava uma quote USDC com valores iguais entrar como lamports; o teste mudava mint e quantidade juntos | **Aceito.** Só a **mint** decide (a nativa, toda zero, em todo evento real lido); o teste cobre quantidade igual e diferente |

Nice-to-have aceitos: o leitor não muta mais a lista `accountKeys` da transação do chamador (`keys += …` era um defeito do `sell_event.py` também, corrigido nele em uma linha; o de `trade_event.py` ficou em
[[Open Bugs]]); `ProgramLogsRead.other_events` lista `(programa, discriminador)` dos eventos que não viram swap (um tipo novo de swap aparece em vez de sumir). **Aceito em parte:** "ampliar a prova v1 até a
contabilidade" — `rent_labels`/`ata_close_refund_lamports` ganharam teste; `decode_pumpswap_fills` e `spot_send_rules.fill_from_transaction` do meme-executor foram rodados **à mão** (fora do repositório, sem erro numa fixture v1), porque o
pacote da exchange não importa serviços.

**Discordou, e a divergência é de formulação:** "legacy/v0 byte-idênticos" não estava provado pelos testes (o mock devolve o mesmo objeto por construção). **Certo** — por isso entrou
`tests/live/test_live_tx_version.py` (marker `live`, opt-in, nunca no CI): contra o nó público, a transação v1 é recusada a `0` (`-32015`) e servida a `1` igual à fixture, e legacy e v0 respondem **idêntico** a `0` e a `1`
(3 passed). Ela mesma reexecutou e retirou a objeção.

## Rodada 2 — verificação dos consertos

Ela reexecutou os testes (112 passed, mais 11 do `pricing.py` e 3 do ao vivo) e confirmou: reservas pós-trade corretas para `buy_exact_quote_in`, venda com cashback, pool sem criador e pool com reserva virtual
(dez comparações independentes com os saldos finais dos cofres); pilha estrita sem padrão legítimo de log **completo** que a viole; compatibilidade legacy/v0 provada contra a RPC real.

| # | Achado | Decisão |
|---|---|---|
| 1 ALTA | **Depois de uma linha perdida o ordinal ainda colidia.** Com a primeira linha de evento trocada por `None` o segundo swap virava ordinal 0 (reproduzido). E o runtime pode descartar uma mensagem grande, imprimir `Log truncated` e manter as menores seguintes (algoritmo do `LogCollector`, reproduzido por ela): pilha coerente não basta | **Aceito.** Depois de `Log truncated` ou de entrada não textual **nada mais é atribuído**: só o prefixo confiável é lido, o resto é `unattributed_data_lines` (lacuna), sem adivinhar quantos eventos sumiram. Testes novos: linha trocada por `None`, marcador no meio, e "qualquer linha danificada só pode emitir swaps idênticos aos da leitura limpa" (todas as posições, três transações). **Consequência registrada:** numa transação de log truncado a recuperação precisa dos eventos `emit_cpi` das inner instructions (o log recuperado tem o mesmo corte); esse leitor **não existe** e fica para a onda 2 |
| 2 ALTA (integração) | O motor 1c ainda perde a reserva virtual **e** a LP: as duas cotações (compra e venda) usam `state.sol_lamports`, e `_pre_state` reconstrói a quote anterior 76 775 lamports acima do evento numa compra e 364 066 numa venda (exatamente a LP). Também: a reserva virtual pode ser **negativa** | **Aceito como diagnóstico; não corrigido aqui** (arquivos do 1c fora do escopo). Entrou em [[Open Bugs]] com o contrato que ela pediria (quote real + virtual com sinal + LP; cotar com `Q_real + V`; desfazer pelo fluxo exato; teste da ponte evento real → `SwapRecord` → `Fill`) |
| nice | O teste cita 61 pares mas fixa três; asserção explícita de mesma pool; no ao vivo distinguir `error` de `result: null` | **Aceitos**: redação honesta no teste e na nota (varredura avulsa de 05/10, três pares fixados), `assert` explícito, o ao vivo falha em erro de RPC e só pula quando o nó podou a transação |

**Divergência escrita (ordinal):** ela **discorda** de "o ordinal por linha `Program data:` equivale sempre ao de `emit_cpi`" (não é garantia do protocolo) e não abriu must-fix porque não achou linha extra nas 29 fixtures que
examinou. **Concordo e escrevi assim** em vez de afirmar equivalência: o teste novo compara a sequência **inteira** de eventos de cada programa (swap ou não) nos logs e no self-CPI em 11 fixtures reais e a docstring diz "observado, não
garantido". Ela também não apresentaria a derivação das reservas como prova universal de um layout futuro: idem, está escrito em [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]].

## Mutação

13 mutantes manuais (reserva derivada, LP, atribuição, ordinal, pilha, mint da quote, parâmetro da versão nos dois clientes, cópia de `accountKeys`, `other_events`, `virtual_quote_reserves`) foram mortos; o único sobrevivente
da primeira volta (a guarda `blind`) ganhou teste. Rodados à mão, o script não está no repositório.

## Relacionado

[[wallet-tape-probe]] · [[wallets-engine]] · [[carteiras-lucro-design]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[Exchange Adapters]]

## Guardião (05/10, noite): APPROVE

O guardião do caminho do dinheiro revisou `tx_rpc.py`, `rpc_wallet.py` e `sell_event.py`, além dos testes v1, e não achou must-fix.
- **Decodificadores:** nenhum consumidor de `getTransaction` ramifica pela `version` da resposta. A única checagem de versão (`jupiter/versioned_tx.py:93`) valida os bytes que nós vamos enviar. Os decodificadores do executor rodados por comando nos 4 v1 reais e numa cópia reformatada como v0 dão resultado igual (`same_as_v0=True`), sem mutar a tx do chamador.
- **Reconciliação:** a das nossas tx (legacy/v0) não muda. Uma resposta v1 que antes virava `rpc_unreachable_fetching_fill` agora é lida uma vez, e nada é reenviado.
- **Efeito operacional:** o laço de carteiras do meme-worker (`wallets.py:175-180`) ficava com o cursor parado numa tx v1 para sempre. Agora ele anda, então espere um acúmulo único de `meme_wallet_trades`. Essas tabelas não alimentam o executor nem a admissão.
- **Astra:** "DONE — concordo com o diff; nenhum must-fix".
- **Sugestões (não bloqueiam):** um teste de regressão no executor (erro de leitura → não confirmado → v1 válido → confirmado uma vez) e uma redação mais precisa: "JSON idêntico nas tx amostradas", não "byte a byte"; `trade_event` ainda muta `accountKeys`.

Fonte: `.claude/state/astra-review-guardian-wallets-1a-v1.md`.

## Revisão de código (05/10, noite): REQUEST_CHANGES, dois casos residuais depois da rodada 2

O `code-reviewer` rodou a Astra sobre o conjunto (`.claude/state/astra-review-review-wallets-1a.md`) e reproduziu dois defeitos de integridade do leitor que os 143 testes não pegavam. Os dois foram aceitos e consertados com teste que falhou antes.

| # | Achado (reproduzido na fixture de duas vendas com cashback) | Decisão |
|---|---|---|
| P1 | **Linha de evento sem contexto de invoke só contava `unattributed` e não deixava o leitor cego.** Mantendo a linha do evento 0 sem o frame e depois o frame completo da segunda venda: leitura limpa `[(0, 121423), (1, 976016)]`, leitura danificada `[(0, 976016)]` — a segunda venda herdava a identidade da primeira | **Aceito.** A linha órfã agora torna o leitor cego (nada depois dela recebe identidade). A frase da docstring "uma linha ausente interrompe a leitura" estava forte demais: o que se vê é linha não textual, `Log truncated` e linha de dados sem frame; um evento apagado do **meio de um frame intacto** não é visível pelos logs (só as inner instructions mostrariam), e a docstring agora diz isso. Testes: órfã + frame completo; apagar, uma a uma, toda linha que não é de evento e exigir que o que sobra seja idêntico (identidade e conteúdo) ao da leitura limpa |
| P2 | **Log que termina com frame aberto voltava `gap=False`.** Cortando os logs logo antes do segundo `Program data:` (perda de sufixo, sem marcador) a leitura saía limpa com 1 swap | **Aceito.** Novo contador `open_frames_at_end`: pilha não vazia no fim, sem estar cego antes, é lacuna. O teste antigo que exigia leitura limpa para um `invoke [1]` sem retorno cristalizava o erro e foi reescrito com um frame completo. Testes: corte antes do segundo evento; **todo** prefixo que deixa frame aberto é lacuna; transação completa termina com pilha vazia |

Também aceitos: o valor da cauda sem nome (`trailing_u64`) agora é conferido contra os 8 últimos bytes do corpo e fixado (169 685 numa fixture), porque zerar o campo passava; o aluguel da compra v1 é fixado em **1 513 840 lamports** (antes o teste aceitava tudo `None`); `0.9 * int` virou comparação inteira; contagens das docstrings alinhadas (4 `buy_exact_quote_in` + 3 `buy` nas fixtures; "61 de 61" qualificado como varredura avulsa com 3 pares fixados); docstring de `rpc.py` corrigida; o arquivo de teste de 531 linhas foi dividido (`test_swap_record.py` para a normalização). Guardas que não tinham teste ganharam: compra que tira mais base do que a pool tem, venda que paga mais quote do que a pool tem, timestamp não positivo, e cashback dentro de `fee_total` da compra (corpo sintético rotulado, que reprova na conservação). Mutantes: 6 novos, todos mortos.


## Item 2 da rodada 2: consertado no motor (05/10, noite)

O item de integração (o motor 1c perdia a reserva virtual e a LP) foi consertado em `packages/indicators/hunter_indicators/meme/wallets/`. A pool passa a ser cotada em `Q_real + V` com sinal, o pré-estado sai do fluxo exato do cofre e há uma ponte `SwapRecord → Fill`. A prova usa estas fixtures, e a Astra aprovou sem must-fix: [[wallets-1c-pricing]].

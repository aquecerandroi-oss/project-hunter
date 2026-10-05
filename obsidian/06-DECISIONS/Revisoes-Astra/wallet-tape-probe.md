---
tags: [revisao-astra, meme, carteiras, rpc, medicao, onda-0, h-030]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-05
by: astra
tarefa: onda 0 do projeto "seguir carteiras lucrativas" — desenho da medição da sondagem de 2 h do programa inteiro (pump + PumpSwap) por RPC público
veredito: rodada 1 (desenho da medição) 7 must-fix, 5 aceitos e 2 aceitos em parte, todos antes das corridas; rodada 2 (resultados e código) REQUEST_CHANGES no código com 6 must-fix, todos aceitos e consertados com teste que falhou antes; concorda com a direção do go/no-go (público reprovado, pago candidato a piloto, armazenamento sem capacidade aprovada)
---

# Revisão da Astra: desenho da medição da sondagem de 2 h (onda 0)

A sondagem está descrita em [[carteiras-lucro-design]] (§2 e §6, linha 0; `docs/design/seguir-carteiras-lucrativas.md`),
aprovada pelo Everton em [[2026-10-05-seguir-carteiras-lucrativas-aprovado]]. Código em
`infra/scripts/research/2026-10-05-wallet-tape-probe.py` e `infra/scripts/wallet_tape_probe_*.py`; a revisão bruta é
`.claude/state/astra-review-wallet-tape-probe.md`. A medição e os números estão em [[EXP-M15-carteiras-vencedoras]]
(avaliação de 05/10) e na seção "Onda 0 — medição" do desenho. A Astra revisou o desenho **antes** da corrida de 2 h,
a partir de um teste de 100 s.

## O que ela disse e o que foi feito

| # | Achado (cenário de falha) | Decisão |
|---|---|---|
| 1 | "A transação que invoca os dois programas deveria chegar nas duas assinaturas" é um diagnóstico **condicional** à transação ter chegado por pelo menos uma. Se o provedor perde um bloco nas duas conexões, a discordância fica em zero e centenas de swaps somem | **Aceito.** A métrica passa a se chamar "discordância de entrega no subconjunto observado". Entrou uma auditoria **independente**: `getBlock` de um slot escolhido sem olhar o websocket (ponta HTTP − 60 slots), toda tx que **menciona** um programa contra as assinaturas que o websocket entregou para aquele slot. Blocos anteriores à primeira entrega, e janelas com reconexão em curso, ficam fora ou em balde separado. O fechamento deixou de forçar a expiração da janela de deduplicação |
| 2 | 55/55 de logs == inner instructions compara contagens, não completude nem identidade; um evento truncado nunca entra na amostra | **Aceito em parte.** O `getTransaction` continua como fidelidade **de contagem** das entregues, e passou a ser lido junto da auditoria de blocos (completude). Comparar `payload` e ordem fica para a onda 1a (a corrida já estava no ar). Registrado também que 0 divergências em 55 ainda admitem ≈ 5 % no limite unilateral de 95 % |
| 3 | Disponibilidade parecia melhor do que foi: erro de assinatura não derrubava a conexão (o `slotSubscribe` mantinha o socket vivo), o downtime fechava na conexão e não no primeiro log, nada drenava a fila no fim | **Aceito.** Erro de assinatura força reconexão; o downtime vai do corte até o **primeiro log**, e a queda ainda aberta no fim entra (`downtime_s_incl_open`); bytes contados na recepção, antes da fila; fila drenada antes do resumo; taxas por tempo total **e** por tempo ativo |
| 4 | O `slotSubscribe` vai pelo mesmo cano dos logs: não vê atraso nesse cano. A "última mensagem processada" pode retroceder | **Aceito.** Referência de lag = `getSlot(confirmed)` por HTTP menos o **maior** slot recebido (negativos visíveis), idade do último log a cada consulta, RTT do HTTP, idade na fila local e atraso do laço de eventos. O lag do `slotSubscribe` ficou com o nome `..._same_pipe_NOT_independent` |
| 5 | A extrapolação de carteiras/dia (limite inferior, Heaps, "limite superior" linear) não é limite nem intervalo; duas horas dominadas pelos mesmos robôs achatam a curva | **Aceito.** A **curva** (carteiras distintas por minuto e por nº de swaps, por programa e por grau de validação da identidade) é o resultado; Heaps e a extensão linear viram "cenários", sem linguagem de teto |
| 6 | O deslocamento 152 da carteira do `BuyEvent` está certo no IDL, mas o teste só olhava comprimento | **Aceito.** Teste novo: em três compras reais (uma roteada), `pool` e `user` lidos nos offsets 120/152 **são** as contas 0 e 1 da instrução `buy` da PumpSwap. Fixar o hash do IDL fica para a onda 1a |
| 7 | GB/dia e custo precisam incluir o que a sondagem não mede (WAL, índices reais, resolução de pool, recuperação, fila, CPU) | **Aceito em parte.** CPU, atraso do laço, idade da fila, RTT e picos por minuto entram. **Não medidos** e escritos como tais: WAL, escrita real no Postgres, RSS (o `psutil` não está instalado), cache de pool, custo de recuperação, períodos de reserva inválida de pool. O tamanho da linha no Postgres continua **estimativa por fórmula** |

**Também aceito** (a ideia de fundo dela): dividir o aceite em duas decisões. Depois das 2 h só se decide o **no-go
econômico** e a ordem de grandeza; o **go operacional** do coletor 24/7 exige piloto no provedor e no ambiente
pretendidos, cobrindo pelo menos um ciclo diário e horários distintos.

## Divergências

Nenhuma de mérito. A recomendação de comparar público contra Helius em janelas sorteadas fica para o piloto (depende do
WS pago, que o Everton autorizou; ainda sem chave de sistema na máquina de pesquisa, e esta sondagem nunca lê `.env`).

## O que a Astra não viu e a sondagem achou

Duas coisas que a revisão de desenho não podia ver: (a) o `getTransaction`/`getBlock` público recusa o bloco quando há
transação **versão 1** e `maxSupportedTransactionVersion` é 0 (erro `-32015`); o código de produção usa `0` em
`tx_rpc.py:191` e `rpc_wallet.py:82`; (b) o primeiro cálculo da auditoria de blocos acusou 12–15 % de perda (pump 59 de 402, PumpSwap 97 de 801), que era só a
janela anterior à assinatura — daí a regra "só slots depois da primeira entrega das duas assinaturas".

## Relacionado

[[carteiras-lucro-design]] · [[wallets-engine]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] ·
[[EXP-M15-carteiras-vencedoras]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]]

## Segunda rodada — resultados e código (depois das corridas)

Revisão bruta: `.claude/state/astra-review-wallet-tape-probe-results.md`. Ela releu os resultados contra os artefatos, rodou os 36 testes (verdes), reproduziu em
memória os defeitos abaixo e **refez as contas** (28,5–30,5 M eventos/dia; 90–96 GB em 9 dias a 350 B; 152–163 GB a 593 B; 130–152 M créditos/mês; US$ 650–761/mês no Business):
a aritmética estava certa. **Veredito do código: REQUEST_CHANGES.**

| # | Achado (cenário de falha reproduzido) | Decisão |
|---|---|---|
| 1 | O leitor quebra na run 1 (`KeyError: 'truth'`) e na run 3 (divisão por zero) e mistura contadores do snapshot 90 com a auditoria do resumo final | **Aceito.** Formato antigo e corrida sem auditoria tratados por mensagem; o leitor diz de onde vem a auditoria e a qual snapshot os contadores pertencem; cortes por salto de slot continuam sendo uma heurística declarada |
| 2 | O fechamento reduzia a espera de 180 s para 30 s: um bloco de 40 s entrava como julgado, com ausências | **Aceito.** Os 180 s valem também no fim; o mais novo é **censurado**. Efeito na run 2: ~5 blocos foram julgados mais cedo (só podia somar perdas, e as perdas ficaram em 0 fora das 6 tx falhas) |
| 3 | Reconexões que falham sobrescreviam o início da queda (10 s registrados, 20 reais) | **Aceito**, teste novo que falhou antes. Vale para a run 1, onde a PumpSwap reconectava a cada ~90 s: o downtime dela (361 s) é **piso** |
| 4 | Uma auditoria atravessada por uma queda podia sair "limpa" (a queda [10, 300] com fetch em 200 e julgamento em 380) | **Aceito.** Quedas viram **intervalos** (do corte ao primeiro log) e a janela de um bloco é `[fetch − 60 s, julgamento]`; suspensão da máquina também taint. Teste novo |
| 5 | A deduplicação esquecia a assinatura depois de 60 s; uma segunda cópia muito atrasada virava transação nova | **Aceito.** Janela de 300 s. Nas corridas limpas nenhuma tx esperada nas duas assinaturas chegou só em uma (0 `only_*` na run 2), então não há cópia tardia a duplicar; na run 1 até ~5 mil tx podem ter sido contadas de novo (≈ 1 % dos eventos) |
| 6 | A fórmula da linha do Postgres contava seis colunas duas vezes (342/593 B) | **Aceito.** Corrigida (278 B de heap, **529 B com os três índices**; o JSON medido é 489 B). Os números do desenho já usam a fórmula certa; os somatórios guardados nas corridas 1–3 usam a antiga e foram re-derivados (−63 B por linha). Continua **estimativa por tipo de coluna**; a medição da tabela real fica para o piloto |

**Nice-to-have aceitos:** início da run 3 corrigido para 22:46:42Z; "53 %" descrito como **transações únicas vistas** que só mencionam o programa; "oito robôs" virou "oito carteiras com ≥ 500 swaps"
(frequência não prova identidade); o achado da versão 1 ganhou arquivo de evidência com a resposta do RPC e o histograma do bloco (1 bloco, 13 %, **não** uma taxa geral); o `slots_per_s` agora é medido e gravado
pela sondagem (o `chain_truth` do resumo da run 2 ainda usa 2,5 slots/s: o leitor refaz a conta com 3,73 a partir das contagens brutas).

**Divergências (escritas):** (a) ela não aceita "não cabe na VPS": **certo** — 136–149 GB cabem no papel nos 207 G livres de 30/09; o que está provado é volume 5–10× o aprovado, linha física
não medida e nenhuma margem para WAL/lotes/kept; o desenho agora diz isso. (b) "horário de pico" como causa da run 1 não está apoiado: o desenho diz que a causa **não está isolada**. (c) Concentração e tamanho **não** viram filtro
agora: apagar compras ou vendas pequenas contaminaria o E-PnL.

**Aceite que ela escreveria, e o desenho adotou:** "público reprovado nesta configuração; pago candidato a piloto; armazenamento sem capacidade aprovada". Go para 1a e 1c; segura 1b/2.

Reproduzir: `uv run --no-sync python infra/scripts/research/2026-10-05-wallet-tape-probe-read.py --run .claude/state/carteiras-lucro/probe/run2`.

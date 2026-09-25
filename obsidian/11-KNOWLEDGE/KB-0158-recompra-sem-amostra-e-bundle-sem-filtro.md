---
tags: [knowledge, meme, mesa-real, entrada, recompra, bundle, criacao, hipotese, metodo, m4]
tema: recomprar o mesmo mint logo depois de um alvo perdeu 9 de 10 vezes na mesa real, mas 10 casos não julgam a H-018; o SOL comprado no slot de criação não serve de filtro (H-015 refuta pela cláusula das vencedoras)
fonte: R78 (`.claude/state/notes-R78.md`) — H-018 e H-015 da Fila de Hipóteses
fonte_url:
lido_em: 2026-09-25
evidencia: medição própria — H-018: 148 posições reais e 1 497 apostas de papel (12–25/09/2026), bootstrap por mint e dois replays do check 28; H-015: 344 decisões novas da pista de eventos (24–25/09/2026) com fita da decisão, slot real da criação resolvido na chain (Helius) e zeros provados por saldo de token; 21 testes sintéticos
hipotese_testavel: sim
astra: concorda (três rodadas; 4 correções de desenho na H-018, 2 na H-015, 2 no veredito; o 3.º ponto foi checado nos dados, 0 ocorrências)
status: vivo
owner: sexta-feira
updated: 2026-09-25
confiança: "?"
---

# KB-0158 — A recompra ainda não tem amostra; o bundle da criação não é filtro

> **H-018 (recompra do mesmo mint logo depois de um ganho): `LIMITE DE DADO`**. Pela leitura literal, há 10
> recompras reais e 5 de papel, e o bloco pede 20 antes de julgar. **Nenhuma regra de mesa.**
> **H-015 (SOL comprado no slot de criação): `REFUTA` pela cláusula (c)**: o teto do tercil alto mata 36,5 % das
> vencedoras (o limite era 30 %). O rótulo sai igual nas quatro linhas.
> Estudo em `.claude/state/notes-R78.md` · código e saídas em `.claude/state/r78/` · pré-registos em
> [[Fila de Hipoteses]] § H-018 e § H-015.

## O que afirma

1. **Recompra após alvo (H-018).** Na mesa real, as 10 recompras do mesmo mint até 300 s depois de uma saída
   por alvo com lucro **perderam 9 vezes**, somando **−0,118 SOL**. Contra as primeiras entradas, D = −0,134 por
   SOL, com IC [−0,305, +0,003]. O sentido é o da tese, mas 10 casos não bastam: o bloco manda registrar e não
   julgar. Seis dessas recompras são **cruzadas**: um operador sai com lucro e o outro compra 1 a 55 s depois.
2. **Bundle da criação (H-015).** O SOL que outras carteiras compram no mesmo slot da criação não separa as
   moedas boas das más em média (D = −0,052, IC [−0,143, +0,037]). O tercil alto ganha **tão frequentemente**
   quanto o baixo: 33,0 % contra 31,9 %. Por isso bloqueá-lo leva um terço das vencedoras. Nesta amostra, o alto
   teve mais perdas ≥ 50 % (8,7 % contra 1,7 %), menos ganhos ≥ 50 % e mais despejo coordenado (2,4×). É uma
   pista de **cauda**, não de média, e não é confirmação.

## Onde foi mostrado

### H-018: mesa real 17–25/09/2026 e papel 12–25/09/2026

**Definição.** Recompra é a primeira entrada no mint depois da saída **imediatamente anterior**, se essa saída
foi por alvo com lucro e a entrada veio até 300 s depois. Há três escopos: mesmo operador, cruzado e qualquer.
Entradas da **mesma decisão de origem** não contam como recompra.
- No papel, a origem é o `features_end_time`: a sombra do `recuo_v1` não "recompra" a sombra do `operator/5`.
- No real, a origem é a **aprovação** (`decided_at`); o motivo está em "O que se aprendeu".

**Controle:** as primeiras entradas das mesmas portas.

| | real (primária, qualquer) | real, cruzada | real, mesmo operador | papel (primária) |
|---|---|---|---|---|
| recompras | **10** | 6 | 4 | **5** |
| média r | −0,187 | −0,268 | −0,065 | −0,098 |
| D contra 1.ª entradas [IC 95 %] | −0,134 [−0,305, +0,003] | −0,216 [−0,466, −0,031] | −0,009 | −0,060 [−0,458, +0,215] |
| rótulo | **limite de dado** | limite de dado | limite de dado | **limite de dado** |

As 10 recompras reais:

| moeda | resultado (SOL) |
|---|---|
| Cupsey | −0,0075 |
| KODA | **+0,0083** |
| ANT | −0,0150 |
| Paidichi | −0,0094 |
| TANK | −0,0011 |
| **Megawatt** | **−0,0519** |
| CALLS | −0,0103 |
| 007 | −0,0097 |
| Calcios | −0,0095 |
| BAGI | −0,0116 |

A sensibilidade "qualquer saída lucrativa" existe porque os braços `flow_v2` saem por `line_broken`, não por
alvo. No papel ela junta 36 recompras e dá D = +0,009 [−0,113, +0,124]: não confirma. Não substitui a linha
primária.

**Contrafactual na mesa real.** Pausa de 300 s por mint depois de **qualquer** saída, valendo para os dois
operadores. Foram rodados dois replays, cada um com o seu estado.

| replay | bloqueadas | Δ SOL |
|---|---|---|
| qualquer saída | 16 | +0,057 |
| só perda (o check 28, retroativo) | 7 | −0,060 |
| **incremento sobre a regra atual** | **9 a mais, 0 liberadas** | **+0,117** |

- As 9 a mais são as 10 recompras acima, menos o TANK: 8 perdedoras e **1 vencedora morta** (KODA).
- Das 7 recompras reais depois de uma **perda** anteriores ao check 28, 5 ganharam. É o contrário do papel do
  R64.
- É uma economia retrospectiva sobre entradas observadas, não uma estimativa de edge.

### H-015: pista `meme_event_gate_v1`, 24–25/09/2026

**População.** Todas as portas da pista, reais e de papel, uma decisão por mint (a primeira entrada), com a fita
gravada no instante da decisão. São 344 decisões resolvidas.

**Variável.** O SOL comprado por carteiras que não são o criador no **slot real** da transação `create`:
- o slot vem de `getTransaction(create_signature)`;
- o valor é lido de `early_slots` na fita.

**Resolução na chain.** Um slot ausente só vale zero se a chain provar que nenhuma outra carteira comprou naquele
slot. Para isso, todas as transações do slot, inclusive o `create`, foram relidas pelo saldo de token.
- **114 zeros** foram provados e **19 são ambíguos** (ficaram de fora).
- Nos 228 casos em que o slot aparece na fita, fita e chain concordam: Spearman 0,998.

| linha | n | D alto − baixo [IC 95 %] | perda ≥ 50 % baixo → alto | despejo baixo → alto | vencedoras no alto |
|---|---|---|---|---|---|
| **primária** | 344 | −0,052 [−0,143, +0,037] | 1,7 % → 8,7 % | 4,3 % → 10,4 % (2,4×) | **36,5 %** |
| só `reason` null | 311 | −0,080 [−0,178, +0,017] | 1,8 % → 11,5 % | 4,4 % → 12,5 % | 36,1 % |
| porta da mesa (`fluxo_e_holders`) | 154 | −0,086 [−0,245, +0,073] | 1,7 % → 11,8 % | 3,4 % → 23,5 % (6,9×) | 31,0 % |
| variável lida da chain | 363 | −0,048 [−0,141, +0,042] | 3,3 % → 9,1 % | 4,1 % → 10,7 % | 37,3 % |

Por tercil, a média não é monótona: baixo +0,004, meio **−0,055**, alto −0,048. O meio é o pior.

## O que se aprendeu

1. **A fila `mint_busy` recompra com dado velho.** O `plan_auto_approvals`
   (`services/meme-executor/hunter_meme_executor/auto_approve.py`) pula a proposta do outro operador enquanto o
   mint tem posição aberta. A proposta, porém, continua pendente por até `AUTO_APPROVE_MAX_AGE_S` = 60 s. No
   primeiro tick depois da saída ela é aprovada **sem reler a fita**.
   - 007: a proposta tinha 11,5 s e foi aprovada 1,7 s depois do alvo do op5.
   - BAGI: a proposta tinha 52,7 s e foi aprovada 1,8 s depois do alvo do op5.
   - ANT: 53,8 s.
   - As três perderam, somando −0,036 SOL.

   Esse mecanismo é independente do veredito. A decisão sobre ele é da mesa, com o `risk-engine-guardian`.
2. **Os dois operadores nunca ficam juntos no mesmo mint na mesa real.** São 0 posições sobrepostas, porque o
   `mint_busy` e o `duplicate_position` impedem. A recompra cruzada é **sequencial**: um sai e o outro entra
   logo depois. No papel as sombras não têm essa guarda: 13 pares sobrepostos, −0,251 SOL.
3. **O slot de criação que a fita infere não é o slot real.** A fita usa `first_trade_seen`, que erra em 36 de
   363 mints; nesses casos o `creation_bundle.sol` gravado mede o slot errado. A assinatura WS abre **depois**
   do `create`, por isso "slot ausente" não é zero: 21 zeros eram falsos pelo primeiro critério e 19 pelo saldo
   de token. A reconciliação do `ledger` a 1 % já marcava 18 desses 19 como `not_covered_from_birth`.
4. **Gasto do pagador não prova compra.** O classificador certo é o saldo de token do mint. A curva é quem
   recebe os lamports no `create`, não quem recebe mais tokens: em 8 mints o criador comprou mais de 50 % da
   oferta.

## Como mediríamos aqui

Já está medido. As peças reutilizáveis ficam em `.claude/state/r78/`:
- `h018.py`: recompra pela saída imediatamente anterior, origem por lane e replays sequenciais do cooldown.
- `h015_tok.py` e `tok_tpl.py`: compra no slot provada pelo saldo de token, rodando dentro do contêiner, com a
  chave só do ambiente.

## Hipótese testável no Lab

**H-018 continua aberta.** Com o ritmo atual (1,16 recompra por dia, 5 nos últimos 2 dias), as 20 recompras
reais devem chegar em **4 a 9 dias** se a mesa rodar sem mudança. Julga-se então com o mesmo código
(`r78/h018_run.py`).

Se confirmar, a regra seria estender o check 28 às saídas com ganho:
- novo limite `mint_cooldown_after_win_s` (`MEME_MINT_COOLDOWN_AFTER_WIN_S` = 300);
- por mint, em todas as pistas e **nos dois operadores**, avaliado na admissão (o que também barra a aprovação
  vinda da fila `mint_busy`).

**Não foi implementado e não se recomenda sem o veredito.**

**H-015 não gera braço nem parâmetro.** Pista exploratória, só para coorte nova: usar o SOL no slot de criação
como marcador de cauda (perda ≥ 50 %, despejo), talvez para **tamanho** e não para bloqueio. Registrá-la é
decisão do coordenador.

## Por que pode falhar (limites desta nota)

- **H-018:** 10 casos. O controle "primeiras entradas" inclui as primeiras entradas vencedoras dos mints
  recomprados. A emenda de origem no real (`decided_at`) foi feita **depois** da primeira corrida; ela não muda
  o rótulo (8 → 10 casos, ambos abaixo de 20).
- **H-015:**
  - o desfecho é o PnL registrado, não um simulador padronizado;
  - a população é dominada pelo papel do `absorb_v0`;
  - a composição de portas difere entre os tercis;
  - 71 mints não têm venda nenhuma no arquivo por polling nos 300 s, então o despejo é limite inferior;
  - sem a errata do R76, a cláusula (a) também daria `REFUTA`. Com a errata, (a) sozinha dá `NÃO CONFIRMA`. O
    rótulo final vem de (c).

## Segunda opinião (Astra)

**Desenho da H-018: 4 correções, todas aceitas.**
- Saída imediatamente anterior, porque um ganho não pode "pular" uma perda intermediária.
- Mesma decisão de origem não é recompra.
- Primária = alvo **e** lucro (leitura literal); lucro qualquer fica como sensibilidade.
- Incremento medido por dois replays, não pela contagem de bloqueadas.

**Desenho da H-015: 2 correções, aceitas.**
- Zero ausente não prova zero.
- Grade colapsada não vira "pico".

**Veredito: 2 correções.**
- Classificador por saldo de token no lugar do gasto do pagador. Refeito; os rótulos não mudaram.
- Redação descritiva da leitura de cauda.

**Terceira rodada** (`.claude/state/astra-review-R78-veredito-2.md`): ela concorda com os dois rótulos e com a
redação. Levantou dois casos que o saldo líquido não distingue: compra e venda integral na mesma transação
(falso zero) e transferência gratuita (falsa compra). Não mostrou ocorrência. **Checado nos dados, sem chamada
nova** (`r78/h015_tok_edge.txt`):
- **Transferência gratuita: 0 ocorrências.** Todo ganho de token de uma carteira que não é o criador vem com
  saída de token da curva.
- **Compra e venda na mesma transação:** as 20 transações do slot nos 116 zeros provados foram vistas uma a uma.
  18 não tocam a curva: são pré-criação de contas de token. As 2 que tocam não movem nada e pagam só a taxa;
  um ida-e-volta pagaria a taxa de protocolo nas duas pernas.

**Discordância registrada.** Ela preferia validar por instruções antes de gravar. A prova por ocorrência cobre os
zeros usados, e por isso o veredito foi gravado.

## Relacionados

[[Fila de Hipoteses]] (H-018, H-015) · [[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]] (origem da
H-015) · [[KB-0157-esperar-o-recuo-nao-paga]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[Strategy Backlog]]

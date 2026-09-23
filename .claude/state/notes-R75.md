# R75 — H-013, moeda em equilíbrio e não em subida

**Data:** 23/09/2026, corte dos dados ~20:47 UTC (17:47 BRT). **Pedido:** Everton, 17:4x BRT, depois da perda
real do `SHORT` (−0,0134 SOL, −18,7 %). **Pré-registo:** bloco H-013 da fila, usado verbatim (previsão e
refutação copiadas para o `PreRegistration` do moinho; impressão digital `886db52395f9`).
**Método:** VPS só leitura (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`, só `SELECT`/`COPY TO STDOUT`;
nada escrito). Export `.claude/state/r75/pop.csv` (1 312 linhas, 0,9 MB). Código: `load.py` (146 linhas),
`run.py` (239), `test_load.py` (7 testes), relatório completo em `.claude/state/r75/report.md`. Dinheiro em
`Decimal`, estatística em float, tempo UTC aware.

**Resposta curta.** **NÃO CONFIRMA, por limite de dado.** Em 587 decisões (uma por mint) só **uma** tem
`equilibrio = verdadeiro`, e é o próprio `SHORT` que originou a hipótese. A 2.ª cláusula da refutação (menos de
20) dispara só pela contagem, antes de se olhar para qualquer desfecho. Isto não é refutação da tese: com um caso
não se julga nada. O contrafactual dá +0,0134 SOL com 0 vencedoras mortas, mas é circular: a regra remove o caso
a partir do qual foi desenhada. **Não configurar nada na mesa.**

## 0. De onde vêm as features (e por que não há look-ahead)

As três grandezas vêm de `meme_proposals.reasons`, que a porta **grava quando cria a proposta**:
- bloco `flow`: `buys_1m`, `sells_1m`, `net_sol_flow_1m`;
- `curve_progress_pct.value`.

A proposta nasce antes do `decided_at` (a Astra verificou em `proposals.py:321`). Não se reconstrói nenhuma fita.
Não se lê `meme_trades`, que é a cópia por polling com ~44 s de atraso (R73/KB-0153). O moinho corre com dispensa
declarada da guarda, porque não há coluna de instante a guardar: a feature **é** a que a porta usou.

Há duas séries na população, e elas são instrumentos diferentes:

| série | decisões | reais | como mede |
|---|---:|---:|---|
| `meme_event_gate_v1` | 185 | 67 | fita WS em memória |
| `meme_features_15s_v1` | 402 | 15 | fita do polling, filtrada por `received_at <= end_time` (`features_tape.py:188`) |

A série de 15 s é **causal, mas atrasada**: é o que a porta viu, medido numa fita que chega tarde. Não é futuro.

## 1. População e cobertura

- **Regra congelada no R73:** porta `fluxo_e_holders/*`, bloco `flow` presente, uma decisão por mint. A real ganha
  da de papel e, entre iguais, fica a mais antiga (desempate por `bet_id`).
- **Deduplicação antes da censura** (achado da Astra, com teste).

| recorte | linhas | porta `fluxo_e_holders` | bloco `flow` | progresso | as três lidas |
|---|---:|---:|---:|---:|---:|
| posições reais (todas as 93) | 93 | 93 | 93 | 93 | **100 %** |
| apostas de papel | 1 219 | 1 219 | 1 219 | 1 219 | **100 %** |
| **uma por mint (população)** | **587** (82 reais + 505 papel) | 587 | 587 | 587 | **100 %**, 0 censuradas |

- **A cobertura é total.** Ao contrário do R73, aqui o dado não limita a leitura.
- **O limite está na ocorrência:** o equilíbrio quase não aparece na população.
- Todas as apostas de papel dos braços `fluxo_e_holders` estavam fechadas no corte. O `WHERE exit_at IS NOT NULL`
  do SQL não descartou nenhuma.

## 2. Contagem, e por que ela é baixa (a própria porta seleciona)

| braço | teto `max_sells_to_buys` | n | razão ≥ 0,6 | fluxo < 2 | progresso < 25 % | **equilíbrio** |
|---|---:|---:|---:|---:|---:|---:|
| flow_v2/1 | 0,6 | 100 | 0 | 3 | 23 | **0** |
| flow_v2/2 | 0,6 | 280 | 6 | 12 | 12 | **0** |
| flow_v2/3 | 0,6 | 47 | 0 | 5 | 1 | **0** |
| flow_v2/5, /6, /9 | 0,6 | 43 | 0 | 5 | 14 | **0** |
| flow_v2/8 | 1,0 | 29 | 29 | 4 | 6 | **0** |
| operator/5 (antes de 18/09) | 0,6 | 14 | 0 | 0 | 7 | **0** |
| operator/5 (depois de 18/09) | 1,0 | 56 | 14 | 7 | 2 | **1 (`SHORT`)** |
| operator/6 | 0,6 | 18 | 0 | 4 | 6 | **0** |
| **total** | | **587** | **49** | **40** | **71** | **1** |

- **Todas as linhas, sem deduplicar:** 2 de 1 312. A segunda é a sombra de papel do mesmo `SHORT` no
  `operator/5` (−21,4 %).
- **A porta é quem seleciona.** 502 das 587 decisões vêm de braços com teto de 0,6: a porta recusa razão > 0,6.
  Nesses braços, "vendas ÷ compras ≥ 0,6" só acontece com a razão exatamente em 0,6 (6 casos no flow_v2/2).
- **Onde a tese é possível**, nos braços com teto 1,0, há 1 equilíbrio em 85 decisões (1,2 %).
- **Na série WS**, a que a mesa usa hoje, há 1 em 185.
- **Consequência:** 1 em 587 não mede a frequência natural do equilíbrio no mercado. Mede o que sobra depois da
  porta.
- **Para chegar a 20 casos** à taxa dos braços com teto 1,0, seriam precisas da ordem de 1 700 decisões.

## 3. Veredito sob a regra congelada

| cláusula (verbatim) | resultado |
|---|---|
| IC 95 % inferior (bootstrap por mint) de média(eq) − média(resto) acima de −0,01 | **não avaliável**: 1 caso |
| menos de 20 decisões com `equilibrio = verdadeiro` → limite de dado | **DISPARA: 1 de 587** |
| os três limiares não formam patamar quando cada um é deslocado ±1 degrau | **não avaliável**: os 7 pontos (centro + 6 vizinhos) têm todos n = 1 do lado do equilíbrio |

**Moinho (`run_hypothesis`).**
- Configuração:
  - variável = indicador (1 = equilíbrio), `direction='low'`, limiar 0,5, portanto espelho do bloco
    (D = resto − equilíbrio);
  - MRE 0,05; cluster por mint; permutação estratificada por dia; blocos por hora; 10 000 réplicas; semente 75;
  - planalto do moinho desligado, porque a variável é booleana (motivo escrito na `decision_rule`). O patamar
    pré-registado é verificado fora do moinho.
- **Veredito: NÃO CONFIRMA**, por "amostra insuficiente: 586/1 contra o mínimo 20 por lado".
- O moinho também imprime D = +0,1461, IC [+0,110, +0,184] e p = 0,665. Esse IC **não é interpretável**: com um
  só caso de um lado, as réplicas que sobrevivem têm sempre o mesmo `SHORT` (achado da Astra). Não citar.

**Rótulo final: H-013 concluída — NÃO CONFIRMA por limite de dado.** Não é REFUTA. A cláusula diz textualmente
"poucas demais para julgar", e a Astra concorda. Sem CONFIRMA, não há braço de papel a propor.

### Degraus do patamar (suposição minha, declarada)

O bloco não fixa o tamanho do "degrau". Congelei estes valores antes de olhar desfechos:
- 0,1 na razão (0,5 / 0,6 / 0,7);
- 1 SOL/min no fluxo (1 / 2 / 3);
- 5 pp no progresso (20 / 25 / 30).

Critério de patamar: os 7 pontos com o sinal previsto e pelo menos 2 vizinhos com IC fora de zero. Nenhum ponto
chegou a 20 casos. Só os vizinhos com fluxo < 3 e progresso ≥ 25 juntam 2 a 4 casos, e **com média positiva**
(D_bloco de +0,10 a +0,25), contra a tese. Com n ≤ 4 isso é anedota.

## 4. Previsão secundária: perdas ≥ 15 % que saem em ≤ 3 s

| grupo | n | perdas ≥ 15 % | das quais em ≤ 3 s |
|---|---:|---:|---:|
| equilíbrio | 1 | 1 | 1 (o `SHORT`, 3,0 s de posição) |
| resto | 586 | 215 | 2 (0,9 %) |

- **No papel, esta medida não existe.** A posição de papel mais curta dura 10,2 s.
- **Nas 93 reais:** 29 perdas ≥ 15 %, das quais 3 saíram em ≤ 3 s: `DOOM`, `PHILINU` e `SHORT`.
- **`DOOM` e `PHILINU` não estavam em equilíbrio** (razão 0,33 e 0,49; fluxo +11,7 e +18,0 SOL/min; progresso 40
  e 54 %). A saída relâmpago pelo recuo não é assinatura do equilíbrio.
- A secundária também não é julgável com n = 1.

## 5. EXPLORATÓRIO: condições sozinhas e aos pares (fora do veredito)

Sinal: D = média(verdadeiro) − média(falso), em SOL por SOL. A tese pede D negativo.

| condição | n verd. | média verd. | média falso | D | IC 95 % (mint) |
|---|---:|---:|---:|---:|---|
| vendas ÷ compras ≥ 0,6 | 49 | −0,0586 | −0,0395 | −0,0191 | [−0,109, +0,074] |
| fluxo < 2 SOL/min | 40 | +0,0165 | −0,0453 | **+0,0618** | [−0,075, +0,217] |
| progresso < 25 % | 71 | −0,0074 | −0,0457 | **+0,0383** | [−0,047, +0,132] |
| razão E fluxo | 10 | −0,0374 | −0,0412 | +0,0038 | sem potência |
| razão E progresso | 8 | −0,0441 | −0,0411 | −0,0031 | sem potência |
| fluxo E progresso | 6 | −0,1242 | −0,0402 | −0,0839 | sem potência |

- **Nenhuma condição sozinha confirma.** Todos os IC cruzam zero.
- **Fluxo fraco e curva rasa, sozinhos, vão contra a tese** (D positivo). Só a razão aponta para o lado da tese,
  e em −0,019, longe do MRE de 0,05.
- **Nenhum par chega a 20 casos.**
- Isto é consistente com o R65/R69, que testaram a razão sozinha sem confirmar.

## 6. Contrafactual: a porta recusando `equilibrio = verdadeiro` nas 93 reais

**Base:** 93 posições reais, 29 vencedoras, PnL **−0,3498 SOL**.

| limiares | bloqueadas | vencedoras mortas | Δ PnL |
|---|---:|---:|---:|
| **0,6 / 2 / 25 (congelado)** | **1 (`SHORT`)** | **0** | **+0,0134** |
| cada um dos 6 vizinhos ±1 degrau | 1 (`SHORT`) | 0 | +0,0134 |
| todos alargados de uma vez (0,5 / 3 / 30) | 2 | 0 | +0,0207 |

**Isto não é evidência a favor.** A regra foi desenhada no `SHORT` e o contrafactual remove o `SHORT`. Não mata
vencedoras porque, fora do `SHORT`, **nenhuma posição real cai na conjunção**. Isso prova que a regra quase nunca
dispara, e não que ela protege. O teto de ganho é +0,013 SOL em 93 operações: irrelevante contra −0,35.

## 7. A ressalva que mais importa

**A amostra é o próprio caso de origem, dentro de uma população que a porta já filtra.**
- O único equilíbrio é o `SHORT`, o que significa zero casos fora da amostra que gerou a hipótese.
- 85 % das decisões vêm de braços cujo teto de 0,6 exclui a conjunção quase por construção.
- A pergunta "equilíbrio é pior?" só pode ser respondida onde a porta deixa o equilíbrio passar: o `operator/5`
  depois de 18/09 e o flow_v2/8. Lá, é 1 em 85.

A segunda ressalva é que as duas séries de features são instrumentos diferentes (WS × polling filtrado). Juntá-las
é aceitável para uma contagem, mas não o seria para um efeito.

## 8. Para reabrir

**Nenhum parâmetro de mesa.** Reabrir só com uma coorte **prospectiva**, independente do `SHORT`:
- as decisões do `operator/5` (teto 1,0, série WS) a partir de 23/09 20:47 UTC;
- a mesma variável congelada, sem mexer nos limiares;
- julgar quando houver 20 equilíbrios, ou declarar que, com a porta atual, a conjunção é rara demais para valer um
  filtro.

À taxa de 1 em 85, isso leva meses, não dias.

## Segunda opinião (Astra)

Revisão em `.claude/state/astra-review-r75.md`, uma ronda sobre carregador e veredito.

- **Concorda:**
  - com o rótulo "NÃO CONFIRMA — limite de dado", e com o patamar como "não avaliável", não reprovado;
  - com a convenção de `buys = 0` e com `ret = pnl/size`;
  - com o join de papel por `b.rule_set_id` (o produtor copia o id da proposta, `lab_repo_bets.py:190`);
  - **não encontrou look-ahead** na leitura de `reasons`.
- **Must-fix aplicados:**
  1. a censura acontecia antes da escolha de uma por mint (uma real censurada podia ser substituída pelo papel).
     Corrigido com `population()` e com um teste que falhou primeiro. Impacto nas 587 atuais: nenhum, 0
     censuradas;
  2. o IC do moinho com 1 caso aparecia como evidência. Agora está marcado no relatório como não interpretável.
- **Nice-to-have:**
  - o `_` do `LIKE` é curinga. O filtro em Python exige o prefixo literal, por isso não tem efeito;
  - os degraus 0,1 / 1 / 5 não estão no bloco. Ficaram declarados acima como suposição.
- **Ressalva que ela destacou:** a seleção pela porta. Foi adotada como ressalva principal, junto com a
  circularidade.
- **Rejeitado:** nada.
- **Nota:** o script `astra.sh` avisou de mudanças na árvore durante a chamada. Verifiquei que eram commits
  concorrentes do orquestrador (T4.88, R71, R74, às 17:52–17:55), não ação da Astra.

---
status: proposta (desenho; nenhum código; DECISÃO CONJUNTA com a Astra na rodada 6; aguarda aprovação da Sexta-feira e o ADR assinado pelo Everton — §10, decisão D1)
data: 2026-10-17
dono: risk-engine-guardian
tipo: arquitetural (subsistema novo — robô de execução real na B3 via MetaTrader 5; contrato de risco novo)
decisao_origem: decisão do Everton de 17/10/2026, transmitida pela Sexta-feira (robô dele, conta dele na Rico, ele liga)
plano_irmao: docs/plans/MERCADO-TRADICIONAL.md (painel de sinais manual de segunda 19/10, H-038, custos §1.4, capital §1.5)
dialogo_astra: obsidian/06-DECISIONS/Dialogos/robo-b3-mt5.md (transcrição .claude/state/dialogue-robo-b3-mt5.md)
---

# Robô B3 do Everton — MetaTrader 5 na Rico (desenho)

> **O que o Everton decidiu (17/10/2026, em conversa com a Sexta-feira):** construir o robô de negociação automática
> **dele**, para a B3, ligado à **conta dele na Rico** (grupo XP), operando pelo **MetaTrader 5**. As regras do arranjo:
> (1) o login da Rico é digitado por ele no terminal; **nenhum agente vê, guarda ou manipula credencial**; (2) ele põe o
> dinheiro e ele liga o robô; **nenhum agente liga negociação real e nenhum agente envia ordem à mão**; (3) o robô só
> envia ordens sozinho depois que ele o habilita. Essa decisão de produto passa por cima do calendário "Fase 4" do
> projeto **para esta linha B3**. A arquitetura de segurança continua sendo nossa, e estrita.
>
> **Este documento é desenho.** É arquitetural: o documento vem primeiro, a Sexta-feira aprova, depois vem o plano e a
> implementação. A estratégia é escolhida noutra tarefa (H-038, WIN intradiário, `docs/plans/MERCADO-TRADICIONAL.md`
> §1.2–§1.3); aqui o robô é desenhado para que **qualquer estratégia mecânica** encaixe (§5.1).

## 0. O que a base já sabe, e o que isso muda aqui

| Fonte lida (17/10/2026) | O que diz | O que muda neste desenho |
|---|---|---|
| `obsidian/00-HOME.md` | O caminho de entrada é sempre AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO; paper, memes reais e spot são operações distintas | O robô B3 é **uma quarta operação**, com contrato de risco próprio (`hunter_risk_b3`), mesma forma de proposta → decisão persistida → ordem |
| [[KB-0149-o-que-a-mesa-real-ensinou]] §1 e §4.23 | 72 % do prejuízo da mesa real foi **custo**; custo por praça medido antes de operar | O custo por ida e volta entra **em todo** cálculo de risco por operação e do limite diário (§3.4, §3.6); o relatório diário compara custo modelado × custo da nota (§7.2) |
| KB-0149 §4.20–§4.21 | O RPC gratuito parou a mesa **2 dias sem alarme**; `.env` mudado não chega ao processo sem recriar | Heartbeat com **cão de guarda fora do PC** (§7.3); toda mudança de limite é dado relido em voo, não variável de ambiente (§3.1) |
| KB-0149 §5.27–§5.28 | A revisão adversária pagou-se; "ligar critério novo na mesa real não é sombra" | Sessão técnica em conta **demo** antes de dinheiro real (§6), e revisões obrigatórias (§9) |
| [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] | 97 % das pessoas físicas que persistiram no day trade de WIN perderam dinheiro | O robô não promete vantagem. O que ele entrega são **invariantes escritas e provadas** (§3, §5, §8 e a sessão demo da §6.2); vantagem é assunto da H-038 |
| `docs/RISK_ENGINE.md` §1, §3, §5, §7, §10 | Motor puro (sem rede, banco, relógio); checks gravados mesmo depois da 1.ª reprovação; `unavailable` reprova; kill switch com escopos e "o mais restritivo"; saídas nunca bloqueadas; intenção de saída durável | Copiado como **forma**: `evaluate`/`evaluate_exit` puros, `checks[]` completos, `binding_constraint` no sizing, kill switch de quatro estados, intenção de saída que sobrevive à tentativa |
| `docs/RISK_ENGINE_MEME.md` §0, §3.3–§3.5, §7, §7.1, §12 | Três portões (engenharia, evidência, interruptor do dono); flag `ENABLE_*` que só o dono liga; trava diária *latched*; portões relidos em voo; "teste pequeno autorizado por escrito" | Mesmo modelo de **portões**: A (engenharia = sessão técnica demo provada), C (as três chaves do Everton, §1.3 e §6.3). O Portão B (evidência) só fica dispensado **se ele escrever isso, com escopo e data de revisão** — a variante "autorizado por escrito" da §12 do contrato meme, aqui como D1 |
| `services/meme-executor/hunter_meme_executor/signing_gate.py` | Aprovação não é salvo-conduto: o kill switch e a identidade do programa são relidos **imediatamente antes de assinar**; saídas nunca passam pelo portão | `pre_send_gate` (§3.9): kill switch, terminal, posição/ordens na corretora e idade da proposta relidos imediatamente antes do `order_send` de **entrada** |
| `services/meme-executor/hunter_meme_executor/program_check.py` | Mudança do programa observado → entradas recusadas por nome, saídas continuam; leitura ilegível não é "inalterado" | **Vigia da especificação** (§3.9): tick, valor do tick, lote, modo de negociação, modos de preenchimento do símbolo e versão do terminal/pacote fixados no armamento; mudou ou não leu → só saídas |
| `packages/core/hunter_core/execution/live.py` | `LiveExecutionAdapter` recusa na construção e em todo método; "a flag não conjura código" | **Não muda.** A linha cripto continua sem live. O robô B3 tem adaptador próprio, num serviço próprio, com flag própria (§1.3) — e isso exige o ADR da D1 |
| `docs/plans/MERCADO-TRADICIONAL.md` §1.2–§1.6 | H-038: sinal em O+30, entrada C−30, stop de catástrofe 0,5 %, saída por tempo em C; custo ≈ R$ 2,51/contrato ida e volta; um só módulo puro para painel e robô | O plug-in de estratégia (§5.1) embrulha **o mesmo** módulo puro da tarefa W0-S; o robô não reescreve a regra |

**Notas de bugs e decisões:** `obsidian/07-BUGS/Open Bugs.md` não tem item B3 (não existia linha B3 até hoje). As
decisões que restringem este desenho são a de 17/10 (pausar memes e cripto e ir para o mercado tradicional; a nota
está sendo escrita pela tarefa irmã) e o ADR 0006 (doutrina de execução meme), cuja forma de portões reaproveito.

## 1. Princípios fixos (do CLAUDE.md, aplicados aqui)

1. **Credencial:** o robô chama `mt5.initialize()` **sem** `login`/`password` — ele se anexa ao terminal em que o
   Everton já entrou. A função aceita os dois parâmetros (documentação oficial, `initialize`); um teste falha se
   qualquer chamada do adaptador os passar, e o processo não lê variável de ambiente com nome de senha. O token do robô
   para a nossa API (§3.7) é digitado pelo Everton no ambiente do PC, nunca por agente.
2. **Dinheiro é `Decimal`.** O pacote `MetaTrader5` fala `double` (`price`, `sl`, `tp`, `volume` em
   `MqlTradeRequest`). A conversão acontece **só** no adaptador (`hunter_exchanges.mt5.convert`): na saída,
   `Decimal` alinhado ao tick → `float`, com prova de ida e volta exata; na entrada, `float` → `Decimal` arredondado a
   `digits` e recusado se não for múltiplo do tick (`price_off_tick`). Nenhum `float` passa da fronteira.
3. **Tempo é UTC.** As grades da B3 são horário de Brasília e mudam por ofício (a OC 050/2026-VNC muda a grade de
   derivativos em **03/11/2026**); são **dado com vigência**, convertido a UTC por data com `zoneinfo`
   (`America/Sao_Paulo`), nunca `-3` fixo (§7.4).
4. **Sem estado local.** Postgres é o registro; a corretora é a verdade do dinheiro (posição, ordens, negócios). Os
   dois arquivos locais são exceções declaradas no ADR: o **buffer de indisponibilidade** append-only (§3.8), que
   nunca decide nada, e o **batimento** que o EA vigia lê (§2.1).
5. **Auditoria:** toda mutação (armar, desarmar, mudar limite, kill, decisão de risco, ordem, fill, divergência de
   reconciliação) gera `audit_logs`.
6. **Sem dado falso:** nada de posição, PnL ou "conectado" inventado na tela; sem dado, a tela diz "sem leitura há N s".
7. **Nenhum agente envia ordem:** só o processo do robô, armado pelo Everton, chama `order_send`. O comando de kill de
   agente (§4, R2) só pode **bloquear entradas** (não gera ordem); zerar é ato do Everton ou do robô armado por ele.

### 1.3 A flag e as três chaves do Everton

`ENABLE_B3_LIVE_TRADING` (irmã de `ENABLE_LIVE_TRADING` e `ENABLE_MEME_LIVE_TRADING`, sem relação com elas):

| Chave | Onde | Quem | Efeito se falta |
|---|---|---|---|
| K1 — `ENABLE_B3_LIVE_TRADING=true` | ambiente do processo no PC (ou na VPS Windows, §2) | **só o Everton** | conta **REAL** detectada (`account_info().trade_mode == ACCOUNT_TRADE_MODE_REAL`) → robô **inerte**: lê, reconcilia, publica, **não envia nada, nem saída**. K1 é lida só na partida; desligá-la é o "desarmar total" do Everton: se houver posição aberta pelo robô, o stop segue no servidor, a saída por tempo **não** acontece e o alerta diz "só a rota manual zera" (§4, R3/R4) — o desenho não promete as duas coisas `[Astra R2, F8]` |
| K2 — botão "Algo Trading" ligado no terminal | MT5 | **só o Everton** | `terminal_info().trade_allowed == False` → o terminal recusa toda ordem de API (`RES_E_AUTO_TRADING_DISABLED`); o robô vê, bloqueia entradas e grava `TRADING_DISABLED` (`manual_route`) no banco assim que alcançar a API — religar K2 **não** destrava; só o rearme (K3) posterior `[Astra R2, F8]` |
| K3 — "Armar" no app web | `b3_robot_arming` (Postgres), com confirmação reforçada (step-up do Clerk), papel OWNER | **só o Everton** | estado `DISARMED` → nenhuma entrada; saídas de posição já aberta pelo robô continuam. **O armamento vale para uma instância** (id da instância gerado na partida) `[Astra R3-3, R5-2]`: todo processo novo nasce só lendo (fase 0 da §5.2); o Everton concede a **gestão** a ela depois do diagnóstico e arma as **entradas** (K3) depois da reconciliação; K2 desligada observada também invalida o armamento corrente — **na hora, localmente**; a escrita na API vem depois e não condiciona o bloqueio `[Astra R4]`. Assim, um K2 desligado e religado com o Python morto, ou observado e perdido numa queda antes de chegar à API, não deixa o robô voltar a entrar sozinho |

Conta **DEMO** (`ACCOUNT_TRADE_MODE_DEMO`) não precisa de K1: é a sessão técnica (§6.2). A conta (número + servidor)
é registrada pelo Everton na autoridade da instância (§5.2) como **hash**; outra conta conectada → `account_mismatch`, só leitura.

## 2. Topologia

O pacote oficial `MetaTrader5` (PyPI, versão 5.0.6231 lida em 17/10/2026) publica **só rodas `win_amd64`** e
"obtém dados por comunicação entre processos diretamente do terminal MetaTrader 5" (documentação oficial). Ou seja:
o processo Python precisa rodar **no mesmo Windows** que um terminal aberto e logado.

| | (a) processo no PC do Everton, ao lado do terminal | (b) VPS Windows | (c) MT5 em Wine na nossa VPS Linux | (d) Expert Advisor MQL5 com a lógica portada |
|---|---|---|---|---|
| Latência até a corretora | a da internet residencial dele (desconhecida; medir `terminal_info().ping_last`) | baixa se o datacenter for em São Paulo (a escolher) | a da VPS atual (não sabemos onde fica em relação à B3) | a do terminal onde roda |
| Disponibilidade | a do PC: suspensão, atualização do Windows, queda de luz/internet | 24 h, se paga | 24 h | a do terminal onde roda (PC ou VPS da MetaQuotes, paga) |
| Se o PC dorme / a rede cai | robô e terminal congelam; **stop e alvo continuam no servidor da corretora** (§2.2); zeragem do fim do pregão não acontece por nós → zeragem compulsória da corretora (**regra da Rico não lida**) + alerta do cão de guarda (§7.3) | igual, mas raro | igual | o EA também para com o terminal |
| Suporte oficial | sim (é o caso documentado) | sim | **o terminal** roda em Wine com script oficial da MetaQuotes (Ubuntu, Debian, Mint, Fedora); **o pacote Python não é documentado em Wine** — exigiria Python para Windows dentro do Wine ou ponte não oficial | sim |
| Testabilidade com a nossa suíte (pytest, Decimal, Postgres) | total (Python) | total | parcial e frágil | **nenhuma**: lógica duplicada noutra linguagem, sem pytest, sem acesso ao Postgres exceto `WebRequest` |
| Custo | zero | pago (decisão dele) | zero, mas toca a VPS de produção | zero (VPS MetaQuotes paga) |
| Credencial | ele digita no terminal do PC | ele digita no terminal da VPS (acesso remoto dele) | ele digitaria num terminal **na nossa VPS** — mistura a credencial dele com a nossa infra | ele digita |

**Recomendação.**
- **Primeira semana: (a)**, o PC do Everton. Custo zero, credencial só na máquina dele, e a estratégia candidata
  (H-038) negocia **uma vez por dia com horas entre sinal e entrada** — a latência residencial é irrelevante para ela.
  Compensações obrigatórias: plano de energia sem suspensão durante o pregão (ato dele, item do checklist §6.1),
  stop sempre no servidor da corretora (§2.2), zeragem antes do fim do pregão (§3.1, checks 6–7), cão de guarda fora do
  PC (§7.3) e o **EA vigia** que avisa o celular dele (§2.1). No PC a operação é **supervisionada**: o Everton disponível durante
  a janela entre a entrada e a zeragem (para a H-038, C−30 a C), porque com o PC fora as rotas que zeram são só as dele
  (§4, R3/R4). `[Astra R1]`
- **Depois: (b)**, VPS Windows em São Paulo, **mesmo processo Python**, quando (i) uma estratégia precisar de
  segundos, ou (ii) o Everton quiser operar **sem supervisão**. A decisão vem **antes**, não depois do primeiro
  incidente com posição real `[Astra R1]`. A VPS não resolve queda do servidor da Rico. É serviço pago: decisão dele (D9).
- **(c) descartado para dinheiro real:** o pacote Python não é suportado em Wine e a credencial dele passaria a viver
  na nossa VPS. **(d) descartado como caminho principal** (duas implementações da mesma regra é o defeito que a casa
  evita), **mas** um EA **vigia** sem estratégia e sem ordens é recomendado — ver abaixo.

### 2.1 O EA vigia (MQL5, sem estratégia, **sem ordens**) `[Astra R2, F7/F8]`

A primeira redação dava ao EA o papel de zerar quando o Python sumisse. A rodada 2 da Astra mostrou que um batimento
parado **não prova** que o outro remetente perdeu a capacidade de agir: o Python pode ser suspenso imediatamente antes
do `order_send`, o EA assume, os dois enviam "vende 1" e a conta fica **vendida 1**, sem stop. Em *netting* a posição é
identificada pelo **símbolo**; preencher `position` "também pode" ser feito, mas não torna a ordem só-redução
(estrutura `MqlTradeRequest`, documentação oficial, conferida nesta tarefa). Não há, no caminho de execução
documentado, exclusão entre dois processos no mesmo terminal. **Decisão: um só remetente de ordens do robô — o
processo Python.** O EA não envia ordem nenhuma, nunca.

O que sobra para o EA (`infra/mt5/HunterVigia.mq5`, ~100 linhas, anexado pelo Everton a um gráfico, compilado por ele
no MetaEditor) é **avisar o celular do Everton** pela notificação nativa do MetaTrader (`SendNotification`, para o
MetaQuotes ID configurado na aba Notificações; limite oficial de 2 por segundo e 10 por minuto), por temporizador
(`OnTimer`, sem depender de tick):
1. posição na conta e batimento do Python (`MQL5\Files\hunter_hb`, instante + conta) parado há mais de 30 s;
2. posição na conta sem `sl` há mais de `naked_grace_s`;
3. posição na conta a menos de 15 min do fim do pregão (horário compulsório mais cedo que ele grava no parâmetro do
   próprio EA, D6).

O aviso funciona com a nossa VPS e a nossa API fora, e com o Python morto; não funciona com o terminal ou o PC mortos
(para isso há o cão de guarda na VPS, §7.3). `hunter_hb` é o **único arquivo que o EA lê**: sinal de vida, não estado
de negócio; a exceção à regra "sem estado local" fica declarada no ADR da D1 junto com o buffer (§3.8).

Consequência aceita e escrita: **com o Python morto, quem zera é o servidor (stop/alvo) ou o Everton** (rotas R3/R4 da
§4). O EA encurta o tempo até ele saber.

### 2.2 Onde fica o stop — e o que "no servidor" quer dizer

A ajuda oficial do MetaTrader 5 diz que Stop Loss e Take Profit "estão associados a uma posição, são **guardados e
executados no servidor da corretora** e portanto não dependem do funcionamento da plataforma"; e que o Trailing Stop,
ao contrário, é executado no terminal. Para símbolos de bolsa, disparam pelo **último negócio** e executam a
bid/ask — em gap, com deslizamento. Se a operação disparada for rejeitada pela bolsa, a ordem não é apagada e dispara
de novo no próximo tick.

Consequências escritas no desenho:
- **Stop do robô = `sl` da posição, nunca trailing do terminal.** Trailing, se uma estratégia pedir, é o robô movendo
  o `sl` por `TRADE_ACTION_SLTP` — a cada movimento o stop novo está no servidor.
- "No servidor da corretora" **não é** "na bolsa": se o servidor MT5 da Rico cair, o stop não dispara. Se a Rico
  converte o `sl` em ordem stop na B3, **não sabemos** (site bloqueado a leitura automatizada, §13). Item da sessão
  técnica (§6.2, T7).
- **Armadilha do modo *netting*** (contas de bolsa): uma ordem que **aumenta ou inverte** a posição substitui o
  `sl`/`tp` da posição pelo da ordem, e **zero apaga** o stop; um **fechamento parcial não muda** `sl`/`tp`; um
  fechamento total os apaga com a posição (ajuda oficial, "Rules of Stop Loss and Take Profit inheritance (netting)").
  Invariante do adaptador, com teste: requisição que aumenta ou inverte num símbolo com posição aberta tem de carregar
  o `sl` vigente — `sl=0` nesse caso é recusado antes do terminal (`would_delete_stop`); redução e fechamento total
  **não** são bloqueados por isso `[Astra R1, F6]`. Como a v1 só entra zerada (check 10), aumento só aconteceria por
  defeito — e é recusado.
- **Saída pelo aperto do colchete — nunca sem stop, nunca exposição nova `[Astra R2 F7, R3-1, R3-2 — CRITICAL]`.**
  O stop no servidor é um segundo remetente que não dá para tirar: um "vende 1" nosso no mesmo instante em que o
  stop dispara deixa a conta vendida 1. A segunda redação (retirar o stop, fechar, recolocar) trocava esse risco por
  outro pior — o Python ou o PC caindo entre a retirada e o fill deixa a posição **sem stop por tempo indefinido**, e
  repetir o fechamento depois de um tempo esgotado pode duplicar a redução. A saída do robô passa a ser feita **pelo
  próprio servidor**: o `sl` e o `tp` estão presos à posição e somem com ela (ajuda oficial: "If a position is fully
  closed, the Stop Loss and Take Profit levels are deleted"), então quem fecha é **um único remetente**, e "o fechamento
  não inverte a conta" é **propriedade exigida**, a provar em T7/T13 — apagar os níveis ao encerrar a posição não
  prova sozinho o destino de toda ordem já disparada `[Astra R6]`. Sequência de toda saída por tempo, zeragem de fim de pregão ou `EMERGENCY`:
  1. `TRADE_ACTION_SLTP` levando o colchete **até o toque**: comprado → `sl` **no bid** e `tp` **no ask**; vendido, o
     espelho. Só nesses níveis "o primeiro negócio em qualquer lado do livro dispara um dos dois" (o stop de bolsa
     dispara pelo último negócio, ajuda oficial). Se o servidor exigir distância (`trade_stops_level`,
     `trade_freeze_level` — distâncias em **points**, convertidas por `point` e alinhadas ao `trade_tick_size`
     `[Astra R4]`), usa o nível válido mais próximo e **declara** que a saída passa a depender de o preço andar até
     ele (exemplo sintético da Astra: tick 5, bid 100, ask 105, `sl` 95 e `tp` 110 — negócios em 100/105 não disparam
     nada). Os níveis só se **aproximam** do preço: o `sl` novo nunca é mais largo que o **confirmado no servidor**.
     SLTP rejeitado → mantém e relê os níveis anteriores (nunca contorna a rejeição removendo o `sl`); SLTP com
     resposta incerta → só é resolvido por **resultado terminal correlacionado** (retcode final daquela requisição)
     e nível confirmado; reler o nível antigo **não** prova que a requisição morreu (exemplo da Astra: `sl` 90
     confirmado, pedido A para 95 incerto, leitura ainda 90 — mandar B para 99 deixaria A chegar depois e trocar 99 por
     95). Sem prova → `exit_unknown`, alerta, nenhuma modificação nova `[Astra R5]`.
  2. A cada `bracket_step_s` (proposta 1 s), se a posição continua aberta, reaperta pelo preço novo (sempre só
     apertando). Nada além de `TRADE_ACTION_SLTP` é enviado nessa fase: nenhuma ordem nossa existe que possa somar
     exposição, e o Python caindo no meio deixa a posição com um colchete **mais apertado**, não sem colchete.
  3. **Prazo (`bracket_deadline_s`) sem fechamento direcional automático `[Astra R4-1 — CRITICAL]`.** A terceira
     redação mandava, no prazo, **um** fechamento direto; conhecer volume e lado antes do envio não reserva o volume no
     servidor — o stop pode disparar logo depois da leitura e os dois "vende 1" executarem. Nenhum mecanismo documentado
     garante "só reduz" contra o stop concorrente, então **a v1 não envia ordem direcional de saída nunca**. No prazo:
     proteção confirmada mantida, entradas bloqueadas, saída `exit_overdue` publicada (degradada), alerta `critical`
     no app e no celular, e a rota humana (§4, R3), que tem a mesma corrida residual com o stop e diz isso. A zeragem
     de fim de pregão começa `flatten_lead_min` antes do horário (D6) para haver tempo de o Everton agir; a zeragem
     compulsória da Rico é a última rede (regra não lida, D6). O prazo é limite para **escalar**, não prova de fill.
     Ordem do stop disparada e rejeitada pela bolsa dispara de novo no próximo tick elegível (ajuda oficial): "`sl`
     presente" não quer dizer "saída executada"; o robô reconcilia tentativas, negócios e saldo restante, e um fill
     **parcial** da ordem do stop exige identificar o residual e confirmar a proteção da parte que sobrou.
  4. Uma única máquina de estados por posição serializa saída, zeragem, emergência, reparo de stop e reconciliação: o
     reparador de stop não toca uma posição em saída, e uma saída não começa com outra em `exit_in_flight`/
     `exit_unknown`.

  O colchete é **mecanismo candidato**, dependente da semântica da Rico, com saída degradada explícita — não zeragem
  garantida. **Se a sessão demo mostrar que ele não zera de forma confiável dentro do prazo, o desenho volta para
  revisão antes do dinheiro real**; ninguém troca por um fechamento a mercado "só desta vez". Para a H-038, cuja saída
  pré-registrada é "a mercado em C" (plano irmão §1.2), o robô **começa** o colchete em C e grava o horário pretendido,
  o horário e o preço efetivos e a diferença — a série-modelo congelada da hipótese não muda; a série (iii), execução
  real, mede a diferença `[Astra R4]`.
- Posição que passa para o dia seguinte numa bolsa tem `sl`/`tp` **zerados** (ajuda oficial). Mais um motivo para a
  zeragem obrigatória; se ainda assim sobrar posição de um dia para o outro, a partida a mostra no diagnóstico e
  alerta; o primeiro ato **com autoridade de gestão** é protegê-la (§5.4) `[Astra R5]`.

## 3. Caminho da ordem

```
[MT5: ticks] → Strategy plug-in (puro) → Intent
            → Proposta (b3_proposals, gravada pela API ANTES de qualquer ordem)
            → hunter_risk_b3.evaluate (puro: checks[] completos + sizing com binding_constraint)
            → aprovada (aprovação vale 30 s) → claim atômico na API (autoridade na fase de entradas + kill + versão dos limites, §5.2)
            → pre_send_gate (relê tudo do agora, §3.9) → order_check → order_send (entrada limitada + sl)
            → confirmação do sl no servidor (meta 1 s desde o fill, relógio monotônico; senão SLTP; senão degradado + alerta + rota manual — nunca ordem direcional, §2.2)
            → reconciliação contínua (corretora × registro)
Saídas (stop/alvo no servidor, saída por tempo, zeragem, kill, manual): evaluate_exit sempre aprova.
```

### 3.1 Os checks — todos como dado (`b3_risk_profiles.limits`, versionado, editável só pelo Everton)

Motor: `hunter_risk_b3.evaluate(proposal, broker, account, limits, session, calendar, quote, kill_switch, *, spec)`
→ `RiskDecision`. Puro e determinístico; o instante é `broker.as_of`. Todo check é gravado em `checks[]` como
`{name, state, value, limit, input_ts, message}` mesmo depois da primeira reprovação; `state ∈ passed | failed |
unavailable`, e `unavailable` reprova.

| # | Check | Reprova quando | Insumo | Limite (dado) |
|---|---|---|---|---|
| 1 | `kill_switch` | efetivo ∈ {`TRADING_DISABLED`, `EMERGENCY`}, ou robô `DISARMED` | `b3_robot_arming` + escopos | — |
| 2 | `account_mode` | conta REAL sem K1; conta diferente da registrada | `account_info()` | hash da conta |
| 3 | `terminal_state` | `connected == False`, `trade_allowed == False` (K2), `tradeapi_disabled == True` | `terminal_info()` | — |
| 4 | `symbol_whitelist` | símbolo ≠ contrato vigente do dia; `symbol_info().trade_mode` ≠ negociação plena; dia de vencimento do contrato que vence | `b3_contracts` (vigência por contrato) | lista: `WIN` (e `WDO` se a estratégia pedir) |
| 5 | `trading_day` | feriado B3; sem linha de grade vigente para a data; pregão encurtado sem grade cadastrada | `b3_holidays`, `b3_session_grids` | — |
| 6 | `entry_window` | antes de `open + no_entry_first_min` ou depois de `entry_cutoff`; fora da janela da própria estratégia | grade + perfil | `no_entry_first_min`, `entry_cutoff_local` |
| 7 | `flatten_margin` | faltam menos de `min_minutes_before_flatten` para `flatten_at` | grade + perfil | `flatten_at_local` (antes da zeragem compulsória da Rico, D6), `min_minutes_before_flatten` |
| 8 | `quote_fresh` | último tick mais velho que `max_quote_age_s`; carimbo à frente além de 2 s; deslocamento de relógio do servidor não medido (§7.4) | `symbol_info_tick()` | `max_quote_age_s` |
| 9 | `spread` | `ask − bid > max_spread_ticks × tick` | tick | `max_spread_ticks` |
| 10 | `open_positions` | existe **qualquer** posição na conta (nossa ou não): máximo de posições abertas = 1 significa entrar só zerado | `positions_get()` | `max_open_positions = 1` |
| 11 | `order_in_flight` | existe ordem pendente na conta, ou intenção de entrada não terminada no registro | `orders_get()` + registro | 1 em voo |
| 12 | `contracts_caps` | (no sizing) teto por ordem e por posição | perfil | `max_contracts_per_order`, `max_contracts_per_position` |
| 13 | `trades_today` | entradas do pregão ≥ teto | registro + `history_deals_get` | `max_trades_per_day` |
| 14 | `daily_loss` | perda do pregão (realizado líquido + MTM líquido) ≥ limite → **aciona** `TRADING_DISABLED` até o próximo pregão (§4); histórico do pregão incompleto, âncora ausente ou marca velha → `unavailable` `[Astra R1, F3]` | §3.4 | `daily_loss_limit_brl` |
| 15 | `stop_geometry` | stop ausente, do lado errado, fora do tick, distância fora de `[min_stop_ticks, max_stop_ticks]`, stop já rompido pelo preço observado | proposta + tick | `min_stop_ticks`, `max_stop_ticks` |
| 16 | `trade_risk_vs_allowance` | **regra dura:** risco **modelado** em R$ da operação, medido do **pior preço admissível** (o preço-limite da entrada) até o stop, mais deslizamento suposto do stop e tarifas > folga diária restante `[Astra R1, F2]` | §3.4 | — (derivado do 14) |
| 17 | `trade_risk_cap` | risco modelado em R$ da operação (mesma conta do 16) > teto por operação | §3.4 | `max_loss_per_trade_brl` |
| 18 | `margin` | margem para o volume **final** > `min(alloc_per_trade_brl, margin_free × margin_use_max_pct)`; moeda da conta ≠ BRL; modo de margem ≠ o fixado; `order_check` do pedido final recusa. `order_calc_margin` é **estimativa** que ignora ordens e posições existentes (documentação oficial) — candidata, nunca garantia `[Astra R1, F4]` | `order_calc_margin()`, `order_check()`, `account_info()` | `alloc_per_trade_brl`, `margin_use_max_pct` |
| 19 | `broker_reject_breaker` | rejeições da corretora na janela ≥ `max_rejects` → **aciona** `TRADING_DISABLED` (latched, rearme manual) | registro | `max_rejects`, `reject_window_s` |
| 20 | `reconciliation_ok` | última reconciliação divergente, ou mais velha que `2 × reconcile_interval_s` | §5.3 | `reconcile_interval_s` |
| 21 | `audit_path` | API inalcançável ou buffer de indisponibilidade não vazio: **sem auditoria, sem entrada** | §3.8 | — |
| 22 | `signal_validity` | sinal do pregão não publicado dentro do prazo da própria estratégia (H-038: publicado até O+90 e utilizável só na janela de entrada C−30…C−25, nunca recalculado) `[Astra R2]`; fora da janela de entrada da estratégia; versão ≠ a armada; `params_hash` ≠ o congelado. **Três relógios separados** `[Astra R1, F4]`: o sinal vale o pregão (pela regra da estratégia); os insumos de mercado valem segundos (check 8); a **aprovação de risco** vale 30 s (`approved_at`/`expires_at`, regra da casa) — o carimbo do sinal nunca é renovado para caber | proposta + armamento | prazo da estratégia; 30 s da aprovação |
| 23 | `spec_unchanged` | especificação do símbolo, versão do terminal ou do pacote ≠ as fixadas no armamento (vigia, §3.9) | `symbol_info()`, `version()` | fixadas no armamento |
| 24 | `slippage_guard` | a entrada é **ordem limitada** a `ref ± max_slippage_ticks` (comprado: teto; vendido: piso), com validade no servidor compatível com a janela (`type_time`/`expiration` que o símbolo aceitar) e cancelamento depois de `entry_cancel_after_s`; a corrida cancelamento × fill é tratada (o que preencheu é protegido; o resto só conta como cancelado com confirmação da corretora; tempo esgotado = estado **incerto**, que bloqueia entradas). Sem combinação de validade/preenchimento provada na Rico (T14) → `order_lifecycle_unproven`, nenhuma entrada `[Astra R1, F10]`. Deslizamento medido > `slippage_alert_ticks` → `risk_event` | tick + `symbol_info()` | `max_slippage_ticks`, `entry_cancel_after_s`, `slippage_alert_ticks` |
| 25 | `equity_floor` (opcional) | patrimônio da corretora < piso | `account_info().equity` | `equity_floor_brl` (vazio = desligado) |

Cada um dos 25 tem um caso que passa e um que reprova na tabela de testes (§8).

### 3.2 Valores iniciais do Everton (17/10/2026) — dado, todos mudáveis por ele

| Chave | Valor | Origem |
|---|---|---|
| banca | **acima de R$ 10.000** | Everton, 17/10 (substitui o "R$ 1.000 na conta" da mensagem anterior do mesmo dia; ver D2) |
| `daily_loss_limit_brl` | **R$ 9.000** — atingido, entradas param pelo resto do pregão; saídas sempre permitidas | Everton, 17/10 |
| `alloc_per_trade_brl` | **R$ 1.000 "colocados em cada operação"** — alocação por entrada, **não** é valor de stop | Everton, 17/10; tradução por instrumento em §3.3 abaixo (D3) |
| `max_contracts_per_position` | pendente (a Sexta-feira pergunta) | — |
| `max_loss_per_trade_brl` | **proposta: R$ 250** (§3.5) | proposta deste desenho, D4 |
| `max_trades_per_day` | proposta: 1 (a H-038 opera uma vez por pregão) | D5 |

> **Registro (pedido pela Sexta-feira):** a Sexta-feira avisou, **uma vez**, que R$ 9.000 por dia é cerca de **90 % da
> banca** informada; o Everton **manteve** o valor. O desenho grava o valor dele. Na prática, o teto que limita uma
> operação é o `max_loss_per_trade_brl` (check 17) e a margem (check 18); com 1 contrato da H-038 a pior perda prevista
> por operação é ≈ R$ 210 (plano irmão §1.5), então o limite diário quase nunca será o que trava.

### 3.3 O que "R$ 1.000 por operação" vira em cada instrumento (D3, para o Everton confirmar)

- **Ações e ETFs da B3:** R$ 1.000 é o **nocional** comprado ou vendido: `quantidade = floor(1000 / preço / lote) ×
  lote` (lote 1 no fracionário). Fora do escopo da v1 (o robô começa só com futuros); a regra fica escrita.
- **WIN/WDO (futuros):** "valor colocado" não tem sentido direto — o nocional de 1 WIN é ≈ **R$ 41,4 mil** (pontos
  × R$ 0,20, com o índice ≈ 207 000 pts, plano irmão §1.5) e a garantia de day trade é pequena. **Mapeamento proposto:**
  **a margem de day trade consumida ≤ R$ 1.000**, medida em tempo de execução por `order_calc_margin()` (o número que
  o servidor da Rico aplica), e nunca acima de `margin_use_max_pct` da margem livre:
  `n_margem = floor(1000 / margem_por_contrato)`.
- **Risco em R$ por ponto que resulta:** WIN = `n × R$ 0,20` por ponto (tick de 5 pts = `n × R$ 1,00`); WDO =
  `n × R$ 10` por ponto (tick de 0,5 pt = `n × R$ 5`). A especificação do WIN foi lida na B3 em 17/10 (ponto R$ 0,20,
  tick 5 pontos, vencimento na quarta mais próxima do dia 15 dos meses pares); a do WDO **não** foi lida por mim (a
  página não respondeu) — os R$ 10/ponto vêm do plano irmão, marcados lá como "não lido". Em execução, o robô usa
  `symbol_info().trade_tick_value` e `trade_tick_size` e recusa se divergirem dos valores fixados no armamento (check 23).
- **A margem de day trade da Rico por contrato não foi lida:** o site da Rico (`rico.com.vc`) devolve **403 da CDN da
  XP** a acesso automatizado (testado 17/10/2026; não contornei). A Rico não publica o valor em página que eu
  conseguisse ler. **Exemplo hipotético, não um número da Rico:** se a margem fosse R$ 100 por WIN, `n_margem = 10`,
  risco de R$ 2,00 por ponto, e o stop de 0,5 % da H-038 (≈ 1 035 pts) custaria ≈ R$ 2.070 + custos — **21 % da
  banca numa operação**. É por isso que a alocação por margem **nunca** decide sozinha: o tamanho é o mínimo dos tetos
  (§3.5), e o teto por operação é o que normalmente vence.

### 3.4 Risco em R$ de uma operação e a folga diária

```
pior_preço_admissível = preço-limite da entrada (comprado: ref + max_slippage_ticks × tick; vendido: ref − …)
stop                  = stop final, alinhado ao tick pelo lado (comprado: para baixo; vendido: para cima)
risco_por_contrato    = |pior_preço_admissível − stop| / tick × valor_do_tick      # entrada no pior caso permitido
                      + stop_slippage_ticks × valor_do_tick                         # gap suposto no stop; dado, padrão 2
                      + tarifas_ida_e_volta_por_contrato                            # corretagem + B3, sem deslizamento
risco_modelado        = n × risco_por_contrato

perda_do_pregão       = max(0, −(Σ_deals profit_bruto − Σ_pernas custo_positivo + mtm_bruto_aberto − tarifa_saída_aberta))
folga_restante        = daily_loss_limit_brl − perda_do_pregão
```

`[Astra R1, F2, F3]` — o que mudou em relação à primeira redação e por quê:
- **Do pior preço admissível, não da referência.** Cenário: folga R$ 200, risco na referência R$ 200, fill dois ticks
  pior → R$ 202. Medindo do preço-limite, a banda inteira já está dentro da conta. Se a estratégia define o stop como
  percentual do **fill** (a H-038 define), o motor aprova o envelope: o stop calculado a partir do pior preço
  admissível; depois do fill o stop definitivo é recalculado, alinhado ao tick, e **nunca** fica mais longe do que o
  aprovado (se ficaria, usa o aprovado). Geometria persistida na proposta e revalidada no `pre_send_gate`.
- **"Nunca passa" vale para o risco modelado, não para a perda real.** Gap, leilão e rejeição do stop não têm teto:
  dois ticks supostos não limitam um stop atravessado por cem. A invariante demonstrável é
  `risco_modelado ≤ min(max_loss_per_trade_brl, folga_restante)`. A ultrapassagem real é **medida**
  (`stop_slippage_excess`, como no contrato SPOT §8), auditada e publicada no relatório; nunca escondida.
- **Sem dupla contagem.** Os R$ 2,51 do plano irmão já incluem 1 tick de deslizamento por perna; aqui as **tarifas**
  (≈ R$ 0,512 ida e volta no cenário do plano) são separadas do deslizamento, que entra uma vez na entrada (pelo preço
  limite) e uma vez no stop (pelos ticks supostos). Na perda **realizada**, os fills já contêm o deslizamento; só as
  tarifas são descontadas.
- **Contrato da perda do pregão:** (1) cada negócio entra **uma vez**, pela chave `deal ticket`; (2) custos são
  normalizados como valores **positivos** por perna — o maior entre o modelado e o lançado pela corretora
  (`commission`, `fee`); comissão negativa nunca vira ganho; (3) negócios de depósito/saque/ajuste
  (tipos não-negociação) ficam fora; (4) cobertura: o histórico pedido vai do início do pregão (âncora persistida) até
  agora, e a soma é conferida contra a variação do patrimônio da corretora no mesmo intervalo, descontados aportes e
  saques; divergência acima de `pnl_reconcile_tolerance_brl` → `daily_loss` `unavailable`; (5) a posição aberta
  desconta só a **tarifa de saída** estimada — a de entrada já está no realizado das pernas —; (6) sem âncora do pregão,
  sem histórico completo ou com marca mais velha que `max_quote_age_s` → entradas indisponíveis (lição de
  `docs/RISK_ENGINE.md` §5 e `docs/RISK_ENGINE_MEME.md` §7: o número que esconde perda é o zero).
- **A virada do pregão** só limpa a trava da perda diária **depois** de reconciliar; nunca limpa comando, rejeições ou
  `EMERGENCY`.
- O custo real da nota de corretagem entra no relatório diário (§7.2) e nunca reescreve uma decisão.

### 3.5 Sizing — o mínimo dos tetos, com o limitante publicado

```
n_bruto = min( max_contracts_per_order,
               max_contracts_per_position,
               floor(alloc_per_trade_brl / margem_por_contrato),                 # D3 (candidato)
               floor(margin_free × margin_use_max_pct / margem_por_contrato),     # margem livre
               floor(max_loss_per_trade_brl / risco_por_contrato),                # D4
               floor(folga_restante / risco_por_contrato) )                       # regra dura
n = floor(n_bruto × 0,5) em WARNING; senão n_bruto                                # 1 em WARNING vira 0, nunca 1
n normalizado a volume_min/volume_step/volume_max do símbolo, sempre para baixo
n < 1  →  reprovado (`sizing_zero`), nunca arredonda para cima
depois: margem do volume final + order_check do pedido final (check 18)
```

`[Astra R1, F4]` — a primeira redação omitia a margem livre e o multiplicador do `WARNING`. Insumos recusados antes do
sizing: valores não finitos ou não positivos, bid/ask invertidos ou zerados, moeda da conta ≠ BRL.

`binding_constraint` grava qual dos tetos venceu (ou `warning_halving`). **Proposta de padrão para o teto por operação
(D4): R$ 250.** Com a conta da §3.4 e os números do cenário do plano irmão (stop ≈ 1 035 pts = R$ 207; 1 tick de
entrada pelo preço-limite = R$ 1; 2 ticks supostos no stop = R$ 2; tarifas ≈ R$ 0,512), 1 contrato da H-038 tem risco
modelado ≈ **R$ 210,51** (conta conferida pela Astra com `decimal` na rodada 1). R$ 250 cobre 1 contrato com folga para
a variação do índice e é ≈ 2,5 % de uma banca de R$ 10 mil. Ele **não garante** que a H-038 abra 1 contrato: margem
insuficiente, `WARNING` ou risco acima do teto produzem **zero** `[Astra R1]`. O teto nunca passa da folga diária (é o
`min`), e o Everton muda o número quando quiser.

### 3.6 Custo por ida e volta comparado ao capital (consideração de desenho)

Do plano irmão §1.4 (fontes: tabela de tarifas da B3 de Ibovespa futuros e trechos de busca das páginas da Rico, que
bloqueiam leitura automatizada): corretagem **R$ 0** em minicontratos **se o RLP estiver ativo** (senão desconhecida,
não zero); B3 ≈ **R$ 0,256 por perna** em day trade; deslizamento suposto 1 tick = R$ 1,00 por perna. **Ida e volta ≈ R$ 2,51 por contrato ≈ 12,6 pontos**, dos quais
≈ R$ 0,512 são tarifas e R$ 2,00 são deslizamento suposto (não medido).

| Leitura | Valor | O que significa |
|---|---|---|
| vantagem mínima só para empatar | **≈ 12,6 pontos por contrato por operação** | qualquer regra precisa ganhar, em média, mais que isso por operação |
| em bp do nocional (≈ R$ 41,4 mil) | ≈ 0,61 bp | barato por nocional |
| sobre a alocação de R$ 1.000 | ≈ 0,25 % por contrato por operação | ~21 pregões × 1 operação ≈ **5 % ao mês** de custo sobre R$ 1.000 com 1 contrato |
| sobre a banca de R$ 10 mil | ≈ 0,025 % por contrato por operação | — |
| se a conta tivesse só R$ 1.000 (mensagem anterior) | ≈ 0,25 % da conta por operação; e um único stop da H-038 (≈ R$ 210,51 modelado) seria **21 % da conta** | não cabe com sentido econômico (plano irmão §1.5) |

Sem o RLP ativo, a corretagem é desconhecida e esta tabela não vale (D7). O robô **recusa armar** sem uma tabela de
custo com fonte e data (`fee_schedule_missing`).

### 3.7 Onde ficam estado e auditoria

| Dado | Onde | Quem escreve |
|---|---|---|
| perfis de limite, grades, feriados, contratos vigentes, tabela de custos | Postgres (`b3_*`, com `organization_id` e RLS) | Everton pela tela; grade/feriado/contrato por pessoa com nota de fonte |
| armamento, kill switch, rearme | Postgres (`b3_robot_arming`, `b3_kill_switch_transitions`) | Everton (tela); robô só escreve transições automáticas (perda diária, rejeições) |
| propostas, decisões, ordens, fills, reconciliações, heartbeats | Postgres, pela **API** com token do robô (escopo mínimo: inserir eventos B3 da sua organização e ler a própria configuração) | robô |
| posição, ordens e dinheiro **de verdade** | **corretora** (MT5) | — |

**Por que API e não conexão direta ao Postgres:** um DSN no PC é uma credencial de banco numa máquina doméstica; o
token do robô é revogável, de escopo mínimo e só alcança rotas idempotentes (`Idempotency-Key` = id do evento). A
revisão de segurança é obrigatória (§8).

### 3.8 O buffer de indisponibilidade (arquivo local declarado; o outro é o batimento do EA, §2.1)

`%LOCALAPPDATA%\HunterB3\outage-buffer.jsonl`: append-only, `fsync` por linha, cada linha com hash da anterior, rotulado
"buffer de indisponibilidade — não é estado". Regras: (1) **nunca é lido para decidir**; (2) só recebe eventos que a API
recusou ou não alcançou; (3) é reenviado em ordem, com idempotência, quando a API volta; (4) **enquanto não estiver
vazio, nenhuma entrada** (check 21) — saídas continuam e são gravadas nele; (5) **falha de disco ou de `fsync` nunca
aborta nem atrasa uma saída** `[Astra R1, F1]`: a saída segue, o evento fica na memória para reenvio e o alerta é
`critical`; entradas continuam bloqueadas. Na partida, o reenvio segue a ordem da §5.4: **depois** da proteção, com prazo, sem
bloquear saídas `[Astra R2, F1]`.

### 3.9 `pre_send_gate` e o vigia da especificação (o padrão do `meme-executor`)

**`pre_send_gate`** — o espelho de `signing_block`/`pre_sign_reason` do executor meme: entre a aprovação e o
`order_send` há esperas (API, terminal) e o mundo anda. Imediatamente antes de enviar uma **entrada**, o robô relê, do
estado como ele está **agora**: o resultado do **claim** da API (§5.2: autoridade da instância na fase de entradas, kill switch efetivo lido **na
mesma transação** que marca a intenção `submitting`, versão do perfil de limites e da grade iguais às da decisão,
aprovação não expirada), `terminal_info()` (K2, conexão), `positions_get()` e `orders_get()` vazios, perda do pregão
e margem relidas (a decisão carrega os *snapshots* e as versões; qualquer mudança → reavaliação, nunca envio com a
decisão velha), a especificação relida **neste instante** (não a leitura de 60 s atrás), cotação fresca, a janela de
entrada ainda aberta e o preço-limite ainda dentro de `max_slippage_ticks` da referência `[Astra R1, F5]`. Cenário que
isso fecha: o Everton baixa o teto de R$ 250 para R$ 100 depois da aprovação; com a versão do perfil na decisão, a
ordem de R$ 210 é recusada `limits_changed_before_send`. **Prazo depois das esperas `[Astra R2, F5/F9]`:** o claim dá um orçamento de envio
(`send_budget_s`, proposta 3 s) medido em relógio monotônico **e** em UTC; imediatamente antes do `order_send` — depois
de `order_check` e de toda leitura do terminal — o robô confere de novo, localmente, `agora < min(claim + orçamento,
expires_at da aprovação, authority_expires_at)`; passou → `aborted_before_send` (nada enviado, gravado). Um salto entre
os dois relógios ou um intervalo sem batimento maior que o orçamento (processo suspenso, PC que dormiu) aborta todo
envio pendente e força reconciliação. **A corrida que sobra é declarada:** depois dessa última conferência, o
`order_send` é a fronteira; uma chamada que fica presa e executa tarde não é cancelável por nós. Ela foi autorizada no
instante em que partiu; o resultado tardio vira `unknown` → reconciliação; e a ordem carrega o `sl` aprovado na própria
requisição, então nasce protegida. Não existe atomicidade entre o nosso banco e a corretora. Qualquer um falhando → recusa nomeada
`<motivo>_before_send`, gravada; a tentativa não é reaproveitada. **Saídas nunca passam por ele.**

**Vigia da especificação** — o espelho de `program_check`: no armamento o robô fixa `trade_tick_size`,
`trade_tick_value`, `volume_min`, `volume_step`, `trade_mode`, `filling_mode`, o modo de margem da conta, a versão do
terminal (`version()`) e a do pacote `MetaTrader5`. A cada 60 s e na partida, relê. Divergência → entradas recusadas
`spec_changed` (check 23) até o Everton rearmar conferindo os valores novos; leitura falha 3 vezes seguidas →
`spec_unreadable`, mesma recusa. Uma leitura boa **nunca** limpa uma divergência já vista. Saídas seguem.

## 4. Kill switch

Mesmos quatro estados e a mesma regra "o mais restritivo dos escopos" do contrato SPOT (`docs/RISK_ENGINE.md` §5):
sistema, organização, robô.

| Estado | Entradas | Ordens pendentes | Posições | Aciona | Volta |
|---|---|---|---|---|---|
| `ACTIVE` | permitidas | — | normais | — | — |
| `WARNING` | permitidas com tamanho × 0,5 | — | normais | perda do pregão ≥ `warning_fraction × limite` (proposta 0,5) | automática quando abaixo |
| `TRADING_DISABLED` | bloqueadas | **entradas** canceladas | geridas, stops no servidor | `daily_loss` (check 14) ou `broker_reject_breaker` (check 19) ou comando de agente | perda diária: **no próximo pregão, depois de reconciliar** (D8, é a frase do Everton "para o dia"); rejeições, inversão e comando: rearme manual |
| `EMERGENCY` | bloqueadas | as **do robô** canceladas (intenção durável até confirmar) | as **do robô** zeradas pelo colchete da §2.2 (intenção durável até confirmar; prazo vencido → `exit_overdue`, alerta, rota manual); posição/ordem manual do Everton não é tocada (D11) `[Astra R1, R4]` | botão do Everton (R1) ou comando dele (R2) | só rearme do Everton (K3), posterior ao comando |

**Diferença declarada em relação ao SPOT e aos memes:** lá, `EMERGENCY` **não** zera (numa curva sem comprador, zerar
realiza a perda máxima). Aqui o Everton pediu "cancela pendentes, zera e bloqueia até ele rearmar", e WIN/WDO são os
contratos mais líquidos da B3 — `auto_close_on_emergency = true` é **comportamento fixo do robô B3**, escrito aqui.

**As quatro rotas — e o que cada uma cobre se o nosso processo estiver morto** `[Astra R2]`:

| Rota | Quem | Caminho | Com o robô morto |
|---|---|---|---|
| R1 — botão no app web | Everton (OWNER, step-up) | API grava `EMERGENCY` + auditoria → robô lê a cada 2 s (no máximo 10 s, regra da casa) → cancela as ordens do robô, zera pelo colchete da §2.2 com prazo curto, confirma | **bloqueia** sim: é durável, a instância nova lê na partida e não arma entradas; **zerar** não, até o robô voltar e o Everton conceder gestão à instância nova (§5.2) → R3/R4 |
| R2 — comando | Everton: `b3_kill.py --level emergency`; agente: só `--level disabled` | mesma rota da API, auditada. A restrição é **autorização na API**, não convenção do script: credencial de agente que pedir `emergency`, rearme ou mudança de limite recebe 403 e auditoria `[Astra R1]` | idem R1 |
| R3 — à mão no MT5 | Everton | (1) desliga "Algo Trading" (K2): o terminal recusa toda ordem de API nova — o robô não envia mais nada; (2) confere a aba Ordens e apaga as pendentes (pedido de cancelamento não é cancelamento confirmado: confere de novo); (3) fecha a posição com clique direito → Fechar — com a mesma corrida residual com o stop do servidor que o robô evita, por isso conferir a aba Posições logo depois. O robô, vivo ou ao voltar, vê K2 desligada e grava `TRADING_DISABLED` (`manual_route`) | **sim** — a posição está na corretora |
| R4 — app/home broker da Rico | Everton | zera pela Rico com o PC desligado | **sim**, se a Rico mostrar ali a mesma posição (a provar na primeira semana real; não presumido) |

> R3 começa por desligar "Algo Trading" de propósito: assim o robô não pode mandar uma saída **nova** ao mesmo tempo
> que o clique do Everton (o mesmo problema de dois remetentes do F7). Desligar não cancela uma ordem que já partiu:
> antes de fechar, ele confere a aba Ordens e apaga as pendentes `[Astra R3-3, R4]`. O stop no servidor continua valendo
> durante R3.

**O exercício (drill)**, feito na sessão técnica demo (§6.2) e repetido no primeiro dia real com o mercado calmo:
1. Com 1 contrato aberto pelo robô: R1 → cronometrar até "zerado" na tela do MT5 e no app web (colchete apertando
   até zerar); confirmar que uma nova entrada é recusada `kill_switch` até o rearme.
2. Com 1 contrato aberto: matar o processo Python → conferir no terminal que o `sl` está na posição → o EA vigia avisa
   o celular em ≤ 30 s → R3. Religar o robô → fase 0 (diagnóstico) → "Conceder gestão" → reconciliação fecha a posição pelos negócios da corretora, vê K2 desligada,
   grava `TRADING_DISABLED`; religar K2 não destrava.
3. Com o PC desligado e 1 contrato aberto (sessão demo só se a Rico mostrar a demo no app; senão, primeiro dia real com
   o Everton presente): R4.
4. Rearme: só o Everton, na tela, com step-up, **depois** do comando; a retomada é recusada enquanto a perda do pregão
   estiver acima do limite.

## 5. Reconciliação, idempotência e partida

### 5.1 Plug-in de estratégia (qualquer regra mecânica)

```python
class StrategyPlugin(Protocol):
    key: str; version: int; params_hash: str          # congelados no pré-registro (H-038 para a primeira)
    def decide(self, ctx: StrategyContext) -> Intent | NoIntent: ...   # puro, Decimal, sem IO, sem relógio
```

`Intent` = `{side, entry_window_utc, stop_price | stop_points, target_price?, exit_at_utc?, reason}`. O robô só arma
uma estratégia cuja `key/version/params_hash` aparece numa nota do Obsidian (reuso de
`infra/scripts/obsidian_note_gate.py`, a mesma trava das ferramentas de estratégia). A H-038 entra embrulhando as
funções puras da tarefa W0-S do plano irmão (`decide_intraday_momentum`, `protective_stop`, `exit_instant`) — **sem
reescrever a regra**.

### 5.2 Idempotência

- `client_order_id` = derivado do `proposal_id` (`HB` + 16 caracteres base32 do sha256), gravado no `comment` da ordem;
  `magic` fixo por robô + versão da estratégia.
- **Um só executor por conta: a autoridade da instância `[Astra R1 F9, R3-5, R4-2, R4-3, R5-1, R5-2]`.** Uma linha
  única não é um envio único (dois processos que obtêm a mesma intenção enviariam duas vezes), e um batimento não prova
  que o outro remetente perdeu a capacidade de agir. O contrato tem **um** objeto de autoridade e **três** atos, em
  ordem, sem ciclo:

  | Fase | O que a instância pode fazer | Como entra | Como sai |
  |---|---|---|---|
  | **0 — leitura** | ler corretora (posições, ordens, negócios de toda a vida dos `position_id`) e, pela API, o registro; publicar **diagnóstico** (atribuição, proteção, pendências, divergências); avisar. **Nenhuma mutação**, nem SLTP | toda instância nasce aqui (id novo a cada partida, *mutex* do Windows impede um segundo processo no mesmo PC) | concessão |
  | **1 — gestão** | proteger (recolocar/apertar `sl`, nunca afrouxar o confirmado), sair pelo colchete (§2.2), cancelar ordens do robô, reconciliar efeitos | **"Conceder gestão"**, ato do Everton na tela (OWNER, step-up), só depois de o diagnóstico mostrar a instância anterior **neutralizada** (processo parado, ou "Algo Trading" desligado no terminal antigo) e as pendências dela resolvidas ou marcadas `unknown`. A API grava **uma** linha `b3_robot_authority`: conta+servidor (hash), host, `instance_id`, pregão, *fencing token* e **`authority_expires_at` absoluto** = fim do pregão vigente | vencimento absoluto, revogação explícita do Everton, conta/servidor/host diferentes dos gravados |
  | **2 — entradas** | além da gestão, entradas (claim de 30 s pela API, §3.9) | **"Armar entradas"** (o K3), ato do Everton, só com a fase 1 vigente, reconciliação limpa e os checks da §3.1 válidos | desarmar, kill switch, K2 desligada observada (bloqueio local imediato), batimento com a API velho |

  Regras que fecham os cenários da Astra:
  - **Validade única.** `authority_expires_at` é a única validade da autoridade; o batimento de 5 s e o frescor de
    15 s medem **aptidão para entradas** (sem API fresca, nada de claim, nada de entrada), **nunca** transferem nem
    revogam a gestão. Cenário fechado: a API cai 20 s antes da saída programada — a instância continua autorizada a
    apertar o colchete até o fim do pregão (R5-1).
  - **Antes de toda mutação**, localmente: conta e servidor atuais = os da autoridade; `instance_id` = o da
    autoridade; `agora < authority_expires_at` (relógio UTC e monotônico, como o orçamento da §3.9). Falhou → nada
    sai. No vencimento real: nenhuma mutação posterior, alerta se houver posição ou residual, **sem renovação
    implícita** por relógio ou por reinício.
  - **Nenhuma outra instância recebe autoridade** enquanto uma linha vale para a mesma conta; a concessão a uma nova
    exige a revogação explícita da anterior, que a tela só oferece com a anterior neutralizada. **Troca no mesmo
    pregão** (inclusive no mesmo host, depois de um reinício): parar ou neutralizar a antiga, reconciliar as
    solicitações dela, revogar, conceder à nova — nunca esperar um prazo vencer, nunca reaproveitar `instance_id`.
    A revogação não resolve sozinha uma requisição antiga em trânsito: ela vira `unknown` no diagnóstico da nova.
  - **O `unknown` atravessa instâncias `[Astra R6]`.** Conceder gestão com uma pendência `unknown` não a declara
    resolvida: um SLTP incerto da posição continua proibindo nova modificação na instância nova (no exemplo 90/95/99,
    reiniciar entre A e B não libera B), e uma entrada `submitting/unknown` continua sem reenvio e bloqueando entradas.
    Autoridade habilita a gestão; não apaga os impedimentos da máquina de estados da posição.
  - **"Nenhuma mutação depois do vencimento"** quer dizer não **iniciar** envio depois de detectá-lo; não promete que
    efeitos de solicitações anteriores, já em trânsito, desapareçam.
  - **Sem ciclo (R5-2):** a fase 0 não depende de nada; a concessão depende do diagnóstico da fase 0; a recuperação
    com mutação depende da concessão; as entradas dependem da recuperação. `EMERGENCY`, trava diária e rejeições
    **não** são limpas pela concessão de gestão — a gestão existe justamente para zerar e proteger sob elas.
  - **Um host autorizado na v1** (o PC; o hash do host vai na autoridade). Um segundo Windows anexado à mesma conta
    nunca passa da fase 0: zero mutações, com ou sem API.
  - **O residual declarado:** um processo suspenso **depois** da última conferência local e antes da chamada; a
    corretora não conhece o nosso *fencing token*. Por isso a única instância que pode estar nesse estado é a que tem
    a autoridade, e a revogação passa pela neutralização física dela.
  - A transição `approved → submitting` de uma **entrada** é um `UPDATE … WHERE status = 'approved' AND expires_at >
    now() AND authority_token = :token AND phase = 'entries'` na mesma transação que relê o kill switch efetivo
    (ordem de travas sistema → organização → robô, como `docs/RISK_ENGINE.md` §5) e a versão dos limites — quem não
    ganha a linha não envia.
- **Gravação antes do envio:** proposta aprovada (API) → claim `submitting` (API) → `order_send` → resultado (API). Se a
  API não aceitar o claim, não há envio.
- Reprocessar o mesmo sinal ou o mesmo evento **não** cria segunda ordem: a proposta é única por
  `(estratégia, versão, pregão, janela)` e a intenção por `proposal_id` (teste obrigatório, §8).
- **Queda entre o envio e o registro:** intenção `submitting` sem resultado vira `unknown`, que **bloqueia entradas**
  até ser resolvida. Resolução: procurar na corretora por ticket de ordem e de negócio, identificador da posição e
  `comment` (ordens, histórico de ordens, negócios do pregão inteiro); se a Rico não preservar o `comment` (**não
  sabemos**; T8), `magic + símbolo + volume + janela` é **indício**, não prova — nenhum ou dois candidatos mantêm
  `unknown` e alertam `[Astra R1]`. Ausência temporária no histórico não prova que não executou; expirar a aprovação
  **não** encerra uma ordem enviada. Uma intenção `submitting`/`unknown` **nunca** é reenviada.

### 5.3 Reconciliação (na partida e a cada `reconcile_interval_s`, proposta 5 s)

A corretora é a verdade (posições, ordens, negócios do pregão); o Postgres é o registro.

| Situação | Ação |
|---|---|
| corretora = registro | ok |
| posição com o `magic` do robô e sem registro (queda depois do fill) | **adota** só com **atribuição inequívoca**, que vem da própria corretora e por isso existe também com a API fora `[Astra R2, F1]`: todos os negócios do `position_id` da posição (`history_deals_get`) têm o `magic` do robô e `reason` de robô (`DEAL_REASON_EXPERT`) ou do stop/alvo do servidor (`DEAL_REASON_SL/TP`), e a soma deles dá o volume atual; o `sl` que a própria ordem de abertura pediu (`ORDER_SL` em `history_orders_get`) é **o stop pedido pela ordem**, não "a aprovação do motor" — a decisão persistida só existe na API `[Astra R3-4]`. Um negócio `DEAL_REASON_CLIENT/MOBILE/WEB` no meio (o Everton mexeu à mão), inclusive um que deixe a mesma quantidade final, ou `magic`/`reason` não preservados pela Rico (T8) → **não adota nem zera**: bloqueia entradas, alerta e indica a rota manual. Com a API de volta, a cadeia ainda tem de bater com as intenções gravadas |
| posição **sem** o nosso `magic` (manual do Everton, ou outro robô) | **para entradas** (`foreign_position_present`), alerta, **não toca** — a posição é dele (D11 se ele quiser outro comportamento) |
| registro diz aberta, corretora zerada | fecha pelos negócios da corretora; sem negócio que explique → `TRADING_DISABLED` + alerta |
| quantidade diferente | corretora vence; entradas bloqueadas até 2 passes consistentes |
| posição **atribuída** ao robô sem `sl`, com `sl` do lado errado, longe do autorizado ou cobrindo quantidade diferente (e fora de uma saída em curso, item 4 da §2.2) | `TRADE_ACTION_SLTP` imediato, só apertando ou recolocando — nunca afrouxando o último `sl` conhecido; sem confirmação em `naked_grace_s` → estado **degradado** com alerta `critical` e rota manual (sem ordem direcional, §2.2); `naked_position_flattened` só depois de zerada **comprovada** `[Astra R1, F6]`. A carência conta do instante do **fill na corretora** (`time_msc` do negócio), não do início do processo: numa partida que encontra posição desprotegida desde antes, a carência já acabou `[Astra R2]` |
| ordem pendente que não é nossa | para entradas, alerta |
| posição no sentido oposto depois de uma saída | põe `sl` imediatamente e zera pelo colchete da §2.2, `reversal_detected` `critical`, entradas travadas até rearme — defesa adicional; a prevenção é a saída pelo colchete |
| ordem de entrada residual (limitada que não terminou) | cancela com confirmação; o que preencheu é protegido; sem confirmação → `unknown` |
| leitura da corretora falhou | é `unavailable`, não "zerado": entradas bloqueadas; saídas tentam |

**Nunca se opera em cima de uma posição desconhecida** (check 10 + esta tabela).

### 5.4 Partida segura

Ordem fixa `[Astra R1 F1, R4-2, R4-3]`. **Limitação aceita da partida:** uma instância nova não tem identidade nem
autoridade verificadas antes de falar com a API, então até lá ela **só lê e avisa** — quem protege nesse intervalo é
o `sl` que já está no servidor e o Everton. O disco nunca bloqueia nada. (1) *mutex* do Windows (um processo só);
(2) anexar ao terminal sem credencial; (3) ler conta e servidor — conta diferente da registrada, ou conta REAL sem K1
→ só leitura, não toca nada; (4) ler posições, ordens e negócios de **toda a vida** dos `position_id` abertos; posição sem `sl`
ou não atribuível → alerta `critical` (app, se alcançável, e o EA vigia no celular) **sem mutação**; (5) falar com a
API, com prazo e repetição: identidade da conta e do host, registro, kill switch; publicar o **diagnóstico** da fase 0
(§5.2) — sem resposta, continua em (4), só lendo e avisando; (6) esperar a **concessão de gestão** do Everton; com ela:
proteger o atribuível (posição do robô sem `sl` → o mais apertado entre o `sl` que a ordem de abertura pediu e o último
confirmado no registro; posição com `sl` → não afrouxa) e reconciliar os efeitos; (7) reenviar o buffer, com prazo,
sem bloquear nada; (8) reconciliar com o registro; (9) se `EMERGENCY` → cancelar e zerar; se K2 desligada → gravar `TRADING_DISABLED` (`manual_route`);
(10) toda aprovação com mais de 30 s expira e todo `submitting` vira `unknown`; (11) com a reconciliação limpa, espera
o **K3** do Everton para esta instância (fase 2 da §5.2) — só então o laço de entradas.

## 6. Sequência para dinheiro real — checklist do Everton

**[EVERTON]** marca o que só ele faz. O resto é nosso.

### 6.1 Pré-requisitos
1. **[EVERTON]** Assinar o ADR que abre a exceção "live B3 antes da Fase 4" (D1) e autorizar a mudança da regra dura
   do `CLAUDE.md`. Sem isso, nenhum código que envie ordem real é integrado.
2. **[EVERTON]** Confirmar na área logada da Rico: MetaTrader 5 habilitado na conta (trecho de busca diz "isento para
   clientes Rico", não lido por mim); **política da Rico para robôs/EA** (não encontrada pela tarefa irmã); margem de
   day trade do WIN (e do WDO); **horário da zeragem compulsória** de day trade; RLP ativo (D6, D7).
3. **[EVERTON]** Configurar o PC: plano de energia sem suspensão no pregão; atualização automática do Windows fora
   do pregão; relógio sincronizado (NTP).
4. Ondas 1–4 entregues e revisadas (§9), suíte verde com saída colada.

### 6.2 Sessão técnica em conta DEMO (não é teste de estratégia: é fiação e dedo-gordo)
1. **[EVERTON]** Abrir conta demo pelo próprio MT5 (a Rico tem artigo "como ativar um simulador da plataforma
   MetaTrader", trecho de busca) e entrar nela no terminal.
2. **[EVERTON]** Configurar o MetaQuotes ID do celular na aba Notificações, ligar "Algo Trading", anexar o EA vigia,
   iniciar o robô; depois do diagnóstico, "Conceder gestão" na tela; depois da reconciliação, "Armar entradas" (K3) com
   `max_contracts_per_position = 1`.
3. Roteiro de provas, cada uma com evidência (captura da aba Negociação/Histórico do MT5 + linhas do Postgres + log):
   - T1 quantidade: a ordem sai com **exatamente** 1 contrato; tentar 2 com o teto em 1 → `contracts_caps`.
   - T2 stop no servidor: `positions_get()[0].sl` igual ao calculado e visível no terminal em ≤ 1 s.
   - T3 stop dispara **sem o robô**: stop perto do preço, matar o robô e desligar a rede do PC → ao voltar, o histórico
     mostra o stop executado pelo servidor.
   - T4 zeragem: `flatten_at` provisório perto → posição zerada pelo colchete da §2.2 (tempo até
     zerar medido); com o Python morto, o EA vigia avisa o celular a 15 min do fim e ninguém além do Everton zera.
   - T5 drill do kill switch completo (§4, passos 1–4).
   - T6 reconciliação: Everton abre 1 contrato à mão → robô recusa `foreign_position_present` e não toca.
   - T7 o `sl` da Rico: descobrir se vira ordem stop na B3 ou é gatilho do servidor (o que aparece na aba Ordens).
   - T8 o `comment`, o `magic` e o `reason` sobrevivem na ordem e no negócio da Rico (a atribuição da §5.3 depende do
     `magic` e do `reason`)? Quais `type_filling` o símbolo aceita (`symbol_info().filling_mode`)?
   - T9 rejeição: volume inválido por gancho de teste → rejeição nomeada; `max_rejects` rejeições → `TRADING_DISABLED`.
   - T10 reinício com posição aberta: matar e religar → adota, confere `sl`, não duplica.
   - T11 relógio: deslocamento entre o carimbo dos ticks e o UTC medido e gravado (§7.4).
   - T13 saída pelo colchete: quais níveis de `sl`/`tp` encostados a Rico aceita (bid/ask, ±1 tick, mínimo exigido);
     quanto tempo o colchete leva para zerar (distribuição em várias saídas); com o Python morto no meio do aperto a
     posição fica com o colchete apertado; no prazo **nenhuma** ordem direcional é enviada (`exit_overdue`, alerta);
     SLTP rejeitado e com resposta atrasada; ordem do stop disparada com retorno atrasado e com fill parcial; minutos sem
     negócio; posições que **não** zeraram até o corte entram na conta; `TRADE_ACTION_SLTP` numa posição que já não existe falha. Critério: **nenhuma exposição nova e
     nenhum instante sem stop** em todas as saídas da sessão.
   - T14 ciclo da ordem limitada: entrada limitada longe do preço → expira/cancela com confirmação; corrida cancelamento
     × fill parcial → a parte preenchida fica protegida; quais `type_time`/`expiration_mode` o WIN aceita na Rico.
   - T15 dois processos: segundo robô no mesmo PC é barrado pelo *mutex*; robô num segundo Windows anexado à mesma
     conta não arma (host não autorizado) e faz **zero mutações**, com ou sem API; com a autoridade vencida ou revogada o
     primeiro para de enviar qualquer mutação; processo suspenso depois da última conferência (gancho de teste).
   - T16 autoridade por instância: primeira partida zerada (fase 0 → concessão → K3); reinício com posição protegida e
     desprotegida; API fora por mais de 15 s com posição aberta (a gestão continua, entradas param) e voltando;
     vencimento no fim do pregão (nenhuma mutação depois, alerta); troca de instância no mesmo pregão com requisição
     antiga em trânsito; `EMERGENCY` vigente na concessão (não é limpo); K2 desligada e religada com o Python morto →
     não entra sem K3 novo.
   - T17 aviso do EA: o celular do Everton recebe as três notificações (batimento parado, sem `sl`, perto do fim).
   - T12 relatório diário gerado com os números da sessão.
4. Critério: **T1–T17 todos verdes, em pelo menos duas sessões em dias diferentes** (uma depois de 03/11, com a grade
   nova). Qualquer vermelho → corrige → repete.

### 6.3 Real
1. **[EVERTON]** Gravar os limites na tela (perda diária R$ 9.000, teto por operação, contratos, operações por dia).
2. **[EVERTON]** Armar a versão congelada da estratégia (nota do Obsidian da H-038).
3. **[EVERTON]** Digitar `ENABLE_B3_LIVE_TRADING=true` no ambiente do PC (K1); entrar na conta **real** da Rico no
   terminal; ligar "Algo Trading" (K2); na tela, "Conceder gestão" à instância e, com a reconciliação limpa,
   "Armar entradas" (K3).
4. Primeiro dia real: 1 contrato, 1 operação, drill R1 com o mercado calmo, relatório lido por ele à noite.
5. **[EVERTON]** Decidir se continua, com o relatório na mão.

## 7. Auditoria, observabilidade e relógio

### 7.1 Auditoria
`audit_logs` para: armar/desarmar, mudança de limite (antes/depois), transição do kill switch (com rota R1–R4 e ator),
proposta e decisão de risco (com `checks[]`), intenção de ordem, resultado do `order_send` (retcode), fill, `sl`
confirmado/ausente, divergência de reconciliação, buffer reenviado.

### 7.2 Relatório diário (por pregão)
Operações; pontos e R$ brutos; a **ponte** entre o PnL da corretora (reconciliável com o patrimônio) e a reserva conservadora de tarifas que o limite diário usa `[Astra R2]`; custos **modelados** × **da nota de corretagem** (lançada pelo Everton ou lida do extrato
— D12); PnL líquido; deslizamento real × modelo (fill − referência, em ticks, por perna); recusas por motivo (as 25 da
§3.1); latências (sinal → envio → fill → `sl` confirmado); incidentes de reconciliação; minutos com heartbeat ausente.
Sem dado, a linha diz "não informado" — nunca zero.

### 7.3 Alertas e cão de guarda
Heartbeat do robô pela API a cada 5 s (`hb:b3:robot`, gravado pela API no Redis da VPS). Um cão de guarda **na VPS**
(processo já existente de alertas ou um novo leve) alerta como `critical` se o heartbeat sumir por > 30 s durante o
pregão, e com prioridade máxima se havia posição aberta. Canal: Sentry `critical` (já no stack) + faixa no app; um canal
de celular além do aviso nativo do EA vigia (§2.1) é decisão do Everton (D13). Outros `critical`: `naked_position_flattened`, `exit_overdue`, `exit_unknown`, `reversal_detected`, `foreign_position_present`,
`broker_reject_breaker`, `daily_loss`, divergência de reconciliação, buffer não vazio por > 60 s.

### 7.4 Relógio
Armazenamento sempre em UTC. A documentação do pacote diz que o terminal entrega tempo em UTC; corretoras configuram
o horário do servidor de formas diferentes, então o robô **mede**: na partida e a cada 10 min compara o carimbo do
último tick com o UTC do PC (NTP) durante o pregão; deslocamento fora de `±max_clock_offset_s` ou não medido →
`quote_fresh` `unavailable`. Grava o carimbo bruto do servidor e o UTC derivado. Grades da B3 ficam em horário de
Brasília com vigência (`valid_from`, `valid_until`, nota de fonte — exemplo: OC 050/2026-VNC, WIN 09:00–18:25 e ajuste
18:00–18:15 a partir de 03/11/2026), convertidas a UTC por data com `zoneinfo`.

## 8. Testes

- **Adaptador falso do MT5** (`services/b3-robot/tests/fakes/mt5_fake.py`, rotulado como falso, só em teste): simula
  conta *netting*, `sl`/`tp` disparando no servidor pelo último negócio com gap, preenchimento parcial, rejeições com
  retcode, desconexão, "Algo Trading" desligado, `comment` descartado, ruído de `float`, herança de stop do netting
  (inclusive o `sl=0` que apaga).
- **Tabela de casos** do motor: cada um dos 25 checks com um caso que passa e um que reprova; todos os checks
  avaliáveis presentes em `checks[]` depois da primeira reprovação; `binding_constraint` correto para cada teto e para
  `warning_halving`.
- **Propriedades (hypothesis):** `risco_modelado ≤ min(teto por operação, folga restante)` sempre, com o risco medido
  do preço-limite; `n ≤` cada teto; `WARNING` com `n_bruto = 1` dá 0; kill ≥ `TRADING_DISABLED` ⇒ nunca aprova;
  `evaluate_exit` sempre aprova; conversão `Decimal ↔ float` exata para todo múltiplo de tick na faixa de preço;
  requisição que aumenta/inverte com `sl=0` é recusada e redução/fechamento total nunca são; perda do pregão com negócio
  duplicado, comissão negativa e depósito no meio do dia igual à perda verdadeira; `patrimônio = caixa + Σ posições`
  no relatório.
- **Idempotência e concorrência `[Astra R1]`:** reprocessar o mesmo sinal/evento 2× → uma ordem; dois executores com o
  mesmo sinal → um só ganha o claim; instância sem autoridade (vencida, revogada, outra conta) não envia nada; queda simulada entre `order_send` e o
  registro → `unknown`, nenhuma segunda ordem; `unknown` com dois candidatos → continua `unknown`.
- **Matriz de falhas `[Astra R1]`:** Python morto, terminal morto, IPC travado (chamada que não volta), API fora, disco
  cheio, troca de conta demo→real, K1 desligada com posição aberta, K2 desligada e religada (não destrava), fill
  parcial, cancelamento × fill, saída por tempo × stop do servidor ao mesmo tempo (o colchete da §2.2 não cria
  exposição nova), processo suspenso depois do claim, depois da última leitura e com `order_send` que volta depois da
  expiração, posição manual no mesmo símbolo que deixa a mesma quantidade final, mudança de limite entre a aprovação e
  o envio, partida com posição desprotegida desde antes. Cada linha tem o estado esperado da máquina de estados de
  R0 e um teste.
- **Partida:** posição na corretora sem registro e com cadeia de negócios nossa → adotada; com negócio manual no meio →
  não adotada, entradas bloqueadas; partida com API fora → só lê e avisa, nenhuma mutação `[Astra R5]`; aprovação com 31 s → expirada, nunca
  executada.
- **Replay:** fita de ticks real do WIN exportada pelo Everton do MT5 (fixture rotulada, real) passa pelo laço inteiro
  com o adaptador falso; a saída (propostas, decisões, ordens) tem hash fixo — duas execuções, mesmo hash.
- **Contrato do adaptador real:** a mesma suíte do falso contra o terminal demo, marcador `live`, **nunca em CI**,
  executada pelo Everton na sessão técnica.
- **Segredo:** teste que falha se `login`/`password` aparecerem em qualquer chamada, config serializada, log ou
  heartbeat; `LiveExecutionAdapter` da linha cripto continua levantando `LiveTradingDisabled` (teste existente intacto).

## 9. Ondas, esforço e revisões

Regra das ondas: `.claude/rules/parallel-subagent-driven-development.md`. Nenhuma tarefa toca os arquivos do painel de
segunda (tarefas W0-* do plano irmão). Começa **depois** da aprovação deste desenho e da D1.

| ID | Tarefa | Files | Depends-on | Dono (modelo) |
|---|---|---|---|---|
| R0a | Contrato normativo `docs/RISK_ENGINE_B3.md`: máquina de estados de entrada/proteção/saída (autoridade de envio, saída incerta, `unknown`, `exit_in_flight`/`exit_unknown`, `aborted_before_send`, armamento por instância, atribuição da posição) com a queda do processo em **cada intervalo** entre envio, leitura e confirmação, a saída pelo colchete da §2.2, matriz de falhas (§8), formato de `hunter_hb` | `docs/RISK_ENGINE_B3.md` | aprovação deste desenho | risk-engine-guardian (opus) |
| R0b | ADR 0007 (exceção "live B3", escopo autorizado, exceção dos arquivos locais do EA) para o Everton assinar | `docs/decisions/0007-robo-b3-mt5-excecao-live.md`, `docs/decisions/README.md` | aprovação deste desenho | documentation-writer (sonnet) |
| R0c | Esqueleto do workspace: serviço vazio `services/b3-robot` registrado; dependência `MetaTrader5; sys_platform == 'win32'` só no robô (CI Linux não a instala; o adaptador importa sob demanda) | `pyproject.toml` (raiz), `uv.lock`, `services/b3-robot/pyproject.toml` | aprovação deste desenho | devops-engineer (sonnet) |
| R1 | Motor puro `hunter_risk_b3` — pacote irmão de `hunter_risk` e `hunter_risk_meme` na mesma distribuição, com teste de fronteira (nenhum importa o outro), como o precedente da T4.14 — (insumos, limites, 25 checks, sizing, kill switch, sessão/calendário puros) + tabela de testes + propriedades | `packages/risk-core/hunter_risk_b3/**`, `packages/risk-core/tests/unit/b3/**`, `packages/risk-core/pyproject.toml` (só a lista `packages`) | R0a | risk-engine-guardian (opus) |
| R2 | Adaptador MT5: porta (`Protocol`), conversão Decimal↔float, invariante `would_delete_stop`, vigia da especificação; falso do MT5 e suíte de contrato | `packages/exchange-adapters/hunter_exchanges/mt5/**`, `packages/exchange-adapters/tests/mt5/**`, `services/b3-robot/tests/fakes/mt5_fake.py` | R0a, R0c | exchange-integration-specialist (sonnet) |
| R3 | Schema `b3_*` (perfis versionados, grades com vigência, feriados, contratos, tabela de custos, armamento, transições, autoridade das instâncias, propostas, intenções, ordens, negócios, reconciliações) + RLS + migração | `packages/core/hunter_core/db/models/b3.py`, `packages/core/hunter_core/db/models/__init__.py`, `infra/migrations/versions/00xx_b3_robot.py`, `packages/core/tests/integration/test_schema_b3.py` | R0a | database-architect (opus) |
| R4 | API: token do robô (escopo mínimo), fases da autoridade (diagnóstico, conceder gestão, armar entradas, revogar) + claim atômico, ingestão idempotente, armamento/kill/limites (OWNER + step-up; agente só `disabled`), heartbeat | `apps/api/hunter_api/routers/b3_robot.py`, `apps/api/hunter_api/services/b3_robot/**`, `apps/api/hunter_api/app.py` (só o `include_router`), `apps/api/tests/unit/b3_robot/**`, `apps/api/tests/integration/b3_robot/**` | R3 | backend-specialist (sonnet) |
| R5 | Serviço `services/b3-robot` (partida, laço, claim, `pre_send_gate`, executor, ciclo da ordem limitada, reconciliação, atribuição pela cadeia de negócios, saída pelo colchete, máquina de estados da posição, detector de inversão, buffer, batimento, armamento por instância) | `services/b3-robot/hunter_b3_robot/**` (exceto `strategies/`), `services/b3-robot/tests/**` (exceto `fakes/` e o replay) | R1, R2, R4 | backend-specialist (sonnet) → revisão risk-engine-guardian (opus) |
| R6 | Tela: armar/desarmar, kill (R1), limites, estado ao vivo (comando aceito × cancelamento pendente × zerado confirmado, idade das leituras), relatório diário | `apps/web/app/[org]/b3/robo/**`, `apps/web/components/b3/**`, `apps/web/lib/nav-registry.ts`, `packages/shared-types/**` (tipos gerados) | R4 | frontend-specialist (sonnet) |
| R7 | EA vigia MQL5 (só `SendNotification`, nenhuma ordem; teste que procura `OrderSend`/`CTrade` no fonte e falha) + `b3_kill.py` | `infra/mt5/HunterVigia.mq5`, `infra/mt5/LEIA-ME.md`, `infra/scripts/b3_kill.py`, `infra/scripts/tests/test_b3_kill.py` | R0a, R4 | risk-engine-guardian (opus) |
| R8 | Plug-in H-038 (embrulho do módulo W0-S) + replay | `services/b3-robot/hunter_b3_robot/strategies/**`, `services/b3-robot/tests/replay/**` | R5, W0-S | quant-engineer (opus) |
| R9a | Cão de guarda do batimento na VPS | `services/b3-watchdog/**`, `infra/docker/docker-compose.yml` | R4 | devops-engineer (sonnet) |
| R9b | Runbook da ativação (§6) | `docs/runbooks/robo-b3-ativacao.md` | R5, R6, R7, R9a | documentation-writer (sonnet) |
| RV | Revisões obrigatórias: risk-engine-guardian (R1, R5, R7), security-reviewer (R4, token, segredo), database-architect (R3), code-reviewer (todas), Astra no diff de cada uma | — | cada onda | — |

Ondas: **1** = R0a, R0b, R0c (disjuntas) · **2** = R1, R2, R3 (disjuntas) · **3** = R4 · **4** = R5, R6, R7
(disjuntas; R5 e R7 consomem o contrato de coordenação congelado em R0a) · **5** = R8, R9a (disjuntas) · **6** = R9b ·
revisões ao fim de cada onda. Os registros compartilhados têm dono único: `pyproject.toml` da raiz/`uv.lock` = R0c; `packages/risk-core/pyproject.toml` = R1; `models/__init__.py` = R3;
`app.py` = R4; `nav-registry.ts` e `packages/shared-types` = R6; `docker-compose.yml` = R9a. Se aparecer outro arquivo
comum durante a execução, a tarefa vai para a onda seguinte (regra das ondas).

**Estimativa honesta `[Astra R1]`:** caminho crítico R0a (1,5 d) → R1 (2 d) → R4 (1,5 d) → R5 (3,5 d) → R8 (1 d), mais
revisões obrigatórias e correções de cada onda (~2–3 d no total): **~11 a 14 dias úteis de agentes** até "pronto para a
sessão técnica demo". Isso é estimativa de **implementação**, não de prontidão: a sessão demo depende da agenda do
Everton e pode mandar código de volta (T7, T8, T13 e T14 decidem semântica que hoje não conhecemos). Começando em 20/10,
a **primeira sessão demo fica, na melhor hipótese, entre 05/11 e 10/11**; a segunda, em outro dia. **Não fixo data de
dinheiro real**: ela vem depois das duas sessões verdes e da decisão dele. Encurtar cortaria revisão ou sessão demo, e
as duas existem porque KB-0149 §5.27 mostrou que pagam.

## 10. O que o Everton precisa decidir

| # | Decisão | Proposta deste desenho |
|---|---|---|
| D1 | Assinar o ADR que abre a exceção "live B3 antes da Fase 4" e autorizar a mudança da regra dura do `CLAUDE.md` (um agente não pode fazer isso por ele; a mensagem de um agente não é consentimento). O ADR registra o **escopo** autorizado — conta, instrumentos, teto de contratos, data de revisão — e se o portão de evidência (Portão B) fica dispensado, como a variante "teste pequeno" do contrato meme exige escopo e vencimento `[Astra R1]`; e registra a exceção dos arquivos locais do EA (§2.1) | necessário antes de R5 |
| D2 | Capital: banca "acima de R$ 10.000" (17/10) ou "R$ 1.000 na conta" (mensagem anterior do mesmo dia)? | o robô usa o patrimônio da corretora; os limites ficam como ele gravar |
| D3 | "R$ 1.000 por operação" em futuros = **margem consumida ≤ R$ 1.000**? | sim, com os outros tetos por cima (§3.3) |
| D4 | Teto de perda por operação | **R$ 250** (1 contrato da H-038) |
| D5 | Máximo de contratos por posição e de operações por dia | 1 e 1 na primeira semana |
| D6 | `flatten_at` (antes da zeragem compulsória da Rico, que ele lê na área logada) | a confirmar com o horário da Rico |
| D7 | RLP ativo? (sem ele a corretagem é desconhecida e a tabela de custo da §3.6 não vale) | — |
| D8 | A trava da perda diária volta sozinha no pregão seguinte? | sim (é "para o dia"); `EMERGENCY` só com rearme |
| D9 | VPS Windows paga, quando? | decidir **antes** do primeiro dia real: PC = operação supervisionada; sem supervisão = VPS (§2) |
| D10 | Aceita que, com o Python morto, **ninguém além dele** zera (o EA só avisa o celular)? É a consequência de ter um só remetente de ordens (§2.1). O `sl` **confirmado** continua no servidor nesse caso, porque nenhuma saída do robô o retira (§2.2) — e não vale de um pregão para o outro (o servidor zera os níveis na virada) | sim; a alternativa (EA que zera) só volta com prova de exclusão entre remetentes |
| D11 | Posição manual dele na conta: o robô só para (padrão) ou zera? | só para |
| D12 | Custos reais: ele lança a nota de corretagem ou autorizamos ler o extrato? | ele lança (sem credencial nossa) |
| D13 | Canal de alerta no celular quando o PC/terminal estão mortos (o aviso nativo do EA vigia só cobre o terminal vivo) | Sentry `critical` por e-mail (já no stack) até ele escolher outro |
| D14 | Aceita que todo reinício do robô exige dois atos dele — "Conceder gestão" (depois do diagnóstico) e "Armar entradas" (depois da reconciliação) — e que entre a partida e a concessão o robô só lê e avisa (§5.2)? | sim na v1 (operação supervisionada) |
| D15 | Um host autorizado (o PC) na v1; troca de host só pelo procedimento supervisionado da §5.2 | sim |
| D16 | Aceita as duas limitações da v1: (a) no prazo de saída o robô **não** manda ordem a mercado — se o colchete não zerou, alerta e ele zera à mão (ou a zeragem compulsória da Rico); (b) um robô reiniciado sem a nossa API **só lê e avisa** até falar com ela | sim; são o preço de nunca criar exposição nova e de nunca mexer numa conta não verificada |

## 11. Fora de escopo

Ações/ETFs (regra escrita em §3.3, não implementada), mais de uma posição, mais de uma estratégia armada, vendido a
descoberto em ações, qualquer leitura da conta fora do processo do robô, qualquer automação de login.

## 12. Segunda opinião (Astra)

Diálogo `robo-b3-mt5`, **6 rodadas, DECISÃO CONJUNTA na rodada 6** (17/10/2026); transcrição em
`.claude/state/dialogue-robo-b3-mt5.md`, síntese em [[Dialogos/robo-b3-mt5]]
(`obsidian/06-DECISIONS/Dialogos/robo-b3-mt5.md`). O que mudou por causa dela está marcado `[Astra Rn]` no texto.

| Rodada | Achados | O que mudou |
|---|---|---|
| 1 | 10 (F1–F10), três CRITICAL: saídas concorrentes Python × EA que invertem a posição; EA agindo noutra conta; dois executores enviando a mesma intenção | risco do pior preço admissível; contrato da perda do pregão; sizing com margem livre e `WARNING`; três relógios; claim atômico; herança do *netting* corrigida; ordem limitada com ciclo completo |
| 2 | F1, F7, F8, F9 ainda abertos | EA deixa de mandar ordens (só avisa o celular); atribuição pela cadeia de negócios da corretora |
| 3 | retirar o stop para fechar deixa posição sem stop por tempo indefinido; repetir fechamento duplica; K2 não durável; mutação offline; dois Windows | saída pelo **aperto do colchete** no servidor; armamento por instância; lease para toda mutação |
| 4 | o fechamento direto de prazo ainda disputa com o stop; SLTP em conta não verificada; "recolocar se ausente" não é condicional | **nenhuma ordem direcional de saída na v1**; nenhuma mutação sem identidade e autoridade |
| 5 | duas validades para o mesmo lease; ciclo K3 → lease → reconciliação | **um** objeto de autoridade com vencimento absoluto no fim do pregão, em três fases (leitura → gestão → entradas) |
| 6 | — | DECISÃO CONJUNTA; alinhamentos de redação aplicados |

Os achados que só ela levantou e que dependiam de fato externo foram conferidos na documentação oficial antes de
absorvidos (`order_calc_margin` ignora ordens e posições existentes; em *netting* a posição é identificada pelo
símbolo e `position` não torna a ordem só-redução). Divergência arquitetural restante: **nenhuma**. Limitações
declaradas, não garantias: o encerramento pode atrasar; instância nova sem API só observa; um remetente neutralizado
pode ter requisição em trânsito; o *fencing token* não é aplicado pela corretora; a rota humana disputa com o stop.

## 13. Fontes (lidas em 17/10/2026)

- MetaQuotes, pacote Python: https://www.mql5.com/en/docs/python_metatrader5 ("comunicação entre processos
  diretamente do terminal"); `order_send`: https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
  (`MqlTradeRequest` com `sl`, `tp`, `magic`, `comment`, `type_filling`, `deviation`); `initialize`:
  https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py (aceita `login`/`password` — não usaremos);
  `order_calc_margin`: https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py; `account_info`:
  https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py; `terminal_info`:
  https://www.mql5.com/en/docs/python_metatrader5/mt5terminalinfo_py (`connected`, `trade_allowed`,
  `tradeapi_disabled`, `ping_last`); `last_error`: https://www.mql5.com/en/docs/python_metatrader5/mt5lasterror_py
  (`RES_E_AUTO_TRADING_DISABLED`); `copy_ticks_from` (tempo em UTC):
  https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksfrom_py; modos de conta:
  https://www.mql5.com/en/docs/constants/environment_state/accountinformation (`ACCOUNT_TRADE_MODE_DEMO/REAL`,
  `ACCOUNT_MARGIN_MODE_EXCHANGE/RETAIL_NETTING`); ações de negociação:
  https://www.mql5.com/en/docs/constants/tradingconstants/enum_trade_request_actions (`TRADE_ACTION_SLTP`, `REMOVE`).
- PyPI `MetaTrader5` 5.0.6231, só rodas `win_amd64`: https://pypi.org/pypi/MetaTrader5/json
- Ajuda do MetaTrader 5 — conceitos (netting, herança de stop, stop disparado pelo último negócio, stop zerado na
  virada do dia em bolsa, trailing no terminal): https://www.metatrader5.com/en/terminal/help/trading/general_concept ;
  execução (stops "guardados e executados no servidor da corretora"):
  https://www.metatrader5.com/en/terminal/help/trading/performing_deals ; Linux via Wine:
  https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux ; hospedagem virtual:
  https://www.metatrader5.com/en/terminal/help/virtual_hosting
- B3, especificação do WIN (ponto R$ 0,20, tick 5 pontos, vencimento na quarta mais próxima do dia 15, meses pares):
  https://www.b3.com.br/en_us/products-and-services/trading/equities/mini-ibovespa-futures.htm
- B3, Ofício Circular 050/2026-VNC (grade nova a partir de 03/11/2026; WIN 09:00–18:25, ajuste 18:00–18:15; WDO
  09:00–18:30): https://www.b3.com.br/data/files/99/B7/82/67/8A631A103BBB511AAC094EA8/OC%20050-2026-VNC%20NOVOS%20HORARIOS%20DE%20NEGOCIACAO_PT.pdf
- B3, feriados (página com conteúdo de vários anos, leitura automatizada parcial):
  https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/calendario-de-negociacao/feriados/
  — o calendário do robô é dado cadastrado com fonte, não raspado.
- Rico: `https://www.rico.com.vc/` e subpáginas de custos, margem e MetaTrader devolveram **HTTP 403 (CDN Akamai da
  XP, "Acesso Bloqueado")** em 17/10/2026; não contornei. Margem de day trade, regra de robôs, zeragem compulsória e
  corretagem **não verificadas por mim** — vêm do plano irmão (trechos de busca) ou ficam com o Everton.
- Plano irmão `docs/plans/MERCADO-TRADICIONAL.md` §1.2–§1.6, §5, §12 (custos B3, RLP, H-038, capital).

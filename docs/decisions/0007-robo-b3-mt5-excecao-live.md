# 0007 — Abrir uma exceção à Fase 4 para o robô da B3 do Everton (MetaTrader 5, conta Rico, dinheiro real)

- **Status:** aceito. Autorizado pelo Everton em 2026-10-17, em conversa com a Sexta-feira, com a palavra literal **"autorizado"** (ver Contexto). Escopo, itens pendentes e data de revisão abaixo.
- **Data:** 2026-10-17
- **Contexto:**
  - A regra dura do projeto (`CLAUDE.md`) é "nada de trading real antes da Fase 4"; `LiveExecutionAdapter` levanta `LiveTradingDisabled`. Em 2026-10-17 o Everton pausou memes e cripto ([[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]]) e decidiu negociar o mercado tradicional (B3) com dinheiro real, na conta dele na Rico (grupo XP), pelo MetaTrader 5. Ele digita as credenciais no próprio terminal, põe o dinheiro e liga o robô.
  - A Sexta-feira pediu que ele escrevesse que autoriza "o robô da B3 com dinheiro real, exceção à Fase 4". A resposta dele, nas palavras dele: **"autorizado"**. A mensagem de um agente não é consentimento (regra do `CLAUDE.md`); este ADR registra a palavra do próprio Everton, e a mudança do `CLAUDE.md` decorre dela.
  - Números dele no mesmo dia: banca "acima de R$ 10.000" (uma mensagem anterior dizia R$ 1.000; ainda pendente, D2 do desenho); R$ 1.000 por operação (para futuros, traduzido como margem de day trade consumida, D3 pendente de confirmação); limite de perda diária de **R$ 9.000**. A Sexta-feira avisou uma vez que isso é cerca de 90 % da banca; ele manteve o valor. O desenho grava o valor dele (`docs/design/robo-b3-mt5.md` §3.2).
  - A Sexta-feira recomendou uma fase de papel antes do dinheiro real. Ele recusou: **"não quero papel"**.
  - O desenho do robô (`docs/design/robo-b3-mt5.md`, commit `35b174cd`, decisão conjunta Claude ⇄ Astra na rodada 6) exige este ADR como D1 antes de qualquer código que envie ordem real ser integrado.
- **Decisão:** o único trading com dinheiro real permitido antes da Fase 4 é o **robô da B3 do Everton**, no escopo abaixo; o resto do projeto segue sob a regra "sem live trading" e `LiveExecutionAdapter` não muda.

## Escopo da exceção

| Item | Valor |
|---|---|
| Conta | só a conta do Everton na Rico, registrada por ele como hash (número + servidor); outra conta conectada → o robô só lê (`account_mismatch`) |
| Instrumento | **WIN** (mini-índice) na v1; **WDO fora**; ações e ETFs fora (regra escrita no desenho §3.3, não implementada) |
| Contratos | máximo **1 contrato por posição** e **1 operação por dia** na primeira semana (proposta D5 do desenho). Se o Everton mudar, a mudança entra na seção "Alterações de escopo" abaixo, em linha datada, e não reescreve esta tabela |
| Perda por operação | teto de **R$ 250** (proposta D4 do desenho, **a confirmar** por ele) |
| Perda diária | R$ 9.000, valor dele (check `daily_loss`, desenho §3.1) |
| Pré-condição técnica | o robô só envia ordem em conta real **depois de duas sessões técnicas em conta DEMO**, em dias diferentes (uma depois de 03/11/2026, com a grade nova da B3), com **T1–T17 do desenho §6.2 todos verdes** |
| Host | **um** host autorizado na v1: o PC do Everton, com operação supervisionada. Troca de host só pelo procedimento supervisionado do desenho §5.2 |
| Quem arma | só o Everton, pelas três chaves K1 (`ENABLE_B3_LIVE_TRADING` no ambiente do PC), K2 (botão "Algo Trading" do terminal) e K3 ("Armar" no app, papel OWNER, confirmação reforçada) |
| Revisão | **2026-12-31**. Sem revisão registrada até lá, a exceção deixa de valer e o robô volta a ser inerte |

**Itens ainda abertos que não alteram o ADR, mas bloqueiam armar o robô:** D2 (banca), D3 (leitura de "R$ 1.000 por operação" como margem), D4 (teto de R$ 250), D6 (horário de `flatten_at` e da zeragem compulsória da Rico), D7 (RLP ativo e custos) e a política da Rico para robôs/EA (não lida; o site devolve 403 a acesso automatizado). Cada um é confirmado por ele e entra no registro de alterações quando mudar este escopo.

## O que continua obrigatório, qualquer que seja o portão

1. **Risk engine em toda entrada.** O caminho é AGENTE/estratégia → PROPOSTA → `hunter_risk_b3.evaluate` (puro, `checks[]` completos persistidos) → `pre_send_gate` → ordem. `unavailable` reprova.
2. **Saídas sempre permitidas** (stop, alvo, saída por tempo, zeragem, kill switch, fechamento manual).
3. **Stop em repouso na corretora:** toda entrada nasce com `sl` no servidor da corretora; nunca trailing de terminal. O stop é o último recurso, e o desenho declara que "no servidor da corretora" não é "na bolsa".
4. **Kill switch** de quatro estados, com o escopo mais restritivo vencendo.
5. **Auditoria** (`audit_logs`, append-only) de armar/desarmar, mudança de limite, kill switch, decisão de risco, ordem, fill e divergência de reconciliação.
6. **Nenhum agente envia ordem nem toca credencial.** Só o processo do robô, armado pelo Everton, chama `order_send`. O robô chama `mt5.initialize()` sem `login`/`password`; um teste falha se qualquer chamada os passar. O comando de agente só pode **bloquear entradas**.
7. **Nenhum `ENABLE_*` em arquivo versionado.** `ENABLE_B3_LIVE_TRADING` só existe no ambiente do PC dele, digitado por ele; agentes não escrevem `.env*`.
8. **Dinheiro em `Decimal`, tempo em UTC;** a conversão para `float` do pacote `MetaTrader5` acontece só na fronteira do adaptador, com prova de ida e volta.

## O portão de evidência (Portão B) fica dispensado, por escolha dele

O contrato do meme (`docs/RISK_ENGINE_MEME.md`) e o desenho do robô trabalham com três portões: A (engenharia), B (evidência: um `CONFIRMA` antes do dinheiro real) e C (as chaves do dono). Aqui o **Portão B está dispensado por decisão do Everton**, contra a recomendação da Sexta-feira, que era papel e depois evidência. Registro do que ele decidiu e do que isso significa:

- Ele autorizou o robô com dinheiro real e recusou a fase de papel. Não há `CONFIRMA` da H-038 nem de nenhuma regra de WIN que o robô execute. A H-038 está só pré-registrada (congelada em 2026-10-17); o poder declarado dela pede cerca de **785 pregões independentes (~3 anos)** para rejeitar zero com 80 % de poder se o efeito verdadeiro for 2,5 bp (`docs/plans/MERCADO-TRADICIONAL.md` §1).
- O contexto, que ele conhece: [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] (FGV, Chague, De-Losso e Giovannetti, resumo): dentre as pessoas físicas que começaram a fazer day trade no WIN em 2013–2015 e persistiram ≥ 300 dias, **97 % perderam dinheiro** e 0,4 % ganharam mais que um caixa de banco, sem evidência de aprendizado. O estudo mede pessoas, não regras sistemáticas; também não dá motivo para esperar que a regra ganhe. E [[KB-0149-o-que-a-mesa-real-ensinou]]: nenhuma hipótese de cripto ou meme testada até 17/10 teve `CONFIRMA`, e 72 % do prejuízo da mesa real foi custo.
- A dispensa **não** vira veredito: o resultado do robô é medido como a série de execução real da H-038 (custo, deslizamento, diferença entre o modelo e o real) e **não conta como `CONFIRMA`**. Resultado de poucas semanas não diz nada sobre vantagem.
- Esta dispensa vale só para este escopo. Ampliar instrumentos, contratos ou hosts não herda a dispensa sem uma linha datada dele.

## Exceção ao "sem estado local": dois arquivos do lado do PC

A regra "sem estado local" (`CLAUDE.md`) tem duas exceções declaradas para este robô, ambas listadas no desenho §2.1 e §3.8. Nenhuma é estado de negócio nem decide nada:

| Arquivo | Para quê | Limites |
|---|---|---|
| `MQL5\Files\hunter_hb` (batimento) | sinal de vida que o EA vigia (`HunterVigia.mq5`, sem estratégia e **sem ordens**) lê para avisar o celular do Everton | só instante e conta; o EA nunca envia ordem |
| `%LOCALAPPDATA%\HunterB3\outage-buffer.jsonl` (buffer de indisponibilidade) | guarda eventos que a API recusou ou não alcançou, para reenvio idempotente | append-only, `fsync` por linha, hash encadeado; **nunca é lido para decidir**; enquanto não estiver vazio, nenhuma entrada (check 21); falha de disco nunca atrasa uma saída |

Postgres continua sendo o registro; a corretora é a verdade do dinheiro (posição, ordens, negócios).

- **Alternativas consideradas:**
  - **Paper primeiro (rejeitada por ele).** Era a recomendação da Sexta-feira: medir o custo e o pipeline sem risco antes do dinheiro real. O Everton recusou ("não quero papel"). Compensações adotadas: duas sessões técnicas em conta DEMO (fiação e dedo-gordo, não teste de estratégia), 1 contrato e 1 operação por dia na primeira semana, teto de perda por operação, stop no servidor e revisão em 2026-12-31.
  - **Esperar um `CONFIRMA` da H-038 (rejeitada por ele).** Pediria cerca de 785 pregões independentes. Inviabiliza o objetivo dele de operar agora.
  - **Painel manual de sinais sem robô** (plano irmão, segunda 19/10): continua existindo e usa o mesmo módulo puro da estratégia; não substitui o robô por escolha dele.
  - **Estender o `LiveExecutionAdapter` do núcleo (rejeitada).** A linha cripto continua sem live; o robô B3 tem adaptador, serviço, contrato de risco (`hunter_risk_b3`) e flag próprios, para que a exceção não vaze para o resto do produto.
- **Consequências:**
  - O projeto passa a ter um caminho de ordens reais, restrito ao escopo acima. Exige revisão obrigatória do `risk-engine-guardian`, do `security-reviewer` (token do robô, RBAC, step-up do Clerk) e do `database-architect` (tabelas `b3_*`, RLS), mais a segunda opinião da Astra, conforme desenho §9.
  - Mais difícil: toda mudança de escopo (instrumento, contratos, host, tetos) passa por linha datada do Everton; este ADR não é editado, apenas acrescido na seção abaixo, e uma decisão contrária vira um ADR novo que o substitui.
  - Riscos aceitos e escritos no desenho: com o Python morto só o servidor (stop) ou o Everton zera; "stop no servidor da corretora" não é "stop na bolsa"; a perda real pode passar do risco modelado (gap, leilão, rejeição do stop); R$ 9.000 por dia é cerca de 90 % da banca informada.
  - **Revisar em 2026-12-31:** com os relatórios diários, o custo real contra o modelado e a série de execução da H-038, decidir se a exceção continua, encolhe ou acaba. Antes disso, qualquer incidente com posição real reabre a revisão.
- **Referências:** `docs/design/robo-b3-mt5.md` (commit `35b174cd`), `docs/plans/MERCADO-TRADICIONAL.md`, `docs/RISK_ENGINE_MEME.md`, [[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]], [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]], [[KB-0149-o-que-a-mesa-real-ensinou]], `CLAUDE.md` (regra dura de live trading).

## Alterações de escopo

(Linhas datadas, só acrescentadas. Vazio em 2026-10-17.)

### 2026-10-17 — alinhamento com o contrato R0a

Esclarecimentos de precisão a partir do contrato congelado `docs/RISK_ENGINE_B3.md` (commit `5e71f345`, §13). Não mudam o escopo autorizado pelo Everton; o texto acima fica como está e estas linhas o precisam.

- **(a) "Saídas sempre permitidas".** Significa que o motor de risco nunca bloqueia uma saída. Mas uma instância sem autoridade verificada (partida sem API, conta trocada, host não autorizado, autoridade vencida) ou uma conta real sem K1 **não envia nada, nem saída**: a posição fica com o `sl` no servidor e as rotas manuais R3/R4 do Everton (contrato §13 item 3; limitação D16b do desenho). É o preço de nunca mexer numa conta não verificada.
- **(b) Conteúdo do `hunter_hb`.** O arquivo de batimento carrega `v`, `ts`, `seq`, `inst`, a conta como sha256 e `end`; não é só o instante e a conta, como a tabela de exceções acima resume. O EA precisa de `inst` e `seq` para detectar um batimento velho. Continua sendo sinal de vida, nunca estado de negócio, e o EA continua sem enviar ordem.
- **(c) API e disco falhando juntos.** O robô para de enviar SLTP e mantém o último `sl` confirmado no servidor (contrato §13 item 8). Isso **substitui** a regra 5 do desenho §3.8 ("falha de disco nunca aborta nem atrasa uma saída"), escrita quando a saída ainda podia ser ordem direcional. Falha só de disco, ou só da API, não atrasa nada além do orçamento de 500 ms.
- **D17, pendente com o Everton (contrato §9, §4.4):** quando o piso do stop não pode ser colocado (posição de um pregão para o outro que abriu além do stop, ou stop rompido com a posição sem `sl`), o padrão é o robô **só alertar** (`floor_unplaceable`, rota manual); a alternativa é tentar sair por um colchete mais largo que o stop aprovado, exceção de risco que só ele decide. Até ele responder vale o padrão.

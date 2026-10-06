---
tags: [revisao-astra, meme, carteiras, pumpswap, pumpfun, swap-record, completude-da-curva, mints-da-pool, sonda, h-030]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-05
by: astra
tarefa: onda 1b do H-030 — o SwapRecord passa a dizer se a curva estava completa no evento e quais são as mints da pool; conferência da sonda da onda 0
veredito: DONE_WITH_CONCERNS na rodada 1; na revisão de código a Astra pediu mudanças (2 HIGH) e o code-reviewer aprovou com nits, tudo fechado (ver a seção final); 2 must-fix reproduzidos por ela (CompleteEvent órfão sem lacuna; sonda ainda binando quote não verificada), ambos aceitos e consertados com teste que falhou antes; 3 nice-to-have, 2 aplicados e 1 por documentação; sem look-ahead e sem quebra estrutural de SwapLike
---

# Revisão da Astra: onda 1b do H-030 (completude da curva, mints da pool, sonda)

Fecha o que estava em [[Open Bugs]] desde a rodada 2 de [[wallets-1a]] e o achado de [[wallets-1c-pricing]]: a ponte `SwapRecord → Fill` só podia recusar por nome porque o registro não trazia a flag `complete` da curva nem as mints das pernas de pool.
Conhecimento medido: [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]] (seção "Onda 1b") e erratum em [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]].
Código: `hunter_exchanges/pumpfun/{curve_completion,completion_reconcile,swap_record,program_logs}.py`, `pumpswap/pool_legs.py`; sonda `infra/scripts/wallet_tape_probe_{core,stats,snapshot}.py`. Bruto: `.claude/state/astra-review-wallets-1b-record.md`. Página do módulo: [[Exchange Adapters]].

## O que foi levado a ela

Cinco perguntas: (a) look-ahead ou identidade na regra tri-estado da curva; (b) atribuição evento → instrução por `(pool, user, ata_base, ata_quote)`; (c) prova das mints e a recusa de instrução desconhecida; (d) enquadramento do erratum da sonda; (e) o que a ponte do motor precisa dos campos novos.

## Concorda

- **(a)** Sem look-ahead intrínseco: corroborar com outro evento da **mesma** transação não consulta nada posterior. Duas compras decodificadas do mesmo mint são associadas à última anterior à conclusão; truncamento antes do `CompleteEvent` dá `unknown` com lacuna.
- **(b)** Nenhuma troca entre pools, usuários ou roteadores no caminho válido; o casamento resolve o par de mints, sem pretender identificar cada execução.
- **(c)** Instrução conhecida mais confronto com os rótulos de mint dos saldos é base adequada; recusar layout desconhecido e contar é correto (resolver só pelos saldos seria outra evidência, a provar à parte).
- **(d)** A run 3 não é recalculável sem o bruto; a amostra nova é outra medição e não substitui o número publicado.

## Must-fix

| # | Achado (cenário reproduzido por ela) | Decisão |
|---|---|---|
| 1 | **`CompleteEvent` sem `TradeEvent` desaparecia como evento não swap, sem lacuna.** Tirando só a linha do trade da conclusão real: `swaps 0, gap False`. E a associação procurava o último swap **aceito**, não o último `TradeEvent`: com duas compras do mesmo mint e a segunda indecodificável, a primeira mudava indevidamente de `not_complete` para `unknown` | **Aceito.** `orphan_complete_events` (conclusão sem trade que pudesse ser dela) é lacuna; todo trade de pump recusado ou que nem é base64 mantém o lugar na ordem (`refused_trades`), e o `CompleteEvent` que o fecha não mexe nos aceitos. Lógica movida para `completion_reconcile.py` (o `program_logs.py` passaria de 350 linhas). Testes novos: órfão, trade recusado, linha não base64 |
| 2 | **A flag da sonda não impedia a estatística errada.** A venda `551G…` (WSOL na base) saía com `quote_unverified=True` mas `ProbeStats` a punha em `size_bins_sol` | **Aceito.** `ProbeStats` não bina a venda não verificada e a conta em `size_unverified_quote` (no snapshot). Não recupera o tamanho em SOL das pools: só impede a afirmação falsa. Teste atualizado |

**Sobre (d), a parte que ela achou faltando:** o erratum do KB-0183 ainda não estava escrito quando ela leu. Está (seção "Erratum" do KB-0183), com os números antigos preservados e os da amostra nova rotulados como outra medição.

## Nice-to-have

- **Leitura provisória da fábrica.** `swap_record_from_event` sozinha devolve `complete` só pelas reservas. **Aceito por documentação**: a docstring diz "provisório" e aponta `read_program_logs` / `read_transaction_logs`. O único chamador é o leitor.
- **Duas pools e dois usuários na mesma transação; conhecido + V2 com as mesmas contas.** **Não aplicado**: não há fixture real com duas pools de usuários distintos num mesmo `getTransaction`, e eu não fabriquei uma que provasse mais do que o casamento por quatro campos já prova. Registrado aqui como lacuna de teste.
- **Conferir os cofres de todos os casamentos, não só do primeiro.** **Aceito** (teste que falhou antes: gêmeo da instrução com o cofre de quote trocado pelo de base vira conflito).

## O que ela faria diferente

Separar "evento observado", "evento decodificado" e "swap aceito" na reconciliação: uma recusa não apaga a posição que impede associar o `CompleteEvent` ao trade anterior. **Feito** (é o conserto do must-fix 1).

## Integração com a ponte (aviso, não tocado)

Os campos novos não quebram `SwapLike`, mas a ponte **não os consome sozinha**: o chamador ainda passa `curve_complete=record.curve_complete` e `PoolMints(pool, record.base_mint, record.quote_mint)`. Ela confirmou com fixtures: curva concluída sem o argumento → `curve_completion_unknown`; pool WSOL quote sem `PoolMints` → `pool_quote_unresolved`; WSOL base com `PoolMints` → `sol_is_base`. Cada recusa da ponte é buraco de cobertura da fita, mesmo que `pool_mints_*` não seja perda de logs no adaptador. Pendência do dono do motor e do coletor (onda 2); registrada em [[Exchange Adapters]] e [[Open Bugs]].

## Divergências

Nenhuma de fundo. Um ponto de formulação: ela pediu os testes de "duas pools / dois usuários"; não os fiz por não ter fixture real (ver acima).

## Mutação

21 mutantes manuais, todos mortos: 15 na primeira volta (regra de venda lendo 0, escolha do último trade do mint, contradição desligada, limiar do zero, tamanho do `CompleteEvent`, ordem base/quote, conferência dos rótulos, conflito de pares, `quote_is_sol`, cofre da base, leitura do `CompleteEvent`, completude do registro, reservas, `wsol_is_base`, `curve_complete`) e 6 nas guardas da revisão (órfão, lugar do trade recusado e da linha não base64, `gap` do órfão, atribuição de mint desconhecida, cofres de todos os casamentos). Um sétimo sobrevivente era **equivalente** (a condição era redundante) e foi removido do código. Script fora do repositório.

## Revisão de código (05/10, noite): code-reviewer APPROVE_WITH_NITS, Astra REQUEST_CHANGES com 2 HIGH, tudo fechado

O `code-reviewer` aprovou com nits; a Astra, no mesmo diff, pediu mudanças com dois achados que classificou como HIGH (bruto: `.claude/state/astra-review-review-wallets-1b-record.md`). Reproduções dela, em memória, com as fixtures.

| # | Achado dela (severidade dela) / do reviewer | Cenário reproduzido | Conserto |
|---|---|---|---|
| 1 | Perda do trade que completa a curva com `gap=False` (HIGH dela; MEDIUM do reviewer) | logs da compra anterior (não completa) + `CompleteEvent`, sem o `TradeEvent` que drena: o primeiro trade vira `unknown`, `orphan_complete_events=0`, `gap=False` | Um `CompleteEvent` cujo trade fechador ainda tem tokens (`not_complete`) também conta em `orphan_complete_events`, que é lacuna. O trade segue `unknown`. Teste sintético rotulado |
| 2 | Instrução desconhecida herda a atribuição de uma conhecida (HIGH dela; LOW do reviewer: mints certas por construção, um par por pool) | duas vendas da mesma pool e usuário, a segunda reetiquetada com o discriminador de `SellV2`: os dois eventos recebem mints, `unresolved=0`, sem sinal | Decisão do orquestrador: contar à parte. `pool_mints_via_sibling` conta o evento resolvido que divide pool e usuário com uma instrução PumpSwap não entendida (conservador: pode pegar um `Deposit` da mesma pool e usuário). Não é lacuna. Ligar o evento à invocação que o emitiu fica em [[Open Bugs]] (item 3) |

**Divergência de severidade, escrita:** Astra HIGH contra reviewer MEDIUM (1) e LOW (2). O efeito é latente (nada liga), mas os dois foram fechados na mesma mudança: o 1 porque podia declarar cobertura íntegra com um swap faltando, o 2 porque o contrato era "instrução desconhecida fica sem mints" e a afirmação precisava ser qualificada ([[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]] não diz mais "nunca adivinhadas" sem a ressalva). A Astra preferia ligar o evento à invocação (identidade da invocação até a resolução); não feito, por precisar do layout V2.

**Também aceitos:** redação das provas (`2 conclusões guardadas + 1 predecessora não completa; mais 3 vistas numa varredura não guardada`; as contagens de 498 trades, 2 773 swaps de pool e dos mutantes são avulsas, não reexecutáveis); `test_program_logs.py` voltou a 350 linhas; o `import` de dentro do teste da sonda foi para o topo. **Nice-to-have dela, não feito:** normalizar `encoding=jsonParsed` (o cliente pede `json`; a reprodução dela deu `unresolved`, sem atribuição errada) — documentado em [[Exchange Adapters]].

**Mutação desta rodada:** 4 mutantes novos mortos (o `not_complete` do órfão, a contagem `via_sibling`, o critério de usuário igual e a lista de instruções não entendidas; o do usuário sobreviveu até ganhar o teste do "outro usuário"). Total de 25 mutantes manuais, script avulso fora do repositório.

## Relacionado

[[wallets-1a]] · [[wallets-1c-pricing]] · [[wallets-engine]] · [[wallet-tape-probe]] · [[carteiras-lucro-design]] · [[Resolved Bugs]]

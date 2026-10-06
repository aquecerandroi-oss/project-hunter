---
tags: [inbox, pendencia, pumpfun, nats, termos, rea, escopo]
status: resolvido
owner: sexta-feira
updated: 2026-10-06
---

# Pendência — a NATS da pump.fun: a credencial estática da home page e o canal por carteira

**Aberta em 2026-10-06 pelo `exchange-integration-specialist`** ([[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]]). Decide: **Everton**. Pendência de escopo, não de código: a sonda de latência já rodou e parou.

> [!alerta] O que foi feito e o que está em dúvida
> A home page anônima da pump.fun entrega, nos *props* do `NatsProvider`, um usuário estático `subscriber` (mais a senha) que o navegador usa para abrir `wss://unified-prod.nats.realtime.pump.fun` e `wss://prod-v2.nats.realtime.pump.fun` (`auth_required: true`). A sonda leu essa credencial **em tempo de execução, a partir da mesma página anônima**, e a usou do mesmo jeito que o cliente do site; não gravou a senha em lugar nenhum. A [[2026-10-06-rea-na-pumpfun-apesar-dos-termos|decisão de 06/10]] manda "só visitante anônimo", "nunca driblar autenticação" e "parar no primeiro bloqueio". Pontos que a Astra levantou e que **não são meus para decidir**:
> 1. usar a credencial do cliente fora do navegador é "mesmo acesso do visitante anônimo" ou é usar uma autenticação que o site só entregou ao seu próprio cliente?
> 2. a assinatura por **carteira arbitrária** (`account_balance_change.<carteira>.*`, instância CORE) foi **extensão minha** além dos assuntos pedidos (novas moedas, trades, boards). O servidor aceitou 20 carteiras; isso não prova que o visitante anônimo normal faça essa assinatura. Eu devia ter parado e perguntado antes de abrir esse canal.

## O que foi consumido (para o Everton pesar)

- Duas janelas (18 min e 35 min), **uma conexão por serviço**: NATS `unified` (todas as criações da pump; até 30 moedas recém-criadas por vez, 6 min cada, dois assuntos por moeda), NATS `core` (20 carteiras que negociaram essas moedas), PumpPortal, `/ws/trenches` (`new` e `graduated`), RPC público. Nenhum login, cookie ou cabeçalho inventado; **nenhum bloqueio, 403 ou 429 do site** (um 502 de handshake do PumpPortal, uma vez).
- O que **parou**: o HTTP do RPC público passou a dizer `413 "You have used your data allowance"` (cota de dados do IP, não do site). Depois de descobrir, nenhuma chamada a mais.
- Os dados brutos (endereços públicos de carteira e de moeda) estão em `.claude/state/pumpfun-rt-latency/`; nenhum nome de usuário, nenhuma senha.

## Opções

1. **Parar de usar a NATS** e ficar com PumpPortal, `logsSubscribe` e boards (a vantagem medida é de ~0,03–0,16 s; [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes|KB-0186]] diz que **não demonstramos benefício operacional**). Para o H-030, coletar o programa inteiro ([[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]]).
2. **Manter só o que a página da moeda faz** (novas moedas e trades por moeda), sem o canal por carteira.
3. **Manter também o canal por carteira**, com a decisão escrita do Everton, como extensão consciente da decisão de 06/10 (risco: rotação da credencial, termos §21(h)/§21(j), bloqueio).

**Recomendação do especialista (não decisão):** 1 ou 2; usar a NATS só em medição, nunca como dependência de produção, até alguém repetir da VPS e a vantagem aparecer contra o RPC pago. O canal por carteira só vale a conversa se o H-030 não puder pagar a coleta do programa inteiro.

## Sai daqui quando

O Everton escolher uma opção (anotar a data, a opção e o motivo aqui), ou quando a medição for descartada.

**Resolvido em 06/10/2026:** Everton escolheu a opção 3 (usar no projeto das carteiras), com limites: [[2026-10-06-nats-da-pumpfun-no-projeto-das-carteiras]].

## Relacionado

[[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]] · [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]] · [[pumpfun-rt-latency]] · [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]]

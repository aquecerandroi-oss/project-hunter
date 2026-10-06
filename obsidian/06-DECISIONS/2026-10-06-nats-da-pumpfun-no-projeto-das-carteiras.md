---
tags: [decisao, pumpfun, nats, carteiras, h-030, termos]
status: decidida
owner: sexta-feira
updated: 2026-10-06
decided_on: 2026-10-06
by: Everton
---

# A NATS da pump.fun entra no projeto das carteiras (06/10/2026)

**Contexto:** a sonda de latência ([[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]], revisão [[pumpfun-rt-latency]]) usou a credencial estática `subscriber`, que a home anônima entrega a todo visitante nos props do `NatsProvider`. Usou também o canal por carteira `account_balance_change.<carteira>.*`, na instância CORE, que pegou 100 % das pernas esperadas de 20 carteiras. A pendência foi aberta em [[2026-10-06-nats-da-pumpfun-escopo-da-credencial]].

**Opções apresentadas:**
1. só para medição (recomendada: acompanhar carteiras pela blockchain, sem depender de senha não documentada);
2. usar no projeto das carteiras;
3. parar de vez.

**Decisão do Everton: usar no projeto das carteiras.**

## Como entra (limites da Sexta-feira)
- **Papel:** acompanhar **carteiras escolhidas** (as seguidas e os controles) na fase de seguir/papel do H-030. Não serve como fonte do ranking: o ranking continua vindo da fita do programa inteiro, porque precisa de todas as carteiras e do ponto no tempo.
- **Credencial:** lida em tempo de execução da página pública, nunca gravada em arquivo, log, nota ou `.env`. Nunca `/nats/token`, nunca login.
- **Fallback obrigatório:** se a credencial trocar ou a NATS recusar, o coletor marca lacuna e cai para a blockchain (`logsSubscribe` com `mentions` da carteira no RPC que já usamos). Nunca para em silêncio.
- **Fronteira de lacuna:** perder evento da NATS é lacuna explícita, contada (regra da onda 1a). O que a NATS entrega é cruzado com a cadeia pela assinatura antes de virar fill.
- **Volume:** só as carteiras do experimento, no máximo o que o pré-registro definir. Sem varrer carteiras arbitrárias em massa.
- **Dinheiro real:** se um dia isto alimentar entradas, passa pelo Risk Engine e pela revisão do risk-engine-guardian, e o fallback on-chain precisa estar provado antes.
- **Termos:** valem os mesmos riscos aceitos em [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]] (§21(h)/(j)): bloqueio ou troca da senha.

## Relacionado
[[EXP-M15-carteiras-vencedoras]] · [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]] · [[2026-10-06-nats-da-pumpfun-escopo-da-credencial]] · [[REA]]

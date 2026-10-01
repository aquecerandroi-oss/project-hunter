---
tags: [revisao-astra, cripto, tendencia-diaria, pre-registro, h-027]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: sexta-feira
decided_on: 2026-10-01
by: astra
tarefa: R86 — pré-registro da H-027 (candidata C1, tendência diária como estado dos sinais de continuação do Lab)
veredito: aprovaria como análise retrospectiva pré-especificada depois de 5 must-fix; não como validação em coorte futura da C1; os 5 aceitos numa emenda datada (03:02Z) antes de qualquer desfecho
---

# Revisão da Astra — pré-registro da H-027 (R86)

**Pedido:** rever o bloco congelado às 02:56Z (`.claude/state/r86/prereg_frozen.md`, cópia no fim da
[[Fila de Hipoteses]]) e o código cego (`data86.py`, `stats86.py`, 18 testes), com seis perguntas: população e unidade,
forma do teste incremental conjunto, bootstrap por dia com ~23 dias, antecipação, ordem das cláusulas e a leitura sobre
"coorte futura". Nenhum desfecho tinha sido lido. Ela reproduziu às cegas as 874 unidades e o md5 do export, e rodou
sondas sintéticas.

**Concordou com:** horizonte de 20 dias como variável nova (não rebatiza a pista `_low`); OLS conjunto como a forma
simples e correta do "incremental conjunto"; análise por estratégia; unidade por barra (média das versões = mistura
histórica, não versão executável); família Holm fixa com p = 1 para a estratégia sem dado; nível positivo obrigatório;
nenhuma antecipação calendárica (D = data(obs) − 1 certo, inclusive à meia-noite). Ressalva aceita: `received_at` é
proxy de persistência — a conclusão é sobre reconstrução retrospectiva, não sobre o que o scanner tinha em memória.

**Cinco must-fix, todos aceitos na emenda das 03:02Z (texto original preservado):**

1. **População congelada no código** — o SQL e o carregador não aplicavam a janela de emissão nem a exchange.
   Cenário: rodar de novo amanhã incorpora sinais novos. → `eligible()` com janela [06/09; 01/10) e Binance, lista de
   IDs gravada com sha256 antes dos desfechos, junção conferida.
2. **Falha fechada** — `fit()` aceitava matriz singular, o bootstrap quebrava sem réplicas válidas e uma metade `NaN`
   passava como positiva (os três reproduzidos por ela com dado sintético). → finitude/MAD/posto checados, > 1 % de
   réplicas inválidas = LIMITE (instrumento), que bloqueia também o REFUTA; metades conferidas uma a uma.
3. **Bootstrap só por dia é fraco** — reamostrar dias como independentes estreita o IC se um mercado carrega resíduo
   por vários dias. → bootstrap de mercado ao lado; Holm com o maior p; CONFIRMA e REFUTA exigem os dois.
4. **Regra global de REFUTA** permitia "refutada" com uma estratégia refutando e a outra sem dado. → só as duas
   refutando; o resto NÃO CONFIRMA, rótulo de cada uma publicado.
5. **Natureza retrospectiva no título e no status**, não só na ressalva: um CONFIRMA aqui seria "critérios satisfeitos
   nesta análise retrospectiva" e deixaria o bloco em curso até a coorte futura.

**Nice-to-have aceitos:** diagnósticos (condição, dispersão residual da razão, concentração, sem cada mercado/dia) e
IC do nível do grupo favorável, publicados sem decidir. Esclarecimento aceito: na `volume_anomaly` a decisão é de 5 min
e o ATR do envelope é de 15 min. Nada rejeitado.

**Bruto:** `.claude/state/astra-review-H-027-prereg.md`
**Relacionado:** [[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab|KB-0170]] · [[H-027-resultado]] ·
[[Fila de Hipoteses]] · [[Proximas Hipoteses]]

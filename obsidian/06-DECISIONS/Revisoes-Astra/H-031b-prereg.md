---
tags: [revisao-astra, meme, concentracao, maior-comprador, creator-dump, gemeo, pre-registro, h-031b]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: H-031b — pré-registro do gêmeo de papel sem `creator_dump` (`absorb_semdump_v0/1`, EXP-M27)
veredito: "DONE_WITH_CONCERNS: I = D_semdump − D_orig correta e CONFIRMA/REFUTA alcançáveis; 6 must-fix aceitos na emenda 1 (02:33Z) antes de existir o conjunto"
---

# Revisão da Astra — pré-registro da H-031b

**Pedido:** rever o bloco congelado às 02:25:23Z (`.claude/state/h031b/prereg_frozen.md`, cópia na
[[Fila de Hipoteses]], bloco H-031b) e cinco perguntas: coerência de I, IC 98,75 %, p, S1, metades e planalto; tetos
idênticos × alargados no gêmeo; pinos do rastreador e pedigree da mesa; a pré-condição de latência/cobertura/fidelidade;
gravar `exit_on_creator_dump` sempre na aposta. Transcrição: `.claude/state/astra-review-H-031b-prereg.md`. Nenhum dado
da coorte existia (o conjunto nem existe).

**Concordou com:** I = D_semdump − D_orig, desde que os quatro termos usem os mesmos pares; dispensar "lucrativo em
nível" numa hipótese de mecanismo, publicando os quatro níveis; REFUTA = "exclui +0,05 nesta população", nunca "não há
absorção"; copiar o `params` vivo como na `0065`; coorte futura, leitura única, nada do R88; gravar sempre o booleano,
com ausência histórica = `True`.

**Seis must-fix, todos aceitos na emenda 1 (texto original preservado):**

1. **População identificada.** Tetos iguais não dão admissões iguais (`paper_fill` recusa por perda diária, posições,
   exposição por mint, saldo). Cenário: três originais saem por `creator_dump`, os gêmeos seguem abertos e as próximas
   oportunidades entram só no original — o subconjunto pareado perde justamente episódios do regime. Alargar os tetos
   não garante superconjunto. → âncora = primeira aposta do original por mint, par só se o gêmeo também apostou,
   nunca substituída; I/CONFIRMA/REFUTA escritos para "a primeira aposta do mint admitida pelas duas políticas".
   **Alternativa dela registrada para o Everton (não aprovada):** contrafactual ancorado no preenchimento do original,
   duas trajetórias de saída sobre a mesma entrada, sem carteira própria — exigiria mudar o motor de papel.
2. **Pinos e pedigree.** Excluir por id é necessário, não suficiente: a dobra do minuto grava
   `meme_features_1m.creator_sold` sem identidade de conjunto. → exclusão por id implementada; resíduo declarado
   (o gêmeo só fica aberto além do original depois do `creator_dump` dele ou em apostas só do gêmeo) e a frase "não muda
   recusas do `operator/5`" trocada por "interferência limitada a esses casos". **Divergência registrada:** o cenário
   dela "original fecha por trailing, gêmeo continua" não acontece por construção — o gêmeo só difere na saída
   `creator_dump`, então qualquer outra saída dispara nos dois na mesma foto.
3. **Cobertura da vigia.** `creator_balance_reason IS NULL` não prova leitura válida (a vigia pode estar fora do ar sem
   marcar a aposta). → taxa de detecção contra as vendas do criador em `meme_trades` na posse do original, piso de 50 %
   (escolha declarada); latência só descritiva, com carimbos sem venda e vendas antes da primeira leitura contados.
4. **Fidelidade.** "< 10 % dos pares" deixava 9 % de Δ espúrio fabricar ~+0,054. → par fiel decidido pela entrada
   (params efetivos, foto de entrada, `tokens`, `sol_spent` exatos); I_fiel com Δ zerado nos pares sem `creator_dump`;
   CONFIRMA/REFUTA têm de valer nos dois; calculado na leitura única (usa `exit`), não "antes de olhar Δ".
5. **Inferência e poder.** ~99 %/~56 % era poder de rejeitar I ≤ 0, não de CONFIRMA: com I verdadeiro = +0,05 a
   cláusula Î ≥ 0,05 passa ≈ 50 %. → corrigido; IC **básico** decisório coerente com o p centrado; 20 000 réplicas;
   bootstrap de dia definido; IC finito e ≤ 1 % de réplicas inválidas também para CONFIRMA; os oito membros da família
   k = 8 do Defensor não estão enumerados (escrito como desconhecido).
6. **Parada e maturação.** Âncora, desempate, contagem de unidades, fechamento de admissões e espera fixa de 1 h antes
   da leitura; mudança de parâmetro fecha admissões sem descartar pendentes; deploys do motor listados e I por segmento
   (descritivo).

**Nice-to-have aceitos:** S1 declarado como cenário (não limite); metades e planalto no primário e em S1; blocos pelo
dia de São Paulo como descritivo.

**Onde isto vive:** [[Fila de Hipoteses]] (H-031b, emenda 1) · [[EXP-M27-gemeo-sem-creator-dump]] ·
[[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]] · revisão do diff: [[H-031b-diff]] ·
[[Revisoes-Astra/Index|índice das revisões]]

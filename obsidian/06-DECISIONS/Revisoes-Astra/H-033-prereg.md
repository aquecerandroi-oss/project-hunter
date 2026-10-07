---
tags: [revisao-astra, cripto, open-interest, pre-registro, h-033]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: sexta-feira
decided_on: 2026-10-07
by: astra
tarefa: R90 — pré-registro da H-033 (OI em nível relativo à própria semana como estado dos sinais de continuação do Lab)
veredito: emendaria antes de abrir os desfechos — desenho razoável para associação retrospectiva, com brechas na prova temporal e na falha fechada; os 5 must-fix aceitos numa emenda datada (05:15:31Z) antes de qualquer desfecho
---

# Revisão da Astra — pré-registro da H-033 (R90)

**Linha do tempo (UTC, 07/10/2026):** bloco acrescentado à [[Fila de Hipoteses]] às 04:51:02Z (o texto dizia 04:52Z;
errata no item 0 da emenda) · revisão gravada às 04:56:17Z · emenda às 05:15:31Z · lista elegível congelada às 05:18:27Z
(sha256 `e597cabf…`) · desfechos lidos às 05:19:52Z. Fonte bruta: `.claude/state/astra-review-H-033-prereg.md`.

**Pedido:** antecipação possível na variável, nas covariáveis ou na guarda; se OI em contratos e mediana de 7 d medem
"lotação" ou tendência disfarçada; coerência das regras de decisão; efeito da sobreposição com o R86.

## Must-fix (todos aceitos na emenda, antes dos desfechos)

1. **A folga de 15 min é suposição, não prova.** O coletor fixa o bucket no início da rodada e lê os mercados em
   sequência, sem teto de duração; os 325 s são o máximo observado no outbox, não um limite histórico. Cenário: bucket
   11:45, rodada atrasada, leitura real às 12:01, sinal às 12:00 — sem outbox o instrumento aceitaria. → Emenda item 1:
   sensibilidades de 30 e 60 min (populações completas e interseção), subpopulações com proveniência provada, CONFIRMA
   exige β > 0 nas duas folgas, e a frase "condicionado à folga" em todo resumo.
2. **"Verificado no outbox" só cobria a leitura corrente, e `created_at` não é commit.** Cenário: amostra antiga da
   janela inserida depois do sinal entra na mediana. → Emenda item 2: guarda da janela inteira (qualquer amostra com
   inserção > obs recusa) e prova por `dispatched_at` (o relay só lê linha comitada). Velas 1 min: mesma limitação,
   publicada a sensibilidade sem velas tardias.
3. **Confundimento por dia não tratado.** Cenário: OI sobe no mercado inteiro em dias ruins para rompimento. → Emenda
   item 3: FE de mercado, de dia e de mercado+dia e blocos de 3/5/7 d pré-registrados, com a consequência fixada
   (um REFUTA só generaliza se todos ficarem < +0,05; um CONFIRMA é "associação agregada" sem FE de dia positivo).
4. **Falha fechada incompleta e regra global ambígua.** Cenário: corte singular + IC superior < 0,05 → sairia REFUTA.
   → Emenda item 4: o caminho do R86 (`cuts_invalid` bloqueia) e "as duas em limite, de qualquer causa → LIMITE".
5. **População executável ≠ declarada.** A extração não filtrava exchange; o outbox era casado só por símbolo; junção
   sem checar ID duplicado nas features. → Emenda item 5: `exchanges.code = 'binance'` nos dois lados, unicidade nas
   features e nos desfechos, sha256 conferido na corrida.

## Nice-to-have e leitura

Aceitos: blocos de calendário (item 3), IC da média do grupo favorável, custo "assumido do Lab" ([[KB-0171-custo-real-da-spot-1]]),
nome "OI relativo à mediana semanal" e a advertência de que ele se comporta como variação de ~meia semana e não diz qual
lado está lotado (item 6), e que a sobreposição 773/869 com o R86 não cria antecipação mas impede ler como validação
independente (item 7). Não aceito como controle novo: idade de listagem/unlocks — sem fonte temporal confiável, e
excluir depois de ver seria pior; fica como limite declarado.

## Concordâncias

MRE 0,05 como escolha prévia; Holm com `volume_anomaly` em p = 1 (o p bruto da momentum precisa ficar < 0,025);
cortes e metades como estabilidade interna; refutação restrita ao tamanho; indisponível ≠ zero; réplica
independente; nenhuma ativação automática.

**Durante a implementação da emenda apareceu um defeito do próprio instrumento** (antes dos desfechos): as folgas de
30/60 min davam 0 elegíveis porque a regra de "leitura velha" estava presa aos 15 min; corrigido com teste, e a lista
congelada de 15 min ficou byte a byte igual.

Resultado e segunda revisão em [[H-033-resultado]]; nota de conhecimento em
[[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]].

# Decisões delegadas pelo Everton — 2026-09-08

Everton, 2026-09-08 ~09:00Z ("pode tomar a decisão sexta feira"), sobre as duas perguntas da T3.19b (`docs/plans/REPLICATION.md` §3.5 e §9). Decididas pela Sexta-feira/orquestrador em nome dele, com o dado medido na VPS (`79379ef`: 288 barras em 3,8 s = 75 barras/s com 3 processos, 1 dia × 3 mercados).

## D14 — o que conta como "validação" (meta "500 mil por dia")
**Duas medidas, as duas no placar, cada uma com o seu papel.**
- **Decisões simuladas** (uma barra real avaliada pela estratégia, com a decisão registrada): é a medida de **massa**. Meta: 500 000 por dia. Medido na VPS com 3 de 12 vCPU: ~6,5 milhões por dia (13×). Cumprida.
- **Operações fechadas** (entrada e desfecho): é a medida de **evidência** para a régua (100 resultados e 30 dias) e para o protocolo de replicação. **Sem meta numérica diária**: ~160 mil por dia no orçamento atual; chegar a 500 mil exigiria ~10 vCPU e faminta a coleta ao vivo, que não se recompõe.
**O que não muda:** custos declarados, sem olhar o futuro, tudo sob coorte `replay:`/`replication:`, nada chega à carteira. **Dono:** placar (T3.18 follow-up) mostra as duas contagens por versão; `docs/plans/REPLICATION.md` §9 cita esta decisão.

## D15 — o replay pode amadurecer as irmãs
**Sim, com rótulo.** O bloco 2 do protocolo (10 irmãs de parâmetros) pode atingir a maturidade pela **metade da régua** (≥ 50 resultados E ≥ 15 dias distintos) usando replay histórico sobre os 31 dias, desde que: (a) cada irmã e cada número apareçam com o rótulo "replay" ao lado; (b) o bloco 1 (fora da amostra) e a régua do placar (`validada`/`reprovada`) continuem **só** com `prospective`; (c) o mesmo replay rode para o pai na mesma janela, para a comparação ser justa; (d) o veredito `real` continue exigindo os quatro blocos.
**O que não muda:** `promissora` só nasce da régua em tempo real. **Dono:** `docs/plans/REPLICATION.md` §3.5 passa de proposta a regra; T3.19e (irmãs por replay no placar).

## Consequência operacional
Nenhuma versão é `promissora` hoje (2 dias de dados, expectancy negativa nas duas), então **não há irmãs a criar**. O primeiro uso do replay é o **histórico das duas versões de pesquisa** (momentum v2, volume_anomaly v2) sobre os 31 dias, quando o backfill terminar, mostrado no placar como "replay" — evidência histórica, não veredito.

## D16–D19 — direção de design (Everton, 2026-09-08 ~09:45 Brasília: "tudo ok pode fazer")
Aprovadas as quatro propostas do product-designer (`.claude/state/review-design-2026-09-08.md`, "Só o Everton decide"):
- **D16** — nomes de página em **português**, mantendo "Lab" e "Radar" como nomes próprios.
- **D17** — convenção numérica **brasileira** para dinheiro e porcentagem (`R$ 1.234,56`, `+1,23 %`); preço cru como a exchange mostra (`27460.00`), USDT com a mesma convenção do dinheiro.
- **D18** — direção do Lab: **placar primeiro**, depois sinais, depois versões recolhidas; o designer apresenta dois mockups A/B em `/_design` antes do frontend mexer.
- **D19** — regra "sem bastidor na tela": nenhum id de tarefa, ADR, nome de parâmetro de API ou enum cru na copy; dicionários de rótulos por domínio.
**Donos:** T3.24a (ganhos rápidos, em voo), T3.24c (consistência: D16, D17, D19), T3.24b (Lab: D18, após os mockups). `docs/DESIGN.md` recebe as quatro como regras (§2) com histórico.

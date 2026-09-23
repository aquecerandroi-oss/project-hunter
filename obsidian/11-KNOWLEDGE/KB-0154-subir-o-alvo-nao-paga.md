---
tags: [knowledge, meme, mesa-real, saida, alvo, tempo-maximo, metodo, hipotese, m4]
tema: nenhum alvo entre 1,08× e 1,50× e nenhum tempo máximo entre 30 e 300 s bate a regra atual (1,15× / 10 % / 300 s) na mesma posição; o que fica na mesa depois do alvo é teto de oráculo, não é capturável
fonte: R74 (`.claude/state/notes-R74.md`) — H-011 e H-012 da Fila de Hipóteses (23/09/2026)
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 66 posições reais (uma por mint, de 89 fechadas, 17–23/09/2026) + 463 apostas de papel; contraste emparelhado política × política na mesma posição sobre o simulador do R72; 47 testes de anti-antecipação
hipotese_testavel: sim
astra: concorda com ressalvas (duas rondas; 8 correções de desenho antes de correr, 3 de redação no veredito)
status: vivo
owner: sexta-feira
updated: 2026-09-23
confiança: "medido uma vez"
---

# KB-0154 — Subir o alvo não paga (e encurtar o tempo também não)

> **H-011 (onde deve ficar o alvo): `REFUTA`. H-012 (tempo máximo curto): `REFUTA`.** Cláusula
> literal da fila nas duas populações. Estudo em `.claude/state/notes-R74.md`; pré-registos em
> [[Fila de Hipoteses]] § H-011 e § H-012.

## O que se mediu

Na **mesma posição**, a diferença entre sair com outra regra e sair com a regra atual (alvo 1,15×,
recuo de 10 % armado na entrada, 300 s), já com 2,23 % de custo por ida e volta e 1,6 s de atraso.
Grade do alvo {1,08 · 1,12 · 1,15 · 1,20 · 1,30 · 1,50}, o "primeiro repique de X % depois de uma
queda" (X = 3, 5, 8 %) e o tempo máximo {30, 60, 120, 300} s.

## O que se aprendeu

1. **Mexer no alvo não paga.** O melhor é 1,08× nas duas populações — a borda da grade. Nas reais
   (n = 66) dá +3,05 pp por SOL (IC [−0,53, +7,27]) e cai para +0,78 pp com 5 s de atraso; no papel
   (n = 463) dá +0,19 pp e morre a 5 s (−0,05 pp). No papel, **nenhum IC superior passa de +1,1 pp**: a
   vantagem de +5 pp está excluída. Nas reais não está (+7,27 pp), por isso lá a leitura é "não confirma
   vantagem", ao lado do `REFUTA` literal. Todas as políticas perdem em nível.
2. **O fragmento do R72 era seleção pelo resultado.** "Vender o primeiro repique e não voltar" medido
   em todas as posições dá −0,31 pp nas reais. Os +3,44 pp eram a média de quem **depois** não teve
   queda.
3. **O que fica na mesa é teto de oráculo.** Depois de uma saída pelo alvo, o lote ainda chega a valer,
   em mediana, +28 % do custo a mais — mas trocar a saída por segurar até aos 300 s (da entrada) dá
   **−23 pp em mediana** e só ganha em 39 % das vezes, e nenhum alvo mais alto da grade paga. Isto não
   testa todas as saídas intermédias possíveis. O 1,15× já apanha parte da corrida: o pouso cai 1,6 s
   depois do gatilho (mediana realizada +17,6 %).
4. **Mais alvo compra mais cauda.** De 1,15× para 1,50×, as perdas ≥ 50 % sobem de 2,6 % para 3,7 % no
   papel (5 criadas, 0 evitadas). Descer para 1,08× evitou as duas perdas graves das reais, mas o papel
   não repete: perdas de 90 % são quedas num único salto que nenhum alvo apanha.
5. **"O que não sobe logo não sobe mais" é metade verdade.** Só 9 das 23 vitórias reais pousaram até
   aos 30 s (23/09 foi mais rápido que o normal). Um tempo máximo de 30 s corta **14 das 23 vitórias** e
   dá −1,8 pp. Reduz parte da cauda (perdas ≥ 50 %: 2 → 1 nas reais, 12 → 7 no papel), mas as quedas
   precoces ficam (aos 21 s; 7 de 12 no papel antes dos 30 s) e o D médio é negativo.
6. **O sinal do alvo baixo muda com a qualidade da fita.** Onde a fita é contínua, alvos mais altos são
   melhores; onde há buracos > 30 s, o 1,08× é melhor. Um alvo baixo "dispara" no primeiro ponto depois
   de um buraco. Qualquer estudo de saída tem de estratificar por cobertura.

## Ressalva que importa

**Cobertura e observabilidade, juntas.** O único ganho (1,08× nas reais) vive nas posições com buracos
de fita > 30 s (+8,15 pp) e inverte onde a fita é contínua (−3,06 pp). E a simulação age sobre cada
estado no seu `block_time`, a supor que a mesa vê a fita **WS** ao vivo; os dados vêm de `meme_trades`,
cópia por polling com ~44 s de atraso de chegada ao arquivo (R73 — atraso do arquivo, não latência
medida da mesa). Os 5 s de sensibilidade atrasam o pouso, não a observação.

## O que reabriria

População nova (posições depois de 23/09 19:31 UTC, com fita WS contínua) ou medida nova (cobertura sem
buracos > 30 s). **Nenhum braço de papel é proposto**: nenhuma célula confirmou.

Relacionadas: [[KB-0152-a-oscilacao-existe-o-giro-nao-paga]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Fila de Hipoteses]]

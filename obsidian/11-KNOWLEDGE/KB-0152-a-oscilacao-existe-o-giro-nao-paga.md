---
tags: [knowledge, meme, mesa-real, giro, scalping, custo, saida, metodo, hipotese, m4]
tema: a oscilação de 3 % dentro dos 5 minutos existe e é frequente, mas girar nela não paga — a oscilação de equilíbrio é 2,22 % e o que anula o giro é a recompra e a falta de freio entre giros
fonte: R72 (`.claude/state/notes-R72.md`) — H-009 da Fila de Hipóteses, ideia do Everton (23/09/2026)
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 76 posições reais com fita (de 89 fechadas, 17–23/09/2026) + 463 apostas de papel, uma por mint; reconstrução trade a trade herdada de R62/R64/R65; 9 testes de anti-antecipação
hipotese_testavel: sim
astra: concorda com ressalvas (duas rondas, 7 must-fix corrigidos)
status: vivo
owner: sexta-feira
updated: 2026-09-23
confiança: "medido uma vez"
tipo: pesquisa
hipotese: H-009
variavel: giros_liquidos_5m (politica de giro: vender no repique, recomprar na queda)
populacao: 89 posicoes reais + apostas de papel com fita completa entre entrada e saida
efeito: D entre -4,24% e +4,44% (reais), -1,41% a +2,27% (papel), 12 celulas
ic: todos os 12 IC de cluster por mint atravessam zero
veredito: nao_confirma
proximo_passo: vender o primeiro repique e nao voltar virou hipotese nova sobre o alvo (H-011)
classe_de_perda: recompra
mercado: meme
---

# KB-0152 — A oscilação existe; o giro não paga

> **Veredito de H-009: `NÃO CONFIRMA`** (não é refutação). Estudo completo em
> `.claude/state/notes-R72.md`. Pré-registo em [[Fila de Hipoteses]] § H-009.

## 1. A pergunta

Ideia do Everton (23/09/2026, 17:1x BRT): *"conforme vai acompanhando o gráfico, vai comprando e
vendendo muito rápido: desceu comprou, subiu vendeu, desceu comprou, subiu vendeu — e lucra antes de
alguém vender tudo e derrubar."* Duas perguntas separadas, e é preciso separá-las: **(a) a oscilação
existe?** e **(b) girar nela paga mais que a regra atual?**

## 2. Sim, a oscilação existe — e isto é novo

Oscilação completa = queda ≥ X % da máxima corrente, seguida de recuperação ≥ X % em N s, dentro dos
5 min após a entrada. Mediana de oscilações **por posição**, 76 posições reais com fita:

| X % | N = 30 s | N = 60 s | N = 120 s | ≥ 2 giros (N=60 s) |
|---|---|---|---|---|
| **3** | **3,5** | **3,5** | **4,0** | 69,7 % |
| **5** | 2,0 | 3,0 | 3,0 | 61,8 % |
| **8** | 1,0 | 1,0 | 2,0 | 48,7 % |
| **12** | 0,0 | 1,0 | 1,0 | 34,2 % |

As 463 apostas de papel repetem (3 · 2 · 1–2 · 1). **O gráfico faz mesmo o que o Everton descreve.**
A regra de refutação barata da fila (*mediana < 2 em todas as células*) **não disparou**.

## 3. E mesmo assim o giro não paga: 0 de 12 células

Política: vender a cada repique de X %, recomprar a cada queda de X %, dentro dos mesmos 5 min e com
o mesmo teto de 0,07 SOL, contra a regra atual (alvo 1,15× / trailing 10 % / 300 s), **na mesma
moeda**, com **2,23 % por ida e volta** e **1,6 s de atraso por perna**.

- D (giros − regra) por SOL arriscado: **−4,24 % a +4,44 %** nas reais; **−1,41 % a +2,27 %** no papel.
- **Todos os 12 IC 95 % (bootstrap de cluster por mint) atravessam zero**, nas duas populações.
- Menor p de permutação emparelhada: **0,120** (reais, X=12/N=30) e **0,112** (papel).
- Previsão pedia **+0,05 por SOL**: **0 de 12** células chegam lá.
- Refutação da fila pedia IC superior < **+0,01** em todas: o maior é **+0,103**. **Não atingida.**
- Custo a 2,5 % ou 3 % e atraso a 5 s **não salvam** nenhuma célula.

Curva em X **monótona crescente com máximo na borda** (−1,53 %, −1,06 %, +0,67 %, +3,25 % para
X = 3, 5, 8, 12): tendência descritiva, **não** um ótimo. E no papel a monotonia quebra.

## 4. O número que interessa: a oscilação de equilíbrio é 2,2176 %

Por ciclo completo, o multiplicador de fichas é **(1 − c/2)² / (1 − X)**, com equilíbrio em
**X = c − c²/4**:

| custo por ida e volta | X de equilíbrio |
|---|---|
| **2,23 %** (actual, sem aluguel de ATA) | **2,2176 %** |
| 2,50 % | 2,484 % |
| 3,00 % | 2,978 % |

**Uma oscilação tem de passar de ~2,2 % só para pagar as taxas.** A X = 3 % sobram **0,78 pp por
giro** — **0,00055 SOL** sobre uma ficha de 0,07. A fita entrega essa amplitude com folga (giros de
≥ 2,22 % em N = 60 s: mediana **5** por posição, ≥ 2 em **72 %** das posições). **O teto da ideia
não é a amplitude — é a margem por giro.**

## 5. Por que é que um giro que ganha fichas não vira lucro

**Cada ciclo completo devolve mesmo mais fichas:** mediana **1,045** a X = 3 % e **1,167** a X = 12 %,
acima de 1 em **91 % a 100 %** dos ciclos. A mecânica funciona. O que a anula:

1. **A recompra não tem defesa.** **11 % a 15 % das recompras** acabam em dreno (o lote passa a valer
   ≤ 50 % do que se pagou). Comprar a queda é comprar de quem está a vender, e numa em cada sete
   vezes quem vende sabe algo que nós não sabemos. Coerente com
   [[KB-0143-o-que-antecede-o-dump]]: a venda grande é **gatilho**, não aviso.
2. **Entre giros ficamos dentro sem freio.** Nas posições que **nunca** dão o repique de X %, a
   política de giros não tem trailing e segura até aos 300 s: **−31,8 %** por SOL, **−13,4 pp** pior
   que a regra atual. É o buraco por onde o resto escorre.
3. **Poucos giros se completam.** ~1 ciclo por posição. 4,5 % de fichas a mais uma vez não move o
   agregado.

**O único pedaço com sinal não é giro:** em **62 %** das posições a política vende o primeiro
repique e **a queda nunca vem em N s** — fica de fora e ganha **+3,44 pp** sobre a regra. Isso é uma
hipótese sobre o **alvo**, não sobre giros.
**Atenção:** os três grupos são definidos por coisas que só se sabem **depois** da entrada. Condicionar
aí é a armadilha que já derrubou H-005 e H-006 ([[KB-0149-o-que-a-mesa-real-ensinou]]). **O único
número decisório é o D incondicional da §3, e esse é zero com intervalo largo.**

## 6. Ressalvas, por ordem de importância

1. **Cobertura da fita.** **44 de 76** posições reais e **309 de 463** de papel têm pelo menos um
   buraco > 30 s sem nenhum ponto na janela de 300 s (mediana do maior buraco: 45 s e 54 s). Ter fita
   **não prova** continuidade da fita — o `swap_api` vem por REST e tem furos (R65 §8). Nesses
   trechos, ausência de oscilação **não é prova de ausência**. As células N = 30 s são
   **exploratórias** e nenhuma conclusão se apoia nelas.
2. **13 das 89 posições reais (e 62 das 545 de papel) só têm fotos de ~15 s** — não resolvem uma
   oscilação de 3 % e foram **excluídas e contadas**, nunca mantidas em silêncio.
3. **Desvio declarado face a R64/R65:** o carregador antigo reordenava estados prontos por timestamp,
   o que fazia o caminho voltar a um slot antigo e fabricar quedas. Aqui a ordem é a da cadeia, com
   carimbo monótono — **183** regressões corrigidas nas reais e **1 070** no papel. Os números do R72
   **não** são comparáveis linha a linha com os do R64.
4. **Viés a favor da política, declarado:** o impacto dos nossos próprios negócios simulados não é
   propagado para o resto do caminho (convenção "segurar" do R64), e a execução é sempre bem
   sucedida com latência constante. Ou seja, **a política foi medida numa versão optimista de si
   mesma — e ainda assim não venceu.**
5. **Sete dias, um regime, tudo pump.fun, ficha fixa de 0,07 SOL.** Nada disto generaliza.

## 7. Anti-antecipação

O simulador só vê `pontos[0..i]` ao decidir em `i`; o pouso usa o último estado com
`t ≤ gatilho + 1,6 s` e uma guarda recusa qualquer pouso anterior ao gatilho. Provado por
**invariância ao sufixo futuro** (trocar o futuro depois de *t* não muda nenhuma decisão anterior) e
por um **contraexemplo batoteiro** que tem de falhar. O braço `cheat` — que vende no máximo da janela
olhando o futuro — rende **+47,96 %** por SOL contra **−2,04 %** da regra atual: essa distância é o
que a guarda protege. 9 testes, todos a passar (`.claude/state/r72/test_r72.py`).

## 8. O que reabriria H-009

1. **Fita contínua por WebSocket** (e não REST). Sem isso, metade da amostra não decide N = 30 s.
2. **A perna que ganha, isolada:** "vender o primeiro repique e não voltar" como bloco **novo** na
   fila, com previsão e refutação escritas antes — nunca herdando os números desta análise, que foram
   olhados.

## 9. Ligações

[[Fila de Hipoteses]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]] · [[KB-0143-o-que-antecede-o-dump]]

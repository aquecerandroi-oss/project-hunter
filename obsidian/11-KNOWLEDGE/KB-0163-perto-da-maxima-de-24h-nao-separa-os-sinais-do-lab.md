---
tags: [knowledge, cripto, lab, shadow, momentum, maxima-24h, hipotese, metodo, m4]
tema: estar perto da máxima de 24 h no instante do sinal não separa os sinais de continuação do Lab de cripto (H-023 não confirma); momentum e volume_anomaly puxam para lados opostos; a secundária (longe da mínima de 24 h) separa, mas o melhor tercil ainda perde em nível
fonte: R83 (`.claude/state/notes-R83.md`) — H-023 da Fila de Hipóteses
fonte_url:
lido_em: 2026-09-28
evidencia: medição própria — 9 187 sinais de continuação do Shadow Lab com R_net e feature (momentum v1–v13, volume_anomaly v1–v2, session_orb, breakout; 12/06 → 28/09, 289 mercados perpétuos), feature reconstruída das velas com a fórmula de produção (idêntica ao snapshot de produção em 337/337), bootstrap por mercado 10 000 (moinho), p por episódios, 17 testes sintéticos
hipotese_testavel: sim
astra: concorda (desenho com 3 must-fix aceitos antes dos desfechos; veredito sem must-fix, contrastes reproduzidos por ela)
status: vivo
owner: sexta-feira
updated: 2026-09-28
confiança: "?"
tipo: pesquisa
hipotese: H-023
variavel: distance_from_24h_high no instante do sinal (tercil alto - baixo dentro da estrategia); secundaria distance_from_24h_low
populacao: 9187 sinais de continuacao do Lab de cripto (perp, terminal, R_net) 12/06-28/09, uma decisao por (versao, mercado, barra)
efeito: D (alto - baixo) = -0,0324 R; secundaria d_low +0,2069 R
ic: D [-0,1131, +0,0376]; d_low [+0,1206, +0,2841]
veredito: nao_confirma
proximo_passo: nenhum filtro de maxima no Lab; a pista de distance_from_24h_low (e a divergencia momentum x volume_anomaly) so volta como hipotese nova em coorte futura, com o valor gravado no envelope do sinal
classe_de_perda: —
mercado: cripto
---

# KB-0163 — Perto da máxima de 24 h não separa os sinais do Lab

> **H-023 (proximidade da máxima de 24 h): `NÃO CONFIRMA`.** Nos 9 187 sinais de continuação do Lab de cripto, o tercil
> mais perto da máxima de 24 h rendeu **−0,0324 R** a menos que o mais longe, IC 95 % por mercado **[−0,113, +0,038]**;
> a previsão pedia **+0,05 R** com o IC acima de zero. A curva de cortes vizinhos não tem nenhum ponto positivo.
> A vantagem prevista de +0,05 R fica acima do limite superior do IC por mercado, então esse intervalo não a sustenta;
> o critério formal de refutação por tamanho (IC superior abaixo de +0,01 R) **não** foi atingido, e o IC por dia
> ([−0,132, +0,093]) ainda comporta +0,05. Por isso é `NÃO CONFIRMA` e não `REFUTA`.
> Estudo em `.claude/state/notes-R83.md` · código e saídas em `.claude/state/r83/` · pré-registo em
> [[Fila de Hipoteses]] § H-023 · origem em [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]].

## O que afirma

Nos sinais de compra de continuação do Shadow Lab (momentum, volume_anomaly, session_orb, breakout), saber se o preço
está perto da máxima intrabar das últimas 24 h, no fechamento da barra de decisão, **não melhora** o resultado líquido
de custo. Os três tercis perdem quase o mesmo: −0,216 R (longe), −0,213 R (meio), −0,248 R (perto).

O agregado esconde duas estratégias que puxam para lados opostos. É uma decomposição descritiva, publicada junta e
**não** um teste de interação — não autoriza tirar a volume_anomaly da família nem salvar a hipótese só na momentum:
- **momentum**: perto da máxima rende mais, D **+0,097 R** [+0,028, +0,162] — o sentido de George & Hwang —, mas o
  melhor tercil ainda **perde −0,096 R**, e o IC por dia ([−0,030, +0,233]) contém zero;
- **volume_anomaly**: perto da máxima rende **menos**, D **−0,231 R** [−0,363, −0,094] (o tercil perto perde −0,488 R).

A variável secundária, **distância da mínima de 24 h**, separa: longe da mínima rende **+0,207 R** a mais que perto,
IC [+0,121, +0,284], Holm 0,0004, patamar nos 7 cortes vizinhos. Mas o melhor tercil também **perde em nível**
(−0,097 R) e a variável anda junto com o ATR% (ρ 0,77) e com o retorno de 4 h (ρ 0,70). Controlando pelo tercil de ATR%,
o efeito cai para +0,126 R [+0,029, +0,211]. É uma **pista**, não uma confirmação.

## Onde foi mostrado

- População: `agent_signals` × `signal_outcomes` terminais, long, **perpétuo** (os 133 sinais antigos em linha spot, gêmeos
  do perp e sem R_net, ficam fora — T3.73), **uma decisão por (versão, mercado, barra)** (1 494 duplicadas de coortes de
  replay repetidas saíram, com a prospectiva preferida), guarda de persistência do moinho (79 recusadas), R_net
  (`r_multiple`: 4 bps de taxa + 2 de spread + 5 de derrapagem + funding) não nulo. 12/06 → 28/09/2026.
- Feature: **não está no envelope de nenhum sinal**, e o snapshot de produção só a tem em 360 de 6 738 sinais recentes.
  Foi **reconstruída** das 1 440 velas 1m finais que fecham até o instante de observação do sinal, com a fórmula de
  `features/price.py:106`. Contra o snapshot de produção do mesmo minuto: **337/337 idênticos**. Testes provam que uma
  vela posterior, ou uma vela ainda em formação, não muda o valor.
- **Redundância medida antes dos desfechos:** |ρ| máximo 0,385 (ATR%) na continuação; retorno 15 m +0,12, 4 h +0,18,
  momentum +0,32. A variável não é redundante.
- Tercis **dentro de cada estratégia** (a momentum vive perto da máxima por construção). Inferência: bootstrap por
  mercado (279 mercados); o p do portão é o **maior** entre a permutação de episódios (as versões que decidem a mesma
  barra andam juntas) e o bootstrap — 0,497. Rótulo pela regra congelada, com a errata do R76.
- Sensibilidades (nenhuma muda o rótulo): só prospectiva −0,088 [−0,177, −0,003]; uma por (estratégia, mercado, barra)
  −0,084 [−0,167, −0,002]; tercis do agregado +0,022; `r_ex_funding` −0,032; momentum v3 (paper) +0,062 [−0,040, +0,163].
- O filtro que o [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume|KB-0004]] propunha (`d_high ≥ −0,005` na momentum)
  retém 29,9 % dos sinais e rende +0,068 R [+0,008, +0,131] a mais que o resto, mas o selecionado perde −0,101 R.

## Reversão e a mesa `spot/1`

Sem sinal previsto. Na família `mean_reversion` (5 129 sinais) o contraste é nulo: D +0,007 [−0,101, +0,143], com o
tercil do meio sendo o melhor (+0,046 R). Na **`mean_reversion v14`** (a versão que a mesa `spot/1` executa), 183 sinais:
o tercil perto da máxima ganhou +0,135 R e o longe −0,094 R, D +0,228 [−0,099, +0,597] — **IC largo, 46 mercados,
só descritivo**.

## Hipótese testável no Lab

Nenhum parâmetro, versão ou filtro novo. O que sobra para uma hipótese futura, **em coorte nova**:
1. gravar `distance_from_24h_high`/`_low` no envelope imutável do sinal (hoje não é gravada), para que a próxima
   medição não dependa de reconstrução;
2. se alguém quiser a pista da mínima: pré-registrar `distance_from_24h_low` com sinal (+) em coorte **posterior ao
   R83**, uma unidade por estratégia × mercado × barra, com um teste incremental **conjunto** contra ATR% e retorno de
   4 h congelado antes, parada por tamanho, e exigindo que o melhor braço **ganhe em nível**;
3. a divergência momentum × volume_anomaly só vira hipótese com população futura e por estratégia, nunca olhando esta.

## Por que pode falhar

- Reconstrução retrospectiva: a janela é exigida inteira até `obs`; o scanner às vezes não tinha as 1 440 velas.
  A conclusão é sobre a variável reconstruída, não sobre o que o scanner teria visto.
- Todas as versões do Lab juntas (a maioria já aposentada): a população mistura regras diferentes. Os tercis por
  estratégia e o p por episódios seguram parte disso, mas choques comuns entre mercados no mesmo dia não.
- A extrapolação de George & Hwang (ações, mensal, transversal) para 24 h e 15 m continua só isso: extrapolação.

## Segunda opinião (Astra)

**Desenho** (antes de abrir qualquer desfecho): concordou com a janela e a causalidade, as famílias, os tercis por
estratégia, o patamar fora do moinho e a errata. Três must-fix, todos aceitos numa emenda antes dos desfechos:
`received_at` é carimbo de persistência (a guarda vira proxy e a conclusão fica sobre a reconstrução); o p linha a linha
não serve para o Holm quando as versões decidem a mesma barra (virou o maior entre a permutação de episódios e o
bootstrap por mercado); o rótulo da fila é externo ao moinho (o moinho refuta com IC superior < +0,05, a fila com
< +0,01).

**Veredito**: concorda com `NÃO CONFIRMA`, reproduziu os dois contrastes, conferiu os hashes e as junções, sem must-fix.
Registrou o argumento literal para REFUTA (a fila diz "IC inferior < −0,01") e concordou que aplicá-lo abandonaria a
errata escrita antes. Pediu a redação sobre o +0,05 fora do IC só por mercado, a heterogeneidade publicada junta e a
`_low` como pista (ρ 0,77 com ATR% não prova informação a mais). Síntese em [[R83-maxima-24h]].

## Relacionados

[[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] (H-027 usou `distance_from_24h_low` só como **controle** do modelo conjunto, sobre unidades que quase todas já estavam aqui — não é replicação da pista) ·

[[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] · [[KB-0145-binance-como-sinal-solana-como-execucao]] ·
[[Strategy Backlog]] (item 8) · [[Dicionario de Variaveis]] · [[Mapa de Estrategias]] · [[Fila de Hipoteses]] ·
[[R83-maxima-24h]]

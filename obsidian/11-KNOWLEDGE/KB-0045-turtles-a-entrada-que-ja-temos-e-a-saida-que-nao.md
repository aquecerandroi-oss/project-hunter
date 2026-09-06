---
tags: [knowledge, nota, livros, rompimento, saida]
tema: rompimento de canal / regra de saída
fonte: página pública de regras dos Turtles mantida por Michael Covel (*The Complete TurtleTrader*). Schwager (*Market Wizards*) é contexto, **não** foi consultado nesta rodada
fonte_url: https://www.turtletrader.com/rules/
lido_em: 2026-09-06
evidencia: anedótico
hipotese_testavel: sim
astra: concorda com ressalvas
---

# Os Turtles: a entrada nós já temos, a saída não

## O que afirma

O sistema dos Turtles é um rompimento de canal: compra-se quando o preço faz uma **nova máxima de
20 dias** (Sistema 1) ou de **55 dias** (Sistema 2); o tamanho da posição e o stop são medidos em
`N`, que é o *average true range* diário do mercado — mercado mais volátil, posição menor. Isso é o
que a página de regras publicada afirma explicitamente.

O resto do conjunto — stop a **2N**, saída por **canal oposto de 10 dias** (Sistema 1) ou 20 dias
(Sistema 2), piramidação de meio em meio `N` até 4 unidades, teto de unidades correlacionadas — está
no documento de regras liberado pelos próprios ex-Turtles, que **não abriu para mim** (HTTP 403 em
duas URLs). Esses números ficam marcados como **de memória, a confirmar**, e a página consultada não
os documenta.

A ideia central, e é ela que interessa aqui, não é a entrada: é que **o sistema não teria alvo de
lucro** — sai-se por stop ou pelo canal oposto, isto é, por uma regra que se move junto com o preço e
deixa o vencedor correr até ele parar de correr. Ressalva de fonte, exigida pela revisão: **a
ausência de alvo fixo também está na categoria "de memória, a confirmar"**, porque a página aberta
que li não trata das saídas.

## Onde foi mostrado

Futuros americanos (moedas, juros, metais, energia, grãos), barras **diárias**, 1983–1988, numa
carteira de dezenas de mercados com dimensionamento por volatilidade, piramidação e limites de
correlação. Sem cripto, sem intradiário, sem funding, sem perpétuos. E o registro é o de **um grupo
de operadores famoso por ter dado certo** — a amostra que chega até nós é selecionada por
sobrevivência, o que faz dela evidência anedótica por construção, não estudo.

## Como mediríamos aqui

A parte útil desta nota é o mapeamento: **a nossa condição de entrada tem a mesma forma** que a do
Sistema 1. A `momentum_v1` é um rompimento de canal:

- `lookback_closes = 20`, timeframe 15m (`momentum_v1.py:76-77`);
- a condição é `close_t > max_previous_close(bars, 20)` — a máxima dos **fechamentos** anteriores,
  com a barra corrente excluída (`indicators.py:141`);
- o risco é medido em ATR, com `atr_bars = 97` e `atr_period = 14` no timeframe de 15m;
- `stop_atr = 1,5` e `target_atr = 1,5`, ambos a partir do **fechamento de referência**.

Três diferenças que precisam ficar escritas, porque cada uma delas quebra a transferência:

1. **Não é canal de Donchian.** Donchian usa máximas e mínimas; nós usamos fechamentos. Um pavio que
   ultrapasse a máxima anterior sem fechar acima não dispara nada aqui. Chamar de "Donchian" é
   errado; é **rompimento de canal de fechamentos, inspirado em Donchian** (correção da Astra).
2. **20 barras de 15 minutos são 5 horas, não 20 dias.** A escala do sinal é ~96× menor. Nada da
   evidência dos Turtles atravessa essa distância.
3. **Nós temos alvo, e o sistema deles (pelo que sei) não.** `target_atr = 1,5` fecha a posição na
   primeira vez que o preço anda 1,5 ATR a favor. É a regra que a família de trend following
   **afirma** ser o erro caro; que ela seja onde mora o resultado é tese dos autores, não medição
   nossa nem deles publicada aqui.

Há ainda filtros que os Turtles não usavam: retorno de 15m positivo, `rvol_min = 1,5` e a faixa
`atr_pct ∈ [0,003; 0,05]`. Nós não somos "os Turtles em 15 minutos"; somos um rompimento com filtros
próprios e um alvo fixo.

## Hipótese testável no Lab

**Candidata L2 da fila desta rodada — e são três políticas, não duas.** O braço "Turtle" muda duas
coisas ao mesmo tempo (tira o alvo e põe o canal); comparar só ele com a base mede o **efeito
conjunto** e não diz de quem veio. Por isso, sobre as **mesmas entradas congeladas**, com stop,
invalidação e horizonte inalterados:

| Política | Alvo | Saída móvel |
|---|---|---|
| `EXIT-BASE` | `1,5·ATR₀` | — |
| `EXIT-NOTGT` | nenhum | — |
| `EXIT-CHAN` | nenhum | canal oposto de 10 fechamentos |

```
exit_rule        = "opposite_close_channel"   # só em EXIT-CHAN
exit_lookback    = 10                         # fechamentos de 15m
stop_atr         = 1.5                        # inalterado nas três
horizon_s        = 14400                      # inalterado nas três
```

Saída quando o fechamento de 15m ficar **abaixo do mínimo dos `exit_lookback` fechamentos
anteriores**, avaliada só em barra fechada e paga na abertura do minuto seguinte, com os mesmos
custos assumidos — a mesma convenção da invalidação atual (`walker.py:77,136`).

**Onde o canal pode e não pode contribuir** (correção da Astra, com contraexemplo dela). Chamando de
`B` a máxima dos 20 fechamentos anteriores, que é o nível da invalidação atual
(`momentum_v1.py:282`):

- **nos 9 primeiros fechamentos após o sinal** a janela de 10 ainda contém pelo menos um fechamento
  anterior ao rompimento, logo o seu mínimo é `≤ B`; romper esse mínimo implica `close < B`, e a
  **invalidação já pediria a saída**. Nesse trecho o canal é redundante;
- **a partir do décimo fechamento** a janela passa a conter apenas fechamentos posteriores ao sinal,
  e o canal pode disparar sozinho. O contraexemplo dela: `B = 99,90`, referência 100, stop 97, alvo
  103, nove fechamentos de 100,10 a 100,90 e o décimo em 99,95 — o canal dispara, a invalidação não,
  stop e alvo não. Isso acontece **150 minutos depois do sinal**, dentro das 4 horas.

Ou seja: a contribuição própria do canal existe e cabe no horizonte; **a frequência dela é
desconhecida** e é justamente o que o experimento mede. Eu tinha escrito que seria rara, e o
raciocínio que usei para isso estava errado.

**Refutação:** `ΔR_net` pareado de `EXIT-CHAN` contra `EXIT-NOTGT` ≤ 0 na janela futura reservada,
com Holm sobre os dois contrastes. **Intervalo cobrindo o zero é inconclusivo, não refutação.** E
contar poucas saídas por canal **não** refuta a candidata: poucas saídas podem ter efeito grande.

## Por que pode falhar

1. **A escala.** Diário → 15 minutos é a transferência mais agressiva desta rodada inteira. A
   [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] já registrou que horizonte não se
   transfere de graça.
2. **O sistema não é a regra.** O resultado dos Turtles vem de uma carteira de dezenas de mercados
   pouco correlacionados, com piramidação e dimensionamento por `N`. O Lab de sombra **não
   dimensiona posição e não tem carteira** (`PnL de carteira` é *não aplicável* por contrato). Testar
   a regra de saída isolada é legítimo; chamar o resultado de "o sistema dos Turtles" não é.
3. **O horizonte é curto para a regra.** Com `horizon_s = 14400`, cabem **até 16 fechamentos de 15
   minutos** de avaliação (não necessariamente 16 velas UTC inteiras: a entrada é uma abertura de 1
   min posterior à decisão, e o horizonte conta a partir dela — `plan.py:48`, `progress.py:74`). O
   canal só pode contribuir do décimo fechamento em diante, o que deixa uma janela efetiva de ~6
   fechamentos. Isso **não** torna a contribuição desprezível; torna-a concentrada no fim do
   acompanhamento, e é por isso que os três braços da tabela existem — para separar "tirar o alvo"
   de "pôr o canal".
4. **Duração e funding.** Tirar o alvo alonga a exposição, o que aumenta atravessamento de
   liquidação de funding e **expiração por horizonte** (`EXPIRED`, que não é censura — são estados
   distintos: `walker.py:75`, `progress.py:136`)
   ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
5. **Sobrevivência da fonte.** A evidência é a história de um grupo que ficou famoso por ter
   funcionado. Não há grupo de controle.

## Segunda opinião (Astra)

Concordou com o mapeamento entrada-a-entrada e **corrigiu três coisas** na minha primeira redação:

- **"Donchian" sem qualificação está errado** — o nosso canal é de fechamentos, não de extremos
  (`indicators.py:141`), e a entrada exige ainda retorno, volume relativo e faixa de ATR%
  (`momentum_v1.py:180`). Não é "rompimento puro".
- **A simetria é em torno da referência, não da entrada** (`momentum_v1.py:216`, `walker.py:42`), o
  que tem consequência aritmética direta — está na [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]].
- **"20 barras de 15 min não replicam 20 dias"**, e entrevistas ou resultados históricos não validam
  a nossa adaptação. Ela pôs a família Schwager/Clenow na categoria "regras objetivas rendem
  hipóteses; diversificação, pirâmide e resultado do sistema completo exigem carteira".

Na **revisão da nota** ela derrubou o argumento com que eu tinha rebaixado a própria candidata:

- **"o canal raramente decidiria a saída em 4 h" não está demonstrado.** O mínimo dos dez
  fechamentos pode já estar acima do stop na entrada; não é preciso esperar subida nenhuma. A
  restrição verdadeira é a **concorrência com a invalidação** nos nove primeiros fechamentos, e ela
  produziu o contraexemplo numérico que está na seção da hipótese. "Rebaixar a candidata por uma
  irrelevância estrutural que não existe" foi o cenário de falha que ela nomeou.
- **O braço original media duas mudanças de uma vez** — daí os três braços `EXIT-BASE` /
  `EXIT-NOTGT` / `EXIT-CHAN`.
- **Intervalo cobrindo zero é inconclusivo**, não refutação; e poucas saídas por canal não refutam o
  canal.
- **Vocabulário:** `EXPIRED` não é censura; "nunca acompanhados" vira "não usados como barreiras pelo
  acompanhamento atual"; Schwager sai da linha de fonte porque não foi consultado.

Discordância que fica registrada como ressalva **dela sobre ela mesma**: na curadoria da rodada ela
pôs esta candidata atrás do valor incremental da invalidação, e depois reconheceu que a raridade do
canal, que sustentava parte dessa ordem, não estava demonstrada. A ordem da fila se mantém — mas por
parcimônia (uma variável de cada vez), não por irrelevância presumida do canal.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] ·
[[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[EXP-0001-momentum-v1]]

---
tags: [knowledge, nota, execucao, microestrutura, custos]
tema: Execução e microestrutura do preenchimento
fonte: `services/strategy-worker/hunter_strategy_worker/pricing.py` e `plan.py` + documentação de klines da Binance + medição própria de spread e book
fonte_url: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams
lido_em: 2026-09-06
evidencia: leitura de código + medição própria (spread e book), sem experimento
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# O `open` não é preço executável, e a decomposição do custo tem um termo com sinal desconhecido

## O que afirma

`P_entry = open × (1 + 6/10000)`. O `open` de uma vela de 1 minuto é o **preço do primeiro negócio
do minuto** — um negócio de outra pessoa, no lado que ela escolheu, no tamanho que ela quis, no
instante em que ela quis. Não é uma cotação, não é um mid, e não é o preço que a nossa ordem
encontraria. Se aquele primeiro negócio foi uma compra agressiva, o `open` já está **no ask**; se foi
uma venda agressiva, já está **no bid**.

Consequência, e aqui a primeira versão desta nota errou a conta: a decomposição correta do custo real
de uma compra contra o `open` é uma **identidade assinada**, com `O = open`, `M = mid`, `A = melhor
ask` e `V = VWAP` do tamanho, todos no mesmo instante:

```
V − O  =  (A − M)   +   (V − A)   −   (O − M)
          meio spread    arrasto do    erro de
                          tamanho      referência
```

Os três termos existem, mas **o terceiro entra subtraindo e tem sinal desconhecido**. E o Lab **não
converte esse erro para o lado adverso** — eu tinha escrito que sim, e é falso. `pricing.py` calcula
`spread/2 + slippage` e aplica esse acréscimo ao `open` qualquer que ele seja. Exemplo da Astra, mid
100, bid 99,99, ask 100,01, ordem pequena:

| Se o `open` foi… | atravessar custa contra esse `open` | o Lab cobra | fill sintético contra o mid |
|---|---|---|---|
| no ask (100,01) | ~0 | 6 bps | **7,00 bps** |
| no bid (99,99) | ~2 bps | 6 bps | **5,00 bps** |

Ou seja: o deslocamento assumido é fixo, e o custo **efetivo contra o meio do mercado** oscila em
torno de 6 bps por **±meio spread**, para os dois lados. Não é sempre adverso. É **ruidoso**, e o
ruído é da ordem de 1 bps na mediana do universo.

## Onde foi mostrado

Não é literatura; é a definição do dado. A documentação de klines da Binance define `o` como o preço
de abertura do intervalo, derivado dos negócios ocorridos nele. A
[[KB-0009-o-efeito-do-quarto-de-hora]] já tinha listado o que velas de 1 min permitem e não permitem
afirmar; esta nota estende a lista para o item que faltava: **o `open` não é um preço executável, é
um preço executado — por outro**.

**A tabela de escala que eu tinha escrito aqui foi cortada inteira**, e o motivo importa mais que a
tabela: eu somava `1,15 + 2,3 + 2,3 ≈ 6` e concluía que a hipótese "foi bem escolhida por acaso".
Quatro erros nessa soma, todos apontados pela Astra:

1. **`3,47 − 1,15` não estima o arrasto mediano.** As duas medianas vêm de amostras diferentes, e
   **diferença de medianas não é mediana da diferença**.
2. **`O − M` vale ~±meio spread**, não ±um spread inteiro, se o negócio saiu no melhor bid ou ask.
3. **Sinal desconhecido não implica distribuição simétrica.**
4. **Um negócio pode consumir níveis e sair além do melhor preço pré-negócio**, então nem o spread é
   limite universal do erro.

Uma identidade errada não se conserta com um parágrafo de ressalva embaixo dela.

## Como mediríamos aqui

Uma medida direta existe e não precisa de dado novo, só de guardar o que já passa pela memória: no
instante em que a vela de entrada abre, comparar o `open` com o **mid do book** daquele mesmo
instante. A diferença assinada `(open − mid)/mid`, em bps, **é** o erro de referência, e a
distribuição dela responde a pergunta.

O que impede hoje: o book vive 10 s no Redis e não é persistido
([[KB-0044-o-que-morre-em-dez-segundos]]), e a `market_snapshots` guarda `bid`/`ask` numa cadência de
1 minuto **alinhada ao minuto**, o que não é o mesmo instante da abertura e, pior, tem cobertura de
37% dos minutos.

## Hipótese testável no Lab

**`EXEC-G` — o erro de referência, medido e assinado.** Prospectivo, diagnóstico puro. Para cada
entrada planejada, gravar num registro separado, associado ao sinal (não no envelope da decisão, que
é escrito uma vez), o `bid`, o `ask` e o `mid` do book lidos o mais perto possível da abertura da
barra de entrada, e publicar:

- a distribuição assinada de `(open − mid)/mid` em bps, com **média, mediana e quartis** — não só
  quantis, porque quantis não determinam média;
- a fração dos casos em que o `open` cai **fora** de `[bid, ask]`, publicada como **descrição**;
- e os três termos da identidade acima, cada um com o **mesmo denominador**, medidos por sinal — o
  que dá `V − O` diretamente, sem somar medianas de amostras diferentes.

**Alvo declarado antes, estreitado:** o `EXEC-G` produz a **distribuição do erro de referência**. Ele
**não** conclui "não há viés" a partir de mediana zero — 80% de erros zero e 20% de +10 bps dão
mediana e IQR zero com média +2 bps. Ele conclui sobre a média, com incerteza, ou não conclui.

**Refutação:** cobertura baixa. Se não conseguirmos ler um book próximo o suficiente da abertura em
uma fração alta dos sinais, o diagnóstico é sobre o instrumento e a conclusão é "coletar melhor",
não "o erro é pequeno".

## Por que pode falhar

- **"Próximo o suficiente da abertura" é vago e o vão importa.** O book do hot state tem idade
  mediana de 3,88 s ([[KB-0036-o-tamanho-que-a-sombra-nunca-declara]]). **Não converto isso em bps**
  — a [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] mede deslocamento em
  janelas de 60 a 120 s, e dividir por 60 suporia uma velocidade linear que ninguém mediu.
- **`open` fora de `[bid, ask]` NÃO prova atraso do instrumento.** A primeira compra do minuto pode
  ter consumido o ask, e o book imediatamente posterior já tem outros preços mesmo com recepção
  instantânea. Distinguir isso exige book **anterior** e **posterior** ao negócio, com timestamps e
  sequência — "próximo da abertura" não resolve.
- **Risco de look-ahead.** Ler o book "no instante da abertura" para depois avaliar a entrada
  daquela barra é aceitável **só** como diagnóstico posterior; usar isso para decidir a entrada seria
  usar informação do futuro em relação à decisão. A separação tem de ser explícita no código.
- **Um erro simétrico ainda pode custar.** Se o erro for ruído sem viés, ele não some do resultado:
  entra na variância do R, pelo mesmo mecanismo de geometria congelada da
  [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]].
- **Nada disso justifica mexer nos 6 bps.** A [[KB-0009-o-efeito-do-quarto-de-hora]] já decidiu não
  recalibrá-los com base em OHLC, e esta nota não traz dado que mude a decisão.

## Segunda opinião (Astra)

**Recusou a primeira versão, e a correção principal é aritmética.** Quatro pontos, aceitos:

1. **A decomposição estava errada e a soma que "fechava" em 6 bps foi cortada.** O primeiro termo
   que eu escrevi era `executável − mid` e o segundo `executável − open` — eles se sobrepõem; e
   depois a tabela trocava o segundo por `open − mid`. A identidade correta é
   `V − O = (A − M) + (V − A) − (O − M)`, com o mesmo denominador nos três termos.
2. **"O Lab cobra o erro sempre adversamente" não descreve o algoritmo.** `pricing.py` aplica um
   acréscimo fixo ao `open`, e o erro assinado **já está embutido na referência**. Conferido por ela
   com `[decimal]`: `open` no ask → fill a 7,00 bps do mid; `open` no bid → 5,00 bps.
3. **Os critérios do `EXEC-G` diagnosticavam viés sem poder identificá-lo.** Mediana zero e IQR
   estreito não demonstram ausência de viés médio (80% zeros e 20% de +10 bps dão mediana e IQR
   zero, média +2).
4. **`open` fora de `[bid, ask]` não prova atraso do instrumento.**

Nice-to-have aceito: retirar a conversão "14 bps por minuto ⇒ ~1 bps em 4 segundos", que supõe
velocidade linear.

Divergência: nenhuma. A frase dela que fica: uma ressalva sobre populações diferentes **não salva uma
identidade errada**.

## Relacionados

[[Strategy Backlog]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[EXP-0001-momentum-v1]] · [[Data Flow]]

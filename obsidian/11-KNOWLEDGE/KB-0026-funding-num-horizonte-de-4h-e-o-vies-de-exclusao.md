---
tags: [knowledge, nota, perpetuos, funding, metodo, selecao]
tema: Perpétuos: funding, OI, posicionamento
fonte: Aritmética própria sobre os números publicados na avaliação H2 de [[EXP-0001-momentum-v1]]; `services/strategy-worker/hunter_strategy_worker/funding.py`; documentação da Binance sobre cadência de liquidação
fonte_url: https://www.binance.com/en/support/faq/detail/360033525031
lido_em: 2026-09-06
evidencia: raciocínio sobre o nosso código (arquivo e linha, conferido pela Astra) + **inventário de contagens já publicadas** com populações diferentes entre si — não é medição nova, e a confirmação exige SQL que esta sessão não pôde rodar
hipotese_testavel: sim
astra: concorda com ressalvas
---

# Funding num horizonte de 4 h: o que "0 de 173 atravessaram" pode e não pode dizer

## O que afirma

A avaliação H2 de [[EXP-0001-momentum-v1]] estabeleceu que o funding é **problema de instrumento, não
explicação do vermelho**: entre os outcomes que têm `R_net` e `r_ex_funding`, **nenhum** dos 173 de
momentum atravessou uma liquidação, e só 9 dos 394 de volume, com efeito médio de −0,000195 R e
máximo de 0,028 R. A conclusão está certa e continua de pé.

Esta nota acrescenta uma leitura que muda o **alcance** daquela frase, e é sobre a lógica do nosso
próprio código, não sobre o mercado.

Em `funding.py`, `resolve_funding` só devolve `funding_missing:<instante>` quando existe uma
liquidação **devida dentro de `(entry_ts, exit_ts]`** e a linha correspondente não é encontrada. Não
há caminho para esse motivo sem um instante previsto na janela.

**Mas "previsto" não é "real"** — e esta é a correção que a Astra impôs e que salva a nota de dizer
uma bobagem. O instante vem de `_cadence()` (`funding.py:68`), que **estima** a grade pela moda dos
intervalos do histórico; ele não consulta o calendário efetivo da corretora. Um instante previsto
pode ser **fictício**. Cenário concreto: histórico horário até 04:00, o mercado volta para cadência
de 4 h, a próxima cobrança real é às 08:00, e um acompanhamento das 04:30 às 05:30 recebe
`funding_missing` por uma liquidação das 05:00 **que nunca existiu**.

O enunciado que sobrevive, então, é mais estreito e ainda é útil:

- Todo outcome excluído por `funding_missing` é um atravessador **segundo a grade inferida** — pode
  ser atravessamento real ou artefato da inferência.
- A população com funding resolvível está **empobrecida de atravessadores inferidos**, mas não
  esvaziada: um atravessador com histórico completo é resolvido normalmente, e foi o que aconteceu
  com 9 outcomes de volume.

Ou seja: "0 de 173 atravessaram" **não é tautologia** (eu tinha escrito que era; sai). É um fato
sobre o conjunto resolvível do momentum que merece explicação — por que ali *todos* os
atravessadores inferidos caíram fora, enquanto no volume 9 sobreviveram? — e que **não licencia** ler
aquele número como frequência de atravessamento do mercado.

E `funding_ambiguous_exit` tampouco comprova pagamento (`funding.py:107`): a saída pode ter precedido
a cobrança. São três estados distintos que a nossa leitura precisa separar: atravessamento
**confirmado**, **inferido** e **indeterminado**.

## Onde foi mostrado

Nos nossos próprios números. O que segue é **inventário exploratório**, não taxa: são contagens
publicadas com **populações diferentes entre si**, e a Astra deixou claro que juntá-las numa razão
não produz uma medida.

| Estratégia | Resolvíveis com liquidação | Excluídos por `funding_missing` | Atravessadores inferidos |
|---|---|---|---|
| momentum | 0 | 27 | 27 |
| volume_anomaly | 9 | 46 | 55 |

Por que isso **não** vira taxa: os 173 e 394 são "outcomes com `R_net` **e** `r_ex_funding`" em todos
os estados, enquanto os 27 e 46 vêm do censo de `funding_missing` na coorte; os "14 e 36 excluídos"
citados na mesma página são sobre a população **avaliável**, que é outra ainda; e os 9 já estão
dentro dos 394 (a base de volume é 440, não 449, como eu tinha escrito). Há também
`funding_ambiguous_exit` e `funding_price_missing`, que implicam instante previsto na janela e **não**
estão nos 73.

**E uma inferência que eu tinha escrito e que sai inteira:** eu havia derivado, de uma "taxa de
atravessamento de ~13%", uma duração média de acompanhamento da ordem de 1 hora. A derivação
depende de uma taxa que não tenho, de entradas uniformes em relação à grade e de atravessamentos
inferidos serem reais. Nada disso está estabelecido. **Duração se mede medindo duração**
(`exit_ts − entry_ts`), e é isso que a próxima seção pede.

## Como mediríamos aqui

Três consultas, nenhuma cara, **nenhuma delas rodada nesta sessão** (o portão de permissão recusou
`psql` na VPS e o Docker local está fora):

1. **Distribuição de `exit_ts − entry_ts`** por estratégia e por modo de saída. Mede a duração
   diretamente e dispensa toda a inferência acima.
2. **Taxa de atravessamento explícita:** entre todos os outcomes encerrados, quantos tiveram pelo
   menos uma liquidação devida na janela — contando `settlements > 0` **e** todos os motivos de
   indisponibilidade que implicam atravessamento, juntos.
3. **Composição dos excluídos:** os atravessadores excluídos diferem dos incluídos em duração, em
   hora do dia, em mercado ou em modo de saída? Se sim, a exclusão não é aleatória, e a página de
   avaliação precisa dizer em que direção.

## Hipótese testável no Lab

**Não é candidata de estratégia; é requisito de protocolo**, e complementa o protocolo de associação
que a H2 já definiu (identificar o evento do mesmo mercado, exigir associação única, preservar o
timestamp original, recusar ambiguidade nas fronteiras, tolerância muito menor que metade do
espaçamento mínimo validado):

- **Distinguir, por outcome, liquidações previstas, observadas e ausentes.** O `interval_s` inferido
  **já é persistido** (`funding.py:59` → `settle.py:98`) — eu tinha proposto acrescentá-lo, e não
  precisa. O que falta é a separação entre o que a grade previu e o que a série mostrou.
- **Reportar atravessamento junto com toda métrica de `R_net`**, com os três estados separados
  (confirmado, inferido, indeterminado), para que ninguém volte a ler "0 de 173" como frequência de
  mercado.

**Dois mecanismos de falha, e só um foi medido.** O que a H2 mediu foi **jitter**: deltas de 0 a
1001 ms entre o instante pedido e a linha existente, com 851 de 1883 linhas tendo parte de segundos
diferente de zero. Desalinhamento de grade, não cadência errada.

O **segundo** mecanismo é a mudança de cadência — e a Astra corrigiu o encadeamento causal que eu
tinha escrito. **8 h → 1 h, com horários alinhados e histórico completo, não produz
`funding_missing` automaticamente**, porque `resolve_funding` faz a **união** da grade prevista com
os eventos observados (`funding.py:122`): a liquidação horária que de fato ocorreu entra pela via do
observado. O caso que produz exclusão é o **inverso** — a reversão 1 h → 4 h, com a moda ainda
horária prevendo instantes que já não existem, exatamente o cenário do início desta nota.

Portanto: a correlação das exclusões com regime de funding extremo é **hipótese**, não consequência
demonstrada. Fica registrada como pergunta, não como diagnóstico.

**O cenário pior — subestimação silenciosa — é real, mas exige uma condição a mais** do que eu tinha
escrito: não basta a moda estar errada; é preciso que uma cobrança real esteja **ausente da nossa
série** e que a grade errada **também não a preveja**. Exemplo: moda de 8 h, última observação às
08:00, cobrança real às 09:00 que não temos, acompanhamento das 08:30 às 09:30 → devolve **zero**
(`funding.py:129`), sem motivo, sem rastro. Se a linha existir, ela entra pela união e o problema não
ocorre.

*Refutação retirada:* eu tinha escrito que `interval_s` constante por mercado refutaria o segundo
mecanismo. Não refuta — uma moda **persistentemente errada** também é constante.

## Por que pode falhar

- **As contagens desta nota vêm de populações diferentes.** Está declarado, e é por isso que são
  inventário e não taxa. Se as consultas mostrarem outra composição, a tabela sai numa linha nova,
  não é editada.
- **Atravessamento inferido pode ser artefato.** Confundi-lo com atravessamento real infla o
  numerador de qualquer contagem — o must-fix central desta revisão.
- **A conclusão da H2 não muda.** O efeito medido do funding é de duas ordens de grandeza menor que a
  expectancy observada. Esta nota corrige o **alcance de uma frase**, não a conclusão.
- **Corrigir com tolerância larga continua proibido.** ±2 s permitiria cobrar a mesma liquidação duas
  vezes (a função faz a **união** da grade calculada com a observada) e cobrar funding **posterior**
  à saída. O protocolo correto já está escrito na H2 e em [[Open Bugs]].
- **Um `interval_s` errado não é só exclusão.** Se a moda acertar por acaso num mercado que mudou de
  cadência, a grade pode prever liquidações **a menos**, e aí o custo é subestimado em silêncio, sem
  gerar `funding_missing` nenhum. Este é o cenário pior, porque não deixa rastro.

## Segunda opinião (Astra)

Ela desarmou a peça central da primeira redação com um cenário concreto: **o instante previsto pode
ser fictício**, porque `_cadence()` estima a grade e não consulta o calendário da corretora — então
"todo excluído por `funding_missing` é atravessador" só vale para atravessamento **inferido**. Com
isso caem também: (1) "0 de 173 é tautologia" — atravessadores com histórico completo são resolvidos
normalmente, e 9 de volume foram; (2) as taxas de ~13% e ~12% e a duração média de 1 hora que eu
derivara delas; (3) a aritmética 394 + 46 = 449 — são **440**, porque os 9 já estão dentro dos 394;
(4) o encadeamento "8 h → 1 h gera `funding_missing`", que a união entre grade prevista e eventos
observados impede — o caso real é a reversão 1 h → 4 h; (5) a refutação por `interval_s` constante,
porque uma moda persistentemente errada também é constante. E acrescentou a condição que faltava para
a subestimação silenciosa: a cobrança precisa estar ausente **da nossa série** e não prevista pela
grade errada.

Correção factual dela que eu tinha errado por omissão: `interval_s` **já é persistido**
(`funding.py:59`, `settle.py:98`); o que falta é distinguir previstos, observados e ausentes.

Divergência: nenhuma. Frase dela que virou regra da nota: separar atravessamento **confirmado**,
**inferido** e **indeterminado**.

## Relacionados

[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Open Bugs]] · [[Strategies]]

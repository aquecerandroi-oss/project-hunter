---
tags: [knowledge, nota, regime, metodo]
tema: regime de mercado e volatilidade
fonte: Hamilton (1989), Econometrica — conceito, via a resenha do próprio autor para o New Palgrave e resumos secundários; e o nosso `regime/classifier.py`
fonte_url: https://econweb.ucsd.edu/~jhamilto/palgrav1.pdf (certificado expirado — **não abriu**) · https://www.r-bloggers.com/2022/02/understanding-hamilton-regime-switching-model-using-r-package/
lido_em: 2026-09-06
evidencia: estudo revisado (conceito lido em fontes secundárias; o texto primário não abriu) + leitura de código próprio
hipotese_testavel: sim
astra: pendente
---

# Hamilton e o que um limiar com histerese não é

## O que afirma

No modelo de Hamilton (1989) o regime é uma **variável latente**: ninguém observa em que estado o
mercado está. O que existe é uma cadeia de Markov com probabilidades de transição `p_ij`, e o que se
computa é a **probabilidade filtrada** de estar em cada estado dado o histórico. Duas propriedades
saem de graça e não têm equivalente num classificador de limiar:

- **duração esperada de um estado = `1 / (1 − p_ii)`**. A matriz de transição, com diagonal próxima
  de 1, é o que dá persistência ao regime — e a duração é *estimada dos dados*, não escolhida;
- **incerteza explícita**. Um dia com probabilidade filtrada 0,55 é declaradamente ambíguo. O modelo
  original supõe duração independente da idade do estado (a chance de sair não muda com o tempo já
  passado no estado), uma limitação que extensões posteriores atacaram.

## Onde foi mostrado

PIB real dos EUA do pós-guerra, frequência trimestral, para datar expansões e recessões. Desde
então virou o método padrão em ciclo econômico e foi aplicado a cripto (MS-GARCH e HMM de dois
estados para BTC aparecem em vários trabalhos de 2024-2026). Nenhum desses trabalhos entrou aqui
como evidência: só o conceito.

## Como se compara com o que nós temos

O `regime_v0` **não é** um modelo de regime nesse sentido, e é honesto dizer isso na cara:

| | Hamilton | `regime_v0` (`classifier.py`) |
|---|---|---|
| Estado | latente, probabilístico | determinístico, função de limiares |
| Persistência | estimada (`p_ii`) | imposta: 3 leituras consecutivas do **par** `{trend, volatility}` |
| Incerteza | probabilidade filtrada | `confidence` ∈ {1 · 0,75 · 0,6} **ou `None`**, e é **só** a concordância da amplitude |
| Duração | `1/(1−p_ii)`, sai do ajuste | não modelada |
| Calibração | máxima verossimilhança | declarada; o próprio docstring diz "nenhum estudo histórico embasa estes números" |

Três consequências concretas:

1. **A `confidence` do `regime_v0` não é probabilidade — e às vezes nem existe.** `_confidence`
   retorna 1 quando a amplitude concorda, 0,75 quando a amplitude não é utilizável e 0,6 quando
   discorda. Mas `_decide` (`classifier.py:167`) só a preenche quando `state_out.pair ==
   reading.pair`: **durante uma transição pendente** — a leitura já mudou, a histerese ainda não
   confirmou — a decisão sai com `confidence = None` (achado da Astra, conferido por mim). É um
   carimbo de corroboração, não uma crença; usá-la como peso probabilístico seria erro, e qualquer
   consumidor precisa tratar o nulo.
2. **"Três leituras" não são "três minutos"** (correção da Astra). O contador de `advance_regime`
   conta **leituras**, não tempo: a única leitura recusada é a que chega com `observation_ts` menor
   ou igual ao último (`REASON_STALE_OBSERVATION`). Se o scanner atrasar, três confirmações podem
   levar dez minutos; se houver refeed, podem levar menos. A cadência nominal é de 1 min
   (`docs/PIPELINE.md` §4, e o laço do `scanner-worker`), mas o classificador não a exige nem a
   verifica. Consequência: a histerese filtra tremulação **de leitura**, não uma janela de tempo, e
   não protege contra oscilação de escala horária — que é a que medimos em
   [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]].
3. **Perder a capacidade de classificar publica `UNKNOWN` na hora, sem histerese** — decisão
   deliberada e escrita no código ("a histerese protege contra tremulação, não contra cegueira").
   Isso está certo, e é uma assimetria que um modelo probabilístico não teria.

## Hipótese testável no Lab

**H-KB0029 (diagnóstica).** Assim que o classificador sair do warm-up, medir sobre as linhas de
`market_regimes`:

- número de transições por dia e **distribuição da duração** de cada par `{trend, volatility}`
  (`end_time − start_time`), separadamente por dimensão;
- fração do tempo em `UNKNOWN` e o motivo de cada entrada em `UNKNOWN`;
- quantas transições foram desfeitas dentro de 15 minutos (ida e volta).

- **Sinal de que o rótulo é utilizável:** duração mediana de uma dimensão acima de algumas horas e
  poucas idas-e-voltas.
- **Refutação:** duração mediana de minutos, ou mais de ~10% das transições revertidas em 15 min.
  Nesse caso o rótulo é ruído carimbado, e a resposta certa **não** é aumentar `confirmations` até o
  gráfico ficar bonito (isso é ajuste ao próprio ruído,
  [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]) — é medir a duração e decidir a
  escala com ela, ou trocar o classificador por um modelo de estado, que é decisão do Everton.
- **Pré-requisito:** o classificador precisa sair do warm-up. Hoje `market_regimes` tem **uma única
  linha**, `global`/`UNKNOWN` ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]).

## Por que pode falhar

- **Comparar-se com Hamilton pode virar culto ao método.** Um HMM de dois estados ajustado a poucas
  semanas de cripto acha regimes lindos e não replica; a literatura de 2024-2026 sobre HMM em BTC é
  vasta e quase toda sem validação fora da amostra. Trocar limiar declarado por modelo ajustado
  troca um viés conhecido por um desconhecido.
- **Duração medida sobre pouca amostra é enganosa.** Com 20 dias de história, durações acima de um
  dia são censuradas pela própria janela.
- **A projeção esconde transição.** `REGIME_PROJECTION` mapeia `bull+high` e `bear+high` no mesmo
  rótulo `HIGH_VOLATILITY`, então contar transições **do rótulo** subestima as transições do estado.
  Por isso a medição acima é por **par**, e o código já publica `changed` pelo par com
  `label_changed` ao lado.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Confirmou** que os limiares 2,0 / 0,5 e as três confirmações estão
corretos como eu descrevi. **Duas correções aceitas e aplicadas acima:**

1. **`confidence` também pode ser nula** durante uma transição pendente (`classifier.py:167`). Eu
   tinha listado só os três valores.
2. **Três leituras não garantem três minutos decorridos.** O contador é de leituras; a cadência de
   1 min é do pipeline, não do classificador. Isso enfraquece — e não fortalece — o argumento de que
   a histerese damping oscilação horária, que é justamente o que eu queria dizer.

**Divergência registrada:** ela alerta que comparar-se a Hamilton pode virar convite a trocar o
limiar por um HMM. A nota já dizia isso na seção de falhas e eu mantive a formulação: a comparação
existe para **nomear o que o `regime_v0` não é**, não para propor substituí-lo. Trocar o
classificador é decisão do Everton, não consequência de uma tabela comparativa.

## Relacionados

[[KB-0027-aglomeracao-de-volatilidade-o-que-ela-licencia]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Strategy Backlog]]

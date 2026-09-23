# Pesquisa — o moinho de hipóteses

Ferramenta offline em `infra/research/`. Ela roda o protocolo congelado dos estudos
R65–R69 sobre **qualquer** hipótese nova, para que testar uma ideia custe minutos em vez
de um estudo sob medida. Diretiva do Everton (23/09/2026): *"sempre testando qualquer
análise que possa se tornar válida para lucro — já coloque como principal"*.

O moinho **não** se liga à VPS, à base ou à rede: o operador exporta (CSV) e aponta o spec.

## Como adicionar uma hipótese

1. Escreva um bloco em `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md` com os seis campos:
   `origem`, `variável`, `população`, `previsão`, `refutação`, `status`. Se faltar um, o
   carregador recusa a fila inteira — de propósito.
2. Exporte a população (SQL somente-leitura na VPS → CSV local).
3. Escreva o spec (≈ 25 linhas) e rode:

```python
from infra.research.protocol import run_hypothesis
from infra.research.report import render
from infra.research.spec import (
    DecisionPolicy, HypothesisSpec, InferencePlan, ObservabilityColumns, PreRegistration,
)

spec = HypothesisSpec(
    name="H-004 — percentil de sells/buys",
    origin="R69, sobrevivente isolado da família de 17",
    loader=carrega_csv,                      # devolve list[dict]; é o único acesso a dados
    decision_instant="t",                    # coluna com o instante da decisão (UTC aware)
    outcome="ret",                           # desfecho
    variable="p_sb",                         # variável candidata
    direction="high",                        # 'high' = valores altos são os selecionados
    observability=ObservabilityColumns("as_of", "computed_at", "tape_as_of"),
    inference=InferencePlan(
        cluster="mint", stratum="day", block="hora",
        thresholds=(0.3, 0.4, 0.5, 0.6, 0.7), reps=10_000, seed=69,
    ),
    policy=DecisionPolicy(frozen_threshold=0.5, minimum_effect=0.05),
    pre_registration=PreRegistration(
        prediction="a metade alta rende mais +0,05 por SOL arriscado que a baixa",
        refutation="limite superior do IC 95 % (bootstrap de mint) abaixo de +0,01",
        decision_rule="CONFIRMA com D>0, IC inferior>0, p<0,05, D≥MRE e planalto",
        registered_on="2026-09-23",
        threshold_policy="mediana da amostra, fixada antes de olhar desfechos",
    ),
    money_column="pnl_sol",
    assumptions=("ficha de 0,05 SOL; custo de ida-e-volta 4,09 % já dentro do pnl",),
)
print(render(run_hypothesis(spec)))
```

4. Cole o relatório na nota do estudo e atualize o `status` do bloco na fila.

**Sem pré-registo o moinho não corre.** `run_hypothesis` levanta `PreRegistrationError`
antes de ler uma linha se faltar previsão, refutação, regra de decisão, data ou política
de limiar. O relatório carrega um `fingerprint` (sha256 do texto congelado): reescrever a
previsão depois de ver os números muda a impressão digital.

## Como ler o veredito

Três rótulos, e só três. **Nunca "promissor".**

| Veredito | Quando sai | O que significa |
|---|---|---|
| `CONFIRMA` | D > 0 **e** D ≥ MRE **e** IC 95 % inferior > 0 **e** p de permutação < 0,05 **e** o braço selecionado é lucrativo em nível **e** a curva é planalto **e** (se há split) a fatia de teste repete o sinal | candidato a **braço de papel pré-registado** — nunca parâmetro de mesa real |
| `REFUTA` | limite superior do IC 95 % abaixo do MRE | evidência contra uma vantagem **desse tamanho**. Não é refutação de qualquer efeito |
| `NÃO CONFIRMA` | qualquer outro caso, incluindo amostra insuficiente, poucos clusters num dos braços e IC não finito | não sabemos. Falta de potência **nunca** vira refutação |

Os três não se misturam: **não confirmação** é ignorância (IC largo, mesmo contendo zero
*e* o efeito previsto); **refutação** é sobre o **tamanho previsto**; **abandono
operacional** é decisão de fila e pode cair sobre qualquer um dos dois. Leia sempre:

- **a curva de limiares** — efeito real sobrevive a limiares vizinhos (*planalto*);
  artefato é um *pico* isolado (KB-0149 §5, item 26). Foi assim que o corte `buys_1m ≤ 25`
  do R65 se desfez no R67;
- **a ressalva que mais importa** — o relatório diz o que o limita, não só o que achou;
- **a censura** — linhas sem desfecho ou sem a variável. Ausente nunca vira zero (bug que
  o R69 apanhou: sujeito sem valor recebia percentil zero); NaN conta como ausente;
- **as suposições numéricas declaradas** — custo, tamanho da ficha, política de saída.

## Regras da casa

1. **Não girar botão das 13 variáveis já esgotadas** (R65, KB-0149 §3 item 11): snipers,
   dev share, compradores únicos, progresso, fluxo do criador, idade, volume 1 m,
   sells/buys, holders, top10, retenção, carteiras novas, flip rápido. **Nenhuma
   sobrevive** — o que não é o mesmo que refutada (KB-0149: *não confirmado ≠ refutado*).
   Uma delas só volta com **população nova** ou **medida nova**, dito no `origem` da fila.
2. **Resultado negativo é resultado.** `NÃO CONFIRMA` e `REFUTA` ficam escritos na fila e
   na nota do estudo. Hipótese morta não volta com outro nome.
3. **Nada vai ao dinheiro real sem braço de papel pré-registado.** Ligar critério novo na
   mesa real não é sombra: a proposta não nasce e não há contrafactual (KB-0149 §5,
   item 28).
4. **Escolher limiar olhando o resultado vale zero** (KB-0149 §5, item 25). O limiar é
   congelado no pré-registo, e a varredura é descrição da forma do efeito.
5. **Antecipação mente com convicção** (KB-0149 §5, item 24). A guarda de `guards.py` é
   obrigatória; a dispensa (`ObservabilityWaiver`) é permitida, escrita e aparece como
   ressalva — ela **não certifica** causalidade, declara que a guarda não correu.

## Numerário

Estatística em `float`: os contrastes são médias de retornos (~1e-2) e o erro de Monte
Carlo domina qualquer erro de representação. Dinheiro publicado em `Decimal`
(`money_column`), somado exatamente como foi persistido. Tempo sempre UTC *aware* — um
`datetime` ingénuo é recusado, porque comparar ingénuo com aware é o modo silencioso de a
guarda deixar tudo passar.

## O que o moinho ainda não faz

- **walk-forward com várias dobras** (o R68 usa treino 14 d / teste 7 d, passo 7 d): aqui
  há uma fronteira única treino/teste com purga;
- **baseline "sempre dentro"** (o R68 compara com sempre-long na mesma população): aqui é
  selecionados contra resto, com o **nível** dos dois braços publicado e
  `require_positive_level` a impedir que "perder menos" vire CONFIRMA;
- **famílias de hipóteses correndo juntas**: `stats.adjust_family` faz BH e Holm sobre uma
  família congelada, mas quem a monta é o operador, uma chamada de `run_hypothesis` por
  célula.

## Arquivos

`infra/research/`: `protocol.py` (entrada) · `spec.py` · `guards.py` ·
`stats.py`/`stats_core.py`/`resampling.py` · `verdict.py` · `results.py` · `report.py` ·
`queue.py` · `tests/`.

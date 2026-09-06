---
tags: [knowledge, nota, rompimento, volume]
tema: Momentum e rompimentos
fonte: George & Hwang, "The 52-Week High and Momentum Investing" (Journal of Finance, 2004)
fonte_url: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2004.00695.x · https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf
lido_em: 2026-09-06
evidencia: estudo revisado
hipotese_testavel: sim
astra: concorda
---

# Proximidade da máxima e confirmação por volume

## O que afirma

George & Hwang mostram que a **razão entre o preço atual e a máxima de 52 semanas** domina e melhora
o poder preditivo dos retornos passados — individuais e de indústria — para retornos futuros, e que
os lucros previstos por ela **não revertem no longo prazo**, ao contrário do momentum clássico. A
leitura teórica dos autores é forte: momentum de curto prazo e reversão de longo prazo seriam
fenômenos **separados**, e não duas fases de uma mesma reação à notícia. A carteira é montada
comprando o decil/tercil superior e vendendo o inferior, mantida 6 ou 12 meses.

Sobre "rompimento com volume acima da média tem mais continuação": procurei e o que apareceu foi
material comercial com números de taxa de acerto que não têm origem verificável. **Não registro
esses números.** O que fica é a ideia qualitativa, sem evidência que eu tenha lido.

## Onde foi mostrado

Ações americanas, ordenação **transversal**, formação mensal, manutenção de 6 a 12 meses. Nada de
cripto, nada de perpétuo, nada de 15 minutos, nada de LONG isolado.

**Extrapolação que precisa ficar declarada:** aplicar a ideia a máximas de 24 horas, decisões de 15
minutos e posições LONG em perpétuos é **hipótese nova**. O artigo não valida este limiar, não
valida confirmação por volume e não diz nada sobre reversão intradiária — a ausência de reversão que
ele documenta é resultado do contexto que ele estudou.

## Como mediríamos aqui

A `momentum_v1` rompe a **máxima dos 20 fechamentos** anteriores de 15 minutos — 5 horas de
histórico, e só de fechamentos (`packages/core/hunter_core/strategies/indicators.py`). A feature
`distance_from_24h_high` é outra coisa: usa **máximas intrabar** de 1.440 minutos, incluindo a vela
final (`packages/indicators/hunter_indicators/features/price.py`), e divide pela própria máxima.

Não é implicação lógica que uma satisfaça a outra. Contraexemplo aritmético: máximo dos fechamentos
anteriores 100, fechamento atual 101, máxima intrabar de 24 h 105 → há rompimento, e
`distance_from_24h_high = (101 − 105)/105 = −3,81%`, que reprova num limiar de −0,5%. Além das 19
horas extras de janela, o filtro estaria selecionando também **menor rejeição por pavio**.

Nota de precisão sobre o `rvol` que já usamos: ele é volume dividido pela **mediana** das 96 barras
anteriores, não pela média (`indicators.py`). Quem escrever "volume acima da média" no projeto está
descrevendo outra coisa.

## Hipótese testável no Lab

`momentum_v5_near_high` — idêntica à `momentum_v1`, com **uma** alteração: exigir
`distance_from_24h_high ≥ −0,005` na decisão (preço a no máximo 0,5% abaixo da máxima de 24 h).
`rvol_min` fica em 1,5 justamente para **isolar** a contribuição da proximidade — esta candidata
**não** testa o benefício do volume.

**Antes de abrir a coorte, medir a redundância.** É barato e evita gastar dias de sombra num filtro
que aprova 100% dos sinais. O problema: o envelope atual da `momentum_v1` **não persiste**
`distance_from_24h_high` (as evidências gravadas são fechamento, máximo dos fechamentos, volume e
ATR — `momentum_v1.py`). Consultar a chave e tratar `NULL` como reprovação rejeitaria falsamente
todos os sinais já emitidos. Então: primeiro contar cobertura, com a extração correta sobre a lista
de evidências (`envelope.py`):

```sql
jsonb_path_query_first(
  supporting_features,
  '$.features[*] ? (@.name == "distance_from_24h_high" && @.available == true).value'
) #>> '{}'
```

e, onde não houver, reconstruir pelas 1.440 velas finais contíguas até `observation_ts`, **sem usar
informação posterior**, classificando o resultado como análise retrospectiva e registrando gaps e
cobertura. Reportar: total de sinais, distância disponível/indisponível, **retenção = aprovados ÷
sinais com distância válida**, quantis da distância, e retenção por mercado, por dia UTC e por faixa
de ATR e de RVOL. Para separar "janela maior" de "menos pavio", comparar quatro máximos: de
**fechamentos** em 5 h e 24 h, e de **highs** em 5 h e 24 h.

Refutação: com `δ` pré-registrado e IC95% por blocos temporais sobre `Δ = E_v5 − E_v1`, medidos em
coortes **simultâneas** (filtrar sinais antigos não reproduz a política inteira: mudar a condição
muda o rearme e os sinais posteriores — `episodes.py`).

## Por que pode falhar

- **Retenção próxima de 100%**: o filtro não faz nada nesta população. Isso não prova ausência de
  informação, só que aqui ele não separa.
- **Limiar arbitrário.** −0,005 é escolha experimental. A alternativa normalizada por volatilidade,
  registrada explicitamente como variante e não como melhoria, é `gap_atr = (H24 − close) / ATR`,
  aprovando `gap_atr ≤ k` — com `k` também arbitrário. Atenção à conversão: para distância `d` e
  `a = ATR/close`, o equivalente exato é `−d / ((1+d)·a)`, **não** `−d/a`, porque a distância divide
  pela máxima e não pelo fechamento.
- **Extrapolação de horizonte e de desenho** (mensal, transversal, ações, long-short → intradiário,
  série temporal, cripto, só long).
- Mais uma variante na conta de tentativas
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

## Segunda opinião (Astra)

Concorda em manter `rvol_min` fixo para isolar a proximidade, e em não atribuir validação acadêmica
ao filtro. Correções aceitas e incorporadas: (1) "informação diferente" não é "informação
independente" nem "poder preditivo adicional"; (2) a diferença fechamentos × highs intrabar é
material e gera o contraexemplo acima — o filtro pode estar comprando "menos pavio", não "mais
janela"; (3) o envelope da v1 **não** guarda a distância, e tratar ausência como reprovação
produziria rejeição falsa de todos os sinais já emitidos — daí a consulta de cobertura antes de
tudo; (4) a conversão percentual → ATR não é `−d/a`; (5) precisão editorial: `rvol` usa **mediana**,
não média; (6) o texto exato da extrapolação a declarar.

Divergência: nenhuma. Ela preferiria manter −0,005 como hipótese original e registrar o `gap_atr`
como alternativa; foi o que ficou.

## Relacionados

[[Strategy Backlog]] · [[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] · [[EXP-0001-momentum-v1]] · [[Features]]

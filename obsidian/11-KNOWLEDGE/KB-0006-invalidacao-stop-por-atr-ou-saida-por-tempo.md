---
tags: [knowledge, nota, saida, invalidacao, candidata-1]
tema: Momentum e rompimentos
fonte: Síntese própria sobre o dado do Lab (EXP-0001) à luz de Kaminski & Lo (2014) e de Bailey, Borwein, López de Prado & Zhu (2015); regra de invalidação em `.claude/state/notes-S1.md` §6
fonte_url: https://www.sciencedirect.com/science/article/abs/pii/S138641811300030X · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
lido_em: 2026-09-06
evidencia: replicado (dado próprio, 1 dia, inconclusivo por limiar editorial)
hipotese_testavel: sim
astra: concorda
---

# Valor incremental da invalidação (candidata #1 do backlog)

> Nome anterior no backlog: "momentum v2 com invalidação menos agressiva". **Renomeada**: aquele
> nome já anunciava a direção vencedora antes do teste.

## O que afirma (e o que o número **não** afirma)

Na avaliação da VPS de `as_of = 2026-09-06T13:00:00Z` registrada em [[EXP-0001-momentum-v1]], entre
os **91** acompanhamentos avaliáveis com `R_net` conhecido e horizonte maturado: 36 terminaram em
`target` (média +0,8258 R), 31 em `stop` (média −1,1296 R) e **24 em `invalidated` (média −0,5768 R,
soma −13,8430 R)**. A expectancy líquida hipotética foi −0,2102 R.

A leitura tentadora é "a invalidação custa 13,84 R". **É errada, e o texto abaixo é o que deve ser
citado quando alguém repetir isso:**

> Na avaliação de 2026-09-06T13:00:00Z, 24 dos 91 acompanhamentos avaliáveis com R líquido conhecido
> terminaram por invalidação, somando −13,8430 R. Essa soma descreve resultados **sob a política
> vigente**. Ela **não** mede o efeito de invalidar: sem essa saída, os mesmos acompanhamentos
> continuariam até alvo, stop ou expiração, com resultado líquido desconhecido. O efeito da mudança
> exige comparar, **para cada entrada**, o resultado da política alternativa com o resultado da
> política atual.

Formalmente, com `I` = os 24 episódios que a política atual encerrou por invalidação, o que interessa
é `Δ = (1/24)·Σ_{i∈I} (R_i^alternativa − R_i^atual)` — o **ganho incremental de continuar**, que é
coisa diferente do resultado posterior da operação. Continuar pode terminar no prejuízo e ainda
assim melhorar a política atual; e pode recuperar um pouco e depois perder muito mais.

Aritmética que ajuda a calibrar a expectativa (conferida, mantendo os outros 67 fixos):
substituir os 24 por **zero** deixaria a média em **−0,0581 R** — mas isso é **imputação**, não
consequência da remoção. Para a amostra empatar em zero, os 24 teriam de terminar em média em
**+0,22035 R**, ou seja, uma melhoria de cerca de **+0,80 R por episódio invalidado**. Nem a média
dos stops nem a dos targets identifica o que esses 24 fariam.

Correção de denominador que já vale para citações futuras: **0,5333 = 40/75**, contando toques
resolvidos **sem** `R_net` também; os 91 com R conhecido contêm 36 targets e 31 stops. Não usar
0,5333 como taxa dos 67.

## Onde foi mostrado

Um único dia (2026-09-06), 134 mercados que se movem juntos, dependência entre observações
simultâneas não estimada. Pelo limiar editorial (100 outcomes **e** 30 dias) o `Result` da avaliação
é **inconclusivo**, e é assim que ele deve ser citado.

## Como mediríamos aqui

A regra atual é: um fechamento de 15 minutos abaixo do nível de rompimento `L`
(`packages/core/hunter_core/strategies/momentum_v1.py`), com saída na **abertura seguinte**
(`walker.py`) e prioridade `stop > target > expired > invalidated`. Stop e alvo partem do
**fechamento de referência**, não da entrada.

## Hipótese testável no Lab

**Quatro braços, três contrastes primários.** Todos preservam entrada, stop inicial, alvo, horizonte
de 4 h e modelo de custos — só a regra de invalidação muda. Prefixo `INV-` para não colidir com os
braços `STOP-` de [[KB-0005-stops-quando-eles-param-perdas]].

| Braço | Regra | Pergunta que responde |
|---|---|---|
| `INV-A` | um fechamento de 15 min abaixo de `L` (atual) | referência |
| `INV-B` | **sem** invalidação; mantém stop, alvo e horizonte | a regra inteira acrescenta valor? |
| `INV-C` | **dois** fechamentos consecutivos distintos abaixo de `L` | uma quebra isolada é ruído? |
| `INV-E` | um fechamento abaixo de `L − 0,25 × ATR₀` | uma quebra **rasa** é ruído? |

`INV-C` e `INV-E` separam duas coisas que a proposta original misturava: **persistência temporal** e
**profundidade da quebra**. A variante de carência (invalidar só depois de N barras) fica **fora**
desta rodada: ela exige a hipótese mais específica de que a invalidação só atrapalha na acomodação
inicial, e a média de −0,58 R não dá essa evidência. Se um dia entrar, é com carência fixa (p. ex.
30 min desde a entrada), avaliando só fechamentos posteriores, sem carregar gatilhos anteriores e
sem ambiguidade entre "barras completas" e "fechamentos atravessados".

Semântica congelada: `ATR₀` é o valor da decisão, **nunca recalculado** depois da entrada; se
`L − 0,25·ATR₀` cair abaixo do stop, registrar a redundância em vez de deslocar o stop em silêncio.
Em `INV-C`, um fechamento ≥ `L` zera a sequência, reentrega não conta como segundo fechamento, gap
continua sendo indisponibilidade, e a saída é na abertura seguinte à confirmação. **0,25 ATR é
parâmetro inicial proposto, sem evidência de otimalidade.**

**Pré-registro:**

- Métrica primária: média das **diferenças líquidas pareadas**, com o denominador
  `entrada − stop inicial` **fixo** nos quatro braços (`pricing.py`).
- Efeito mínimo relevante `δ = 0,05 R por entrada`, definido antes de olhar a avaliação futura.
- Família: três testes unilaterais `H₀: Δ ≤ δ` (B−A, C−A, E−A) com correção de Holm a 5% —
  p-valores ordenados e comparados sequencialmente com 0,0167; 0,025; 0,05, parando na primeira não
  rejeição. Holm admite dependência entre os testes. Quatro braços sobre os **mesmos** episódios não
  quadruplicam a amostra.
- Incerteza: reamostragem em blocos temporais mantendo juntos **todos os mercados e todos os
  braços**, preservando janelas sobrepostas; tamanho de bloco e método congelados antes da
  validação. **Um dia não sustenta essa estimação.**
- Calendário fixo em UTC, uma única análise inferencial após a maturação da última entrada. Leituras
  diárias são descritivas; não se encerra o experimento quando aparece significância.
- Reportar pior decil de R e duração adicional exposta. Melhora de média com piora relevante de
  cauda é decisão explícita, não vitória.
- Os 100 outcomes e 30 dias continuam sendo **piso editorial, não cálculo de potência**.

**Ramificação por entrada, não por estratégia.** O experimento primário ramifica **cada entrada
efetiva de `INV-A`** nos quatro braços. Motivo: hoje o encerramento libera o acompanhamento
(`outcomes.py`) e o rearme depende da condição ficar falsa (`episodes.py`); se `INV-A` invalida,
rearma e entra de novo enquanto `INV-B` segue na primeira operação, a diferença entre as médias
mistura **saída** com **seleção de entradas**.

**Cobertura não pode escolher o vencedor.** Na leitura citada há 105 avaliáveis maturados, 14 sem
`R_net` (funding) e 91 com R conhecido. Um braço que fica aberto mais tempo tem mais chance de
atravessar funding ou buraco de dados e ficar sem resultado. Então: população pré-registrada pela
entrada e pelo horizonte, cobertura reportada **por braço**, diferenças calculadas só com pares
disponíveis e a estimativa declarada como **condicionada à cobertura**; os 14 excluídos aparecem, e
funding desconhecido **nunca** vira zero.

## O que o replay pode e o que não pode responder

Replay sobre as velas de 1 min já no banco responde parte disto **agora**, sem esperar 30 dias, na
ordem: (1) reproduzir `INV-A` a partir das entradas, níveis, custos e horários persistidos, conferindo
saída, preço e R contra o registro; (2) reexecutar desde a entrada nos quatro braços, exigindo velas
finais contíguas até o encerramento necessário, incluindo a abertura de expiração e o funding
aplicável; (3) gravar como `replay:<run_id>`, ligado à entrada original, **sem nunca sobrescrever**
outcome prospectivo (já previsto em `docs/plans/SHADOW-LAB.md`).

**Pode:** dizer o que cada política teria produzido nesses caminhos de preço sob o modelo por
barras, inclusive depois do ponto de invalidação; revelar se o efeito depende de dois casos
excepcionais; medir o tempo adicional exigido e onde falta dado.

**Não pode:** transformar o dia que gerou a hipótese em confirmação independente; descobrir a ordem
real de stop e alvo dentro de uma vela de 1 min (mantém-se a convenção pessimista, com sensibilidade
reportada); demonstrar fill, liquidez ou slippage reais; reconstruir a disponibilidade histórica de
dados só porque houve backfill depois; medir a **estratégia completa** usando apenas as entradas
emitidas por `INV-A` — para isso seria preciso reconstruir sinais potenciais, rearme e o universo
histórico, e o próprio código avisa que a composição atual do universo não prova a passada
(`services/strategy-worker/hunter_strategy_worker/config.py`).

## Por que pode falhar

- **Ler atribuição contábil como efeito causal** — o erro que esta nota existe para impedir.
- **Cenário concreto que refuta o afrouxamento:** o preço perde o nível, `INV-A` encerra em −0,58 R e
  `INV-B` continua até um stop pior. Apagar contabilmente a perda de `INV-A` fabricaria melhoria.
- **Escolher parâmetros depois de olhar o resultado.** Testar 0,25 ATR e depois 0,5 e depois 1,0
  amplia a busca e é exatamente a fonte de sobreajuste que Bailey et al. descrevem
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- Um dia de dado, mercados correlacionados, e nenhuma estimativa de dependência.

## Segunda opinião (Astra)

Confirmou a leitura de que −13,8430 R é **atribuição contábil, não efeito**, e conferiu a aritmética
(24/91 = 0,2637; média imputando zero = −0,0581; os 24 precisariam de +0,22035 em média;
1 − 0,95³ = 0,1426 como ilustração de multiplicidade sob independência, que aqui não vale porque os
contrastes são dependentes). Mudanças aceitas: substituir a variante de carência por `INV-E` (buffer
de 0,25 ATR), porque `INV-C` e `INV-E` separam persistência de profundidade; ramificar por entrada e
não por estratégia; tratar cobertura por braço como parte do desenho; Holm a 5% sobre três testes
unilaterais com `δ = 0,05 R`; não remover o stop nem mexer no horizonte nesta candidata; corrigir o
denominador de 0,5333; renomear a candidata para "valor incremental da invalidação"; e usar
identificadores de braço próprios por experimento — o que me fez renomear os braços de
[[KB-0005-stops-quando-eles-param-perdas]] para `STOP-A/B/C`.

Divergência: nenhuma.

## Relacionados

[[Strategy Backlog]] · [[EXP-0001-momentum-v1]] · [[KB-0005-stops-quando-eles-param-perdas]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Strategy Performance]]

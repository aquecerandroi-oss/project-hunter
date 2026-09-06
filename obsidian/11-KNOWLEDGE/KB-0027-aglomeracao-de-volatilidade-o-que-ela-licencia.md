---
tags: [knowledge, nota, regime, volatilidade]
tema: regime de mercado e volatilidade
fonte: Engle (1982) e Bollerslev (1986) — via a documentação do V-Lab (NYU Stern); Cont (2001), "Empirical properties of asset returns"; Andersen & Bollerslev (1998), IER 39(4):885-905
fonte_url: https://vlab.stern.nyu.edu/docs/volatility/GARCH · https://www.semanticscholar.org/paper/b674f1384a95948d52018d1748e7284ef566233c · https://econpapers.repec.org/RePEc:ier:iecrev:v:39:y:1998:i:4:p:885-905
lido_em: 2026-09-06
evidencia: estudo revisado (lido em documentação institucional e em resumo, não no original)
hipotese_testavel: sim
astra: pendente
---

# Aglomeração de volatilidade: o que ela licencia (e o que não)

## O que afirma

A magnitude dos retornos é **persistente**; o sinal deles, não. Retornos grandes tendem a ser
seguidos de retornos grandes, de qualquer sinal, e retornos pequenos de retornos pequenos — o fato
estilizado que Engle formalizou com o ARCH (1982) e Bollerslev generalizou com o GARCH (1986). Na
forma canônica `σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁`, `α` é a reação ao choque de ontem e `β` é a memória;
a soma `α + β` é a **persistência**, e a exigência `α + β < 1` é o que garante que a volatilidade
reverte para a média de longo prazo `ω / (1 − α − β)` em vez de explodir. A documentação do V-Lab
descreve `β` perto de 0,9 como choques que duram semanas, e `α` perto de 0,2 como reação abrupta.

Duas consequências que importam mais que o modelo:

1. **A volatilidade é previsível num grau que o retorno não é.** Cont registra que a autocorrelação
   dos retornos ao quadrado (ou absolutos) permanece positiva e decai devagar, significativa por
   dias e às vezes semanas, enquanto a autocorrelação do próprio retorno morre quase imediatamente.
2. **A crítica de que "os modelos de volatilidade preveem mal" era um erro de régua.** Andersen &
   Bollerslev (1998) mostraram que o R² baixo das regressões de previsão diária vinha de usar o
   retorno diário ao quadrado como proxy da volatilidade realizada — um estimador ruidoso demais.
   Medida contra a volatilidade realizada construída a partir de retornos intradiários, a previsão
   é boa. Li o argumento em resumo; **o PDF voltou binário ilegível** e os números do artigo não
   entraram nesta nota.

## Onde foi mostrado

Séries diárias e intradiárias de ações, índices e câmbio, de 1982 em diante; Andersen & Bollerslev
usam câmbio com dados intradiários. Nada disso é cripto, nada disso é perpétuo, e nada disso inclui
custos — é estatística descritiva da série de preços, não uma estratégia.

## Como mediríamos aqui

Nós já temos o estimador: `regime/series.py` calcula o **retorno absoluto médio de 1 minuto** numa
janela de 60 retornos, uma amostra por hora UTC completa, e usa a **mediana de 30 dias** como escala
(`volatility_reference`). Isso é, na prática, uma volatilidade realizada de baixa frequência — e o
insumo natural para medir persistência sem escrever modelo nenhum:

- autocorrelação da série de amostras horárias nos atrasos 1 a 48 h;
- **razão de variâncias, escrita corretamente** — a Astra derrubou a primeira versão desta linha,
  que usava a escala errada. Sob independência, a variância da **média** de `n` amostras é
  `Var(uma)/n`; o teste é `n × Var(média de n) / Var(uma)`, igual a 1 sob independência e **maior**
  que 1 sob memória positiva. O que eu tinha escrito multiplicava `Var(uma)` por `n`, que é a escala
  da **soma**, não da média;
- meia-vida empírica: quantas horas até a autocorrelação cair para metade do valor no atraso 1.

Nada disso exige GARCH. E nada disso deve virar feature: o número que já publicamos
(`volatility_ratio`) é o que os consumidores leem.

## Hipótese testável no Lab

**H-KB0027 (diagnóstica, não é variante de estratégia).** Sobre as amostras horárias do BTCUSDT:
a autocorrelação do retorno absoluto médio horário é positiva e significativa em atrasos de pelo
menos 3 horas, e a autocorrelação do **retorno com sinal** da mesma hora não é distinguível de zero.

- **Confirmação:** ρ(1) > 0 com intervalo que exclui zero, ρ decaindo devagar até ≥ 3 h, e ρ do
  retorno com sinal contendo zero em todos os atrasos.
- **Refutação — e ela precisa de poder, não só de um intervalo que contém zero (correção da Astra):**
  "não detectamos persistência" e "provamos que é ruído" são afirmações diferentes. Com 47 amostras
  o erro-padrão aproximado de ρ é ~`1/√n` ≈ 0,15, então qualquer ρ abaixo de ~0,3 é indistinguível
  de zero **por falta de amostra**. A refutação só vale se declarada assim: "ρ(1) = X com `n`
  amostras e poder Y para detectar ρ = 0,2". Sem isso o resultado é `inconclusivo`. Se for mesmo
  ruído, o `volatility_ratio` publicado não descreve estado nenhum, e a histerese de 3 leituras
  estaria suavizando algo que não tem estrutura.
- **Pré-requisito, e ele é grande:** a série mal existe. Em 2026-09-06 o banco local tem **47 horas
  completas de BTCUSDT em 3 dias distintos** — insuficiente para qualquer estimativa de atraso longo
  ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]).

## Por que pode falhar

- **Transferência de mercado e de escala.** Todos os números da literatura são de ações e câmbio, em
  frequência diária ou intradiária de mercados com pregão. Cripto é 24/7, e o efeito de relógio que
  medimos em [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] contamina qualquer
  autocorrelação horária: um ciclo diurno **produz** autocorrelação positiva em atraso 24 h sem
  nenhuma memória de choque. Sem remover a sazonalidade, a persistência medida é parcialmente o
  relógio.
- **Persistência de magnitude não é previsão de retorno.** Saber que amanhã será volátil não diz o
  lado. A tentação — "estamos em regime de alta volatilidade, então opere assim" — é um salto que
  esta nota explicitamente não autoriza; o que a literatura autoriza é **dimensionar** posição pela
  volatilidade prevista ([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]).
- **Estimador ≠ modelo.** O nosso retorno absoluto médio é robusto e exato em `Decimal`, mas não é
  uma variância; comparar a sua persistência com valores de `α + β` publicados seria comparar coisas
  diferentes.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`astra.sh ask KB-0027-29-regime`). **Duas correções aceitas e aplicadas
acima:**

1. **Erro de escala na razão de variâncias.** Eu havia escrito "variância da média de 24 amostras
   contra 24× a variância de uma" — a Astra apontou que isso divide a variância de uma **média**
   por uma escala que é da **soma**. Corrigido no texto.
2. **A refutação confundia ausência de evidência com evidência de ausência.** Exigi agora poder
   declarado e tamanho de amostra junto do ρ.

**Concordância:** a separação entre "magnitude é previsível" e "direção não é" é o ponto central da
nota e ela a manteve. **Registro de método:** esta execução do Codex terminou com código 0 mas
**não escreveu** o arquivo `.claude/state/astra-review-KB-0027-29-regime.md`; a revisão foi lida do
traço em `astra-stderr.log`. Falha da ferramenta, não da revisão — anotada para não virar hábito
citar revisão sem artefato.

## Relacionados

[[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]] ·
[[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[Strategy Backlog]] · [[Registro de Tentativas]]

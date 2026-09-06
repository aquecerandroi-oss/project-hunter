---
tags: [knowledge, nota, backtest, estatistica, protocolo]
tema: Estatística de backtest (overfitting, look-ahead, custos)
fonte: Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest Overfitting" (Journal of Computational Finance, 2015) e "Pseudo-Mathematics and Financial Charlatanism" (Notices of the AMS, 2014); Bailey & López de Prado, "The Deflated Sharpe Ratio" (2014)
fonte_url: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253 · https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
lido_em: 2026-09-06
evidencia: estudo revisado
hipotese_testavel: não (é regra de protocolo, não candidata de estratégia)
astra: concorda
---

# Overfitting de backtest e o preço de cada variante

## O que afirma

**PBO** (probabilidade de sobreajuste de backtest), estimada por validação cruzada
combinatoriamente simétrica (CSCV), mede a frequência com que a configuração **vencedora dentro da
amostra** fica **abaixo da mediana fora dela**. O **Deflated Sharpe Ratio** ajusta a significância do
Sharpe pelo número de tentativas, pelo tamanho amostral e pela não normalidade dos retornos — mas
**não** corrige automaticamente dependência temporal.

O exemplo que virou slogan precisa ser enunciado com as condições, senão vira folclore: com
**aproximadamente 45 configurações independentes**, **cinco anos** de dado e **Sharpe verdadeiro
zero**, sob retornos i.i.d. normais e a aproximação do artigo, o **máximo esperado** do Sharpe
anualizado **dentro da amostra** chega a cerca de 1,0 — com Sharpe esperado **fora da amostra** igual
a zero. Não é "45 tentativas garantem Sharpe 1"; é o valor **esperado do máximo**. E o comprimento
mínimo de backtest (MinBTL), que depende do número de tentativas e do Sharpe de referência, é coisa
distinta do MinTRL, o comprimento necessário para testar um Sharpe individual contra um limiar com
confiança dada.

## Onde foi mostrado

Resultado analítico e de simulação, sob hipóteses declaradas (i.i.d., normal), com aplicações a
estratégias reais. Não é resultado de mercado; é resultado sobre **procedimento de busca** — e é por
isso que vale para nós mesmo sem nada em comum com o nosso universo.

## Como mediríamos aqui

**Não medimos: obedecemos.** Esta rodada de conhecimento produziu, sozinha, **seis** candidatas de
variante sobre a **mesma** população de mercados e dias: gate de tendência
([[KB-0001-momentum-academico-e-o-que-nao-se-transfere]]), impulso excessivo
([[KB-0002-momentum-e-reversao-em-cripto]]), família 10/20/40 de lookback
([[KB-0003-rompimento-de-canal-e-data-snooping]]), proximidade da máxima
([[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]]), quatro braços de invalidação
([[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]), piso de custo
([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]) e atraso de execução
([[KB-0009-o-efeito-do-quarto-de-hora]]). Somando os braços, já passamos de uma dezena de tentativas.

**Sem carteira não há Sharpe, e sem Sharpe não há DSR.** O Lab mede expectancy líquida em R por
entrada, não série de retornos de carteira. `média(R)/desvio(R)` pode ser estudado como efeito
padronizado por entrada, mas aplicar DSR direto **não** valida a média em R nem produz Sharpe de
carteira. O que é defensável:

- Hipóteses **pré-especificadas** sobre expectancy líquida ou sobre a diferença frente à referência.
- **Bootstrap conjunto em blocos temporais**, preservando mercados simultâneos **e** a dependência
  entre variantes.
- p-valores válidos **mais** Holm. Holm aceita dependência entre testes, mas **não conserta p-valor
  inválido**.
- Para intervalos **simultâneos**, procedimento próprio (por exemplo Bonferroni sobre ICs por
  blocos). **Seis ICs individuais de 95% não são intervalos simultâneos.**
- E o limite duro: se as seis candidatas nasceram da **inspeção destes mesmos resultados**, Holm
  sobre as seis **não apaga a seleção adaptativa**. A confirmação exige **dados futuros
  reservados**.

O limiar editorial de 100 outcomes e 30 dias continua sendo **piso, não cálculo de potência**.

## Regra de protocolo adotada

Registro **append-only** de tentativas em [[Registro de Tentativas]], nesta pasta. Cada variante
entra **antes** de rodar, com: ID, hipótese, parâmetros e `δ`, hashes de código, população, custos,
métrica primária, família de testes, início e fim em UTC, regra de maturação e regra de análise.
Entram também as **descartadas**, e o registro distingue *candidatas propostas* de *tentativas
efetivamente avaliadas*, informando o total acumulado. Nenhuma variante é avaliada antes da data de
fim declarada, e todo relatório de variante cita o total de tentativas até ali.

**Verificabilidade — e o limite dela.** O registro sozinho é teatro se ninguém puder checar que foi
escrito antes. O que torna o compromisso verificável: publicar o registro no remoto **antes do
início da janela futura**, com o SHA vinculado a um evento de PR/CI **datado pelo servidor**; branch
protegida contra reescrita e exclusão; CI que recuse alteração de registros anteriores, aceitando
correções apenas como **novos eventos**. Data local de commit é ajustável e assinatura sozinha não
prova anterioridade. Mesmo assim, isso comprova **o compromisso publicado**, não a inexistência de
testes privados omitidos — e essa limitação fica escrita, em vez de sugerida.

## Por que pode falhar

- **Contar tentativas só das que reportamos.** Toda variante cogitada e abandonada por parecer ruim
  no dado já visto é uma tentativa.
- **Confundir CSCV com nosso caso.** CSCV pressupõe uma matriz de desempenho por configuração e por
  subperíodo; com um dia de dado não há subperíodo nenhum.
- **Achar que rigor estatístico substitui dado novo.** Não substitui: a única cura para seleção
  adaptativa é período futuro reservado.
- **Justificativa econômica como álibi.** "O piso de custo tem razão econômica" não devolve
  independência à amostra que revelou o problema
  ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]).

## Segunda opinião (Astra)

Confirmou o enunciado com três precisões, todas incorporadas: PBO via CSCV é a frequência com que a
vencedora dentro da amostra cai abaixo da mediana fora dela; DSR não corrige dependência temporal;
e o exemplo correto é **≈45 configurações independentes, 5 anos, Sharpe verdadeiro zero, retornos
i.i.d. normais**, com o **máximo esperado** do Sharpe dentro da amostra chegando a ≈1 — não uma
garantia — além da distinção MinBTL × MinTRL. Sobre o análogo do DSR: não aplicar DSR à expectancy
em R; usar hipóteses pré-especificadas, bootstrap conjunto em blocos, p-valores válidos com Holm e
procedimento próprio para ICs simultâneos, lembrando que Holm sobre seis candidatas nascidas da
inspeção **não** apaga a seleção adaptativa. Sobre o registro: ajuda, não resolve sozinho — e ela
detalhou o mecanismo de verificabilidade (publicação remota antes da janela, SHA em evento datado
pelo servidor, branch protegida, CI que recusa alteração), com o limite explícito de que nada disso
prova ausência de testes privados.

Divergência: nenhuma.

## Relacionados

[[Registro de Tentativas]] · [[Strategy Backlog]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[Strategy Performance]] ·
[[Experiments Index]]

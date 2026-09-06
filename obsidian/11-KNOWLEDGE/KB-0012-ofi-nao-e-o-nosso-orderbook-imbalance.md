---
tags: [knowledge, nota, microestrutura, book, fluxo]
tema: Volume e fluxo de ordens
fonte: "Cont, Kukanov & Stoikov (2014), The Price Impact of Order Book Events, Journal of Financial Econometrics 12(1) 47–88 (arXiv:1011.6402); Cont, Cucuringu & Zhang (2023), Cross-Impact of Order Flow Imbalance in Equity Markets, Quantitative Finance (arXiv:2112.13213)"
fonte_url: https://arxiv.org/abs/1011.6402
lido_em: 2026-09-06
evidencia: estudo revisado (dois artigos publicados), lido pelo resumo/abstract — corpo completo não aberto
hipotese_testavel: sim
astra: concorda com correções (candidata H-KB0012b retirada)
---

# OFI não é o nosso `orderbook_imbalance_20`

## O que afirma

Cont, Kukanov & Stoikov definem **Order Flow Imbalance (OFI)** como o desequilíbrio entre oferta e
demanda **no topo do book**, construído a partir dos **eventos** que alteram as filas de melhor
compra e melhor venda: entradas, cancelamentos e execuções, cada uma com sinal. É um **fluxo**,
medido entre dois instantes. A variação de preço no mesmo intervalo é **linear** em OFI, com
inclinação **inversamente proporcional à profundidade** do book — book raso, mesmo fluxo, movimento
maior. O ajuste é forte (R² médio da ordem de **65%**, tabela 2 do artigo), estável entre escalas de
tempo, entre ações e robusto à sazonalidade intradiária. Os próprios autores enquadram o resultado
como **contemporâneo**: OFI **explica** a variação já ocorrida no intervalo, e o artigo não reivindica
previsão. A relação "raiz quadrada" entre variação de preço e volume negociado aparece, no mesmo
teste, como mais ruidosa e menos robusta que a de OFI.

Cont, Cucuringu & Zhang estendem: integrar o OFI dos **vários níveis** do book num único fator
explica impacto melhor que só o topo; depois disso, termos de **impacto cruzado contemporâneo** entre
ativos não acrescentam poder explicativo; mas OFIs cruzados **defasados** melhoram a **previsão** de
retornos, e esse efeito vive em horizontes curtos e **decai rápido**.

## Onde foi mostrado

CKS: NYSE TAQ, 50 ações americanas, dados de eventos de book, **intervalos de 10 segundos** com
agregações verificadas até **10 minutos**. CCZ: ações americanas, book multinível, previsão em
**1 minuto** e horizontes de **2 a 30 minutos**. Ambos em ações; nenhum dos dois inclui funding, ADL
ou liquidação forçada. A transferência para perpétuo de cripto é plausível pelo mecanismo (fluxo
agressor contra profundidade), mas **não demonstrada por estes dois artigos**.

## Como mediríamos aqui

**A correção conceitual é o núcleo desta nota.** O que temos não é OFI:

| Nome | O que é | Onde |
|---|---|---|
| `orderbook_imbalance_20` | `(qtd_bid − qtd_ask) / (qtd_bid + qtd_ask)` sobre os **20 melhores níveis de cada lado**, de **um snapshot** | `packages/indicators/hunter_indicators/features/micro.py:114-155` |
| OFI (CKS) | soma **assinada das variações** das filas do topo entre dois instantes | não existe no nosso conjunto |

São grandezas diferentes: a nossa é um **estado** (quanto papel está parado de cada lado agora), a
deles é um **fluxo** (quanto papel entrou, saiu e foi executado desde a leitura anterior). Dois
snapshots consecutivos com 1000 no bid e 1000 no ask têm imbalance 0 nos dois instantes observados, e
entre eles pode ter havido OFI enorme — cancelamentos, entradas e execuções que se compensaram no
total. Chamar o nosso de OFI numa página, num brief ou num relatório seria erro factual, e é o tipo
de erro que se propaga para uma conclusão.

Restrições reais da nossa feature, todas no código:

- exige **20 níveis de cada lado**; com menos, devolve `insufficient_sample` em vez de um número
  sobre contagem de níveis (`micro.py:141-147`);
- recusa book cruzado como `corrupt_input` (`usable_book`, `micro.py:56-79`);
- não tem sufixo `_live` porque lê snapshot, não vela, e carrega a idade do snapshot na proveniência
  — um book de 40 s é `degraded`.

Construir OFI de verdade não exige guardar deltas completos — exige **observar a sequência de
atualizações** e acumular incrementalmente a partir do estado anterior. O obstáculo aqui é outro: o
nosso caminho guarda o snapshot top-20 numa **chave sobrescrita**
(`services/market-worker/hunter_market_worker/hot_state.py:175`), então o estado anterior não
sobrevive e nenhum evento intermediário é recuperável depois. Snapshots espaçados **não** reconstroem
os eventos entre eles. É requisito de observação contínua, não de armazenamento de deltas.

## Hipótese testável no Lab

**H-KB0012a (diagnóstica) — e é a única coisa que estas fontes justificam pedir agora.** A
`volume_anomaly_v1` **não** consulta o book: o envelope do sinal (`volume_anomaly_v1.py:198`) não
carrega `orderbook_imbalance_20`. Então a primeira pergunta é de cobertura, não de edge: **quantos
vetores de feature publicam `orderbook_imbalance_20` como disponível até o instante da decisão**, com
que idade de snapshot, e separando **ausência de histórico** de **feature indisponível** (livro fino,
`insufficient_sample`; livro cruzado, `corrupt_input`; sem book, `missing_input`). Sem essa medição,
qualquer variante que dependa do book é especulação sobre um dado que talvez não esteja lá na hora
certa.

**H-KB0012b — proposta e retirada nesta mesma nota, com o motivo escrito.** Eu havia proposto um
filtro `orderbook_imbalance_20 ≥ 0` na entrada, justificado por "a inclinação do impacto é
inversamente proporcional à profundidade". **A justificativa não se sustenta e a candidata sai da
fila:** `orderbook_imbalance_20` é uma **razão**, invariante a escala — multiplicar todas as
quantidades por mil não muda o valor — logo ela **não mede profundidade**, que é a propriedade
invocada. E mais quantidade parada no ask não é o mesmo que mais venda **agressora**. Uma regra que
aceita um book raso e equilibrado e recusa um book profundo com asks predominantes, dizendo-se
proteção contra impacto, está medindo outra coisa.

Se um dia voltar, volta como hipótese **independente**, com janela declarada, população comparável,
tratamento explícito dos ausentes e confirmação em período futuro — e sem citar CKS/CCZ como
validação, porque os horizontes deles (10 s a 30 min) não alcançam as 2 h da estratégia.

**O que eu explicitamente NÃO proponho:** usar `orderbook_imbalance_20` como preditor de retorno de
2 h. O resultado de CKS é **contemporâneo**; o de CCZ que é preditivo é de OFI **defasado e cruzado**,
decai rápido e é de outra grandeza que não temos. Uma feature de estado de book prevendo 2 h à frente
não tem apoio em nenhuma das duas fontes.

## Por que pode falhar

- **Dado ausente na hora exata.** Se o book só está fresco em parte dos instantes de decisão, uma
  sub-população fica selecionada por *qualidade de coleta*, e a diferença medida **pode confundir**
  efeito do book com qualidade da coleta.
- **Confundir estado com fluxo** — o erro que esta nota existe para evitar.
- **Horizonte incompatível.** Os efeitos citados vão de 10 s a 30 min; o horizonte da
  `volume_anomaly_v1` é 7200 s (`volume_anomaly_v1.py:77`).
- **Ações ≠ perpétuo.** Outros participantes, sem funding, sem ADL. O mecanismo é plausível; a
  magnitude não é importável.
- **Confundir razão com profundidade** — o erro que derrubou a H-KB0012b nesta revisão.
- **"Amostra insuficiente" não é refutação.** Se um teste de book cortar a população a ponto de nada
  ser mensurável, o resultado é **inconclusivo**, e escolher depois a janela que melhorou o número
  seria conclusão seletiva.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0012-ofi.md`. **Quatro must-fix, todos aceitos, e um deles matou a
candidata que eu tinha proposto** — o resultado mais útil desta revisão:

1. **`orderbook_imbalance_20` é uma razão, invariante a escala; não mede profundidade.** A
   justificativa que eu dera para H-KB0012b invocava a inclinação inversamente proporcional à
   profundidade de CKS, e a regra proposta não mede essa propriedade. Cenário de falha dela: o filtro
   aceita book raso e equilibrado e recusa book profundo com asks predominantes, alegando proteção
   contra impacto. **Candidata retirada da fila**, com o motivo escrito no corpo.
2. **"Imediato" não estava definido** (janela, denominador, redução mínima) — e o Lab registra saída
   intrabar pelo fechamento da barra (`outcomes.py`, `walker.py:104`), então stop aos 2 s e aos 58 s
   são indistinguíveis. Escolher a janela depois de ver qual melhorou seria conclusão seletiva.
3. **Corrigi os horizontes.** Eu escrevera "efeitos vivem em segundos" e "três ordens de grandeza".
   CKS usa intervalos de 10 s com agregações até 10 min; CCZ prevê em 1 min com horizontes de 2 a
   30 min.
4. **"Exige persistir deltas" era exigência demais.** OFI é calculável incrementalmente a partir do
   estado anterior; o obstáculo real é que guardamos o snapshot top-20 numa chave sobrescrita
   (`hot_state.py:175`), então snapshots espaçados não recuperam os eventos entre eles.

Cortes aceitos: R² de "cerca de 70%" para **média de 65%** (tabela 2); retirei "sem prioridade
preço-tempo idêntica" por falta de comparação documentada; retirei "custo quase zero" do diagnóstico;
troquei "a diferença será efeito da coleta" por "pode confundir"; e qualifiquei o exemplo 1000/1000
como "nos snapshots observados".

**Divergência:** nenhuma. Ela também aponta duas páginas fora do meu escopo de escrita nesta rodada
que merecem atualização — [[Features]] (explicitar estado top-20 versus fluxo temporal) e a página
do agente de fluxo de ordens (que combina métricas de estado e de fluxo sob o mesmo nome). Fica
registrado aqui para o plantão.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] ·
[[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] ·
[[KB-0017-liquidacoes-o-fluxo-forcado-que-nao-observamos]] · [[EXP-0002-volume-anomaly-v1]] · [[Features]] ·
[[Anomalies]]

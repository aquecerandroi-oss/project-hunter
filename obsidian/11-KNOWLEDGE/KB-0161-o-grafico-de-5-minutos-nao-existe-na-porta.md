---
tags: [knowledge, meme, mesa-real, entrada, grafico, linha, suporte, rompimento, fita, cobertura, hipotese, metodo, m4]
tema: a moeda que a porta fluxo_e_holders compra tem 1 a 4 minutos de vida, então quase nunca há os 5 minutos de trocas antes da compra que a H-021 pedia; a hipótese fecha por limite de dado sem abrir desfechos, e o arquivo de trocas não serve para reconstruir a estrutura do preço
fonte: R81 (`.claude/state/notes-R81.md`) — H-021 da Fila de Hipóteses
fonte_url:
lido_em: 2026-09-26
evidencia: medição própria, só contagens cegas — 885 primeiras decisões por mint resolvidas da porta fluxo_e_holders (12–26/09/2026), idade na decisão, parâmetros dos conjuntos, 174 600 trocas do arquivo em volta de cada decisão, 338 fitas da decisão comparadas com o arquivo; nenhum desfecho lido; 14 testes sintéticos
hipotese_testavel: sim (com medida nova)
astra: concorda
status: vivo
owner: sexta-feira
updated: 2026-09-26
confiança: "?"
tipo: pesquisa
hipotese: H-021
variavel: distancia_do_suporte (preço na decisão ÷ mínimo negociado nos 5 min anteriores − 1); secundárias fundos_mais_altos e rompimento
populacao: 885 primeiras decisões por mint resolvidas da porta fluxo_e_holders (12-26/09); só 1 com 5 min de fita antes da decisão (limite 150)
efeito: — (desfechos não abertos)
ic: —
veredito: limite_de_dado
proximo_passo: gravar a estrutura do preço marginal na fita da decisão (desde a assinatura, executável em T) e só então pré-registrar uma H-021b em coorte prospectiva
classe_de_perda: comprou_no_topo
mercado: meme
---

# KB-0161 — O gráfico de 5 minutos não existe na porta

> **H-021 (estrutura do gráfico na hora da compra): `NÃO CONFIRMA` por limite de dado (estrutural).** A cláusula
> de dado do próprio bloco dispara antes de qualquer contraste: há **1** decisão com 5 min de fita antes da compra, e
> o bloco pede 150. **Nenhum desfecho foi aberto.** Estudo em `.claude/state/notes-R81.md` · código e saídas em
> `.claude/state/r81/` · pré-registo em [[Fila de Hipoteses]] § H-021.

## O que afirma

1. **A porta compra moedas de 1 a 4 minutos.** Todos os conjuntos da porta `fluxo_e_holders` têm `max_age_s = 300`
   (`flow_v2/1…10`, `operator/3…6`, `recuo_v1/1`, `recuo_ctrl_v1/1`).
   - Idade na decisão: mediana **1,6 min**, p90 3,8 min, máximo 315 s.
   - Só **6 de 885** decisões têm moeda com ≥ 300 s — a idade é medida no instante das features e a decisão chega
     segundos depois.
   - Só **1** tem o arquivo de trocas começando 5 min antes de T. Isso só mostra que o arquivo começa cedo o bastante,
     não que a janela esteja completa.
   - Não é impossibilidade matemática, é incompatibilidade estrutural: esperar não enche a amostra.
2. **A linha de produção não é a variável do bloco, e quase nunca existe nestas moedas.**
   - O bloco pede o mínimo **negociado** em 5 min. A produção (`hunter_indicators/meme/lines.py`) traça a **reta pelos
     dois últimos mínimos locais** de 15 min de fotos da curva.
   - Na série de 1 minuto (`meme_features_1m`), consultada pela pesquisa, `distance_to_support_pct` existe em **67 de
     623** decisões. Nas outras, `line_reason` = `flat` (290), `too_few_points` (256) ou `no_snapshot` (7), e 3 não
     têm linha de 1 minuto.
   - **Mesmo essas 67 não chegam ao portão.** As duas pistas da porta montam a linha do portão sem os campos da linha
     (`lab_repo_fast.py`, `event_gate_rows.py`); só a via de 1 minuto (`lab_repo.py`) os lê.
   - Nenhuma proposta da porta tem o bloco `line` nas razões (0 de 3 734).
   - O braço que usava a linha (EXP-M2, `trendline_v0/1`, idade ≥ 300 s) está aposentado com **0 propostas** em toda
     a vida.
3. **O arquivo de trocas não serve para reconstruir a estrutura.** A auditoria cega usou duas populações.
   - **A** = 338 decisões da pista de eventos: a 1.ª proposta por mint, quando essa proposta tem fita da decisão.
   - **B** = 775 primeiras decisões com alguma troca na janela.
   - **Contagem de trocas no minuto julgado** `(as_of − 60 s, as_of]` (A): o arquivo tem **menos da metade** das trocas
     que a fita ao vivo contou em **28,7 %** das decisões, e zero em pelo menos um quarto. É uma comparação de
     contagens, não uma reconciliação troca a troca.
   - **O que já estava na base** (A): nenhuma troca daquele minuto tinha sido **recebida** até o instante das
     features (`as_of`) em **95 %** das decisões. Não é o arquivo inteiro até a decisão, mas basta para dizer que
     uma versão executável a partir do arquivo não é viável ([[KB-0153-o-maior-comprador-nao-estava-no-arquivo]]).
   - **Slot de criação** (A): o slot inferido ao vivo e o 1.º slot arquivado discordam em 32 de 264 (12,1 %), ou 32
     de 203 entre os pares comparáveis (15,8 %). Os dois são aproximações; nenhum é a criação comprovada.
   - **Último slot** (B): em 184 de 775 (**23,7 %**) o último slot tem preços diferentes, e o arquivo não guarda a
     ordem das transações dentro do slot. O "preço na decisão" fica ambíguo; amplitude mediana 2,1 %.
   - **Preço de fill:** o preço gravado é o de execução de cada troca, não o marginal da curva. Misturar compras e
     vendas mistura execuções. Exemplo sintético: com o marginal parado, uma venda a 0,98 e uma compra a 1,02 dão
     uma "distância" de 4 % e um "rompimento".
4. **Numa moeda de 1 a 4 minutos, "distância do suporte" quer dizer sobretudo "quanto já subiu desde o lançamento".**
   A curva começa num preço padrão (o p1 do mínimo da janela é 2,80e-8 SOL/token). Na variante adaptada, com a janela
   cortada no nascimento, a distância tem Spearman 0,60 com o preço na decisão (postos médios, `r81/sp_check.txt`). É
   parente de `progresso`, uma das 13 variáveis esgotadas ([[KB-0149-o-que-a-mesa-real-ensinou]] §3).

## Onde foi mostrado

| peça | número |
|---|---|
| primeiras decisões por mint resolvidas | 885 (802 papel, 83 reais; 477 da pista de eventos, 408 da de 15 s) |
| com moeda ≥ 300 s / com 5 min de fita arquivada | 6 / **1** (limite do bloco: 150) |
| variante adaptada (janela cortada no nascimento, arquivo desde o nascimento) | 623 decisões — **desfechos não abertos** |
| fundos mais altos com valor (3 minutos inteiros) | 175 de 623 (moeda < 180 s = ausente) |
| linha de produção na série de 1 min | 67 de 623 (nenhuma chega ao portão das duas pistas) |
| fotos da curva recebidas antes de T | mediana 6 nos últimos 5 min (p10 4); < 5 fotos em 11,5 % |

**Por que os desfechos da variante não foram abertos.** A decisão foi tomada com a Astra.
- A variante não pode dar veredito da H-021, porque muda a população e a variável.
- Serviria só para escolher a próxima hipótese, e com um instrumento que a auditoria mostrou não identificar a
  variável.
- Abrir é irreversível; não abrir é reversível. O script `r81/h021.py` fica pronto, com as correções da Astra e o
  rótulo "exploratório, não veredito".
- Uma coorte nova enche depressa: a porta fez 99 a 106 primeiras decisões por mint resolvidas por dia em 24–26/09
  (as duas pistas juntas).

## Por que importa

1. **"Comprou no topo" não pode ser lido pelos 5 minutos anteriores nesta porta.** Com 1 a 4 minutos de vida, quase
   nunca há cinco minutos antes da compra. O que a porta vê é o **lançamento** e o **fluxo** desde ele.
2. **Um teto `max_distance_to_support_pct` nesta porta recusaria tudo.** As duas pistas não entregam os campos da
   linha ao portão, e `rules_criteria.line_refusals` recusa linha ausente (`line_unknown`). Mesmo que os entregassem,
   a linha falta em 556 de 623 decisões (89 %) na série de 1 minuto.
3. **A pergunta continua aberta.** O [[Perdas/comprou_no_topo|maior vazamento]] continua sem variável que o separe
   antes da compra. Este estudo não trouxe evidência a favor da tese nem contra ela.

## Como mediríamos aqui

Só com **instrumentação nova** (não implementada; é o próximo passo):
1. Gravar, na fita da decisão (`meme_decision_tapes.derived`, próxima versão), a estrutura do **preço marginal**,
   calculada ao vivo a partir do estado WS no instante da decisão.
   - O marginal vem das reservas depois de cada troca, que o estado WS já recebe (`event_state.py`). A ordem é a de
     **recebimento**; precisa de uma política explícita para eventos fora de ordem, ou de ordem verificável, antes de
     ser tratada como a trajetória do preço.
   - Campos: mínimo desde a assinatura (ou dos últimos 5 min), último marginal, mínimos por minuto e máxima anterior
     ao último slot.
   - Guardar `covered_since` e as lacunas. Se a moeda não for coberta desde o nascimento, a ausência leva nome e nunca
     vira zero.
2. Com isso, pré-registar uma **H-021b** numa coorte **prospectiva** (decisões depois da instrumentação, só da pista
   de eventos, 150 resolvidas).
   - Janela = min(5 min, vida desde a criação).
   - Controle de `curve_progress_pct` declarado antes, porque a distância confunde-se com quanto a moeda já subiu.
   - Mesma forma de previsão, refutação e regra de rótulo da H-021.
   - Não condicionar a H-021b a nenhum número deste estudo: não há nenhum.

## Hipótese testável no Lab

Nenhuma com os dados de hoje. A H-021b fica descrita acima e depende da instrumentação.

## Por que pode falhar

- **Mesmo com instrumento bom, a variável pode ser só `progresso`.** Sem o controle declarado antes, um efeito da
  distância pode ser o efeito já esgotado da subida desde o lançamento.
- **Viés da pista.** Uma H-021b só da pista de eventos não diz nada da pista de 15 s, que nunca teve fita WS.

## Segunda opinião (Astra)

- **Desenho** (`.claude/state/astra-review-R81-design.md`). Concorda com NÃO CONFIRMA por limite de dado e com
  `concluída`, sem desfechos.
  - Pediu tirar "permanente": os 6 casos ≥ 300 s mostram incompatibilidade estrutural, não impossibilidade. Aceito.
  - Recomendou **não** abrir a variante antes de auditar o instrumento e não condicionar a H-021b a ela. Aceito.
  - Os cinco must-fix da variante (slot de criação, janela incompleta, ordem no último slot, fill × marginal, bugs do
    script) foram medidos na auditoria ou corrigidos no script, que não foi rodado.
- **Veredito** (`.claude/state/astra-review-R81-verdict.md`). Mantém NÃO CONFIRMA por limite de dado, sem abrir a
  variante, e mantém a H-021 em Pistas (o Dataview lê `limite_de_dado`). Corrigido o que ela apontou:
  - o "~89 %" confundia a série da pesquisa com o que chega ao portão;
  - faltavam os 3 casos sem linha de 1 minuto;
  - os 95 % referem-se ao minuto julgado recebido até o `as_of`;
  - denominadores do slot e das duas populações da auditoria;
  - "postos médios" agora tem a saída gravada;
  - o fill deixou de ter uma regra universal;
  - a ordem do WS é de recebimento;
  - restos do script: vencedoras sem denominador e regra do moinho.
  - Nada foi rejeitado. Detalhe em `.claude/state/notes-R81.md` §6.

## Relacionados

[[Fila de Hipoteses]] · [[Dicionario de Variaveis]] · [[Mapa de Estrategias]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0153-o-maior-comprador-nao-estava-no-arquivo]] ·
[[KB-0159-a-desaceleracao-nao-avisa-o-topo]] · [[KB-0160-o-link-reciclado-nao-avisa-o-golpe]] ·
[[EXP-M2-a-linha-manda]] · [[comprou_no_topo]]

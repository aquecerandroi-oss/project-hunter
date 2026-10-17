---
tags: [dialogo, astra, b3, win, ia, llm, grafico, h-042, pesquisa, anti-antecipacao]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: quant-engineer
decided_on: 2026-10-17
by: claude + astra
tarefa: "desenhar o teste histórico da 'IA trader' que lê o gráfico de 5 min do WIN (H-042) e construir o arnês com dados sintéticos, antes de qualquer dado real ou chamada paga"
veredito: "5 rodadas; R1: 7 must-fix (contraste dependente da geometria da IA, fill selecionado pelo futuro, completude dos baldes, alvo antes do fill, censura, isolamento do Codex); R2: 10 sondas reproduzidas (permutação esparsa, cauda ausente, limite sem fill, gap, telemetria, persistência); R3: 5 (censura do gêmeo, otimista não é limite, registro por tentativa, telemetria estrita, futilidade no estudo); R4: 1 (item.updated e sequência de eventos); R5 DECISÃO CONJUNTA. Não atesta executor, dado real, cliente escolhido nem vantagem"
---

# A IA que lê o gráfico do WIN (H-042): o desenho até a decisão conjunta

**Pedido:** o Everton quer uma "IA trader" que olhe o gráfico do WIN como um humano — desenhe suporte, resistência e
tendência e entre tentando antecipar o próximo movimento. A Sexta-feira topou **testar no histórico antes de qualquer
dinheiro**. Desenho: `docs/design/ia-le-grafico.md`; arnês: `infra/research/b3/ia_grafico/`; rascunho do
pré-registro (fora da [[Fila de Hipoteses]] até congelar): `.claude/state/h042/prereg_draft.md`; transcrição bruta:
`.claude/state/dialogue-ia-le-grafico.md`.

**O que a base mudou no plano:** [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] (taxa-base: 97 % das
pessoas físicas perdem no WIN → medir contra o acaso, não contra zero); [[KB-0149-o-que-a-mesa-real-ensinou]] §5
(antecipação mente com convicção → renderizador recusa barra depois de *t*); [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]
e [[KB-0168-fibonacci-elliott-e-lta-diaria]] (linha desenhada no gráfico pronto fabrica vantagem → a IA só vê o
prefixo e os níveis dela não entram na simulação); [[KB-0080-candlestick-evidencia]] (candles não batem o acaso).

## O que mudou em cada rodada

| rodada | achado da Astra (com cenário ou sonda) | o que mudou |
|---|---|---|
| 1 | com stop/alvo **da IA**, uma moeda que compra largo e vende curto ganha da deriva (D = +5 bp sem ler nada); fill de limite seleciona pelo futuro; minuto ausente vira barra "íntegra"; alvo pode vir antes do fill; censura só com teto; `read-only` não prova que o agente só vê a imagem | **dois braços**: direcional com geometria do arnês (2 × ATR(14), simétrica) e π **por horário**; estratégia completa por instante elegível (none e sem fill = 0); balde de 5 min só completo; na barra do fill só o stop vale; espelho e autoconcordância viram diagnósticos |
| 2 | permutação com amostragem esparsa dá NaN; cauda ausente aceita; limite sem minutos vira "sem fill"; stop + tick não limita a perda num gap (−1 012,56 contra −107,56); telemetria ilegível aceita; teto reinicia por lote; nada gravado por tentativa | amostragem por **pregões inteiros**; permutação só entre pregões com a **mesma máscara**; última barra tem de terminar em *t*; limite com minuto ausente = censura; gap na entrada paga o tick de cada perna; orçamento cumulativo; calibração da permutação (4,2 % a 5 %) |
| 3 | o gêmeo censurado não contava (CONFIRMA com 24 contrafactuais ausentes); a imputação otimista também não é limite; queda entre as duas tentativas ganhava tentativas novas; `usage: {}` e evento novo passavam; estudo sintético sem a futilidade | censura dos dois lados e dos patamares (união); censura no primário bloqueia **CONFIRMA e REFUTA**; registro **por tentativa** (intenção e débito antes do envio); telemetria estrita (versão homologada antes de enviar, tipos conhecidos, uso completo, mensagem = saída); estudo com futilidade |
| 4 | `item.updated` com `command_execution` passava; sequência e estrutura dos eventos não eram validadas | ferramenta em qualquer fase invalida; sequência homologada `turn.started` → itens → `turn.completed` último; saldo do orçamento reconstruído do registro |
| 5 | **DECISÃO CONJUNTA** | — |

## O que a fumaça mostrou (3 chamadas, imagens sintéticas, nada real)

GPT-6 Astra pelo Codex isolado (codex-cli 0.153.4): gráfico normal → "none" com níveis desenhados (15 436 tokens de
entrada, 531 de saída, 19 s); espelho → venda limite (15 434 / 492 / 18 s) — um par só, nada se conclui. A
**sentinela** (isca em `../apoio/sentinela.txt` e o pedido de copiá-la) não vazou — o agente escreveu "execution was
blocked by policy" — mas o `--json` **não emitiu nenhum item de ferramenta**; só os 51 411 tokens de entrada denunciaram
as voltas internas. Lição: **evento de ferramenta não prova isolamento**; o teto de 20 000 tokens virou alarme e o
adaptador do Codex ficou **fora do lote autorizado** até o Everton escolher o cliente (API direta sem ferramentas
recomendada). Total da fumaça: 83 695 tokens.

## Características do procedimento (sintético, suposições do cenário — não poder no WIN)

Com futilidade, 24 meses × 7 pregões, desvio de 30 bp, 100 repetições: efeito 0 → para por futilidade 81 %, REFUTA
17 %; 3 bp nominal (2,72 realizado) → CONFIRMA 35 %, NÃO CONFIRMA 36 %, parada 27 %; 5 bp → CONFIRMA 93 %; **5 bp com
0,2 % de censura → CONFIRMA 1 %** — a completude do export do MT5 durante as posições decide se a H-042 pode confirmar.

## Decisão conjunta (rodada 5)

1. Dois braços distintos; vencer o controle **não** identifica suporte/LTA como mecanismo.
2. Censura dos dois lados e dos patamares entra no veto; imputações são sensibilidades. Censura em P impede CONFIRMA e
   REFUTA; censura só em H impede CONFIRMA, sem invalidar o REFUTA do primário observado.
3. Primeira resposta válida em até duas tentativas consumidas; intenção antes do envio, resultado antes da próxima;
   retomada sem devolver tentativas.
4. Ferramenta em qualquer fase encerra o ensaio; telemetria incompleta ≠ ausência de ferramenta; teto de tokens é
   alarme, não prova.
5. Futilidade é parada operacional, separada dos três rótulos; espelho e autoconcordância são diagnósticos.
6. **Pendências antes do congelamento/lote:** manifesto (corte, embargo, contrato, ids e ordem dos pregões, hashes);
   grade histórica, cauda do pregão anterior e **identidade do contrato** provadas pelo carregador (o runbook pede a
   série contínua `WIN$N` — conflito aberto com a janela "sem emenda"); retomada em processo novo com saldo global;
   cliente escolhido e isolado pelo Everton. Nenhum LLM no caminho risco → execução (ADR 0002).

Discordância resolvida a favor da Astra em todas as rodadas; nenhuma decisão contra ela ficou registrada. A H-042
continua **rascunho**; nenhum dado real foi mostrado a modelo algum.

## Relacionado

[[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Ideias do Everton]] · [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0168-fibonacci-elliott-e-lta-diaria]] ·
[[KB-0080-candlestick-evidencia]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[Dialogos/mercado-tradicional|diálogo mercado-tradicional]] ·
[[Dialogos/Index|diálogos]]

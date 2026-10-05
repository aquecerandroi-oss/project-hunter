---
tags: [revisao-astra, meme, carteiras, smart-money, copy-trading, pre-registro, desenho, obsidian]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: quant-engineer
decided_on: 2026-10-05
by: astra
tarefa: desenho "seguir quem ganha dinheiro de verdade" (docs/design/seguir-carteiras-lucrativas.md) e rascunho H-030
veredito: REQUEST_CHANGES no desenho; concorda com a pesquisa — os 9 must-fix foram absorvidos antes de o desenho ir ao Everton
---

# Revisão da Astra: seguir carteiras lucrativas (desenho + rascunho H-030)

Pedido do Everton (05/10): "começamos a seguir quem faz dinheiro de verdade". O desenho está em
`docs/design/seguir-carteiras-lucrativas.md`, o rascunho do pré-registro em `.claude/state/carteiras-lucro/PREREG.md`
e a síntese da evidência em [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]]. A revisão bruta está em
`.claude/state/astra-review-carteiras-lucro-design.md`. Antecedentes: [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]]
e [[EXP-M15-carteiras-vencedoras]].

## Respostas às seis perguntas

| Pergunta | Astra |
|---|---|
| Episódio que entrou antes da janela e fechou dentro dela | Pode, e não é look-ahead, **desde que o custo esteja preservado**. Sem custo, o episódio fica incompleto, não ganha custo zero |
| Controle pareado | Do jeito proposto ele compara a política inteira com outra população e **não isola o ranking** |
| Sacos e exclusões | Têm furos: perdas abertas recentes, liquidação contada duas vezes, transferências e exclusões que só se conhecem depois da entrada |
| Replay noturno como "papel" | É aceitável como pesquisa prospectiva com execução simulada. **Não prova** a execução, e isso fica para a onda 5 |
| Tabela nova com partição diária | Concorda. O orçamento estava incompleto e a premissa de 90 d estava errada (são 30 d, `settings.py:125`) |
| Limiares | Podem ser congelados como escolhas. Mas **2 000 apostas não dão potência para +0,05 R**, e pegar o mais largo de dois IC não resolve a dependência cruzada |

## Must-fix e o que foi feito (todos aceitos)

| # | Achado (cenário de falha) | Decisão |
|---|---|---|
| 1 | Causalidade só por `block_time`. Eles vendem às 23:59:59 e a nossa saída simulada usa reservas de 00:00:01; ou um trade recuperado às 03:00 entra no retrato das 00:05 | **Aceito.** Agora há três instantes: corte econômico, disponibilidade (`received_at`) e publicação (`published_at`). O desfecho copiado tem de terminar inteiro antes do corte. Um evento recebido depois do pouso teórico não gera compra |
| 2 | Perdas abertas ficavam fora do C-PnL, e a liquidação podia ser descontada duas vezes | **Aceito.** O C-PnL passa a ser a **mesma política** do braço, então o saco dela fecha para nós pelo stop ou pelo tempo. Nasce o E-PnL = realizado + **variação** do valor de liquidação (entra uma vez). Transferência gera `unmatched`; acima de 20 % a contabilidade é incompleta e a entidade não é elegível |
| 3 | Exclusão retroativa: MEV visto 1 slot depois apagaria a aposta; o total de trades do dia exclui a manhã; ligações futuras fundem hoje; o corte de concentração usa participação final | **Aceito.** As exclusões ficam separadas em ranking (histórico) e aposta (causal), sem nada retroativo. O robô de volume usa o dia anterior. Ligações valem a partir de `known_at`. O teto vira causal: 20 apostas por entidade por dia |
| 4 | O controle "ativo não elegível" atribui ao ranking o efeito dos filtros | **Aceito.** Controle 1 (H2) = elegíveis fora do top-30. O antigo virou Controle 2, descritivo. Sorteio, semente, sem reposição, desempate e cobertura do pareamento estão congelados. O pareamento ganhou tercil de liquidez antes do gatilho |
| 5 | Preço sem contrato: slot sem trade levava ao "próximo trade" (futuro), migração, liquidez de pool sem swap, `quote_sell` sem teto de SOL real, taxa contada duas vezes no `net_proceeds` | **Aceito.** §3.1: o último estado com slot ≤ pouso e nunca o próximo trade. Censurada entra a R = −1. Teto de SOL real obrigatório. `net_proceeds` não desconta de novo. Fixtures reais por praça |
| 6 | Cobertura de 99 % no dia pode esconder a lacuna exatamente no despejo que dispararia a saída | **Aceito.** Contaminação por episódio e por aposta. CONFIRMA exige ≤ 2 % contaminadas e que H1 se mantenha com elas a R = −1. A auditoria também cobre controles e carteiras fora do topo. Deduplicação por (assinatura, programa, ordinal) e atribuição ao mint do evento |
| 7 | A poda de 7 d perde o custo de lote aberto antigo e a prova de por que a entidade foi ranqueada | **Aceito.** `meme_wallet_lots` sobrevive à poda. O retrato leva manifesto. `fills_kept` guarda também os episódios que puseram a entidade no top-30. Retenção de 9 d com poda só depois da marca de sucesso. Restauração grava lacuna |
| 8 | O maior de dois bootstraps separados não cobre dependência dia × entidade (Cameron & Miller, JHR 2015, §V) | **Aceito.** Erro-padrão em duas vias (CGM) com t de G−1 e *pigeonhole* como robustez. A potência foi declarada: 2 000 → ≈ 0,075 R, 4 500 → 0,05 R. O alvo subiu para 4 500, com piso de 2 000 |
| 9 | O PREREG não existia e a tabela de veredito estava incompleta | **Aceito.** O PREREG foi escrito com CONFIRMA conjunto, REFUTA pelos dois métodos, limite de dado, encerramento e aborto. Entidade com < 10 apostas continua no resultado e só conta contra o piso |

## Nice-to-have

- **Aceitos:** C-PnL alinhado à política (virou o item 2); 5 slots chamado de "cenário-base", não de garantia;
  sensibilidade só com ligações fortes e tamanho dos grupos publicado; lacuna com slot (hoje `meme_ingest_gaps` não
  tem, `meme_radar.py:274`), que fica para a decisão da onda 1b.
- **Correção numérica aceita:** "centenas de GB" estava errado. Com 30 d de retenção seriam 31,5–63 GB, e a tabela
  separada continua preferida.

## Divergências

Nenhuma de mérito. Uma nuance que fica escrita: a Astra lembra que o RPC público "não é para produção" (documentação
da Solana). Isso já estava no desenho como risco. Agora está explícito que **24/7 deve exigir o WS da Helius**, com
custo desconhecido, e que essa decisão é do Everton.

## O que ela concorda

Ranquear **copiabilidade** e não reputação nem marcação; entrar e sair depois da entidade, com impacto e custo;
reabrir a pergunta com população maior em vez de reanalisar a fita da R57; congelar limiares e declarar a família;
dinheiro real fora do escopo, com a onda 5 obrigatória depois de um eventual CONFIRMA.

- **Decisão do Everton (05/10):** projeto aprovado por inteiro, Helius paga se precisar — [[2026-10-05-seguir-carteiras-lucrativas-aprovado]].

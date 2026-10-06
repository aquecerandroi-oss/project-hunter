---
tags: [dialogo, meme, carteiras, h-030, armazenamento, disco, particionamento, onda-1b]
updated: 2026-10-05
status: registro
owner: sexta-feira
decided_on: 2026-10-05
by: sexta-feira (claude+astra)
---

# Diálogo: armazenamento da fita de carteiras do H-030 depois da onda 0 (3 rodadas)

Claude, no papel de `database-architect`, conversou com a Astra em três rodadas para decidir como guardar a fita do
programa inteiro (pump + PumpSwap). O motivo: a onda 0 mediu 28,5–31 M swaps/dia
([[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]]), e a aprovação de 10–20 GB
([[2026-10-05-seguir-carteiras-lucrativas-aprovado]]) deixou de valer.

- Desenho: `docs/design/seguir-carteiras-lucrativas.md` §9.
- Transcrição: `.claude/state/dialogue-wallet-tape-storage.md`.
- Antecedentes: [[wallet-tape-probe]], [[carteiras-lucro-design]] e [[wallets-engine]].

## Como a conversa andou

| Rodada | Claude | Astra |
|---|---|---|
| 1 | Propôs (b): derivar à noite (fatos carteira-dia e gatilhos pré-simulados), fita bruta enxuta de ~1,2 d, ~16–25 GB | **Não.** (b) é outra especificação. A liquidação da entidade não é a soma das carteiras (exemplo: 90 + 90 contra 166). "Metade das posses ≥ 60 s" não é a mediana. A exclusão por financiador conhecido depois precisa de proveniência. O C-PnL por carteira não compõe por entidade. Evento tardio entra no corte seguinte. Lotes não se podam por silêncio. Prefixo de assinatura rejeitado. Ela prefere (e) |
| 2 | Retirou (b). Trouxe três fatos novos: a assinatura custa 1,92 GB/dia (13,44 GB em 7 d); os lotes do contrato não têm teto (0,216 posição aberta nova por trade na fita de 01/10); poda por dependência dá pico de 7,2 d. Propôs um horizonte de lote H = 14 d | **Não a H.** Ela mostrou três cenários: a perda 10 → 1 SOL some sem venda; uma venda velha casa com compra nova pela cabeça da fila; um lote expira dentro da janela móvel. Pares carteira/mint não são lotes. "Impossível em qualquer formato" virou "nenhuma opção completa demonstrou caber" |
| 3 | Retirou H. Propôs campanha finita com contabilidade intacta, teto físico e o texto da decisão | **DECISÃO CONJUNTA** |

## DECISÃO CONJUNTA (rodada 3, Astra), resumida

1. **(e):** fita L0 compacta no Postgres, com estas características:
   - assinatura inteira de 64 B, programa e ordinal;
   - partição diária;
   - BRIN em `slot`, a medir;
   - sem btree de consulta nem filtro no ingresso.

   (b) foi retirada; o corte de swaps pequenos, rejeitado; a opção só-curva (f) muda a população. O Parquet (d) é
   alternativa de estudo e depende de exceção arquitetural do Everton. "Nenhuma opção completa apresentada demonstrou
   caber em 20 GB" não é impossibilidade universal.
2. **Campanha finita, sem H.** Lotes abertos inteiros (quantidade, custo, origem, ordem) durante toda a campanha. A
   duração máxima é fixada antes do congelamento, e o fim do ingresso fica separado do fim da retenção. Reduzir os
   prazos de §2.2 (lotes fechados +60 d, episódios 60 d, kept até o veredito + 90 d) exige revisão explícita; até lá,
   eles entram no orçamento.
3. **Poda por dependência.** *p*+7 é a primeira liberação possível, não automática. Pico normal = 7 + (hora da
   liberação)/24 dias. A coleta para, com lacuna, no que vier primeiro: limite de atraso, teto do H-030 ou reserva
   ameaçada.
4. **Reexecução idempotente por efeito**, com publicação atômica e imutável e canonicalização com memória limitada. Os
   dois relógios continuam estritos.
5. **Onda 1c-bis:** o motor refatorado no acesso, com as regras intactas e prova diferencial. Os retratos gravam toda
   entidade que passa a atividade, por cenário; as demais ficam em contagens declaradas.
6. **Backup degradado:** L0 e lotes fora do dump, evidências dentro. A restauração marca a cobertura contábil como
   desconhecida.
7. **Teto físico e disco** são proposta ao Everton, não capacidade garantida. A faixa de planejamento é de 80–175 GB
   (74,5–163 GiB). Um teto de 100 GiB (107,4 GB) **pode interromper** a campanha. Recomendação: +100 GiB de disco; +50
   GiB só se a projeção medida couber.
8. **Portão:** a onda 1b definitiva e a onda 2 esperam por quatro coisas:
   - os crons provados pelo efeito;
   - o backup de 05/10 esclarecido;
   - o piloto físico com tabela de ensaio isolada;
   - a decisão do Everton com os números.

## O que a conversa ensinou (vale além do H-030)

- **Agregar no ingresso troca a pergunta.** Qualquer representação mais curta que a fita precisa de prova de
  suficiência para fusão, fronteira e janela móvel. Somar carteiras não dá a entidade, porque a liquidação é não linear.
- **"Enquanto aberto" sem teto, num mercado de sacos mortos, é crescimento infinito.** O limite certo é a duração da
  campanha, não um corte contábil escondido.
- **O motor puro da onda 1c foi testado em sintético e não escala para a janela real** (~210 M fills). A escala é uma
  propriedade a provar, não um detalhe de implementação.
- **A medição achou três coisas operacionais fora do escopo:**
  - crons de poda não instalados (a outbox sem poda desde 28/09);
  - o backup de 05/10 ausente no log;
  - WAL de ~86 GB/dia com `shared_buffers` padrão.

## Depois da decisão conjunta

O orquestrador acrescentou a pergunta secundária de seguidores
([[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]]). O desenho ganhou o item 7 de §9.6: tabela de fotos
de perfil `meme_wallet_profile_snapshots`, ponto no tempo por `known_at`, ≤ 3 000 carteiras/noite, ~0,5 MB/noite.
Esse item não fez parte das três rodadas: foi revisado à parte pela Astra (`.claude/state/astra-review-wallet-profile-snapshots.md`).

## Divergências

Nenhuma de mérito no fim. Ficam escritas as que a conversa resolveu: (b) foi retirada pela rodada 1, e H pela rodada 2.

## Relacionado

[[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]] · [[EXP-M15-carteiras-vencedoras]] ·
[[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[wallets-engine]] · [[wallet-tape-probe]] ·
[[2026-09-27-retencao-de-dados-e-backup]] · [[Open Bugs]]

---
tags: [experimento, meme, kol, call, evento, m4, r61]
status: pre-registrado (condicionado à T4.68a)
owner: sexta-feira
updated: 2026-09-19
origem: Everton, 19/09/2026 02:0x BRT — "tem muita gente chamando moeda; com muitos seguidores explode rápido e cai rápido — estamos analisando as que estão começando a bombar?"
previsao: inconclusivo → descartar
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# EXP-M20 — Sinal de call: o KOL lido no patch de 1 s (não no minuto fechado) paga entre 2 e 30 min de idade?

## Hipótese
A primeira carteira KOL que entra numa moeda **já viva** (2–30 min de idade, ainda no pico anterior, ≥ 30 holders) é
seguida por compradores em número suficiente para pagar 1,25 %/perna + 3 % de slippage com trailing 20 % / 5 min — **desde
que o sinal seja lido no patch de 1 s dos boards**, não no minuto fechado. Na moeda de < 2 min o KOL é o bundle do bloco e
não há tese (KB-0141, KB-0142).

## Por que agora
R61 (KB-0142) mediu que, no minuto fechado, o `kol_count` chega junto com o pico (R −0,07, acerto 15 %, negativo em toda
célula), mas que o proxy de leitura a 1 s (`R_mid`) dá +0,08 R [+0,01, +0,16], acerto 38 %, n 445 em 72 h na faixa de
2–30 min — cauda concentrada (sem os 3 maiores +0,04) e um dia em quatro negativo. É a única porta que a pesquisa abriu;
é estreita e precisa de medição prospectiva, não de mais replay (o replay não tem o instante do patch).

## Pré-requisito (T4.68a — sem fonte nova)
`boards.py::ingest` já recebe cada patch; hoje persiste só o último do minuto. Emitir em memória
`kol_seen{mint, kol_before, kol_after, board, server_ts, received_at}` para o portão de evento (mesmo molde de
`event_gate_rows.build_event_row`) e gravar `kol_first_seen_at` (write-once) em `meme_tokens` — uma coluna, uma migração.
Sem isso a EXP não é mensurável: o gatilho teria ±55 s de erro e reproduziria o R61.

## Método (papel primeiro, `research_only`)
- Braço `kol_v0/1`: gatilho `kol_seen` com `kol_after > kol_before`, idade 120–1 800 s, mcap ≥ 0,95 × máximo observado
  até ali (série de 15 s), holders ≥ 30, E2 (pedigree), `dev_share ≤ 10 %`; 0,05 SOL; saídas trailing 20 % do pico
  pós-entrada **ou** 300 s; `exit_on_migration = false`. Limiares vêm das células do R61 (2 algarismos, origem declarada).
- Controle predeclarado: `flow_v2/6` no mesmo minuto **e** as mesmas moedas sem o gatilho (entrada em instante aleatório
  na mesma janela de idade, mesma frequência).
- Medir 3 dias (≥ 60 apostas esperadas: ~150 aparições/dia × filtros): R médio, acerto, concentração dos 3 maiores,
  mediana; `received_at − server_ts` do patch (latência real do sinal); pico − `kol_first_seen_at` na série de 15 s
  (o lead/lag do R61 refeito com a resolução certa).

## Regra de decisão (congelada)
- **Confirma** se R médio > 0 com IC95 fora de zero, acerto ≥ 30 %, top-3 ≤ 50 % do bruto e nenhum dia com R < −0,10.
- **Descarta** se R médio ≤ 0 ou se, medido a 1 s, o pico ainda vier antes do sinal em ≥ 50 % dos casos.
- Nada é ativado na mesa por este EXP; vira candidata (um dia de validação, replay + estresse + replicação) só depois.

## Não faz parte
Feed de canais de call no Telegram/X (T4.68 propriamente): a spec (campos e latência) está na nota R61 §7 e só se
justifica se este EXP mostrar que **algum** sinal de "gente entrando" antecede o pico com a resolução de segundos.

Ligações: [[KB-0142-kol-e-call-antecipam-ou-confirmam]] · [[KB-0141-sniper-de-lancamento]] ·
[[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[EXP-M8-evento-que-pode-dar-bum]] · [[EXP-M19-subida-com-gente-atras]] ·
`.claude/state/notes-R61.md`

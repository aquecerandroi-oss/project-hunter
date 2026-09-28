---
tags: [revisao-astra, cripto, fibonacci, lta, pre-registro, h-025, h-026]
date: 2026-09-28
updated: 2026-09-28
status: registro
owner: sexta-feira
decided_on: 2026-09-28
by: astra
tarefa: R85 — desenho da H-025 (retração de Fibonacci 50–61,8 % no diário) e da H-026 (LTA diária, braços A e B), antes de qualquer pivô, evento ou retorno no painel real
veredito: sem antecipação inevitável; 6 must-fix aceitos numa emenda datada (13:12Z); o contraste incremental ficou fora e a leitura foi restringida
---

# Revisão da Astra — pré-registro da H-025 e da H-026 (R85)

**Pedido:** revisar o texto congelado às 13:05Z (`.claude/state/r85/prereg_frozen.md`, sha256 `398b63be…`) contra o
painel do R84 e a [[EXP-0016-trendline-breakout]], com perguntas sobre antecipação, controle do mesmo dia, bloco do
bootstrap, MRE/patamar/corte/K6 e a saída estrutural. Nenhum pivô, evento, contagem ou retorno real existia.

**O que ela confirmou (antecipação):** buscar L no passado é causal (não precisa ser pivô); ATR14(h) já existe em
h + 5; conferir o respeito à reta até o nascimento em b + 5 é causal; o 3.º toque pode confirmar e emitir A no mesmo
fechamento; P de B pode incluir a máxima do toque desde que congelado; o controle do mesmo dia e o universo em e = d + 1
(volume até d) são conhecidos no fechamento.

**Seis must-fix, todos aceitos na emenda da [[Fila de Hipoteses]] (H-025 e H-026), antes de qualquer evento real:**

1. **Início da busca da primeira retração** era ambíguo (fundo, h ou h + 5 mudam a população). → começa em h,
   inclusive; só emite depois da confirmação; travessia antes consome a faixa. Teste sintético novo (pavio na própria
   vela do pivô) falhou antes da correção e passa depois.
2. **Toques distintos e P de B.** Cenário dela: duas velas seguidas junto à linha contariam como dois toques. → índice
   s estritamente entre os toques com fecho ≥ ℓ + 1 ATR; P congelado no fechamento do toque; pendências só morrem por
   rompimento, morte da linha ou prazo.
3. **O controle mede "esta regra supera este controle", não a geometria.** Cenário: qualquer queda recente recupera;
   H-025 daria D positivo com vizinhos positivos sem nada de Fibonacci. → leitura restringida por escrito; a
   especificidade fica no descritivo das faixas. **Parcial:** o contraste incremental que ela propôs (placebos,
   pareamento por retorno prévio, ATR% e idade da estrutura) **não** foi congelado — limite declarado.
4. **Inferência.** Cenário: duas rajadas de eventos pertencem a dezenas de janelas móveis e "passam" o piso de 40. →
   calendário completo, D* = ΣS*/ΣN*, mesmos índices para todos os braços, cobertura em intervalos **não sobrepostos**;
   para a estrutural, blocos de 120 d.
5. **Fecho carregado não é venda executável.** Cenário: a moeda para antes de e + 10 e volta muito abaixo. → venda na
   primeira abertura real, atraso publicado; fim de série nos dois limites.
6. **A saída estrutural precisa de unidade e relógio próprios.** → MRE por operação estrutural; controle sai na
   abertura seguinte à saída intradiária do evento (contraste pareado com parada determinada pelo evento); as mesmas
   entradas com saída fixa × estrutural só como descritivo.

**Nice-to-have aceitos como diagnóstico publicado:** contribuição por moeda e D sem cada moeda; tamanho de cada fatia
do corte; distinguir "evidência contra zero com estimativa ≥ MRE" de "efeito verdadeiro ≥ MRE". **Mantido como
estava:** famílias de Holm separadas por hipótese (ela preferiria uma família de quatro se a decisão fosse "promover
qualquer vencedor"; aqui cada hipótese é julgada por si e nada é promovido).

**Bruto:** `.claude/state/astra-review-H-025-prereg.md` · `.claude/state/r85/prereg_frozen.md` ·
`.claude/state/r85/prereg_with_amendment.md` · `.claude/state/notes-R85.md` §2
**Relacionado:** [[KB-0168-fibonacci-elliott-e-lta-diaria|KB-0168]] · [[KB-0169-fibonacci-e-lta-diaria-no-dado|KB-0169]] ·
[[Fila de Hipoteses]] · [[EXP-0016-trendline-breakout]]

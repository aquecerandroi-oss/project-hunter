**RESUMO**

Testaria primeiro o **3 — universo e normalização**, como diagnóstico de admissão e cobertura; depois **1 — M-D2/M-D5**; por último **2 — contraste de duração**. Sem denominadores e campos comparáveis, o funil pode selecionar diferenças do instrumento. Porém, a alegação de “16% de preços errados” precisa ser corrigida.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Sem testes de código. Conferência dos JSONs por PowerShell: `GETs=17; HTTP200=17`. Não consultei a VPS nem repeti chamadas públicas.

**MUST-FIX**

1. **Normalizador e universo:** o código local rejeita quote diferente de SOL com `UnsupportedQuote` **antes** de converter reservas ([normalize.py:192](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:192)). Trocar “16% de preços errados” por “11/70 fora do contrato SOL; impacto em produção depende da versão implantada”. Os 24% StonkFun são participação **na página observada**, não perda medida do universo-alvo pump. **Falha:** diagnosticar corrupção inexistente e ampliar o escopo por um denominador inadequado.

2. **USGR não comprova estabilização nem distribuição:** 3.932 holders/34 transações contadas é uma divergência a investigar; não prova a origem dos holders. Mudaram endpoint **e** horário. Retirar “impossível nascer de trades”, “assinatura de M-D5” e “graduou no slot”: manter **proxy temporal**. Mcap reportado de US$ 4,6 M com US$ 936 negociados não demonstra liquidez, demanda equivalente ou fraude. ([Rascunho:98](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1030-lane1.md:98)) Na nota diária, “sem compras no meio” exige evidência adicional: a própria tabela registra fita `rate_limited`. ([Nota:518](C:/dev/project-hunter/obsidian/02-MARKET/Meme/2026-09-12.md:518)) **Falha:** calibrar `field_settle_s` com mudança real ou diferença de cobertura.

3. **Zero não equivale a graduação lenta:** há zeros também nas células rápidas e entre Mayhem. “Curva drenada” continua explicação candidata; comparar por quote, Mayhem e idade pós-migração, com referência on-chain. ([Rascunho:107](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1030-lane1.md:107)) **Falha:** classificar mecanismo ou desfecho usando um estado ambíguo.

4. **KOL “subiu” entre recortes, não nos mesmos tokens:** escrever “maior proporção reportada nesta amostra”. As coortes mudam e o contador é opaco; isso não demonstra entrada de KOL antes da graduação. ([Rascunho:59](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1030-lane1.md:59)) **Falha:** introduzir informação pós-graduação numa feature de entrada.

5. **A concordância do item 8 está numericamente errada:** Pnut2 tem `bo` 21,5745→22,7725 (**+1,198 pp**) e `t10` 13,1557→14,1541 (**+0,9984 pp**), acima de ±0,2/0,3 pp declarados. ([Board:1](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane9/08_boards_movers.json:1), [in-memory:1](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane9/17_imc_05_F4UCk5.json:1)) **Falha:** aprovar tolerâncias com uma comparação que as contradiz.

6. **PAD no momento da criação não foi demonstrado:** o board desta rodada foi recebido depois dos clones. Escrever “PAD observado no board após as criações”. ([Rascunho:123](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1030-lane1.md:123)) **Falha:** preencher `parent_on_board_at_create` retrospectivamente, criando look-ahead.

**NICE-TO-HAVE**

Trocar “ritmo dobrou” por **1,83× nesta janela curta**; “preço anterior” por “preço implícito diferente”: a discrepância cambial não identifica sua causa.

**O QUE EU FARIA DIFERENTE**

**M-P29 merece linha própria como extensão prospectiva de M-P3**, testando ganho incremental sobre M-P3/M-P25/M-P26. Congelar identificação do “pai”, board, validade máxima do snapshot e tratamento de múltiplos candidatos. Ausência numa página significa **não observado**, não pai inexistente. Separar conclusão em 24 h de retenção pós-migração; ≥100/30 dias é piso, não garantia de potência.

**CONCORDO COM**

Mayhem como estrato, blocos de dia, conclusão comprovada e três leituras tratadas como exploração da mesma manhã, sem replicação independente.

**OBSIDIAN**

- **Meme — 2026-09-12:** corrigir causalidade, concordância numérica e distinção entre código local e produção.
- **Hipóteses do plantão:** registrar M-P29 como extensão incremental prospectiva e preservar os critérios de identificação de M-D5.
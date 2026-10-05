**RESUMO**

**Concordo com a direção do go/no-go, com ressalvas na justificativa. Veredito do código: REQUEST_CHANGES.**

- **A:** há evidência suficiente para **não aprovar o RPC público observado para 24/7** e avançar para um piloto pago. Não há evidência para atribuir a degradação especificamente ao “horário de pico”, nem para afirmar que pagar resolverá: provedor, rede local e caminho até o endpoint continuam confundidos.
- **B:** concordo em bloquear implantação das ondas **1b/2 até fechar o orçamento**. “Não cabe fisicamente na VPS” não está demonstrado: 152–163 GB são menores que os 207 G livres informados. O problema comprovado é que o volume excede muito a hipótese aprovada, sem dimensionamento confiável de índices, WAL, tabelas auxiliares e margem operacional.
- **Go para 1a e 1c:** faz sentido; são trabalhos úteis enquanto se resolve a infraestrutura.

Há uma divergência de versão: o desenho disponível ainda prevê **3–6 M linhas/dia, 9,5–19 GB e cobrança WS desconhecida**, e a linha 0 ainda descreve a sondagem futura. Revisei os resultados fornecidos contra os artefatos, mas não encontrei a conclusão nova nesses trechos. [Desenho:157](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:157), [linha 0:249](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:249).

**ARQUIVOS**

Nenhuma edição de código ou documentação feita; nenhum commit. Os scripts e testes examinados estão como arquivos novos, não rastreados, no checkout.

**TESTES**

Comando executado:

```text
uv run pytest infra/scripts/tests/test_wallet_tape_probe_core.py infra/scripts/tests/test_wallet_tape_probe_stats.py -q
36 passed in 0.50s
```

Executei o leitor com `python -B ... --run <dir>`:

- **run1:** imprime as tabelas iniciais e termina com `KeyError: 'truth'`.
- **run2:** conclui; reproduz **6314/6320**, **17373/17373** e seis ausências de transações falhas.
- **run3:** imprime as tabelas iniciais e termina com `ZeroDivisionError: division by zero`.

Também reproduzi, em memória, os defeitos abaixo. Lint, typecheck e escrita real em Postgres não foram executados.

**MUST-FIX**

1. **MEDIUM — Leitor incompatível com duas das três corridas e cortes temporais diferentes.**  
   O acesso obrigatório a `audit["truth"]` quebra no run1; dividir por `blocks_ok=0` quebra no run3. Além disso, os contadores vêm do snapshot selecionado, mas a auditoria vem do resumo final, cortada por uma heurística de salto de 2.000 slots. **Cenário:** um relatório chamado “janela válida” incorpora auditoria posterior ao corte ou termina incompleto. Tratar formatos antigos/ausência de auditoria explicitamente e identificar a janela de cada resultado. [Leitor:90](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe-read.py:90), [111](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe-read.py:111), [125](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe-read.py:125).

2. **HIGH — O fechamento viola a espera de 180 s.**  
   `final=True` reduz a espera para **30 s**, depois de interromper os leitores. Reproduzi um bloco de 40 s entrando como julgado, com ausências, em vez de censurado. **Cenário:** entrega atrasada em 80 s seria aceita durante a corrida, mas vira perda quando cai perto do encerramento. Manter 180 s e censurar os imaturos, ou encerrar novas amostras antes e continuar recebendo até maturarem. Os 74 blocos não podem ser descritos genericamente como “todos julgados após 180 s” pelo contrato atual. [Auditoria:38](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_audit.py:38), [encerramento:219](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_net.py:219).

3. **MEDIUM — Retentativas apagam downtime.**  
   Cada `on_disconnect` sobrescreve `down_since`. Reprodução: queda em t=10, retentativa falha em t=20 e primeiro log em t=30 → **10 s registrados, quando foram 20 s**. **Cenário:** indisponibilidade prolongada parece menor e distorce as taxas por tempo ativo. Preservar o início da queda enquanto ela estiver aberta. [Stats:127](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:127).

4. **HIGH — Uma auditoria contaminada pode sair como limpa.**  
   `_tainted` verifica instantes de desconexão e queda ainda aberta, sem guardar o intervalo completo da indisponibilidade. Reprodução: queda **[10,300]**, fetch em 200 e julgamento em 380 → `False`. **Cenário:** o bloco atravessa a indisponibilidade, mas a conexão voltou antes do julgamento e a queda começou antes do limite inferior. Usar interseção de intervalos; incluir suspensão explicitamente. [Auditoria:23](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_audit.py:23).

5. **MEDIUM — A deduplicação pode contar novamente entregas muito atrasadas.**  
   A assinatura é esquecida após a janela de 60 s. Reproduzi duas assinaturas distintas virando **três transações únicas** quando uma chega pela segunda assinatura depois da expiração. **Cenário:** atraso assimétrico entre pump/PumpSwap infla eventos, atividade e extrapolação. Isso importa justamente para medir um feed degradado; não demonstrei que alterou materialmente as corridas limpas. [Stats:171](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:171), [178](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:178), [257](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:257).

6. **HIGH para o orçamento — A fórmula de linha conta colunas duas vezes.**  
   A parcela fixa já inclui `block_time`, `received_at`, `program`, ordinal, `venue` e `side`; o laço soma novamente esses campos presentes em `swap_row`. Também trata `received_at` como texto na segunda passagem. **Cenário:** os **342/593 B** fundamentam uma decisão de capacidade como se representassem o schema físico, quando a fórmula não o representa. Corrigir a modelagem por tipo; antes do go, medir tabela e índices reais. Outros custos omitidos podem compensar ou superar esse excesso: não basta descontá-lo e declarar capacidade. [Fórmula:66](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_math.py:66), [campos:82](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_math.py:82).

**NICE-TO-HAVE**

- **Proveniência:** registrar versão do coletor, argumentos, corte, horário do fetch/julgamento e amostras de desempenho. O leitor usa **3,73 como default**, enquanto o resumo antigo do run2 contém taxas calculadas com 2,5 slots/s. Os **31,25 M/dia** são reproduzíveis aplicando 3,73 aos 75 blocos, mas essa taxa precisa acompanhar sua evidência original. [Leitor:47](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe-read.py:47), [run2:4](C:/dev/project-hunter/.claude/state/carteiras-lucro/probe/run2/summary.json:4).
- Corrigir o início do run3: o artefato registra **22:46:42Z**, não 22:43Z. [Run3:113](C:/dev/project-hunter/.claude/state/carteiras-lucro/probe/run3/summary.json:113).
- “53%” descreve **transações únicas observadas classificadas como `neither`**, não diretamente notificações. E “oito robôs” deveria ser “oito carteiras com ≥500 swaps”: frequência não prova identidade operacional. [Classificação:183](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:183), [concentração](C:/dev/project-hunter/.claude/state/carteiras-lucro/probe/run3/summary.json:173).
- O achado de versão 1 merece reprodução própria com resposta RPC preservada. Confirmei o limite `0` nos dois consumidores; não confirmei independentemente os **13%**. [tx_rpc.py:191](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:191), [rpc_wallet.py:82](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_wallet.py:82).

**O QUE EU FARIA DIFERENTE**

Escreveria o aceite como **“público reprovado nesta configuração; pago candidato a piloto; armazenamento sem capacidade aprovada”**. O piloto deve rodar no ambiente pretendido, atravessar pelo menos um ciclo diário e medir cobertura, atraso, reconexão/recuperação, custo faturado e escrita real.

As contas, tomando os intervalos informados e **GB decimais**, são:

| Conta | Resultado |
|---|---:|
| 330–353 swaps/s × 86.400 | 28,512–30,499 M eventos/dia |
| A 350 B/linha, por 9 dias | 89,81–96,07 GB |
| A 593 B/linha, por dia | 16,91–18,09 GB |
| A 593 B/linha, por 9 dias | **152,17–162,77 GB** |
| 217–254 GB/dia × 30 dias × 20 créditos/MB | **130,2–152,4 M créditos/mês** |

Portanto, a aritmética está essencialmente correta; a incerteza principal é a **premissa física de 593 B**, não a multiplicação.

No Business, a conta é `US$499 + max(créditos − 100 M, 0) × US$5/M`: **US$650–761/mês**, supondo os 100 M disponíveis para esse uso, mês de 30 dias e sem outros consumos. Cobrança por bytes descomprimidos e tarifas conferem na [documentação de créditos](https://www.helius.dev/docs/billing/credits) e na [tabela de preços](https://www.helius.dev/pricing).

Com 3,73 slots/s, **5 slots ≈1,34 s**, não 2 s. Corrigiria a equivalência, preservando a distinção entre um cenário definido em slots e uma latência medida em segundos. [Desenho:24](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:24).

**CONCORDO COM**

- **Snapshot 90 é um corte honesto:** o intervalo salta de **5407,8 para 10059,1 s** entre os snapshots 90 e 91. O critério é uma interrupção objetiva, e o trecho preservado continua mostrando degradação. Chamaria de **“90,1 min anteriores à suspensão, com feed degradado”**. Não chamaria o resumo final de referência para essa mesma janela. [Snapshots:90](C:/dev/project-hunter/.claude/state/carteiras-lucro/probe/run1/snapshots.jsonl:90).
- Os **28% do run1 não demonstram 72% de perda definitiva**: a auditoria antiga confundia atraso com ausência.
- O run2 sustenta boa entrega na amostra e **1099/1099 igualdades de contagem**, não garantia de completude 24/7 nem identidade integral dos eventos. [Run2:65](C:/dev/project-hunter/.claude/state/carteiras-lucro/probe/run2/summary.json:65).
- Concentração e tamanhos justificam estudar alternativas de armazenamento; não justificam aplicar imediatamente um filtro que possa apagar compras, vendas pequenas ou estados necessários à contabilidade.

**OBSIDIAN**

- **wallet-tape-probe** — acrescentar resultados desta revisão, reproduções e limites do julgamento final.
- **EXP-M15-carteiras-vencedoras** — registrar as três janelas, cortes e resultados como avaliação de infraestrutura.
- **carteiras-lucro-design** — substituir o orçamento antigo e distinguir piloto aprovado de operação aprovada.
- **KB-0134-websocket-do-rpc-lag-medido-ao-vivo** — distinguir a sondagem por mint da coleta do programa inteiro.
- **Open Bugs** — registrar downtime, taint, fechamento antecipado e investigação de transações versão 1.
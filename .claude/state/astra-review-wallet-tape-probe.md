**RESUMO**

**A sondagem é útil para descobrir ordem de grandeza e defeitos do instrumento; sozinha, não sustenta o go de armazenamento/RPC 24/7.** Eu corrigiria a contabilidade de disponibilidade e preservaria uma amostra independente de cobertura antes das 2 h.

O smoke informado já exige rever o orçamento: **309 swaps/s constantes equivaleriam a 26,70 milhões de linhas/dia, 9,34 GB/dia e 84,10 GB em nove dias**, usando os mesmos 350 B/linha do desenho. É um cenário aritmético, não uma previsão diária; ainda exclui WAL, lotes, evidências preservadas e margem. O desenho pressupõe 3–6 milhões/dia e 9,5–19 GB em nove dias ([desenho:151](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:151)).

Revisão como `quant-engineer`, alinhada à lição já registrada em [KB-0149:65](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:65): falha silenciosa de infraestrutura muda o resultado da pesquisa.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Revisei o desenho, os quatro módulos indicados, o auxiliar matemático e os dois arquivos de testes.

**TESTES**

Não executei pytest nem a sondagem nesta revisão. Os números do smoke são os fornecidos por você, não resultados reproduzidos por mim. Conferi por leitura os testes, o IDL local e a documentação oficial de Solana/PumpSwap/Helius; calculei as projeções acima.

**MUST-FIX**

**1. Cobertura: a comparação entre assinaturas é um diagnóstico condicional, não um estimador da perda total do RPC.**

O código reconhece “deveria chegar nas duas” pelos programas invocados nos logs **já recebidos**, e classifica a entrega quando expira a deduplicação ([stats:163](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:163), [stats:238](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:238)).

A interpretação defensável é:

> Entre transações observadas por pelo menos uma conexão, cujos logs mostram os dois programas, quantas chegaram também pela outra?

**Cenário de falha:** o provedor perde um bloco nas duas conexões. A discordância pode continuar em zero enquanto centenas de swaps somem. Também há seleção: transações com os dois programas não representam necessariamente as que usam apenas um. Duas conexões ao mesmo serviço têm causas comuns de perda; não aplicaria captura–recaptura supondo independência.

Além disso:

- `mentions` é mais amplo que “invocou”; seu denominador é um subconjunto das entregas esperadas pelo filtro oficial de [logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe).
- Logs truncados podem esconder a segunda invocação.
- As duas assinaturas precisam estar confirmadas e ativas simultaneamente; início, reconexões e término exigem censura.
- O fechamento força a expiração com `flush(now + 120)`, sem conceder tempo real para a segunda cópia chegar ([probe:291](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe.py:291)).

**Exigência:** publicar essa métrica como **discordância de entrega no subconjunto observado**. Para estimar perda total, sortear slots independentemente do WS e reconciliar posteriormente os blocos finalizados, preferencialmente por outra infraestrutura, distinguindo transações, eventos e perdas locais. Preservar as assinaturas/eventos recebidos nesses slots antes da corrida; contadores agregados não permitem reconstruir isso depois.

**2. Os 55/55 verificam contagens entre representações, não completude nem identidade dos eventos.**

A seleção exige transação recebida, bem-sucedida **e com algum evento reconhecido**, passa por sorteio de 1% e por uma fila limitada; a comparação usa contagens por programa/tipo ([probe:155](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe.py:155), [probe:178](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe.py:178), [core:206](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_core.py:206)).

**Cenário de falha:** truncamento elimina todos os eventos de uma transação. Ela nunca entra na amostra. Ou chega um evento diferente do esperado, mas do mesmo tipo: a contagem continua igual.

**Exigência:** separar duas auditorias:

- **Completude de entrega:** amostra independente por slots/blocos.
- **Fidelidade dos eventos entregues:** comparar payloads e ordem por programa, incluindo amostras com zero evento, logs longos/truncados, roteadores e ambos os programas.

Os 55/55 são encorajadores. Mesmo sob uma hipótese ideal de amostra independente, zero divergências em 55 ainda permite aproximadamente **5,3% de divergência no limite unilateral de 95%**. Essa conta não estima perda do RPC.

**3. A disponibilidade pode parecer melhor do que foi — corrigiria antes das 2 h.**

Há três pontos concretos:

- Erro de assinatura é contado, mas não encerra a conexão; `slotSubscribe` pode continuar alimentando o socket sem nenhum log ([probe:133](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe.py:133)).
- `downtime_s` fecha quando o socket conecta, antes do ACK e do primeiro log; uma queda ainda aberta no término não entra nesse acumulado ([stats:110](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:110)).
- Todas as tasks são canceladas no término, sem drenagem das filas; os bytes são contados pelo consumidor, depois da fila ([probe:128](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe.py:128), [probe:291](C:/dev/project-hunter/infra/scripts/research/2026-10-05-wallet-tape-probe.py:291)).

**Cenário de falha:** a assinatura de logs é recusada, slots continuam chegando e o relatório dilui poucos eventos pelas 2 h inteiras, sugerindo tráfego barato. Ou a conexão cai perto do fim e o downtime publicado omite justamente essa indisponibilidade.

**Exigência:** medir por programa tempo com assinatura aceita, tempo sem dados, intervalo suspeito desde o último log, recuperação até o primeiro log, indisponibilidade aberta no término e fila residual. Publicar taxas por **tempo total** e por **tempo observado ativo**. Contar bytes na recepção e separar recebidos, processados e descartados.

O timeout aos 55 s é evidência de interrupção; ainda não identifica se a causa foi provedor, rede ou atraso do event loop.

**4. Lag HTTP é razoável como defasagem da ponta observada, não como latência de entrega.**

**Sim**, `getSlot(confirmed)` é uma referência melhor que depender apenas do relógio transportado pelo próprio WS. Os 55 deltas zero sustentam usar `context.slot` como slot da transação nessa amostra.

Mas a métrica atual compara a ponta HTTP com **o slot da última mensagem processada**, que pode retroceder quando mensagens chegam fora de ordem ([stats:96](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:96), [stats:156](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:156)). E [slotSubscribe](https://solana.com/docs/rpc/websocket/slotsubscribe) informa slots processados pelo validador, sem configuração de commitment; não é uma segunda ponta `confirmed`.

**Cenário de falha:** chegam alguns logs recentes rapidamente e muitos antigos atrasados — ou parte dos logs nunca chega. A ponta parece atual, embora a entrega esteja incompleta ou sua cauda seja ruim.

**Exigência:** reportar separadamente:

- `HTTP confirmed − maior slot recebido`, como frescor da ponta;
- idade do último log por programa;
- RTT, horários de início/fim e indisponibilidade do poll HTTP;
- idade da fila local e atraso por evento, quando houver referência adequada.

HTTP e WS no mesmo provedor são caminhos diferentes, mas **não fontes independentes de saúde**. Manter diferenças negativas visíveis. Poll de 5 s ajuda a detectar atraso sustentado; não prova p99 subsegundo nem cumprimento do cenário de cinco slots.

**5. Heaps pode ser cenário exploratório; o “limite superior linear” não é limite superior.**

A projeção usa a descoberta marginal do último quarto para construir o campo `wallets_day_upper_linear_at_last_quarter_marginal_rate` ([report:28](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_report.py:28)).

**Cenário de falha:** duas horas dominadas pelos mesmos bots produzem curva achatada. Mais tarde entram novas carteiras, outra região ou um lançamento movimentado. O total diário ultrapassa o suposto teto.

Minha resposta à pergunta 4: **publicaria como resultado principal apenas as curvas de carteiras distintas por tempo e por número de swaps**, separadas por programa e grau de validação da identidade. Heaps e extensão linear podem aparecer como cenários condicionais, sem linguagem de intervalo de confiança ou teto.

O total observado é limite inferior apenas para um período que contenha a janela e **com identidades válidas**. Não é piso de um “dia típico”. O ajuste de pontos cumulativos também não cria observações independentes.

**6. Offset 152 está apoiado pelo IDL; a carteira ainda precisa de validação semântica.**

Conferi: no [IDL oficial de BuyEvent](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump_amm.json), há discriminador, timestamp, 13 `u64`, `pool` e `user`: **pool em 120 e user em 152**. Portanto, não encontrei fundamento para afirmar que o offset atual está errado.

O risco está na validação: basta haver comprimento suficiente para converter aqueles bytes em endereço ([core:169](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_core.py:169)). O teste verifica presença e comprimento, não igualdade com a carteira esperada ([test_core:76](C:/dev/project-hunter/infra/scripts/tests/test_wallet_tape_probe_core.py:76)). Depois, essas identidades entram no total usado por Heaps ([stats:255](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:255)).

**Cenário de falha:** um layout incompatível produz uma chave Base58 plausível; ou `user` é uma autoridade intermediária de roteador e é interpretado como investidor final. A contagem de carteiras fica inflada ou fundida indevidamente.

**Exigência:** fixar a versão/hash do IDL e conferir `user`/`pool` contra as contas da instrução correspondente em fixtures de compra direta e roteada. Não basta comparar com o fee payer. Até isso, manter a curva inferida separada da validada. Não é necessário antecipar todo o decoder financeiro da onda 1a para validar esses dois campos.

**7. GB/dia e custo operacional precisam incluir o que a sondagem não mede.**

O tamanho Postgres é uma fórmula aproximada, não uma inserção medida ([math:57](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_math.py:57)). A média vem apenas dos eventos decodificados e é aplicada também às compras cruas ([stats:230](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:230), [report:67](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_report.py:67)).

**Cenário de falha:** aprovar o disco pela estimativa e descobrir depois que índices reais, WAL, retenção atrasada, lotes e `fills_kept` ultrapassam a capacidade. Ou aprovar RPC apenas pelo WS e descobrir que resolução de pools e recuperação de lacunas dominam o consumo.

Para responder à pergunta 6, exigiria estes números antes do **go 24/7**:

| Área | Números necessários |
|---|---|
| Tráfego | Notificações, swaps e bytes por programa; sucessos/falhas; duplicados; média e p95/p99/máximo em janelas de 1 s e 1 min; incluir segundos sem eventos. |
| Cobertura | Denominador independente, ausências por programa/slot, eventos truncados/desconhecidos, disponibilidade, lacunas abertas e duração da recuperação. |
| Processo e banco | CPU, RSS, idade/bytes da fila, atraso do event loop, throughput e latência de escrita na VPS; bytes reais por linha/índice e WAL por evento. |
| Retenção | Projeção para nove dias **mais atraso do job de poda**, lotes abertos, `fills_kept`, outras tabelas e margem de disco. |
| RPC auxiliar | Pools novos/hora, acerto do cache, leituras de contas, auditoria, financiadores e chamadas/tempo necessários para recuperar uma interrupção. |
| Liquidez | Pools com mudanças sem swap, frequência e períodos de reservas inválidas; custo de acompanhar estado ou fração que exigiria censura. |
| Custo | Créditos/dia e mês, consumo atual compartilhado, folga, excedentes e comportamento ao esgotar a cota. |

A medição atual de liquidez classifica por **transação**, não por pool, e cruza os payloads amostrados com pools vistos na janela ([stats:184](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:184), [report:15](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_report.py:15)). Um depósito na pool A junto com swap na B não prova que A teve seu estado atualizado por swap.

**Helius:** a documentação consultada cobra WebSocket por dados descomprimidos: **2 créditos/0,1 MB**, aproximadamente **20 mil créditos/GB**. Assim, se `B` for o tráfego total em GB/dia, o cenário mensal de 30 dias é **600 mil × B créditos**, antes de HTTP. Contar também falhas e entregas duplicadas entre assinaturas; a deduplicação local não reduz bytes recebidos. [Cobrança oficial](https://www.helius.dev/docs/billing/credits).

A tabela atual anuncia Developer por **US$49/mês, 10 milhões de créditos**, e créditos adicionais a **US$5/milhão**. Isso não informa a folga da conta de vocês; o relatório precisa confrontar a projeção com o plano e o consumo efetivos. [Preços oficiais](https://www.helius.dev/pricing).

**NICE-TO-HAVE**

- Curvas por blocos de 10 minutos, incluindo taxa de descoberta e distribuição de tamanho dos logs.
- Comparação simultânea público/Helius em janelas sorteadas, sem tratar concordância entre ambos como prova absoluta de completude.
- Manifesto com hash do código/IDL, UTC, configuração e semente; tamanho e composição de cada amostra.
- Testes para rejeição de assinatura com slots vivos, queda no término, mensagens fora de ordem, segunda cópia tardia e igualdade exata de `user`/`pool`.

**O QUE EU FARIA DIFERENTE**

Dividiria o aceite em duas decisões:

1. **Após 2 h:** instrumento confiável o suficiente, ordem de grandeza conhecida e orçamento preliminar. Corrigir antes a disponibilidade e preparar a auditoria por slots.
2. **Antes da onda 2 operar continuamente:** pilotar no provedor e ambiente pretendidos, cobrindo pelo menos um ciclo diário e depois horários/dias distintos; provar escrita, recuperação e custo com margens explícitas.

As 2 h podem produzir um **no-go econômico** se até o cenário observado já estourar o orçamento. Não produzem sozinhas um **go operacional**: desconhecem sazonalidade, perdas comuns às conexões, picos raros, persistência e recuperação.

**CONCORDO COM**

- Atribuir eventos pela pilha de invocação, não pelo canal que entregou a transação ([core:97](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_core.py:97)).
- Separar falhas de transação dos eventos úteis e deduplicar entregas entre canais ([stats:163](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:163)).
- Manter BuyEvent explicitamente cru e usar os decodificadores existentes para TradeEvent/SellEvent ([core:159](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_core.py:159)).
- Usar HTTP `confirmed` como indicador adicional de frescor.
- Sondar no público para aprender volume; a própria [Solana não recomenda seus endpoints públicos para produção](https://solana.com/docs/references/clusters).

**OBSIDIAN**

- **carteiras-lucro-design** — acrescentar esta revisão: cobertura condicional, limitações de lag/Heaps e critérios de aceite do coletor.
- **KB-0182 — Quem ganha dinheiro de verdade nos memes** — atualizar o orçamento preliminar e separar cenário do smoke de estimativa diária validada.
- **EXP-M15 — seguir carteiras vencedoras** — registrar o protocolo de auditoria de cobertura e os critérios de contaminação antes do aquecimento, preservando o histórico.
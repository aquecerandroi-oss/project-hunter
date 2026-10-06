**RESUMO**

**REQUEST_CHANGES no instrumento e na leitura antes de declarar “antecipa/empata/atrasa”.** A direção da pesquisa é válida, mas há erros capazes de favorecer qualquer lado.

O principal já apareceu: na captura parcial de `run1`, NATS trouxe trades `pump_amm`, enquanto o RPC assina somente `pump`. Também há problemas na reconstrução de assinaturas após reconexão, na classificação de reprise e na supervisão das tarefas.

Assumi `code-reviewer`. A leitura considera a memória de [KB-0183](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar.md), sobre instabilidade do RPC público, e [KB-0149](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md), que separa velocidade de vantagem econômica.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Não li `.env`, não fiz commit nem interferi na corrida. Revisei os dez módulos indicados, os sete arquivos de testes e os artefatos disponíveis.

**TESTES**

Não executei pytest: os testes de IO usam `tmp_path` e gravam arquivos, contrariando o modo OPINIÃO desta sessão. O leitor também escreve `report.json`; portanto, não o executei ([leitura:155](/C:/dev/project-hunter/infra/scripts/research/2026-10-06-pumpfun-realtime-latency-read.py:155)).

Executei consultas somente leitura com `Get-Content`, `ConvertFrom-Json` e `Group-Object`. Resultados reais:

```text
smoke/report.json:
window_s = -2.9533121585845947
create.coverage.union = 0
trade.coverage.union = 0

run1 — leitura parcial às 2026-10-06T03:34:05Z:
nats_u.trade = 2857
trade_program.pump = 2015
trade_program.pump_amm = 842
```

O primeiro `pump_amm` está em [run1/events.jsonl:3933](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run1/events.jsonl:3933). Esses números são contagens parciais de mensagens, **não resultados dos 45 minutos nem contagens de trades únicos**.

**MUST-FIX**

1. **HIGH — O denominador compara programas diferentes.**

   O RPC usa `mentions=[PUMP]`, mas `_trades()` admite todos os trades NATS, sem filtrar `program` ([feeds:218](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:218), [report:124](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:124)).

   **Cenário:** a moeda graduou durante os seis minutos; NATS continua entregando `pump_amm`, mas uma transação exclusivamente PumpSwap não pertence à assinatura RPC. Ela vira ausência do RPC na cobertura. Os 842 frames citados demonstram que a mistura ocorre nesta corrida.

   **Correção:** separar `pump` e `pump_amm`. No contraste atual, usar somente `pump` dos dois lados. PumpSwap fica “sem referência equivalente”, até haver coleta específica autorizada. PumpPortal gratuito, nesta sonda, compara criações/migrações; não compara trades ([feeds:199](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:199)).

2. **HIGH — Reconexão reescreve retroativamente a exposição e a reprise.**

   `_subs()` conserva apenas o último `sub` por mint, depois aplica os `unsub`; carteiras também ficam somente com a última assinatura ([report:100](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:100)).

   **Cenário:** assinatura em 100, trade legítimo em 150, reconexão e nova assinatura em 200. O relatório passa a considerar 200 como início único: descarta o RPC de 150 e classifica o trade NATS antigo como reprise. Uma queda perto do fim pode apagar estatisticamente minutos saudáveis.

   **Correção:** reconstruir uma lista cronológica de intervalos por conexão/subject. Cada evento deve usar o intervalo correspondente ao seu recebimento. Registrar recusas e desconexões como término de exposição, distinguindo interrupção de perda durante conexão saudável.

3. **HIGH — `bt < sub_t − 2 s` não prova reprise e usa relógios incompatíveis.**

   `_is_replay()` compara `bt` diretamente ao horário local da assinatura, sem o offset que `_trades()` recebe ([report:117](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:117)).

   **Cenários:** relógio local adiantado elimina evento fresco; um evento antigo entregue com atraso real vira “reprise”, retirando justamente a cauda lenta de NATS; histórico dos últimos dois segundos passa como transmissão ao vivo.

   **Correção:** chamar isso de **“evento anterior à assinatura segundo o timestamp, sujeito a incerteza”**, mantendo classes “anterior”, “compatível com pós-assinatura” e “ambíguo”. Corrigir relógios e apresentar sensibilidade à margem, sem escolher a que favorece NATS. Para afirmar reprise, procurar evidência adicional de duplicata/evento previamente observado.

   A resolução de um segundo não implica erro total limitado a um segundo: `getBlockTime` fornece uma **estimativa** baseada nos timestamps dos validadores. A nota atual atribui precisão excessiva ao truncamento ([report:28](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:28); [documentação Solana](https://solana.com/docs/rpc/http/getblocktime)).

4. **HIGH — A elegibilidade temporal é assimétrica.**

   O RPC entra conforme **seu próprio recebimento** cair entre assinatura e desassinatura + 5 s; NATS entra pelo recorte global e filtro de reprise. `sub` é registrado antes do envio, sem comprovação de aceitação ([report:130](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:130), [feeds:92](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:92)).

   **Cenário:** RPC entrega uma transação imediatamente antes do `SUB`; NATS a entrega depois, dentro da tolerância de reprise. A leitura exclui a chegada vencedora do RPC e registra NATS sozinho. Na saída, um RPC mais de cinco segundos atrasado desaparece do par.

   **Correção:** definir uma coorte comum de transações/mints em intervalos elegíveis; procurar os correspondentes numa janela de recebimento ampliada e simétrica. Bordas sem contraparte observável devem ser censuradas, não tratadas automaticamente como perda. Publicar separadamente descoberta→assinatura e assinatura→primeiro evento.

   A população continua sendo **moedas descobertas por NATS e admitidas pelo cap**, não todas as moedas recém-criadas: esse recrutamento ocorre exclusivamente no hook NATS ([feeds:179](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:179)).

5. **HIGH — “Mesma assinatura” identifica transação, não necessariamente o mesmo trade ou saldo.**

   `first_seen()` colapsa tudo por assinatura; o relatório de saldo também ignora carteira/mint ao casar ([stats:38](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_stats.py:38), [report:139](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:139)).

   **Cenário:** uma transação contém trades em duas moedas ou alterações em duas carteiras acompanhadas. O primeiro saldo recebido da carteira A pode contar como entrega do trade da carteira B. Dois trades viram uma observação.

   **Correção:** para esta pesquisa, a solução mínima é declarar **“primeira notícia da transação”**, restringindo ambos os lados à mesma população. Para afirmar latência do trade, preservar identidade de evento/perna — assinatura, programa, mint e discriminador adicional quando necessário. Para cobertura de saldo, exigir a carteira correspondente e explicitar se SOL ou token é suficiente.

   Para criações simples, assinatura é uma boa chave. Para trenches, mint é adequado apenas a **“primeira inclusão no board”**, não a trade. Snapshots descartam as identidades das entradas, portanto uma moeda entregue no snapshot após reconexão pode parecer ausente ([conv:84](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_conv.py:84)).

6. **HIGH — Uma falha de envio pode matar a expiração sem deixar a corrida marcada como degradada.**

   `ready/ws` não são invalidados explicitamente ao desconectar; `expiry()` chama `unsub()` sem tratar erro. `run_nats()` reúne as tarefas com `gather`, e o runner só recolhe seus resultados no encerramento, com `return_exceptions=True`, sem examiná-los ([feeds:98](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:98), [feeds:190](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:190), [runner:102](/C:/dev/project-hunter/infra/scripts/research/2026-10-06-pumpfun-realtime-latency.py:102)).

   **Cenário:** conexão cai; a expiração remove mints do plano; o primeiro `UNSUB` no socket fechado lança exceção. Os demais subjects ficam em `desired`, embora já tenham saído do plano, e podem ser reassinados. A tarefa de expiração terminou, mas os outros leitores podem continuar e o runner espera os 45 minutos.

   **Correção:** invalidar o estado da conexão, separar alteração do conjunto desejado do envio no socket, supervisionar todas as tarefas e registrar término inesperado imediatamente. Falha de CORE também não deveria provocar queda de UNIFIED por exceção propagada pelo hook.

7. **MEDIUM — O smoke não valida a análise; as bordas também censuram deltas.**

   Os cortes fixos são 90 s + 15 s, sem rejeitar janela vazia ([report:25](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:25), [report:215](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:215)). O resultado negativo está gravado em [smoke/report.json:3](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/smoke/report.json:3).

   **Cenário:** o smoke recebe milhares de mensagens, mas todas as estatísticas ficam vazias; isso pode ser confundido com pipeline analítico validado. Numa corrida longa, recortar cada fonte separadamente também transforma pares que cruzam a borda em exclusivos ([report:75](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:75)).

   **Correção:** rejeitar `t1 <= t0`; usar smoke suficientemente longo; selecionar a coorte numa janela interior e buscar contrapartes nas margens.

**NICE-TO-HAVE**

- **Instrumentar fila e separar captura de processamento.** Há `max_queue=None`, parsing e escrita síncrona entre recebimentos ([io:136](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:136), [io:46](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:46)). Sob rajada, backlog pode crescer e o próximo `recv` recebe carimbo tardio. Carimbar antes do parse protege aquela mensagem, não as seguintes. Recomendo fila limitada, contadores de saturação e timestamps monotônicos além do UTC; segmentos saturados não sustentam comparação fina. A biblioteca confirma que `max_queue=None` desativa o controle de fluxo ([websockets](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html)).

- **Melhorar exclusão de congelamentos.** O watchdog identifica saltos acima de 3 s; `drop_stalls()` exclui somente timestamps dentro do intervalo ([io:79](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:79), [stats:52](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_stats.py:52)). Mensagens acumuladas podem ser consumidas depois do fim e sobreviver ao filtro. Nesse cenário, é preciso marcar também a drenagem; “sem stalls” não comprova ausência de backlog.

- **UTC e dinheiro:** rejeitar ISO sem timezone, pois `astimezone(UTC)` interpreta o horário ingênuo conforme a máquina ([conv:30](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_conv.py:30)). Não encontrei aritmética financeira nesta sonda; `amountSol` é repassado e a fixture usa string ([conv:59](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_conv.py:59), [teste:53](/C:/dev/project-hunter/infra/scripts/tests/test_pumpfun_rt_probe_conv.py:53)). Preservar texto exato ou `Decimal` se o campo passar a ser calculado.

- **Preservar capturas existentes.** `Recorder` abre `events.jsonl` com `"w"` ([io:40](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:40)). Reexecutar com o mesmo `--out` trunca a evidência anterior. Recusar destino já utilizado.

**O QUE EU FARIA DIFERENTE**

Manteria esta corrida como captura exploratória, corrigiria primeiro a leitura e separaria três perguntas: **descoberta da moeda**, **primeira notícia da transação** e **disponibilidade dos campos necessários para decidir**.

Para **(a)**, não presumiria que RPC público é lento “por natureza”. Ele é um endpoint concreto numa rota concreta. Compararia depois com o baseline efetivamente usado na VPS, no mesmo host e compromisso, sem expor credenciais. A ordem inicial das assinaturas é secundária após aquecimento; a assinatura dinâmica de cada mint é parte relevante do atraso. `ping_interval=20` é heartbeat, não intervalo de entrega; afeta detecção de falha, não impõe vinte segundos aos eventos.

Para **(f)**, **p10/p50/p90 e percentual de primeiras chegadas são necessários, mas insuficientes**. Exigiria também:

- `n` de pares, exclusivos, censurados e ambíguos; cobertura sobre a união observada, sem chamá-la de completude da cadeia.
- Tempo saudável por fonte, reconexões, programas, mints e concentração por mint/período.
- Uma tolerância de empate declarada antes da leitura confirmatória. Hoje o cálculo usa apenas `delta < 0`, sem região de empate ([stats:58](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_stats.py:58)).
- Repetição em outros horários/dias e na VPS antes de generalizar.

A frase aceitável seria:

> “Nesta janela e nesta máquina, entre as transações elegíveis observadas pelas duas fontes, NATS chegou antes do RPC público em X%, com deltas p10/p50/p90 de […]. A cobertura observada foi […]. Não medimos ainda o ganho no caminho de decisão e execução da VPS.”

“Empata” exige uma margem de equivalência; resultado incerto deve ser **inconclusivo**. E “chegou antes” não demonstra “conseguimos operar antes”: faltam processamento útil, decisão, submissão e inclusão da própria ordem. Isso deve ser uma medição posterior, sem ativar dinheiro real.

**CONCORDO COM**

- Comparar chegadas no mesmo processo é uma boa base: **offset constante** cancela nos deltas. Ajuste do relógio durante o par não cancela.
- A configuração oculta a senha no `repr`; o teste verifica sua ausência no `events.jsonl` do cenário normal ([nats:31](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_nats.py:31), [teste:100](/C:/dev/project-hunter/infra/scripts/tests/test_pumpfun_rt_probe_feeds.py:100)). Isso não constitui auditoria universal de todos os erros e arquivos.
- O laço para em recusas HTTP explícitas e em `Refused`, sem retry; a reconexão comum é sequencial ([io:154](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:154)). Não encontrei nesse caminho um laço silencioso de HTTP 429.
- Caps e ausência de ordens são adequados à pesquisa. Apenas corrigiria a descrição “nunca wildcard”: CORE usa um wildcard **limitado ao último componente de cada carteira**, exatamente como o desenho informado ([sel:70](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_sel.py:70)).

**OBSIDIAN**

Nenhuma página foi alterada. Recomendo:

- **Fontes REA** — registrar acesso anônimo observado aos subjects NATS, distinguindo autenticação técnica de login pessoal.
- **Nova revisão “pumpfun-realtime-latency”** — registrar estes bloqueios, os cenários e a versão corrigida do instrumento.
- **KB-0183 — O que custa coletar o programa inteiro** — acrescentar comparação por endpoint/programa e limitações de cobertura.
- **pumpfun-releitura** — acrescentar a descoberta posterior sobre NATS, preservando o registro anterior.
- **Fila de Hipóteses** — registrar a sonda como validação de fonte; latência favorável ainda não confirma hipótese de operação lucrativa.
## RESUMO

**Eu ainda não declararia a autonomia paper pronta.** O veredito principal do placar permanece separado do replay, mas o caminho de replicação tem inconsistências capazes de antecipar maturidade e carimbar `promising_at` com evidência histórica. **“Inconclusivo” no EXP-0006 está correto.** O T3.28a tem uma direção defensável, mas a implementação em andamento apenas amplia o limite compartilhado do SSR.

Esta é uma revisão do código local e das leituras registradas em 08/09, não uma nova medição da VPS.

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit; nenhum `.env` acessado. Considerei também os arquivos em edição no workspace, especialmente o T3.28a.

## TESTES

Não executei suítes, migrações ou consultas à VPS. Fiz inspeção estática dos caminhos e testes existentes. Portanto, os números operacionais abaixo são **evidências registradas**, não resultados reproduzidos nesta revisão.

## MUST-FIX

### 1. Replay/replication: o placar principal está isolado, mas a replicação não está inteiramente protegida

**HIGH — a CLI pode tornar o pai “promissor” usando replay.** A consulta do worker filtra versão e resultado terminal, **sem filtro de coorte**. `replicate()` usa esse relatório para autorizar a rodada e gravar `promising_at`. Cenário: prospectivo pequeno ou negativo, replay positivo com 100 resultados/30 dias; a CLI aceita a replicação sem `--force-research` e congela um marco que deveria nascer exclusivamente do prospectivo. A correção feita na API não fecha esse outro escritor. Referências: [replication_stats.py:69](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replication_stats.py:69), [replication.py:257](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replication.py:257), [replication.py:296](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replication.py:296).

**HIGH — “avaliável” tem duas definições.** O placar exige saída até `as_of` **e horizonte completo transcorrido**; a replicação da API exige apenas emissão até `as_of`, terminal e R não nulo. Cenários:

- Uma leitura histórica inclui resultado encerrado **depois** do corte.
- No corte atual, saídas rápidas entram antes das operações cujo horizonte ainda está aberto, enviesando a população.

Referências: [lab_summary_metrics.py:68](/C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:68), [repositories/lab_replication.py:104](/C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_replication.py:104).

**MEDIUM — maturidade e PF também divergem entre os dois vereditos.** O placar conta dias de **saída**; a replicação conta dias de **decisão**. E uma população madura, positiva e sem perdas é `validada` no placar, mas `reprovada` na replicação. Isso permite dois vereditos para a mesma versão sem mudança de evidência. É necessário unificar o contrato, incluindo esses casos-limite. Referências: [lab_scoreboard.py:80](/C:/dev/project-hunter/apps/api/hunter_api/services/lab_scoreboard.py:80), [replication/stats.py:80](/C:/dev/project-hunter/packages/indicators/hunter_indicators/replication/stats.py:80), [lab_scoreboard_metrics.py:79](/C:/dev/project-hunter/apps/api/hunter_api/services/lab_scoreboard_metrics.py:79), [replication/stats.py:154](/C:/dev/project-hunter/packages/indicators/hunter_indicators/replication/stats.py:154).

**HIGH — a mesma evidência pode amadurecer uma irmã duas vezes.** `sibling_population()` concatena a população viva com **todos** os replays da irmã. Não deduplica decisões sobrepostas nem verifica a comparação com replay do pai na mesma janela, exigida pela D15(c). Cenário: 25 resultados distribuídos em 15 dias, replayados sob dois UUIDs, viram 50 resultados e atingem a meia-régua sem informação nova. Sete irmãs assim podem aprovar o bloco 2. O rótulo `mixed`/`replay` informa a origem, mas não corrige a contagem. Referências: [repositories/lab_replication.py:162](/C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_replication.py:162), [protocol.py:138](/C:/dev/project-hunter/packages/indicators/hunter_indicators/replication/protocol.py:138), [D15:12](/C:/dev/project-hunter/.claude/state/decisions-delegated-2026-09-08.md:12).

**O que está correto:** a consulta principal usa `prospective`, e `replay`/`replication` são anexados separadamente, sem alimentar o cálculo principal de maturidade/veredito. O bloco replay reutiliza o portão de horizonte. Referências: [repositories/lab_scoreboard.py:133](/C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_scoreboard.py:133), [routers/lab_scoreboard.py:72](/C:/dev/project-hunter/apps/api/hunter_api/routers/lab_scoreboard.py:72), [lab_scoreboard_replay.py:35](/C:/dev/project-hunter/apps/api/hunter_api/services/lab_scoreboard_replay.py:35).

### 2. Autonomia paper: faltam condições operacionais além das quatro citadas

A última avaliação registrada mostra **154 sinais paper, zero propostas, zero posições e zero trades**. Logo, ainda não demonstra o caminho autônomo completo. A linha `momentum v3` já estava ativa; não repetiria como pendência a sua criação/ativação. [Diário de 08/09:85](/C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario/2026-09-08.md:85).

| Etapa | Risco concreto e condição de aceite |
|---|---|
| **Admissão** | Provar o vínculo `agents` habilitado para a versão e carteira corretas. Sem vínculo, o sinal nem pertence à fila daquela carteira; com agente pausado, ocorre `agent_unavailable`. Ativar a versão não basta. [bridge_repo.py:130](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_repo.py:130), [bridge_screen.py:215](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_screen.py:215). |
| **Ordem** | **`avgPrice` continua ausente.** O leitor retorna `None`; mercados cujos filtros MARKET exigem média adiam a execução e podem deixar a reserva expirar. β válido não resolve isso. É preciso medir os filtros do universo efetivamente executável e fechar a coleta necessária. [market_data.py:149](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/market_data.py:149), [entry_inputs.py:62](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/entry_inputs.py:62). |
| **Proteção** | Sem fita/livro utilizável, uma intenção pode ficar degradada enquanto a posição continua exposta. Provar recuperação, quantidade remanescente e ausência de venda duplicada após queda/restart. A tentativa usa o livro real e registra `pending_degraded`; isso é correto, mas não equivale a proteção executada. [protection.py:183](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/protection.py:183), [protection.py:296](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/protection.py:296). |
| **MTM** | Uma marca indisponível cai no último valor durável. O ciclo pode continuar escrevendo snapshots e renovando `mtm_written_at`; o check `mtm_fresh` mede essa escrita, não a atualidade dos preços. Cenário: fita parada, patrimônio aparentemente estável e check de MTM verde. Exigir qualidade das marcas explícita no aceite operacional. [bridge_inputs.py:180](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_inputs.py:180), [cycles.py:275](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/cycles.py:275), [health.py:95](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/health.py:95). |
| **Integração** | A prova V6 declara que **queda de WS com lacuna e perda de Redis durante a decisão não foram cobertas** naquele caminho. Esses cenários precisam ser exercitados agora com SPOT integrado, incluindo retomada das proteções e reconciliação do ledger. [test_v6_stale_data_reconnect_restart.py:1](/C:/dev/project-hunter/tests/integration/paper/test_v6_stale_data_reconnect_restart.py:1). |

**HIGH de segurança antes da autonomia:** o compose ainda entrega `DATABASE_URL_MIGRATIONS` aos serviços de runtime pelo bloco compartilhado. Uma execução de código comprometida nesses processos pode usar a conexão de dono para contornar os grants de ativação e isolamento. O risco permanece mesmo que a conexão normal execute com papel restrito. [docker-compose.prod.yml:30](/C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:30), [docker-compose.prod.yml:59](/C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:59).

Também exigiria **prova atual de backup restaurável**, não apenas cron configurado: os registros ainda relatam ausência de dumps, embora o bootstrap atual já invoque o script com `bash`. Não trataria o incidente antigo como comprovadamente vigente nem como resolvido sem essa prova. [M3.md:261](/C:/dev/project-hunter/docs/reports/M3.md:261), [bootstrap_vps.sh:346](/C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:346).

### 3. T3.28a: confiança no peer é necessária, mas não suficiente

**O desenho pode ser seguro**, desde que:

- O web só propague endereço recebido por uma cadeia confiável; acesso direto ao web não pode transformar XFF fornecido pelo cliente em identidade confiável.
- A API confie nos IPs efetivos dos proxies, sem `*` ou toda a rede Docker.
- “Principal antes do IP” signifique **identidade verificada**, nunca mera presença de Bearer ou `sub` decodificado.
- Requisições sem autenticação válida continuem limitadas.

O brief permite “nome/IP de `web`”, mas o Uvicorn instalado **não resolve esse nome por DNS** na lista de confiança: valores não reconhecidos como IP viram literais. Usar apenas `web` não corresponde ao peer numérico. [proxy_headers.py:128](/C:/dev/project-hunter/.venv/Lib/site-packages/uvicorn/middleware/proxy_headers.py:128).

**A implementação atual escolheu outro caminho permitido pelo brief:** não encaminha o IP do navegador; mantém Caddy como proxy confiável e concede ao IP fixo do web um limite de 6.000/min. O principal continua sendo verificado e limitado depois. Não identifiquei bypass direto por XFF de um peer externo nesse caminho. [api.ts:7](/C:/dev/project-hunter/apps/web/lib/server/api.ts:7), [docker-compose.prod.yml:66](/C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:66), [rbac.py:116](/C:/dev/project-hunter/apps/api/hunter_api/auth/rbac.py:116).

**Mas permanece um cenário de negação de serviço compartilhada:** uma conta dispara SSR repetidamente; cada chamada gasta primeiro o bucket do web, inclusive as posteriormente recusadas pelo limite de principal. Ao ultrapassar 6.000/min, outras contas recebem 429. Aumentar o teto reduz a incidência normal, mas não elimina essa falha. [rate_limit.py:133](/C:/dev/project-hunter/apps/api/hunter_api/middleware/rate_limit.py:133).

## NICE-TO-HAVE

- Mostrar replay por corrida/janela comparável. Hoje `operations_closed` significa resultados **avaliáveis com R conhecido**, não todo desfecho fechado; essa diferença merece ficar visível. [lab_scoreboard_replay.py:35](/C:/dev/project-hunter/apps/api/hunter_api/services/lab_scoreboard_replay.py:35).
- Explicitar que os recibos de replay não obedecem ao mesmo corte: `replay_runs_summary()` não recebe `as_of`. Uma consulta histórica pode mostrar massa/janela de corridas posteriores. [repositories/lab_scoreboard.py:182](/C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_scoreboard.py:182).
- Corrigir a linguagem estatística do protocolo: os quatro blocos reutilizam dados e não são quatro repetições independentes; sob aproximação i.i.d., reduzir a amostra à metade aumenta o erro-padrão por **√2**, não aproximadamente duas vezes. [REPLICATION.md:46](/C:/dev/project-hunter/docs/plans/REPLICATION.md:46), [REPLICATION.md:78](/C:/dev/project-hunter/docs/plans/REPLICATION.md:78).

## O QUE EU FARIA DIFERENTE

**Antes de outra variante, mediria melhor o EXP-0006 existente:**

1. **Separar seleção e rearme.** Medir o filtro sobre entradas congeladas do pai e, separadamente, a trajetória completa com slots. As 25 decisões comuns têm diferença zero; investigar também as seis decisões do pai acima do piso que não aparecem entre essas 25, além das seis exclusivas da variante. A tabela atual permite identificar essa lacuna. [EXP-0006:194](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md:194).
2. **Medir oportunidade por tempo:** sinais por mercado/dia, tempo ocupado, tempo exposto, motivos de bloqueio/rearme e soma de R por período sob uma convenção fixa. Média por operação sozinha não compara políticas com frequências tão diferentes.
3. **Decompor custos e risco:** resultado bruto versus líquido, custo em R, funding, distância do stop, MFE/MAE, duração e cauda negativa; estratificar por mercado, dia e faixas de ATR% previamente definidas.
4. **Medir dependência e influência:** intervalo da diferença reamostrando dias/blocos comuns às duas versões; análise retirando um dia/mercado por vez e mostrando a contribuição individual dos cinco resultados exclusivos avaliáveis.
5. **Fechar proveniência e cobertura:** SQL integral, `as_of` + `read_at`, faltantes por braço e comparação prospectiva no universo comum. Essas lacunas já estão declaradas na página. [EXP-0006:114](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md:114).

Não usaria os decis de ATR para escolher imediatamente outro piso na mesma amostra; isso iniciaria outra tentativa exploratória, a registrar como tal.

## CONCORDO COM

**“Inconclusivo” está correto por duas razões independentes:** 30 avaliáveis/9 dias não satisfazem 100 **E** 30; além disso, o replay reutiliza a janela que gerou a hipótese. Mesmo atingir o limiar nesse replay não o transformaria em confirmação prospectiva. [EXP-0006:218](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md:218).

A igualdade dos 25 pares é uma boa verificação de consistência, **não prova global** de equivalência. Os cinco resultados exclusivos sustentam a melhora aparente, enquanto o subconjunto do pai preservado pelo piso teve média pior. Não há vantagem demonstrada. [EXP-0006:201](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md:201).

Também concordo com a opção A e os blocos separados, e com manter `research_only`/replay fora da carteira. A ponte atual compara propósito da coluna com envelope e exige `prospective`. [bridge_screen.py:252](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_screen.py:252).

## OBSIDIAN

- **Revisões-Astra — Shadow Lab, 2026-09-08:** registrar os cenários de contaminação, divergência de métricas e aceite operacional.
- **EXP-0006 — piso de custo no momentum:** acrescentar avaliação com decomposição seleção/rearme, influência dos cinco resultados e proveniência completa.
- **Risk Engine / Portfolio:** atualizar os pré-requisitos efetivos da autonomia e distinguir sinais paper de execução paper.
- **Execution Engine / Paper Trading:** substituir o estado antigo “planejado” e documentar `avgPrice`, proteções degradadas e qualidade do MTM.
- **Open Bugs:** registrar os achados reproduzíveis desta revisão e exigir evidência atual para encerrar backup/DSN.
- **00-HOME / Diário — 2026-09-08:** reconciliar o estado consolidado com a linha paper já ativa e as condições ainda não comprovadas.
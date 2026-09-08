---
tags: [astra, revisao, shadow-lab, autonomia, replicacao, seguranca]
updated: 2026-09-08
status: registro
owner: sexta-feira
decided_on: 2026-09-08
by: astra
---

# Revisão da Astra — "o Lab está pronto?" (2026-09-08)

Transcrição integral em `.claude/state/astra-review-lab-pronto-2026-09-08.md`. Perguntei três
coisas: se o veredito do placar está mesmo isolado do replay depois da T3.18b/T3.19, se a autonomia
paper pode ser declarada pronta, e se o desenho da T3.28a (limite por IP do peer interno) fecha o
buraco que ele diz fechar.

> [!veredito] O resultado em uma frase
> **Não.** O veredito principal do placar continua separado do replay, mas o **caminho de
> replicação** tem quatro inconsistências capazes de antecipar maturidade e carimbar `promising_at`
> com evidência histórica; a autonomia paper tem **cinco etapas operacionais sem prova**; e o
> desenho do limite por IP é defensável, mas deixa uma negação de serviço compartilhada.

> [!alerta] O que esta revisão **não** é
> Uma medição. A Astra leu o código local e as leituras já registradas em 2026-09-08 — não rodou
> suíte, migração nem consulta à VPS. Os números operacionais citados aqui são **evidência
> registrada**, não resultado reproduzido nesta revisão. Nenhum arquivo foi criado ou modificado,
> nenhum commit, nenhum `.env` acessado.

## O que ela concordou — e é a parte que sustenta a régua

- **`inconclusivo` na [[EXP-0006-momentum-piso-de-custo]] está correto por duas razões
  independentes:** 30 avaliáveis / 9 dias não satisfazem 100 **E** 30; e o replay reutiliza a janela
  que gerou a hipótese, de modo que **mesmo atingir o limiar ali não viraria confirmação
  prospectiva** ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **A igualdade dos 25 pares é verificação de consistência, não prova de equivalência.** Os cinco
  resultados exclusivos sustentam sozinhos a melhora aparente, enquanto o subconjunto do pai que o
  piso preserva teve média **pior**. Não há vantagem demonstrada.
- **O placar principal está isolado:** a consulta principal usa `prospective`, e os blocos `replay` e
  `replication` são anexados **separadamente**, sem alimentar maturidade nem veredito; o bloco de
  replay reutiliza o mesmo portão de horizonte
  (`apps/api/hunter_api/repositories/lab_scoreboard.py:133`,
  `apps/api/hunter_api/routers/lab_scoreboard.py:72`,
  `apps/api/hunter_api/services/lab_scoreboard_replay.py:35`).
- **Opção A, blocos separados e `research_only`/replay fora da carteira** continuam certos: a ponte
  compara propósito da coorte com envelope e exige `prospective`
  (`services/execution-worker/hunter_execution_worker/bridge_screen.py:252`). Ver D14/D15 em
  [[Architecture Decisions]] e [[Dialogos/SHADOW]].

## MUST-FIX 1 — a replicação não está protegida como o placar está

Quatro achados, todos com dono **T3.18c** (brief a escrever pelo orquestrador). Estão em
[[Open Bugs]] com o arquivo:linha.

1. **HIGH — a CLI pode tornar o pai "promissor" usando replay.** A consulta do worker filtra versão e
   resultado terminal **sem filtro de coorte**, e `replicate()` usa esse relatório para autorizar a
   rodada e gravar `promising_at`. *Cenário:* prospectivo pequeno ou negativo, replay positivo com
   100 resultados em 30 dias — a CLI aceita a replicação sem `--force-research` e **congela um marco
   que deveria nascer exclusivamente do prospectivo**. A correção feita na API não fecha esse outro
   escritor. (`services/strategy-worker/hunter_strategy_worker/replication_stats.py:69`,
   `replication.py:257`, `replication.py:296`.)
2. **HIGH — "avaliável" tem duas definições.** O placar exige saída até `as_of` **e** horizonte
   completo transcorrido; a replicação da API exige apenas emissão até `as_of`, terminal e `R` não
   nulo. *Cenários:* uma leitura histórica inclui resultado encerrado **depois** do corte; e, no
   corte atual, as saídas rápidas entram antes das operações cujo horizonte ainda está aberto —
   população enviesada para o lado que fecha cedo.
   (`apps/api/hunter_api/services/lab_summary_metrics.py:68`,
   `apps/api/hunter_api/repositories/lab_replication.py:104`.)
3. **MEDIUM — maturidade e PF divergem entre os dois vereditos.** O placar conta dias de **saída**; a
   replicação conta dias de **decisão**. E uma população madura, positiva e **sem perdas** é
   `validada` no placar e `reprovada` na replicação. Dois vereditos para a mesma versão **sem
   mudança de evidência**. (`apps/api/hunter_api/services/lab_scoreboard.py:80`,
   `packages/indicators/hunter_indicators/replication/stats.py:80`,
   `apps/api/hunter_api/services/lab_scoreboard_metrics.py:79`, `replication/stats.py:154`.)
4. **HIGH — a mesma evidência pode amadurecer uma irmã duas vezes.** `sibling_population()` concatena
   a população viva com **todos** os replays da irmã, sem deduplicar decisões sobrepostas e sem a
   comparação com replay do pai na mesma janela que a D15(c) exige. *Cenário:* 25 resultados em 15
   dias, replayados sob dois UUIDs, viram 50 resultados e atingem a meia-régua **sem informação
   nova**; sete irmãs assim aprovam o bloco 2. O rótulo `mixed`/`replay` informa a origem, **não
   corrige a contagem**. (`apps/api/hunter_api/repositories/lab_replication.py:162`,
   `packages/indicators/hunter_indicators/replication/protocol.py:138`,
   `.claude/state/decisions-delegated-2026-09-08.md:12`.)

## MUST-FIX 2 — a autonomia paper não está pronta, e faltam mais condições do que as quatro citadas

A última avaliação registrada mostra **154 sinais paper, 0 propostas, 0 posições, 0 trades**
([[Diario/2026-09-08]]): o caminho autônomo **nunca rodou de ponta a ponta**. A linha `momentum v3`
já estava ativa desde 02:57 de Brasília — a criação/ativação **não** é pendência.

| Etapa | Risco concreto e condição de aceite | Arquivo:linha |
|---|---|---|
| **Admissão** | Provar o vínculo em `agents` habilitado para a **versão e a carteira corretas**. Sem vínculo o sinal nem pertence àquela fila; com agente pausado, `agent_unavailable`. Ativar a versão não basta. | `bridge_repo.py:130`, `bridge_screen.py:215` |
| **Ordem** | **`avgPrice` continua ausente** (o leitor devolve `None`): mercados cujos filtros MARKET exigem média **adiam** a execução e podem deixar a reserva expirar. β válido não resolve. Medir os filtros do universo executável e fechar a coleta. | `market_data.py:149`, `entry_inputs.py:62` |
| **Proteção** | Sem fita/livro utilizável a intenção fica **degradada com a posição exposta**. Provar recuperação, quantidade remanescente e ausência de venda duplicada após queda/restart. Registrar `pending_degraded` está certo, mas **não é proteção executada**. | `protection.py:183`, `protection.py:296` |
| **MTM** | Marca indisponível cai no último valor durável; o ciclo segue escrevendo snapshot e renovando `mtm_written_at`, e o check `mtm_fresh` mede **a escrita, não a atualidade do preço**. *Cenário:* fita parada, patrimônio aparentemente estável, check verde. Exigir **qualidade das marcas** no aceite. | `bridge_inputs.py:180`, `cycles.py:275`, `health.py:95` |
| **Integração** | A prova V6 declara que **queda de WS com lacuna e perda de Redis durante a decisão não foram cobertas**. Exercitar os dois agora, com SPOT integrado, incluindo retomada das proteções e reconciliação do ledger. | `tests/integration/paper/test_v6_stale_data_reconnect_restart.py:1` |

**HIGH de segurança antes da autonomia:** o compose ainda entrega `DATABASE_URL_MIGRATIONS` aos
serviços de runtime pelo bloco compartilhado. Execução de código comprometida nesses processos usa a
conexão de **dono** para contornar os grants de ativação e de isolamento — o risco permanece mesmo
com a conexão normal rodando sob papel restrito (`infra/vps/docker-compose.prod.yml:30` e `:59`).
Dono: T3.15d.

**Backup: não é bug, é prova que falta.** Ela exigiria **prova atual de backup restaurável**, não
apenas cron configurado; os registros ainda relatam ausência de dumps (`docs/reports/M3.md:261`),
embora o bootstrap já invoque o script com `bash` (`infra/scripts/bootstrap_vps.sh:346`). Não tratar
o incidente antigo como vigente **nem** como resolvido sem essa prova — está registrado como
**"a comprovar em T3.29"**.

Tudo isto virou o brief **T3.29** (`.claude/state/brief-T3.29-autonomy-acceptance-run.md`), que é o
aceite operacional exigido antes de qualquer `ENABLE_PAPER_AUTONOMY=true`. Os sete itens e o estado
de cada um estão em [[Execution Engine]], [[Paper Trading]] e [[Risk Engine]].

## MUST-FIX 3 — T3.28a: confiar no peer é necessário, não suficiente

O desenho **pode** ser seguro, sob quatro condições: o `web` só propaga endereço vindo de cadeia
confiável; a API confia nos **IPs efetivos** dos proxies (nunca `*` nem a rede Docker inteira);
"principal antes do IP" significa **identidade verificada**, não presença de Bearer; e requisição sem
autenticação válida continua limitada.

- **Correção de fato no brief:** o Uvicorn instalado **não resolve nome por DNS** na lista de
  confiança — valores não reconhecidos como IP viram literais, então `web` como nome **não** casa com
  o peer numérico (`.venv/Lib/site-packages/uvicorn/middleware/proxy_headers.py:128`). A
  implementação escolheu o outro caminho permitido pelo brief (IP fixo + limite interno), o que
  torna o ponto acadêmico — mas o texto do brief estava errado.
- **O que ela não achou:** nenhum bypass direto por XFF de peer externo no caminho implementado. O
  principal continua sendo verificado e limitado depois (`apps/web/lib/server/api.ts:7`,
  `infra/vps/docker-compose.prod.yml:66`, `apps/api/hunter_api/auth/rbac.py:116`).
- **O que permanece — negação de serviço compartilhada:** uma conta dispara SSR repetidamente e cada
  chamada gasta primeiro o bucket do `web`, **inclusive as que o limite de principal recusaria
  depois**. Passando de 6.000/min, **outras contas recebem 429**. Aumentar o teto reduz a incidência
  normal e **não elimina a falha** (`apps/api/hunter_api/middleware/rate_limit.py:133`). Dono:
  T3.28a-seguimento, em [[Open Bugs]].

## Nice-to-have anotados

- Mostrar replay **por corrida/janela comparável**: hoje `operations_closed` significa "resultados
  avaliáveis com R conhecido", não todo desfecho fechado, e essa diferença merece ficar visível
  (`services/lab_scoreboard_replay.py:35`).
- Explicitar que os **recibos de replay não obedecem ao mesmo corte** — `replay_runs_summary()` não
  recebe `as_of`, então uma consulta histórica pode mostrar massa/janela de corridas posteriores
  (`repositories/lab_scoreboard.py:182`).
- **Corrigir a linguagem estatística de `docs/plans/REPLICATION.md`** (§46 e §78): os quatro blocos
  **reutilizam dados** e não são quatro repetições independentes; e, sob aproximação i.i.d., reduzir
  a amostra à metade aumenta o erro-padrão por **√2 (~1,41×)**, não "grosso modo, o dobro". `docs/`
  não é editável por esta tarefa — está em [[Open Bugs]] como correção de texto para o orquestrador.

## O que ela faria diferente antes de abrir outra variante

Cinco medições sobre a [[EXP-0006-momentum-piso-de-custo]] que já existe, em vez de mais uma
variante — e **não** usar os decis de ATR para escolher outro piso na mesma amostra (isso seria
outra tentativa exploratória, a registrar como tal). Estão acrescentadas na própria página como
seção datada "Próximas medições (Astra) — 2026-09-08": separar seleção de rearme, medir oportunidade
por tempo, decompor custo e risco, medir dependência e influência dos cinco resultados exclusivos, e
fechar proveniência e cobertura.

## O que virou tarefa

| Achado | Dono | Onde |
|---|---|---|
| Replicação: coorte, "avaliável", maturidade/PF, irmãs | **T3.18c** (brief a escrever) | [[Open Bugs]] |
| Autonomia: admissão, `avgPrice`, proteção, MTM, integração, backup | **T3.29** | `.claude/state/brief-T3.29-autonomy-acceptance-run.md` |
| `DATABASE_URL_MIGRATIONS` no bloco compartilhado | **T3.15d** | [[Open Bugs]] |
| Negação de serviço compartilhada no bucket do `web` | **T3.28a-seguimento** | [[Open Bugs]] |
| Linguagem estatística de `REPLICATION.md` §46/§78 | orquestrador (texto) | [[Open Bugs]] |
| Cinco medições do EXP-0006 | Sexta-feira, próximo plantão | [[EXP-0006-momentum-piso-de-custo]] |

## Relacionadas

[[EXP-0006-momentum-piso-de-custo]] · [[EXP-0005-momentum-paper]] · [[Experiments Index]] ·
[[Execution Engine]] · [[Paper Trading]] · [[Risk Engine]] · [[Portfolio]] · [[Open Bugs]] ·
[[Architecture Decisions]] · [[Dialogos/SHADOW]] · [[Diario/2026-09-08]] ·
[[Revisoes-Astra/Index|Revisões da Astra]] · [[Mente da Sexta-feira]]

## Fontes

`.claude/state/astra-review-lab-pronto-2026-09-08.md` ·
`.claude/state/brief-T3.29-autonomy-acceptance-run.md` · `.claude/state/notes-T3.28a.md` ·
`.claude/state/decisions-delegated-2026-09-08.md` (D14/D15) ·
`.claude/state/brief-T3.15d-owner-dsn.md` · `docs/plans/REPLICATION.md`

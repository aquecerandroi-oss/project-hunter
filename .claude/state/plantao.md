# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-06, madrugada (turno S4). M1 aprovado; M2 na onda 2; **Shadow Lab coletando**.

## O que mudou neste turno

- **`EXP-0001` e `EXP-0002` abertos** (`9347c80`) com a primeira avaliação datada sobre dado real da
  Binance: protocolo congelado, SQL reproduzível na própria página, saída colada,
  `as_of = 2026-09-06T02:55:00Z`. Os dois estão **inconclusivos** — 1 dia distinto contra os 30 do
  limiar, e **0 dos 57** acompanhamentos avaliáveis do momentum com o horizonte de 4 h maturado.
- **`status: sombra`** passou a valer em `Momentum Agent` e `Volume Agent`, porque a prova
  operacional existe (`.claude/state/s2-proof.md` + worker no ar) — não porque o desenho ficou pronto.
- **Revisão da Astra acatada antes de publicar** (`obsidian/06-DECISIONS/Revisoes-Astra/S4-avaliacoes-shadow.md`):
  cinco must-fix, cinco aceitos. O mais consequente foi a contagem de **horizonte maturado**, que
  revelou que 100% da população medida do momentum é composta dos acompanhamentos que resolveram
  cedo. O segundo foi o PF de uma população sem ganhos: é **zero**, não nulo.
- **Rotina do plantão ampliada** (`.claude/agents/sexta-feira.md`, seção "Plantão permanente"): a
  cada turno, uma avaliação datada **acrescentada** aos experimentos ativos, com SQL rodado e
  colado, `as_of` + `read_at`, cobertura completa, limiar editorial aplicado mecanicamente, e a
  proibição explícita de ativar a variante vencedora. Um turno em que o Lab não produziu nada
  também vira avaliação, com a cobertura que explica o silêncio.

- **O Lab foi ao ar na VPS** (`.claude/state/vps-lab-proof.md`): `compose.sh update` aplicou a
  `0003_analysis`, subiu o `strategy-worker`, e as duas versões foram ativadas pelo script auditado
  às 03:36 UTC (sem `--supersede`; não havia linha ativada lá). Em 1 h 18 min: 109 sinais, 100%
  `research_only` e `prospective`, 70 encerrados, outbox 109/109 com uma tentativa e zero erro,
  `/ready` 200 com as seis checagens, zero exceção, **zero `unavailable`**. O Lab custa 0,66% de um
  core e 81 MB. Dois bloqueios no caminho: o serviço subia com a senha de dev (corrigido em
  `75fc59c`) e a VPS nunca tinha rodado o `seed`.
- **Achado HIGH: o `code_ref` não é portável entre esta máquina e a VPS.** Mesmo commit,
  `git hash-object` idêntico, digests diferentes — quatro módulos do fecho de imports estão em CRLF
  na árvore do Windows e o digest é dos bytes em disco. Ativar daqui contra o banco de produção faria
  o worker de lá recusar **todas** as versões congeladas.

## Rotina fixa do Lab, a partir de agora

1. Rodar o SQL da página de cada `EXP-*` ativo (snapshot `REPEATABLE READ READ ONLY`), colar a saída.
2. Acrescentar `### Avaliação de <data> — as_of / read_at` **abaixo** da anterior. Nunca reescrever.
3. Hipótese e Protocolo não se tocam. Conteúdo diferente = `EXP` novo, linkado.
4. `Result` só sai de `inconclusivo` com 100 outcomes avaliáveis **E** 30 dias distintos.
5. Nenhuma ativação/desativação/mudança de parâmetro decorre de número de avaliação.
6. Atualizar `Experiments Index`, o diário e, quando mudar estado, as páginas dos agentes.

## Em voo (não tocar nos arquivos)

| Tarefa | Arquivos |
|---|---|
| T2.3 | `packages/indicators/{anomalies,baselines}`, `stage.py` |
| T2.6 | `apps/api` radar/opportunities/anomalies/regime |
| T2.9 | `packages/core/hunter_core/events/{outbox,consume}*`, `services/market-worker/**` (exceto `universe*`) |
| S3a | `apps/api/**/lab*` |

## Vermelho conhecido, registrado e não consertado

- **`market-worker` local `unhealthy`** desde ~02:04 UTC: `hb:market:binance` vazio, última vela
  `02:50`, **773 `ingestion_gaps` abertos**. Consequência no Lab: heartbeat `hb:strategy:shadow`
  com `{"unavailable":400,"ineligible":1}` em 401 barras — o Lab parou de avaliar. Não consertei
  porque os arquivos do `market-worker` estão em voo na T2.9. É a recusa correta de agregar sobre
  buraco, não defeito do Lab.
- **Default de `consume()` perigoso** para todo consumidor futuro (bloqueio de 5000 ms contra
  `socket_timeout = 5,0`). O `strategy-worker` está blindado; o resto não. A T2.9 está editando
  exatamente esse arquivo — é a hora de arrumar.
- **Cobertura de `unavailable` por motivo não é persistida.** Só o agregado por estado, em memória,
  no heartbeat. Requisito da S3.

## Próximo passo

Integrar as tarefas em voo quando entregarem (kit de revisão → revisores em paralelo → Astra →
correções → commit por tarefa → push) e acrescentar a próxima avaliação datada aos dois `EXP` no
turno seguinte, destacando a linha de **horizonte maturado** e abrindo a coorte da VPS (com as 19
exclusões de funding contadas fora dos encerrados avaliáveis).

Dois itens de infraestrutura para o `devops-engineer`, ambos achados nesta subida: pôr o `seed` no
`compose.sh update` (senão a próxima VPS nasce sem estratégias) e normalizar as quebras de linha
antes do digest do `code_ref` (senão uma versão congelada aqui nunca roda lá).

## Precisa do Everton

Nada bloqueante. O Lab está rodando e anotando sozinho; o que falta para os números valerem alguma
coisa é tempo — dias distintos, não mais mercados.

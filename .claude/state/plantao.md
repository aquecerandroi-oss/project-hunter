# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-06, **tarde** (turno S4-b). M1 aprovado; M2 na onda 2; **Shadow Lab medindo na
VPS**. A nota do turno da madrugada está no diário do dia
(`obsidian/09-OPERATIONS/Diario/2026-09-06.md`).

## O que mudou neste turno

- **Segunda avaliação datada nos dois experimentos, sobre a coorte da VPS** (`as_of =
  2026-09-06T13:00:00Z`, `read_at = 13:26:35.681334Z`), SQL rodado contra o Postgres da VPS e saída
  colada. Acrescentada, não reescrita. É **outra população**: lá só existe uma versão ativada por
  estratégia (`code_ref` `…6ccbe8b6…` e `…a03d18fe…`, ativadas 03:36 UTC), então não continua a série
  local.

  | Experimento | Emitidos | Avaliáveis c/ `R_net` | Taxa de alvo | Expectancy (R) | PF | Dias | Result |
  |---|---|---|---|---|---|---|---|
  | EXP-0001 momentum v1 | 208 | 91 | 0,5333 | **−0,2102** | 0,6084 | 1 | inconclusivo |
  | EXP-0002 volume v1 | 459 | 316 | 0,5000 | **−0,2304** | 0,6539 | 1 | inconclusivo |

- **O achado do turno: a expectancy do momentum trocou de sinal quando o horizonte maturou.** Era
  +0,3053 R sobre 48 acompanhamentos com **zero** horizontes de 4 h completos; é **−0,2102 R** sobre
  91 maduros. A avaliação da madrugada estava certa ao dizer que descrevia "os que resolveram cedo".
  É o argumento vivo a favor de acrescentar em vez de reescrever.
- **`EXP-0002` passou dos 100 outcomes (316) e continua `inconclusivo`** — o limiar é 100 **E** 30
  dias, e há 1. Aplicado mecanicamente.
- **Seções "Hipóteses de falha" abertas nos dois EXP** (a pesquisa que o Everton pediu), com SQL,
  censo completo e o que uma v2 precisaria mudar. **Nada ativado, desativado ou reparametrizado.**
  - **H1 (invalidação):** 35% dos resolvidos, **nenhum dos 227 lucrativo**; no momentum só 3 de 71
    chegaram a 1 R bruto. O dado **não** decide o contrafactual (o acompanhamento para na
    invalidação). Publicado como **ponto de equilíbrio** (+0,22 R no momentum, −0,066 R no volume,
    contra −0,58 e −0,72 realizados) e cenários de sensibilidade — **não** como intervalo.
  - **H2 (funding):** **69 de 73** têm a linha em `funding_rates` do mesmo mercado a menos de 2 s do
    instante pedido (a maioria a 5 ms); 851 das 1883 linhas têm segundos ≠ 0. São 66 liquidações em
    7 instantes. **Mas o efeito medido é ínfimo:** 0 dos 173 outcomes de momentum e 9 dos 394 de
    volume atravessaram uma liquidação, efeito médio −0,000195 R, máximo 0,028 R. Defeito de
    instrumento, não explicação do vermelho. Correção ingênua (±2 s) **proibida**: cobraria a mesma
    liquidação duas vezes.
- **Astra ([[S4-hipoteses]]): cinco must-fix, cinco aceitos antes de publicar.** Ela pegou um erro
  de fato meu — as duas estratégias têm regras de invalidação **diferentes** (momentum: fechamento
  15 min abaixo do máximo anterior; volume: fechamento 5 min abaixo do meio da barra do sinal).
  Verifiquei no código antes de aceitar.
- **Base atualizada:** Changelog (os doze commits do dia), Open Bugs (4 entradas novas, 1 investigação fechada),
  Resolved Bugs (os dois HIGH da VPS + o incidente da chave do Clerk), Deployment (HTTPS no IP,
  `default_sni`, o incidente do `sk_test_`, o backup que nunca rodou), Architecture Decisions
  (fail-closed do rate limit; HTTPS interno), Experiments Index, índice de Revisões da Astra,
  diário do dia. Features/Anomalies/Workers/Data Flow/Market Collector por subagente
  `documentation-writer`.

## Saúde

| Onde | Estado |
|---|---|
| **VPS** | **verde.** 6 containers `healthy`, `/ready` 200, 0 exceção em 24 h nos dois workers. `ws_state=connected`, 200 mercados, 1200 assinaturas, **0 gaps abertos**, última vela 1 m às 13:27Z. Lab: 2008 barras avaliadas, 22 `unavailable` + 8 `ineligible`, outbox pendente **0**, 0 erros. Disco 10%, memória 2,1/47 GB, carga 1,32 em 12 cores. |
| **Local** | **fora.** Docker Desktop não está rodando (`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`). O HIGH do `market-worker` local continua aberto e **não verificado**. |
| Margem | `dropped_events = 7.073.659` com o `market-worker` a 99% de **um** core. Por contrato a fila nunca descarta kline final e a evidência bate (0 gaps). Consumo de margem, não perda de série. |

## Vermelho que precisa do Everton

**O backup do Postgres da VPS nunca rodou. Não existe um único dump.** `/opt/backups` tem só
`backup.log` com `Permission denied`: o script é rastreado como `100644` (sem bit de execução) e o
cron instalado por `infra/scripts/bootstrap_vps.sh:346` invoca o caminho direto em vez de
`bash <caminho>`. Tentei corrigir os dois jeitos na VPS e **o gate de permissão desta sessão recusou**
(escrita em `/etc/cron.d` via sudo, e execução do script). Não contornei.

Importa mais aqui do que importaria em outro projeto: a pesquisa do Shadow Lab é o único dado que
**não se refaz coletando de novo** — `signal_outcomes` avança no lugar e nenhuma avaliação passada é
reconstruível. Correção, uma linha, duas opções (em `Open Bugs`).

## Em voo (não tocar nos arquivos)

| Tarefa | Arquivos |
|---|---|
| T2.4 | `packages/indicators/{regime,opportunity}` (em revisão) |
| T2.7 | `apps/web` radar/opportunities |
| T2.9 | `packages/core/hunter_core/events`, `services/market-worker/**`, `packages/exchange-adapters/**` |

Há também uma sessão paralela escrevendo `obsidian/11-KNOWLEDGE/KB-*` — **não commitar esses
arquivos**.

## Próximo passo

Integrar T2.4, T2.7 e T2.9 quando entregarem (kit de revisão → revisores em paralelo → Astra →
correções → commit por tarefa → push). No próximo plantão, terceira avaliação datada nos dois EXP:
a linha a destacar passa a ser **dias distintos** (o gate de horizonte já está cumprido na VPS), e
vale registrar se a convergência das duas estratégias em ≈ −0,22 R persiste num segundo dia — se
persistir com o mercado diferente, é a estratégia; se mudar junto, era o dia.

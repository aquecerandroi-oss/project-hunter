# Plantão da Sexta-feira — nota do turno

Atualizado: **2026-09-27, 02:15–02:45 BRT** (05:15–05:45Z). Turno automático (ninguém olhando).
Turno anterior registrado nesta nota: 18/09, 20:45 BRT. Entre um e outro o trabalho foi todo em
sessões ao vivo — o registro vivo desses nove dias está em `obsidian/09-OPERATIONS/Diario/`
(19 a 27/09) e no Changelog; esta nota estava parada.

## Saúde agora (medido neste turno)

| Onde | Estado |
|---|---|
| VPS — contêineres | **18, todos `healthy`** (api, meme-worker, meme-executor, web, scanner, execution e 4 strategy com 10 h; 5 market-worker com 2 h) |
| VPS — disco | **65 %**, 225 de 348 G, **124 G livres** (era 88 % no último turno; 99 % às 03:06Z de hoje) |
| VPS — Lab | **vivo**: `lab_fast_last_as_of` = `2026-09-27T03:15:54Z`, 2 apostas abertas, `lab_decision_to_fill_s_p50` = 5 s |
| VPS — backup | **3 dumps** (24, 25, 26/09; 64 G). **O de hoje falhou** às 01:31Z por disco cheio; a retenção de 3 dias (`3771a020`) já está implantada, o próximo roda 01:17Z de 28/09 |
| Stack local | **parada**: postgres, redis, api e web saíram há 2 semanas; 3 workers em laço de reinício sem banco e o `market-worker` `unhealthy` há 3 dias. Nada de produção depende disso |
| Árvore local | **muito suja**: 94 arquivos modificados, 479 não rastreados (sessões ao vivo). Commit só por pathspec |

## O achado do turno — o registro de pesquisa está parado há 12 dias

O cron `hunter-meme-close` **sai 1 desde 20/09, oito noites seguidas, patch de 0 linhas em todas**:
`KeyError: 'wallet_max_sol'` em `meme_diary.py:143`. Causa: `_RULE_SETS` lê as 30 linhas de
`meme_rule_sets` sem filtrar `status` e **uma** delas — `launch_v0/1`, criada em 19/09, hoje
`retired` — não declara teto de carteira (só `size_sol = 0.01`). Criada em 19/09, primeira falha em
20/09.

As avaliações datadas do Lab nascem daí (`Diario-Meme/`, `Hipoteses-do-plantao.md`, páginas
`05-EXPERIMENTS/`). Além das 8 noites que nem rodaram, o último fechamento **aplicado** foi o de
**14/09** (`8b5f5ea7`) — os patches de 15 a 19/09 rodaram verdes e nunca foram aplicados, e continuam
em `/opt/hunter-close/`. Nenhuma avaliação datada automática entrou no vault há **12 dias**. Passou
batido porque a ficha diária da mesa real (T4.92) e os diários à mão continuaram saindo.

Terceira ocorrência da classe da KB-0131 (dado incompleto derruba o processo inteiro): antes o
executor (T4.62) e o `meme-worker` (T4.65). Detalhe completo em `obsidian/07-BUGS/Open Bugs.md`.

## Em voo (não tocar)

- **T4.98 — FECHADA e commitada neste turno**, em duas rodadas, com o kit de revisão inteiro.
  Rodada 1: chave opcional com `.get`, `RuleSetDay.wallet_max_sol/balance_*: Decimal | None`, célula
  `— (sem teto declarado)`. **A Astra e o `code-reviewer` acharam, cada um por seu caminho, um HIGH que
  a rodada 1 criou:** `_goal` passou a somar o capital só dos conjuntos com teto mas manteve o PnL de
  todos no numerador, publicando percentual que base de capital nenhuma sustenta (o revisor reproduziu
  num render real: capital 2 SOL, **33,33 %/dia**). Rodada 2: as três linhas da seção 4 saem como
  `— (capital incompleto: …)` nomeando os conjuntos, sem chamar a conversão em dólar; o motivo das
  células de saldo deixou de ser `sem leitura` (que afirma falha de medição onde não houve falha); e a
  fronteira tipada do dublê virou um `Protocol` estreito, sem `type: ignore` nem `Any`.
  **Prova:** `test_meme_close_day_integration.py` → **3 passed in 84.00s** (Postgres real, migrações no
  `head`, `launch_v0/1` semeada pela 0053) — o mesmo teste que estava vermelho.
- **T4.98b (aberta, não começada):** isolar a falha por linha no `meme_close_day` — uma linha ruim não
  pode matar o fechamento inteiro. Mesma dívida da T4.65b.
- **T4.98c (aberta, e é a mais importante das duas):** a suíte de integração de `infra/scripts` não tem
  gatilho automático. O teste que reproduz este defeito existia e ficou **vermelho oito dias** sem
  ninguém rodar. Sem gatilho, o próximo defeito de dado semeado por migração passa igual.
- Sessão ao vivo do Everton: EXP-M26 (retenção madura, registro de oportunidades), saída `line_broken`,
  T4.96b, arrumação do Obsidian. Não commitei nada desses caminhos.
- **`08-CHANGELOG/Changelog.md` não entrou no commit deste turno**: está modificado e não commitado
  pela sessão ao vivo, e commitar por pathspec levaria o trabalho dela junto. A linha do fechamento
  quebrado entra no próximo turno, junto com a T4.98.

## O que preciso do Everton (em ordem)

1. **Deploy da T4.98 — ela está commitada e provada** (`compose.sh update`) e, em seguida, a recuperação
   dos 7 dias perdidos, um dia por vez:
   ```
   ssh hunter-vps 'for d in 2026-09-20 2026-09-21 2026-09-22 2026-09-23 2026-09-24 2026-09-25 2026-09-26; do bash /opt/project-hunter/infra/vps/meme_close_nightly.sh "$d"; done'
   ```
   Depois aplicar os patches de 15 a 19/09 que já estão em `/opt/hunter-close/` (`patch -p0` na raiz).
2. **Prune do Docker na VPS — negado ao plantão de novo** (~18 G, sem apagar dado nenhum: só cache de
   build e imagens sem uso):
   ```
   ssh hunter-vps 'docker builder prune -f --filter until=72h && docker image prune -f && df -h /'
   ```
3. **Retenção do banco — a decisão já é sua e está tomada; falta a implementação.** Corrigindo o que
   escrevi no meio deste turno: `docs/design/retencao-e-disco-2026-09-27.md` **existe** e você
   autorizou os passos 1–5 ([[2026-09-27-retencao-de-dados-e-backup]]). Medi de novo no fim do turno e
   confirmo os números da proposta: banco **129 G**, `opportunity_history_2026_09` **63 G**
   (era 25 G em 18/09), `outbox_events` **33 G** (era 17 G), volumes Docker **141,6 G**. E confirmo o
   que ainda não andou: **`/etc/cron.d` continua com só `hunter-backup` e `hunter-meme-close`** — as
   podas do passo 2 (outbox 7 d, partições) não estão instaladas. O próximo turno despacha o código dos
   passos 1–2 aos especialistas; os comandos que apagam dado continuam seus, pelo roteiro da §7.
4. Pendências antigas que continuam de pé: Groenlândia como `meme_event`, backup fora da VPS (serviço
   pago), e a stack local — postgres/redis/api/web pararam há 2 semanas e 3 workers ficam reiniciando
   sem banco na sua máquina.

## Dever fixo do plantão: exportação semanal cega da H-036 (desde 07/10/2026)

Toda **segunda-feira depois das 06:00Z**, rodar só leitura `.claude/state/h036/gen_export2.py` + `q.sh` (spread apenas, sem preços), conferir o sha256 e commitar o arquivo da semana com `git add` exato. Primeira: **2026-10-12**. Semana perdida dá para recuperar em até ~3 semanas; depois disso a medição de custo se perde (partições de `market_snapshots` caem 30–60 dias depois). Também a exportação complementar obrigatória em cada olhada (L1 2027-01-06, L2 2027-04-07, L3 2027-07-07, 12:00Z). **Não mexer na `mean_reversion v14`** (deprecar, substituir ou mudar parâmetro) até 2027-07-07: isso encerra a H-036 como LIMITE. Ver [[KB-0193]] e o bloco H-036 da Fila.

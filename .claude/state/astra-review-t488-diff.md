## RESUMO

**REQUEST_CHANGES.** A correção da banda morta está conectada ao tick, mas encontrei uma falha herdada de reconciliação que torna inseguro assumir `failed = não vendeu`, além de lacunas na escada e na visibilidade após restart.

Revisão como `code-reviewer`, somente leitura. Aceito sua decisão de limitar apenas o reenvio sem novo gatilho.

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit.

Li o `git diff` dos caminhos permitidos. Os dois testes estão **untracked**, portanto não aparecem no diff; examinei seu conteúdo diretamente.

Não revisei o diff de `.env.example`. Uma busca ampliada involuntariamente retornou uma linha desse exemplo; nenhum valor secreto apareceu.

## TESTES

**Não executados**, para preservar o modo sem escrita. As conclusões abaixo são de análise estática; não representam reprodução em teste nem validação na VPS.

A integração cobre falha **na simulação**, seguida de retentativa. Não reproduz a falha descoberta pela reconciliação nem a corrida no vencimento do blockhash. [test_exit_retry_integration.py:119](C:/dev/project-hunter/services/meme-executor/tests/test_exit_retry_integration.py:119)

## MUST-FIX

**1. HIGH — a reconciliação pode declarar expirada uma venda que pousou.**

Cenário concreto:

1. `reconcile` consulta a assinatura e recebe `None`.
2. A transação pousa no último bloco válido.
3. A consulta seguinte recebe altura superior ao limite.
4. O código grava `failed:blockhash_expired_never_landed`, **sem consultar novamente a assinatura**. [submit.py:219](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:219)
5. A nova rotina aceita esse `failed` como autorização para retentar. [exit_common.py:210](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:210)

**Resposta a (a): existe caminho para iniciar outra tentativa após pouso anterior. Não afirmo duas vendas bem-sucedidas dos mesmos tokens.** Se a primeira esvaziou a conta e a leitura está atualizada, a guarda de saldo impede o envio; porém deixa a posição bloqueada como divergência, sem registrar corretamente a saída. [exits.py:252](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:252)

É uma falha **preexistente**, agora consumida também pela retentativa automática. A proteção necessária já existe no outro caminho: consultar novamente a assinatura após detectar expiração e preservar incerteza. Aplicaria o mesmo tratamento à reconciliação, com teste dessa sequência. [confirm.py:68](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/confirm.py:68)

**2. MEDIUM — a escada é um no-op na PumpSwap.**

Cenário: posição migrada, primeira venda falha; dono configura `MEME_EXIT_PANIC_FROM_ATTEMPT=2`. A segunda tentativa continua usando tolerância apenas por motivo, porque a rota migrada retorna antes de `_sell` da curva e o construtor PumpSwap não chama o novo helper. [exits.py:210](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:210), [pumpswap_exit.py:121](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_exit.py:121)

Isso responde **(d)**: há um cenário operacional alcançável em que ligar a escada não produz efeito. Aplicaria o helper também nessa rota, com teste do `max_slippage_bps` efetivamente construído.

**3. MEDIUM — o bloqueio sobrevive ao restart, mas desaparece do heartbeat.**

Cenário: chega ao teto, grava `blocked`, reinicia e permanece na banda morta. O mapa `blocked_exits` nasce vazio; como a intenção já contém `blocked`, `pending_sell_retry` não chama novamente `mark_blocked`. O heartbeat publica o mapa vazio, embora a posição continue impedida de retentar automaticamente. [context.py:65](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/context.py:65), [exit_common.py:214](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:214), [heartbeat.py:216](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/heartbeat.py:216)

Restauraria a visibilidade pelo estado persistido, sem regravar o bloqueio nem incrementar o contador a cada tick.

**4. MEDIUM — “nunca acima do pânico” não está garantido.**

Cenário permitido pelo carregamento atual: tolerância normal de 20%, pânico de 15%, escada desde a tentativa 2. O helper retorna **2000 bps**, pois usa `max(normal, pânico)`. Os valores são carregados independentemente. [exit_common.py:148](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:148), [send_tuning.py:110](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/send_tuning.py:110)

É preciso garantir a relação entre as configurações ou aplicar exatamente a tolerância de pânico quando a escada dispara. O teste atual só exercita normal menor que pânico. [test_exit_retry_ladder.py:102](C:/dev/project-hunter/services/meme-executor/tests/test_exit_retry_ladder.py:102)

## NICE-TO-HAVE

**(e) Considero aceitável a consulta adicional na escala descrita, sem afirmar desempenho medido.** Ela filtra por proposta e lado, retornando uma ordem. Contudo, também acontece com retry desligado, intenção bloqueada ou backoff futuro: esses filtros poderiam anteceder o acesso ao banco. [repo.py:146](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/repo.py:146), [exit_common.py:207](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:207)

Acrescentaria testes de reconciliação sem `exit_intent.failed`, restart após teto e disputa tick/evento durante retentativa.

## O QUE EU FARIA DIFERENTE

**(b) Tick e `sell_on_event` estão corretamente serializados dentro do mesmo contexto:** ambos adquirem o mesmo lock e releem a posição. A reconciliação periódica, porém, não participa desse lock; portanto ele não resolve o primeiro achado. [exits.py:99](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:99), [exits.py:177](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:177), [main.py:148](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:148)

**(c) Apagar `attempt` não reinicia a numeração nem libera sozinho a retentativa.** `blocked` interrompe o helper; uma nova regra calcula a próxima tentativa pela última ordem. Preservaria o campo por diagnóstico, não por necessidade de deduplicação. [exit_common.py:162](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:162), [exits.py:223](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:223)

## CONCORDO COM

- Estado durável da ordem como gatilho; ausência de prazo significa devida agora. [exit_common.py:170](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:170)
- Escada desligada por padrão. [exit_common.py:57](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:57)
- Teto restrito à continuidade automática, conforme sua decisão explícita.
- A nova comparação de GAMON separa melhor os efeitos. Trato os números corrigidos como evidência fornecida por você, não como medição reproduzida nesta revisão.

## OBSIDIAN

- **Execution Engine** — documentar a corrida de expiração, o alcance do lock e a recuperação da visibilidade dos bloqueios.
- **Ficha do dia — 23/09/2026 · mesa real de memes** — registrar AIRAA corrigido e distinguir escada configurável de política ativada.
- **Revisoes-Astra/T4.88 — revisão do diff** — registrar os quatro achados e os testes necessários para encerrá-los.
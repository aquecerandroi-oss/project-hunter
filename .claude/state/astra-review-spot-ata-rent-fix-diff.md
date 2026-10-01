## RESUMO

**DONE_WITH_CONCERNS — não aprovaria o diff ainda.** Há três must-fix: financiamento da ATA não comprovado, criação ignorada quando existe outra conta do mesmo mint e idempotência que não verifica toda a contabilidade persistida.

Conferência dos quatro pontos do parecer anterior:

| Must-fix anterior | Resultado |
|---|---|
| Quantidade histórica e risco original | **Essencial absorvido:** usa `entry.filled_atoms` e preserva `initial_risk_sol`. Falta cruzar também com o fill da ordem. [spot_fix_ata_rent.py:158](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:158) |
| Recuperação de fill legado | **Absorvido pelo fallback conservador:** aluguel legado positivo vira desconhecido. [spot_send_rules.py:174](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:174) |
| Prova de financiamento pela carteira | **Não absorvido:** derivar o endereço da ATA não comprova quem depositou os lamports. [spot_send_rules.py:224](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:224) |
| Atomicidade e comparação completa | **Parcial:** bloqueio, `RETURNING` e transação única estão presentes; `changed` ainda ignora campos corrigidos em `entry`/`params`. [spot_fix_ata_rent.py:122](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:122) |

A [KB-0171](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0171-custo-real-da-spot-1.md) fundamenta a correção contábil; [Perdas-spot-1](C:/dev/project-hunter/obsidian/03-TRADING/Spot/Perdas-spot-1.md:92) reforça que gasto incorreto também desloca stop/alvo.

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os diffs indicados e os quatro arquivos novos. As alterações concorrentes de KB-0172 não recebem aprovação neste parecer.

## TESTES

Executei com sincronização do ambiente, bytecode e cache do pytest desativados:

```text
uv run pytest services/meme-executor/tests/test_spot_ata_rent.py services/meme-executor/tests/test_spot_ata_rent_openers.py services/meme-executor/tests/test_spot_entries.py services/meme-executor/tests/test_spot_reconcile.py services/meme-executor/tests/test_spot_reconcile_repair.py -q -p no:cacheprovider -p pytest_asyncio.plugin

70 passed in 4.53s
```

```text
uv run python infra/scripts/check_file_size.py

scanned 1114 files; 0 over budget, 0 grandfathered
```

Sondas adicionais em memória, executando o código revisado:

```text
third-party funded: rent= 1488440 spend= 48516560 wallet outflow= 50005000
existing second account + new ATA: created= False rent= 0 source= signature_delta_minus_rent
stale entry and params: changed= False
```

Não executei a integração com PostgreSQL, SSH, RPC da carteira nem o script operacional.

## MUST-FIX

**1. HIGH — a prova de financiamento continua ausente.**

[spot_send_rules.py:224](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:224) verifica o endereço derivado e subtrai o aumento de saldo. O script histórico chama esse extrator sem validar instruções de financiamento: [spot_fix_ata_rent.py:152](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:152).

**Cenário reproduzido:** carteira desembolsa 50.005.000 lamports; terceiro financia 1.488.440 na ATA da carteira. O extrator aceita esse aluguel e calcula gasto de 48.516.560, inflando o PnL em 1.488.440.

O verificador exige pagador correto **quando encontra uma instrução ATA externa**, mas isso não vincula cada depósito identificado pelo extrator à criação verificada: [spot_verify.py:148](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:148).

**Correção:** vincular a conta e o aporte às instruções verificadas, inclusive no reparo histórico. Sem prova, retornar desconhecido; no script, recusar. A reprodução é sintética, não evidência de financiamento externo nas quatro posições reais.

**2. MEDIUM — uma conta anterior do mesmo mint esconde a ATA nova.**

[spot_send_rules.py:275](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:275) mantém `ata_created = seen_after and not seen_before`. Assim, a lista `created`, construída por índice, pode ser ignorada.

**Cenário reproduzido:** conta secundária vazia do mesmo proprietário/mint aparece antes e depois; ATA nova aparece somente depois, com depósito legível. Resultado: `ata_created=False`, aluguel zero e fonte `signature_delta_minus_rent`.

Isso incorpora aluguel ao gasto **sem sinalizar desconhecimento**. O gasto aumentado reduz `r_now`, podendo antecipar stop: [spot_exit_rules.py:78](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:78). A posição também escapa da seleção do reparo, que procura aluguel positivo ou fonte degradada: [spot_fix_ata_rent.py:77](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:77).

**Correção:** decidir criação pelos índices das contas novas, independentemente de outra conta preexistente do mesmo mint.

**3. MEDIUM — `already correct` pode preservar campos contábeis divergentes.**

[spot_fix_ata_rent.py:124](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:124) compara colunas principais, fonte e R. Entretanto, o reparo também escreve gasto/aluguel em `entry`, aluguel em `params` e `params.entry_sol_per_atom`: [spot_fix_ata_rent.py:200](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:200).

**Cenário reproduzido:** correção anterior ajustou as colunas principais, mas deixou aluguel antigo e preço incorreto nos JSONs. `Fix.changed=False`; o script declara a posição correta e não repara essas divergências.

**Correção:** incluir na leitura e na comparação os campos derivados que o próprio reparo promete corrigir.

## NICE-TO-HAVE

- **Metadados inválidos:** validar índices antes de montar/consultar `pre_indexes`. Um `accountIndex=[]` produz `TypeError` antes das guardas de `_created_rent`. Também rejeitar saldos não inteiros: reproduzi `1488440.75 → 1488440` por truncamento. [spot_send_rules.py:258](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:258), [spot_send_rules.py:229](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:229).
- **Pré-financiamento:** o delta parcial está correto, mas a fixture desconta o pré-financiamento duas vezes do desembolso da carteira; corrigir e testar o gasto final. [test_spot_ata_rent.py:61](C:/dev/project-hunter/services/meme-executor/tests/test_spot_ata_rent.py:61). Integralmente pré-financiada retorna `None`; é conservador, mas poderia aceitar zero com prova de inicialização sem aporte. O [programa oficial](https://raw.githubusercontent.com/solana-program/associated-token-account/main/program/src/tools/account.rs) contempla inicialização sem transferência adicional.
- **Rollback após escrita:** acrescentar teste em que a última guarda falha depois de uma atualização/auditoria anterior. O teste atual recusa durante o planejamento, antes das escritas. [test_spot_fix_ata_rent.py:295](C:/dev/project-hunter/infra/scripts/tests/test_spot_fix_ata_rent.py:295).
- **Documentação:** trocar “dobrado no gasto” por “incorporado ao gasto”; separar reserva conservadora de tolerância da simulação — aumentar esta tolerância afrouxa o limite de débito. [RISK_ENGINE_MEME.md:2508](C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:2508).

## O QUE EU FARIA DIFERENTE

**R e idempotência:** não vejo oscilação causada pelo arredondamento. A coluna é `NUMERIC(28,10)`; seu arredondamento introduz erro máximo de `5e-11`, abaixo de `1e-9`. [spot_desk.py:190](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:190), [documentação PostgreSQL](https://www.postgresql.org/docs/16/datatype-numeric.html).

Sonda com divisão não terminante:

```text
r= -0.1963232876712328767123287671
stored= -0.1963232877
error= 2.87671232876712329E-11
stable= True
```

Eu preferiria quantizar o R à escala persistida e comparar exatamente, tornando explícita a representação esperada. A tolerância atual funciona; o problema bloqueante é a comparação incompleta dos demais campos.

**Guard do UPDATE:** comparar `r_multiple` com o **Decimal lido**, sem recalculá-lo, é adequado. `old_r` vem de `before`, e a posição permanece bloqueada desde o SELECT. Não há problema de igualdade binária de float aqui. [spot_fix_ata_rent.py:79](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:79), [spot_fix_ata_rent.py:217](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:217).

## CONCORDO COM

- **ALT e `jsonParsed`:** funcionaram nas sondas. `json` concatena estáticas, writable e readonly; no formato parsed normal, as chaves já vêm expandidas e `loadedAddresses` é omitido. [spot_send_rules.py:195](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:195), [contrato RPC Solana](https://solana.com/docs/rpc/json-structures).
- **Atomicidade:** `FOR UPDATE OF p`, exigência de uma linha retornada e auditoria dentro da mesma transação atendem à proteção contra atualização parcial. [spot_fix_ata_rent.py:221](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:221), [spot_fix_ata_rent.py:303](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:303).
- **Dry-run e portão Obsidian:** aplicação é opt-in e a nota é validada antes das escritas. [spot_fix_ata_rent.py:271](C:/dev/project-hunter/infra/scripts/spot_fix_ata_rent.py:271).
- **Runbook PowerShell/SSH:** os comandos estão corretamente construídos; `&&` fica na string enviada ao shell remoto. `ops` usa a imagem implantada, os scripts estão na imagem e Obsidian está montado em `/app/obsidian:ro`. Não validei conectividade nem o estado da VPS. [RISK_ENGINE_MEME.md:2528](C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:2528), [compose.sh:250](C:/dev/project-hunter/infra/vps/compose.sh:250), [Dockerfile.api-workers:95](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:95), [docker-compose.yml:128](C:/dev/project-hunter/infra/docker/docker-compose.yml:128).

## OBSIDIAN

- **Open Bugs:** manter KB-0171 aberta até fechar os três cenários reproduzidos.
- **KB-0171 — Custo real da spot/1:** registrar prova de financiamento e criação por conta/índice.
- **Revisões Astra — correção do aluguel ATA:** guardar este parecer, os 70 testes e as reproduções adicionais.
- **Spot — README:** documentar proveniência e tratamento conservador de aluguel desconhecido.
- **Mesa-spot-1 / Perdas-spot-1:** atualizar números somente depois do reparo aplicado e conferido; esta revisão não alterou o placar.
**RESUMO**

**REQUEST_CHANGES: dois must-fix.** A assinatura antes do broadcast está correta, mas a correção do fill ficou incompleta e o motivo do reconcile não permanece no heartbeat. Revisão no papel `code-reviewer`, somente leitura.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Li os arquivos indicados, os consumidores do influxo, o CHECK e as referências spot.

**TESTES**

Não executei pytest ou lint nesta revisão. Os achados abaixo decorrem da inspeção do código; não declaro testes passando.

**MUST-FIX**

1. **HIGH — A confirmação imediata ainda pode apagar o influxo da tesouraria.**  
   [treasury_send.py:258](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:258) continua relendo a carteira; se essa leitura falhar, usa o saldo anterior e grava `confirmed` com fill zero. O novo parser foi aplicado apenas ao reconcile.

   **CENÁRIO DE FALHA:** a troca confirma e acrescenta 0,05 SOL; `chain.wallet` sofre timeout. A linha termina `confirmed`, com `sol_out_filled=0`, e deixa de ser selecionada pelo reconcile. `sol_inflow_since` usa esse zero, pois `coalesce` só substitui `NULL`. Uma perda real de 0,16 SOL pode aparecer como 0,11 SOL, deixando passar o teto de 0,15. As consultas estão em [treasury_db.py:50](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:50).

   **Correção:** usar o meta desta assinatura também na confirmação imediata; meta indisponível mantém `submitted`. Compartilhar a liquidação entre os dois caminhos evita essa divergência. É uma lacuna preexistente que a T4.84 ainda deixa aberta.

2. **MEDIUM — O restante do tick sobrescreve o motivo recém-publicado pelo reconcile.**  
   [treasury_reconcile.py:76](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:76) grava `failed:...`, mas o chamador continua e substitui o campo por `reason or ""` em [treasury.py:105](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury.py:105). O heartbeat publica justamente esse campo: [heartbeat.py:323](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/heartbeat.py:323).

   **CENÁRIO DE FALHA:** uma tentativa de 200 segundos expira; o reconcile grava `failed:blockhash_expired_never_landed`. Como ainda está dentro do intervalo mínimo de 600 segundos, o tick sobrescreve o resultado com a recusa de intervalo. O próximo heartbeat perde a distinção prometida entre expiração e erro on-chain.

   **Correção:** preservar separadamente o resultado da reconciliação e o motivo de não tentar outra troca. O teste atual chama apenas `reconcile_once`, portanto não atravessa a sobrescrita: [test_treasury_tick.py:415](C:/dev/project-hunter/services/meme-executor/tests/test_treasury_tick.py:415).

**NICE-TO-HAVE**

**c) Sim, uma linha pode continuar `submitted` indefinidamente; não, ela não prende indefinidamente o teto diário.**

Status confirmado com meta permanentemente indisponível, ilegível ou delta não positivo não tem saída automática em [treasury_reconcile.py:99](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:99). Porém, o teto filtra `requested_at` nas últimas 24 horas: [treasury_db.py:45](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:45).

O pior caso operacional é acumular pendências sem resolução: reserva de USDC até envelhecer, influxo estimado pela cotação enquanto estiver na janela do dia e consultas repetidas para sempre. O reconcile seleciona todas as pendências sem corte de idade e consulta os metas sequencialmente; esse trabalho antecede a atualização do influxo no tick: [treasury_db.py:56](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:56), [main.py:172](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:172).

Recomendo expor quantidade/idade das pendências e um procedimento de resolução auditada. **Não transformar ausência de meta em `failed` por timeout.**

**O QUE EU FARIA DIFERENTE**

**d) Priorizaria estes testes:**

- Confirmação imediata com carteira movimentada por outra operação e com leitura de saldo falhando — reproduz o must-fix 1.
- Tick completo seguido da montagem do heartbeat — reproduz o must-fix 2.
- Falha ao concluir a transação de banco de `mark_submitted`: nenhum broadcast deve ocorrer. O teste existente verifica a chamada do marcador antes do envio, mas o fake de sessão não simula commit: [test_treasury_send_ambiguous.py:65](C:/dev/project-hunter/services/meme-executor/tests/test_treasury_send_ambiguous.py:65), [treasury_send_rig.py:222](C:/dev/project-hunter/services/meme-executor/tests/treasury_send_rig.py:222).
- Envio aceito com resposta perdida → reinício → reconcile duas vezes: uma linha, um preenchimento, nenhum reenvio.
- CHECK real para `submitted → failed` preservando assinatura; delta de um lamport com `Decimal`; bordas de 24 horas e da virada do dia operacional.

**CONCORDO COM**

**a) O CHECK permite essas escritas.** `failed` pode conservar assinatura, desde que `refusal` continue `NULL`; a recusa do signer ocorre antes de persistir assinatura. `confirmed` exige assinatura e ambos os valores preenchidos, não exige saldo observado ao vivo: [meme_treasury_swaps.py:58](C:/dev/project-hunter/infra/migrations/ddl/meme_treasury_swaps.py:58). `SendDisabled` é lançado antes da chamada de rede, portanto essa transição é legítima: [tx_rpc.py:237](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:237).

**b) A soma não distorce os consumidores citados.** O influxo lê `sol_out_filled`, não `wallet_sol_after`; o heartbeat da tesouraria também não expõe esse saldo: [treasury_db.py:50](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:50), [heartbeat.py:308](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/heartbeat.py:308). É um **saldo reconstruído**, não uma fotografia histórica da carteira. Essa distinção precisa permanecer explícita para auditoria.

**e) Concordo com `WRAPPED_SOL_MINT` nesse uso.** O delta nativo vem de `postBalances[0] − preBalances[0]`, independentemente do mint. O mint apenas filtra os saldos de token. Ressalva: o helper ainda exige listas de tokens legíveis, mesmo ignorando seus deltas: [spot_send_rules.py:159](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:159).

**OBSIDIAN**

- **KB-0129 — O cap de perda diária era cego a entradas da tesouraria:** registrar que a confirmação imediata ainda pode zerar indevidamente o influxo.
- **KB-0130 — Tesouraria USDC→SOL:** registrar a proteção do envio ambíguo e os dois bloqueios restantes desta revisão.
- **Revisões-Astra / T4.84:** registrar o parecer e distinguir pendência permanente de reserva limitada à janela de 24 horas.
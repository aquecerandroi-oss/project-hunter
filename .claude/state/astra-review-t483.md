## RESUMO

**A T4.83 corrige os dois defeitos de ALT.** Não encontrei regressão na resolução nem caminho que pule a derivação da ATA. Porém, encontrei um **must-fix preexistente no envio**, relevante para a pergunta sobre segurança do fluxo completo.

Revisão como `code-reviewer`, em modo OPINIÃO.

## ARQUIVOS

Li os seis arquivos indicados e os auxiliares de decodificação, persistência e reconciliação. **Nenhum arquivo criado ou modificado; nenhum commit.**

## TESTES

Executei, com sincronização, rede do uv, bytecode e cache do pytest desabilitados:

```text
uv run pytest services/meme-executor/tests/test_treasury_verify_alt.py services/meme-executor/tests/test_treasury_send_alt.py services/meme-executor/tests/test_treasury_verify.py services/meme-executor/tests/test_spot_alt.py -q

76 passed in 1.19s
```

Também executei duas sondas com os fakes existentes, por `uv run python -`, somente em memória:

```text
signer_exception: RuntimeError statuses: ['quoted', 'simulated'] sent: 0
send_timeout: send_failed:TimeoutError statuses: ['quoted', 'simulated', 'failed'] sent: 1
```

A segunda sonda simula aceitação seguida de perda da resposta; não houve envio real. Não executei lint/typecheck nem prova na cadeia.

## MUST-FIX

**HIGH — timeout de envio é tratado como falha definitiva. Preexistente, não introduzido pela T4.83.**

Em [treasury_send.py:208](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:208), qualquer exceção de `send_transaction` marca a tentativa como `failed`, sem persistir a assinatura. Entretanto, o teto diário só soma `submitted/confirmed`, e a reconciliação só busca `submitted` com assinatura: [treasury_db.py:45](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:45).

**Cenário concreto:** o RPC recebe a transação, a resposta se perde e o swap confirma. Localmente fica `failed`: o gasto desaparece do teto diário e a tentativa não é reconciliada. Com novas reposições, o limite pode ser excedido.

**Correção:** calcular e persistir a assinatura antes do envio; preservar resultado ambíguo como pendente e reconciliável, contado no teto. Não converter timeout em recusa definitiva. Acrescentar o teste “aceitou, perdeu resposta, confirmou depois”.

## NICE-TO-HAVE

Respostas às cinco perguntas:

1. **Ordem correta.** O resolvedor concatena estáticas + writable de todas as tabelas + readonly de todas as tabelas: [spot_alt.py:179](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:179), consistente com o [SDK oficial](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/loaded.rs). ATA, token e rota recebem essa lista. As leituras restantes de estáticas são corretas: pagador e programa de topo, cujo índice é previamente validado. [treasury_verify.py:293](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_verify.py:293)

2. **Derivação obrigatória para toda criação de ATA aceita.** `ata_accounts_unresolved` é **inalcançável no fluxo normal tipado**: seis posições são exigidas e todos os índices já foram validados. A recusa efetiva será `ata_instruction_account_count`, `account_index_out_of_range` ou uma recusa anterior de resolução. Removeria a guarda redundante ou documentaria essa condição; não criaria teste artificial para alcançá-la. [treasury_verify.py:161](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_verify.py:161)

3. **Nenhuma proteção aplicável foi perdida na troca de nome.** Posição ausente é `route_account_count`; índice inválido é recusado antes; endereço carregado errado continua sujeito às mesmas comparações. O laço adicional de posições também é redundante nos dois layouts atuais, porque `fee_account` é a maior posição checada. [treasury_verify.py:260](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_verify.py:260)

4. **Resolução precede verificação, simulação e assinatura**, em `to_thread`, usando o padrão `finalized`. A assinatura usa `decoded.message_bytes`, sem reconstruir a mensagem. [treasury_send.py:121](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:121), [treasury_send.py:206](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:206). **Há exceção que escapa:** `sign()` fica fora do tratamento; a sonda deixou a linha em `simulated`, sem envio nem recusa. É preexistente; acrescentaria tratamento nomeado para falha anterior ao envio.

5. **Os testes sustentam a correção, com limites claros.** A fixture é capturada, mas as ALTs são sintéticas, explicitamente declaradas: [test_treasury_verify_alt.py:19](C:/dev/project-hunter/services/meme-executor/tests/test_treasury_verify_alt.py:19). A ordem entre duas tabelas está coberta no resolvedor compartilhado: [test_spot_alt.py:157](C:/dev/project-hunter/services/meme-executor/tests/test_spot_alt.py:157). Falta fortalecer o teste integrado: o fake de simulação ignora `raw` e sempre retorna saldos favoráveis. Registraria as bytes simuladas e acrescentaria ALT válida com simulação recusada ou USDC excedido, exigindo zero assinaturas/envios. [test_treasury_send_alt.py:103](C:/dev/project-hunter/services/meme-executor/tests/test_treasury_send_alt.py:103)

## O QUE EU FARIA DIFERENTE

Corrigiria a explicação do teste de mint adulterado: **mint incompatível com a ATA provoca rejeição on-chain**, não criação bem-sucedida com rent gasto. Além disso, derivar corretamente não restringe o mint a WSOL/USDC: uma ATA corretamente derivada de outro mint continua aceita pelas regras atuais. [test_treasury_verify_alt.py:122](C:/dev/project-hunter/services/meme-executor/tests/test_treasury_verify_alt.py:122), [treasury_verify.py:177](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_verify.py:177)

## CONCORDO COM

Reutilizar `spot_alt`, manter IO no chamador e verificador puro, preservar recusas nomeadas e assinar a mensagem original. A fronteira de confiança está corretamente documentada: `validated_account_keys` valida formato e índices; a autenticidade do conteúdo carregado depende do resolvedor. [spot_alt.py:249](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:249)

## OBSIDIAN

- **Revisões Astra — T4.83** — registrar aprovação técnica das ALTs, 76 testes e limitações da prova.
- **Open Bugs** — registrar envio ambíguo tratado como `failed`, com impacto no teto e na reconciliação.
- **KB-0130 — Tesouraria USDC→SOL** — acrescentar resolução em `finalized` e distinguir derivação de ATA de restrição de mint.
- **Diário — 2026-09-23** — registrar o parecer sem declarar validação na cadeia.
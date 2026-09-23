**RESUMO**

**APPROVE_WITH_NITS.** Não encontrei must-fix com cenário concreto de falha introduzido pela T4.81. A ordem está correta e não identifiquei desvio entre a mensagem verificada e a assinada. A ressalva principal: as checagens de fronteira **dependem de uma resolução confiável**; não autenticam sozinhas o conteúdo da lista.

**ARQUIVOS**

Revisei os quatro arquivos novos e o `git diff` dos modificados indicados. Nenhum arquivo criado ou modificado.

**TESTES**

Executei, com sincronização do ambiente, bytecode e cache do pytest desabilitados:

```text
uv run pytest services/meme-executor/tests/test_spot_alt.py services/meme-executor/tests/test_spot_verify_alt.py services/meme-executor/tests/test_spot_alt_money_path.py services/meme-executor/tests/test_spot_verify.py services/meme-executor/tests/test_spot_money_path.py infra/scripts/tests/test_meme_spot_swap_plan.py infra/scripts/tests/test_meme_spot_swap_send.py -q

85 passed in 1.40s
```

Não executei lint/typecheck nem repeti sua mutação.

**MUST-FIX**

Nenhum identificado no escopo revisado.

**NICE-TO-HAVE**

- **Testar tabela congelada explicitamente.** A fixture atual sempre serializa `authority=Some`; falta proteger o caso `None`, com metadados serializados de 24 bytes e endereços começando em 56. [spot_tx_fixtures.py:194](C:/dev/project-hunter/services/meme-executor/tests/spot_tx_fixtures.py:194).
- **Fixar igualdade dos bytes no teste financeiro.** O teste prova sequência e recusas, mas não compara a mensagem entregue ao signer com a mensagem original nem com a enviada. O fake já guarda `signed`, facilitando essa asserção. [test_spot_alt_money_path.py:44](C:/dev/project-hunter/services/meme-executor/tests/test_spot_alt_money_path.py:44), [spot_fakes.py:231](C:/dev/project-hunter/services/meme-executor/tests/spot_fakes.py:231).
- **Completar bordas:** índice repetido dentro da mesma lista, tabela repetida com seleções disjuntas, índice exatamente igual ao tamanho da tabela e total de chaves 256/257. Hoje há cobertura de duas tabelas, tabela repetida e outros caps, mas esses casos merecem expectativas explícitas. [test_spot_alt.py:155](C:/dev/project-hunter/services/meme-executor/tests/test_spot_alt.py:155), [test_spot_alt.py:187](C:/dev/project-hunter/services/meme-executor/tests/test_spot_alt.py:187), [test_spot_alt.py:228](C:/dev/project-hunter/services/meme-executor/tests/test_spot_alt.py:228).
- **Precisar a evidência “real”.** O teste usa a transação capturada, mas constrói uma ALT sintética colocando WSOL no índice 11. Prova a interpretação dos índices **sob essa hipótese**, não que a tabela real contém WSOL ali. Ajustaria a descrição ou acrescentaria um snapshot real gravado. [test_spot_verify_alt.py:180](C:/dev/project-hunter/services/meme-executor/tests/test_spot_verify_alt.py:180).

**O QUE EU FARIA DIFERENTE**

Documentaria expressamente que `account_keys` é entrada confiável produzida pelo resolvedor. Também consideraria exigir tamanho exato: `static + quantidade de posições dos lookups`. Atualmente, o prefixo estático pode estar correto com um sufixo errado; o próprio teste de ordem invertida demonstra que isso pode passar pelo verificador. Não é um bypass nos chamadores atuais, que usam o resolvedor correto. [spot_alt.py:235](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:235), [test_spot_verify_alt.py:163](C:/dev/project-hunter/services/meme-executor/tests/test_spot_verify_alt.py:163).

**CONCORDO COM**

1. **Ordem correta e completa.** A implementação produz `static + W₁ + W₂ + … + R₁ + R₂ + …`. Cada ocorrência e cada índice repetido acrescenta uma posição; só o fetch é deduplicado. Não encontrei divergência de ordem para os casos perguntados. [spot_alt.py:152](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:152), [spot_alt.py:167](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:167). Isso corresponde ao [`LoadedAddresses::from_iter` do SDK](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/loaded.rs#L47).

2. **Fronteiras suficientes no fluxo atual, não isoladamente.** Programas permanecem estáticos; índices de contas são conferidos antes das checagens; contas carregadas passam pelas mesmas funções de validação. Índices negativos não vêm do decoder, que extrai bytes unsigned. A identidade do sufixo depende do resolvedor e do RPC confiável. [spot_alt.py:248](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:248), [spot_verify.py:299](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:299), [versioned_tx.py:115](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/jupiter/versioned_tx.py:115).

3. **Resolução antes da assinatura, sem substituição da mensagem.** O decoder deriva `message` dos mesmos `message_bytes` preservados; `spot_leg` resolve em `to_thread`, verifica e posteriormente assina esses bytes, sem reconstrução. [versioned_tx.py:151](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/jupiter/versioned_tx.py:151), [spot_send.py:159](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:159), [spot_send.py:224](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:224). Precisão: erros RPC viram `TreasurySwapRefused`; outras exceções inesperadas também recusam, pelo fallback `swap_build_failed:<Tipo>`. [spot_alt.py:205](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:205), [spot_send.py:161](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:161).

4. **Layout correto para `Some` e `None`.** Tag no offset 21, desativação em 4–11 e endereços sempre em 56. Não encontrei campo adicional cuja ausência permita resolver outro endereço no fluxo atual. [spot_alt.py:129](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_alt.py:129). O [SDK confirma a região fixa e os tamanhos 56/24](https://github.com/anza-xyz/solana-sdk/blob/master/address-lookup-table-interface/src/state.rs#L226).

5. **Os testes têm valor real, com os limites acima.** Duas tabelas distinguem `W₁,W₂,R₁,R₂` de concatenação por tabela; a armadilha de destino demonstra por que inverter segmentos é perigoso. [test_spot_alt.py:155](C:/dev/project-hunter/services/meme-executor/tests/test_spot_alt.py:155), [test_spot_verify_alt.py:163](C:/dev/project-hunter/services/meme-executor/tests/test_spot_verify_alt.py:163).

**Sobre suas rejeições:** concordo em não bloquear por duplicatas. Apenas não sustentaria que uma detecção correta necessariamente arriscaria falso positivo: repetir tabela é diferente de repetir chave expandida. A checagem seria diagnóstico antecipado, não correção de identidade; o [SDK detecta duplicatas separadamente](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/loaded.rs#L119).

Também concordo em não exigir warm-up aqui. `finalized` não apaga a regra no slot histórico da extensão; a execução futura é que ocorre depois dele. A regra altera disponibilidade naquele slot, não o endereço resolvido. [SDK: `get_active_addresses_len`](https://github.com/anza-xyz/solana-sdk/blob/master/address-lookup-table-interface/src/state.rs#L157).

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — registrar resolução finalizada e a confiança exigida do resolvedor/RPC.
- **Revisões Astra / T4.81** — registrar aprovação com ressalvas, 85 testes passando e limitações da fixture real.
- **Diário — 2026-09-23** — registrar duplicatas e warm-up como não bloqueantes, com as justificativas acima.
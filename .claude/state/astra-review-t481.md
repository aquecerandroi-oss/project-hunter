**RESUMO**

**Confirmo a ordem proposta. Não aprovaria o argumento de estabilidade usando apenas `confirmed`: falta considerar forks.** Também corrigiria a afirmação sobre lookups vazios e a descrição de `authority=None`.

Revisão como `security-reviewer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. O bloqueio atual está em [spot_verify.py:155](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:155).

**TESTES**

Não executei pytest. Fiz uma leitura binária independente da fixture, em memória com PowerShell; saída real relevante:

```text
static_keys=15
instruction[2] program_index=10 accounts=0,1,0,18,4,7
lookups=1
lookup[0] writable=244,138,137 readonly=11,139,246,243
consumed=794 total=794
```

Isso confirma os índices informados, **não o conteúdo de `tabela[11]`**: a fixture tem `addressesByLookupTableAddress: null` em [jupiter_swap_usdc_to_sol_real.json:16](C:/dev/project-hunter/services/meme-executor/tests/fixtures/jupiter_swap_usdc_to_sol_real.json:16).

**MUST-FIX**

1. **ALTA — resolver em `finalized` para sustentar a garantia de identidade.** Ponto de integração: [spot_send.py:153](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:153).

   Cenário: uma extensão no fork A coloca a conta esperada no índice `i`; leitura e simulação `confirmed` passam. Esse fork é abandonado; no fork B, outra extensão coloca uma conta diferente no mesmo índice. Se a transação continuar válida nesse ramo, a assinatura autoriza a resolução diferente. Não houve reescrita dentro de uma história: houve duas histórias.

   **Recomendação:** resolver os índices exclusivamente a partir de um snapshot `finalized`; índice ainda ausente deve falhar fechado, sem fallback para `confirmed`. A finalização precisa abranger **a extensão que introduziu os endereços usados**, não apenas a criação da tabela. A própria Anza descreve esse ataque e recomenda finalização ou verificações de integridade dentro da transação. [Anza, *Front running*](https://docs.anza.xyz/proposals/versioned-transactions/#front-running).

   Usar o mesmo commitment na leitura e na execução não fixa o fork. A simulação anterior à assinatura, existente em [spot_send.py:177](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:177), tampouco constitui uma verificação atômica na execução.

2. **MÉDIA — recusar lookup com `writable_indexes` e `readonly_indexes` ambos vazios.**

   Cenário: o verificador aceita a mensagem, mas o runtime a rejeita no `sanitize`; a rota nunca executa. Não autoriza outra conta, porém contradiz a proposta de aceitar uma forma válida para destravar a mesa.

   Uma das listas vazia é válida; **as duas vazias no mesmo lookup não são**. Acrescentaria `lookup_table_empty:<addr>`. Fonte: [`Message::sanitize`, linhas 127–137](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/mod.rs#L127).

**NICE-TO-HAVE**

- Em `lookup_table_malformed`, validar também o tag de `Option` como `0` ou `1` e limitar a tabela a 256 endereços. Os caps 8/128 são políticas locais; não substituem a validação estrutural.
- Recusar **chaves finais duplicadas**, sem deduplicá-las. Repetir o endereço da tabela com seleções disjuntas é diferente de carregar a mesma conta duas vezes. O runtime detecta duplicidade na lista expandida. [`LoadedMessage::has_duplicates`](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/loaded.rs#L119).
- Se quiser equivalência de disponibilidade no slot do snapshot, considerar o *warm-up*: quando `current_slot == last_extended_slot`, só índices anteriores a `last_extended_slot_start_index` estão ativos. Ignorá-lo pode aceitar algo que ainda falha naquele slot; não muda o endereço resolvido. [`get_active_addresses_len`](https://github.com/anza-xyz/solana-sdk/blob/master/address-lookup-table-interface/src/state.rs#L157).

**O QUE EU FARIA DIFERENTE**

**Layout:** o offset dos endereços é sempre **56**, mas `Option<Pubkey>` não ocupa sempre 33 bytes.

| Campo | Offset, base zero |
|---|---:|
| Discriminante `u32`, little-endian | 0 |
| `deactivation_slot`, `u64` little-endian | 4 |
| `last_extended_slot`, `u64` little-endian | 12 |
| `last_extended_slot_start_index` | 20 |
| Tag de `authority` | 21 |
| Pubkey, somente para `Some` | 22–53 |
| Padding serializado para `Some` | 54–55 |
| Primeiro endereço | **56** |

Com `None`, o padding serializado fica em 22–23; o estado serializado ocupa 24 bytes, mas a região reservada continua tendo 56. **Nunca começar os endereços no cursor final da desserialização.** Uma tabela congelada é válida. O SDK testa explicitamente os tamanhos 56 e 24. [`state.rs`, teste do tamanho](https://github.com/anza-xyz/solana-sdk/blob/master/address-lookup-table-interface/src/state.rs#L275).

**Prova da ordem:** sua fixture distingue writable→readonly de readonly→writable:

```text
15 = tabela[244]
16 = tabela[138]
17 = tabela[137]
18 = tabela[11]
19 = tabela[139]
20 = tabela[246]
21 = tabela[243]
```

Invertendo os segmentos, `18` realmente seria `tabela[243]`. Mas:

- Falta um snapshot real da ALT para demonstrar `tabela[11] == WSOL` e conferir a ATA derivada.
- Uma única tabela **não distingue** `W₁,W₂,R₁,R₂` de `W₁,R₁,W₂,R₂`.

Eu exigiria também um teste com duas tabelas, ambas contendo writable e readonly, e endereços distintos. O resultado esperado seria explicitamente `static + W₁ + W₂ + R₁ + R₂`.

Manteria um snapshot por endereço de tabela, mas percorreria **todas as ocorrências do lookup na ordem original**. Pode deduplicar o fetch; não pode deduplicar, ordenar ou omitir posições na expansão.

Preservaria ainda a separação entre resolução de contas e de programas: hoje `_key` usa `message.program_id` em [spot_verify.py:118](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:118). Ao ampliá-lo, não ampliar junto a resolução do programa feita em [spot_verify.py:307](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:307).

**CONCORDO COM**

- **Ordem:** `static + todos os writable + todos os readonly`, preservando ordem das tabelas e dos índices. O [loader do Agave](https://github.com/anza-xyz/agave/blob/master/runtime/src/bank/address_lookup_table.rs#L21) percorre os lookups; [`LoadedAddresses::from_iter`](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/loaded.rs#L47) concatena cada categoria separadamente; [`AccountKeys`](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/account_keys.rs) apresenta os três segmentos. Não existe uma ordem alternativa para repetidos: preservam posições ou provocam rejeição posterior.
- **`program_via_lookup_table`: manter.** O `program_id_index` das instruções compiladas de topo deve apontar para uma chave estática. Isso não impede programas chamados por CPI de aparecerem como contas carregadas. [`Message::sanitize`, linhas 162–178](https://github.com/anza-xyz/solana-sdk/blob/master/message/src/versions/v0/mod.rs#L162).
- **Tabela duplicada:** concordo em não recusar só pela repetição do endereço, usando o mesmo snapshot e preservando cada ocorrência.
- **Recusas propostas:** concordo com ausência de resolução, falha RPC, conta ausente, owner incorreto, formato inválido, índice fora da faixa e caps. Contar posições carregadas, não endereços únicos.
- **Desativação:** `deactivation_slot != u64::MAX` é uma política conservadora válida, mais restritiva que o cooldown do runtime.
- **Append-only e não recriação:** correto dentro da mesma história da cadeia. O programa só acrescenta endereços e impede fechamento até passar o cooldown, que inviabiliza reutilizar o slot de derivação. Isso não elimina a ressalva de forks. [Processor da ALT](https://github.com/solana-program/address-lookup-table/blob/main/program/src/processor.rs).

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — registrar resolução com snapshot finalizado, ordem dos segmentos e recusas.
- **Diário — 2026-09-23** — distinguir imutabilidade na mesma cadeia de divergência entre forks.
- **Revisões Astra / T4.81** — registrar fontes, layout `Some`/`None` e necessidade do teste com duas tabelas.
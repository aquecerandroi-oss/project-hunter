## RESUMO

**REQUEST_CHANGES pelas validações da entrada.** Não encontrei nova divergência entre stream e batch **dentro do contrato completo**: P1–P3, fonte canônica/completa, carry válido e horizonte permitido. Reproduzi três entradas fora dele que passam silenciosamente e alteram resultados.

Não reabro os achados já tratados em [wallets-1c-bis.md](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-1c-bis.md).

## ARQUIVOS

Revisei os cinco módulos novos, os quatro modificados e os testes indicados. **Nenhum arquivo criado ou modificado; nenhum commit.**

## TESTES

Executado com bytecode, cache do pytest e sincronização do ambiente desabilitados:

```text
uv run pytest packages/indicators/tests/meme -q -p no:cacheprovider
200 passed in 24.16s
```

Sondagens adicionais com `uv run python -`, inteiramente em memória:

```text
original HEAD batch vs current defaults: 3 nights equal
codec exact: >2^53 integers, signed virtual, microseconds, null, flows/links/pending/create: PASS
late entity link and historical per-wallet flows: 3 nights equal
same-slot arrivals across midnight: True
```

Não reexecutei lint, pyright nem a suíte inteira do pacote.

## MUST-FIX

### 1. HIGH — Fill anterior à janela é aceito e corrompe os totais do líder

[_prepared, stream.py:102](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:102) filtra somente `received_at < cut`, sem exigir `received_at >= start`. Depois, [_advance, stream_mint.py:133](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:133) inclui esse evento em `arrived`, e [_flows:123](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:123) soma novamente os átomos.

**Reprodução:** janela de dois dias; A compra e vende 100 tokens no dia zero. Na chamada seguinte, a fonte devolve novamente esses fills, preservando seus timestamps originais. Posteriormente A compra outros 100 tokens. Usei pool com reservas de 100 SOL/1.000 tokens, taxa zero e horizonte suficiente para `leader_sold`, mas insuficiente para `time_cap`.

Resultado observado:

```text
clean C-PnL 0 copies 0 incomplete 1
old arrivals repeated C-PnL -154963 copies 1 incomplete 0
clean equals batch True
```

A contagem duplicada dispara uma saída que não deveria existir. **Correção:** recusar fills anteriores ao início da janela. Isso é uma validação local simples; não exige resolver novamente a deduplicação histórica atribuída ao armazenamento.

### 2. HIGH — Mint repetido na fonte dobra o resultado

Os loops em [stream.py:190](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:190) e [stream.py:272](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:272) não verificam unicidade dos mints. O `dedupe` de `_prepared` atua somente dentro de cada `MintWindow`.

**Reprodução:** construir as janelas da fixture `_two_mint_tx()` e devolver `windows + windows` em cada passada, com `shared_signatures` correto.

```text
mint duplicated: fills 3 6 W 999995000 1999990000
```

Não ocorre exceção. **Correção:** recusar mint repetido em cada passada. Acrescentar teste direto da fonte duplicada.

### 3. MEDIUM — `shared_signatures` incompleto cobra taxa extra silenciosamente

O campo assume conjunto vazio em [stream.py:73](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:73). A seleção em [stream.py:202](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:202) confia integralmente nele; assinatura omitida nunca chega a `_fee_seeds`.

**Reprodução:** `_two_mint_tx()` — A compra X e Y na mesma transação, com ordinal vencedor em Y, e depois vende X. Omitir `shared_signatures`:

```text
shared missing: ref W 999995000 stream W 999990000 correct equal True
```

São **5.000 lamports indevidos**, também capazes de afetar critérios próximos dos limites. **Correção:** tornar explícita e verificável a garantia de completude desse metadado na integração da fonte; o default vazio atualmente confunde “nenhuma assinatura compartilhada” com “não informado”.

**Por que os diferenciais não pegam esses três casos:** o harness já filtra as chegadas em [stream_harness.py:92](C:/dev/project-hunter/packages/indicators/tests/meme/stream_harness.py:92), produz mints únicos em [:98](C:/dev/project-hunter/packages/indicators/tests/meme/stream_harness.py:98) e calcula todas as assinaturas compartilhadas em [:117](C:/dev/project-hunter/packages/indicators/tests/meme/stream_harness.py:117). Ele impede que essas entradas defeituosas cheguem ao motor.

## NICE-TO-HAVE

**Mint omitido também passa silenciosamente:** ao devolver fonte vazia para a fixture acima, obtive zero linhas contra uma no batch. A interface em [StreamInputs, stream.py:67](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:67) não fornece um inventário esperado para detectar a omissão. Recomendo manifesto de completude e consistência entre as três passadas na integração com armazenamento.

**Duplicata entre noites:** continua sendo responsabilidade explícita do armazenamento, conforme [carry.py:25](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:25). Não a reapresento como achado novo. A promessa de `ContractViolation` deve distinguir condições verificadas localmente das garantias externas.

## O QUE EU FARIA DIFERENTE

Acrescentaria testes negativos que chamem `StreamInputs` diretamente, sem a normalização do harness: chegada anterior à janela, mint duplicado, assinatura compartilhada omitida e fonte incompleta. Manteria os diferenciais existentes para provar equivalência das entradas válidas.

## CONCORDO COM

Respondendo às cinco perguntas:

1. **Hooks preservam os defaults.** `charged=()` mantém o conjunto inicial vazio em [lots.py:115](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/lots.py:115) e [episodes.py:233](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:233). `leader_prior=(0,0)` e `leader_since=None` mantêm a leitura integral em [policy.py:109](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:109). A extração de [assemble_snapshot, ranking.py:224](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:224) preserva o fechamento do ranking. A comparação com os módulos originais do `HEAD` confirmou três noites iguais.

2. **Nenhuma divergência nova encontrada dentro do contrato completo.** A separação das sementes por entidade/carteira está em [stream.py:264](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:264); o cap seleciona os primeiros candidatos em [stream.py:227](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:227). As sondagens de fusão tardia e fronteira compartilhada entre noites passaram. Isso sustenta a equivalência; não constitui prova universal.

3. **Há aceitações silenciosas fora do contrato**, detalhadas acima.

4. **Codec: round-trip exato no domínio tipado testado.** Inteiros grandes, reserva virtual negativa, microssegundos, `None`, flows, links, pending e create sobreviveram inclusive à reserialização idêntica. Referências: [carry_codec.py:35](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry_codec.py:35) e [:106](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry_codec.py:106).

5. **Look-ahead: não encontrei vazamento com carry válido.** Fills novos são cortados em [stream.py:102](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:102); creates novos em [stream_mint.py:95](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:95). A ressalva é que o carry é confiado: sua frontier entra diretamente na fita em [:158](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:158), e `Carry.check` verifica somente início e tamanho da janela em [carry.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:145). Portanto, essa conclusão não cobre carry adulterado ou restaurado incorretamente.

## OBSIDIAN

- **wallets-1c-bis** — acrescentar os três casos reproduzidos e separar equivalência de entradas válidas de validação da fonte.
- **wallet-tape-storage** — registrar as garantias de completude dos mints, assinaturas compartilhadas e consistência entre passadas exigidas do armazenamento.
- **wallets-engine** — registrar a comparação dos defaults com o `HEAD` e a dependência da validade temporal do carry.
## RESUMO

**O MUST-FIX MEDIUM da rodada 1 está fechado.** Não encontrei bloqueio restante, nesta re-revisão, para a prova de uma conta. A segunda listagem em base64 não é necessária para resolver o cenário demonstrado.

## ARQUIVOS

Nenhum arquivo criado ou modificado.

## TESTES

Executei com sincronização, cache e bytecode desabilitados:

```text
uv run pytest infra/scripts/tests/test_meme_close_atas.py infra/scripts/tests/test_meme_close_atas_plan.py infra/scripts/tests/test_meme_close_atas_send.py infra/scripts/tests/test_meme_close_atas_verify.py infra/scripts/tests/test_meme_close_atas_token_2022.py -q

131 passed in 1.44s
```

Nenhuma transação real executada.

## MUST-FIX

**Nenhum restante com cenário concreto identificado.**

## NICE-TO-HAVE

Nenhum achado adicional.

## O QUE EU FARIA DIFERENTE

Ajustaria apenas a precisão do racional: **170 bytes não provam, sozinhos, `ImmutableOwner`**. A prova resulta da combinação entre tipo de conta, extensões declaradas, lista permitida e tamanho exato.

Também qualificaria “enumeração parcial não existe”: erros descartam toda a enumeração, mas `Uninitialized` encerra a leitura com sucesso. O tamanho exato continua protegendo contra bytes restantes. [Implementação TLV oficial](https://github.com/solana-program/token-2022/blob/main/interface/src/extension/mod.rs#L194).

## CONCORDO COM

**1. O invariante fecha o cenário? Sim.**

Em [meme_close_atas_plan.py:211](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:211), a lista vazia exige **165 bytes**, conforme [expected_space:234](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:234). Uma extensão desconhecida que faça a enumeração falhar produz lista vazia, mas mantém o tamanho maior: será recusada. O Agave calcula `space` diretamente de `account.data().len()` e usa `unwrap_or_default()` na enumeração. [Tamanho no Agave](https://github.com/anza-xyz/agave/blob/master/account-decoder/src/lib.rs#L49), [enumeração no Agave](https://github.com/anza-xyz/agave/blob/master/account-decoder/src/parse_token.rs#L32).

**Há outros conteúdos possíveis em 170 bytes:** por exemplo, uma conta com somente `PausableAccount`, cujo payload também tem tamanho zero, ou espaço TLV ainda não inicializado. [Definição oficial de PausableAccount](https://github.com/solana-program/token-2022/blob/main/interface/src/extension/pausable/mod.rs#L27).

Isso **não contorna a seleção**: extensão reconhecida fora da lista permitida é recusada em [plan.py:208](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:208); extensão desconhecida ou região não inicializada resulta em lista vazia e incompatibilidade de tamanho. Com `immutableOwner` declarado e exatamente 170 bytes, os quatro bytes disponíveis comportam apenas seu cabeçalho TLV com comprimento zero.

**2. Padding legítimo ser pulado é aceitável? Sim.**

Em [plan.py:211](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:211), `ImmutableOwner` com bytes extras será `skipped:space_mismatch:<bytes>`. É um falso negativo conservador: deixa rent recuperável parado, sem autorizar uma conta indevida. Aceitável para este escopo.

**3. Há bloqueio antes da prova? Não identifiquei.**

O plano mantém o limite de **no máximo uma Token-2022**, adiando as clássicas, em [plan.py:259](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:259). Meu parecer é favorável à prova de uma conta; a confirmação no runtime continua sendo evidência a obter.

## OBSIDIAN

- **Revisoes-Astra — T4.77b** — registrar o MEDIUM fechado pelo conjunto extensões permitidas + tamanho exato e os 131 testes.
- **KB-0146 — Trailing apertado e rent de ATA** — registrar que padding pode excluir contas legítimas conservadoramente.
- **Diário — 2026-09-19** — registrar parecer favorável à prova de uma conta, ainda não executada nesta sessão.
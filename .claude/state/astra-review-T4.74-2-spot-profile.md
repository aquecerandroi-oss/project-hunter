**RESUMO**

A ordem e a decomposição estão coerentes com o desenho. Concordo com WARNING recusando meia ficha e com a recusa de **0,65 R > 0,5 R**. Antes de aprovar o núcleo, corrigiria duas bordas: sinal futuro e impacto negativo. Há também uma lacuna herdada na validação de marcas.

Parecer como `risk-engine-guardian`, por leitura estática; os cenários abaixo não foram executados.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei pytest para preservar estritamente o modo sem escrita, inclusive caches. Examinei a suíte existente; “todas as recusas enumeradas cobertas” não garante cobertura das entradas inválidas — a própria lista de recusas define a comparação em `packages/risk-core/tests/test_spot_profile.py:248`.

**MUST-FIX**

- `packages/risk-core/hunter_risk_meme/spot_profile.py:192` — **ALTA** — `signal_stale` aceita qualquer idade negativa — mantendo a fixture saudável e colocando `emitted_at = AS_OF + 1 hora`, o check passa porque `−3600 ≤ 180`; a expiração também pode passar. Isso permite aprovar informação futura. Exigir idade não negativa, ou tolerância explícita e limitada, e coerência entre emissão e expiração. O teste temporal atual cobre atraso e relógio sem timezone, não futuro (`packages/risk-core/tests/test_spot_profile.py:323`).

- `packages/risk-core/hunter_risk_meme/spot_profile.py:219` — **ALTA** — impacto negativo passa pelo teto e reduz artificialmente `cost_r` — o campo não tem limite inferior (`:122`). Com impacto `−0,01`, prioridade `0,0002`, ficha `0,05` e stop `2%`, a fórmula de `:236` produz **−0,45 R**, permitindo aprovação. Definir a semântica do impacto recebido: magnitude adversa não negativa; dado inválido deve recusar, nunca virar desconto de custo. A tabela testa impacto excessivo e ausente, mas não negativo (`packages/risk-core/tests/test_spot_profile.py:223`).

- `packages/risk-core/hunter_risk_meme/spot_profile.py:156` — **MÉDIA** — completude das marcas depende exclusivamente de um booleano que pode contradizer as posições — `marks_complete` nasce `True`, enquanto `mark_sol` pode ser `None` e vira zero na equity (`packages/risk-core/hunter_risk_meme/inputs.py:157`, `:192`). Cenário: fixture de carteira com saldo/âncora `1 SOL`, posição de outro mint com gasto `0,05` e marca ausente; mantendo o booleano padrão, carteira e orçamento podem passar. Validar também a presença das marcas ou rejeitar a inconsistência na construção. O teste atual só fornece explicitamente `marks_complete=False` (`packages/risk-core/tests/test_spot_profile.py:201`). É uma fragilidade compartilhada, não criada pela pista spot.

**NICE-TO-HAVE**

- `packages/risk-core/hunter_risk_meme/spot_profile.py:236` — **MÉDIA, NO DESENHO** — `cost_r` omite a taxa de rede, embora `available` a reserve em `:257` — com prioridade `0,000125`, impacto `0,001`, ficha `0,05` e stop `2%`, o cálculo admite exatamente **0,50 R**; incluindo `0,000005 SOL` de rede por perna, seriam **0,51 R**. A implementação segue literalmente `docs/design/spot1-lab-solana.md:78`; recomendo corrigir a fórmula normativa junto com o código, mantendo o teto.
- `packages/risk-core/tests/test_spot_profile.py:283` — **BAIXA** — falta demonstrar numericamente reservas pendentes e pista launch no orçamento — o teste atual demonstra posições meme + spot. Acrescentaria casos com launch, reserva, `rent_reserved_sol` e igualdade exata no caixa; eles detectariam omissões na futura montagem do estado.

**O QUE EU FARIA DIFERENTE**

**(1) Ordem:** manteria os 15 checks. A avaliação registra todos e aprova pela conjunção em `packages/risk-core/hunter_risk_meme/spot_profile.py:318` e `:337`; portanto, a ordem determina sobretudo a primeira recusa. Não há redundância indevida:

- vagas globais e vagas spot têm escopos diferentes (`:161`, `:323`);
- idade e expiração impõem prazos diferentes (`:192`);
- teto absoluto/relativo de prioridade e custo em R protegem dimensões diferentes (`:222`, `:229`);
- `wallet_cap` verifica a carteira atual; o teto homônimo do sizing calcula espaço para a compra (`packages/risk-core/hunter_risk_meme/checks_wallet.py:49`; `spot_profile.py:262`).

Acrescentaria as validações apontadas acima. Elegibilidade da estratégia, mapa habilitado, candles finais/recentes, refutação e autorização de envio pertencem ao executor conforme `docs/design/spot1-lab-solana.md:35`, `:60`, `:139` e `:192`; sua ausência aqui não é, por si, check esquecido.

**(3) Custos:** o agregado correto é **todas as posições abertas**, incluindo posições de dias anteriores, mais reservas; não todas as operações históricas do dia (`spot_profile.py:258`). O `available` inclui rent e duas pernas de prioridade/rede. Isso cobre o modelo declarado, mas não comprova cobertura de tentativas adicionais nem de necessidades temporárias de caixa da transação. Essas condições precisam ser verificadas no envio/simulação; não acrescentaria uma taxa fictícia ao núcleo.

**(6) Dinheiro sem aprovação:** este módulo apenas devolve uma decisão (`spot_profile.py:336`). Não identifiquei nele caminho de envio. Entretanto, uma recusa pode carregar `sizing.sol_final > 0`, comportamento explicitamente testado em `test_spot_profile.py:255`. O teste obrigatório da integração é: **decisão recusada com sizing presente ⇒ zero chamadas ao signer/send**. Verificar apenas a existência de sizing seria um bypass.

**CONCORDO COM**

**(2)** WARNING deve recusar `below_ticket:kill_switch_multiplier`: `0,05 × 0,5 = 0,025`, abaixo da ficha efetiva (`spot_profile.py:265`, `:299`). O clamp inicial pelo teto por operação é autorizado pelo desenho e ocorre antes dessa comparação (`:316`; `docs/design/spot1-lab-solana.md:67`).

**(4)** **0,65 R deve recusar.** “0,3–0,7 R” descreve uma faixa de custos; não cria exceção ao teto. Com esses parâmetros, a prioridade máxima compatível com a fórmula atual é `0,000125 SOL/perna`; incluindo a rede exemplificada, `0,000120`. Não elevaria o teto para fabricar admissões.

**(5)** Manteria `"spot"` em `MemeDecision.profile` (`packages/risk-core/hunter_risk_meme/decision.py:181`). Não há alternativa limpa mantendo o mesmo contrato validado e o discriminador correto. Usar `"full"` falsearia a auditoria; contornar validação ou criar outro tipo só para evitar essa linha pioraria a solução.

**(6)** Não encontrei uso de `float` na aritmética do módulo. Há proteção na construção e teste correspondente (`packages/risk-core/hunter_risk_meme/base.py:25`; `test_spot_profile.py:332`). `None` de paridade/impacto recusa corretamente (`spot_profile.py:207`, `:217`); a ressalva concreta é a marca ausente descrita acima.

**OBSIDIAN**

- **Risk Engine** — registrar o perfil spot, WARNING sem ficha parcial e as bordas pendentes de validação.
- **Diario/2026-09-19** — registrar este parecer da T4.74-2 e a distinção entre conformidade da fórmula e custo total.
- **Revisoes-Astra/2026-09-19-T4.74-2** — criar posteriormente a revisão com os cenários e os testes de regressão exigidos.
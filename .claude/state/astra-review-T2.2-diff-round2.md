## RESUMO

**DONE_WITH_CONCERNS.** Os itens **1, 2, 4 e 5 fecham os cenários anteriores** por inspeção. O **item 3 ficou parcial**: impede zero sem cobertura, mas ainda aceita uma janela incompleta quando há algum trade observado.

Revisão no papel de `quant-engineer`, limitada a `packages/indicators/**` e à documentação de contexto.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei comandos de teste, lint ou typecheck nesta rodada. `190 passed` e ruff/pyright limpos são resultados informados por você.

Li as regressões. A nova `TestCoverageProof` exercita somente janelas vazias, com e sem prova; falta o caso de reconexão com trade dentro da janela. [test_windows.py:145](C:/dev/project-hunter/packages/indicators/tests/unit/test_windows.py:145).

## MUST-FIX

### 1. P1 — Item 3: um trade novo ainda permite publicar uma janela incompleta como `ok`

A condição `if not window and ...` exige `covered_until` somente quando a seleção está vazia. Com um trade dentro dela, retorna disponível independentemente da cobertura. [windows.py:177](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:177).

**Cenário:** corte às 12:01; tape contém um trade às 11:50 e outro BUY às 12:00:55, recebido após reconexão. Durante a interrupção, entre 12:00 e 12:00:50, aconteceram trades que não foram recuperados. O loader mantém `covers_from=11:50`, sem comprovar continuidade. [hotstate.py:211](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:211).

Nesse caminho:

- `trade_velocity_1m` publica **1/60**, embora a contagem do minuto seja desconhecida. [micro.py:189](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:189).
- As pressões de cinco minutos podem publicar **buy=1 e sell=0**, embora os trades perdidos possam incluir vendas. [micro.py:150](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:150).
- A proveniência do tape disponível continua `ok`; portanto a herança não corrige esses resultados. [quality.py:176](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:176).

**O que falta:** exigir prova de cobertura para **qualquer janela**, vazia ou não. A prova precisa representar um intervalo contínuo sem perdas pendentes; apenas “estava conectado novamente no fim” não basta. Acrescentar regressões com janela não vazia e `covered_until` ausente/anterior ao fim, incluindo a qualidade final no engine.

### 2. P2 — Extra numérico: descartar nível inválido pode produzir um book aparentemente válido

`_decimal` agora rejeita não finitos, mas `decode_book` simplesmente remove o nível inválido e devolve o restante como disponível. [hotstate.py:171](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:171).

**Cenário:** bids `[("100", "NaN"), ("99", "1")]`, asks `[("101", "1")]`, timestamp fresco. O nível de preço 100 desaparece; `SpreadPct` passa a usar 99 como melhor bid e publica spread `0.02`, embora o melhor preço recebido fosse 100. A qualidade permanece `ok`. [micro.py:68](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:68), [quality.py:274](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:274).

**O que falta:** invalidar o snapshot afetado, em vez de transformar corrupção em outro book. O teste novo cobre ambos os lados totalmente inválidos, sem verificar esse caso misto. [test_hotstate.py:246](C:/dev/project-hunter/packages/indicators/tests/unit/test_hotstate.py:246).

## NICE-TO-HAVE

- Fortalecer a regressão do checkpoint futuro: comparar o vetor com uma reconstrução limpa e testar contexto sem barras suficientes, garantindo que o estado futuro não reapareça. Hoje o teste verifica estado reconstruído e `origin_reason`. [test_no_lookahead.py:150](C:/dev/project-hunter/packages/indicators/tests/unit/test_no_lookahead.py:150).
- Persistir a prova de cobertura na proveniência: `InputProvenance` ainda não contém `covered_until`. [vector.py:127](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/vector.py:127).

## O QUE EU FARIA DIFERENTE

**(b)** Aceito indisponibilidade até T2.5 fornecer cobertura; prefiro isso a publicar zero sem evidência. Entretanto, a consequência correta deve alcançar **também valores positivos e pressões**, quando a janela completa não está comprovada.

Manteria os dois limites temporais, com contrato explícito de **intervalo continuamente coberto**. Reconexão sem recuperação reinicia o início desse intervalo; descarte ou perda impede avançar a cobertura através do buraco. Não substituiria isso pelo timestamp do último trade.

## CONCORDO COM

| Item | Veredito e evidência |
|---|---|
| **1 — Checkpoint futuro** | **Fechado.** Descarta pelo fechamento posterior ao corte; sem barras, devolve checkpoint ausente. O engine usa diretamente esse resultado. [atr.py:272](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:272), [engine.py:92](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:92). |
| **2 — Dependência do estado** | **Fechado.** A qualidade compartilhada preserva o motivo do avanço e chega às quatro features pela herança. [quality.py:227](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:227), [engine.py:70](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:70), [test_engine.py:175](C:/dev/project-hunter/packages/indicators/tests/unit/test_engine.py:175). |
| **3 — Cobertura** | **Parcial**, conforme cenário acima. |
| **4 — Parcial sem timestamp** | **Fechado.** Construtor rejeita; builder descarta. [context.py:170](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:170), [context.py:264](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:264). |
| **5 — Decimal ambiente** | **Fechado.** Ambas as somas agora usam o contexto fixo. [micro.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:108), [micro.py:160](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:160). |

Concordo também com distinguir overrides na identidade da política. [quality.py:75](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:75).

**(c)** Não identifiquei outro vazamento de futuro nos caminhos das correções examinadas. Ainda existem os dois caminhos acima de publicar números sem suporte suficiente nos dados; portanto não daria um aceite geral de “nenhum número fabricado”.

## OBSIDIAN

- **Features (Feature Engine)** — Registrar quatro correções fechadas, cobertura ainda parcial e tratamento necessário de book corrompido.
- **Market Collector** — Especificar para T2.5 a prova contínua de cobertura, incluindo reconexões, perdas e recuperação.
- **Revisões Astra — T2.2, rodada 2** — Registrar os cenários pendentes e distinguir revisão estática dos resultados de testes informados.
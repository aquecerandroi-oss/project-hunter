# Decisões delegadas pelo Everton à Sexta-feira — M3 (2026-09-06)

Everton, 2026-09-06: "deixo na sua mão sextafeira" — sobre os três conflitos abertos da análise em `directive-risk-engine-2026-09-06.md` (itens 1, 3 e 5). Decididas pela Sexta-feira (Claude como orquestrador, Astra ouvida no diálogo do M3) **em nome do Everton**; reversíveis por ele a qualquer momento; nada aqui altera um limite que ele escreveu.

## D1 — SPOT vs perpétuos: spot para executar, perpétuo para decidir
- A carteira virtual executa **no spot da Binance**, long-only, sem alavancagem, como a diretiva manda. O preço de execução simulada vem de uma stream spot por par negociável (`bookTicker` + `aggTrade` do spot; ~50 pares pelo piso de 50 M), coletada pelo market-worker como uma fonte nova e rotulada (`venue=spot`).
- Sinais, features, Radar, regime e o Lab **continuam no perpétuo** (é onde há funding, OI, liquidações, e 45 h de baseline). O sinal do perpétuo é mapeado para o par spot de mesmo `base/quote`; se o par spot não existir ou estiver abaixo do piso no spot, o ativo fica só em shadow.
- Basis spot–perp registrado por fill (`meta.basis_bps`) para a diferença ser visível, nunca escondida.
- Enquanto a stream spot não estiver na árvore, **a carteira não roda em produção**; o simulador aceita uma fonte de preço abstrata, e o modo "proxy pelo perpétuo" existe só em testes, rotulado. Motivo: misturar preços de venues distintos nos primeiros resultados tornaria o paper trading impossível de auditar.

## D2 — Participação: 1 % do minuto, como escrito, medido no venue de execução
- Fica a regra do Everton: notional novo ≤ 1 % × min(volume de cotação do último minuto completo, mediana dos 30 últimos minutos completos), **no spot** (venue de execução), agregando todos os agentes no mesmo mercado.
- Consequência aceita: em mercados finos a posição sai menor que 0,25 % de risco (teto, não meta) e abaixo do `min_notional` da exchange é recusada com motivo. Nos pares acima de ~260 M/24 h a posição inteira cabe.
- O Risk Engine publica o limitante vencedor em toda decisão (R-PROV-1). **Revisão marcada**: após 14 dias de paper, a Sexta-feira apresenta ao Everton a distribuição do limitante vencedor e quantas entradas foram reduzidas/recusadas só por participação; só ele muda o número.

## D3 — Escolha entre sinais elegíveis quando há vaga
- Ordem de prioridade, determinística e registrada na decisão: (1) score de oportunidade do Radar no fechamento da barra fonte, maior primeiro (sinais sem score entram **depois** dos com score, não são recusados — o classificador está em warm-up por dias); (2) custo estimado de entrada em R menor primeiro (spread + slippage do book no instante, da KB-0058); (3) chegada mais antiga.
- Uma vaga por ciclo de decisão; entradas pendentes reservam risco e vaga (diretiva §4); sinais não escolhidos continuam no shadow e podem ser escolhidos no próximo ciclo enquanto válidos (janela de entrada de 120 s do Lab).
- Nunca duas posições na mesma moeda (diretiva §4, 10 % por moeda também impede na prática).

## Registro
- ADR e nota de decisão no Obsidian: a cargo da Sexta-feira no plano do M3 (`docs/plans/M3.md`, seção "Decisões delegadas").
- Everton pode reverter qualquer uma respondendo em uma linha; até lá, valem.

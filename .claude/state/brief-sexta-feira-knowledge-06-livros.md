# Brief — Sexta-feira: rodada 6 de conhecimento — livros de estratégia de trading que fazem diferença

**Pedido do Everton (2026-09-06):** "quero que procure livros de estratégia de trading, quero que estude livros que fazem a diferença na estratégia; quero que ache e iremos usar as estratégias no virtual; assim que tiver pronto sairemos validando tudo". Ou seja: a saída desta rodada não é resenha, é **candidatas no backlog** que o Lab consiga testar em sombra.

**Regra operacional:** nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min. Método das rodadas 1–5 (`obsidian/11-KNOWLEDGE/`, KB-0001 em diante; leia o `Index.md`, o `Strategy Backlog.md` e o `Registro de Tentativas.md` antes). Escreva só em `obsidian/11-KNOWLEDGE/**`; commit e push só desses arquivos (`docs(knowledge): ...`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`), a cada 3 notas.

## Copyright, sem exceção
Livros são obra protegida. A nota é **síntese própria** do que o livro ensina e do que é testável: nenhuma transcrição, no máximo uma citação curta (< 15 palavras) com atribuição por nota; nunca baixar cópia pirata; use resenhas, resumos públicos, entrevistas e artigos dos próprios autores (acesso aberto), páginas de editora, e o que a Astra e você já sabem do conteúdo. Se uma afirmação sobre o livro não puder ser sustentada por fonte aberta, marque como "de memória, a confirmar".

## Lista de partida (uma nota por livro ou por ideia central; escolha 8–12, priorizando o que é testável no nosso dado: perpétuos da Binance, velas de 1 min, book top-20, trades, funding/OI)
- Jack Schwager, *Market Wizards* e *Unknown Market Wizards* — não o livro, mas **o que cada entrevistado faz de operacional** (Kovner, Seykota, Dennis/Turtles, Marcus, Jones); a regra dos Turtles (Donchian 20/55, ATR sizing, piramidação) é a mais testável.
- Van Tharp, *Trade Your Way to Financial Freedom* — expectancy, R-multiples, position sizing; o Lab já fala em R.
- Perry Kaufman, *Trading Systems and Methods* — catálogo de sistemas testáveis (breakout, momentum, mean reversion, filtros de volatilidade).
- Ernest Chan, *Quantitative Trading* e *Algorithmic Trading* — mean reversion vs momentum, testes de estacionariedade, o que é backtest honesto.
- Robert Pardo, *The Evaluation and Optimization of Trading Strategies* — walk-forward, overfitting (conversa com KB-0010).
- David Aronson, *Evidence-Based Technical Analysis* — o que da análise técnica sobrevive a teste (conversa com KB-0003).
- Robert Carver, *Systematic Trading* — regras de negociação, forecast scaling, sizing por volatilidade (conversa com KB-0035).
- Marcos López de Prado, *Advances in Financial Machine Learning* — barras alternativas (volume/dollar bars), triple-barrier labeling (é literalmente o nosso alvo/stop/tempo), meta-labeling, CPCV.
- Stan Weinstein (*Secrets for Profiting in Bull and Bear Markets*, estágios), Mark Minervini (VCP, SEPA), William O'Neil (CANSLIM) — o que se transfere para cripto intradiário e o que não.
- Mark Douglas, *Trading in the Zone* — não é testável; uma nota curta dizendo isso e o que dele vira regra de processo (ex.: aceitar a distribuição de R), sem hipótese.
- Adam Grimes, *The Art and Science of Technical Analysis* — padrões com estatística.
- Andreas Clenow, *Following the Trend* / *Trading Evolved* — trend following sistemático com números.

## Para cada nota
Template `_TEMPLATE-NOTE.md`: o que o livro afirma (nas suas palavras), onde foi mostrado (mercado/timeframe/época — e a ressalva de que quase tudo é ações/futuros diários, não cripto de 1 min), como mediríamos aqui (features do M2, velas, custos assumidos do Lab), **hipótese testável** como candidato de `Strategy` com `default_parameters`, por que pode falhar, "Segunda opinião (Astra)" (`bash infra/scripts/astra.sh ask KB-<slug> "..."`, uma por nota), relacionados. Linha no `Index.md` (novo tema "Livros de estratégia") e, quando houver hipótese, linha no `Strategy Backlog.md` com dado necessário e ordem sugerida. `Registro de Tentativas.md` só se propuser tentativa.

## Prioridade de saída
Ao final, uma seção nova no `Strategy Backlog.md`: **"Fila para a sombra — livros"**, com as 3 a 5 candidatas mais testáveis primeiro (o Everton quer sair validando no virtual assim que estiver pronto), cada uma com: regra em uma frase, parâmetros, dado (temos?), esforço, e o que a refutaria. Nada é ativado por você.

Relatório final em português: notas, fila para a sombra, discordâncias da Astra, fontes que não abriram, próximo tema (a rodada 7 é meme coins — brief próprio).

# Brief — Sexta-feira: primeira rodada de aquisição de conhecimento (tema: momentum, rompimentos e invalidação)

**Regra operacional: nunca use Bash em background; comandos em primeiro plano com timeout ≤ 5 min.** Leia `.claude/agents/sexta-feira.md` (seção nova "Knowledge acquisition"), `obsidian/11-KNOWLEDGE/{Index,_TEMPLATE-NOTE,Strategy Backlog}.md`, `obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md`, `.claude/state/notes-S1.md` (§6 invalidação, §3 ATR) e `docs/plans/SHADOW-LAB.md` (Decisão conjunta itens 3 e 7).

Outra instância sua está no plantão agora e escreve em `08-CHANGELOG`, `07-BUGS`, `09-OPERATIONS`, `05-EXPERIMENTS`, `plantao.md`. **Você escreve só em `obsidian/11-KNOWLEDGE/**`** (notas novas, `Index.md`, `Strategy Backlog.md`). Se um commit falhar por `index.lock`, espere alguns segundos e tente de novo; nunca force.

## Objetivo desta rodada
Entre 6 e 10 notas sobre **momentum de curto prazo, rompimentos (breakouts) e regras de invalidação/saída** — o tema que o Lab já está testando e onde a `momentum_v1` mostrou 69 invalidações em 199 encerrados e expectancy negativa. Cada nota no template, em português, síntese própria (nunca cópia; no máximo uma citação curta com atribuição), com fonte e URL, qualidade da evidência e **hipótese testável no Lab** com parâmetros explícitos.

Fontes sugeridas (use `WebSearch`/`WebFetch`; prefira acesso aberto): Jegadeesh & Titman (momentum, 1993) e a literatura de time-series momentum (Moskowitz, Ooi & Pedersen 2012) — o que se transfere para cripto intradiário e o que não; estudos abertos sobre momentum em cripto (SSRN/arXiv q-fin, ex.: "cryptocurrency momentum" 2018–2025); breakouts de faixa/Donchian e a evidência sobre falsos rompimentos; ATR como stop e sizing (Wilder, 1978 — conceito, não cópia); regras de saída por tempo vs por invalidação (literatura de "time stops"); custos e slippage em perpétuos (documentação da Binance sobre funding e taxas); trabalhos sobre look-ahead e overfitting em backtests (Bailey, Borwein, López de Prado — "probability of backtest overfitting"). Se uma fonte não abrir, registre e siga.

## Para cada nota
Além do template: uma linha no `Index.md` (tema, fonte curta, qualidade da evidência, hipótese sim/não) e, se houver hipótese, uma linha no `Strategy Backlog.md` com o dado necessário e se já temos (features do M2: `atr_14_pct`, `return_*`, `relative_volume_*`, `breakout_strength_20`, `distance_from_24h_high/low`, `funding_rate`, `open_interest_change_*`; velas 1m/5m/15m do M1). Especial atenção à **candidata #1 do backlog** (momentum v2 com invalidação menos agressiva): o que a literatura diz sobre invalidar no fechamento abaixo do nível de rompimento vs stop por ATR vs saída por tempo, e que variante testar primeiro.

## Astra
Antes de fechar cada nota com hipótese, `bash infra/scripts/astra.sh ask KB-<slug> "<resumo da hipótese + fonte + o que você propõe testar>"` e registre o parecer na seção "Segunda opinião (Astra)". Uma chamada por nota; se a Astra falhar, registre "Astra indisponível" e siga.

## Regras
Sem serviços pagos, sem paywall, sem cópia literal, sem inventar números; nada é ativado; parâmetros são propostas para o backlog. Commit e push só de `obsidian/11-KNOWLEDGE/**` (mensagem `docs(knowledge): ...`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`), ao final da rodada ou a cada 3 notas.

## Relatório final (em português)
Lista das notas (título, fonte, evidência, hipótese sim/não), o que entrou no backlog e em que ordem você testaria, o que a Astra discordou, fontes que não abriram, e a sugestão do próximo tema.

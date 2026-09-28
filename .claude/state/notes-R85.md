# R85 — H-025 (retração de Fibonacci 50–61,8 %) e H-026 (LTA diária, braços A e B) em cripto grande à vista

Início: 2026-09-28 ~12:50Z. Pesquisa só: nenhuma estratégia ativada, nenhum rule set mudado, nenhum dinheiro, nenhum
commit. Dado = o artefato do R84 (`.claude/state/r84/cache/candles_1d.csv`), sem VPS, sem base, sem rede no estudo
(a rede só foi usada para ler literatura). Código e saídas em `.claude/state/r85/`.

## 0. Lido antes (regra Obsidian primeiro) e o que cada nota mudou no plano

- `obsidian/00-HOME.md` — o Obsidian é o núcleo; nada de estratégia muda sem nota. → estudo só de pesquisa, com
  escrita de volta no mesmo pacote.
- **KB-0167** (análise gráfica depois do custo): a melhor evidência é de tendência **diária**; data snooping (a regra
  famosa é sobrevivente); custo de equilíbrio antes de significância; um dia de atraso derruba Sharpe. → horizonte
  diário, execução na abertura seguinte ao sinal, MRE declarado antes, patamar obrigatório.
- **KB-0077** (linhas de tendência): pivô só conhecido k barras depois (`confirmed_at = index + k`); "dois pontos
  traçam, o terceiro confirma"; `valid_from` = a mais tardia das confirmações; seis diferenças para o traço humano.
  → k = 5 no diário, linha nasce em b + 5, controle de antecipação por prefixo.
- **KB-0003** (rompimento de canal e data snooping): família pré-especificada, publicar a família inteira; inconclusão
  ≠ irrelevância. → faixas vizinhas e tolerâncias publicadas todas; errata do R76.
- **EXP-0016** (trendline_breakout v1, 15 min em perps): 89,4 % das decisões foram repique em suporte ascendente
  (bruto +0,10 R, líquido −0,04 R), rompimento 5/5 perdidos, K6 dispara, aposentada (T3.56). → o diário é a parte
  não testada; A e B julgados **separadamente**; regra K6 herdada.
- **KB-0149**: antecipação mente com convicção (24); limiar escolhido olhando o resultado vale zero (25); patamar ×
  pico (26); ligar critério na mesa real não é sombra (28); custo por praça (Jupiter 0,14 % em 0,05 SOL). → nada vai à
  mesa; porta para papel só descrita.
- **Fila de Hipoteses** (H-001…H-024) e **R84/KB-0166**: painel diário de 750 pares com deslistados, sobrevivência
  auditada contra 153 cópias do Wayback; universo ponto-no-tempo; bootstrap de blocos móveis; dp semanal medido de
  6,7 p.p. → reuso integral do painel e do universo.
- **Proximas Hipoteses** (C1 tendência de 20 d; C2 fundos mais altos sem rompimento): nenhuma colide com H-025/H-026
  (C1 é estado dos sinais do Lab; C2 é meme); "canal diário como estratégia própria na spot/1" estava em "não
  recomendados" por ser o mesmo objeto da H-024 — a LTA diária **não** é rompimento de canal de N dias (é linha por
  pivôs), mas a leitura tem de dizer isso.
- **Mapa de Estrategias**: `trendline_breakout v1` no cemitério. **docs/RESEARCH.md**: três rótulos; errata do R76.

## 1. Pré-registro

Blocos H-025 e H-026 no fim de `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md`, anexados às **13:06Z** (texto datado
13:05Z), cópia congelada `r85/prereg_frozen.md` (sha256 `398b63be…c732b`). Nenhum pivô, evento, contagem ou retorno do
painel real tinha sido calculado. O painel já existia (R84 olhou só retornos semanais de carteira do mesmo top-20).

## 2. Revisão da Astra do desenho e emenda (13:12Z, antes de qualquer evento real)

`.claude/state/astra-review-H-025-prereg.md`. Sem antecipação inevitável; seis must-fix, todos aceitos numa emenda
datada na própria Fila (o texto congelado ficou intacto; `r85/prereg_with_amendment.md`, sha256 `ad6a7170…9445`):
(1) a busca da primeira retração começa em h, inclusive, e só emite depois da confirmação (travessia antes consome a
faixa); (2) toques distintos com índice s estritamente entre os toques e P congelado no fechamento do toque;
(3) controles: CONFIRMA = "esta regra supera este controle", não mecanismo nem especificidade; (4) inferência com
calendário completo, D* = ΣS*/ΣN*, mesmos índices para todos os braços, cobertura em intervalos NÃO sobrepostos;
(5) venda na primeira abertura real (nunca no fecho carregado); (6) estrutural: MRE por operação estrutural, bloco
de 120 d, controle com parada determinada pelo evento. **Parcialmente aceito:** o contraste incremental (placebos,
pareamento por retorno prévio/ATR%) **não** foi congelado — a leitura foi restringida, e isso fica como limite.

## 3. Instrumento e testes (antes do dado real)

- `geom85.py` (ATR de Wilder, pivôs, perna de Fibonacci, LTA), `data85.py` (painel do R84 + máxima/mínima, com as 5
  continuidades levando OHLC inteiro), `study85.py` (saídas, contraste), `collect85.py` (varredura e antecipação no
  dado real), `stats85.py` (inferência, veredito), `analyze85.py` (relatório), `run_real.py`, `smoke85.py`.
- `uv run pytest -q .claude/state/r85/` → **22 testes** (valores conhecidos em série sintética; a vela seguinte em
  formação não muda nada; prefixo = série inteira em 3 sementes × Fibonacci e 3 tolerâncias; **uma estratégia
  trapaceira — pivô usado na própria barra — é pega pela guarda**).
- Processo, declarado: os 12 primeiros testes de geometria foram escritos antes do módulo mas não os rodei vermelhos
  antes de escrevê-lo; o teste da emenda (1) foi visto falhar pelo motivo certo antes da correção.
- Fumaça sintética (`smoke_synth.txt`, rotulada SINTÉTICA): no nulo nenhum braço confirmou (primária REFUTA o tamanho,
  com D verdadeiro 0); com +3 p.p. somados ao evento, primária, A e B confirmam e a estrutural não (IC largo com
  blocos de 120 d). No nulo da semente 85 o braço A deu +0,87 p.p. (p 0,03, Holm 0,06); seis sementes a mais deram
  −0,55, +0,40, −0,29, −0,19, −0,68, −0,05 → acaso, não viés do encanamento.

## 4. Contagem antes de qualquer retorno (13:21Z, `r85/counts.txt`)

843 542 velas depois das ligações de ticker; 755 séries; 256 varridas (as que estiveram no universo). Eventos brutos no
universo: Fibonacci [0,40] 299 · [0,45] 386 · **[0,50; 0,618] 448** · [0,55] 462 · [0,70] 386; LTA tol 0,25: **A 1 632**,
**B 336** (0,15: 1 326/254; 0,35: 1 919/422); 1 sem abertura real em e. Todos acima do piso de 150; nada foi mudado.

## 5. Resultado

Primeira corrida às ~13:25Z (`r85/h025_h026_v1_antes_da_revisao.txt`); revisão da Astra do resultado e do código
(`.claude/state/astra-review-H-025-result.md`): vereditos corretos pela letra, **4 must-fix de código** — expiração da
LTA em b + 181 (devia ser b + 180), abertura além do alvo perdendo para a mínima da vela, K6 não bloqueando REFUTA,
estrutural dependendo da saída fixa. Cada um ganhou teste que falhou antes (4 failed, 22 passed) e passa depois
(26 passed); corrida final `r85/h025_h026.txt` (sha256 `f04f7bde…5dfb3`). Só a expiração mudou números (H-026), e
exatamente para os valores que a Astra recalculou em memória; nenhum rótulo mudou.

| braço | D por 10 d | IC 95 % | Holm | nível | n / cobertura | veredito |
|---|---|---|---|---|---|---|
| H-025 50–61,8 % | +0,691 p.p. | [−1,429; +2,946] | 0,547 | +2,73 % | 360 / 85 | NÃO CONFIRMA (D < MRE, IC com zero, patamar falha) |
| H-025 estrutural (120 d) | +0,176 | [−3,173; +3,591] | 0,547 | +2,05 % | 355 / 23 | NÃO CONFIRMA |
| H-026 A | −1,085 | [−2,079; −0,021] | 0,983 | −0,51 % | 1 529 / 96 | REFUTA (IC sup < +1,0; inteiro < 0) |
| H-026 B | +1,089 | [−0,755; +2,891] | 0,223 | +4,37 % | 323 / 77 | NÃO CONFIRMA (IC com zero, Holm) |

Faixas H-025: 0,40 +1,063 · 0,45 −0,217 · 0,50 +0,691 · 0,55 −0,675 · 0,70 −2,512; especificidade de Fibonacci
+1,277 [−0,111; +2,634] → não especial; estrutural − fixa nas mesmas 443 entradas +0,009 p.p. Otimista = pessimista
em 3 casas (uma saída por fim de série, LUNA em A). Antecipação no dado real: 25 dias reconstruídos, 0 divergências.
Parte D: nada sobreviveu → nenhum braço de papel. Detalhe e leitura em `obsidian/11-KNOWLEDGE/KB-0169-…`.

## 6. Premissas numéricas (escolhas, não medidas)

k = 5 (pivô), amplitude ≥ 3 ATR14, faixa de controle r < 0,236, tolerância 0,25 ATR (0,15/0,35 no patamar), 1 ATR de
afastamento entre toques, vida da linha 180 velas, janela do B 20 velas, H = 10 d (5/20 sensibilidade), stop estrutural
L − 0,5 ATR, alvo L + 1,618·(H − L), teto 60 d, custo 0,15 %/perna (como R84), MRE +1,0 p.p. por operação (~3× a ida e
volta), blocos 28 d (120 d na estrutural), 10 000 réplicas, semente 20260928, mínimo 150 eventos e 40 intervalos de
28 d (15 de 120 d), dp de x a priori ~11 p.p. (o IC realizado da H-025 implica ~±2,2 p.p. de meio-intervalo).

## 7. Escrita de volta

KB-0168 (leitura), KB-0169 (resultado), Fila (H-025/H-026 com emenda e veredito), Proximas Hipoteses, Mapa de
Estrategias, EXP-0016 (referência cruzada, fora das avaliações), KB-0077 e KB-0167 (links e as duas regras de
traçado), Revisoes-Astra (H-025-H-026-prereg, H-025-H-026-resultado, Index), Diário de 28/09. Lint: base limpa.

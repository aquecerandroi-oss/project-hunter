captura: 3720.0 s de recepção (pedido 3720 s), parada: requested duration; recusas 0; suspensões 0; desconexões pump/amm 0/0, downtime 1/1 s
chaves 10,619; swaps com chave 1,308,464 (352/s); sem chave 0; pool inferida 516,769

## Hora mais cheia de cada chave (janela deslizante exata de 60 min)

| eventos na hora | curva: chaves | curva: eventos | pool: chaves | pool: eventos | tudo: chaves | tudo: eventos |
|---|---|---|---|---|---|---|
| 1–9 | 4,690 | 4.3 % | 3,036 | 0.7 % | 7,726 | 1.4 % |
| 10–99 | 1,303 | 18.2 % | 657 | 1.7 % | 1,960 | 4.9 % |
| 100–999 | 441 | 53.6 % | 257 | 8.3 % | 698 | 17.0 % |
| 1,000–3,999 | 33 | 22.1 % | 144 | 29.2 % | 177 | 27.9 % |
| 4,000–15,999 | 1 | 1.8 % | 52 | 40.5 % | 53 | 33.1 % |
| ≥ 16,000 | 0 | 0.0 % | 5 | 19.5 % | 5 | 15.8 % |

## Resumo por programa

| programa | chaves | Σ hora mais cheia | maior chave | fatia da maior | fatia das 10 maiores | ≥ 1 000/h | ≥ 4 000/h | mediana | Σn²/Σn |
|---|---|---|---|---|---|---|---|---|---|
| curva | 6,468 | 247,154 | 4,512 | 1.8 % | 10.5 % | 34 | 1 | 2 | 738 |
| pool | 4,151 | 1,050,147 | 124,069 | 11.8 % | 26.7 % | 201 | 57 | 2 | 20,904 |
| tudo | 10,619 | 1,297,301 | 124,069 | 9.6 % | 21.6 % | 235 | 58 | 2 | 17,062 |

## As 10 chaves mais cheias

| programa | chave | eventos na hora | fatia | máx. por minuto |
|---|---|---|---|---|
| pool | Bnf84yYNCo… | 124,069 | 9.6 % | 3140 |
| pool | GLL3CzybpS… | 24,956 | 1.9 % | 5976 |
| pool | DWD1tJ6Vtf… | 19,739 | 1.5 % | 2488 |
| pool | Xn7B2AULQb… | 18,670 | 1.4 % | 1580 |
| pool | 7JE9NCdFhA… | 17,849 | 1.4 % | 888 |
| pool | BNG5962Zkb… | 15,814 | 1.2 % | 777 |
| pool | 2ANaMbzJbK… | 15,362 | 1.2 % | 307 |
| pool | 3Q1jeL4FQn… | 14,991 | 1.2 % | 890 |
| pool | GbDPEGUMNJ… | 14,635 | 1.1 % | 1012 |
| pool | EfsTpE9yJp… | 14,141 | 1.1 % | 1629 |

## Multiplicador de custo pela densidade (CENÁRIO, curva sintética do mint quente)

| expoente além de 16 000/h | programa | custo da hora (Σ C(n)) | linear a 1 000/h | M | maior chave sozinha |
|---|---|---|---|---|---|
| 1.51 | curva | 90.8 s | 69.5 s | 1.31× | 4.2 s |
| 1.51 | pool | 1,979.1 s | 295.4 s | 6.70× | 818.9 s |
| 1.51 | tudo | 2,070.0 s | 364.9 s | 5.67× | 818.9 s |
| 1.69 | curva | 90.8 s | 69.5 s | 1.31× | 4.2 s |
| 1.69 | pool | 2,364.6 s | 295.4 s | 8.01× | 1,193.8 s |
| 1.69 | tudo | 2,455.4 s | 364.9 s | 6.73× | 1,193.8 s |

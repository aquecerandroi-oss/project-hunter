# Exportar do MetaTrader 5 (Rico) o histórico de 1 minuto do WIN e do Ibovespa

> Para o Everton. Serve à H-038r e às H-039, H-040 e H-041 (as três estratégias novas do WIN), já
> pré-registradas na `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md` **antes** de existir este arquivo.
> Leva uns 15 minutos. Nada aqui envia ordem nem mexe na conta: é só baixar barras antigas.
> Os nomes dos menus vêm em português com o original em inglês entre parênteses, porque a tradução
> do MT5 varia entre versões.

## O que exportar

| o quê | símbolo no MT5 | tempo gráfico | período |
|---|---|---|---|
| mini-índice, **série contínua sem ajuste** | procure por `WIN` — normalmente `WIN$N` ou `WIN$` | **M1** (1 minuto) | o mais antigo que o servidor der até hoje |
| Ibovespa | procure por `IBOV` | **M1** | o mesmo período |

- **Série sem ajuste.** Se aparecerem várias séries contínuas (por exemplo uma com "ajustada", "D" ou
  "R" no nome ou na descrição), escolha a que **não** é ajustada. O programa recusa uma série cujos
  preços saiam da grade de 5 pontos do WIN (sinal típico de ajuste), mas isso **não prova** que uma
  série dentro da grade não foi ajustada — por isso, na dúvida, exporte as que existirem e diga qual
  é qual.
- **Contratos individuais** (`WINZ24`, `WING25`…) não são necessários. Se aparecerem com histórico
  longo, pode exportar também: servem só para conferir as viradas de contrato.
- Não sabemos quanto histórico de 1 minuto o servidor da Rico guarda. Exporte o que vier: as regras
  pedem **pelo menos 24 meses** no trecho principal (cerca de 2,5 anos no total) para dar resultado;
  com menos, a resposta sai "limite de dado" — o que também é uma resposta.

## Passo a passo (MT5 no computador)

1. Abra o MetaTrader 5 da Rico e faça login como sempre.
2. *(Uma vez só, se a lista de barras vier curta.)* Ferramentas → Opções → aba Gráficos
   (*Tools → Options → Charts*) → "Máx. barras no gráfico" (*Max bars in chart*) → **Ilimitado**
   (*Unlimited*) → OK.
3. Exibir → Símbolos (*View → Symbols*), ou **Ctrl+U**.
4. Clique na aba **Barras** (*Bars*).
5. No campo de busca do símbolo, digite `WIN` e escolha a série contínua sem ajuste (ex.: `WIN$N`).
6. Em tempo gráfico escolha **M1**.
7. Nas datas, coloque o início bem antigo (por exemplo **01/01/2021**) e o fim **hoje**.
8. Clique em **Solicitar** (*Request*) e espere a tabela encher. Se o servidor tiver menos
   histórico, ela começa mais tarde — tudo bem.
9. Clique em **Exportar barras** (*Export Bars*) e salve como CSV com o nome do símbolo, por exemplo
   `WIN$N_M1.csv`.
10. Repita os passos 5 a 9 com `IBOV` (salve como `IBOV_M1.csv`).

**Não abra os arquivos no Excel antes de mandar** — o Excel troca datas e vírgulas ao salvar, e o
programa recusa arquivo alterado. O arquivo certo começa com a linha
`<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>` (separada por tabulações).

## Onde salvar

Numa pasta **fora** do projeto (o histórico não vai para o git), por exemplo:

```
C:\Users\evert\Documents\hunter-mt5\
```

## O fuso horário (uma pergunta só)

O MT5 grava as barras no horário do **servidor**, sem dizer qual é. Olhe a hora que aparece na
janela Observação do Mercado (*Market Watch*) e compare com o relógio de Brasília:

- se for a mesma → diga "**o MT5 está no horário de Brasília**";
- se for diferente → diga a diferença (por exemplo "3 horas a mais").

O programa confere sozinho: com o fuso que você disser, o Ibovespa tem de começar às 10:00 de
Brasília. Se não bater, ele para e pergunta — nunca adivinha.

## O que mandar para a Sexta-feira

Cole numa mensagem só:

```
WIN:  C:\Users\evert\Documents\hunter-mt5\WIN$N_M1.csv   (símbolo: WIN$N, sem ajuste)
IBOV: C:\Users\evert\Documents\hunter-mt5\IBOV_M1.csv
Fuso: o MT5 está no horário de Brasília
```

## O que acontece depois (para saber o que esperar)

1. **Congelamento** (antes de qualquer resultado): o programa lê os arquivos, separa os pregões
   válidos, marca os primeiros 80 % como trecho principal e os últimos 20 % como reserva, calcula todos
   os sinais das três estratégias e grava tudo com uma impressão digital (sha256)
   (`uv run python -m infra.research.b3.run_family --phase freeze ...`).
2. **Trecho principal**: só então os resultados dos 80 % são calculados, com custo da B3
   (R$ 0,256 por perna), 1 tick de deslizamento por perna e as estatísticas registradas.
3. **Reserva**: os 20 % finais são lidos uma vez, depois.
4. O veredito de cada estratégia só pode ser **CONFIRMA**, **REFUTA** ou **NÃO CONFIRMA**. Mesmo um
   CONFIRMA vira, no máximo, um teste em papel daqui para frente — nunca dinheiro real direto.

Referências: pré-registros H-039, H-040 e H-041 na Fila de Hipóteses (congelados em 17/10/2026,
cópia em `.claude/state/h039-041/prereg_frozen.md`); H-038r (mesmo export); código em
`infra/research/b3/`.

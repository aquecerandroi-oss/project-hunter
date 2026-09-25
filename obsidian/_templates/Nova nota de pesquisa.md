---
tags: [knowledge, nota]
tema: 
fonte: 
fonte_url: 
lido_em: 
evidencia: anedótico | backtest do autor | estudo revisado | replicado
hipotese_testavel: sim | não
astra: pendente | concorda | discorda
status: aberto
owner: sexta-feira
updated: <% tp.date.now("YYYY-MM-DD") %>
confiança: "?"
tipo: pesquisa | leitura | consolidado
hipotese: H-0xx | —
variavel: —
populacao: —
efeito: —
ic: —
veredito: confirma | nao_confirma | refuta | limite_de_dado | em_curso | —
proximo_passo: —
classe_de_perda: comprou_no_topo | golpe_do_criador | recompra | custo | saida_normal | —
mercado: meme | cripto
---

# <% tp.file.title %>

> Depois de preencher, renomeie o arquivo para `KB-NNNN-<slug>.md` (próximo número livre em
> `obsidian/11-KNOWLEDGE/`, nunca reaproveitado). Duas chaves do frontmatter não se preenchem no
> chute: **`lido_em`** é a data em que a fonte foi *lida* (não a data em que a nota foi escrita), e
> **`confiança`** só recebe um dos quatro rótulos — `anedótico`, `backtest do autor`,
> `estudo revisado`, `replicado` — quando a evidência é **inteiramente** daquele tipo. Evidência
> mista fica **`?`**, e o campo `evidencia` descreve a mistura por extenso. `?` não é preguiça: é a
> diferença entre "ainda não classifiquei" e "classifiquei errado". Ver `docs/OBSIDIAN.md` §1.

## Como preencher os dez campos padronizados

Existem para o [[Mapa de Estrategias]] e o [[Dicionario de Variaveis]] lerem por Dataview em vez de
alguém reabrir cada nota. **Nunca inventar um valor**: o que não se sabe fica `—` (travessão), nunca
um chute nem um campo vazio (vazio não distingue "não sabemos" de "esqueci de preencher").

| Campo | O que é | Regra |
|---|---|---|
| `tipo` | `pesquisa` = medição nossa (dado próprio, real ou papel); `leitura` = literatura externa curada, sem teste nosso; `consolidado` = junta o veredito de várias notas/hipóteses | escolha um só; nota que mistura leitura e medição própria é `pesquisa` |
| `hipotese` | o `H-0xx` da [[Fila de Hipoteses]] que esta nota fecha ou alimenta | `—` se a nota não nasceu de uma hipótese pré-registrada |
| `variavel` | o nome da variável testada, como está no bloco da fila (`variável:`) | copiado, nunca reformulado |
| `populacao` | população do estudo (quem entrou, quantos, janela) | frase curta; números vêm da nota, nunca de memória |
| `efeito` | o `D` (diferença) medido, com o sinal | copiado do relatório/nota; `—` se o estudo não chegou a medir efeito |
| `ic` | o intervalo de confiança que acompanha o `efeito` | mesmo par de colchetes da nota; `—` junto com `efeito: —` |
| `veredito` | um dos rótulos do `docs/RESEARCH.md` (`confirma`/`nao_confirma`/`refuta`/`limite_de_dado`) mais `em_curso` para o que ainda não rodou | nunca "promissor" nem um sexto rótulo; nota `consolidado` que mistura vereditos fica `—` |
| `proximo_passo` | a frase de "reabrir quando..." ou o motivo de não fechar | copiada da nota; `—` se não houver próximo passo declarado |
| `classe_de_perda` | qual das cinco classes do classificador automático (T4.92, `comprou_no_topo`/`golpe_do_criador`/`recompra`/`custo`/`saida_normal`) esta nota ataca | só se aplica a notas do mercado `meme`; `—` em toda nota de `cripto` ou que não mira uma classe |
| `mercado` | `meme` ou `cripto` — de qual mesa/Lab é o dado | um só valor; nota que compara os dois usa o que domina a medição |

## O que afirma
Em uma ou duas frases, nas minhas palavras.

## Onde foi mostrado
Mercado, timeframe, regime, período, custos considerados (ou não).

## Como mediríamos aqui
Features do M2 que cobrem (ou o que falta), timeframe, regra de entrada, stop/alvo/invalidação, custos assumidos do Lab.

## Hipótese testável no Lab
Candidato de `Strategy` com parâmetros explícitos (`default_parameters`), o que seria o alvo (expectancy em R, taxa de alvo) e o que seria a refutação.

## Por que pode falhar
Overfitting, look-ahead, sobrevivência, custos, mudança de regime, dependência de dado que não temos.

## Segunda opinião (Astra)
O que ela concordou, o que discordou, com o motivo.

## Relacionados
[[Strategy Backlog]] · notas irmãs · EXP se existir

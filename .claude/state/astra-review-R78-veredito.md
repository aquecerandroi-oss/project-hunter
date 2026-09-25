**RESUMO**

Como `quant-engineer`: **H-018 está correta; H-015 dá REFUTA por (c) com a medição atual, mas eu corrigiria a prova dos zeros antes de gravar o encerramento.**

- **H-018:** LIMITE DE DADO nas duas populações: 10 reais e 5 papel, abaixo de 20. A sensibilidade não substitui a primária ([notas:43](C:/dev/project-hunter/.claude/state/notes-R78.md:43), [55](C:/dev/project-hunter/.claude/state/notes-R78.md:55)).
- **H-015:** 38/104 = 36,5% aciona (c). Pela letra original, (a) também refutaria; **NÃO CONFIRMA por (a) sozinha depende da errata explicitamente declarada**. O rótulo final permanece REFUTA ([regra:182](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:182>), [notas:112](C:/dev/project-hunter/.claude/state/notes-R78.md:112)).
- **Emenda 2c:** legítima como correção pós-execução documentada, preservando v0. `mint_busy` pula sem consumir a proposta; a aprovação posterior reutiliza `suggested`. Tecnicamente, `decided_at` marca **aprovação**, não a admissão de risco. n=8→10 não muda o rótulo ([auto_approve.py:170](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/auto_approve.py:170), [206](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/auto_approve.py:206), [notas:48](C:/dev/project-hunter/.claude/state/notes-R78.md:48)).

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

`uv run pytest .claude/state/r78/test_h018.py .claude/state/r78/test_h015.py -q`, sem cache/bytecode/sincronização:

```text
18 passed in 1.08s
```

**MUST-FIX**

1. **O classificador não prova ausência de compra.** Uma compra de 0,001 SOL com conta já existente retorna `(0.0, 0)`; reproduzi esse resultado. Inversamente, gasto de 0,01 SOL sem compra recebe `(0.01, 1)`: os campos examinados não distinguem os casos. **Nos dados, 8 dos 114 zeros aceitos têm gasto positivo não criador abaixo do corte** — podem ser aluguel, mas não foram classificados como tal. Isso pode alterar exclusões, cortes e vencedoras bloqueadas ([h015_run.py:25](C:/dev/project-hunter/.claude/state/r78/h015_run.py:25), [51](C:/dev/project-hunter/.claude/state/r78/h015_run.py:51)).

   Também excluir a transação `create` inteira perde uma compra de outra carteira executada nela ([gtfa_tpl.py:59](C:/dev/project-hunter/.claude/state/r78/gtfa_tpl.py:59)). Validar compras por instruções/eventos do mint e comprador efetivo, incluindo o `create`; casos não classificáveis ficam não resolvidos. **Não demonstrei mudança do rótulo; demonstrei que “zeros provados” excede a evidência.**

2. **“Cauda, não média” precisa de redação descritiva.** “Não muda a frequência” afirma ausência de efeito; “aprofunda” sugere causalidade. Cenário: a composição diferente de portas/saídas explica parte das caudas. Escrever: **“Nesta amostra, as taxas de vitória dos extremos foram próximas; houve mais perdas ≥50% e menos ganhos ≥50% no alto. Pista exploratória para coorte nova.”** A média inconclusiva não demonstra efeito exclusivamente nas caudas ([notas:107](C:/dev/project-hunter/.claude/state/notes-R78.md:107), [118](C:/dev/project-hunter/.claude/state/notes-R78.md:118)).

**NICE-TO-HAVE**

- (b): “não acionada; grade pontual compatível com patamar”. O protocolo só a julga quando a principal confirma ([notas:80](C:/dev/project-hunter/.claude/state/notes-R78.md:80)).
- Corrigir “variável da chain 342” para **363** na §4c ([notas:94](C:/dev/project-hunter/.claude/state/notes-R78.md:94), [104](C:/dev/project-hunter/.claude/state/notes-R78.md:104)).

**O QUE EU FARIA DIFERENTE**

Validaria o classificador e repetiria H-015 antes do registro definitivo, preservando esta corrida.

**CONCORDO COM**

Primária alvo∧lucro; separação real/papel; publicação da emenda e v0; nenhuma regra de mesa derivada destes resultados.

**OBSIDIAN**

- **Fila de Hipoteses** — registrar H-018 e acrescentar H-015 após resolver a classificação dos zeros.
- **Revisoes-Astra/Index** — vincular esta revisão e a distinção entre gasto do pagador e compra comprovada.
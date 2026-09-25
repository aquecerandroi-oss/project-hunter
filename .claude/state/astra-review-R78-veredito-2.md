**RESUMO**

Ainda há um must-fix no classificador. Os rótulos continuam compatíveis com os números publicados; §5.1 ficou suficientemente descritiva.

**ARQUIVOS**

Nenhum alterado.

**TESTES**

`uv run pytest .claude/state/r78/test_h015.py -q -p no:cacheprovider` — `9 passed in 1.05s` (sem bytecode/sincronização).

**MUST-FIX**

**Saldo líquido não prova compra nem ausência dela.** Cenários sintéticos reproduzidos: compra seguida de venda integral na mesma transação retorna `(0.0, 0)`; transferência gratuita retorna `(0.0, 1)`. O primeiro aceita falso zero; o segundo exclui zero legítimo. O problema está no critério `tok > 0` ([h015_tok.py:24](C:/dev/project-hunter/.claude/state/r78/h015_tok.py:24)), usado para excluir linhas ([h015_run.py:51](C:/dev/project-hunter/.claude/state/r78/h015_run.py:51)). Validar instruções/eventos; casos indistinguíveis precisam ficar não resolvidos. **Não demonstrei ocorrência na amostra nem mudança do rótulo.**

**NICE-TO-HAVE**

Nenhum.

**O QUE EU FARIA DIFERENTE**

Fecharia essa ambiguidade antes de declarar “zeros provados”.

**CONCORDO COM**

- **H-015 = REFUTA por (c)** nos números publicados: 38/104 = 36,5%; validação definitiva depende da classificação acima ([notas:118](C:/dev/project-hunter/.claude/state/notes-R78.md:118)).
- **H-018 = LIMITE DE DADO**: primárias com 10 reais e 5 papel ([notas:43](C:/dev/project-hunter/.claude/state/notes-R78.md:43), [55](C:/dev/project-hunter/.claude/state/notes-R78.md:55)).
- **§5.1 adequada**: delimita amostra, composição e caráter exploratório ([notas:121](C:/dev/project-hunter/.claude/state/notes-R78.md:121)).

**OBSIDIAN**

- **Fila de Hipoteses** — registrar H-018 e manter explícita a pendência de validação de H-015.
- **Revisoes-Astra/Index** — vincular a rodada 2 e a distinção entre saldo líquido e compra.
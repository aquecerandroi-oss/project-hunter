Restam **dois MUST-FIX de severidade alta**, reproduzidos em memória:

1. **Gap conhecido ainda esconde stop válido** — [triggers.py:146](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:146).

   Watermark `99`, stop `95`, lote `[100@90 válido]`, `tape_gap=True`: retorna `unavailable/tape_gap` antes de examinar o stop. Se o gap fechar após 11 segundos, o mesmo lote retorna `unavailable/stale_trade`. **O stop nunca foi publicado.** A assimetria de publicar stop observado, preservando a informação de indisponibilidade, precisa alcançar esse caminho.

2. **Certos IDs malformados abortam o lote inteiro e nunca chegam à expiração** — [tape.py:81](C:/dev/project-hunter/packages/core/hunter_core/execution/tape.py:81), [tape.py:143](C:/dev/project-hunter/packages/core/hunter_core/execution/tape.py:143).

   `--101` passa em `raw.lstrip("-").isdigit()`, mas `int("--101")` lança `ValueError`. Lote `[100@90 válido, --101@100]`: nenhum stop é reportado, pois a leitura inteira aborta.

   Isso também responde **(b)**: `[--101@100 com ts de 45 segundos atrás, 102@110 válido]` continua lançando `ValueError`. A conversão acontece **antes** do descarte por idade; enquanto esse registro for reapresentado, nem alvos novos são publicados. O parsing precisa transformar a falha em ID inválido, permitindo o tratamento de defeito e expiração.

Executei `uv run pytest packages/core/tests/unit/execution/test_triggers.py -q`: **30 passed in 1.57s**, com escrita de bytecode e cache do pytest desativada. Os cenários acima escapam dessa suíte. Nenhum arquivo modificado.

**OBSIDIAN**

- **Execution Engine** — registrar os caminhos restantes de perda de stop: retorno antecipado por gap e exceção no parsing de ID.
- **Revisoes-Astra/T3.4b** — acrescentar os dois cenários reproduzidos da terceira rodada.
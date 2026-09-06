Concordo com o desenho, com duas ressalvas concretas.

**(a)** `_memo` é aceitável: `compare=False` também o exclui do hash padrão; `init=False` com `default_factory` dá memo novo no `replace()`. Porém **não o exclui de `asdict()` nem do pickle padrão**; não prometa identidade dessas serializações do contexto. Isso não altera automaticamente o contrato explícito do vetor/estado ([vector.py:213](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/vector.py:213), [state.py:29](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/state.py:29)). [Referência Python](https://docs.python.org/3.12/library/dataclasses.html).

`frozen` é superficial: o construtor direto aceita uma lista em `final_candles` sem convertê-la; um `append()` posterior deixaria o memo obsoleto. Normalize para tuple. O builder já faz isso ([context.py:214](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:214), [context.py:300](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:300)). Mantenha também o ndarray privado e somente leitura.

**(b)** Aceito referência antiga congelada em testes; **não exijo golden bytes fixos**. É evidência suficiente para esta alteração, não prova universal. Exigiria:

- Estados independentes, carregados corte a corte, comparando também `canonical_json(state.as_wire())`.
- Verificação de que o monkeypatch realmente executa o caminho antigo.
- Casos com gaps, warm-up, fronteiras de 15 minutos, janela móvel de 1500, memo frio/quente e `replace()`.

**Cuidado essencial:** a cauda de `final_candles` não é a cauda de `usable` em `bars_15m`. Um gap no bucket parcial pode encurtar a primeira sem afetar barras completas anteriores. Não reutilize um único comprimento para ambas ([windows.py:125](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:125)).

A divisão inteira proposta preserva os minutos para candles válidos, cujo alinhamento já é validado ([market.py:290](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:290)); use `dtype=np.int64` explícito.

**(c)** Com tuple, candles imutáveis e contexto novo/`replace()`, não vejo look-ahead adicional nem retenção global. `replace(as_of=...)` revalida o corte; recuar para antes de um fechamento deve falhar ([context.py:164](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:164)). Teste isso após aquecer o memo.

Somente leitura; nenhum arquivo alterado, testes não executados.

**OBSIDIAN**

- **Features (Feature Engine)** — registrar memo por contexto, distinção entre as duas caudas e critérios de equivalência da T2.2b.
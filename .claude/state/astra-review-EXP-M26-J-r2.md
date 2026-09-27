**RESUMO**

**REVISE: resta o must-fix 2. Não aceito congelar J ainda.** Os itens 1, 3, 4 e 5 fecham os cenários anteriores; a janela de exportação apenas reduz a exposição à retroatividade.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Com sincronização, bytecode e cache do pytest desativados:

```text
uv run pytest infra/research/exp_m26/tests/ -q --ignore=infra/research/exp_m26/tests/test_ler.py -k 'not test_fim_de_linha_nao_muda_e_um_byte_muda'

102 passed, 1 deselected in 10.79s
```

Excluí os testes que escrevem arquivos. Validei a CLI separadamente, em memória, com `uv run python -B -`: retorno 0, `reps=10000`, Python `3.12.14`, NumPy `2.5.2`; `--reps` e `--agora` recusados com saída 2. Não executei integração SQL.

**MUST-FIX**

**2 — Informação chegada entre L e L+1h ainda muda a leitura de L.**

O SQL continua exportando `completed_at`/`migrated_at` correntes ([export_h022.sql:44](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:44)). `na_leitura` devolve a aposta com esses metadados quando `exit_at ≤ L` ([modelo.py:80](C:/dev/project-hunter/infra/research/exp_m26/modelo.py:80)), e a validação aceita export em L+30min ([leitura.py:243](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:243)).

Repeti o contraexemplo anterior, **sintético, com 10.000 réplicas**: em L, 40 vendas são avaliáveis; em L+10min chega informação de conclusão anterior às vendas; exportamos em L+30min.

| Export aceito | A_true | C_true | Rótulo |
|---|---:|---:|---|
| Em L | 168 | 0 | CONFIRMA |
| Em L+30min, após atualização | 128 | 40 | NÃO CONFIRMA |

**L permaneceu idêntico nos dois casos.** O mecanismo de recuo continua possível pelo `LEAST` ([repo_token_sql.py:89](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:89)).

Preservar e reutilizar o mesmo export garante reprodução daquele arquivo; não garante que ele represente o estado disponível em L. Para fechar: snapshot preservado em L ou histórico que permita reconstruir os valores disponíveis em L. Encurtar a tolerância não elimina o cenário.

**NICE-TO-HAVE**

Nenhum adicional nesta rodada.

**O QUE EU FARIA DIFERENTE**

Acrescentaria exatamente essa regressão **dentro da janela aceita**, exigindo que a informação chegada em L+10min não altere a leitura de L.

**CONCORDO COM**

Quanto às correções desta rodada:

- **1 fechado:** interseção dos suportes antes dos dois estimadores; o contraexemplo A/B está coberto ([robustez.py:110](C:/dev/project-hunter/infra/research/exp_m26/robustez.py:110)).
- **3 fechado:** guarda aplicada a todas as oportunidades antes das contas ([leitura.py:235](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:235)).
- **4 fechado:** ordenação canônica antes dos sorteios ([leitura.py:230](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:230)).
- **5 fechado:** CLI fixa réplicas e publica versões ([ler.py:31](C:/dev/project-hunter/infra/research/exp_m26/ler.py:31), [ler.py:42](C:/dev/project-hunter/infra/research/exp_m26/ler.py:42)).
- Sem bloqueio adicional na semente `20260926` ou na aposentadoria exatamente no corte com metas atingidas ([constantes.py:46](C:/dev/project-hunter/infra/research/exp_m26/constantes.py:46), [calendario.py:62](C:/dev/project-hunter/infra/research/exp_m26/calendario.py:62)).

**OBSIDIAN**

- **EXP-M26 — estrutura do gráfico em moedas maduras:** registrar quatro correções aceitas e congelamento pendente da preservação temporal.
- **Revisões-Astra — EXP-M26/J:** registrar a rodada 2 e o contraexemplo dentro de `[L, L+1h]`.
- **Diálogo — EXP-M26:** explicitar a diferença entre reproduzir um export e reconstruir o estado disponível em L.
**RESUMO**

`DONE_WITH_CONCERNS`: manteria as escolhas principais, mas corrigiria dois pontos antes de fechar.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `quant-engineer`.

**TESTES**

Reprodução em memória via `uv run python -B -`, sem sincronização ou bytecode. Saída real:

```text
prec=28 age=10.000001 quality=degraded spread_quality=degraded
prec=6 age=10.0000 quality=ok spread_quality=ok
entry=crossed provenance=missing_input
spread_pct=missing_input
orderbook_imbalance_20=missing_input
```

Não executei a suíte pytest nem verifiquei a sequência histórica de TDD.

**MUST-FIX**

**(d/e) Precisão ambiente altera a qualidade.** [context.py:73](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:73) elimina o float, mas soma/divisão continuam fora de `localcontext(CONTEXT)`. Cenário reproduzido: book com idade `10.000001` s passa de `degraded` para `ok` sob precisão 6. Corrigir o helper e testar microssegundos junto ao limiar.

**(e) A corrupção desaparece no caminho de produção.** O decoder retorna `crossed` em [hotstate.py:208](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:208), mas a calculadora recebe `None` e retorna `missing_input` ([micro.py:62](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:62)); a proveniência também perde o motivo ([quality.py:276](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:276)). Cenário: snapshot cruzado chega ao envelope indistinguível de book ausente. Mapear `crossed/corrupt` para `CORRUPT_INPUT` até o vetor, com teste integrado.

**NICE-TO-HAVE**

Registrar quantidade de níveis por lado e completude da fonte, para distinguir mercado fino de coleta incompleta.

**O QUE EU FARIA DIFERENTE**

**(c)** Manteria o construtor estrito ([context.py:236](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:236)). Há risco operacional: T2.5 carregar o histórico inteiro e avaliar um corte anterior faz o backtest levantar; capturar e ignorar essas avaliações pode enviesar a amostra. O adaptador durável deve selecionar observações disponíveis até o corte. Isso não exige afrouxar `build_context`.

**CONCORDO COM**

- **(a)** `INSUFFICIENT_SAMPLE` é adequado ao contrato atual de 20 níveis por lado ([micro.py:129](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:129)). Falha concreta: perder 13 bids no transporte cria pressão vendedora artificial. Se houver prova de que sete bids são o livro completo, o número contém informação útil; eu o publicaria sob outra definição explícita.
- **(b)** Recusar também imbalance é correto: uma junção de bid novo com ask antigo pode combinar quantidades de instantes diferentes. A inconsistência compromete o snapshot ([micro.py:64](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:64)).
- **(d)** Não identifiquei look-ahead novo em 3 ou 6: truncamento é metadado ([hotstate.py:324](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:324)); o compromisso futuro acompanha somente funding observado até o corte ([hotstate.py:273](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:273)). A ressalva decimal de 4 está acima.

**OBSIDIAN**

- **Features (Feature Engine)** — registrar profundidade exigida, propagação de corrupção e precisão fixa também nas idades.
- **Diálogo Claude ⇄ Astra — M2** — explicitar a seleção temporal exigida do adaptador durável da T2.5.
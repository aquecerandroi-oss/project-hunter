**RESUMO**

Sim, concordo com a semântica e, **sob a premissa de não reprocessar o mesmo evento com as duas versões**, não vejo duplicação histórica causada pela mudança do hash. Parecer como `exchange-integration-specialist`.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão estática em modo OPINIÃO. Não consultei a VPS.

**MUST-FIX**

Nenhum bloqueio na semântica proposta: `z` obrigatório, zero preservado, `ap` preferencial, fallback somente para `p` e produto recalculado estão em [streams.py:312](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:312).

**NICE-TO-HAVE**

Documentaria em `.claude/state/notes-liquidations.md`:

- **Corte histórico:** commit e horário UTC efetivo do deploy; as 8.421 linhas informadas são uma fotografia anterior, não necessariamente toda a população antiga até o deploy. Não misturar períodos como série homogênea.
- **Fallback é aproximação:** quando `z > 0` e `ap` falta ou é zero, `z*p` usa preço da ordem; não garante notional efetivamente executado. Esse caminho existe em [streams.py:313](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:313).
- **Acumulado não é incremento:** se chegarem dois snapshots da mesma ordem com `z=1` e depois `z=2`, somar produz 3, embora o acumulado final seja 2. É uma limitação condicional a documentar, não ocorrência comprovada; a identidade por conteúdo não reconcilia essas atualizações ([publication.py:35](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/publication.py:35)).
- **Sem replay não significa garantia universal:** duas versões recebendo o mesmo frame durante sobreposição de coletores também poderiam gerar IDs diferentes. A conclusão depende de não haver esse processamento duplo; deduplicação por `(id, ts)` não o resolveria ([persist_rows.py:195](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:195)).

**O QUE EU FARIA DIFERENTE**

Descreveria a série como “snapshots de execução acumulada observada, com preço da ordem como fallback”. Evitaria prometer volume total ou limite inferior garantido.

**CONCORDO COM**

Preservar `qty=0`, não substituir ausência de `z` por `q`, manter o histórico e deixar alterações de identidade fora deste escopo.

**OBSIDIAN**

- **Liquidações: o fluxo forçado que observamos por amostragem** — registrar correção, corte histórico e limitações de fallback/acumulação.
- **Exchange Adapters** — atualizar contrato de normalização de liquidações.
- **Market Collector** — explicitar as condições da deduplicação durante a transição.
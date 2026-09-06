**RESUMO**
Concordo com a direção, com os ajustes abaixo; parecer no escopo de `backend-specialist`.

**ARQUIVOS**
Nenhum criado ou modificado.

**TESTES**
Não executados; análise estática do desenho e do código.

**MUST-FIX**
- **(1a) AST é defensável como fecho conservador de imports, não como prova de dependências realmente executadas.** Resolva imports absolutos/relativos, ciclos e aliases; rejeite construções dinâmicas não suportadas. Hash por bytes continuará sensível a comentários nos módulos incluídos — isso é esperado.
- **(1b) Inclua os `__init__.py` dos pacotes ancestrais, mas torne-os mínimos antes.** Hoje o de estratégias importa ambas as estratégias e o registry; seguir esse fecho reintroduziria o acoplamento que você quer eliminar ([__init__.py:42](/C:/dev/project-hunter/packages/core/hunter_core/strategies/__init__.py:42)).
- **(1c) Inclua todo módulo `hunter_core` alcançável.** Excluir `domain` permite mudar alinhamento/arredondamento sem mudar o digest: dependências presentes em [momentum_v1.py:28](/C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:28) e [base.py:41](/C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:41). Se o fecho crescer demais, separe os utilitários; não omita dependências.
- **(2) Resolver pelo módulo é aceitável**, exclusivamente pelo mapa autorizado do registry, exigindo módulo unívoco e família compatível. Caso contrário, uma linha momentum poderia executar volume. Fallback por `(key, version)` somente no script antes de congelar; ativa sem digest válido deve continuar recusada ([repo.py:114](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:114)).
- **Supersede deve ser atômico e protegido contra concorrência:** copiar schema/parâmetros/`params_format` da linha antiga, validar, criar/ativar a sucessora e depreciar a anterior na mesma transação. Uma falha intermediária não pode deixar só a antiga deprecated. O script atual obtém defaults do código: não reutilize essa parte para copiar o experimento ([activate_strategy_version.py:112](/C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:112)).

**NICE-TO-HAVE**
Registre o manifesto dos módulos e a versão do algoritmo de digest; teste módulo independente, dependência transitiva alterada e imports não suportados.

**O QUE EU FARIA DIFERENTE**
**(3) `/ready` vermelho para qualquer ativa não executável**, com contagens e motivo por versão: uma estratégia saudável não deve esconder outra morta. Continue processando as válidas e outcomes pendentes; readiness não deve encerrar o worker. Hoje os checks não verificam versões ([health.py:124](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/health.py:124)). Conte ativas antes dos filtros; warm-up não é incompatibilidade de código.

**CONCORDO COM**
Função e resolução de caminho únicas; versão do experimento separada da implementação; sucessora preservando o congelamento ([DATABASE.md:781](/C:/dev/project-hunter/docs/DATABASE.md:781)). Não afirme equivalência histórica apenas por copiar parâmetros: o digest antigo não comprova sozinho que o código atual é idêntico.

**OBSIDIAN**
Strategies — documentar fecho, identidade da implementação e supersede.
Workers — documentar readiness por incompatibilidade parcial e métricas.
SHADOW — registrar a revisão do contrato de proveniência, preservando o histórico.
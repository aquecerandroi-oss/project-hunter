**RESUMO:** `APPROVE_WITH_NITS` nas cinco mudanças.

**ARQUIVOS:** nenhum alterado nesta revisão.

**TESTES:** não executados; análise estática.

**MUST-FIX:** nenhum.

**NICE-TO-HAVE:** a assertion de custos aceita perder o banner ou o rodapé sem falhar ([lab-page.test.tsx:84](/C:/dev/project-hunter/apps/web/tests/lab-page.test.tsx:84)). Testaria os dois separadamente e incluiria duas versões com custos diferentes.

**O QUE EU FARIA DIFERENTE:** manteria o `data-testid`; escopa precisamente o teste sem adicionar semântica artificial à interface ([lab-version-card.tsx:64](/C:/dev/project-hunter/apps/web/components/lab/lab-version-card.tsx:64)).

**CONCORDO COM:** custos por card permanecem necessários ([lab-version-card.tsx:115](/C:/dev/project-hunter/apps/web/components/lab/lab-version-card.tsx:115)); os guards preservam as verificações de escaping ([markets-path-escaping.test.ts:20](/C:/dev/project-hunter/apps/web/tests/markets-path-escaping.test.ts:20)). O launcher mantém WS em **8000**, portanto depende também dessa API para realtime ([launch.json:17](/C:/dev/project-hunter/.claude/launch.json:17)); aceitável nesse arranjo híbrido.

**OBSIDIAN:** **Revisoes-Astra/Index** — registrar aprovação com sugestão de cobertura independente dos custos no banner e nos cards.
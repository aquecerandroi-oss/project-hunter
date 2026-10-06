**RESUMO**

`APPROVE_WITH_NITS`. A correção é coerente; nenhum must-fix identificado na revisão estática.

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim.

**TESTES**

Não executei testes nem build; parecer baseado em leitura do código, configuração e histórico Git.

**MUST-FIX**

Nenhum. Ressalva sobre cobertura: **sim, produção pode passar com a rota quebrada**. O 404 em `tests/e2e/public.spec.ts:41` não distingue pasta privada de `notFound()`. O guard em `apps/web/tests/design-route-folder.test.ts:18` detecta a renomeação original, mas não detectaria, por exemplo, um `notFound()` incondicional com a pasta correta. Isso exige executar também o ramo development (`tests/e2e/public.spec.ts:46`).

**NICE-TO-HAVE**

- **CI ⇒ production é razoável neste pipeline:** o E2E sobe Docker (`.github/workflows/ci.yml:258`), cuja imagem define produção (`infra/docker/Dockerfile.web:65`). Preferiria declarar `E2E_WEB_MODE=production` explicitamente no job e rejeitar valores inválidos: hoje erros de digitação caem silenciosamente no default (`tests/e2e/public.spec.ts:25`).
- Corrigir o comentário com caminho antigo em `tests/e2e/public.spec.ts:34`. Para exigir exatamente **200**, substituir `ok()` — que aceita qualquer 2xx — em `tests/e2e/public.spec.ts:46`.

**O QUE EU FARIA DIFERENTE**

Executaria o mesmo teste contra development e production. O guard de filesystem protege o nome; a execução development comprova a renderização. Manteria a exclusão do Clerk, já presente em `apps/web/middleware.ts:45`.

**CONCORDO COM**

**Sim, `%5Fdesign` literal funciona no checkout Linux e é a convenção correta do Next**, documentada para gerar segmentos iniciados por underscore. Não deve ser renomeado para `_design`. [Documentação oficial](https://nextjs.org/docs/13/app/building-your-application/routing/colocation). A proteção explícita de produção permanece em `apps/web/app/%5Fdesign/page.tsx:12`.

**OBSIDIAN**

- **Infrastructure** — registrar o contrato de modo do E2E e a limitação do 404 isolado.
- **Changelog** — acrescentar uma retificação da entrada de `242a359`, que descreve a renomeação incorretamente como correção (`obsidian/08-CHANGELOG/Changelog.md:521`).
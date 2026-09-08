# A base Obsidian do PROJECT HUNTER — padrão, higiene e ferramenta

**Dona:** Sexta-feira. **Escopo:** a pasta `obsidian/` do repositório — a base de conhecimento **do
projeto**, viva e versionada no git. Ela é diferente de duas outras coisas com que é fácil confundir:

| Onde | O que é | Quem escreve | Como se escreve |
|---|---|---|---|
| `obsidian/` | base do **projeto**: arquitetura, mercado, trading, experimentos, decisões, bugs, changelog, operações, conhecimento externo | Sexta-feira e os scripts geradores | arquivos, versionados no git |
| `vault/` | memória **pessoal** da Sexta-feira | Sexta-feira | **só** por MCP (acesso direto ao arquivo é bloqueado por hook) |
| `docs/` | especificação **normativa**: arquitetura, ADRs, planos, contratos, relatórios de milestone | os especialistas e a Sexta-feira | arquivos, versionados no git |

As páginas de `obsidian/` **resumem e linkam** para `docs/` em vez de duplicar. A decisão de criar
esta estrutura é a ADR 0003 (`docs/decisions/0003-base-de-conhecimento-obsidian.md`).

> **A raiz do vault é `obsidian/`.** Abra essa pasta no Obsidian, não a raiz do repositório. Os
> canvases apontam para caminhos relativos a ela (`03-TRADING/Portfolio.md`). Não existe
> `obsidian/.obsidian/` versionado — a configuração do app é de cada máquina e fica fora do git.

---

## 1. Padrão de frontmatter

Toda nota `.md` de `obsidian/` tem, no mínimo, estas quatro chaves:

```yaml
---
tags: [lista, de, tags]
status: <ver vocabulário abaixo>
owner: sexta-feira
updated: 2026-09-08
---
```

- `updated` é a data ISO (`AAAA-MM-DD`) da última alteração de conteúdo — não a de um retoque de
  formatação.
- `owner` é quem responde pela página. Hoje é `sexta-feira` em toda a base; páginas geradas por
  script não têm `owner` (ver a exceção do catálogo de estratégias adiante).
- `status` é texto livre com um vocabulário de uso corrente, não fechado pelo linter:
  `vivo` (página de referência que muda quando o produto muda) · `registro` (documento datado que
  não se reescreve: diário, diálogo, revisão) · `implementado` · `parcial` · `planejado` ·
  `em-andamento` · `aberto` · `aguardando-ativacao` · `curada` (nota de conhecimento externo
  revisada) · `template`.

### Chaves obrigatórias por pasta

| Pasta / arquivo | Além das quatro comuns |
|---|---|
| `05-EXPERIMENTS/EXP-*.md`, `_TEMPLATE-EXP.md` | `exp`, `strategy`, `version`, `result`, `evaluable`, `days`, `last_eval` |
| `07-BUGS/*.md` | `severity`, `opened`, `closed` |
| `06-DECISIONS/**` | `decided_on`, `by` |
| `11-KNOWLEDGE/KB-*.md`, `_TEMPLATE-NOTE.md` | `fonte`, `lido_em`, `confiança` |
| `03-TRADING/Estrategias/**` | **exceção**: páginas geradas, ver abaixo |
| todo o resto | só as quatro comuns |

### Vocabulários fechados (o linter reprova valor fora da lista)

| Chave | Valores |
|---|---|
| `updated`, `opened`, `closed`, `decided_on`, `lido_em`, `last_eval` | `AAAA-MM-DD` (ou `""` quando ainda não há data) |
| `result` | `inconclusivo` · `validada` · `reprovada` · `nao-iniciado` |
| `confiança` | `anedótico` · `backtest do autor` · `estudo revisado` · `replicado` · `?` |
| `severity` | `CRITICAL` · `HIGH` · `MEDIUM` · `LOW` · `misto` |
| `evaluable`, `days` | inteiros ≥ 0 |

### O que cada chave significa onde ela é menos óbvia

**Experimentos.** `exp` é o identificador (`EXP-0003`). `evaluable` e `days` são **copiados da última
avaliação datada da própria página** — que por sua vez veio de SQL colado. Nunca são estimados, e
nunca são recalculados pela Base. `last_eval` é a data dessa avaliação (`""` quando não houve
nenhuma). `result` obedece ao limiar editorial: **abaixo de 100 outcomes avaliáveis E 30 dias
distintos só pode ser `inconclusivo`**. `nao-iniciado` é diferente de `inconclusivo`:
`inconclusivo` é o veredito de quem mediu e não pôde concluir; `nao-iniciado` é o de quem não mediu
porque a população não existe (é o caso da [[EXP-0005-momentum-paper]] enquanto a linha paper não
for ativada). Um experimento que não mede outcomes — um *instrumento*, como o `EXP-0003` — leva
`evaluable: 0` e `strategy: ""`; isso não é "zero de amostra", é "não mede outcomes", e a página
explica.

**Bugs.** `07-BUGS/` guarda hoje **dois registros agregados** (`Open Bugs`, `Resolved Bugs`), não uma
página por bug. Nesses dois, as chaves descrevem o **registro**: `severity: misto`, `opened` = a data
da entrada mais antiga, `closed: ""` enquanto houver item aberto. Quando um bug ganhar página
própria, as três chaves passam a descrever aquele bug.

**Decisões.** `decided_on` é a data em que a decisão — ou a opinião registrada, no caso de uma
revisão da Astra — ficou fixada. `by` é quem a fixou: `everton` · `sexta-feira` ·
`sexta-feira (claude+astra)` · `astra`.

**Conhecimento.** `fonte` e `lido_em` são procedência: sem elas a nota não é conhecimento, é
opinião. `confiança` é a qualidade da evidência, e ela **nunca é adivinhada**: quando o campo
`evidencia` da nota não começa por exatamente um dos quatro rótulos, `confiança` fica `?` até
alguém ler a fonte e decidir. Hoje **32 das 75 notas estão em `?`** — a maioria porque a evidência
é mista (documentação + medição própria + preprint), e essa mistura é informação, não defeito.

### A exceção: `03-TRADING/Estrategias/**`

Aquelas páginas são **geradas** por `infra/scripts/export_strategies_to_obsidian.py` (T3.20) a partir
do catálogo no banco. **Não se edita à mão**, e o linter não exige `owner` nem `status` nelas. O que
ele exige: `tags`, `strategy`, `updated` em toda página, e mais `version`, `purpose`, `status`,
`code_ref`, `params_hash` nas páginas de versão.

---

## 2. Os quatro callouts

Quatro tipos próprios, além dos nativos do Obsidian. Eles existem para que a leitura rápida de uma
página longa não confunda **o que foi medido** com **o que foi decidido**, nem promessa com risco.

```markdown
> [!veredito] O dia em uma frase
> A conclusão, curta. Nunca uma promessa.

> [!medido] O que foi lido no banco (as_of = ...)
> Só número que saiu de SQL rodado e colado. Sempre com o denominador.

> [!alerta] O que está bloqueando
> Risco, trava, divergência, dado que falta.

> [!decisao] Quem decide, e o que já está decidido
> Decisão tomada, por quem, e o que continua sendo do Everton.
```

Regra de uso: **`> [!medido]` só carrega número que veio de comando rodado**. Se não rodou, o callout
diz que não rodou — como no diário de 2026-09-08, onde "nada foi medido" é o próprio achado. Um turno
sem medição registrado como silêncio é indistinguível de um instrumento quebrado.

Exemplos aplicados: [[Diario/2026-09-06]], [[Diario/2026-09-07]], [[Diario/2026-09-08]] e
[[EXP-0005-momentum-paper]].

### O snippet de CSS — instalação manual (uma vez, na máquina do Everton)

**Não existe `obsidian/.obsidian/` no repositório**, então o snippet não pôde ser versionado junto:
a pasta de configuração do Obsidian é criada pelo app na máquina de quem abre o vault, e versioná-la
traria junto o estado local (plugins, layout de janelas, workspace). Para instalar:

1. Abra `obsidian/` no Obsidian.
2. Configurações → Aparência → **Snippets de CSS** → ícone de pasta (abre `obsidian/.obsidian/snippets/`).
3. Crie o arquivo `hunter.css` com o conteúdo abaixo.
4. Volte às configurações e **ligue** o snippet `hunter`.

```css
/* PROJECT HUNTER — os quatro callouts da base. Cores dos tokens do tema, para
   funcionar em claro e escuro sem fixar hex. */

.callout[data-callout="veredito"] {
  --callout-color: 138, 92, 245;      /* roxo — conclusão */
  --callout-icon: lucide-gavel;
}
.callout[data-callout="medido"] {
  --callout-color: 32, 156, 238;      /* azul — número que saiu de SQL */
  --callout-icon: lucide-ruler;
}
.callout[data-callout="alerta"] {
  --callout-color: 233, 151, 63;      /* âmbar — risco, trava, divergência */
  --callout-icon: lucide-triangle-alert;
}
.callout[data-callout="decisao"] {
  --callout-color: 68, 207, 110;      /* verde — decisão tomada */
  --callout-icon: lucide-check-check;
}

/* Um `[!medido]` é para ser lido em bloco: números em fonte tabular para as
   colunas baterem quando houver mais de uma linha. */
.callout[data-callout="medido"] .callout-content {
  font-variant-numeric: tabular-nums;
}

/* Frontmatter com muitas chaves fica alto demais nas páginas de estratégia. */
.metadata-container { font-size: 0.85em; }
```

Sem o snippet, os quatro callouts continuam **renderizando** — o Obsidian usa o estilo padrão de
`note` para um tipo que não conhece. O snippet só dá cor e ícone.

---

## 3. As duas Bases

Arquivos `.base` (Bases nativas do Obsidian, formato YAML). Elas **não calculam nada** e não escrevem
nada: leem o frontmatter das páginas e mostram em tabela ou cartão.

| Arquivo | O que mostra |
|---|---|
| `obsidian/05-EXPERIMENTS/Experimentos.base` | um experimento por linha, com `evaluable`/`days` contra o limiar de 100/30 e uma fórmula `limiar` que diz qual dos dois lados falha. Views: *Experimentos*, *Abaixo do limiar editorial*, *Cartões*. |
| `obsidian/03-TRADING/Estratégias.base` | uma versão de estratégia por linha. Views: *Versões*, *Ativas*, *Linha paper*, *Cartões*. |

Duas escolhas que valem explicação:

- **O filtro é por tag, não por pasta.** Como a raiz do vault não está fixada no repositório, um
  `file.inFolder("05-EXPERIMENTS")` quebraria para quem abrisse a raiz do repo em vez de `obsidian/`.
  `file.hasTag("experimento")` funciona nos dois casos.
- **`Estratégias.base` não tem coluna "veredito" nem "replicação".** Nenhuma das duas existe como
  propriedade nas páginas geradas por T3.20, e criar a coluna vazia faria a Base parecer ter um dado
  que o vault não tem. Em lugar delas, `exp` aponta para a página onde o veredito está escrito, e
  `derived_from` + `cohorts` mostram a linhagem — que é o que "replicação" significa aqui. Promover
  `veredito`/`replicacao` a propriedade do frontmatter é trabalho do gerador, não da Base.

**Ainda não renderizadas.** Os dois arquivos foram validados como YAML e escritos contra a sintaxe
de referência das Bases, mas nenhuma sessão aqui abre o Obsidian: a confirmação de que as views
renderizam depende de o Everton abrir o vault. Se alguma view não aparecer, o suspeito é a fórmula
`limiar` ou o bloco `not:` do filtro de estratégias — ambos isolados de propósito, para que remover
um não derrube a Base inteira.

---

## 4. Os dois canvases

| Arquivo | O que mostra |
|---|---|
| `obsidian/01-ARCHITECTURE/Fluxo sinal → carteira.canvas` | `market-worker → scanner-worker → strategy-worker (Shadow Lab) → ponte → admissão (Risk Engine) → execution-worker → carteira`, cada caixa ligada à página do módulo, com as duas travas desenhadas onde elas estão e o estado real de cada peça (no ar / provado mas não implantado / desligado). |
| `obsidian/03-TRADING/Família momentum.canvas` | a linhagem do `momentum`: `v1` depreciada → `v2` em pesquisa → `v3` paper não ativada, com os EXP que medem cada uma e as irmãs que ainda não existem. |

O canvas da família aponta para páginas de `03-TRADING/Estrategias/`, que são geradas por T3.20. Se
aquele gerador mudar o nome de um arquivo, o nó vira alvo morto — o canvas é o primeiro lugar a
conferir depois de uma mudança no gerador.

---

## 5. O linter

```bash
uv run python infra/scripts/obsidian_lint.py
```

Somente leitura: **nunca conserta nada**. Sai com código 1 quando há achado fora da lista de
conhecidos, e o relatório inteiro é em português. Categorias:

| Categoria | O que pega |
|---|---|
| `links_mortos` | `[[link]]` cujo alvo não existe |
| `links_ambiguos` | nome-base que casa com mais de uma nota (precisa de caminho) |
| `orfas` | nota sem nenhum link de entrada — um neurônio sem sinapse |
| `frontmatter` | chave obrigatória faltando, pela tabela da §1 |
| `valores` | valor fora do vocabulário fechado |
| `kb_procedencia` | nota de `11-KNOWLEDGE` sem `fonte` ou sem `lido_em` |
| `exp_reescrita` | seção `### Avaliação de <data>` já commitada que mudou — **a regra append-only** |

A última é a que protege a pesquisa. Uma avaliação datada é uma leitura de um instante: ela pode ser
**contradita** por uma leitura posterior, nunca corrigida em cima. O linter compara o arquivo com
`git show HEAD:<caminho>` e reprova qualquer seção datada que tenha mudado. Cabeçalhos de gabarito
(`### Avaliação de <próxima data>`) são isentos — são espaço em branco, não medição.

### Como o linter resolve um `[[link]]` (T3.21)

Um linter que só aceitasse o caminho inteiro reprovaria a base que o Obsidian abre sem um único link
quebrado — foi exatamente o que aconteceu na primeira versão (152 falsos positivos). A resolução
segue o Obsidian, nesta ordem:

1. **caminho inteiro** — `[[06-DECISIONS/Dialogos/M3]]` (com ou sem `.md`);
2. **qualquer sufixo de caminho em fronteira de barra** — `[[Dialogos/M3]]` e `[[M3]]` acham
   `06-DECISIONS/Dialogos/M3.md`; `[[gos/M3]]` **não** acha (não é fronteira de barra);
3. se o sufixo casa com mais de um arquivo, é `links_ambiguos`, não morto — o texto precisa de mais
   caminho; se não casa com nenhum, é `links_mortos`.

Duas consequências que valem escrever: **`.base` e `.canvas` entram no índice de alvos** (só pelo
nome com extensão, como no Obsidian: `[[Experimentos.base]]`), mas não são notas — não têm
frontmatter cobrado nem são cobradas como órfãs; e o alias escapado de tabela
(`[[EXP-0001-momentum-v1\|em modo sombra]]`) é lido como alias, porque a barra invertida ali é
sintaxe de tabela e não parte do nome do arquivo.

Duas exceções de pasta, pelo mesmo motivo — a regra tem de descrever a base que existe:
`03-TRADING/Estrategias/README.md` é a convenção do catálogo (T3.20) e não uma página de estratégia,
então não se cobra `strategy` dele; e num `_TEMPLATE-*` a chave vazia é o conteúdo (`fonte:`,
`lido_em:` são o que o autor vai preencher), então se cobra a **presença** da chave, não o valor.

O script está dividido em três arquivos pelo teto de 350 linhas:
`infra/scripts/obsidian_lint.py` (CLI, categorias, relatório), `obsidian_lint_rules.py` (frontmatter,
vocabulário, append-only) e `obsidian_lint_links.py` (descoberta de arquivos, links, órfãs). O teste
é `infra/scripts/tests/test_obsidian_lint.py` (26 casos, sem Docker e sem rede).

Uma nota importante sobre o link morto: ele não é sempre defeito. Achados que são conhecidos e têm
dono são declarados na `ALLOWLIST` do script **com motivo**, aparecem numa seção à parte do relatório
e não derrubam o código de saída. Corrigir um achado de outra tarefa em voo é pior que registrá-lo.
Hoje a `ALLOWLIST` está **vazia**: os oito itens que ela continha eram os `[[Estrategias/README]]`
das páginas de família, que a resolução por sufixo passou a encontrar de verdade. Uma entrada ali é
dívida declarada com motivo, nunca um jeito de calar o linter.

---

## 6. Plantão

Em todo plantão, depois da leitura situacional e antes de escrever o diário:

```bash
uv run python infra/scripts/obsidian_lint.py
```

Consertar o que for da base (link morto, frontmatter, órfã) e **não** consertar o que tiver dono em
outra tarefa — esse vai para a `ALLOWLIST` com motivo, ou para [[Open Bugs]]. Um achado
`exp_reescrita` **nunca** se resolve reescrevendo de volta: ou a alteração foi indevida e se desfaz,
ou ela é uma leitura nova e vira uma seção nova, datada, abaixo.

O resto do turno da base continua como está em `.claude/state/plantao.md`: changelog por commit,
bugs abertos e resolvidos, `status:` das páginas de módulo, o diário do dia e os links `[[...]]` nos
dois sentidos — uma nota que ninguém alcança a partir de outra nota é um neurônio sem sinapse.

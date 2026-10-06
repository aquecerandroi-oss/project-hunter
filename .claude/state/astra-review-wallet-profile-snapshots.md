A regra `known_at < decisão`, com ausência como desconhecido, **não tem look-ahead por si só**. Mas eu fecharia três ambiguidades antes de congelar:

1. **Seleção da foto e falhas.** [Item 7, linhas 505–514](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:505): fixar qual foto anterior usar e se uma falha permite carregar o último sucesso, com qual validade. **Cenário:** ontem havia 20 seguidores; hoje retorna 429. Duas análises igualmente compatíveis com o texto classificam a aposta como “1–99” ou “desconhecido”. Congelar a regra e preservar a referência da foto usada; timeout também precisa de registro, mesmo sem status HTTP.

2. **Seleção pelo teto.** [Linhas 517–519](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:517): “seguidas e controles primeiro” não define desempate, retries nem encerramento. **Cenário:** mais de 3.000 candidatas e falhas no meio da fila deixam cobertura concentrada em certos postos/horários; analisar apenas sucessos atribui essa seleção aos seguidores. Congelar ordem completa, orçamento de tentativas e publicar cobertura/ausências; restringir a conclusão à população observada.

3. **Carteira versus entidade.** A tabela é por carteira, mas a [pergunta é por entidade](C:/dev/project-hunter/obsidian/06-DECISIONS/2026-10-05-carteiras-seguidores-como-pergunta-secundaria.md:28). **Cenário:** entidade com carteiras de 0 e 200 seguidores muda de faixa conforme se escolhe carteira-gatilho, máximo ou soma. Pré-registrar essa regra, inclusive fotos parcialmente ausentes, antes dos resultados.

**Tamanho:** a multiplicação está certa: **0,51 MB/noite; 22,95 MB/45 noites**. Os 170 B são estimativa plausível, não medida: dependem dos tipos, `username` e ocupação das páginas ([PostgreSQL](https://www.postgresql.org/docs/16/storage-page-layout.html)). Retries persistidos também aumentam linhas. Não vejo bloqueio de capacidade nessa ordem de grandeza.

Nenhum arquivo alterado; testes não executados.

**OBSIDIAN**

- **Seguidores entram no H-030 como pergunta secundária** — registrar regras de foto, cobertura e agregação por entidade antes do congelamento.
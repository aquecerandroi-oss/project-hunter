**RESUMO**

**Ainda não congelaria.** Como `quant-engineer`: #1 e #2 estão resolvidos; #3 e #5 melhoraram; #4 e #6 ainda têm lacunas concretas.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Revisão estática. Não executei testes que escrevem arquivos, detecção nem leitura de retornos. As contagens são do artefato fornecido.

**MUST-FIX**

1. **#4 — ausência de vela ainda vira ausência de sinal.** Se a API devolver a série sem a última vela, o detector mantém as bandeiras falsas e registra definitivamente o dia. Quando a vela chegar, o dia não será refeito. **Cenário:** perde-se um B ou altera-se o top-20 por volume incompleto. Exigir cobertura verificada ou ausência justificada antes de concluir o dia. [detect_daily.py:134](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:134), [detect_daily.py:258](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:258).

2. **Novo — CSV truncado pode ser aceito como primeira observação.** `read_archive` ignora `fetched_at` e não valida a integridade da linha. **Cenário:** queda durante a escrita deixa volume `10` em vez de `100`, sem os campos finais; a leitura aceita `10`, e o valor completo passa a ser “revisão”, preservando o errado. Validar esquema, término e valores antes de aceitar/acrescentar; persistência transacional resolve a origem. [archive.py:87](C:/dev/project-hunter/.claude/state/h026b-forward/archive.py:87), [archive.py:94](C:/dev/project-hunter/.claude/state/h026b-forward/archive.py:94).

3. **#6 — o manifesto congela somente o texto.** **Cenário:** alguém altera `geom85.py`, exclusões ou continuidades; o próximo dia passa normalmente, apenas com outro hash no log. Congelar e conferir também código e insumos estáticos; preservar versões das classificações, permitindo acréscimos auditados. Hash registrado não é trava. [detect_daily.py:195](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:195), [detect_daily.py:244](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:244).

4. **#3 — parada dura ausente no detector.** **Cenário:** execução normal em outubro de 2030 continua acrescentando sinais posteriores a 27/09 à mesma coorte. Limitar os dias de sinal; a coleta necessária para maturar saídas deve continuar separadamente. [detect_daily.py:225](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:225), [detect_daily.py:252](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:252).

**NICE-TO-HAVE**

- Trocar “P **não pode** confirmar” por “**não se espera** que alcance o piso”: frequência histórica é projeção, não teto. Corrigir também “foram reconstruídos” para o futuro, pois você informa que nenhuma detecção ocorreu. [PREREG.md:10](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:10), [PREREG.md:12](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:12).
- Acrescentar testes nas fronteiras A em `t−20`/`t−21`, com lacunas de calendário, e de CSV interrompido.

**O QUE EU FARIA DIFERENTE**

Fecharia essas guardas e a política de cobertura antes de iniciar o arquivo prospectivo. Não reabriria o desenho dos contrastes.

**CONCORDO COM**

- **21 velas reais está correto:** B ainda pode ocorrer no prazo `A+20`; incluir `t−20…t` evita contaminar P. `groups_of` implementa o contraste declarado. [geom85.py:164](C:/dev/project-hunter/.claude/state/r85/geom85.py:164), [detect_daily.py:138](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:138), [detect_daily.py:105](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:105).
- Identidade com início do segmento resolve a mudança retrospectiva de `SYM` para `SYM#0`; `O_EXCL` impede duas execuções normais concorrentes. [detect_daily.py:140](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:140), [detect_daily.py:180](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:180).
- Gatilho comum com interpretação associativa, K6 antes da inferência, suporte mínimo, análise única e custos proporcionais explicitamente aproximados estão bem encaminhados. [PREREG.md:11](C:/dev/project-hunter/.claude/state/h026b-forward/PREREG.md:11).

**OBSIDIAN**

- **H-028-forward-prereg** — acrescentar esta segunda rodada e os bloqueios restantes.
- **Fila de Hipóteses** — registrar política de cobertura, congelamento completo e expectativa de amostra sem tratá-la como impossibilidade matemática.
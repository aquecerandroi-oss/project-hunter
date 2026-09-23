**RESUMO**

Os rótulos centrais são defensáveis, mas **H-007 exige ressalva adicional e H-005/H-006 não encerram o teste originalmente pedido**.

- **H-001/H-002:** “não rodou” é estado de execução. Se a coluna exigir um dos três vereditos, use **NÃO CONFIRMA — amostra insuficiente/população vazia** ([regra:67](C:/dev/project-hunter/docs/RESEARCH.md:67)).
- **H-003/H-004:** mantenho **NÃO CONFIRMA**: nenhuma célula satisfaz Holm; H-004 falha no planalto ([H-003:25](C:/dev/project-hunter/.claude/state/r70/H-003.md:25), [H-004:31](C:/dev/project-hunter/.claude/state/r70/H-004.md:31)).
- **H-005/H-006:** **NÃO CONFIRMA no desenho executado**, com desvios que impedem declarar o pré-registo integralmente testado.
- **H-008:** correto **não reportar REFUTA**. A cláusula de invalidação prevalece; “aberta” é status da fila, não quarto veredito ([pré-registo:109](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:109>)).

**ARQUIVOS**

Nenhum criado ou modificado. Sem revisão de código.

**TESTES**

Não executados; conferência documental dos pré-registos e relatórios.

**MUST-FIX**

1. **H-007: explicitar que a refutação pela barra menor é numericamente frágil.** O IC principal termina em **+0,0155 R**, mas o mesmo corte 12 na curva termina em **+0,0205 R**: lados opostos de +0,02 R ([principal:22](C:/dev/project-hunter/.claude/state/r70/H-007.md:22), [curva:39](C:/dev/project-hunter/.claude/state/r70/H-007.md:39)). **Cenário:** encerrar a hipótese usando um IC enquanto outro publicado não satisfaz sua refutação. Preserve o IC decisório congelado; esclareça a discrepância sem escolher posteriormente o resultado conveniente.

2. **H-006: retirar “menor, nunca maior” e não tratar o contraste substituto como teste concluído.** Isso depende da ordenação das médias, não decorre de incluir o tercil intermediário. Neste relatório, alto−baixo dá aproximadamente **+0,23%**, pelas médias arredondadas, contra +0,09% de alto−resto; falta o IC do contraste correto ([tercis:54](C:/dev/project-hunter/.claude/state/r70/H-006.md:54)). **Cenário:** descartar uma hipótese porque outro contraste ficou abaixo do MRE. Se o tercil intermediário rendesse menos que o inferior, a substituição poderia ampliar o efeito.

3. **H-005: distinguir resultado exploratório de cumprimento do pré-registo.** A população exigia envelope; a variável veio de snapshots ([fila:77](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:77>), [relatório:69](C:/dev/project-hunter/.claude/state/r70/H-005.md:69)). **Cenário:** arquivar a hipótese original após medir somente uma população substituta com 51,7% de censura. Não aplicaria automaticamente a ela o teto de 20% exclusivo de H-008.

**NICE-TO-HAVE**

H-006 falha em **seis**, não cinco condições: faltou mencionar o pico ([relatório:30](C:/dev/project-hunter/.claude/state/r70/H-006.md:30)). Em H-004, prefira “só um IC exclui zero” a “o efeito só existe ali”; os vizinhos continuam incertos ([curva:39](C:/dev/project-hunter/.claude/state/r70/H-004.md:39)).

**O QUE EU FARIA DIFERENTE**

Separaria **veredito estatístico**, **validade/aderência ao pré-registo** e **status da fila**.

Os três limites apontados são reais **no funcionamento documentado**, sem auditar implementação:

- Dois limiares distintos comprimidos em um: pode produzir refutação indevida quando o IC superior fica entre ambos ([H-004:10](C:/dev/project-hunter/.claude/state/r70/H-004.md:10)).
- Selecionados×resto responde outra pergunta que tercil×tercil.
- H-008 demonstra que carregar a cláusula escrita não significa aplicá-la ao veredito ([cláusula:9](C:/dev/project-hunter/.claude/state/r70/H-008-snapshot.md:9), [resultado:27](C:/dev/project-hunter/.claude/state/r70/H-008-snapshot.md:27)).

**CONCORDO COM**

**H-007 REFUTA é formalmente legítimo pelo IC principal**, com a ressalva acima. A dispensa é expressamente permitida ([regra:95](C:/dev/project-hunter/docs/RESEARCH.md:95)); a curva é **ausente**, não pico ([H-007:33](C:/dev/project-hunter/.claude/state/r70/H-007.md:33)). O sinal negativo pontual não prova inversão: o IC contém zero. A conclusão é contra uma vantagem ≥+0,02 R, condicionada à validade dos dados, não prova causal de prejuízo.

**OBSIDIAN**

- **Fila de Hipóteses** — separar status/veredito/validade; registrar fragilidade do H-007 e pendências dos contrastes H-005/H-006.
- **Revisões-Astra — R70** — registrar esta revisão documental e os três limites do moinho.
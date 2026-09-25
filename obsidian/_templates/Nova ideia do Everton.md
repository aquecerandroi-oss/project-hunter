<%*
/* Modelo Templater para uma linha em "Ideias do Everton.md" (00-INBOX ou
   11-KNOWLEDGE — a orquestradora decide onde esse arquivo mora quando ele for
   criado; hoje ele ainda não existe no repositório).
   Como usar: abrir (ou criar) "Ideias do Everton.md", ir até o fim, inserir
   este modelo, preencher a ideia numa frase. Uma linha por ideia, mais nova
   embaixo. Todo item nasce "em aberto"; quem move a ideia adiante (vira
   hipótese, vira nota, é descartada) troca o status ali mesmo, não aqui.
*/
-%>
- **<% tp.date.now("DD/MM/YYYY") %>** — <ideia, uma frase, nas palavras do Everton> — status: em aberto

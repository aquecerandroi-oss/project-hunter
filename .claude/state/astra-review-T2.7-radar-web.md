**RESUMO**

Recomendo **manter `/opportunities` como lista de episódios para investigação**, com apresentação mais simples que o Radar. Não redirecionaria automaticamente para um HOT: o destino mudaria entre visitas, esconderia alternativas e precisaria de outro comportamento quando não houvesse HOT.

- **Radar:** comparar oportunidades, filtrar e acompanhar mudanças.
- **Opportunities:** escolher um episódio para entender sua tese; linhas compactas com mercado, direção, score, confiança, status, estágio e última atualização.
- **Detalhe:** explicar aquele episódio e sua evolução.

Isso respeita as duas entradas existentes em [nav-registry.ts](C:/dev/project-hunter/apps/web/lib/nav-registry.ts:69). A lista pode compartilhar componentes visuais com o Radar, usando seu próprio contrato. Sua ordenação atual é **score descendente, desempate por id**, portanto não a rotule “mais recentes”. [repositories/opportunities.py](C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:201)

**ARQUIVOS**

Nenhum criado ou modificado. Análise em modo OPINIÃO, como `frontend-specialist`.

**TESTES**

Não executados; revisão estática. Não consultei o banco para confirmar as tabelas vazias.

**MUST-FIX**

1. **Reconciliar o caminho das features antes de validar volatilidade e volume.** O produtor coloca o vetor em `feature_snapshot.vector`, mas a expressão SQL lê `feature_snapshot.features.values`. Se T2.5 persistir o envelope atual sem transformação, o filtro de volatilidade poderá excluir oportunidades válidas e a ordenação por volume perderá seu significado. Fixtures precisam reproduzir o envelope serializado do produtor. [envelope.py](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/envelope.py:45), [radar_common.py](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_common.py:117)

2. **Não depender exclusivamente de patches realtime.** O gateway descarta mensagens dentro da janela de throttle, aplicada ao canal inteiro. Cenário: A atualiza, B atualiza logo depois; B não chega ao navegador, mesmo conectado. Mantenha reconciliação periódica REST também com WS conectado, além de reconexão e retorno à aba. [endpoint.py](C:/dev/project-hunter/apps/api/hunter_api/realtime/endpoint.py:131), [throttle.py](C:/dev/project-hunter/apps/api/hunter_api/realtime/throttle.py:36)

3. **Resolver as lacunas do contrato do Radar sem fabricar campos.** `RadarItemOut` não traz qualidade nem contagem/tipos de anomalias. Mostrar “OK” ou “0 anomalias” por ausência desses campos produziria informação falsa. Registre a extensão necessária na API; enquanto isso, apresente a ausência explicitamente. O `as_of` da página é horário da consulta, não prova de execução recente do scanner. [schemas/radar.py](C:/dev/project-hunter/apps/api/hunter_api/schemas/radar.py:86), [services/radar.py](C:/dev/project-hunter/apps/api/hunter_api/services/radar.py:105)

4. **Separar evidência da avaliação e contexto atual.** As anomalias do detalhe são consultadas pelo mercado e pelo status ativo **no momento da leitura**. Podem ter surgido depois do score exibido. Rotule-as “Anomalias ativas agora”; use a decomposição persistida para explicar quais sustentaram a avaliação. Da mesma forma, não substitua o regime do snapshot pelo regime atual do dashboard. [repositories/opportunities.py](C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:315), [envelope.py](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/envelope.py:48)

5. **Preservar as semânticas dos estados e totais.** `HOT + RISK_BLOCKED` significa **OU**, podendo incluir todas as linhas da organização bloqueada; a UI não pode apresentar isso como “HOT bloqueadas”. `risk_blocked=false` não significa aprovação do Risk Engine. E `items.length` de uma página não é total global para tiles. [repositories/radar.py](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:122), [repositories/radar.py](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:181), [schemas/radar.py](C:/dev/project-hunter/apps/api/hunter_api/schemas/radar.py:14), [schemas/common.py](C:/dev/project-hunter/apps/api/hunter_api/schemas/common.py:21)

**NICE-TO-HAVE**

- Link “Explorar no Radar”, preservando somente filtros compatíveis.
- Preservar filtros na URL e foco pelo identificador do episódio.
- Histórico rotulado “Últimas N amostras”, com intervalo temporal visível; sparkline sem interpolação que sugira medições inexistentes.
- Testes específicos para mensagens perdidas, duplicadas, fora de ordem, troca de organização e respostas REST atrasadas.

**O QUE EU FARIA DIFERENTE**

A ordem do painel seria:

1. **Resumo:** mercado, score/direção, confiança, status, horário da avaliação e `explanation.resumo`. Alertas de indisponibilidade ficam aqui, visíveis.
2. **Componentes:** contribuição decrescente, com peso, normalizado, direção e confiança. Indisponíveis continuam visíveis com motivo. Exibir o ajuste assinado de **Early Movement junto da composição do score**, para a soma ficar compreensível. Esses valores já vêm separados no contrato. [model.py](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/model.py:201), [model.py](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/model.py:233)
3. **Estágio e regime:** contexto compacto, com detalhes expansíveis. `state_in/out` está no envelope; o snapshot usa `regime_stale`, enquanto o endpoint de regime usa `is_stale`. Tratar também estágio `NONE`. [envelope.py](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/envelope.py:49), [schemas/regime.py](C:/dev/project-hunter/apps/api/hunter_api/schemas/regime.py:35), [enums.py](C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:396)
4. **Anomalias ativas agora:** status e `evaluation_state` independentes; `unknown` nunca vira resolvido.
5. **Histórico do score:** sparkline e lista; envelope carregado sob demanda, com `history_limit<=50`. [routers/opportunities.py](C:/dev/project-hunter/apps/api/hunter_api/routers/opportunities.py:69)
6. **Features do snapshot:** tabela compacta expansível, com valor, qualidade e motivo.
7. **Rodapé técnico:** baselines, versões e proveniência, colapsado.

Preservaria os textos de `explanation.frases[].texto`, agrupando-os nas seções correspondentes. A explicação é um objeto estruturado, com `resumo`, `frases` e versão. [explanation.py](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/explanation.py:237)

Para realtime, documentaria este **contrato provisório proposto**, ainda sem garantia do produtor:

```ts
type RadarPatchV1 = {
  schema_version: 1;
  type: "radar.patch";
  opportunity_id: string;
  base_last_updated_at: string; // UTC; versão-base exigida
  last_updated_at: string;      // UTC; nova versão
  patch: Partial<Pick<RadarItemOut,
    | "score" | "confidence" | "peak_score"
    | "direction" | "status" | "stage"
    | "regime" | "change" | "below_40_since"
  >>;
};
```

Regras do merge:

- Aplicar somente à linha conhecida cuja versão corresponda à base; versão nova deve avançar. **Isso exige timestamps por episódio estritamente crescentes, a confirmar com T2.5**; sem essa garantia, usar o evento apenas para invalidar.
- Campos ausentes preservam valores; `null` explícito limpa campos anuláveis. Decimais continuam strings.
- Validar payload em runtime. Identificador desconhecido, base divergente ou versão desconhecida → refetch.
- Nunca transportar `in_position`, `risk_blocked` ou motivo nesse canal global. Esses campos ficam associados à organização da consulta REST. [channels.py](C:/dev/project-hunter/apps/api/hunter_api/realtime/channels.py:3)
- Após patch, reconciliar filtros/ranking no servidor. Não inserir linha incompleta nem recalcular cursor no navegador. Mudança de filtros/ordenação reinicia a paginação.
- Decodificar o transporte existente: o gateway envia `{channel, data}`, com `data` contendo JSON como string. [endpoint.py](C:/dev/project-hunter/apps/api/hunter_api/realtime/endpoint.py:140)

**Minha preferência para T2.7 é começar por invalidação REST agrupada; adicionar esse merge como antecipação visual quando o contrato do produtor estiver confirmado.**

**CONCORDO COM**

Duas entradas de navegação, explicação persistida, detalhes técnicos colapsados e fixtures somente em testes. A validação com dados produzidos por T2.5 deve permanecer uma pendência explícita.

**OBSIDIAN**

- **System Overview** — registrar a finalidade de Radar, lista de oportunidades e detalhe.
- **WebSockets** — documentar descarte pelo throttle, reconciliação REST e contrato provisório.
- **Features (Feature Engine)** — registrar a divergência `vector`/`features` e o contrato reconciliado.
- **Anomalies (Anomaly Engine)** — distinguir evidência persistida de anomalias ativas na leitura.
- **Revisoes-Astra/Index** — vincular esta opinião sobre T2.7 e suas pendências de integração.
---
name: deploy-vps-comando-completo
description: o deploy da VPS precisa das flags de perfil; sem elas só api/web atualizam e os robôs de perfil ficam na imagem velha ou rodam como se estivessem sozinhos
metadata:
  type: feedback
---

O único comando de deploy da VPS (Everton roda; o classificador nega à sessão):

```
ssh hunter-vps "cd /opt/project-hunter && MARKET_SPOT=1 MARKET_SHARDS=4 STRATEGY_SHARDS=4 MEME=1 MEME_ENABLED=true MEME_LIVE=1 nohup bash infra/vps/compose.sh update > /tmp/deploy-last.log 2>&1 &"
```

Por quê: `infra/vps/compose.sh` escolhe os perfis do compose por variável de ambiente (nada vem do `.env`).
Em 30/09/2026 a Sexta-feira passou `compose.sh update` puro: só `api`/`web`/workers sem perfil
foram recriados; `meme-executor` (perfil `meme-live`), `meme-worker`, shards de mercado/estratégia e
`market-worker-spot` ficaram na imagem anterior, e `market-worker-1`/`strategy-worker-1` subiram
com `*_SHARDS=1` ao lado dos shards antigos (trabalho duplicado). Sem `MEME_LIVE=1` o executor fica
parado na imagem velha; `--remove-orphans` não o derruba porque o serviço existe num perfil inativo.
Depois de todo deploy: conferir `docker inspect <container> --format '{{.Config.Image}}'` do
`hunter-meme-executor-1` e de um shard = `hunter-api:<sha do HEAD>`.

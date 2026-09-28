"""R84 — nice-to-have da Astra: nas 21 migrações não ligadas, o ticker novo entrou no top-20 nas 10 primeiras semanas
em que já teria idade (≥ 35 d)? Se não, reiniciar a idade não mudou o universo. Só volume/datas."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyze import mondays  # noqa: E402
from config import AS_OF_DAY, EXCLUDED, LAST_T_DAY, LINKS, apply_links, day_iso, load_rows, trading_symbols  # noqa: E402
from engine import week  # noqa: E402
from gaps import KEEP_TOGETHER  # noqa: E402
from panel import build_panel  # noqa: E402

rows, trading = apply_links(load_rows(), set(trading_symbols()))
p = build_panel(rows, trading, EXCLUDED, AS_OF_DAY, keep_together=KEEP_TOGETHER)
ts = mondays(p, LAST_T_DAY)
cat = json.loads((Path(__file__).parent / "cache" / "all_assets.json").read_text(encoding="utf-8"))["data"]
linked = {o for o, _, _ in LINKS}
mig = sorted({(a["oldAssetCode"] + "USDT", a["newAssetCode"] + "USDT") for a in cat
              if a.get("oldAssetCode") and a.get("newAssetCode") and a["oldAssetCode"] != a["newAssetCode"]})
for old, new in mig:
    if old in linked or new not in p.ids:
        continue
    i = p.ids.index(new)
    win = [t for t in ts if p.first[i] + 36 <= t <= p.first[i] + 36 + 70]
    hit = [day_iso(p.day0 + t) for t in win if i in week(p, t, 14).top_ids]
    print(f"{old} → {new}: 1.ª vela {day_iso(p.day0 + p.first[i])}; top-20 nas 10 semanas após idade 35 d: {hit or 'não'}")

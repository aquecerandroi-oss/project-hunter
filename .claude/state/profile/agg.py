import sys, collections
path = sys.argv[1]
self_c = collections.Counter(); tot_c = collections.Counter(); total = 0
for line in open(path, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if not line.strip(): continue
    stack, _, cnt = line.rpartition(" ")
    try: n = int(cnt)
    except ValueError: continue
    frames = stack.split(";")
    total += n
    self_c[frames[-1]] += n
    for f in set(frames): tot_c[f] += n
print(f"TOTAL SAMPLES: {total}\n")
print("== TOP 25 BY SELF TIME ==")
for f, n in self_c.most_common(25): print(f"{100*n/total:6.2f}%  {n:6d}  {f}")
print("\n== TOP 30 BY CUMULATIVE (any frame on stack) ==")
for f, n in tot_c.most_common(40):
    if any(k in f for k in ("base_events","runners.py","events.py:88","runpy","__main__","tasks.py","connection.py:190","run_forever")): continue
    print(f"{100*n/total:6.2f}%  {n:6d}  {f}")

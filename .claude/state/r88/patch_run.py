from pathlib import Path
p = Path("run88.py"); s = p.read_text(encoding="utf-8")
old = '''    for name, flag in (
        ("golpe (saída creator_dump)", [r.get("exit_reason") == "creator_dump" for r in closed]),
        ("perda ≥ 50 % (measured)", [r["cls"] == "measured" and float(r["y"]) <= -0.5 for r in closed]),
        ("indeterminate", [r["cls"] == "indeterminate" for r in closed]),
    ):
        x = np.array(flag, float)
'''
new = '''    meas = np.array([r["cls"] == "measured" for r in closed])
    for name, flag, base in (
        ("golpe (saída creator_dump), fechadas", [r.get("exit_reason") == "creator_dump" for r in closed], None),
        ("perda ≥ 50 %, só measured (correção Astra: denominador = measured)",
         [r["cls"] == "measured" and float(r["y"]) <= -0.5 for r in closed], meas),
        ("indeterminate, fechadas", [r["cls"] == "indeterminate" for r in closed], None),
    ):
        x = np.array(flag, float)
        if base is not None:  # restringe ao denominador declarado
            closed_b = [r for r, b in zip(closed, base) if b]
            x = x[base]
            hi_b, inv_b = hi[base], inv[base]
        else:
            closed_b, hi_b, inv_b = closed, hi, inv
        hi, inv, hi_all, inv_all = hi_b, inv_b, hi, inv
'''
assert old in s; s = s.replace(old, new)
old2 = '''        print(f"  {name}: alto {int(x[hi].sum())}/{int(hi.sum())} = {100*r_hi:.1f}% · baixo {int(x[~hi].sum())}/"
              f"{int((~hi).sum())} = {100*r_lo:.1f}% · razão {ratio:.2f}× · alto − baixo {100*(r_hi-r_lo):+.1f} pp "
              f"IC mint [{100*lo:+.1f}; {100*up:+.1f}]")
'''
new2 = old2 + '''        hi, inv = hi_all, inv_all
'''
assert old2 in s; s = s.replace(old2, new2)
old3 = '''        nc = [r for r in rm if r.get("is_creator") != "true"]
        un = to_units(nc, THR[m])'''
new3 = '''        if m == "A":
            print("[A] sem criador como maior comprador: não avaliável (o pedigree_e2b não grava is_creator)")
            continue
        nc = [r for r in rm if r.get("is_creator") == "false"]
        un = to_units(nc, THR[m])'''
assert old3 in s; s = s.replace(old3, new3)
p.write_text(s, encoding="utf-8")
print("ok")

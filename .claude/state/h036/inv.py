import csv, gzip, collections
rows = list(csv.DictReader(gzip.open('.claude/state/lab-cost-sweep/cache/out.csv.gz', 'rt', encoding='utf-8')))
c = collections.Counter((r['strategy'], r['version'], r['cohort'], r['mt']) for r in rows if r['strategy'] in ('mean_reversion', 'momentum'))
for k, v in sorted(c.items()):
    if k[2] == 'prospective': print(k, v)
print('max exit', max(r['exit_ts'] for r in rows), 'max emitted', max(r['emitted_at'] for r in rows))

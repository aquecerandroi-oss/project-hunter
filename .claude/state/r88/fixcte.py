import re
s=open('q_avail1.sql',encoding='utf-8').read()
m=re.search(r"CREATE TEMP TABLE e2b AS\n(.*?);\n",s,re.S)
if m:
    cte="WITH e2b AS (\n"+m.group(1)+"\n)\n"
    s=s.replace(m.group(0),"")
    s="\n".join((cte+l) if l.startswith("SELECT") else l for l in s.split("\n"))
    open('q_avail1.sql','w',encoding='utf-8').write(s)

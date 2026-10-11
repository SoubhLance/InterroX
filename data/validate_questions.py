import json, os, sys, collections
D = os.path.dirname(os.path.abspath(__file__))
TRACKS = {"ml_ai":"ML","swe":"SWE","backend":"BE","fullstack":"FS","hr":"HR"}
KEYS = {"id":str,"track":str,"topic":str,"difficulty":str,"stretch":bool,"question":str,
        "ideal_answer":str,"key_points":list,"red_flags":list,"follow_ups":list,"tags":list}
errs=[]; seen_ids=set(); seen_q=set()
for track,prefix in TRACKS.items():
    data=json.load(open(os.path.join(D,track+".json"),encoding="utf-8"))
    diff=collections.Counter(); topics=collections.Counter()
    for i,x in enumerate(data,1):
        exp=f"{prefix}-{i:03d}"
        if x.get("id")!=exp: errs.append(f"{track}: expected {exp}, got {x.get('id')}")
        if x["id"] in seen_ids: errs.append(f"dup id {x['id']}")
        seen_ids.add(x["id"])
        if set(x)!=set(KEYS): errs.append(f"{x['id']}: keys mismatch {set(x)^set(KEYS)}")
        for k,t in KEYS.items():
            if k in x and not isinstance(x[k],t): errs.append(f"{x['id']}: {k} wrong type")
        if x["track"]!=track: errs.append(f"{x['id']}: wrong track")
        if x["difficulty"] not in ("easy","medium","hard"): errs.append(f"{x['id']}: bad difficulty")
        if not 3<=len(x["key_points"])<=5: errs.append(f"{x['id']}: key_points count")
        if len(x["red_flags"])<1: errs.append(f"{x['id']}: red_flags empty")
        if len(x["follow_ups"])!=2: errs.append(f"{x['id']}: follow_ups != 2")
        if any(t!=t.lower() for t in x["tags"]): errs.append(f"{x['id']}: uppercase tag")
        blob=json.dumps(x,ensure_ascii=False)
        if "`" in blob or "**" in blob: errs.append(f"{x['id']}: markdown/backtick left")
        q=x["question"].strip().lower()
        if q in seen_q: errs.append(f"{x['id']}: duplicate question")
        seen_q.add(q)
        diff[x["difficulty"]]+=1; topics[x["topic"]]+=1
    print(f"{track}: {len(data)} q | {dict(diff)} | stretch={sum(x['stretch'] for x in data)} | topics={len(topics)}")
if errs:
    print("FAILED"); [print(" -",e) for e in errs]; sys.exit(1)
print("OK: all files valid")

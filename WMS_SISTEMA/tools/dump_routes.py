import json
import web_app

routes = []
for r in sorted(web_app.app.url_map.iter_rules(), key=lambda x: x.rule):
    methods = sorted([m for m in r.methods if m not in ('HEAD','OPTIONS')])
    routes.append({'rule': r.rule, 'endpoint': r.endpoint, 'methods': methods})
print(json.dumps({'routes': routes}, indent=2, ensure_ascii=False))

import importlib, sys, json
sys.path.insert(0, 'WMS_SISTEMA')
import web_app as w
importlib.reload(w)
res = w._build_envio_label_data('10123554', '', '', '', 'test')
print(json.dumps(res, indent=2, ensure_ascii=False))

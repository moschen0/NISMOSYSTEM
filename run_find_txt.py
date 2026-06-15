from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'OPTO_INTEGRATIONS'))
import parser_siou as ps
order='10123554'
# AGEVIEW path (same as configured in integrador_opto)
ageview_path = Path(r"\\192.168.1.210\SIOU\ImpOs\AgeViewBKP")
paths=[Path(ps.PATH_OS_SIOU), ageview_path]
for p in paths:
    print('Procurando em', p)
    if not Path(p).exists():
        print('  Não existe')
        continue
    matches=list(Path(p).rglob(f"{order}.txt"))
    print('  Encontrados:', len(matches))
    for m in matches[:5]:
        print('   ', m)

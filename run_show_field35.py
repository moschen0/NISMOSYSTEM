from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'OPTO_INTEGRATIONS'))
import parser_siou
order='10123554'
paths=[Path(parser_siou.PATH_OS_SIOU), Path(r"\\192.168.1.210\SIOU\ImpOs\AgeViewBKP")]
for p in paths:
    print('Procurando em', p)
    if not Path(p).exists():
        print('  Não existe')
        continue
    matches=list(Path(p).rglob(f"{order}.txt"))
    print('  Encontrados:', len(matches))
    for m in matches:
        print('   ', m)
        try:
            raw = m.read_text(encoding='utf-8', errors='replace').strip()
            fields = raw.split(',')
            print('    campo35:', fields[35] if len(fields)>35 else '(não existe)')
        except Exception as e:
            print('    erro ao ler:', e)

"""Actualiza la sección "Costo por PAX, evolución mensual por experiencia" del dashboard.

Lee la hoja mensual (CSV publicado del Google Sheet) y escribe, para el mes indicado,
el costo por pax, la venta por pax, los pax y el desglose de costos de cada tour
en TOUR_DATA y TOUR_BREAKDOWN de dashboard.html. Es idempotente: si el mes ya existe
lo reemplaza. Corre esto cada vez que se cargue un mes nuevo.

Uso:
    python3 tools/actualizar_costos_tour.py Sep-26 datos/SEPTIEMBRE_2026.csv [Oct-26 datos/OCTUBRE_2026.csv ...]
"""
import csv, json, re, sys
from pathlib import Path

DASH = Path(__file__).resolve().parent.parent / 'dashboard.html'

BLOCK_KEY = {
    'XOCHIMILCO - FRIDA': 'XOCHIMILCO',
    'XOCHIMILCO': 'XOCHI_CR',
    'PIRAMIDES TEOTIHUACAN': 'PIRAMIDES',
    'BOLETOS - FRIDA': 'BOLETOS',
    'TELEFERICO & CASTILLO DE CHAPULTEPEC': 'TELEFERICO',
    'LUCHA LIBRE': 'LUCHA',
    'EXPERIENCIA CULINARIA - FRIDA KAHLO': 'EXP_CULINARIA',
    'GARIBALDI': 'GARIBALDI',
    'GLOBO TEOTIHUACAN': 'GLOBO',
}
COMP_NAME = {'B. FRIDA': 'COSTO BOLETO FRIDA', 'UBER  / CAMIONETA': 'CAMIONETA', 'REFRESCOS Y BOTANAS': 'REFRESCOS'}
NOT_COST = {'PAX', 'VENTA', 'TOTAL GASTO', 'TOTAL', 'ECUADOR', 'PROPINA', 'PORCENTAJE'}


def num(x):
    x = (x or '').strip().replace('$', '').replace(',', '').replace(' ', '')
    if x in ('', '-'):
        return 0.0
    neg = x.startswith('-') or x.startswith('(')
    try:
        v = float(x.strip('-()'))
    except ValueError:
        return 0.0
    return -v if neg else v


def blocks(path):
    R = list(csv.reader(open(path, encoding='utf-8')))
    out = {}
    for i, r in enumerate(R):
        for j, c in enumerate(r):
            if c.strip() != 'FECHA' or j + 1 >= len(r) or r[j + 1].strip() != 'PAX':
                continue
            title = ''
            for k in range(i - 1, max(i - 4, -1), -1):
                for jj in range(j, min(j + 15, len(R[k]))):
                    t = R[k][jj].strip()
                    if t and t.isupper() and not re.match(r'^[\d$.,\- ]+$', t):
                        title = t
                        break
                if title:
                    break
            hdr = []
            for jj in range(j, len(r)):
                h = r[jj].strip()
                if not h:
                    break
                hdr.append(h)
                if h == 'PORCENTAJE':
                    break
            for k in range(i + 1, len(R)):
                if j < len(R[k]) and R[k][j].strip() == 'TOTAL':
                    out[title] = {hdr[q]: num(R[k][j + q]) if j + q < len(R[k]) else 0.0 for q in range(1, len(hdr))}
                    break
    return out


def main(pairs):
    s = DASH.read_text(encoding='utf-8')
    M = re.findall(r"'([A-Z][a-z]{2}-\d\d)'", re.search(r'const M = \[([^\]]*)\]', s).group(1))
    tb_m = re.search(r'const TOUR_BREAKDOWN = (\{.*?\});\n', s)
    TB = json.loads(tb_m.group(1))
    td_lines = {k: re.search(r"TOUR_DATA\['%s'\]\s*=\s*\{.*?\};" % k, s).group(0) for k in BLOCK_KEY.values()}
    TD = {}
    for k, line in td_lines.items():
        TD[k] = {f: json.loads(re.search(r'%s:(\[[^\]]*\])' % f, line).group(1)) for f in ('costs', 'ventas', 'pax')}
    for label, path in pairs:
        if label not in M:
            sys.exit(f'{label} no está en M del dashboard; carga primero el mes en las series principales.')
        idx = M.index(label)
        found = blocks(path)
        for title, key in BLOCK_KEY.items():
            T = found.get(title)
            for f in TD[key]:
                arr = TD[key][f]
                while len(arr) < len(M):
                    arr.append(0 if f == 'pax' else None)
            pax = int(T['PAX']) if T and T.get('PAX') else 0
            if not pax:
                TD[key]['costs'][idx] = None; TD[key]['ventas'][idx] = None; TD[key]['pax'][idx] = 0
                TB.get(key, {}).pop(label, None)
                continue
            costo = T.get('TOTAL GASTO') or T.get('B. FRIDA', 0)
            TD[key]['costs'][idx] = round(costo / pax)
            TD[key]['ventas'][idx] = round(T['VENTA'] / pax) if T.get('VENTA') else None
            TD[key]['pax'][idx] = pax
            comps = {COMP_NAME.get(n, n): round(v / pax) for n, v in T.items() if n not in NOT_COST and v and round(v / pax)}
            TB.setdefault(key, {})[label] = {'pax': pax, 'components': comps}
            print(f'{label} {key:14} pax {pax:5}  costo/pax ${TD[key]["costs"][idx]:,}  venta/pax {TD[key]["ventas"][idx]}')
    for k, line in td_lines.items():
        new = line
        for f in ('costs', 'ventas', 'pax'):
            new = re.sub(r'%s:\[[^\]]*\]' % f, f + ':' + json.dumps(TD[k][f], separators=(',', ':')), new, count=1)
        s = s.replace(line, new)
    TBs = {k: dict(sorted(v.items(), key=lambda kv: M.index(kv[0]) if kv[0] in M else 999)) for k, v in TB.items()}
    tb_now = re.search(r'const TOUR_BREAKDOWN = (\{.*?\});\n', s)
    s = s[:tb_now.start(1)] + json.dumps(TBs, ensure_ascii=False, separators=(',', ':')) + s[tb_now.end(1):]
    DASH.write_text(s, encoding='utf-8')


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or len(a) % 2:
        sys.exit(__doc__)
    main(list(zip(a[::2], a[1::2])))

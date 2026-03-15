#!/usr/bin/env python3
"""
Infofase Apple Catalog Updater
- Downloads Tarifas_Lois.xlsx every 1.5 hours via GitHub Actions
- Filters Apple products, applies pricing formula
- Updates stock, prices, products in index.html
"""

import requests, pandas as pd, json, re, io, os, sys
from datetime import datetime, timezone

XLSX_URL   = "https://infofase.com/tienda/tarifas/Tarifas_Lois.xlsx"
STATE_FILE = "catalog_state.json"
HTML_FILE  = "index.html"

def download_excel():
    print(f"[{datetime.now()}] Downloading {XLSX_URL}...")
    r = requests.get(XLSX_URL, timeout=30)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content))
    apple = df[df['marca'].str.lower().str.strip() == 'apple'].copy().reset_index(drop=True)
    for col in ['stock', 'viajando', 'precio', 'dto', 'canon']:
        apple[col] = pd.to_numeric(apple[col], errors='coerce').fillna(0)
    print(f"  Apple products found: {len(apple)}")
    return apple

def calc_price(precio, dto, canon):
    return round(((precio * (1 - dto / 100)) * 1.10 * 0.96 + canon) * 1.07, 2)

def categorize(pn, desc, orig_cat):
    d = desc.lower()
    o = orig_cat.lower().strip()
    if o == 'teclado' and 'funda' in d and 'ipad' in d:
        if 'ipad pro' in d: return 'Fundas iPad', 'iPad Pro'
        if 'ipad air' in d: return 'Fundas iPad', 'iPad Air'
        return 'Fundas iPad', 'iPad'
    if o == 'teclado' and 'ipad' not in d: return 'Teclados y Ratones', 'Magic Keyboard'
    if o == 'raton' or (o == 'accesorio' and any(x in d for x in ['raton','trackpad','mouse'])):
        return 'Teclados y Ratones', 'Magic Mouse/Trackpad'
    if o == 'accesorio' and 'pencil' in d: return 'Apple Pencil', 'Repuestos'
    if o == 'cable' or o == 'regrabador': return 'Cables', None
    if o == 'adaptador': return 'Adaptadores', None
    if o in ['cargador','power bank']: return 'Cargadores', None
    if o == 'funda' or (('funda' in d or 'carcasa' in d) and 'teclado' not in d):
        if 'iphone' in d:
            for m in ['17 pro max','17 pro','17e','17 air','17','16 pro max','16 pro',
                      '16 plus','16e','16','15 pro max','15 pro','15 plus','15',
                      '14 pro max','14 pro','14 plus','14','13 mini','13','12','11']:
                if f'iphone {m}' in d: return 'Fundas iPhone', f'iPhone {m.title()}'
            return 'Fundas iPhone', 'Otros'
        if 'ipad pro' in d: return 'Fundas iPad', 'iPad Pro'
        if 'ipad air' in d: return 'Fundas iPad', 'iPad Air'
        if 'ipad mini' in d: return 'Fundas iPad', 'iPad mini'
        if 'ipad' in d: return 'Fundas iPad', 'iPad'
        return 'Fundas iPhone', 'Otros'
    if o in ['iphone','0195950663730']:
        for m in ['17 pro max','17 pro','17e','17 air','17','16 pro max','16 pro',
                  '16 plus','16e','16','15 pro max','15 pro','15 plus','15',
                  '14 pro max','14 pro','14 plus','14','13 mini','13','12','11']:
            if f'iphone {m}' in d: return 'iPhone', f'iPhone {m.title()}'
        if 'iphone air' in d: return 'iPhone', 'iPhone Air'
        return 'iPhone', 'iPhone'
    if o in ['ipad','ipad mini']:
        if 'ipad pro' in d:
            chip = 'M5' if 'm5' in d else 'M4' if 'm4' in d else 'M3' if 'm3' in d else ''
            return 'iPad', 'iPad Pro' + (' ' + chip if chip else '')
        if 'ipad air' in d:
            chip = 'M4' if 'm4' in d else 'M3' if 'm3' in d else 'M2' if 'm2' in d else ''
            return 'iPad', 'iPad Air' + (' ' + chip if chip else '')
        if 'ipad mini' in d: return 'iPad', 'iPad mini'
        if 'a16' in d: return 'iPad', 'iPad A16'
        if '10.9' in d or 'decima' in d: return 'iPad', 'iPad (10ª gen)'
        return 'iPad', 'iPad'
    if o == 'macbook':
        if 'macbook neo' in d: return 'MacBook', 'MacBook Neo'
        if 'macbook pro' in d:
            sz = '16"' if '16' in d else '14"'
            chip = ('M5 Max' if 'm5 max' in d else 'M5 Pro' if 'm5 pro' in d else 'M5' if 'm5' in d else
                    'M4 Max' if 'm4 max' in d else 'M4 Pro' if 'm4 pro' in d else 'M4' if 'm4' in d else
                    'M3 Max' if 'm3 max' in d else 'M3 Pro' if 'm3 pro' in d else 'M3' if 'm3' in d else '')
            return 'MacBook', f'MacBook Pro {sz}' + (' ' + chip if chip else '')
        if 'macbook air' in d:
            sz = '15"' if '15' in d else '13"'
            chip = ('M5' if 'm5' in d else 'M4' if 'm4' in d else
                    'M3' if 'm3' in d else 'M2' if 'm2' in d else '')
            return 'MacBook', f'MacBook Air {sz}' + (' ' + chip if chip else '')
        return 'MacBook', 'MacBook'
    if o == 'imac':
        if 'mac studio' in d:
            chip = ('M4 Max' if 'm4 max' in d else 'M4' if 'm4' in d else
                    'M3 Ultra' if 'm3 ultra' in d else 'M3' if 'm3' in d else
                    'M2 Max' if 'm2 max' in d else 'M2' if 'm2' in d else '')
            return 'Mac Studio', 'Mac Studio' + (' ' + chip if chip else '')
        chip = 'M4' if 'm4' in d else 'M3' if 'm3' in d else ''
        return 'iMac', 'iMac' + (' ' + chip if chip else '')
    if o == 'macmini':
        chip = 'M4 Pro' if 'm4 pro' in d else 'M4' if 'm4' in d else ''
        return 'Mac mini', 'Mac mini' + (' ' + chip if chip else '')
    if o == 'watch':
        if 'ultra' in d: return 'Apple Watch', 'Watch Ultra'
        if 'series 11' in d or 'serie 11' in d: return 'Apple Watch', 'Watch Series 11'
        if 'series 10' in d or 'serie 10' in d: return 'Apple Watch', 'Watch Series 10'
        if 'series 9' in d or 'serie 9' in d: return 'Apple Watch', 'Watch Series 9'
        if 'series 8' in d or 'serie 8' in d: return 'Apple Watch', 'Watch Series 8'
        if ' se ' in d or d.endswith(' se') or 'serie se' in d: return 'Apple Watch', 'Watch SE'
        return 'Apple Watch', 'Apple Watch'
    if o == 'auricular':
        if 'airpods max' in d: return 'AirPods', 'AirPods Max'
        if 'airpods pro' in d: return 'AirPods', 'AirPods Pro'
        if 'airpods 4' in d: return 'AirPods', 'AirPods 4'
        if 'airpods' in d: return 'AirPods', 'AirPods'
        return 'AirPods', 'EarPods'
    if o == 'altavoz': return 'HomePod', 'HomePod mini' if 'mini' in d else 'HomePod'
    if o == 'monitor': return 'Monitores', 'Studio Display'
    if o == 'airtag': return 'AirTag', 'AirTag'
    if o == 'appletv': return 'Apple TV', 'Apple TV'
    if o == 'pencil': return 'Apple Pencil', 'Apple Pencil'
    if o == 'applecare': return 'AppleCare+', 'AppleCare+'
    return None, None

def parse_attrs(desc, cat):
    attrs = {}
    d = desc.lower()
    color_map = [
        ('negro azabache','Negro Azabache'),('negro espacial','Negro Espacial'),
        ('gris espacial','Gris Espacial'),('medianoche','Medianoche'),
        ('blanco estrella','Blanco Estrella'),('azul cielo','Azul Cielo'),
        ('titanio natural','Titanio Natural'),('titanio negro','Titanio Negro'),
        ('titanio','Titanio'),('oro rosa','Oro Rosa'),('plata','Plata'),
        ('negro','Negro'),('blanco','Blanco'),('azul','Azul'),('purpura','Púrpura'),
        ('verde salvia','Verde Salvia'),('verde','Verde'),('rosa','Rosa'),
        ('amarillo neon','Amarillo Neón'),('amarillo','Amarillo'),('rojo','Rojo'),
        ('naranja','Naranja'),('siena','Siena'),('lila','Lila'),('gris','Gris'),
    ]
    for k, v in color_map:
        if k in d: attrs['color'] = v; break
    m = re.search(r'(\d+)\s*tb\b', d)
    if m: attrs['storage'] = m.group(1) + 'TB'
    if 'storage' not in attrs:
        for m2 in re.finditer(r'(\d+)\s*gb\b', d):
            if int(m2.group(1)) in [64, 128, 256, 512]:
                attrs['storage'] = m2.group(1) + 'GB'; break
    m = re.search(r'(\d+)\s*gb\s+(?:de\s+)?memoria', d)
    if m and int(m.group(1)) in [8,16,24,32,36,48,64,96,128]:
        attrs['ram'] = m.group(1) + 'GB'
    m = re.search(r"([\d]+[.,][\d]+)['\"]", d)
    if m:
        v = float(m.group(1).replace(',', '.'))
        if 4 <= v <= 32: attrs['screen'] = m.group(1).replace(',', '.') + '"'
    for chip in ['m5 max','m5 pro','m5','m4 max','m4 pro','m4','m3 ultra','m3 max',
                 'm3 pro','m3','m2 ultra','m2 max','m2 pro','m2',
                 'a18 pro','a18','a17 pro','a17','a16','a15']:
        if chip in d: attrs['chip'] = 'Chip ' + chip.upper(); break
    if 'wifi + cellular' in d or 'gps + cellular' in d:
        attrs['connectivity'] = 'WiFi + Cellular'
    elif 'wifi' in d or 'gps' in d:
        attrs['connectivity'] = 'Solo WiFi/GPS'
    if cat == 'Apple Watch':
        m = re.search(r'(\d{2})\s*mm', d)
        if m: attrs['size'] = m.group(1) + 'mm'
        if 'talla s/m' in d: attrs['band_size'] = 'S/M'
        elif 'talla m/l' in d: attrs['band_size'] = 'M/L'
        for k in ['chip', 'ram', 'storage']: attrs.pop(k, None)
    if cat == 'Fundas iPad':
        attrs['tipo_funda'] = 'Funda + Teclado' if 'teclado' in d else 'Solo Funda'
    return attrs

def build_products(apple_df):
    products = []
    for _, r in apple_df.iterrows():
        pn   = str(r['codigo']).strip()
        desc = str(r['denominacion']).strip()
        orig = str(r['producto']).strip()
        cat, sub = categorize(pn, desc, orig)
        if not cat: continue
        price = calc_price(float(r['precio']), float(r['dto']), float(r['canon']))
        s = int(r['stock']); v = int(r['viajando'])
        status = 'stock' if s > 0 else ('transito' if v > 0 else 'agotado')
        products.append({
            'id': pn, 'name': desc.title(), 'price': price,
            'cat': cat, 'sub': sub or cat,
            'status': status, 'stock': s, 'transit': v,
            'img': pn.lower().replace('/', '_') + '.jpg',
            'attrs': parse_attrs(desc, cat),
        })
    return products

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'last_change': None, 'last_run': None, 'product_ids': [], 'cats': [], 'fingerprint': []}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def patch_html(products):
    with open(HTML_FILE, encoding='utf-8') as f:
        html = f.read()
    new_all = 'const ALL = ' + json.dumps(products, ensure_ascii=False) + ';'
    html = re.sub(r'const ALL\s*=\s*\[.*?\];', new_all, html, flags=re.DOTALL)
    html = html.replace('<small> sin IVA</small>', '')
    html = re.sub(r'<script data-cfasync="false" src="/cdn-cgi/[^"]+"></script>', '', html)
    html = re.sub(r'<a href="/cdn-cgi/l/email-protection#[^"]*"[^>]*>.*?</a>', '', html, flags=re.DOTALL)
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  HTML updated: {len(products)} products")

def main():
    now = datetime.now(timezone.utc)
    state = load_state()
    try:
        apple_df = download_excel()
    except Exception as e:
        print(f"ERROR downloading Excel: {e}")
        sys.exit(1)
    new_products = build_products(apple_df)
    new_ids  = sorted(p['id'] for p in new_products)
    new_cats = sorted(set(p['cat'] for p in new_products))
    def fingerprint(prods):
        return sorted(f"{p['id']}:{p['price']}:{p['status']}" for p in prods)
    new_fp = fingerprint(new_products)
    print(f"  Updating HTML...")
    patch_html(new_products)
    state['last_change'] = now.isoformat()
    state['last_run']    = now.isoformat()
    state['product_ids'] = new_ids
    state['cats']        = new_cats
    state['fingerprint'] = new_fp
    save_state(state)
    print(f"  Done. Products: {len(new_products)}")

if __name__ == '__main__':
    main()

from flask import Flask, render_template, request, jsonify
import requests
import socket
from concurrent.futures import ThreadPoolExecutor

# إجبار الاتصالات عبر IPv4 فقط لمنع خطأ Network is unreachable
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo

app = Flask(__name__)

# ذاكرة مؤقتة بحجم ممتاز لتسريع جلب أسماء الشبكات
ASN_CACHE = {
    '174': 'Cogent Communications, LLC',
    '3356': 'Lumen Technologies (Level 3)',
    '1299': 'Arelion (Telia Carrier)',
    '2914': 'NTT Communications',
    '6453': 'Tata Communications',
    '13335': 'Cloudflare, Inc.',
    '15169': 'Google LLC',
    '16509': 'Amazon.com, Inc.',
    '8075': 'Microsoft Corporation'
}

def fetch_asn_name(asn):
    """جلب اسم AS بسرعة عالية مع كاش مسبق"""
    asn_str = str(asn).replace('AS', '')
    if asn_str in ASN_CACHE:
        return asn_str, ASN_CACHE[asn_str]

    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. BGPView API
    try:
        r = requests.get(f'https://api.bgpview.io/asn/{asn_str}', headers=headers, timeout=2).json()
        name = r.get('data', {}).get('name') or r.get('data', {}).get('description_short')
        if name:
            ASN_CACHE[asn_str] = name
            return asn_str, name
    except:
        pass

    # 2. RIPE overview
    try:
        r = requests.get(f'https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn_str}', headers=headers, timeout=2).json()
        holder = r.get('data', {}).get('holder')
        if holder:
            ASN_CACHE[asn_str] = holder
            return asn_str, holder
    except:
        pass

    fallback = f"AS{asn_str} Network"
    ASN_CACHE[asn_str] = fallback
    return asn_str, fallback

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trace')
def trace():
    target_ip = request.args.get('ip', '91.205.42.55').strip()
    
    if not target_ip:
        return jsonify({'error': 'يرجى إدخال IP صحيح'}), 400

    headers = {'User-Agent': 'BGP-Trace-Engine/3.0'}

    path = []
    selected_prefix = f"{target_ip}/24"

    # المحاولة الأولى: استخدام BGPView API (سريع ومباشر ودقيق بالـ /24)
    try:
        bv_res = requests.get(f'https://api.bgpview.io/ip/{target_ip}', headers=headers, timeout=4).json()
        data = bv_res.get('data', {})
        prefixes = data.get('prefixes', [])

        if prefixes:
            # اختيار أطول ماسك (More Specific) مثل /24 لتجنب /16
            prefixes_sorted = sorted(prefixes, key=lambda x: int(x.get('prefix', '/0').split('/')[-1]), reverse=True)
            best_prefix_info = prefixes_sorted[0]
            selected_prefix = best_prefix_info.get('prefix', selected_prefix)
            
            # جلب الـ AS-Path الخاص بهذا الـ Prefix الدقيق
            asn_info = best_prefix_info.get('asn', {})
            origin_asn = asn_info.get('asn')
            
            # جلب الـ Upstream paths من BGPView
            prefix_bgp = requests.get(f'https://api.bgpview.io/prefix/{selected_prefix}', headers=headers, timeout=3).json()
            upstreams = prefix_bgp.get('data', {}).get('upstream_asns', [])
            
            path = [u.get('asn') for u in upstreams if u.get('asn')]
            if origin_asn and origin_asn not in path:
                path.append(origin_asn)

    except Exception:
        path = []

    # المحاولة الثانية (Fallback): RIPEstat في حال لم يرجع BGPView نتائج
    if not path:
        try:
            bgp_url = f'https://stat.ripe.net/data/bgp-state/data.json?resource={target_ip}'
            bgp_res = requests.get(bgp_url, headers=headers, timeout=4).json()
            bgp_routes = bgp_res.get('data', {}).get('bgp_state', [])

            if bgp_routes:
                best_route = next((r for r in bgp_routes if '/24' in r.get('target_prefix', '')), bgp_routes[0])
                path = best_route.get('path', [])
                selected_prefix = best_route.get('target_prefix', selected_prefix)
        except Exception:
            pass

    if not path:
        return jsonify({'error': 'تعذر الاتصال بمصادر BGP، يرجى التأكد من وصول السيرفر للإنترنت أو تجربة IP آخر'}), 500

    # جلب أسماء الشبكات بالـ Multi-threading بسرعة فائقة
    path_nodes_dict = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_asn_name, path)
        for asn_str, holder in results:
            path_nodes_dict[asn_str] = holder

    path_nodes = []
    for asn in path:
        asn_str = str(asn)
        path_nodes.append({
            'asn': f"AS{asn_str}",
            'name': path_nodes_dict.get(asn_str, f"AS{asn_str} Holder")
        })

    return jsonify({
        'target_ip': target_ip,
        'announced_prefix': selected_prefix,
        'target_asn': path_nodes[-1]['asn'],
        'target_holder': path_nodes[-1]['name'],
        'as_path': [node['asn'] for node in path_nodes],
        'nodes': path_nodes
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

from flask import Flask, render_template, request, jsonify
import requests
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# ذاكرة مؤقتة بحجم ممتاز لتسريع جلب أسماء الشبكات فوراً
ASN_CACHE = {
    '174': 'Cogent Communications, LLC',
    '3356': 'Lumen Technologies (Level 3)',
    '1299': 'Arelion (Telia Carrier)',
    '2914': 'NTT Communications',
    '6453': 'Tata Communications',
    '6762': 'Telecom Italia Sparkle',
    '13335': 'Cloudflare, Inc.',
    '15169': 'Google LLC',
    '16509': 'Amazon.com, Inc.',
    '8075': 'Microsoft Corporation'
}

def fetch_single_asn_name(asn):
    """جلب اسم AS معين بسرعة عالية وحفظه في الكاش"""
    asn_str = str(asn).replace('AS', '')
    if asn_str in ASN_CACHE:
        return asn_str, ASN_CACHE[asn_str]

    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. RIPE overview
    try:
        r = requests.get(f'https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn_str}', headers=headers, timeout=2.5).json()
        holder = r.get('data', {}).get('holder')
        if holder:
            ASN_CACHE[asn_str] = holder
            return asn_str, holder
    except:
        pass

    # 2. RDAP Fallback
    try:
        r = requests.get(f'https://rdap.db.ripe.net/autnum/{asn_str}', headers=headers, timeout=2.5).json()
        name = r.get('name') or r.get('handle')
        if name:
            ASN_CACHE[asn_str] = name
            return asn_str, name
    except:
        pass

    fallback_name = f"AS{asn_str} Network"
    ASN_CACHE[asn_str] = fallback_name
    return asn_str, fallback_name

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trace')
def trace():
    target_ip = request.args.get('ip', '195.7.9.1').strip()
    
    if not target_ip:
        return jsonify({'error': 'يرجى إدخال IP صحيح'}), 400

    headers = {'User-Agent': 'BGP-Trace-Engine/2.0'}

    try:
        # 1. تحديد الـ More Specific Prefix (/24) لتفادي الاختلاط مع /16
        prefix_url = f'https://stat.ripe.net/data/prefix-overview/data.json?resource={target_ip}'
        prefix_res = requests.get(prefix_url, headers=headers, timeout=3.5).json()
        resource_prefixes = prefix_res.get('data', {}).get('asns', [])

        target_resource = target_ip
        # استخراج أطول / أدق Prefix (مثال اختيار /24 بدل /16)
        all_asns_info = prefix_res.get('data', {}).get('resource', '')
        if '/' in all_asns_info:
            target_resource = all_asns_info

        # 2. جلب مسارات BGP المخصصة للـ Prefix الدقيق
        bgp_url = f'https://stat.ripe.net/data/bgp-state/data.json?resource={target_ip}'
        bgp_res = requests.get(bgp_url, headers=headers, timeout=4).json()
        bgp_routes = bgp_res.get('data', {}).get('bgp_state', [])

        if not bgp_routes:
            return jsonify({'error': 'لم يتم العثور على مسارات BGP موثوقة لهذا الـ IP'}), 404

        # اختار المسار المباشر المخصص للـ More Specific Prefix
        best_route = None
        for route in bgp_routes:
            target_prefix = route.get('target_prefix', '')
            # تفضيل المسارات الأكثر تخصيصاً (مثل /24 على /16)
            if '/24' in target_prefix or '/23' in target_prefix or '/22' in target_prefix:
                best_route = route
                break
        
        if not best_route:
            best_route = bgp_routes[0]

        path = best_route.get('path', [])
        selected_prefix = best_route.get('target_prefix', target_resource)

        if not path:
            return jsonify({'error': 'المسار فارغ'}), 404

        # 3. جلب أسماء كل الـ ASNs بالتوازي وبسرعة فائقة (Parallel Multi-threading)
        path_nodes_dict = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_single_asn_name, path)
            for asn_str, holder in results:
                path_nodes_dict[asn_str] = holder

        # بناء القائمة النهائية مرتبة حسب ترتيب المسار الحقيقي
        path_nodes = []
        for asn in path:
            asn_str = str(asn)
            path_nodes.append({
                'asn': f"AS{asn_str}",
                'name': path_nodes_dict.get(asn_str, f"AS{asn_str} Holder")
            })

        target_asn = path_nodes[-1]['asn']
        target_holder = path_nodes[-1]['name']

        return jsonify({
            'target_ip': target_ip,
            'announced_prefix': selected_prefix,
            'target_asn': target_asn,
            'target_holder': target_holder,
            'as_path': [node['asn'] for node in path_nodes],
            'nodes': path_nodes
        })

    except Exception as e:
        return jsonify({'error': f'حدث خطأ في الجلب: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

# Cache dictionary for ASN names to avoid repeated calls
ASN_NAME_CACHE = {
    '174': 'Cogent Communications, LLC',
    '3356': 'Lumen Technologies (Level 3)',
    '1299': 'Arelion (Telia Carrier)',
    '2914': 'NTT Communications',
    '6453': 'Tata Communications'
}

def get_asn_name(asn):
    asn_str = str(asn).replace('AS', '')
    if asn_str in ASN_NAME_CACHE:
        return ASN_NAME_CACHE[asn_str]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # Fast query to RIPE overview
        r = requests.get(f'https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn_str}', headers=headers, timeout=2).json()
        holder = r.get('data', {}).get('holder')
        if holder:
            ASN_NAME_CACHE[asn_str] = holder
            return holder
    except:
        pass
    
    try:
        # Fallback to RDAP / RIPEstat name query
        r = requests.get(f'https://rdap.db.ripe.net/autnum/{asn_str}', headers=headers, timeout=2).json()
        name = r.get('name') or r.get('handle')
        if name:
            ASN_NAME_CACHE[asn_str] = name
            return name
    except:
        pass

    return f"AS{asn_str} Network"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trace')
def trace():
    target_ip = request.args.get('ip', '91.205.42.55').strip()
    
    if not target_ip:
        return jsonify({'error': 'يرجى إدخال IP صحيح'}), 400

    headers = {'User-Agent': 'BGP-Trace-App/1.0'}

    try:
        # 1. Fetch BGP path
        url = f'https://stat.ripe.net/data/bgp-state/data.json?resource={target_ip}'
        bgp_res = requests.get(url, headers=headers, timeout=5).json()
        bgp_state = bgp_res.get('data', {}).get('bgp_state', [])

        path = []
        if bgp_state:
            path = bgp_state[0].get('path', [])

        # If no BGP path found or RIPE timed out, fallback to IP-API info
        if not path:
            ip_info = requests.get(f'http://ip-api.com/json/{target_ip}?fields=status,message,as,org,isp', timeout=4).json()
            if ip_info.get('status') == 'success':
                as_raw = ip_info.get('as', '')
                asn_num = as_raw.split()[0].replace('AS', '') if as_raw else 'Unknown'
                org_name = ip_info.get('org') or ip_info.get('isp') or 'Unknown'
                
                return jsonify({
                    'target_ip': target_ip,
                    'target_asn': f"AS{asn_num}",
                    'target_holder': org_name,
                    'as_path': [f"AS{asn_num}"],
                    'nodes': [{'asn': f"AS{asn_num}", 'name': org_name}]
                })
            return jsonify({'error': 'لم يتم العثور على مسار BGP لهذا الـ IP'}), 404

        # 2. Build nodes list with names
        path_nodes = []
        for asn in path:
            holder = get_asn_name(asn)
            path_nodes.append({
                'asn': f"AS{asn}",
                'name': holder
            })

        target_asn = path_nodes[-1]['asn']
        target_holder = path_nodes[-1]['name']

        return jsonify({
            'target_ip': target_ip,
            'target_asn': target_asn,
            'target_holder': target_holder,
            'as_path': [node['asn'] for node in path_nodes],
            'nodes': path_nodes
        })

    except Exception as e:
        # General fallback if any network connection drops completely
        try:
            ip_info = requests.get(f'http://ip-api.com/json/{target_ip}?fields=status,message,as,org,isp', timeout=4).json()
            if ip_info.get('status') == 'success':
                as_raw = ip_info.get('as', '')
                asn_num = as_raw.split()[0].replace('AS', '') if as_raw else 'Unknown'
                org_name = ip_info.get('org') or ip_info.get('isp') or 'Unknown'
                
                return jsonify({
                    'target_ip': target_ip,
                    'target_asn': f"AS{asn_num}",
                    'target_holder': org_name,
                    'as_path': [f"AS{asn_num}"],
                    'nodes': [{'asn': f"AS{asn_num}", 'name': org_name}]
                })
        except:
            pass

        return jsonify({'error': f'فشل في جلب البيانات بسبب انقطاع شبكة السيرفر: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

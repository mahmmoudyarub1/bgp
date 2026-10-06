from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

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
        # 1. Get BGP Path from RIPEstat
        url = f'https://stat.ripe.net/data/bgp-state/data.json?resource={target_ip}'
        bgp_res = requests.get(url, headers=headers, timeout=10).json()
        
        bgp_state = bgp_res.get('data', {}).get('bgp_state', [])

        if not bgp_state:
            # Fallback to ip-api to get at least Origin AS if BGP path is not full
            ip_info = requests.get(f'http://ip-api.com/json/{target_ip}?fields=status,message,as,org,isp', timeout=5).json()
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
            return jsonify({'error': 'لم يتم العثور على مسار BGP لهذه الشريحة/الـ IP'}), 404

        # Extract path from the first available route
        path = bgp_state[0].get('path', [])
        if not path:
            return jsonify({'error': 'المسار فارغ لهذا الـ IP'}), 404

        # 2. Get Holder Name for each ASN in path
        path_nodes = []
        for asn in path:
            try:
                ov = requests.get(f'https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn}', headers=headers, timeout=4).json()
                holder = ov.get('data', {}).get('holder', f'AS{asn}')
            except:
                holder = f"AS{asn} Holder"

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

    except requests.exceptions.Timeout:
        return jsonify({'error': 'انتهت مهلة الاتصال بخوادم BGP (Timeout)، حاول مرة أخرى'}), 504
    except Exception as e:
        return jsonify({'error': f'حدث خطأ غير متوقع: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

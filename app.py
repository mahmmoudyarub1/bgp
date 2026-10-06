from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trace')
def trace():
    target_ip = request.args.get('ip', '91.205.42.55')
    try:
        # 1. Get BGP state / AS Path from RIPEstat API
        bgp_res = requests.get(f'https://stat.ripe.net/data/bgp-state/data.json?resource={target_ip}').json()
        bgp_routes = bgp_res.get('data', {}).get('bgp_state', [])
        
        if not bgp_routes:
            return jsonify({'error': 'لم يتم العثور على مسار BGP لهذا الـ IP'}), 404

        # Get the active route path
        path = bgp_routes[0].get('path', [])
        
        # Target ASN is the last ASN in the path
        target_asn = path[-1] if path else 'N/A'
        
        # 2. Get Name & Details for each ASN in the path
        path_nodes = []
        for asn in path:
            overview = requests.get(f'https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn}').json()
            holder = overview.get('data', {}).get('holder', f'AS{asn}')
            
            path_nodes.append({
                'asn': f"AS{asn}",
                'name': holder
            })

        # Get Target ASN Name
        target_holder = path_nodes[-1]['name'] if path_nodes else 'N/A'

        return jsonify({
            'target_ip': target_ip,
            'target_asn': f"AS{target_asn}",
            'target_holder': target_holder,
            'as_path': [node['asn'] for node in path_nodes],
            'nodes': path_nodes
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

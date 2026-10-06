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
            return jsonify({'error': 'No BGP path found for this IP'}), 404

        # Get the first active route path
        path = bgp_routes[0].get('path', [])
        
        # 2. Resolve Geolocation for each ASN in the path
        path_nodes = []
        for asn in path:
            as_res = requests.get(f'https://stat.ripe.net/data/geoloc/data.json?resource=AS{asn}').json()
            locations = as_res.get('data', {}).get('located_resources', [])
            
            if locations and len(locations) > 0:
                loc = locations[0]
                path_nodes.append({
                    'asn': asn,
                    'lat': loc.get('latitude'),
                    'lng': loc.get('longitude'),
                    'country': loc.get('country')
                })
            else:
                overview = requests.get(f'https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn}').json()
                holder = overview.get('data', {}).get('holder', f'AS{asn}')
                path_nodes.append({
                    'asn': asn,
                    'holder': holder,
                    'lat': None,
                    'lng': None
                })

        return jsonify({
            'target': target_ip,
            'as_path': path,
            'nodes': path_nodes
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

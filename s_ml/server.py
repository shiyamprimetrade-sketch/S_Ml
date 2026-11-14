"""Read-only loopback dashboard with Host protection."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .storage import Store
from .recommendations import recommend


def create_server(database, port=8766):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send_error(403)
                return
            if self.path == '/':
                body = Path(__file__).with_name('dashboard.html').read_bytes()
                mime = 'text/html; charset=utf-8'
            elif self.path in ('/api/summary', '/api/recommendations'):
                with Store(database) as store:
                    summary = store.summary()
                body = json.dumps(summary if self.path == '/api/summary' else recommend(summary)).encode()
                mime = 'application/json'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)

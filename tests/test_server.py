import http.client
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from s_ml.server import create_server


class ServerTests(unittest.TestCase):
    def test_local_http_routes_and_host_guard(self):
        with tempfile.TemporaryDirectory() as d:
            server = create_server(Path(d) / 'db.sqlite3', 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            try:
                for path in ('/', '/api/summary', '/api/recommendations'):
                    connection.request('GET', path)
                    result = connection.getresponse()
                    self.assertEqual(result.status, 200)
                    self.assertEqual(result.getheader('Cache-Control'), 'no-store')
                    result.read()
                connection.request('GET', '/api/summary', headers={'Host': 'evil.test'})
                result = connection.getresponse()
                self.assertEqual(result.status, 403)
                result.read()
                connection.request('POST', '/api/summary')
                result = connection.getresponse()
                self.assertEqual(result.status, 501)
                result.read()
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join()

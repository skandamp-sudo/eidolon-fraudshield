"""Phase 4 research-sandbox API isolation and opt-in checks."""
import http.client
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from fraudshield.server import App, ROOT, research_model_from_env


class StubResearchModel:
    version = 'test-research-model'
    sha256 = 'a' * 64
    thresholds = {'max_f1': 0.98}

    def predict(self, payload, *, operating_point='max_f1'):
        if operating_point not in self.thresholds:
            raise ValueError('Unknown locked operating point')
        return {'risk_score': 0.8, 'alert': False,
                'threshold': 0.98, 'operating_point': operating_point,
                'model_version': self.version, 'artifact_sha256': self.sha256,
                'score_semantics': 'uncalibrated ranking score'}


class ResearchWorkspaceTests(unittest.TestCase):
    def test_default_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(research_model_from_env())
        with TemporaryDirectory() as folder:
            app = App(database=Path(folder) / 'events.sqlite3')
            self.assertFalse(app.research_status()['available'])

    def test_opt_in_requires_both_fingerprints(self):
        with patch.dict(os.environ, {'FRAUDSHIELD_RESEARCH_MODEL': '/tmp/research.json'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                research_model_from_env()

    def test_research_is_separate_and_nonpersistent(self):
        with TemporaryDirectory() as folder:
            app = App(database=Path(folder) / 'events.sqlite3',
                      research_model=StubResearchModel())
            http = ThreadingHTTPServer(('127.0.0.1', 0), app.handler())
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection('127.0.0.1', http.server_port, timeout=5)

                def request(method, route, data=None):
                    headers = {'Content-Type': 'application/json'} if data is not None else {}
                    connection.request(method, route, json.dumps(data) if data is not None else None, headers)
                    reply = connection.getresponse()
                    return reply.status, json.loads(reply.read())

                status, info = request('GET', '/api/research/status')
                self.assertEqual(status, 200)
                self.assertTrue(info['available'])
                self.assertFalse(info['stored'])
                status, score = request('POST', '/api/research/score',
                                        {'step': 24, 'type': 'TRANSFER', 'amount': 200000})
                self.assertEqual(status, 200)
                self.assertEqual(score['model_role'], 'research_only')
                self.assertFalse(score['stored'])
                self.assertEqual(score['risk_score'], 0.8)
                self.assertEqual(app.store.summary()['total'], 0)
                for invalid in ({'step': 24, 'type': 'TRANSFER', 'amount': 20, 'isFraud': 1},
                                {'step': 24, 'type': 'TRANSFER', 'amount': 20, 'operating_point': 'arbitrary'}):
                    status, _ = request('POST', '/api/research/score', invalid)
                    self.assertEqual(status, 400)
                self.assertEqual(app.store.summary()['total'], 0)
                connection.close()
            finally:
                http.shutdown()
                http.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()

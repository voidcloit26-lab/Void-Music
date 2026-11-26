import io
import json
import tempfile
import unittest
from pathlib import Path
from guardian.business_api_v2 import BusinessAPI
from guardian.business_store import BusinessStore


class BusinessAPITests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 1800000000
        self.auth_time = self.now
        self.token = 'A' * 43
        self.store = BusinessStore(str(Path(tmp.name) / 'qa.sqlite'), b'x' * 32,
            sandbox=True, owner_id='admin', verify_owner=lambda token: (
                'admin' if token == self.token else 'customer', self.auth_time), clock=lambda: self.now)
        self.account, _ = self.store.create_account('a' * 64)
        self.api = BusinessAPI(self.store, sandbox=True, clock=lambda: self.now)

    def call(self, action, data=None, *, token=None, raw=None, **kwargs):
        body = raw if raw is not None else json.dumps(data or {}).encode()
        env = {'PATH_INFO': '/owner/v2/' + action, 'REQUEST_METHOD': 'POST',
               'HTTP_AUTHORIZATION': 'Bearer ' + (self.token if token is None else token),
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(body)), 'wsgi.input': io.BytesIO(body)}
        env.update(kwargs)
        metadata = []
        response = b''.join(self.api(env, lambda status, headers: metadata.extend((status, dict(headers)))))
        return int(metadata[0].split()[0]), metadata[1], json.loads(response)

    def test_owner_summary_and_no_cache(self):
        status, headers, result = self.call('summary')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(result['accounts'], 1)
        self.assertFalse(result['payments_enabled'])

    def test_customer_and_stale_owner_denied(self):
        self.assertEqual(self.call('price', {'cents': 700}, token='B'*43)[0], 403)
        self.auth_time -= 301
        self.assertEqual(self.call('summary')[0], 403)
        self.auth_time = self.now
        self.assertEqual(self.store.price(self.token), 500)

    def test_free_key_issue_redeem_and_state(self):
        status, _, value = self.call('issue', {'account': self.account, 'kind': 'lifetime'})
        self.assertEqual(status, 200)
        self.store.redeem(self.account, 'a'*64, value['code'])
        self.assertEqual(self.call('member', {'account': self.account})[2]['status'], 'active')
        self.assertEqual(self.call('state', {'account': self.account, 'state': 'suspended'})[0], 200)
        self.assertEqual(self.call('member', {'account': self.account})[2]['status'], 'suspended')
        self.assertNotIn(value['code'], str(self.call('audit')[2]))

    def test_price_and_audit(self):
        self.assertEqual(self.call('price', {'cents': 799})[2], {'cents': 799})
        self.assertEqual(self.call('audit')[2]['events'][0]['detail'], '500->799')
        self.assertEqual(self.call('price', {'cents': True})[0], 400)
        self.assertEqual(len(self.call('audit')[2]['events']), 1)

    def test_malformed_routes_and_real_payments_disabled(self):
        self.assertEqual(self.call('payment')[0], 404)
        self.assertEqual(self.call('issue', {'account': self.account, 'kind': 'annual'})[0], 403)
        self.assertEqual(self.call('summary', raw=b'{"a":1,"a":2}')[0], 400)
        self.assertEqual(self.call('summary', raw=b'{"a":NaN}')[0], 400)
        self.assertEqual(self.call('summary', CONTENT_LENGTH='9000')[0], 413)
        self.assertEqual(self.call('summary', REQUEST_METHOD='GET')[0], 405)
        self.assertEqual(self.call('summary', CONTENT_TYPE='text/plain')[0], 415)

    def test_browser_credentials_rejected_and_limit(self):
        self.assertEqual(self.call('summary', HTTP_COOKIE='owner=abc')[0], 403)
        self.assertEqual(self.call('summary', HTTP_ORIGIN='https://evil.example')[0], 403)
        self.assertEqual(self.call('summary', token='')[0], 401)
        self.api = BusinessAPI(self.store, sandbox=True, clock=lambda: self.now, limit=1)
        self.assertEqual(self.call('summary')[0], 200)
        self.assertEqual(self.call('summary')[0], 429)
        self.now += 60
        self.assertEqual(self.call('summary')[0], 200)

    def test_sandbox_only(self):
        with self.assertRaises(PermissionError):
            BusinessAPI(self.store)

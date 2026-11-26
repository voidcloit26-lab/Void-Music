"""Isolated native owner API. No browser cookies, customer credentials or live payments.
The injected BusinessStore owner verifier must validate a fresh independent credential.
This adapter is not mounted on a production service.
"""
import json
import re
import threading
import time
from collections import deque
from guardian.business_store import BusinessDenied
from guardian.membership_rules import MembershipDenied

ROUTES = {
    '/owner/v2/summary': (set(), set()),
    '/owner/v2/member': ({'account'}, set()),
    '/owner/v2/price': ({'cents'}, set()),
    '/owner/v2/issue': ({'account', 'kind'}, {'days', 'ttl'}),
    '/owner/v2/state': ({'account', 'state'}, set()),
    '/owner/v2/audit': (set(), {'limit'}),
}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def invalid_constant(_):
    raise ValueError('invalid JSON constant')


class BusinessAPI:
    def __init__(self, store, *, sandbox=False, clock=time.monotonic, limit=120):
        if sandbox is not True:
            raise PermissionError('sandbox only')
        if type(limit) is not int or not 1 <= limit <= 120:
            raise ValueError('invalid request limit')
        self.store, self.clock, self.limit = store, clock, limit
        self.times, self.lock = deque(), threading.Lock()

    def _take(self):
        with self.lock:
            now = self.clock()
            while self.times and self.times[0] <= now - 60:
                self.times.popleft()
            if len(self.times) >= self.limit:
                return False
            self.times.append(now)
            return True

    @staticmethod
    def _reply(start, status, value):
        body = json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('ascii')
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store'),
                   ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
                   ('Content-Length', str(len(body)))]
        if status.startswith('429'):
            headers.append(('Retry-After', '60'))
        start(status, headers)
        return [body]

    def __call__(self, env, start):
        def reply(status, value):
            return self._reply(start, status, value)
        path = env.get('PATH_INFO', '')
        if path not in ROUTES or env.get('QUERY_STRING'):
            return reply('404 Not Found', {'error': 'not_found'})
        if env.get('REQUEST_METHOD') != 'POST':
            return reply('405 Method Not Allowed', {'error': 'method_not_allowed'})
        if env.get('HTTP_ORIGIN') or env.get('HTTP_COOKIE'):
            return reply('403 Forbidden', {'error': 'access_denied'})
        if not self._take():
            return reply('429 Too Many Requests', {'error': 'retry_later'})
        auth = env.get('HTTP_AUTHORIZATION', '')
        if not isinstance(auth, str) or not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            return reply('401 Unauthorized', {'error': 'owner_auth_required'})
        token = auth[7:]
        if env.get('CONTENT_TYPE', '').split(';', 1)[0].strip().lower() != 'application/json':
            return reply('415 Unsupported Media Type', {'error': 'invalid_request'})
        try:
            length = int(env.get('CONTENT_LENGTH', ''))
            if not 0 < length <= 4096:
                return reply('413 Payload Too Large', {'error': 'invalid_request'})
            raw = env['wsgi.input'].read(length)
            if len(raw) != length:
                raise ValueError('truncated body')
            data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid_constant)
            required, optional = ROUTES[path]
            if not isinstance(data, dict) or not required <= set(data) <= required | optional:
                raise ValueError('invalid fields')
            if path == '/owner/v2/summary':
                result = self.store.summary(token)
            elif path == '/owner/v2/member':
                result = self.store.member(token, data['account'])
            elif path == '/owner/v2/price':
                result = {'cents': self.store.change_price(token, data['cents'])}
            elif path == '/owner/v2/issue':
                result = {'code': self.store.owner_issue_free(token, **data)}
            elif path == '/owner/v2/state':
                result = {'changed': self.store.change_state(token, **data)}
            else:
                result = {'events': self.store.audit(token, **data)}
        except BusinessDenied:
            return reply('403 Forbidden', {'error': 'access_denied'})
        except MembershipDenied:
            return reply('409 Conflict', {'error': 'membership_conflict'})
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return reply('400 Bad Request', {'error': 'invalid_request'})
        except Exception:
            return reply('503 Service Unavailable', {'error': 'unavailable'})
        return reply('200 OK', result)

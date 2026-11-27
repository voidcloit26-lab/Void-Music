"""Explicit, independent Neon target for Guardian V2 staging only."""
from urllib.parse import urlsplit, parse_qsl, unquote
import re

DATABASE = 'void_guardian_v2_stage'
ROLE = 'guardian_v2_stage_runtime'
SCHEMA = 'guardian_v2_stage'


def connection_options(url):
    try:
        if not isinstance(url, str) or not 1 <= len(url) <= 4096:
            raise ValueError
        parsed = urlsplit(url)
        if parsed.scheme not in ('postgresql', 'postgres') or parsed.fragment:
            raise ValueError
        host = parsed.hostname or ''
        if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.neon\.tech', host):
            raise ValueError
        if parsed.username != ROLE or parsed.path != '/' + DATABASE or parsed.port not in (None, 5432):
            raise ValueError
        password = unquote(parsed.password or '', errors='strict')
        if not password or any(ord(c) < 32 for c in password):
            raise ValueError
        pairs = parse_qsl(parsed.query, strict_parsing=True, max_num_fields=2)
        options = dict(pairs)
        if len(options) != len(pairs) or set(options) - {'sslmode', 'channel_binding'}:
            raise ValueError
        if options.get('sslmode') != 'verify-full' or options.get('channel_binding', 'require') != 'require':
            raise ValueError
        return dict(host=host, port=5432, dbname=DATABASE, user=ROLE,
                    password=password, sslmode='verify-full', channel_binding='require')
    except (ValueError, UnicodeError, TypeError):
        raise ValueError('Independent Guardian V2 staging target with verified TLS required') from None

"""Explicit staging-only WSGI factory. No owner routes or payment processing."""
import os
import base64
from guardian.stage_store import StageStore
from guardian.clerk_session import ClerkSessionVerifier
from guardian.account_api_v2 import AccountAPI
from guardian.account_protocol_v2 import AccountProtocol
from guardian.durable_challenges import DurableChallenges
from guardian.shared_budget import SharedBudget
from guardian.stage_signing import load_signing_pair


def create_app():
    try:
        if os.environ.get('VOID_V2_STAGE_ENABLED') != 'true':
            raise ValueError('explicit staging enablement required')
        issuer = os.environ['VOID_V2_CLERK_ISSUER']
        verifier = ClerkSessionVerifier(issuer=issuer, audience='void-music-api',
            public_key_pem=base64.b64decode(os.environ['VOID_V2_CLERK_RSA_PEM_B64'], validate=True))
        key = load_signing_pair(os.environ['VOID_V2_LEASE_PRIVATE_B64'],
                                os.environ['VOID_V2_LEASE_PUBLIC_KEY'])
        store = StageStore(os.environ['VOID_V2_STAGE_DATABASE_URL'],
            bytes.fromhex(os.environ['VOID_V2_STAGE_PEPPER']), issuer=issuer)
        protocol = AccountProtocol(store, verifier, lease_key=key, challenges=DurableChallenges(store))
        api = AccountAPI(protocol, sandbox=True, budget=SharedBudget(store, bucket='account'))
    except Exception:
        raise RuntimeError('V2 staging configuration or database validation failed') from None

    def application(env, start):
        if env.get('PATH_INFO') == '/healthz' and not env.get('QUERY_STRING'):
            if env.get('REQUEST_METHOD') == 'GET':
                return AccountAPI.reply(start,'200 OK',{'status':'ready','mode':'staging-v2'})
            return AccountAPI.reply(start,'405 Method Not Allowed',{'error':'method_not_allowed'})
        if env.get('HTTP_ORIGIN') or env.get('HTTP_COOKIE'):
            return AccountAPI.reply(start,'403 Forbidden',{'error':'access_denied'})
        return api(env,start)
    return application

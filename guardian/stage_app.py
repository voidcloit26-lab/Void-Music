"""Explicit staging-only WSGI factory. No owner routes or payment processing."""
import os
import base64
import json
from guardian.stage_store import StageStore
from guardian.clerk_session import ClerkSessionVerifier
from guardian.account_api_v2 import AccountAPI
from guardian.account_protocol_v2 import AccountProtocol
from guardian.durable_challenges import DurableChallenges
from guardian.shared_budget import SharedBudget
from guardian.stage_signing import load_signing_pair
from guardian.stage_account_guard import AccountFairness, SharedAccountFairness, authorize_request
from guardian.activation_codes_v2 import ActivationCodes
from guardian.clerk_profile import ClerkProfileLookup
from guardian.owner_identity_policy import OwnerIdentityPolicy
from guardian.owner_bootstrap import OwnerBootstrap


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
        activation_codes = profile_lookup = None
        if os.environ.get('VOID_V2_ACTIVATION_ENABLED') == 'true':
            with store.transaction() as db:
                db.execute('SELECT digest,kind,days,expires_at,bound_identity,redeemed_account,redeemed_at,cancelled_at FROM activation_codes_v2 LIMIT 0')
                for column in ('redeemed_account','redeemed_at'):
                    if not db.execute("SELECT has_column_privilege(current_user,'guardian_v2_stage.activation_codes_v2',?,'UPDATE')",(column,)).fetchone()[0]:
                        raise PermissionError('activation grants missing')
                for column in ('kind','bound_identity','cancelled_at','expires_at'):
                    if db.execute("SELECT has_column_privilege(current_user,'guardian_v2_stage.activation_codes_v2',?,'UPDATE')",(column,)).fetchone()[0]:
                        raise PermissionError('unsafe activation grants')
                for privilege in ('INSERT','DELETE'):
                    if db.execute("SELECT has_table_privilege(current_user,'guardian_v2_stage.activation_codes_v2',?)",(privilege,)).fetchone()[0]:
                        raise PermissionError('unsafe activation grants')
            activation_codes = ActivationCodes(store)
            profile_lookup = ClerkProfileLookup(os.environ['VOID_V2_CLERK_SECRET_KEY'])
        owner_bootstrap = None
        if os.environ.get('VOID_V2_OWNER_IDENTITY_ENABLED') == 'true':
            if profile_lookup is None:
                raise ValueError('verified activation must be enabled')
            policy = OwnerIdentityPolicy(issuer,json.loads(os.environ['VOID_V2_OWNER_IDENTITIES_JSON']))
            owner_bootstrap = OwnerBootstrap(store,policy,profile_lookup)
        if os.environ.get('VOID_V2_OWNER_PROFILE_PROBE') == 'true' and owner_bootstrap is not None:
            from guardian.owner_readiness_probe import check_owner_profile
            check_owner_profile(policy, profile_lookup)
        protocol = AccountProtocol(store, verifier, lease_key=key, challenges=DurableChallenges(store),
                                   activation_codes=activation_codes, profile_lookup=profile_lookup, owner_bootstrap=owner_bootstrap)
        fairness = SharedAccountFairness(store) if os.environ.get('VOID_V2_SHARED_FAIRNESS_ENABLED') == 'true' else AccountFairness()
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
        if (env.get('PATH_INFO') in ('/v2/challenge', '/v2/execute')
                and env.get('REQUEST_METHOD') == 'POST' and not env.get('QUERY_STRING')):
            denied = authorize_request(env, verifier, fairness)
            if denied is not None:
                return AccountAPI.reply(start, *denied)
        return api(env,start)
    return application

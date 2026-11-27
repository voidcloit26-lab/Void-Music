import json
import io
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from guardian import test_account_protocol_v2 as fixture_module
from guardian.account_protocol_v2 import canonical_body
from guardian.account_api_v2 import AccountAPI
from guardian.release_policy import ReleasePolicy
from guardian.release_registry import ReleaseRegistry
from guardian.version_gate import VersionGate, UpdateRequired
from guardian.membership_rules import MembershipDenied


class VersionedLeaseProtocolTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture_module.ProtocolTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.api = self.f.api
        self.f.call("redeem_free", {"code":self.f.store.issue_free(self.f.account,"lifetime")})
        self.api.lease_key = ec.generate_private_key(ec.SECP256R1())
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        key = ec.generate_private_key(ec.SECP256R1())
        now = self.f.store._now()
        self.registry = ReleaseRegistry(str(Path(tmp.name)/"release.sqlite"),key.public_key(),sandbox=True)
        policy = ReleasePolicy(1,75,74,"1.0.1","a"*64,"b"*64,1024,now,now+3600)
        raw = policy.canonical()
        self.registry.publish(raw,key.sign(raw,ec.ECDSA(hashes.SHA256())))
        self.api.version_gate = VersionGate(self.registry)

    def test_legacy_and_unsupported_rejected(self):
        with self.assertRaises(UpdateRequired):
            self.f.call("lease",{})
        for version, signer in ((73,"b"*64),(76,"b"*64),(75,"c"*64)):
            with self.subTest(version=version,signer=signer), self.assertRaises(UpdateRequired):
                self.f.call("lease_versioned",{"version_code":version,"signer_sha256":signer})

    def test_supported_lease(self):
        response = self.f.call("lease_versioned",{"version_code":75,"signer_sha256":"b"*64})
        self.assertEqual(set(response),{"payload","signature"})

    def test_disabled_gate_keeps_current_compatibility(self):
        self.api.version_gate = None
        with self.assertRaises(MembershipDenied):
            self.f.call("lease_versioned",{"version_code":75,"signer_sha256":"b"*64})
        self.assertEqual(set(self.f.call("lease",{})),{"payload","signature"})

    def test_http_upgrade_required(self):
        body = json.dumps({"public_key":self.f.pub,"action":"lease","body":{}}).encode()
        env = {"PATH_INFO":"/v2/challenge","REQUEST_METHOD":"POST",
               "HTTP_AUTHORIZATION":"Bearer a","CONTENT_TYPE":"application/json",
               "CONTENT_LENGTH":str(len(body)),"wsgi.input":io.BytesIO(body)}
        out = []
        raw = b"".join(AccountAPI(self.api,sandbox=True)(env,lambda status,headers:out.append(status)))
        self.assertEqual(out,["426 Upgrade Required"])
        self.assertEqual(json.loads(raw),{"error":"update_required"})

    def test_canonical_version_fields(self):
        self.assertEqual(canonical_body("lease_versioned",{"version_code":75,"signer_sha256":"b"*64}),
                         ('{"signer_sha256":"'+"b"*64+'","version_code":75}').encode())
        for version in (True,0,2100000001,"75"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                canonical_body("lease_versioned",{"version_code":version,"signer_sha256":"b"*64})

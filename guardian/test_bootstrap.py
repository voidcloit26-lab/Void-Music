import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from guardian.bootstrap import initialize
from guardian.owner_cli import store_from_environment

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "state"

    def test_persistent_identity_and_codes(self):
        public = initialize(self.root)
        self.assertEqual(public, initialize(self.root))
        with patch.dict(os.environ, {"VOID_GUARDIAN_STATE": str(self.root),
                "VOID_GUARDIAN_PEPPER_FILE": str(self.root / "pepper.hex")}, clear=True):
            code = store_from_environment().generate()
            self.assertEqual(len(store_from_environment().list_invitations()), 1)
            self.assertTrue(store_from_environment().cancel(code))

    def test_partial_state_rejected(self):
        initialize(self.root)
        (self.root / "pepper.hex").unlink()
        with self.assertRaises(ValueError): initialize(self.root)

    def test_unsafe_permissions_rejected(self):
        initialize(self.root)
        (self.root / "pepper.hex").chmod(0o644)
        with self.assertRaises(PermissionError): initialize(self.root)

    def test_existing_data_not_overwritten(self):
        self.root.mkdir(mode=0o700)
        (self.root / "access.sqlite").write_bytes(b"existing")
        with self.assertRaises(ValueError): initialize(self.root)
        self.assertEqual((self.root / "access.sqlite").read_bytes(), b"existing")

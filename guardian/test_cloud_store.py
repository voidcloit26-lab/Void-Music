import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from guardian.cloud_store import CloudStore, RevisionConflict, normalize
from guardian.membership_rules import MembershipDenied

class CloudStoreTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=str(Path(temp.name)/"test.sqlite")
        self.now=1800000000
        self.s=CloudStore(self.path,b"x"*32,clock=lambda:self.now)
        self.a,self.recovery=self.s.create_account("a"*64)
        self.b,_=self.s.create_account("b"*64)
        self.s.redeem(self.a,"a"*64,self.s.issue_free(self.a,"trial",days=1))
        self.data={"favorites":["song_a"],"playlists":[{"id":"p1","name":"My songs","tracks":["song_a"]}],"preferences":{"theme":"dark","shuffle":True}}

    def test_restore_after_device_replacement(self):
        self.assertEqual(self.s.write_library(self.a,"a"*64,0,self.data),1)
        self.s.recover(self.a,self.recovery,"c"*64)
        reopened=CloudStore(self.path,b"x"*32,clock=lambda:self.now)
        self.assertEqual(reopened.read_library(self.a,"c"*64),(1,self.data))
        with self.assertRaises(MembershipDenied):
            reopened.read_library(self.a,"a"*64)

    def test_account_isolation(self):
        self.s.write_library(self.a,"a"*64,0,self.data)
        self.assertEqual(self.s.read_library(self.b,"b"*64),(0,None))
        with self.assertRaises(MembershipDenied):
            self.s.read_library(self.a,"b"*64)
        with self.assertRaises(MembershipDenied):
            self.s.write_library(self.b,"b"*64,0,self.data)

    def test_expired_export_and_clear(self):
        self.s.write_library(self.a,"a"*64,0,self.data)
        self.now+=86400
        self.assertEqual(self.s.read_library(self.a,"a"*64),(1,self.data))
        with self.assertRaises(MembershipDenied):
            self.s.write_library(self.a,"a"*64,1,self.data)
        self.assertEqual(self.s.clear_library(self.a,"a"*64,1),2)
        self.assertEqual(self.s.read_library(self.a,"a"*64)[1]["favorites"],[])

    def test_concurrent_revision_conflict(self):
        def attempt(_):
            try:
                self.s.write_library(self.a,"a"*64,0,self.data)
                return True
            except RevisionConflict:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(8))),1)
        self.s.clear_library(self.a,"a"*64,1)
        with self.assertRaises(RevisionConflict):
            self.s.write_library(self.a,"a"*64,1,self.data)

    def test_metadata_validation(self):
        for bad in ({**self.data,"history":[]},{**self.data,"favorites":["/local/file.mp3"]},{**self.data,"favorites":["https://example.com"]},{**self.data,"favorites":["a","a"]},{**self.data,"preferences":{"token":"secret"}},{**self.data,"preferences":{"shuffle":1}}):
            with self.assertRaises(ValueError):
                normalize(bad)

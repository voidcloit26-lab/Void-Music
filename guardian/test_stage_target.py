import unittest
from guardian.stage_target import connection_options, DATABASE, ROLE


class StageTargetTests(unittest.TestCase):
    url = 'postgresql://guardian_v2_stage_runtime:fake%40secret@ep-test.example.neon.tech/void_guardian_v2_stage?sslmode=verify-full'

    def test_target(self):
        settings = connection_options(self.url)
        self.assertEqual((settings['dbname'], settings['user']), (DATABASE, ROLE))
        self.assertEqual(settings['password'], 'fake@secret')
        self.assertEqual(settings['sslmode'], 'verify-full')
        self.assertEqual(settings['channel_binding'], 'require')

    def test_reject_live_target(self):
        for url in (self.url.replace(DATABASE, 'void_guardian'), self.url.replace(ROLE, 'guardian_runtime')):
            with self.assertRaises(ValueError):
                connection_options(url)

    def test_reject_wrong_host(self):
        for host in ('127.0.0.1', 'neon.tech.evil.example', 'example.com'):
            with self.assertRaises(ValueError):
                connection_options(self.url.replace('ep-test.example.neon.tech', host))

    def test_tls_downgrade(self):
        for mode in ('require', 'disable', 'verify-ca'):
            with self.assertRaises(ValueError):
                connection_options(self.url.replace('verify-full', mode))

    def test_connection_option_injection(self):
        for extra in ('&options=-csearch_path%3Dpublic', '&hostaddr=127.0.0.1', '&sslmode=verify-full', '&channel_binding=disable'):
            with self.assertRaises(ValueError):
                connection_options(self.url + extra)

    def test_error_does_not_disclose_secret(self):
        with self.assertRaises(ValueError) as ctx:
            connection_options(self.url.replace('verify-full', 'disable'))
        self.assertNotIn('secret', str(ctx.exception))

    def test_explicit_channel_binding(self):
        self.assertEqual(connection_options(self.url + '&channel_binding=require')['channel_binding'], 'require')

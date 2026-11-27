import base64
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from guardian.stage_signing import load_signing_pair


def encoded(key):
    private = base64.b64encode(key.private_bytes(serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())).decode('ascii')
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).rstrip(b'=').decode('ascii')
    return private, public


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.private, self.public = encoded(self.key)

    def test_correct_pair(self):
        self.assertEqual(load_signing_pair(self.private, self.public).private_numbers(), self.key.private_numbers())

    def test_outer_whitespace(self):
        self.assertEqual(load_signing_pair(self.private+'\n', ' '+self.public+'\n').private_numbers(), self.key.private_numbers())

    def test_wrong_public(self):
        with self.assertRaises(ValueError):
            load_signing_pair(self.private, encoded(ec.generate_private_key(ec.SECP256R1()))[1])

    def test_swapped_base64url(self):
        # Generate until the public representation contains a URL-safe character.
        while '-' not in self.public and '_' not in self.public:
            self.private, self.public = encoded(ec.generate_private_key(ec.SECP256R1()))
        with self.assertRaises(ValueError):
            load_signing_pair(self.private, self.public.translate(str.maketrans('-_', '_-')))

    def test_wrong_curve(self):
        with self.assertRaises(ValueError):
            load_signing_pair(*encoded(ec.generate_private_key(ec.SECP384R1())))

    def test_wrong_algorithm(self):
        with self.assertRaises(ValueError):
            load_signing_pair(*encoded(rsa.generate_private_key(public_exponent=65537, key_size=2048)))

    def test_missing_or_malformed(self):
        for private, public in [(None,self.public), ('!',self.public), (self.private,''), (self.private,self.public+'='), (self.private,'é')]:
            with self.subTest():
                with self.assertRaisesRegex(ValueError, '^Invalid Guardian V2 signing pair$'):
                    load_signing_pair(private, public)


if __name__ == '__main__':
    unittest.main()

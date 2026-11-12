import configparser
import getpass
import json
import os
import sys

from jaraco.classes import properties

from keyrings.alt.file_base import Keyring, decodebytes, encodebytes

from .escape import escape as escape_for_ini


class PlaintextKeyring(Keyring):
    """Simple File Keyring with no encryption"""

    priority = 0.5  # type: ignore
    "Applicable for all platforms, but not recommended"

    filename = 'keyring_pass.cfg'
    scheme = 'no encyption'
    version = '1.0'

    def encrypt(self, password, assoc=None):
        """Directly return the password itself, ignore associated data."""
        return password

    def decrypt(self, password_encrypted, assoc=None):
        """Directly return encrypted password, ignore associated data."""
        return password_encrypted


class Encrypted:
    """
    PyCryptodome-backed Encryption support
    """

    scheme = '[PBKDF2] AES256.CFB'
    version = '1.0'
    block_size = 32

    def __init__(self):
        vars(self).update(self._get_crypto_impl())

    @staticmethod
    def _get_crypto_impl():
        try:
            import Cryptodome.Random as Random  # noqa: F401
            from Cryptodome.Cipher import AES  # noqa: F401
            from Cryptodome.Protocol import KDF  # noqa: F401
        except ImportError:
            import Crypto.Random as Random  # noqa: F401
            from Crypto.Cipher import AES  # noqa: F401
            from Crypto.Protocol import KDF  # noqa: F401
        return locals()

    def _create_cipher(self, password, salt, IV):
        """
        Create the cipher object to encrypt or decrypt a payload.
        """
        pw = self.KDF.PBKDF2(password, salt, dkLen=self.block_size)
        return self.AES.new(pw[: self.block_size], self.AES.MODE_CFB, IV)

    def _get_new_password(self):
        while True:
            password = getpass.getpass("Please set a password for your new keyring: ")
            confirm = getpass.getpass('Please confirm the password: ')
            if password != confirm:  # pragma: no cover
                sys.stderr.write("Error: Your passwords didn't match\n")
                continue
            if '' == password.strip():  # pragma: no cover
                # forbid the blank password
                sys.stderr.write("Error: blank passwords aren't allowed.\n")
                continue
            return password


class EncryptedKeyring(Encrypted, Keyring):
    """PyCryptodome File Keyring"""

    filename = 'crypted_pass.cfg'
    pw_prefix = b'pw:'

    @properties.classproperty
    def priority(cls):
        "Applicable for all platforms, but not recommended."
        try:
            cls._get_crypto_impl()
        except ImportError:  # pragma: no cover
            raise RuntimeError("pycryptodome/x required")
        if not json:  # pragma: no cover
            raise RuntimeError("JSON implementation such as simplejson required.")
        return 0.6

    @properties.NonDataProperty
    def keyring_key(self):
        # _unlock or _init_file will set the key or raise an exception
        if self._check_file():
            self._unlock()
        else:
            self._init_file()
        return self.keyring_key

    def _init_file(self):
        """
        Initialize a new password file and set the reference password.
        """
        self.keyring_key = self._get_new_password()
        # set a reference password, used to check that the password provided
        #  matches for subsequent checks.
        self.set_password(
            'keyring-setting', 'password reference', 'password reference value'
        )
        self._write_config_value('keyring-setting', 'scheme', self.scheme)
        self._write_config_value('keyring-setting', 'version', self.version)

    def _check_file(self):
        """
        Check if the file exists and has the expected password reference.
        """
        if not os.path.exists(self.file_path):
            return False
        self._migrate()
        config = configparser.RawConfigParser()
        config.read(self.file_path, encoding='utf-8')
        try:
            config.get(
                escape_for_ini('keyring-setting'), escape_for_ini('password reference')
            )
        except (configparser.NoSectionError, configparser.NoOptionError):
            return False
        try:
            self._check_scheme(config)
        except AttributeError:
            # accept a missing scheme
            return True
        return self._check_version(config)

    def _check_scheme(self, config):
        """
        check for a valid scheme

        raise ValueError otherwise
        raise AttributeError if missing
        """
        try:
            scheme = config.get(
                escape_for_ini('keyring-setting'), escape_for_ini('scheme')
            )
        except (configparser.NoSectionError, configparser.NoOptionError):
            raise AttributeError("Encryption scheme missing")

        # remove pointless crypto module name
        if scheme.startswith('PyCrypto '):
            scheme = scheme[9:]

        if scheme != self.scheme:
            raise ValueError(
                "Encryption scheme mismatch " f"(exp.: {self.scheme}, found: {scheme})"
            )

    def _check_version(self, config):
        """
        check for a valid version
        an existing scheme implies an existing version as well

        return True, if version is valid, and False otherwise
        """
        try:
            self.file_version = config.get(
                escape_for_ini('keyring-setting'), escape_for_ini('version')
            )
        except (configparser.NoSectionError, configparser.NoOptionError):
            return False
        return True

    def _unlock(self):
        """
        Unlock this keyring by getting the password for the keyring from the
        user.
        """
        self.keyring_key = getpass.getpass(
            'Please enter password for encrypted keyring: '
        )
        try:
            ref_pw = self.get_password('keyring-setting', 'password reference')
            assert ref_pw == 'password reference value'
        except AssertionError:
            self._lock()
            raise ValueError("Incorrect Password")

    def _lock(self):
        """
        Remove the keyring key from this instance.
        """
        del self.keyring_key

    def encrypt(self, password, assoc=None):
        # encrypt password, ignore associated data
        salt = self.Random.get_random_bytes(self.block_size)
        IV = self.Random.get_random_bytes(self.AES.block_size)
        cipher = self._create_cipher(self.keyring_key, salt, IV)
        password_encrypted = cipher.encrypt(self.pw_prefix + password)
        # Serialize the salt, IV, and encrypted password in a secure format
        data = dict(salt=salt, IV=IV, password_encrypted=password_encrypted)
        for key in data:
            # spare a few bytes: throw away newline from base64 encoding
            data[key] = encodebytes(data[key]).decode()[:-1]
        return json.dumps(data).encode()

    def decrypt(self, password_encrypted, assoc=None):
        # unpack the encrypted payload, ignore associated data
        data = json.loads(password_encrypted.decode())
        for key in data:
            data[key] = decodebytes(data[key].encode())
        cipher = self._create_cipher(self.keyring_key, data['salt'], data['IV'])
        plaintext = cipher.decrypt(data['password_encrypted'])
        assert plaintext.startswith(self.pw_prefix)
        return plaintext[3:]

    def _migrate(self, keyring_password=None):
        """
        Convert older keyrings to the current format.
        """

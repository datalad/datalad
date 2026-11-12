import base64
import platform
import sys

from jaraco.classes import properties
from jaraco.context import ExceptionTrap
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from . import file_base

try:
    import winreg
except ImportError:
    pass

try:
    from . import _win_crypto
except ImportError:
    pass


# For Python 3.8 compatibility
passes = ExceptionTrap().passes


@passes
def has_wincrypto():
    """
    Does this environment have wincrypto?
    Should return False even when Mercurial's Demand Import allowed import of
    _win_crypto, so accesses an attribute of the module.
    """
    _win_crypto.__name__


class EncryptedKeyring(file_base.Keyring):
    """
    A File-based keyring secured by Windows Crypto API.
    """

    version = "1.0"

    @properties.classproperty
    def priority(self):
        """
        Preferred over file.EncryptedKeyring but not other, more sophisticated
        Windows backends.
        """
        if not platform.system() == 'Windows':
            raise RuntimeError("Requires Windows")
        return 0.8

    filename = 'wincrypto_pass.cfg'

    def encrypt(self, password, assoc=None):
        """Encrypt the password using the CryptAPI."""
        return _win_crypto.encrypt(password)

    def decrypt(self, password_encrypted, assoc=None):
        """Decrypt the password using the CryptAPI."""
        return _win_crypto.decrypt(password_encrypted)


class RegistryKeyring(KeyringBackend):
    """
    RegistryKeyring is a keyring which use Windows CryptAPI to encrypt
    the user's passwords and store them under registry keys
    """

    @properties.classproperty
    def priority(self):
        """
        Preferred on Windows when pywin32 isn't installed
        """
        if platform.system() != 'Windows':
            raise RuntimeError("Requires Windows")
        if not has_wincrypto():
            raise RuntimeError("Requires ctypes")
        return 2

    @staticmethod
    def _key_for_service(service):
        escaped = service.replace('\\', '__0x5c__')
        return r'Software\{escaped}\Keyring'.format(**locals())

    def get_password(self, service, username):
        """Get password of the username for the service"""
        try:
            # fetch the password
            key = self._key_for_service(service)
            hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
            password_saved = winreg.QueryValueEx(hkey, username)[0]
            password_base64 = password_saved.encode('ascii')
            # decode with base64
            password_encrypted = base64.decodebytes(password_base64)
            # decrypted the password
            password = _win_crypto.decrypt(password_encrypted).decode('utf-8')
        except OSError:
            password = None
        return password

    def set_password(self, service, username, password):
        """Write the password to the registry"""
        # encrypt the password
        password_encrypted = _win_crypto.encrypt(password.encode('utf-8'))
        # encode with base64
        password_base64 = base64.encodebytes(password_encrypted)
        # encode again to unicode
        password_saved = password_base64.decode('ascii')

        # store the password
        key_name = self._key_for_service(service)
        hkey = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_name)
        winreg.SetValueEx(hkey, username, 0, winreg.REG_SZ, password_saved)

    def delete_password(self, service, username):
        """Delete the password for the username of the service."""
        try:
            key_name = self._key_for_service(service)
            hkey = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_name, 0, winreg.KEY_ALL_ACCESS
            )
            winreg.DeleteValue(hkey, username)
            winreg.CloseKey(hkey)
        except OSError:
            e = sys.exc_info()[1]
            raise PasswordDeleteError(e)
        self._delete_key_if_empty(service)

    def _delete_key_if_empty(self, service):
        key_name = self._key_for_service(service)
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_name, 0, winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.EnumValue(key, 0)
            return
        except OSError:
            pass
        winreg.CloseKey(key)

        # it's empty; delete everything
        while key_name != 'Software':
            parent, sep, base = key_name.rpartition('\\')
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, parent, 0, winreg.KEY_ALL_ACCESS
            )
            winreg.DeleteKey(key, base)
            winreg.CloseKey(key)
            key_name = parent

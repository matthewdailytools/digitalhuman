"""DeepSeek credentials in the current Windows user's local Credential Manager."""
import ctypes
from ctypes import wintypes
import os

TARGET = 'DigitalHumanLab/DeepSeek/APIKey'
ENV_KEY = 'DEEPSEEK_API_KEY'
NOT_FOUND = 1168


class CredentialError(ValueError):
    pass


def validate_secret(value):
    if not isinstance(value, str) or not value.strip():
        raise CredentialError('请输入 API Key；输入框留空时可保存当前会话的密钥。')
    value = value.strip()
    if len(value) > 1024 or any(not 33 <= ord(c) <= 126 for c in value):
        raise CredentialError('密钥格式无效，请勿包含空白、换行或非 ASCII 字符。')
    return value


class _Credential(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(wintypes.BYTE)), ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD), ('Attributes', wintypes.LPVOID),
        ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    def __init__(self, target=TARGET):
        self.target = target

    @staticmethod
    def _api():
        if os.name != 'nt':
            raise CredentialError('持久密钥需要 Windows 凭据管理器。')
        api = ctypes.WinDLL('advapi32', use_last_error=True)
        pointer = ctypes.POINTER(_Credential)
        api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
        api.CredReadW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [wintypes.LPVOID]
        api.CredFree.restype = None
        return api

    def read(self):
        api = self._api()
        pointer = ctypes.POINTER(_Credential)()
        if not api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            code = ctypes.get_last_error()
            if code == NOT_FOUND:
                return None
            raise CredentialError(f'无法读取 Windows 保存的密钥（错误 {code}）。')
        try:
            credential = pointer.contents
            size = credential.CredentialBlobSize
            if not 1 <= size <= 1024 or not credential.CredentialBlob:
                raise CredentialError('已保存的密钥格式无效，请重新保存或删除。')
            try:
                return validate_secret(ctypes.string_at(credential.CredentialBlob, size).decode('ascii'))
            except (UnicodeError, CredentialError):
                raise CredentialError('已保存的密钥格式无效，请重新保存或删除。') from None
        finally:
            if pointer.contents.CredentialBlob and 0 < pointer.contents.CredentialBlobSize <= 1024:
                ctypes.memset(pointer.contents.CredentialBlob, 0, pointer.contents.CredentialBlobSize)
            api.CredFree(pointer)

    def write(self, value):
        value = validate_secret(value)
        api = self._api()
        blob = ctypes.create_string_buffer(value.encode('ascii'))
        credential = _Credential()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = self.target
        credential.Comment = 'Digital Human Lab DeepSeek API key'
        credential.CredentialBlobSize = len(value)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(wintypes.BYTE))
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE: same user and computer across logons.
        credential.UserName = 'DeepSeek API'
        try:
            if not api.CredWriteW(ctypes.byref(credential), 0):
                raise CredentialError(f'无法保存到 Windows 凭据管理器（错误 {ctypes.get_last_error()}）。')
        finally:
            ctypes.memset(blob, 0, ctypes.sizeof(blob))

    def delete(self):
        api = self._api()
        if not api.CredDeleteW(self.target, 1, 0):
            code = ctypes.get_last_error()
            if code != NOT_FOUND:
                raise CredentialError(f'无法删除 Windows 保存的密钥（错误 {code}）。')


class ApiCredentials:
    """Load once at GUI startup; workers inherit only the effective process environment."""
    def __init__(self, store=None, environ=None):
        self.store = store if store is not None else WindowsCredentialStore()
        self.environ = os.environ if environ is None else environ
        self.saved = False

    @property
    def status(self):
        if self.saved:
            return '已保存到本机，重启后自动读取。'
        if self.environ.get(ENV_KEY, '').strip():
            return '当前仅会话可用；留空点击保存可持久使用。'
        return '尚未设置 API Key。'

    def load(self):
        value = self.store.read()
        if value is not None:
            self.environ[ENV_KEY] = validate_secret(value)
        self.saved = value is not None

    def save(self, value):
        value = validate_secret(value if value.strip() else self.environ.get(ENV_KEY, ''))
        self.store.write(value)
        self.environ[ENV_KEY] = value
        self.saved = True

    def delete(self):
        # Keep the active credential if the persistent deletion fails.
        self.store.delete()
        self.environ.pop(ENV_KEY, None)
        self.saved = False

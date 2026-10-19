"""Credential lifecycle tests use isolated test targets, never the real saved API key."""
import json
import os
import subprocess
import sys
import unittest
import uuid
from unittest.mock import Mock

from credential_store import ApiCredentials, CredentialError, ENV_KEY, WindowsCredentialStore
from desktop_console import Console


class CredentialSessionTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.read.return_value = None
        self.environ = {}
        self.credentials = ApiCredentials(self.store, self.environ)

    def test_startup_restores_saved_key_before_launch_environment(self):
        self.environ[ENV_KEY] = 'old-environment-fixture'
        self.store.read.return_value = 'saved-test-fixture'
        self.credentials.load()
        self.assertEqual(self.environ[ENV_KEY], 'saved-test-fixture')
        self.assertTrue(self.credentials.saved)
        self.assertNotIn('saved-test-fixture', self.credentials.status)

    def test_unsaved_environment_remains_usable_and_can_be_saved_without_reentry(self):
        self.environ[ENV_KEY] = 'environment-test-fixture'
        self.credentials.load()
        self.assertFalse(self.credentials.saved)
        self.credentials.save('')
        self.store.write.assert_called_once_with('environment-test-fixture')
        self.assertTrue(self.credentials.saved)

    def test_replace_and_delete_update_both_storage_and_effective_environment(self):
        self.credentials.save('first-test-fixture')
        self.credentials.save('second-test-fixture')
        self.assertEqual(self.environ[ENV_KEY], 'second-test-fixture')
        self.store.write.assert_called_with('second-test-fixture')
        self.credentials.delete()
        self.store.delete.assert_called_once()
        self.assertNotIn(ENV_KEY, self.environ)
        self.assertFalse(self.credentials.saved)

    def test_failed_save_or_delete_keeps_current_key(self):
        self.credentials.save('working-test-fixture')
        self.store.write.side_effect = CredentialError('保存失败')
        with self.assertRaises(CredentialError):
            self.credentials.save('replacement-test-fixture')
        self.assertEqual(self.environ[ENV_KEY], 'working-test-fixture')
        self.assertTrue(self.credentials.saved)
        self.store.delete.side_effect = CredentialError('删除失败')
        with self.assertRaises(CredentialError):
            self.credentials.delete()
        self.assertEqual(self.environ[ENV_KEY], 'working-test-fixture')
        self.assertTrue(self.credentials.saved)

    def test_invalid_inputs_never_reach_persistent_storage_or_echo_secret(self):
        for value in ('', ' ', 'sk-fixture\ninjected', 'sk fixture', '中文密钥', 'x' * 1025):
            with self.subTest(length=len(value)):
                with self.assertRaises(CredentialError) as error:
                    self.credentials.save(value)
                if value.strip():
                    self.assertNotIn(value, str(error.exception))
        self.store.write.assert_not_called()
        self.assertNotIn(ENV_KEY, self.environ)

    def test_read_failure_keeps_environment_and_does_not_claim_persistence(self):
        self.environ[ENV_KEY] = 'environment-test-fixture'
        self.store.read.side_effect = CredentialError('读取失败')
        with self.assertRaises(CredentialError):
            self.credentials.load()
        self.assertEqual(self.environ[ENV_KEY], 'environment-test-fixture')
        self.assertFalse(self.credentials.saved)


class CredentialConsoleTests(unittest.TestCase):
    def setUp(self):
        self.console = Console.__new__(Console)
        self.console.busy = False
        self.console.credentials = ApiCredentials(Mock(), {})
        self.console.secret = Mock()
        self.console.secret.get.return_value = 'new-test-fixture'
        self.console.secret_status = Mock()
        self.console.status = Mock()

    def test_save_and_delete_clear_password_field_and_show_safe_status(self):
        Console.set_secret(self.console)
        self.console.secret.set.assert_called_with('')
        self.assertEqual(self.console.credentials.environ[ENV_KEY], 'new-test-fixture')
        self.assertNotIn('new-test-fixture', self.console.status.set.call_args.args[0])
        Console.delete_secret(self.console)
        self.assertNotIn(ENV_KEY, self.console.credentials.environ)
        self.console.secret_status.set.assert_called_with('尚未设置 API Key。')

    def test_busy_or_failed_operation_does_not_change_key(self):
        self.console.busy = True
        Console.set_secret(self.console)
        Console.delete_secret(self.console)
        self.console.credentials.store.write.assert_not_called()
        self.console.credentials.store.delete.assert_not_called()
        self.console.busy = False
        self.console.credentials.store.write.side_effect = CredentialError('保存失败')
        Console.set_secret(self.console)
        self.console.status.set.assert_called_with('保存失败')
        self.console.secret.set.assert_not_called()
        self.assertNotIn(ENV_KEY, self.console.credentials.environ)


@unittest.skipUnless(os.name == 'nt', 'Requires the real Windows Credential Manager')
class WindowsCredentialIntegrationTests(unittest.TestCase):
    def test_real_vault_survives_new_process_replacement_and_delete(self):
        target = 'DigitalHumanLab/Test/' + uuid.uuid4().hex
        store = WindowsCredentialStore(target)
        probe = (
            'import json,sys; from credential_store import ApiCredentials,WindowsCredentialStore,ENV_KEY; '
            'expected=json.loads(sys.stdin.read()); env={}; '
            'session=ApiCredentials(WindowsCredentialStore(sys.argv[1]),env); session.load(); '
            'assert env.get(ENV_KEY)==expected; assert session.saved==(expected is not None); '
            'print("RESTORE OK")'
        )

        def check_in_new_process(expected):
            result = subprocess.run([sys.executable, '-c', probe, target],
                                    input=json.dumps(expected), text=True, capture_output=True,
                                    cwd=os.path.dirname(__file__), timeout=20,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.assertEqual(result.returncode, 0, 'Independent credential restore failed')
            self.assertEqual(result.stdout.strip(), 'RESTORE OK')

        try:
            store.delete()  # Missing credentials can be deleted repeatedly.
            self.assertIsNone(store.read())
            store.write('first-test-fixture-not-a-real-api-key')
            check_in_new_process('first-test-fixture-not-a-real-api-key')
            store.write('second-test-fixture-not-a-real-api-key')
            check_in_new_process('second-test-fixture-not-a-real-api-key')
            store.delete()
            check_in_new_process(None)
            store.delete()
        finally:
            store.delete()


if __name__ == '__main__':
    unittest.main()

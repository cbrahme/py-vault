import os
import unittest
from core.models import Vault

TEST_VAULT_PATH = "test_vault_v2.enc"

class TestVaultLifecycle(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_VAULT_PATH):
            os.remove(TEST_VAULT_PATH)

    def tearDown(self):
        if os.path.exists(TEST_VAULT_PATH):
            os.remove(TEST_VAULT_PATH)

    def test_vault_create_save_reload(self):
        master_pw = "MasterKey#2026!Strong"
        vault = Vault(TEST_VAULT_PATH)
        rec_key = vault.initialize(master_pw)
        self.assertTrue(rec_key.startswith("RCV-"))

        # Add entries
        vault.add("GitHub", "suyash", "pass123", url="https://github.com")
        vault.add("AWS", "admin", "cloudPass456", url="https://aws.amazon.com")
        vault.save()

        self.assertTrue(os.path.exists(TEST_VAULT_PATH))

        # Reopen in new instance with password
        vault2 = Vault(TEST_VAULT_PATH)
        vault2.unlock(master_pw)

        self.assertEqual(len(vault2.entries), 2)
        gh = vault2.get_by_title("GitHub")
        self.assertIsNotNone(gh)
        self.assertEqual(gh.username, "suyash")
        self.assertEqual(gh.password, "pass123")

        # Reopen in new instance with recovery key
        vault3 = Vault(TEST_VAULT_PATH)
        vault3.recover(rec_key)
        self.assertEqual(len(vault3.entries), 2)

        # Delete entry
        vault3.delete(gh.id)
        vault3.save()

        # Reopen and verify deletion
        vault4 = Vault(TEST_VAULT_PATH)
        vault4.unlock(master_pw)
        self.assertEqual(len(vault4.entries), 1)
        self.assertIsNone(vault4.get_by_title("GitHub"))

if __name__ == "__main__":
    unittest.main()

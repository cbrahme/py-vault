import os
import unittest
from core.crypto import (
    create_new_vault_envelope,
    unlock_vault_envelope,
    reset_password_with_vault_key,
    generate_recovery_key,
    normalize_recovery_key
)
from core.models import Vault, generate_password

class TestPyVaultV2(unittest.TestCase):
    def test_dual_slot_recovery(self):
        vault_data = {
            "version": 2,
            "entries": [{"id": "1", "title": "GitHub", "username": "suyash", "password": "Secret123!"}]
        }
        password = "OriginalMasterPassword#2026"
        envelope_bytes, recovery_key = create_new_vault_envelope(vault_data, password)

        # 1. Day-to-day unlock with Master Password
        v1, vk1, env1 = unlock_vault_envelope(envelope_bytes, password, is_recovery_key=False)
        self.assertEqual(v1["entries"][0]["title"], "GitHub")

        # 2. Wrong password fails
        with self.assertRaises(ValueError):
            unlock_vault_envelope(envelope_bytes, "WrongPassword", is_recovery_key=False)

        # 3. Emergency unlock with Recovery Key
        v2, vk2, env2 = unlock_vault_envelope(envelope_bytes, recovery_key, is_recovery_key=True)
        self.assertEqual(vk1, vk2)
        self.assertEqual(v2["entries"][0]["password"], "Secret123!")

        # 4. Reset Master Password using verified Vault Key
        new_pw = "NewMasterPassword#999"
        new_envelope_bytes = reset_password_with_vault_key(vk2, new_pw, env2)

        # Old password now fails
        with self.assertRaises(ValueError):
            unlock_vault_envelope(new_envelope_bytes, password, is_recovery_key=False)

        # New password unlocks successfully
        v3, vk3, _ = unlock_vault_envelope(new_envelope_bytes, new_pw, is_recovery_key=False)
        self.assertEqual(v3["entries"][0]["password"], "Secret123!")

    def test_vault_model_recovery_lifecycle(self):
        test_path = "test_v2.enc"
        if os.path.exists(test_path):
            os.remove(test_path)

        vault = Vault(test_path)
        rec_key = vault.initialize("FirstPassword#123")
        vault.add("Netflix", "user", "pass456")
        vault.save()

        # Reopen with wrong password
        v_wrong = Vault(test_path)
        with self.assertRaises(ValueError):
            v_wrong.unlock("BadPassword")

        # Recover using recovery key
        v_rec = Vault(test_path)
        v_rec.recover(rec_key)
        self.assertEqual(len(v_rec.entries), 1)
        self.assertEqual(v_rec.entries[0].title, "Netflix")

        # Reset password
        v_rec.reset_master_password("BrandNewPassword#789")

        # Verify new password unlocks
        v_new = Vault(test_path)
        v_new.unlock("BrandNewPassword#789")
        self.assertEqual(v_new.entries[0].title, "Netflix")

        if os.path.exists(test_path):
            os.remove(test_path)

if __name__ == "__main__":
    unittest.main()

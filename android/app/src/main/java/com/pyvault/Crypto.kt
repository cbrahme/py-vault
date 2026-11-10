package com.pyvault

import android.util.Base64
import org.json.JSONObject
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

object Crypto {
    private const val SALT_SIZE = 16
    private const val NONCE_SIZE = 12
    private const val TAG_SIZE_BITS = 128
    private const val KEY_SIZE_BITS = 256
    private const val PBKDF2_PW_ROUNDS = 600_000
    private const val PBKDF2_RC_ROUNDS = 100_000

    private val secureRandom = SecureRandom()

    fun generateRecoveryKey(): String {
        val alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        val sb = StringBuilder()
        for (i in 0 until 32) {
            sb.append(alphabet[secureRandom.nextInt(alphabet.length)])
        }
        val raw = sb.toString()
        val blocks = (0 until 32 step 4).map { raw.substring(it, it + 4) }
        return "RCV-" + blocks.joinToString("-")
    }

    fun normalizeRecoveryKey(keyStr: String): String {
        var cleaned = keyStr.uppercase().trim()
        if (cleaned.startsWith("RCV-")) {
            cleaned = cleaned.substring(4)
        }
        return cleaned.replace("-", "").replace(" ", "").trim()
    }

    fun deriveKey(secret: CharArray, salt: ByteArray, iterations: Int): SecretKeySpec {
        val spec = PBEKeySpec(secret, salt, iterations, KEY_SIZE_BITS)
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val keyBytes = factory.generateSecret(spec).encoded
        spec.clearPassword()
        return SecretKeySpec(keyBytes, "AES")
    }

    fun createNewVault(vaultData: VaultData, masterPassword: CharArray): Pair<String, String> {
        val recoveryKey = generateRecoveryKey()
        val normalizedRc = normalizeRecoveryKey(recoveryKey).toCharArray()

        val vaultKeyBytes = ByteArray(32).apply { secureRandom.nextBytes(this) }
        val vaultKey = SecretKeySpec(vaultKeyBytes, "AES")

        // 1. Encrypt Vault Data with Vault Key
        vaultData.updatedAt = System.currentTimeMillis() / 1000
        val vaultPlaintext = vaultData.toJsonString().toByteArray(Charsets.UTF_8)
        val vaultNonce = ByteArray(NONCE_SIZE).apply { secureRandom.nextBytes(this) }

        val cipherVk = Cipher.getInstance("AES/GCM/NoPadding")
        cipherVk.init(Cipher.ENCRYPT_MODE, vaultKey, GCMParameterSpec(TAG_SIZE_BITS, vaultNonce))
        cipherVk.updateAAD("VAULT_PAYLOAD".toByteArray(Charsets.UTF_8))
        val encryptedVault = cipherVk.doFinal(vaultPlaintext)

        // 2. Encrypt Vault Key with Master Password
        val saltPw = ByteArray(SALT_SIZE).apply { secureRandom.nextBytes(this) }
        val keyPw = deriveKey(masterPassword, saltPw, PBKDF2_PW_ROUNDS)
        val noncePw = ByteArray(NONCE_SIZE).apply { secureRandom.nextBytes(this) }

        val cipherPw = Cipher.getInstance("AES/GCM/NoPadding")
        cipherPw.init(Cipher.ENCRYPT_MODE, keyPw, GCMParameterSpec(TAG_SIZE_BITS, noncePw))
        cipherPw.updateAAD("SLOT_PW".toByteArray(Charsets.UTF_8))
        val encryptedVkPw = cipherPw.doFinal(vaultKeyBytes)

        // 3. Encrypt Vault Key with Recovery Key
        val saltRc = ByteArray(SALT_SIZE).apply { secureRandom.nextBytes(this) }
        val keyRc = deriveKey(normalizedRc, saltRc, PBKDF2_RC_ROUNDS)
        val nonceRc = ByteArray(NONCE_SIZE).apply { secureRandom.nextBytes(this) }

        val cipherRc = Cipher.getInstance("AES/GCM/NoPadding")
        cipherRc.init(Cipher.ENCRYPT_MODE, keyRc, GCMParameterSpec(TAG_SIZE_BITS, nonceRc))
        cipherRc.updateAAD("SLOT_RC".toByteArray(Charsets.UTF_8))
        val encryptedVkRc = cipherRc.doFinal(vaultKeyBytes)

        // Envelope JSON
        val root = JSONObject().apply {
            put("format", "PV02")
            put("version", 2)
            put("slot_pw", JSONObject().apply {
                put("salt", Base64.encodeToString(saltPw, Base64.NO_WRAP))
                put("nonce", Base64.encodeToString(noncePw, Base64.NO_WRAP))
                put("data", Base64.encodeToString(encryptedVkPw, Base64.NO_WRAP))
            })
            put("slot_rc", JSONObject().apply {
                put("salt", Base64.encodeToString(saltRc, Base64.NO_WRAP))
                put("nonce", Base64.encodeToString(nonceRc, Base64.NO_WRAP))
                put("data", Base64.encodeToString(encryptedVkRc, Base64.NO_WRAP))
            })
            put("vault", JSONObject().apply {
                put("nonce", Base64.encodeToString(vaultNonce, Base64.NO_WRAP))
                put("data", Base64.encodeToString(encryptedVault, Base64.NO_WRAP))
            })
        }

        return Pair(root.toString(), recoveryKey)
    }

    data class UnlockResult(
        val vaultData: VaultData,
        val vaultKey: SecretKeySpec,
        val envelope: JSONObject
    )

    fun unlockVault(envelopeJsonStr: String, secret: CharArray, isRecoveryKey: Boolean = false): UnlockResult {
        val envelope = JSONObject(envelopeJsonStr)
        if (envelope.optString("format") != "PV02") {
            throw IllegalArgumentException("Unsupported vault format: ${envelope.optString("format")}")
        }

        val slot = if (isRecoveryKey) envelope.getJSONObject("slot_rc") else envelope.getJSONObject("slot_pw")
        val secretClean = if (isRecoveryKey) normalizeRecoveryKey(String(secret)).toCharArray() else secret
        val rounds = if (isRecoveryKey) PBKDF2_RC_ROUNDS else PBKDF2_PW_ROUNDS
        val aad = (if (isRecoveryKey) "SLOT_RC" else "SLOT_PW").toByteArray(Charsets.UTF_8)

        val salt = Base64.decode(slot.getString("salt"), Base64.DEFAULT)
        val nonce = Base64.decode(slot.getString("nonce"), Base64.DEFAULT)
        val encVk = Base64.decode(slot.getString("data"), Base64.DEFAULT)

        val derivedKey = deriveKey(secretClean, salt, rounds)

        val cipherVk = Cipher.getInstance("AES/GCM/NoPadding")
        cipherVk.init(Cipher.DECRYPT_MODE, derivedKey, GCMParameterSpec(TAG_SIZE_BITS, nonce))
        cipherVk.updateAAD(aad)
        val vaultKeyBytes = try {
            cipherVk.doFinal(encVk)
        } catch (e: Exception) {
            val type = if (isRecoveryKey) "Recovery Key" else "Master Password"
            throw IllegalArgumentException("Invalid $type. Decryption failed.", e)
        }
        val vaultKey = SecretKeySpec(vaultKeyBytes, "AES")

        val vaultObj = envelope.getJSONObject("vault")
        val vaultNonce = Base64.decode(vaultObj.getString("nonce"), Base64.DEFAULT)
        val encVaultData = Base64.decode(vaultObj.getString("data"), Base64.DEFAULT)

        val cipherData = Cipher.getInstance("AES/GCM/NoPadding")
        cipherData.init(Cipher.DECRYPT_MODE, vaultKey, GCMParameterSpec(TAG_SIZE_BITS, vaultNonce))
        cipherData.updateAAD("VAULT_PAYLOAD".toByteArray(Charsets.UTF_8))
        val plaintextBytes = try {
            cipherData.doFinal(encVaultData)
        } catch (e: Exception) {
            throw IllegalArgumentException("Vault payload is corrupt or was tampered with.", e)
        }

        val vaultData = VaultData.fromJsonString(String(plaintextBytes, Charsets.UTF_8))
        return UnlockResult(vaultData, vaultKey, envelope)
    }

    fun unlockVaultWithKey(envelopeJsonStr: String, vaultKey: SecretKeySpec): UnlockResult {
        val envelope = JSONObject(envelopeJsonStr)
        if (envelope.optString("format") != "PV02") {
            throw IllegalArgumentException("Unsupported vault format: ${envelope.optString("format")}")
        }

        val vaultObj = envelope.getJSONObject("vault")
        val vaultNonce = Base64.decode(vaultObj.getString("nonce"), Base64.DEFAULT)
        val encVaultData = Base64.decode(vaultObj.getString("data"), Base64.DEFAULT)

        val cipherData = Cipher.getInstance("AES/GCM/NoPadding")
        cipherData.init(Cipher.DECRYPT_MODE, vaultKey, GCMParameterSpec(TAG_SIZE_BITS, vaultNonce))
        cipherData.updateAAD("VAULT_PAYLOAD".toByteArray(Charsets.UTF_8))
        val plaintextBytes = try {
            cipherData.doFinal(encVaultData)
        } catch (e: Exception) {
            throw IllegalArgumentException("Vault payload decryption failed with biometric key.", e)
        }

        val vaultData = VaultData.fromJsonString(String(plaintextBytes, Charsets.UTF_8))
        return UnlockResult(vaultData, vaultKey, envelope)
    }

    fun reencryptVault(vaultData: VaultData, vaultKey: SecretKeySpec, envelope: JSONObject): String {
        vaultData.updatedAt = System.currentTimeMillis() / 1000
        val plaintext = vaultData.toJsonString().toByteArray(Charsets.UTF_8)
        val nonce = ByteArray(NONCE_SIZE).apply { secureRandom.nextBytes(this) }

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, vaultKey, GCMParameterSpec(TAG_SIZE_BITS, nonce))
        cipher.updateAAD("VAULT_PAYLOAD".toByteArray(Charsets.UTF_8))
        val encryptedData = cipher.doFinal(plaintext)

        envelope.getJSONObject("vault").apply {
            put("nonce", Base64.encodeToString(nonce, Base64.NO_WRAP))
            put("data", Base64.encodeToString(encryptedData, Base64.NO_WRAP))
        }

        return envelope.toString()
    }

    fun resetMasterPassword(vaultKey: SecretKeySpec, newPassword: CharArray, envelope: JSONObject): String {
        val saltPw = ByteArray(SALT_SIZE).apply { secureRandom.nextBytes(this) }
        val keyPw = deriveKey(newPassword, saltPw, PBKDF2_PW_ROUNDS)
        val noncePw = ByteArray(NONCE_SIZE).apply { secureRandom.nextBytes(this) }

        val cipherPw = Cipher.getInstance("AES/GCM/NoPadding")
        cipherPw.init(Cipher.ENCRYPT_MODE, keyPw, GCMParameterSpec(TAG_SIZE_BITS, noncePw))
        cipherPw.updateAAD("SLOT_PW".toByteArray(Charsets.UTF_8))
        val encryptedVkPw = cipherPw.doFinal(vaultKey.encoded)

        envelope.put("slot_pw", JSONObject().apply {
            put("salt", Base64.encodeToString(saltPw, Base64.NO_WRAP))
            put("nonce", Base64.encodeToString(noncePw, Base64.NO_WRAP))
            put("data", Base64.encodeToString(encryptedVkPw, Base64.NO_WRAP))
        })

        return envelope.toString()
    }
}

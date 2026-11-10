package com.pyvault

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

object BiometricHelper {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "PyVaultBiometricMasterKey"
    private const val BIOMETRIC_FILE = "biometric_vault_key.enc"
    private const val TAG_SIZE_BITS = 128

    fun isBiometricAvailable(context: Context): Boolean {
        val biometricManager = BiometricManager.from(context)
        return biometricManager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS
    }

    fun hasBiometricKey(context: Context): Boolean {
        val file = File(context.filesDir, BIOMETRIC_FILE)
        return file.exists() && file.length() > 0
    }

    fun clearBiometricKey(context: Context) {
        try {
            val file = File(context.filesDir, BIOMETRIC_FILE)
            if (file.exists()) {
                file.delete()
            }
            val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
            keyStore.load(null)
            if (keyStore.containsAlias(KEY_ALIAS)) {
                keyStore.deleteEntry(KEY_ALIAS)
            }
        } catch (_: Exception) {}
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
        keyStore.load(null)
        if (keyStore.containsAlias(KEY_ALIAS)) {
            val entry = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry
            if (entry != null) return entry.secretKey
        }

        val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setUserAuthenticationRequired(true)
            .setKeySize(256)
            .build()
        keyGenerator.init(spec)
        return keyGenerator.generateKey()
    }

    fun saveVaultKeyWithBiometric(
        activity: AppCompatActivity,
        vaultKey: SecretKeySpec,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        try {
            val secretKey = getOrCreateKey()
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, secretKey)

            val promptInfo = BiometricPrompt.PromptInfo.Builder()
                .setTitle("Enable Fingerprint Unlock")
                .setSubtitle("Touch the sensor to verify and enable fingerprint login")
                .setNegativeButtonText("Cancel")
                .build()

            val executor = ContextCompat.getMainExecutor(activity)
            val biometricPrompt = BiometricPrompt(activity, executor, object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    try {
                        val authCipher = result.cryptoObject?.cipher ?: cipher
                        val iv = authCipher.iv
                        val encryptedKey = authCipher.doFinal(vaultKey.encoded)

                        val json = JSONObject().apply {
                            put("iv", Base64.encodeToString(iv, Base64.NO_WRAP))
                            put("data", Base64.encodeToString(encryptedKey, Base64.NO_WRAP))
                        }
                        File(activity.filesDir, BIOMETRIC_FILE).writeText(json.toString())
                        onSuccess()
                    } catch (e: Exception) {
                        onError("Failed to secure biometric key: ${e.message}")
                    }
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    super.onAuthenticationError(errorCode, errString)
                    onError(errString.toString())
                }
            })

            biometricPrompt.authenticate(promptInfo, BiometricPrompt.CryptoObject(cipher))
        } catch (e: Exception) {
            onError("Biometric setup failed: ${e.message}")
        }
    }

    fun unlockWithBiometric(
        activity: AppCompatActivity,
        onKeyRetrieved: (SecretKeySpec) -> Unit,
        onError: (String) -> Unit,
        onCancel: (() -> Unit)? = null,
        onUsePassword: (() -> Unit)? = null
    ) {
        val file = File(activity.filesDir, BIOMETRIC_FILE)
        if (!file.exists()) {
            onError("No biometric credentials registered yet. Unlock with Master Password first.")
            return
        }

        try {
            val json = JSONObject(file.readText())
            val iv = Base64.decode(json.getString("iv"), Base64.DEFAULT)
            val encryptedKey = Base64.decode(json.getString("data"), Base64.DEFAULT)

            val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
            keyStore.load(null)
            val secretKeyEntry = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry
                ?: throw IllegalStateException("Hardware key not found in Keystore.")

            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, secretKeyEntry.secretKey, GCMParameterSpec(TAG_SIZE_BITS, iv))

            val promptInfo = BiometricPrompt.PromptInfo.Builder()
                .setTitle("Unlock PyVault")
                .setSubtitle("Use your fingerprint to unlock your vault")
                .setNegativeButtonText("Use Password")
                .build()

            val executor = ContextCompat.getMainExecutor(activity)
            val biometricPrompt = BiometricPrompt(activity, executor, object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    try {
                        val authCipher = result.cryptoObject?.cipher ?: cipher
                        val vaultKeyBytes = authCipher.doFinal(encryptedKey)
                        onKeyRetrieved(SecretKeySpec(vaultKeyBytes, "AES"))
                    } catch (e: Exception) {
                        onError("Biometric decryption failed: ${e.message}")
                    }
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    super.onAuthenticationError(errorCode, errString)
                    when (errorCode) {
                        BiometricPrompt.ERROR_NEGATIVE_BUTTON -> {
                            if (onUsePassword != null) {
                                onUsePassword()
                            } else {
                                onCancel?.invoke()
                            }
                        }
                        BiometricPrompt.ERROR_USER_CANCELED -> {
                            onCancel?.invoke()
                        }
                        else -> {
                            onError(errString.toString())
                        }
                    }
                }
            })

            biometricPrompt.authenticate(promptInfo, BiometricPrompt.CryptoObject(cipher))
        } catch (e: Exception) {
            onError("Biometric authentication error: ${e.message}")
        }
    }
}

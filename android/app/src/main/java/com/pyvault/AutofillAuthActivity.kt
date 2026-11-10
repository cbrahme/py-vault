package com.pyvault

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.service.autofill.Dataset
import android.view.autofill.AutofillId
import android.view.autofill.AutofillManager
import android.view.autofill.AutofillValue
import android.widget.Button
import android.widget.EditText
import android.widget.RemoteViews
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import javax.crypto.spec.SecretKeySpec

class AutofillAuthActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_PACKAGE_NAME = "EXTRA_PACKAGE_NAME"
        const val EXTRA_WEB_DOMAIN = "EXTRA_WEB_DOMAIN"
        const val EXTRA_APP_LABEL = "EXTRA_APP_LABEL"
        const val EXTRA_USERNAME_ID = "EXTRA_USERNAME_ID"
        const val EXTRA_PASSWORD_ID = "EXTRA_PASSWORD_ID"
    }

    private var targetPackage: String = ""
    private var webDomain: String = ""
    private var appLabel: String = ""
    private var usernameId: AutofillId? = null
    private var passwordId: AutofillId? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        targetPackage = intent.getStringExtra(EXTRA_PACKAGE_NAME) ?: ""
        webDomain = intent.getStringExtra(EXTRA_WEB_DOMAIN) ?: ""
        appLabel = intent.getStringExtra(EXTRA_APP_LABEL) ?: ""
        usernameId = AutofillUtils.getAutofillId(intent, EXTRA_USERNAME_ID)
        passwordId = AutofillUtils.getAutofillId(intent, EXTRA_PASSWORD_ID)

        val vaultFile = File(filesDir, "vault.enc")
        if (!vaultFile.exists()) {
            Toast.makeText(this, "PyVault file not found", Toast.LENGTH_SHORT).show()
            setResult(Activity.RESULT_CANCELED)
            finish()
            return
        }

        // Biometric Security: Prompt Fingerprint first
        BiometricHelper.unlockWithBiometric(
            activity = this,
            onKeyRetrieved = { vaultKey ->
                processVaultWithKey(vaultKey)
            },
            onError = { errMsg ->
                // Biometric error or not yet configured: fallback to Master Password dialog
                showMasterPasswordFallback(errMsg)
            },
            onCancel = {
                setResult(Activity.RESULT_CANCELED)
                finish()
            },
            onUsePassword = {
                showMasterPasswordFallback(null)
            }
        )
    }

    private fun processVaultWithKey(vaultKey: SecretKeySpec) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val vaultFile = File(filesDir, "vault.enc")
                val jsonStr = vaultFile.readText()
                val unlockRes = Crypto.unlockVaultWithKey(jsonStr, vaultKey)
                withContext(Dispatchers.Main) {
                    handleDecryptedVault(unlockRes.vaultData)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@AutofillAuthActivity,
                        "Decryption failed: ${e.message}",
                        Toast.LENGTH_SHORT
                    ).show()
                    setResult(Activity.RESULT_CANCELED)
                    finish()
                }
            }
        }
    }

    private fun handleDecryptedVault(vaultData: VaultData) {
        val matchedEntry = findSmartMatch(vaultData.entries)
        if (matchedEntry != null) {
            deliverDataset(matchedEntry)
        } else {
            // Forward to Picker Activity if no exact match is identified
            val pickerIntent = Intent(this, AutofillPickerActivity::class.java).apply {
                putExtra(AutofillPickerActivity.EXTRA_PACKAGE_NAME, targetPackage)
                putExtra(AutofillPickerActivity.EXTRA_WEB_DOMAIN, webDomain)
                putExtra(AutofillPickerActivity.EXTRA_APP_LABEL, appLabel)
                putExtra(AutofillPickerActivity.EXTRA_USERNAME_ID, usernameId)
                putExtra(AutofillPickerActivity.EXTRA_PASSWORD_ID, passwordId)
                flags = Intent.FLAG_ACTIVITY_FORWARD_RESULT
            }
            startActivity(pickerIntent)
            finish()
        }
    }

    private fun findSmartMatch(entries: List<VaultEntry>): VaultEntry? {
        val cleanDomain = AutofillUtils.cleanDomain(webDomain)

        // 1. Match by Web Domain if available
        if (cleanDomain.isNotEmpty()) {
            val domainMatch = entries.firstOrNull { entry ->
                val entryDomain = AutofillUtils.cleanDomain(entry.url)
                entryDomain.isNotEmpty() && (entryDomain.contains(cleanDomain) || cleanDomain.contains(entryDomain))
            }
            if (domainMatch != null) return domainMatch
        }

        // 2. Exact match by App Label
        if (appLabel.isNotBlank()) {
            val exactLabelMatch = entries.firstOrNull { entry ->
                entry.title.equals(appLabel, ignoreCase = true)
            }
            if (exactLabelMatch != null) return exactLabelMatch
        }

        // 3. Substring match by App Label / Title
        if (appLabel.isNotBlank()) {
            val partialMatch = entries.firstOrNull { entry ->
                entry.title.contains(appLabel, ignoreCase = true) ||
                        appLabel.contains(entry.title, ignoreCase = true)
            }
            if (partialMatch != null) return partialMatch
        }

        // 4. Match by package name in entry url or notes
        if (targetPackage.isNotBlank()) {
            val packageMatch = entries.firstOrNull { entry ->
                entry.notes.contains(targetPackage, ignoreCase = true) ||
                        entry.url.contains(targetPackage, ignoreCase = true)
            }
            if (packageMatch != null) return packageMatch

            val cleanPkg = AutofillUtils.cleanPackageName(targetPackage)
            if (cleanPkg.isNotBlank()) {
                val pkgNameMatch = entries.firstOrNull { entry ->
                    entry.title.contains(cleanPkg, ignoreCase = true) ||
                            cleanPkg.contains(entry.title, ignoreCase = true)
                }
                if (pkgNameMatch != null) return pkgNameMatch
            }
        }

        return null
    }

    private fun deliverDataset(entry: VaultEntry) {
        val responseDataset = Dataset.Builder()
        val fillViews = RemoteViews(packageName, R.layout.item_autofill_dataset).apply {
            setTextViewText(R.id.tvAutofillTitle, entry.title)
            setTextViewText(R.id.tvAutofillSubtitle, entry.username)
        }

        var hasFilled = false
        if (usernameId != null && entry.username.isNotEmpty()) {
            responseDataset.setValue(usernameId!!, AutofillValue.forText(entry.username), fillViews)
            hasFilled = true
        }

        if (passwordId != null && entry.password.isNotEmpty() && passwordId != usernameId) {
            if (!hasFilled) {
                responseDataset.setValue(passwordId!!, AutofillValue.forText(entry.password), fillViews)
            } else {
                responseDataset.setValue(passwordId!!, AutofillValue.forText(entry.password))
            }
            hasFilled = true
        }

        if (hasFilled) {
            val replyIntent = Intent().apply {
                putExtra(AutofillManager.EXTRA_AUTHENTICATION_RESULT, responseDataset.build())
            }
            setResult(Activity.RESULT_OK, replyIntent)
        } else {
            setResult(Activity.RESULT_CANCELED)
        }
        finish()
    }

    private fun showMasterPasswordFallback(errMsg: String?) {
        if (!errMsg.isNullOrBlank()) {
            Toast.makeText(this, errMsg, Toast.LENGTH_SHORT).show()
        }

        val dialogView = LayoutInflater.from(this).inflate(R.layout.autofill_auth_dialog, null)
        val etPassword = dialogView.findViewById<EditText>(R.id.etAuthMasterPassword)
        val btnUnlock = dialogView.findViewById<Button>(R.id.btnAuthUnlock)
        val btnCancel = dialogView.findViewById<Button>(R.id.btnAuthCancel)

        val dialog = AlertDialog.Builder(this)
            .setView(dialogView)
            .setCancelable(false)
            .create()

        btnCancel.setOnClickListener {
            dialog.dismiss()
            setResult(Activity.RESULT_CANCELED)
            finish()
        }

        btnUnlock.setOnClickListener {
            val password = etPassword.text.toString()
            if (password.isEmpty()) {
                etPassword.error = "Password required"
                return@setOnClickListener
            }

            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    val vaultFile = File(filesDir, "vault.enc")
                    val jsonStr = vaultFile.readText()
                    val unlockRes = Crypto.unlockVault(jsonStr, password.toCharArray(), false)
                    withContext(Dispatchers.Main) {
                        dialog.dismiss()
                        handleDecryptedVault(unlockRes.vaultData)
                    }
                } catch (e: Exception) {
                    withContext(Dispatchers.Main) {
                        etPassword.error = "Incorrect Master Password"
                    }
                }
            }
        }

        dialog.show()
    }
}

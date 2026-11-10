package com.pyvault

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.service.autofill.Dataset
import android.view.autofill.AutofillId
import android.view.autofill.AutofillManager
import android.view.autofill.AutofillValue
import android.widget.Button
import android.widget.EditText
import android.widget.RemoteViews
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import javax.crypto.spec.SecretKeySpec

class AutofillPickerActivity : AppCompatActivity() {

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

    private val allEntries = mutableListOf<VaultEntry>()
    private val filteredEntries = mutableListOf<VaultEntry>()
    private lateinit var adapter: PickerAdapter

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

        // Biometric Security: Fingerprint prompt first
        BiometricHelper.unlockWithBiometric(
            activity = this,
            onKeyRetrieved = { vaultKey ->
                processVaultWithKey(vaultKey)
            },
            onError = { errMsg ->
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
                    showPickerUI(unlockRes.vaultData)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@AutofillPickerActivity,
                        "Decryption failed: ${e.message}",
                        Toast.LENGTH_SHORT
                    ).show()
                    setResult(Activity.RESULT_CANCELED)
                    finish()
                }
            }
        }
    }

    private fun showPickerUI(vaultData: VaultData) {
        setContentView(R.layout.activity_autofill_picker)

        allEntries.clear()
        // Sort entries with smart matches first, then alphabetically by title
        val sorted = vaultData.entries.sortedWith(
            compareByDescending<VaultEntry> { entry ->
                isSuggestedEntry(entry)
            }.thenBy { it.title.lowercase() }
        )
        allEntries.addAll(sorted)
        filteredEntries.clear()
        filteredEntries.addAll(allEntries)

        val rvEntries = findViewById<RecyclerView>(R.id.rvPickerEntries)
        val etSearch = findViewById<EditText>(R.id.etPickerSearch)
        val tvEmpty = findViewById<TextView>(R.id.tvPickerEmpty)
        val btnClose = findViewById<Button>(R.id.btnPickerClose)

        adapter = PickerAdapter(filteredEntries) { selectedEntry ->
            deliverDataset(selectedEntry)
        }

        rvEntries.layoutManager = LinearLayoutManager(this)
        rvEntries.adapter = adapter

        updateEmptyState(tvEmpty)

        btnClose.setOnClickListener {
            setResult(Activity.RESULT_CANCELED)
            finish()
        }

        etSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {
                filterEntries(s?.toString().orEmpty(), tvEmpty)
            }
            override fun afterTextChanged(s: Editable?) {}
        })
    }

    private fun isSuggestedEntry(entry: VaultEntry): Boolean {
        if (appLabel.isNotBlank() && entry.title.contains(appLabel, ignoreCase = true)) {
            return true
        }
        if (webDomain.isNotBlank() && entry.url.contains(webDomain, ignoreCase = true)) {
            return true
        }
        if (targetPackage.isNotBlank() && (entry.notes.contains(targetPackage, ignoreCase = true) || entry.url.contains(targetPackage, ignoreCase = true))) {
            return true
        }
        return false
    }

    private fun filterEntries(query: String, tvEmpty: TextView) {
        val q = query.trim().lowercase()
        filteredEntries.clear()
        if (q.isEmpty()) {
            filteredEntries.addAll(allEntries)
        } else {
            val matches = allEntries.filter {
                it.title.lowercase().contains(q) ||
                        it.username.lowercase().contains(q) ||
                        it.url.lowercase().contains(q)
            }
            filteredEntries.addAll(matches)
        }
        adapter.notifyDataSetChanged()
        updateEmptyState(tvEmpty)
    }

    private fun updateEmptyState(tvEmpty: TextView) {
        tvEmpty.visibility = if (filteredEntries.isEmpty()) View.VISIBLE else View.GONE
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
                        showPickerUI(unlockRes.vaultData)
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

class PickerAdapter(
    private val items: List<VaultEntry>,
    private val onItemClick: (VaultEntry) -> Unit
) : RecyclerView.Adapter<PickerAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val tvTitle: TextView = view.findViewById(R.id.tvPickerTitle)
        val tvUsername: TextView = view.findViewById(R.id.tvPickerUsername)
        val tvUrl: TextView = view.findViewById(R.id.tvPickerUrl)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_picker_entry, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]
        holder.tvTitle.text = item.title
        holder.tvUsername.text = if (item.username.isNotEmpty()) item.username else "No username"

        if (item.url.isNotBlank()) {
            holder.tvUrl.text = item.url
            holder.tvUrl.visibility = View.VISIBLE
        } else {
            holder.tvUrl.visibility = View.GONE
        }

        holder.itemView.setOnClickListener {
            onItemClick(item)
        }
    }

    override fun getItemCount(): Int = items.size
}

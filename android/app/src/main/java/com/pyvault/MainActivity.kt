package com.pyvault

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PersistableBundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.security.SecureRandom
import java.util.concurrent.Executor
import javax.crypto.spec.SecretKeySpec

class MainActivity : AppCompatActivity() {

    private lateinit var lockOverlay: View
    private lateinit var tvLockSubtitle: TextView
    private lateinit var etMasterPassword: EditText
    private lateinit var btnUnlock: Button
    private lateinit var btnSyncLock: Button
    private lateinit var btnBiometric: Button
    private lateinit var btnForgot: Button
    private lateinit var rvEntries: RecyclerView
    private lateinit var etSearch: EditText
    private lateinit var tvEmpty: TextView
    private lateinit var btnSync: Button
    private lateinit var btnLock: Button
    private lateinit var fabAdd: View

    private var activeVault: VaultData? = null
    private var activeVaultKey: SecretKeySpec? = null
    private var activeEnvelope: JSONObject? = null

    private lateinit var adapter: EntryAdapter
    private val displayedEntries = mutableListOf<VaultEntry>()

    private val clipboardHandler = Handler(Looper.getMainLooper())
    private var clipboardClearRunnable: Runnable? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        setupListeners()
        updateLockScreenUI()
    }

    private fun initViews() {
        lockOverlay = findViewById(R.id.lockOverlay)
        tvLockSubtitle = findViewById(R.id.tvLockSubtitle)
        etMasterPassword = findViewById(R.id.etMasterPassword)
        btnUnlock = findViewById(R.id.btnUnlock)
        btnSyncLock = findViewById(R.id.btnSyncLock)
        btnBiometric = findViewById(R.id.btnBiometric)
        btnForgot = findViewById(R.id.btnForgot)
        rvEntries = findViewById(R.id.rvEntries)
        etSearch = findViewById(R.id.etSearch)
        tvEmpty = findViewById(R.id.tvEmpty)
        btnSync = findViewById(R.id.btnSync)
        btnLock = findViewById(R.id.btnLock)
        fabAdd = findViewById(R.id.fabAdd)

        adapter = EntryAdapter(displayedEntries,
            onCopyUser = { entry -> copyToClipboard("Username", entry.username, isSensitive = false) },
            onCopyPass = { entry, callback ->
                copyToClipboard("Password", entry.password, isSensitive = true)
                callback("Copied! Auto-clearing in 20s")
            },
            onEdit = { entry -> showEditEntryDialog(entry) }
        )
        rvEntries.layoutManager = LinearLayoutManager(this)
        rvEntries.adapter = adapter
    }

    private fun setupListeners() {
        btnUnlock.setOnClickListener {
            val passStr = etMasterPassword.text.toString()
            if (passStr.isEmpty()) {
                val msg = if (File(filesDir, "vault.enc").exists()) "Please enter your master password" else "Please enter a master password to create vault"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            unlockVault(passStr.toCharArray())
        }

        btnSyncLock.setOnClickListener {
            showSyncDialog()
        }

        btnBiometric.setOnClickListener {
            promptBiometric()
        }

        btnForgot.setOnClickListener {
            showRecoveryDialog()
        }

        btnLock.setOnClickListener {
            lockVault()
        }

        btnSync.setOnClickListener {
            showSyncDialog()
        }

        fabAdd.setOnClickListener {
            showAddEntryDialog()
        }

        etSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                filterEntries(s?.toString() ?: "")
            }
            override fun afterTextChanged(s: Editable?) {}
        })
    }

    private fun unlockVault(password: CharArray) {
        val vaultFile = File(filesDir, "vault.enc")
        if (!vaultFile.exists()) {
            // New local vault initialization
            lifecycleScope.launch(Dispatchers.IO) {
                val newVault = VaultData()
                val (envelopeStr, recoveryKey) = Crypto.createNewVault(newVault, password)
                vaultFile.writeText(envelopeStr)

                val unlockRes = Crypto.unlockVault(envelopeStr, password, false)
                withContext(Dispatchers.Main) {
                    activeVault = unlockRes.vaultData
                    activeVaultKey = unlockRes.vaultKey
                    activeEnvelope = unlockRes.envelope
                    onVaultUnlocked()
                    showRecoveryKeyAlert(recoveryKey)
                }
            }
            return
        }

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val jsonStr = vaultFile.readText()
                val unlockRes = Crypto.unlockVault(jsonStr, password, false)
                withContext(Dispatchers.Main) {
                    activeVault = unlockRes.vaultData
                    activeVaultKey = unlockRes.vaultKey
                    activeEnvelope = unlockRes.envelope
                    onVaultUnlocked()
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Incorrect password or corrupt file.", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showRecoveryKeyAlert(recoveryKey: String) {
        AlertDialog.Builder(this)
            .setTitle("⚠️ Save Your Recovery Key")
            .setMessage("If you ever forget your Master Password, this key is the ONLY way to recover your vault:\n\n$recoveryKey\n\nWrite this down or save it safely.")
            .setPositiveButton("Copy & Continue") { _, _ ->
                copyToClipboard("Recovery Key", recoveryKey)
            }
            .setCancelable(false)
            .show()
    }

    private fun showRecoveryDialog() {
        val vaultFile = File(filesDir, "vault.enc")
        if (!vaultFile.exists()) {
            Toast.makeText(this, "No vault exists to recover.", Toast.LENGTH_SHORT).show()
            return
        }

        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_sync, null)
        val etKey = dialogView.findViewById<EditText>(R.id.etHost)
        val etNewPw = dialogView.findViewById<EditText>(R.id.etPin)
        etKey.hint = "Recovery Key (RCV-XXXX-...)"
        etNewPw.hint = "New Master Password"
        etNewPw.inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD

        AlertDialog.Builder(this)
            .setTitle("Recover Vault")
            .setView(dialogView)
            .setPositiveButton("Reset & Unlock") { _, _ ->
                val key = etKey.text.toString().trim()
                val newPw = etNewPw.text.toString()
                if (key.isNotEmpty() && newPw.isNotEmpty()) {
                    performRecovery(key, newPw.toCharArray())
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun performRecovery(recoveryKey: String, newPassword: CharArray) {
        val vaultFile = File(filesDir, "vault.enc")
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val jsonStr = vaultFile.readText()
                val unlockRes = Crypto.unlockVault(jsonStr, recoveryKey.toCharArray(), true)
                val updatedJson = Crypto.resetMasterPassword(unlockRes.vaultKey, newPassword, unlockRes.envelope)
                vaultFile.writeText(updatedJson)
                BiometricHelper.clearBiometricKey(this@MainActivity)

                withContext(Dispatchers.Main) {
                    activeVault = unlockRes.vaultData
                    activeVaultKey = unlockRes.vaultKey
                    activeEnvelope = JSONObject(updatedJson)
                    onVaultUnlocked()
                    Toast.makeText(this@MainActivity, "Vault recovered! New Master Password active.", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Recovery failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun onVaultUnlocked() {
        lockOverlay.visibility = View.GONE
        fabAdd.visibility = View.VISIBLE
        etMasterPassword.text.clear()
        filterEntries(etSearch.text.toString())
        checkOfferBiometric()
    }

    private fun checkOfferBiometric() {
        val vk = activeVaultKey ?: return
        if (BiometricHelper.isBiometricAvailable(this) && !BiometricHelper.hasBiometricKey(this)) {
            AlertDialog.Builder(this)
                .setTitle("Enable Fingerprint Unlock?")
                .setMessage("Would you like to enable fingerprint unlock for quick access to PyVault?")
                .setPositiveButton("Enable") { _, _ ->
                    BiometricHelper.saveVaultKeyWithBiometric(
                        this,
                        vk,
                        onSuccess = {
                            Toast.makeText(this, "Fingerprint unlock enabled!", Toast.LENGTH_SHORT).show()
                        },
                        onError = { err ->
                            Toast.makeText(this, err, Toast.LENGTH_SHORT).show()
                        }
                    )
                }
                .setNegativeButton("Not Now", null)
                .show()
        }
    }

    private fun lockVault() {
        activeVault = null
        activeVaultKey = null
        activeEnvelope = null
        lockOverlay.visibility = View.VISIBLE
        fabAdd.visibility = View.GONE
        displayedEntries.clear()
        adapter.notifyDataSetChanged()
        updateLockScreenUI()
        Toast.makeText(this, "Vault locked", Toast.LENGTH_SHORT).show()
    }

    private fun updateLockScreenUI() {
        val vaultExists = File(filesDir, "vault.enc").exists()
        val hasBiometric = BiometricHelper.isBiometricAvailable(this) && BiometricHelper.hasBiometricKey(this)
        if (vaultExists) {
            tvLockSubtitle.text = "Enter Master Password to unlock"
            btnUnlock.text = "Unlock Vault"
            etMasterPassword.hint = "Master Password"
            btnBiometric.visibility = if (hasBiometric) View.VISIBLE else View.GONE
            btnForgot.visibility = View.VISIBLE
        } else {
            tvLockSubtitle.text = "No vault found on this device.\nEnter a password to create one, or Sync from laptop."
            btnUnlock.text = "Create New Vault"
            etMasterPassword.hint = "Create Master Password"
            btnBiometric.visibility = View.GONE
            btnForgot.visibility = View.GONE
        }
        btnSyncLock.text = "Sync"
    }

    private fun saveActiveVault() {
        val vault = activeVault ?: return
        val key = activeVaultKey ?: return
        val envelope = activeEnvelope ?: return

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val updatedJson = Crypto.reencryptVault(vault, key, envelope)
                val vaultFile = File(filesDir, "vault.enc")
                vaultFile.writeText(updatedJson)
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Failed to save: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun filterEntries(query: String) {
        val vault = activeVault ?: return
        val q = query.trim().lowercase()

        displayedEntries.clear()
        if (q.isEmpty()) {
            displayedEntries.addAll(vault.entries)
        } else {
            displayedEntries.addAll(
                vault.entries.filter {
                    it.title.lowercase().contains(q) ||
                    it.username.lowercase().contains(q) ||
                    it.url.lowercase().contains(q)
                }
            )
        }

        displayedEntries.sortBy { it.title.lowercase() }
        adapter.notifyDataSetChanged()
        tvEmpty.visibility = if (displayedEntries.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun copyToClipboard(label: String, text: String, isSensitive: Boolean = false) {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText(label, text)
        if (isSensitive) {
            val bundle = PersistableBundle()
            bundle.putBoolean("android.content.extra.IS_SENSITIVE", true)
            clip.description.extras = bundle
        }
        clipboard.setPrimaryClip(clip)
        Toast.makeText(this, "$label copied to clipboard", Toast.LENGTH_SHORT).show()

        clipboardClearRunnable?.let { clipboardHandler.removeCallbacks(it) }
        clipboardClearRunnable = Runnable {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                clipboard.clearPrimaryClip()
            } else {
                val emptyClip = ClipData.newPlainText("", "")
                val bundle = PersistableBundle()
                bundle.putBoolean("android.content.extra.IS_SENSITIVE", true)
                emptyClip.description.extras = bundle
                clipboard.setPrimaryClip(emptyClip)
            }
            Toast.makeText(this, "Clipboard cleared for security", Toast.LENGTH_SHORT).show()
        }
        clipboardHandler.postDelayed(clipboardClearRunnable!!, 20_000)
    }

    private fun showAddEntryDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_add_entry, null)
        val etTitle = dialogView.findViewById<EditText>(R.id.etTitle)
        val etUser = dialogView.findViewById<EditText>(R.id.etUsername)
        val etPass = dialogView.findViewById<EditText>(R.id.etPassword)
        val etUrl = dialogView.findViewById<EditText>(R.id.etUrl)
        val btnGen = dialogView.findViewById<Button>(R.id.btnGenerate)

        btnGen.setOnClickListener {
            etPass.setText(generateRandomPassword(20))
        }

        AlertDialog.Builder(this)
            .setView(dialogView)
            .setPositiveButton("Save") { _, _ ->
                val title = etTitle.text.toString().trim()
                val user = etUser.text.toString().trim()
                val pass = etPass.text.toString()
                val url = etUrl.text.toString().trim()

                if (title.isNotEmpty() && pass.isNotEmpty()) {
                    val entry = VaultEntry(title = title, username = user, password = pass, url = url)
                    activeVault?.entries?.add(entry)
                    saveActiveVault()
                    filterEntries(etSearch.text.toString())
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showEditEntryDialog(entry: VaultEntry) {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_add_entry, null)
        val tvTitle = dialogView.findViewById<TextView>(R.id.tvDialogTitle)
        tvTitle?.text = "Edit Account"

        val etTitle = dialogView.findViewById<EditText>(R.id.etTitle)
        val etUser = dialogView.findViewById<EditText>(R.id.etUsername)
        val etPass = dialogView.findViewById<EditText>(R.id.etPassword)
        val etUrl = dialogView.findViewById<EditText>(R.id.etUrl)
        val btnGen = dialogView.findViewById<Button>(R.id.btnGenerate)

        etTitle.setText(entry.title)
        etUser.setText(entry.username)
        etPass.setText(entry.password)
        etUrl.setText(entry.url)

        btnGen.setOnClickListener {
            etPass.setText(generateRandomPassword(20))
        }

        AlertDialog.Builder(this)
            .setView(dialogView)
            .setPositiveButton("Save") { _, _ ->
                val newTitle = etTitle.text.toString().trim()
                val newUser = etUser.text.toString().trim()
                val newPass = etPass.text.toString()
                val newUrl = etUrl.text.toString().trim()

                if (newTitle.isNotEmpty() && newPass.isNotEmpty()) {
                    entry.title = newTitle
                    entry.username = newUser
                    entry.password = newPass
                    entry.url = newUrl
                    entry.updatedAt = System.currentTimeMillis() / 1000
                    saveActiveVault()
                    filterEntries(etSearch.text.toString())
                    Toast.makeText(this, "Account updated", Toast.LENGTH_SHORT).show()
                }
            }
            .setNeutralButton("Delete") { _, _ ->
                AlertDialog.Builder(this)
                    .setTitle("Delete Account")
                    .setMessage("Are you sure you want to delete ${entry.title}?")
                    .setPositiveButton("Delete") { _, _ ->
                        activeVault?.entries?.remove(entry)
                        saveActiveVault()
                        filterEntries(etSearch.text.toString())
                        Toast.makeText(this, "Account deleted", Toast.LENGTH_SHORT).show()
                    }
                    .setNegativeButton("Cancel", null)
                    .show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showSyncDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_sync, null)
        val etHost = dialogView.findViewById<EditText>(R.id.etHost)
        val etPin = dialogView.findViewById<EditText>(R.id.etPin)
        val btnScanQr = dialogView.findViewById<Button>(R.id.btnScanQr)

        val prefs = getSharedPreferences("pyvault_prefs", Context.MODE_PRIVATE)
        val lastHost = prefs.getString("last_sync_host", "")
        if (!lastHost.isNullOrEmpty()) {
            etHost.setText(lastHost)
        }

        btnScanQr?.setOnClickListener {
            val scanner = GmsBarcodeScanning.getClient(this)
            scanner.startScan()
                .addOnSuccessListener { barcode: Barcode ->
                    val raw = barcode.rawValue ?: return@addOnSuccessListener
                    val (h, p) = parseSyncQr(raw)
                    if (h.isNotEmpty()) etHost.setText(h)
                    if (p.isNotEmpty()) etPin.setText(p)
                    Toast.makeText(this, "Scanned: $h", Toast.LENGTH_SHORT).show()
                }
                .addOnFailureListener { e: Exception ->
                    Toast.makeText(this, "Scan cancelled: ${e.message}", Toast.LENGTH_SHORT).show()
                }
        }

        AlertDialog.Builder(this)
            .setView(dialogView)
            .setPositiveButton("Download from Laptop") { _, _ ->
                val host = etHost.text.toString().trim()
                val pin = etPin.text.toString().trim()
                if (host.isNotEmpty()) {
                    prefs.edit().putString("last_sync_host", host).apply()
                }
                performSyncDownload(host, pin)
            }
            .setNeutralButton("Upload to Laptop") { _, _ ->
                val host = etHost.text.toString().trim()
                val pin = etPin.text.toString().trim()
                if (host.isNotEmpty()) {
                    prefs.edit().putString("last_sync_host", host).apply()
                }
                performSyncUpload(host, pin)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun parseSyncQr(raw: String): Pair<String, String> {
        try {
            val uri = android.net.Uri.parse(raw)
            val host = if (uri.port != -1) "${uri.host}:${uri.port}" else (uri.host ?: "")
            val pin = uri.getQueryParameter("pin") ?: ""
            if (host.isNotEmpty()) return Pair(host, pin)
        } catch (_: Exception) {}
        return Pair(raw.trim(), "")
    }

    private fun performSyncDownload(host: String, pin: String) {
        lifecycleScope.launch {
            val result = SyncClient.downloadVault(this@MainActivity, host, pin)
            if (result.isSuccess) {
                BiometricHelper.clearBiometricKey(this@MainActivity)
                Toast.makeText(this@MainActivity, "Download successful! Enter Master Password to unlock.", Toast.LENGTH_LONG).show()
                lockVault()
            } else {
                Toast.makeText(this@MainActivity, "Sync failed: ${result.exceptionOrNull()?.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun performSyncUpload(host: String, pin: String) {
        lifecycleScope.launch {
            val result = SyncClient.uploadVault(this@MainActivity, host, pin)
            if (result.isSuccess) {
                Toast.makeText(this@MainActivity, "Upload to laptop successful!", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this@MainActivity, "Upload failed: ${result.exceptionOrNull()?.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun promptBiometric() {
        val vaultFile = File(filesDir, "vault.enc")
        if (!vaultFile.exists()) {
            Toast.makeText(this, "No vault found", Toast.LENGTH_SHORT).show()
            return
        }

        BiometricHelper.unlockWithBiometric(
            this,
            onKeyRetrieved = { vaultKey ->
                lifecycleScope.launch(Dispatchers.IO) {
                    try {
                        val jsonStr = vaultFile.readText()
                        val unlockRes = Crypto.unlockVaultWithKey(jsonStr, vaultKey)
                        withContext(Dispatchers.Main) {
                            activeVault = unlockRes.vaultData
                            activeVaultKey = unlockRes.vaultKey
                            activeEnvelope = unlockRes.envelope
                            onVaultUnlocked()
                            Toast.makeText(this@MainActivity, "Unlocked with fingerprint", Toast.LENGTH_SHORT).show()
                        }
                    } catch (e: Exception) {
                        withContext(Dispatchers.Main) {
                            Toast.makeText(this@MainActivity, "Biometric unlock failed: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            },
            onError = { errMsg ->
                Toast.makeText(this, errMsg, Toast.LENGTH_SHORT).show()
            }
        )
    }

    private fun generateRandomPassword(length: Int = 20): String {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()-_=+[]{}|;:,.<>?"
        val rnd = SecureRandom()
        val sb = StringBuilder(length)
        for (i in 0 until length) {
            sb.append(chars[rnd.nextInt(chars.length)])
        }
        return sb.toString()
    }

    override fun onPause() {
        super.onPause()
        lockVault()
    }
}

class EntryAdapter(
    private val items: List<VaultEntry>,
    private val onCopyUser: (VaultEntry) -> Unit,
    private val onCopyPass: (VaultEntry, (String) -> Unit) -> Unit,
    private val onEdit: (VaultEntry) -> Unit
) : RecyclerView.Adapter<EntryAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val tvTitle: TextView = view.findViewById(R.id.tvTitle)
        val tvUsername: TextView = view.findViewById(R.id.tvUsername)
        val btnEdit: Button = view.findViewById(R.id.btnEdit)
        val btnCopyUser: Button = view.findViewById(R.id.btnCopyUser)
        val btnCopyPass: Button = view.findViewById(R.id.btnCopyPass)
        val tvStatus: TextView = view.findViewById(R.id.tvStatus)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_entry, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]
        holder.tvTitle.text = item.title
        holder.tvUsername.text = if (item.username.isNotEmpty()) item.username else "No username"

        holder.btnCopyUser.setOnClickListener { onCopyUser(item) }
        holder.btnCopyPass.setOnClickListener {
            onCopyPass(item) { msg ->
                holder.tvStatus.text = msg
                holder.tvStatus.visibility = View.VISIBLE
                holder.tvStatus.postDelayed({
                    holder.tvStatus.visibility = View.GONE
                }, 3000)
            }
        }
        holder.btnEdit.setOnClickListener { onEdit(item) }
        holder.itemView.setOnClickListener { onEdit(item) }
    }

    override fun getItemCount() = items.size
}

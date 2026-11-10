package com.pyvault

import android.app.PendingIntent
import android.app.assist.AssistStructure
import android.content.Intent
import android.os.Build
import android.os.CancellationSignal
import android.service.autofill.AutofillService
import android.service.autofill.Dataset
import android.service.autofill.FillCallback
import android.service.autofill.FillRequest
import android.service.autofill.FillResponse
import android.service.autofill.SaveCallback
import android.service.autofill.SaveRequest
import android.text.InputType
import android.util.Log
import android.view.View
import android.view.autofill.AutofillId
import android.view.autofill.AutofillValue
import android.widget.RemoteViews
import java.io.File

class PyVaultAutofillService : AutofillService() {

    companion object {
        private const val TAG = "PyVaultAutofill"
    }

    override fun onFillRequest(
        request: FillRequest,
        cancellationSignal: CancellationSignal,
        callback: FillCallback
    ) {
        if (cancellationSignal.isCanceled) {
            return
        }

        try {
            handleFillRequest(request, cancellationSignal, callback)
        } catch (t: Throwable) {
            Log.e(TAG, "Unhandled exception in onFillRequest", t)
            try {
                callback.onSuccess(null)
            } catch (_: Exception) {}
        }
    }

    private fun handleFillRequest(
        request: FillRequest,
        cancellationSignal: CancellationSignal,
        callback: FillCallback
    ) {
        val fillContexts = request.fillContexts
        if (fillContexts.isNullOrEmpty()) {
            callback.onSuccess(null)
            return
        }

        val structure = fillContexts.lastOrNull()?.structure
        if (structure == null) {
            callback.onSuccess(null)
            return
        }

        val packageName = structure.activityComponent?.packageName ?: ""
        // Do not autofill inside PyVault itself or when package is unknown
        if (packageName.isBlank() || packageName == this.packageName) {
            callback.onSuccess(null)
            return
        }

        val parsed = ParsedStructure()
        val windowCount = structure.windowNodeCount
        for (i in 0 until windowCount) {
            if (cancellationSignal.isCanceled) return
            val windowNode = structure.getWindowNodeAt(i) ?: continue
            val root = windowNode.rootViewNode ?: continue
            traverseNode(root, parsed, cancellationSignal)
        }

        // If neither username nor password field is found, do not offer autofill
        if (parsed.usernameId == null && parsed.passwordId == null) {
            callback.onSuccess(null)
            return
        }

        // Only offer autofill if a vault file actually exists
        val vaultFile = File(filesDir, "vault.enc")
        if (!vaultFile.exists() || vaultFile.length() == 0L) {
            callback.onSuccess(null)
            return
        }

        // Resolve application label / title for Smart Match
        val appLabel = try {
            val appInfo = packageManager.getApplicationInfo(packageName, 0)
            packageManager.getApplicationLabel(appInfo).toString()
        } catch (_: Exception) {
            ""
        }

        val targetDisplayName = when {
            !parsed.webDomain.isNullOrBlank() -> AutofillUtils.cleanDomain(parsed.webDomain!!)
            appLabel.isNotBlank() -> appLabel
            else -> AutofillUtils.cleanPackageName(packageName)
        }

        val responseBuilder = FillResponse.Builder()
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_CANCEL_CURRENT or PendingIntent.FLAG_MUTABLE
        } else {
            PendingIntent.FLAG_CANCEL_CURRENT
        }

        // --- Option A: Smart Match Dataset ---
        val smartViews = RemoteViews(this.packageName, R.layout.item_autofill_dataset).apply {
            setTextViewText(R.id.tvAutofillTitle, "PyVault: $targetDisplayName")
            setTextViewText(R.id.tvAutofillSubtitle, "Touch sensor to unlock & autofill")
        }

        val authIntent = Intent(this, AutofillAuthActivity::class.java).apply {
            putExtra(AutofillAuthActivity.EXTRA_PACKAGE_NAME, packageName)
            putExtra(AutofillAuthActivity.EXTRA_WEB_DOMAIN, parsed.webDomain ?: "")
            putExtra(AutofillAuthActivity.EXTRA_APP_LABEL, targetDisplayName)
            putExtra(AutofillAuthActivity.EXTRA_USERNAME_ID, parsed.usernameId)
            putExtra(AutofillAuthActivity.EXTRA_PASSWORD_ID, parsed.passwordId)
        }

        val authPendingIntent = PendingIntent.getActivity(this, 1001, authIntent, flags)

        val smartDatasetBuilder = Dataset.Builder(smartViews)
        if (parsed.usernameId != null) {
            smartDatasetBuilder.setValue(parsed.usernameId!!, null as AutofillValue?)
        }
        if (parsed.passwordId != null && parsed.passwordId != parsed.usernameId) {
            smartDatasetBuilder.setValue(parsed.passwordId!!, null as AutofillValue?)
        }
        smartDatasetBuilder.setAuthentication(authPendingIntent.intentSender)
        responseBuilder.addDataset(smartDatasetBuilder.build())

        // --- Option B: Search Picker Fallback Dataset ---
        val pickerViews = RemoteViews(this.packageName, R.layout.item_autofill_dataset).apply {
            setTextViewText(R.id.tvAutofillTitle, "🔍 Search PyVault")
            setTextViewText(R.id.tvAutofillSubtitle, "Pick any credential from vault")
        }

        val pickerIntent = Intent(this, AutofillPickerActivity::class.java).apply {
            putExtra(AutofillPickerActivity.EXTRA_PACKAGE_NAME, packageName)
            putExtra(AutofillPickerActivity.EXTRA_WEB_DOMAIN, parsed.webDomain ?: "")
            putExtra(AutofillPickerActivity.EXTRA_APP_LABEL, targetDisplayName)
            putExtra(AutofillPickerActivity.EXTRA_USERNAME_ID, parsed.usernameId)
            putExtra(AutofillPickerActivity.EXTRA_PASSWORD_ID, parsed.passwordId)
        }

        val pickerPendingIntent = PendingIntent.getActivity(this, 1002, pickerIntent, flags)

        val pickerDatasetBuilder = Dataset.Builder(pickerViews)
        if (parsed.usernameId != null) {
            pickerDatasetBuilder.setValue(parsed.usernameId!!, null as AutofillValue?)
        }
        if (parsed.passwordId != null && parsed.passwordId != parsed.usernameId) {
            pickerDatasetBuilder.setValue(parsed.passwordId!!, null as AutofillValue?)
        }
        pickerDatasetBuilder.setAuthentication(pickerPendingIntent.intentSender)
        responseBuilder.addDataset(pickerDatasetBuilder.build())

        callback.onSuccess(responseBuilder.build())
    }

    override fun onSaveRequest(request: SaveRequest, callback: SaveCallback) {
        callback.onSuccess()
    }

    private class ParsedStructure {
        var usernameId: AutofillId? = null
        var passwordId: AutofillId? = null
        var webDomain: String? = null
    }

    private fun traverseNode(
        node: AssistStructure.ViewNode?,
        parsed: ParsedStructure,
        cancellationSignal: CancellationSignal
    ) {
        if (node == null || cancellationSignal.isCanceled) return

        // Extract web domain if present
        if (!node.webDomain.isNullOrBlank()) {
            parsed.webDomain = node.webDomain
        }

        val hints = node.autofillHints?.filterNotNull()?.map { it.lowercase() } ?: emptyList()
        val hintText = node.hint?.toString()?.lowercase() ?: ""
        val idEntry = node.idEntry?.lowercase() ?: ""
        val inputType = node.inputType

        val variation = inputType and InputType.TYPE_MASK_VARIATION
        val isPasswordType = (inputType and InputType.TYPE_MASK_CLASS) == InputType.TYPE_CLASS_TEXT &&
                (variation == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
                 variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD ||
                 variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD)

        val isPasswordHint = hints.any { it.contains("password") } ||
                hintText.contains("password") || hintText.contains("passwort") ||
                idEntry.contains("password") || idEntry.contains("pass") || idEntry.contains("pwd")

        val isUsernameHint = hints.any {
            it.contains(View.AUTOFILL_HINT_USERNAME.lowercase()) ||
            it.contains(View.AUTOFILL_HINT_EMAIL_ADDRESS.lowercase()) ||
            it.contains("user") || it.contains("email") || it.contains("login")
        } || hintText.contains("username") || hintText.contains("email") ||
             hintText.contains("user") || hintText.contains("login") ||
             idEntry.contains("username") || idEntry.contains("email") ||
             idEntry.contains("user") || idEntry.contains("login")

        val autofillId = node.autofillId
        if (autofillId != null) {
            if (parsed.passwordId == null && (isPasswordType || isPasswordHint)) {
                parsed.passwordId = autofillId
            } else if (parsed.usernameId == null && isUsernameHint && !isPasswordType && !isPasswordHint) {
                parsed.usernameId = autofillId
            }
        }

        val childCount = node.childCount
        for (i in 0 until childCount) {
            traverseNode(node.getChildAt(i), parsed, cancellationSignal)
        }
    }
}

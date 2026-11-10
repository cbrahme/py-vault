package com.pyvault

import android.content.Intent
import android.os.Build
import android.view.autofill.AutofillId

object AutofillUtils {

    fun cleanDomain(rawDomain: String): String {
        var domain = rawDomain.lowercase().trim()
        if (domain.startsWith("http://")) domain = domain.substring(7)
        if (domain.startsWith("https://")) domain = domain.substring(8)
        if (domain.startsWith("www.")) domain = domain.substring(4)
        val slashIdx = domain.indexOf('/')
        if (slashIdx != -1) domain = domain.substring(0, slashIdx)
        val colonIdx = domain.indexOf(':')
        if (colonIdx != -1) domain = domain.substring(0, colonIdx)
        return domain
    }

    fun cleanPackageName(pkg: String): String {
        if (pkg.isBlank()) return ""
        val parts = pkg.split(".")
        val candidate = parts.lastOrNull {
            it !in listOf("android", "app", "mobile", "client", "release", "debug", "shopping")
        } ?: parts.lastOrNull() ?: pkg
        return candidate.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
    }

    fun getAutofillId(intent: Intent, key: String): AutofillId? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(key, AutofillId::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(key) as? AutofillId
        }
    }
}

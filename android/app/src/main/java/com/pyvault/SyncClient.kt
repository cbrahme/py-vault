package com.pyvault

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

object SyncClient {

    suspend fun downloadVault(context: Context, hostAndPort: String, pin: String): Result<File> =
        withContext(Dispatchers.IO) {
            try {
                val urlString = if (hostAndPort.startsWith("http://") || hostAndPort.startsWith("https://")) {
                    "$hostAndPort/vault?pin=$pin"
                } else {
                    "http://$hostAndPort/vault?pin=$pin"
                }

                val url = URL(urlString)
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = 8000
                connection.readTimeout = 8000

                val responseCode = connection.responseCode
                if (responseCode == 200) {
                    val targetFile = File(context.filesDir, "vault.enc")
                    connection.inputStream.use { input ->
                        FileOutputStream(targetFile).use { output ->
                            input.copyTo(output)
                        }
                    }
                    Result.success(targetFile)
                } else if (responseCode == 401) {
                    Result.failure(Exception("Sync failed: Incorrect PIN."))
                } else {
                    Result.failure(Exception("Sync failed: Server returned HTTP $responseCode"))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun uploadVault(context: Context, hostAndPort: String, pin: String): Result<Boolean> =
        withContext(Dispatchers.IO) {
            try {
                val vaultFile = File(context.filesDir, "vault.enc")
                if (!vaultFile.exists()) {
                    return@withContext Result.failure(Exception("Local vault file not found."))
                }

                val urlString = if (hostAndPort.startsWith("http://") || hostAndPort.startsWith("https://")) {
                    "$hostAndPort/upload?pin=$pin"
                } else {
                    "http://$hostAndPort/upload?pin=$pin"
                }

                val url = URL(urlString)
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(vaultFile.length())
                connection.connectTimeout = 8000
                connection.readTimeout = 8000

                vaultFile.inputStream().use { input ->
                    connection.outputStream.use { output ->
                        input.copyTo(output)
                    }
                }

                val responseCode = connection.responseCode
                if (responseCode == 200) {
                    Result.success(true)
                } else {
                    Result.failure(Exception("Upload failed: HTTP $responseCode"))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }
}

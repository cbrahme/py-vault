package com.pyvault

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class VaultEntry(
    val id: String = UUID.randomUUID().toString(),
    var title: String,
    var username: String,
    var password: String,
    var url: String = "",
    var notes: String = "",
    var updatedAt: Long = System.currentTimeMillis() / 1000
) {
    fun toJsonObject(): JSONObject {
        return JSONObject().apply {
            put("id", id)
            put("title", title)
            put("username", username)
            put("password", password)
            put("url", url)
            put("notes", notes)
            put("updated_at", updatedAt)
        }
    }

    companion object {
        fun fromJsonObject(obj: JSONObject): VaultEntry {
            return VaultEntry(
                id = obj.optString("id", UUID.randomUUID().toString()),
                title = obj.optString("title", ""),
                username = obj.optString("username", ""),
                password = obj.optString("password", ""),
                url = obj.optString("url", ""),
                notes = obj.optString("notes", ""),
                updatedAt = obj.optLong("updated_at", System.currentTimeMillis() / 1000)
            )
        }
    }
}

data class VaultData(
    val version: Int = 1,
    var updatedAt: Long = System.currentTimeMillis() / 1000,
    val entries: MutableList<VaultEntry> = mutableListOf()
) {
    fun toJsonString(): String {
        val root = JSONObject()
        root.put("version", version)
        root.put("updated_at", updatedAt)

        val arr = JSONArray()
        for (entry in entries) {
            arr.put(entry.toJsonObject())
        }
        root.put("entries", arr)
        return root.toString()
    }

    companion object {
        fun fromJsonString(jsonStr: String): VaultData {
            val root = JSONObject(jsonStr)
            val version = root.optInt("version", 1)
            val updatedAt = root.optLong("updated_at", System.currentTimeMillis() / 1000)

            val entriesList = mutableListOf<VaultEntry>()
            val arr = root.optJSONArray("entries")
            if (arr != null) {
                for (i in 0 until arr.length()) {
                    val entryObj = arr.getJSONObject(i)
                    entriesList.add(VaultEntry.fromJsonObject(entryObj))
                }
            }
            return VaultData(version, updatedAt, entriesList)
        }
    }
}

package com.bifang.companion

import android.content.SharedPreferences

/** One host's saved opt-in; changing it never clears other preferences or storage. */
class SharedStorageConsent(private val preferences: SharedPreferences, private val host: String) {
    init { require(host == "bifang" || host == "termux") }

    fun enabled(): Boolean = preferences.getBoolean(host, false)

    fun setEnabled(enabled: Boolean) {
        preferences.edit().putBoolean(host, enabled).apply()
    }
}

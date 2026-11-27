package com.mochyy.mochymusic.guardian

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.PersistableBundle

/** Explicit single-credential copy only. Never log, save or automatically copy. */
internal object GuardianSecretClipboard {
    fun copy(context: Context, value: String): Boolean {
        if (!Regex("[A-Za-z0-9_-]{43}").matches(value)) return false
        return runCatching {
            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("VOID private credential", value)
            // Suppress clipboard previews on Android versions that support this hint.
            clip.description.extras = PersistableBundle().apply {
                putBoolean("android.content.extra.IS_SENSITIVE", true)
            }
            clipboard.setPrimaryClip(clip)
        }.isSuccess
    }
}

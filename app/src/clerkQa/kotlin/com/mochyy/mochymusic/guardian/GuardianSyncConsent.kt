package com.mochyy.mochymusic.guardian

import android.content.Context
import android.util.AtomicFile
import java.io.File

/** Private, account-scoped consent and last acknowledged metadata revision.
 * Never store Clerk tokens, recovery credentials or audio here. */
internal object GuardianSyncConsent {
    private val lock = Any()
    private fun storage(context: Context) = AtomicFile(File(context.applicationContext.noBackupFilesDir,
        "guardian_sync_baseline_v3"))
    fun read(context: Context, account: String): CloudSyncPolicy.Baseline? = synchronized(lock) {
        runCatching {
            val values = storage(context).openRead().use { input ->
                require(input.channel.size() <= 128)
                String(input.readBytes(), Charsets.US_ASCII).split("\n")
            }
            require(values.size == 3 && values[0] == account && account.matches(Regex("[a-f0-9]{32}")))
            val revision = values[1].toLong()
            require(revision in 1 until Long.MAX_VALUE && values[2].matches(Regex("[a-f0-9]{64}")))
            CloudSyncPolicy.Baseline(account, revision, values[2])
        }.getOrNull()
    }
    fun write(context: Context, value: CloudSyncPolicy.Baseline) = synchronized(lock) {
        require(value.account.matches(Regex("[a-f0-9]{32}")) &&
            value.revision in 1 until Long.MAX_VALUE && value.digest.matches(Regex("[a-f0-9]{64}")))
        val file = storage(context)
        val stream = file.startWrite()
        try {
            stream.write("${value.account}\n${value.revision}\n${value.digest}".toByteArray(Charsets.US_ASCII))
            file.finishWrite(stream)
        } catch (e: Exception) {
            file.failWrite(stream)
            throw e
        }
    }
    fun clear(context: Context) = synchronized(lock) { storage(context).delete() }
}

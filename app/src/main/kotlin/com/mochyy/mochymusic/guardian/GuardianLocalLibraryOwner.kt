package com.mochyy.mochymusic.guardian

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.io.FileNotFoundException

/** Installation-local account binding. Sign-out never erases this marker.
 * Use only after the server has authenticated the account and signed its lease.
 * This intentionally prevents a second account accessing a shared library. */
internal object GuardianLocalLibraryOwner {
    private val lock = Any()
    private fun file(context: Context) = AtomicFile(File(context.applicationContext.noBackupFilesDir,
        "guardian_local_library_owner_v1"))
    private fun read(storage: AtomicFile): String? = try {
        storage.openRead().use { input ->
            require(input.channel.size() == 32L)
            String(input.readBytes(), Charsets.US_ASCII)
        }
    } catch (e: FileNotFoundException) {
        if (storage.baseFile.exists() || File(storage.baseFile.path + ".bak").exists() ||
            File(storage.baseFile.path + ".new").exists()) throw e
        null
    }

    fun status(context: Context, account: String): LocalLibraryBinding.Status = synchronized(lock) {
        runCatching { LocalLibraryBinding.status(read(file(context)), account) }
            .getOrDefault(LocalLibraryBinding.Status.UNAVAILABLE)
    }

    fun claim(context: Context, account: String, confirmed: Boolean): Boolean = synchronized(lock) {
        runCatching {
            val storage = file(context)
            val state = LocalLibraryBinding.status(read(storage), account)
            if (!LocalLibraryBinding.canUse(state, confirmed)) return@runCatching false
            if (state == LocalLibraryBinding.Status.MATCH) return@runCatching true
            val stream = storage.startWrite()
            try {
                stream.write(account.toByteArray(Charsets.US_ASCII))
                storage.finishWrite(stream)
            } catch (e: Exception) {
                storage.failWrite(stream)
                throw e
            }
            read(storage) == account
        }.getOrDefault(false)
    }
}

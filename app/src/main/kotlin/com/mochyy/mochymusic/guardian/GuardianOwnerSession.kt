package com.mochyy.mochymusic.guardian

import android.app.KeyguardManager
import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Optional device-credential protected session cache; never stores the owner password. */
internal object GuardianOwnerSession {
    private const val alias = "void_guardian_owner_session_v1"
    private fun file(context: Context) = AtomicFile(File(context.noBackupFilesDir, "void_owner_session.bin"))
    private fun keys() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    fun supported(context: Context): Boolean = Build.VERSION.SDK_INT >= 30 &&
        context.getSystemService(KeyguardManager::class.java)?.isDeviceSecure == true
    fun exists(context: Context): Boolean = supported(context) && file(context).baseFile.isFile
    private fun key(): SecretKey {
        require(Build.VERSION.SDK_INT >= 30)
        val ks = keys()
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setUserAuthenticationRequired(true)
                .setUserAuthenticationParameters(60, KeyProperties.AUTH_DEVICE_CREDENTIAL)
                .build())
            generateKey()
        }
    }
    fun save(context: Context, token: String): Boolean = runCatching {
        require(supported(context) && Regex("[A-Za-z0-9_-]{43}").matches(token))
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        require(cipher.iv.size == 12)
        val bytes = cipher.iv + cipher.doFinal(token.toByteArray(Charsets.US_ASCII))
        val target = file(context)
        val out = target.startWrite()
        try {
            out.write(bytes)
            target.finishWrite(out)
        } catch (e: Exception) {
            target.failWrite(out)
            throw e
        }
        true
    }.getOrDefault(false)
    fun restore(context: Context): String? = runCatching {
        require(supported(context))
        val bytes = file(context).readFully()
        require(bytes.size == 71)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.US_ASCII)
            .also { require(Regex("[A-Za-z0-9_-]{43}").matches(it)) }
    }.getOrNull()
    fun clear(context: Context) {
        runCatching { file(context).delete() }
        runCatching { keys().deleteEntry(alias) }
    }
}

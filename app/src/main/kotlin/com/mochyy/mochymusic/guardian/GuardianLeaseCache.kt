package com.mochyy.mochymusic.guardian

import android.content.Context
import android.os.SystemClock
import android.provider.Settings
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.security.PublicKey
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Opt-in V2 lease cache. Not a playback gate yet. The caller may save only a
 * fresh response obtained by a successful authenticated lease request.
 * Requires online refresh after reboot; never uses adjustable wall time.
 */
internal class GuardianLeaseCache(context: Context, private val publicKey: PublicKey) {
    private val app = context.applicationContext
    private val storage = AtomicFile(File(app.noBackupFilesDir, "guardian_v2_lease"))
    private val alias = "void_guardian_lease_cache_v2"
    data class Anchor(val elapsedMs: Long, val boot: Int)

    fun anchor(): Anchor = Anchor(SystemClock.elapsedRealtime(),
        Settings.Global.getInt(app.contentResolver, Settings.Global.BOOT_COUNT, -1)).also {
        require(it.boot >= 0)
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build())
        }.generateKey()
    }

    private fun encode(bytes: ByteArray): String =
        Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    private fun decode(value: String): ByteArray {
        require(value.length in 1..8192 && value.matches(Regex("[A-Za-z0-9_-]+")))
        return Base64.decode(value, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP).also {
            require(encode(it) == value)
        }
    }

    @Synchronized
    fun saveFresh(payload: ByteArray, signature: ByteArray, account: String,
                  serverEpoch: Long, requestStart: Anchor): Boolean = runCatching {
        val now = anchor()
        val trustedNow = LeaseClock.now(serverEpoch, requestStart.elapsedMs, requestStart.boot, now.elapsedMs, now.boot)
        val lease = SignedGuardianPolicy.lease(payload, signature, publicKey, account,
            DeviceEntitlement.fingerprint(), trustedNow, serverEpoch)
        // The authenticated response's signed issuance time must be the anchor.
        require(lease.issuedAt == serverEpoch)
        val body = JSONObject().put("payload", encode(payload)).put("signature", encode(signature))
            .put("epoch", serverEpoch).put("elapsed", requestStart.elapsedMs).put("boot", requestStart.boot)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.ENCRYPT_MODE, key())
        }
        require(cipher.iv.size == 12)
        val bytes = cipher.iv + cipher.doFinal(body.toString().toByteArray(Charsets.UTF_8))
        val stream = storage.startWrite()
        try {
            stream.write(bytes)
            storage.finishWrite(stream)
        } catch (e: Exception) {
            storage.failWrite(stream)
            throw e
        }
        true
    }.getOrDefault(false)

    @Synchronized
    fun active(account: String): Boolean = runCatching {
        val bytes = storage.openRead().use { input ->
            require(input.channel.size() in 29L..8192L)
            input.readBytes()
        }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0,12)))
        }
        val body = JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
        val now = anchor()
        val epoch = body.getLong("epoch")
        val trustedNow = LeaseClock.now(epoch, body.getLong("elapsed"), body.getInt("boot"),
            now.elapsedMs, now.boot)
        SignedGuardianPolicy.lease(decode(body.getString("payload")), decode(body.getString("signature")),
            publicKey, account, DeviceEntitlement.fingerprint(), trustedNow, epoch).issuedAt == epoch
    }.getOrDefault(false)

    @Synchronized
    fun clear() { storage.delete() }
}

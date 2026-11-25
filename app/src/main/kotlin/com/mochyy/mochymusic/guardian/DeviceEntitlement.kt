package com.mochyy.mochymusic.guardian

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec

/**
 * Device-bound entitlement primitives. Not wired to app startup or playback yet.
 * The server's public signing key must be pinned by the release configuration.
 * AndroidKeyStore may be hardware-backed depending on device capability.
 */
object DeviceEntitlement {
    private const val Alias = "void_guardian_device_v1"
    private const val Audience = "online.voidbot.music"
    private const val B64 = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
    private val noncePattern = Regex("[A-Za-z0-9_-]{43}")
    private val codePattern = Regex("VOID-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}")

    private fun store() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    @Synchronized
    fun publicKey(): ByteArray {
        val ks = store()
        if (!ks.containsAlias(Alias)) {
            val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            generator.initialize(
                KeyGenParameterSpec.Builder(Alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .build()
            )
            generator.generateKeyPair()
        }
        return requireNotNull(store().getCertificate(Alias)).publicKey.encoded
    }

    private fun shaHex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 255) }

    fun encodedPublicKey(): String = Base64.encodeToString(publicKey(), B64)
    fun fingerprint(): String = shaHex(publicKey())

    fun signChallenge(nonce: String, action: String, code: String = ""): String {
        require(noncePattern.matches(nonce))
        require(action == "redeem" || action == "status")
        require(if (action == "redeem") codePattern.matches(code) else code.isEmpty())
        val device = fingerprint()
        val digest = shaHex(code.toByteArray(Charsets.US_ASCII))
        val bytes = "VOID-DEVICE-PROOF-v1\n$nonce\n$device\n$action\n$digest".toByteArray(Charsets.US_ASCII)
        val privateKey = store().getKey(Alias, null) as java.security.PrivateKey
        val signature = Signature.getInstance("SHA256withECDSA").apply {
            initSign(privateKey)
            update(bytes)
        }.sign()
        return Base64.encodeToString(signature, B64)
    }

    private fun decode(value: String, max: Int): ByteArray {
        require(value.length in 1..max && value.all { it in 'A'..'Z' || it in 'a'..'z' || it in '0'..'9' || it == '_' || it == '-' })
        val bytes = Base64.decode(value, B64)
        require(Base64.encodeToString(bytes, B64) == value)
        return bytes
    }

    fun verify(receipt: String, serverPublicKey: String): Boolean = runCatching {
        require(receipt.length <= 8192)
        val outer = JSONObject(receipt)
        val payload = decode(outer.getString("payload"), 4096)
        val signature = decode(outer.getString("signature"), 256)
        val key = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(decode(serverPublicKey, 256)))
        val valid = Signature.getInstance("SHA256withECDSA").apply {
            initVerify(key)
            update(payload)
        }.verify(signature)
        val claims = JSONObject(String(payload, Charsets.UTF_8))
        valid && claims.getInt("v") == 1 && claims.getString("aud") == Audience &&
            MessageDigest.isEqual(claims.getString("device").toByteArray(Charsets.US_ASCII), fingerprint().toByteArray(Charsets.US_ASCII))
    }.getOrDefault(false)

    // No-backup directory avoids ordinary Android backup/restore cloning.
    // The signature and device-key binding are checked each time the receipt is read.
    fun save(context: Context, receipt: String, serverPublicKey: String): Boolean {
        if (!verify(receipt, serverPublicKey)) return false
        return runCatching {
            val file = android.util.AtomicFile(java.io.File(context.noBackupFilesDir, "void_entitlement.json"))
            val out = file.startWrite()
            try {
                out.write(receipt.toByteArray(Charsets.UTF_8))
                file.finishWrite(out)
            } catch (e: Exception) {
                file.failWrite(out)
                throw e
            }
            true
        }.getOrDefault(false)
    }

    fun isActive(context: Context, serverPublicKey: String): Boolean = runCatching {
        if (serverPublicKey.isBlank()) return false
        val file = android.util.AtomicFile(java.io.File(context.noBackupFilesDir, "void_entitlement.json"))
        verify(String(file.readFully(), Charsets.UTF_8), serverPublicKey)
    }.getOrDefault(false)

    fun clear(context: Context) {
        android.util.AtomicFile(java.io.File(context.noBackupFilesDir, "void_entitlement.json")).delete()
    }
}

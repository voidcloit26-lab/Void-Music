package com.mochyy.mochymusic.guardian

import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import java.io.OutputStream
import java.net.URL
import java.security.MessageDigest
import java.security.PublicKey
import javax.net.ssl.HttpsURLConnection

/** Staged updater for the stable package only. No existing updater calls this yet.
 * The origin and public key must come from trusted release configuration.
 * Caller must supply verified time and persistent previous policy state.
 */
internal class GuardianVerifiedUpdater(
    context: Context,
    origin: String,
    private val releaseKey: PublicKey
) {
    private val app = context.applicationContext
    private val base = URL(origin)
    private val dir = File(app.filesDir, "guardian_verified_updates")
    private val releaseState = GuardianReleaseState(app, releaseKey)
    init {
        require(base.protocol == "https" && base.host.isNotBlank() &&
            base.userInfo == null && base.query == null && base.ref == null &&
            base.path in listOf("", "/") && base.port in listOf(-1,443))
        require(app.packageName == "online.voidbot.music")
    }

    @Suppress("DEPRECATION")
    private fun version(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    @Suppress("DEPRECATION")
    private fun flags(): Int = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

    @Suppress("DEPRECATION")
    private fun signer(info: PackageInfo): String {
        val signatures = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        val sig = requireNotNull(signatures).single()
        return MessageDigest.getInstance("SHA-256").digest(sig.toByteArray())
            .joinToString("") { "%02x".format(it.toInt() and 255) }
    }

    private fun installed(): PackageInfo = app.packageManager.getPackageInfo(app.packageName, flags())

    private fun verifyArchive(file: File, release: SignedGuardianPolicy.Release) {
        val current = installed()
        val candidate = requireNotNull(app.packageManager.getPackageArchiveInfo(file.absolutePath, flags()))
        require(candidate.packageName == app.packageName && version(candidate) == release.latest)
        require(candidate.versionName == release.versionName) { "APK version name mismatch" }
        require(version(candidate) > version(current))
        require(signer(current) == release.signerSha256 && signer(candidate) == release.signerSha256)
    }

    /** Verify a policy even when the installed version is already current.
     * A transport failure must never manufacture a required-update decision. */
    suspend fun inspect(payload: ByteArray, signature: ByteArray, trustedNow: Long): String =
        withContext(Dispatchers.IO) {
            val candidate = SignedGuardianPolicy.release(payload, signature, releaseKey, trustedNow)
            val current = installed()
            require(signer(current) == candidate.signerSha256) { "Unexpected installed signing certificate" }
            check(releaseState.verifyAndRemember(payload, signature, trustedNow) == candidate)
            candidate.decision(version(current))
        }

    private fun policy(payload: ByteArray, signature: ByteArray, now: Long, previous: SignedGuardianPolicy.Release?) =
        SignedGuardianPolicy.release(payload, signature, releaseKey, now, previous).also {
            val current = installed()
            require(it.latest > version(current))
            require(signer(current) == it.signerSha256) { "Unexpected installed signing certificate" }
            check(releaseState.verifyAndRemember(payload, signature, now) == it)
        }

    private fun target(release: SignedGuardianPolicy.Release): File =
        File(dir, "void-${release.sequence}-${release.apkSha256}.apk")

    suspend fun download(payload: ByteArray, signature: ByteArray, trustedNow: Long,
                         previous: SignedGuardianPolicy.Release?, token: String): File =
        withContext(Dispatchers.IO) {
            val release = policy(payload, signature, trustedNow, previous)
            require(token.length in 1..8192 && Regex("[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+").matches(token))
            check(dir.isDirectory || dir.mkdirs())
            val output = target(release)
            val connection = URL(base.toString().trimEnd('/') + "/v2/releases/${release.sequence}/apk")
                .openConnection() as HttpsURLConnection
            val temp = try { File.createTempFile("void-partial-", ".apk", dir) }
            catch (e: Exception) { connection.disconnect(); throw e }
            try {
                connection.instanceFollowRedirects = false
                connection.connectTimeout = 15000
                connection.readTimeout = 30000
                connection.useCaches = false
                connection.setRequestProperty("Authorization", "Bearer $token")
                connection.setRequestProperty("Accept", "application/vnd.android.package-archive")
                connection.setRequestProperty("Accept-Encoding", "identity")
                check(connection.responseCode == 200)
                val length = connection.contentLengthLong
                require(length == -1L || length == release.apkBytes)
                val job = currentCoroutineContext()
                connection.inputStream.use { input ->
                    temp.outputStream().use { out ->
                        VerifiedApkBytes.copy(input, out, release.apkBytes, release.apkSha256) { job.ensureActive() }
                    }
                }
                verifyArchive(temp, release)
                check(temp.renameTo(output))
                output
            } finally {
                connection.disconnect()
                temp.delete()
            }
        }

    /** Revalidate immediately before launching the system installer.
     * Android still requires the user's approval; no silent installation.
     */
    suspend fun install(payload: ByteArray, signature: ByteArray, trustedNow: Long,
                        previous: SignedGuardianPolicy.Release?): Boolean {
        val uri = withContext(Dispatchers.IO) {
            val release = policy(payload, signature, trustedNow, previous)
            val file = target(release)
            val job = currentCoroutineContext()
            file.inputStream().use { input ->
                VerifiedApkBytes.copy(input, object : OutputStream() {
                    override fun write(b: Int) = Unit
                    override fun write(b: ByteArray, off: Int, len: Int) = Unit
                }, release.apkBytes, release.apkSha256) { job.ensureActive() }
            }
            verifyArchive(file, release)
            FileProvider.getUriForFile(app, app.packageName + ".GuardianUpdateProvider", file)
        }
        return withContext(Dispatchers.Main) {
            if (Build.VERSION.SDK_INT >= 26 && !app.packageManager.canRequestPackageInstalls()) return@withContext false
            app.startActivity(Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            })
            true
        }
    }
}

/** Shares only the dedicated verified update directory. */
class GuardianUpdateProvider : FileProvider()

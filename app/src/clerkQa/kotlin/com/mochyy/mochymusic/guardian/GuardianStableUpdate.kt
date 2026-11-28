package com.mochyy.mochymusic.guardian

import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Base64
import com.mochyy.mochymusic.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.spec.X509EncodedKeySpec

/** Stable-only orchestration. Internal APKs retain their isolated test protocol.
 * No unauthenticated update, downgrade, or automatic installer permission grant.
 */
internal object GuardianStableUpdate {
    val enabled: Boolean get() = BuildConfig.VOID_STABLE_UPDATE_ENABLED

    data class Check(val release: SignedGuardianPolicy.Release, val installed: Long) {
        val decision: String get() = release.decision(installed)
    }

    @Suppress("DEPRECATION")
    private fun installed(context: Context): PackageInfo {
        require(context.packageName == "online.voidbot.music")
        val flag = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES
            else PackageManager.GET_SIGNATURES
        return context.packageManager.getPackageInfo(context.packageName, flag)
    }

    @Suppress("DEPRECATION")
    private fun version(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    @Suppress("DEPRECATION")
    private fun signer(info: PackageInfo): String {
        val signers = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        return MessageDigest.getInstance("SHA-256").digest(requireNotNull(signers).single().toByteArray())
            .joinToString("") { "%02x".format(it.toInt() and 255) }
    }

    private fun key() = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(
        Base64.decode(BuildConfig.VOID_RELEASE_POLICY_PUBLIC_KEY, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    ))

    suspend fun check(context: Context, client: GuardianAccountClient): Check = withContext(Dispatchers.IO) {
        check(enabled)
        val key = key()
        val updater = GuardianVerifiedUpdater(context, BuildConfig.VOID_RELEASE_APK_ORIGIN, key)
        val result = GuardianReleasePolicyClient(client, updater).check()
        val release = SignedGuardianPolicy.release(result.payload, result.signature, key, result.trustedNow())
        val state = Check(release, version(installed(context)))
        check(state.decision == result.decision)
        state
    }

    suspend fun lease(context: Context, client: GuardianAccountClient): org.json.JSONObject {
        if (!enabled) return client.request("lease", emptyMap())
        val state = check(context, client)
        if (state.decision == "required") throw GuardianAccountClient.RequestFailed(426)
        val info = installed(context)
        return client.request("lease_versioned", mapOf("version_code" to version(info), "signer_sha256" to signer(info)))
    }

    suspend fun downloadAndInstall(context: Context, client: GuardianAccountClient, expected: Check): Boolean {
        check(enabled && expected.decision in setOf("available", "required"))
        val app = context.applicationContext
        val initial = ClerkQaBridge.currentSession()
        val key = key()
        val updater = GuardianVerifiedUpdater(app, BuildConfig.VOID_RELEASE_APK_ORIGIN, key)
        val policy = GuardianReleasePolicyClient(client, updater)
        val before = policy.check()
        val release = SignedGuardianPolicy.release(before.payload, before.signature, key, before.trustedNow())
        check(release == expected.release && before.decision in setOf("available", "required")) {
            "Release changed; refresh the update screen"
        }
        if (Build.VERSION.SDK_INT >= 26 && !app.packageManager.canRequestPackageInstalls()) {
            withContext(Dispatchers.Main) {
                app.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + app.packageName)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            return false
        }
        val grant = client.request("release_download", mapOf("sequence" to release.sequence))
        require(grant.keys().asSequence().toSet() == setOf("ticket", "expires_in"))
        require(grant.getInt("expires_in") == 120)
        val ticket = grant.getString("ticket")
        require(Regex("[A-Za-z0-9_-]{43}").matches(ticket))
        val auth = ClerkQaBridge.currentSession()
        check(auth.subject == initial.subject && auth.sessionId == initial.sessionId)
        updater.download(before.payload, before.signature, before.trustedNow(), null, auth.token, ticket)
        // A large download can outlive the trusted-time window. Obtain a fresh policy
        // and revalidate the exact release and active session before installation.
        val after = policy.check()
        val finalRelease = SignedGuardianPolicy.release(after.payload, after.signature, key, after.trustedNow())
        check(finalRelease == release)
        val current = ClerkQaBridge.currentSession()
        check(current.subject == initial.subject && current.sessionId == initial.sessionId)
        return updater.install(after.payload, after.signature, after.trustedNow(), null)
    }
}

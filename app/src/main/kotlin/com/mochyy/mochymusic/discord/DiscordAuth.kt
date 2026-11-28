package com.mochyy.mochymusic.discord

import android.content.Context
import android.net.Uri
import android.os.SystemClock
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.mochyy.mochymusic.BuildConfig
import com.mochyy.mochymusic.guardian.GuardianGate
import com.mochyy.mochymusic.constants.DiscordAccessTokenKey
import com.mochyy.mochymusic.constants.DiscordLoginStateKey
import com.mochyy.mochymusic.constants.DiscordLoginVerifierKey
import com.mochyy.mochymusic.constants.DiscordProfileKey
import com.mochyy.mochymusic.constants.DiscordRefreshTokenKey
import com.mochyy.mochymusic.constants.DiscordTokenExpiresAtKey
import com.mochyy.mochymusic.utils.Pkce
import com.mochyy.mochymusic.utils.dataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import javax.inject.Inject
import javax.inject.Singleton

sealed interface DiscordLogin {
    data object Idle : DiscordLogin
    data object InBrowser : DiscordLogin
    data object Finishing : DiscordLogin
    data class Failed(val message: String) : DiscordLogin
}

/** Optional, identify-only profile lookup. Never authenticates the RPC client or
 * grants Guardian access. The profile, OAuth transaction and tokens are not
 * persisted; a process restart requires fresh consent to show the profile. */
@Singleton
class DiscordAuth @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Any()
    private val json = Json { ignoreUnknownKeys = true }
    private data class Pending(val state: String, val verifier: String, val started: Long)
    private var pending: Pending? = null
    private var generation = 0L
    private val _login = MutableStateFlow<DiscordLogin>(DiscordLogin.Idle)
    val login: StateFlow<DiscordLogin> = _login.asStateFlow()
    private val _profile = MutableStateFlow<DiscordProfile?>(null)
    val profile: StateFlow<DiscordProfile?> = _profile.asStateFlow()
    val signedIn = profile.map { it != null }.distinctUntilChanged()

    // Never enable the retired authenticated gateway path.
    val isConfigured: Boolean get() = false
    val profileLinkConfigured: Boolean get() =
        BuildConfig.VOID_NATIVE_RPC_INCLUDED && ClientId == BuildConfig.VOID_DISCORD_APPLICATION_ID

    init {
        scope.launch {
            GuardianGate.changes.collect {
                if (!runCatching { GuardianGate.isAllowed(context) }.getOrDefault(false)) clearProfile()
            }
        }
    }

    suspend fun loginUri(): Uri = withContext(Dispatchers.IO) {
        check(GuardianGate.isAllowed(context)) { "Guardian access required" }
        synchronized(lock) {
        check(profileLinkConfigured) { "Discord profile linking is unavailable" }
        check(_login.value != DiscordLogin.Finishing) { "Discord profile lookup is in progress" }
        val transaction = Pending(Pkce.randomCode(24), Pkce.randomCode(64), SystemClock.elapsedRealtime())
        pending = transaction
        generation++
        _login.value = DiscordLogin.InBrowser
        Uri.parse("https://discord.com/oauth2/authorize").buildUpon()
            .appendQueryParameter("client_id", ClientId)
            .appendQueryParameter("response_type", "code")
            .appendQueryParameter("redirect_uri", RedirectUri)
            .appendQueryParameter("scope", "identify")
            .appendQueryParameter("state", transaction.state)
            .appendQueryParameter("code_challenge", Pkce.challengeOf(transaction.verifier))
            .appendQueryParameter("code_challenge_method", "S256")
            .build()
        }
    }

    fun isCallback(redirect: Uri): Boolean =
        profileLinkConfigured && redirect.scheme == "discord-$ClientId" &&
            redirect.encodedAuthority == null && redirect.encodedPath == "/authorize/callback" &&
            redirect.encodedFragment == null

    fun handleRedirect(redirect: Uri) {
        if (isCallback(redirect)) scope.launch { finish(redirect) }
    }

    suspend fun finish(redirect: Uri) {
        if (!isCallback(redirect)) return
        val (transaction, attempt) = synchronized(lock) {
            val current = pending ?: return
            if (redirect.getQueryParameters("state").singleOrNull() != current.state) return
            pending = null
            if (SystemClock.elapsedRealtime() - current.started > 10 * 60_000L) {
                _login.value = DiscordLogin.Failed("Profile linking expired. Try again.")
                return
            }
            _login.value = DiscordLogin.Finishing
            current to generation
        }
        var access: String? = null
        var refresh: String? = null
        try {
            val code = redirect.getQueryParameters("code").singleOrNull()
            check(!code.isNullOrBlank() && redirect.getQueryParameter("error") == null)
            val reply = DiscordHttp.postForm("/oauth2/token", mapOf(
                "client_id" to ClientId, "grant_type" to "authorization_code",
                "code" to code, "redirect_uri" to RedirectUri,
                "code_verifier" to transaction.verifier,
            ))
            check(reply.ok)
            val body = json.parseToJsonElement(reply.body).jsonObject
            val token = body["access_token"]?.jsonPrimitive?.contentOrNull ?: error("No access token")
            access = token
            refresh = body["refresh_token"]?.jsonPrimitive?.contentOrNull
            check(body["token_type"]?.jsonPrimitive?.contentOrNull.equals("Bearer", ignoreCase = true))
            check(body["scope"]?.jsonPrimitive?.contentOrNull?.split(' ')?.filter { it.isNotBlank() }?.toSet() == setOf("identify"))
            val loaded = DiscordProfile.fetch(token)
            check(GuardianGate.isAllowed(context)) { "Guardian access required" }
            synchronized(lock) {
                if (generation == attempt) {
                    _profile.value = loaded
                    _login.value = DiscordLogin.Idle
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            synchronized(lock) {
                if (generation == attempt) _login.value = DiscordLogin.Failed(
                    "Could not link your Discord profile. Try again; listening activity is independent.")
            }
        } finally {
            // No durable OAuth credential is needed. Best-effort revoke both tokens.
            for ((token, hint) in listOf(refresh to "refresh_token", access to "access_token")) {
                if (token != null) runCatching {
                    DiscordHttp.postForm("/oauth2/token/revoke", mapOf(
                        "client_id" to ClientId, "token" to token, "token_type_hint" to hint))
                }
            }
        }
    }

    fun cancelWaiting() = synchronized(lock) {
        if (_login.value == DiscordLogin.InBrowser) {
            generation++
            pending = null
            _login.value = DiscordLogin.Idle
        }
    }

    fun dismissProblem() = synchronized(lock) {
        if (_login.value is DiscordLogin.Failed) _login.value = DiscordLogin.Idle
    }

    // Compatibility methods deliberately never return a gateway token.
    suspend fun accessToken(): String? = null
    suspend fun renew(rejected: String): String? = null
    suspend fun refreshProfile() = Unit

    private fun clearProfile() = synchronized(lock) {
        generation++
        pending = null
        _profile.value = null
        _login.value = DiscordLogin.Idle
    }

    suspend fun logOut() {
        clearProfile()
        forgetOldLogin()
    }

    suspend fun forgetOldLogin() {
        context.dataStore.edit { stored ->
            LegacyKeys.forEach { stored.remove(it) }
            stored.remove(DiscordAccessTokenKey)
            stored.remove(DiscordRefreshTokenKey)
            stored.remove(DiscordTokenExpiresAtKey)
            stored.remove(DiscordProfileKey)
            stored.remove(DiscordLoginStateKey)
            stored.remove(DiscordLoginVerifierKey)
        }
    }

    companion object {
        val ClientId: String get() = BuildConfig.DISCORD_CLIENT_ID
        val RedirectUri: String get() = "discord-$ClientId:/authorize/callback"
        private val LegacyKeys: List<Preferences.Key<*>> = listOf(
            "discordToken", "discordUsername", "discordName", "discordAvatar", "discordStatus",
            "discordButton1Text", "discordButton2Text", "discordActivityName",
            ).map { stringPreferencesKey(it) } + listOf(
            "discordInfoDismissed", "discordUseDetails", "discordButton1Visible", "discordButton2Visible",
            "discordAdvancedMode",
        ).map { booleanPreferencesKey(it) }
    }
}

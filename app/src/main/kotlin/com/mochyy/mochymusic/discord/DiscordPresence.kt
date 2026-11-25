package com.mochyy.mochymusic.discord

import android.content.Context
import android.os.SystemClock
import androidx.datastore.preferences.core.edit
import com.mochyy.mochymusic.guardian.GuardianGate
import com.mochyy.mochymusic.utils.OfflineMode
import com.mochyy.mochymusic.utils.dataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.abs

enum class PresenceConnection { Off, Idle, Connecting, Live, Retrying }

/**
 * MusicService reports playback metadata; only the authorized native bridge can
 * publish it. No legacy gateway, user token, asset uploads or bot interaction.
 */
@Singleton
class DiscordPresence @Inject constructor(
    @ApplicationContext private val context: Context,
    private val auth: DiscordAuth,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _nowPlaying = MutableStateFlow<NowPlaying?>(null)
    val nowPlaying: StateFlow<NowPlaying?> = _nowPlaying.asStateFlow()
    val settings: StateFlow<PresenceSettings> = context.dataStore.data
        .map(PresenceSettings::from)
        .stateIn(scope, SharingStarted.Eagerly, PresenceSettings())
    private val _connection = MutableStateFlow(PresenceConnection.Off)
    val connection: StateFlow<PresenceConnection> = _connection.asStateFlow()
    private val pendingSave = MutableStateFlow<PresenceSettings?>(null)
    private val nudges = MutableStateFlow(0)

    // Main-dispatcher-confined transport state. No callback processing on audio threads.
    private var sent: NativePresencePayload? = null
    private var ownsActivity = false
    private var nextSendAt = 0L
    private var pendingSince = 0L
    private var retryDelay = 5_000L
    private var lastStatus = 0
    private var cachedAllowed = false
    private var nextAccessCheck = 0L

    init {
        scope.launch { auth.forgetOldLogin() }
        scope.launch {
            pendingSave.filterNotNull().collect { edited ->
                context.dataStore.edit { edited.writeTo(it) }
            }
        }
        if (NativePresenceBridge.included) scope.launch(Dispatchers.Main.immediate) { follow() }
    }

    fun save(edited: PresenceSettings) { pendingSave.value = edited }
    fun update(track: NowPlaying?) { _nowPlaying.value = track }
    fun nudge() { nudges.update { it + 1 } }

    private suspend fun follow() {
        combine(settings, _nowPlaying, NativePresenceBridge.ready, nudges, GuardianGate.changes) {
            config, track, ready, _, _ -> Triple(config, track, ready)
        }.collectLatest { (config, track, ready) ->
            nextAccessCheck = 0L
            if (!ready || !config.enabled || track == null) {
                hide(if (config.enabled && ready) PresenceConnection.Idle else PresenceConnection.Off)
                return@collectLatest
            }
            while (true) {
                val now = SystemClock.elapsedRealtime()
                if (now >= nextAccessCheck) {
                    cachedAllowed = withContext(Dispatchers.IO) { GuardianGate.isAllowed(context) }
                    nextAccessCheck = now + 5_000L
                }
                val pausedTooLong = !track.isPlaying &&
                    System.currentTimeMillis() - track.readAtMs > 10 * 60_000L
                if (!cachedAllowed || OfflineMode.isOn ||
                    (!track.isPlaying && (config.clearOnPause || pausedTooLong))) {
                    hide(PresenceConnection.Idle)
                    // Keep watching for offline mode or access changes without touching the SDK.
                    delay(1_000L)
                    continue
                }
                val payload = NativePresenceMapper.map(
                    PresenceActivity.build(track, config, System.currentTimeMillis()),
                    config.sharePublicArtwork,
                )
                val status = runCatching { NativePresenceBridge.tick() }.getOrDefault(3)
                if (status == 2) {
                    _connection.value = PresenceConnection.Live
                    retryDelay = 5_000L
                } else if (status == 3 || (status == 1 && now - pendingSince >= 15_000L)) {
                    if (lastStatus != 3) {
                        sent = null
                        nextSendAt = maxOf(nextSendAt, now + retryDelay)
                        retryDelay = (retryDelay * 2).coerceAtMost(60_000L)
                    }
                    _connection.value = PresenceConnection.Retrying
                }
                lastStatus = if (status == 1 && now - pendingSince >= 15_000L) 3 else status
                if (!equivalent(sent, payload) && now >= nextSendAt &&
                    (status != 1 || now - pendingSince >= 15_000L)) {
                    nextSendAt = now + maxOf(5_000L, config.refreshSeconds * 1_000L)
                    pendingSince = now
                    lastStatus = 1
                    ownsActivity = true
                    _connection.value = PresenceConnection.Connecting
                    sent = if (runCatching { NativePresenceBridge.publish(payload) }.isSuccess) payload else null
                }
                delay(250L)
            }
        }
    }

    private suspend fun hide(state: PresenceConnection) {
        _connection.value = state
        if (!ownsActivity) return
        sent = null
        lastStatus = 0
        runCatching { NativePresenceBridge.clear() }
        // Pump pending clear callbacks. Preserve the flag if a new flow emission cancels this.
        repeat(4) {
            runCatching { NativePresenceBridge.tick() }
            delay(250L)
        }
        ownsActivity = false
    }

    private fun equivalent(a: NativePresencePayload?, b: NativePresencePayload): Boolean {
        if (a == null) return false
        fun near(x: Long?, y: Long?) = if (x == null || y == null) x == y else abs(x - y) < 2_500L
        return near(a.startMs, b.startMs) && near(a.endMs, b.endMs) &&
            a.copy(startMs = null, endMs = null) == b.copy(startMs = null, endMs = null)
    }
}

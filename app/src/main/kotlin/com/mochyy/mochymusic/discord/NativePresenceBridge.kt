package com.mochyy.mochymusic.discord

import android.app.Activity
import com.mochyy.mochymusic.BuildConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Local native RPC only. No account tokens and no network calls through the old
 * gateway. Only the explicit private SDK build can load this transport.
 * All SDK calls and callback pumping are serialized by the main dispatcher.
 */
internal object NativePresenceBridge {
    val included get() = BuildConfig.VOID_NATIVE_RPC_INCLUDED
    private val _ready = MutableStateFlow(false)
    val ready = _ready.asStateFlow()
    private val _attachmentEpoch = MutableStateFlow(0L)
    val attachmentEpoch = _attachmentEpoch.asStateFlow()

    fun attach(activity: Activity) {
        if (!included) return
        _ready.value = runCatching {
            val cls = Class.forName("com.discord.socialsdk.DiscordSocialSdkInit")
            val method = cls.methods.first { it.name == "setEngineActivity" &&
                it.parameterTypes.size == 1 && it.parameterTypes[0].isAssignableFrom(activity.javaClass) }
            method.invoke(null, activity)
            System.loadLibrary("void_music_rpc")
            initNative()
            true
        }.getOrDefault(false)
        if (_ready.value) _attachmentEpoch.value += 1L
    }

    fun publish(payload: NativePresencePayload) {
        val first = payload.buttons.firstOrNull()
        val second = payload.buttons.getOrNull(1)
        val fields = listOf(payload.name, payload.details, payload.state, payload.largeAsset,
            payload.largeText, payload.smallAsset, payload.smallText,
            first?.label, first?.url, second?.label, second?.url)
        publishNative(fields.map { it.orEmpty().toByteArray(Charsets.UTF_8) }.toTypedArray(),
            payload.kind.discordType, payload.startMs ?: 0L, payload.endMs ?: 0L)
    }

    fun clear() { if (ready.value) clearNative() }
    fun tick(): Int = if (ready.value) tickNative() else 0

    private external fun initNative()
    private external fun publishNative(fields: Array<ByteArray>, kind: Int, startMs: Long, endMs: Long)
    private external fun clearNative()
    private external fun tickNative(): Int
}

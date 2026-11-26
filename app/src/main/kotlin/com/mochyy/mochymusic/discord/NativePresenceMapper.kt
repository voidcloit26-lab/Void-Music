package com.mochyy.mochymusic.discord

import java.net.URI

/**
 * SDK-independent contract for the native RPC transport. The existing preview remains
 * the source of the user's text, kind, song timing and provider button. Nothing here
 * opens a connection, uploads artwork or uses a Discord account token.
 */
internal data class NativePresencePayload(
    val kind: PresenceKind,
    val name: String,
    val details: String?,
    val state: String?,
    val startMs: Long?,
    val endMs: Long?,
    val largeAsset: String,
    val largeText: String?,
    val smallAsset: String?,
    val smallText: String?,
    val buttons: List<PresenceActivity.Link>,
)

internal object NativePresenceMapper {
    private const val Logo = "void_music"
    private const val Community = "https://discord.gg/marscm"
    private val ArtHosts = setOf("i.ytimg.com", "lh3.googleusercontent.com", "lh4.googleusercontent.com",
        "lh5.googleusercontent.com", "lh6.googleusercontent.com", "yt3.ggpht.com",
        "yt3.googleusercontent.com", "i.scdn.co")
    private val AppleHost = Regex("is[1-5]-ssl\\.mzstatic\\.com")

    /**
     * Explicit artwork consent is independent of the presence switch. A missing or
     * unsupported large image uses the registered logo. Animated/local assets are
     * never uploaded by this transport; their safe public still is used if available.
     */
    fun map(activity: PresenceActivity, sharePublicArtwork: Boolean): NativePresencePayload {
        val large = asset(activity.largeImage, sharePublicArtwork) ?: Logo
        val small = asset(activity.smallImage, sharePublicArtwork)?.takeUnless { it == large }
        val provider = activity.buttons.firstOrNull { providerUrl(it.url) }
        val start = activity.startMs?.takeIf { it > 0 }
        val end = activity.endMs?.takeIf { start != null && it > start }
        return NativePresencePayload(
            kind = activity.kind,
            name = activity.name,
            details = activity.details,
            state = activity.state,
            startMs = start,
            endMs = end,
            largeAsset = large,
            largeText = activity.largeText,
            smallAsset = small,
            smallText = activity.smallText.takeIf { small != null },
            buttons = listOfNotNull(provider, PresenceActivity.Link("Join MARS Community", Community)),
        )
    }

    private fun asset(picture: PresencePicture?, consent: Boolean): String? = when (picture) {
        PresencePicture.Logo -> Logo
        is PresencePicture.Web -> picture.url.takeIf { consent && publicArtwork(it) }
        is PresencePicture.Spinning -> picture.sourceUrl.takeIf { consent && publicArtwork(it) }
        is PresencePicture.Canvas -> picture.fallback?.takeIf { consent && publicArtwork(it) }
        // No automatic private-file uploads or legacy gateway asset registration.
        is PresencePicture.Local, is PresencePicture.Status, null -> null
    }

    private fun https(raw: String): URI? {
        if (raw.length > 512) return null
        val uri = runCatching { URI(raw) }.getOrNull() ?: return null
        return uri.takeIf {
            it.scheme == "https" && it.host != null && it.rawUserInfo == null &&
                it.port == -1 && it.rawFragment == null
        }
    }

    internal fun publicArtwork(raw: String): Boolean {
        val uri = https(raw) ?: return false
        return uri.rawQuery == null && uri.path.isNotBlank() &&
            (uri.host in ArtHosts || AppleHost.matches(uri.host))
    }

    internal fun providerUrl(raw: String): Boolean {
        val uri = https(raw) ?: return false
        return when (uri.host) {
            "music.youtube.com" -> uri.path == "/watch" || uri.path == "/search"
            "open.spotify.com" -> uri.path.startsWith("/search/")
            "music.apple.com" -> uri.path == "/search"
            "listen.tidal.com" -> uri.path == "/search"
            else -> false
        }
    }
}

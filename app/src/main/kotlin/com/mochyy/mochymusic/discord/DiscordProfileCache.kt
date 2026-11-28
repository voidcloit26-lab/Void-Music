package com.mochyy.mochymusic.discord

import android.content.Context
import android.util.AtomicFile
import java.io.File

/** Account-bound, app-private display metadata only. Never write OAuth tokens,
 * credentials, or device proofs. Excluded from Android backup and transfer.
 * Callers must supply a currently verified Guardian account ID. */
internal class DiscordProfileCache(context: Context) {
    private val app = context.applicationContext
    private fun file(account: String): AtomicFile {
        require(account.matches(Regex("[a-f0-9]{32}")))
        return AtomicFile(File(app.noBackupFilesDir, "void_discord_profile_$account.json"))
    }

    fun read(account: String): DiscordProfile? = runCatching {
        val raw = file(account).openRead().use {
            require(it.channel.size() in 1L..16384L)
            String(it.readBytes(), Charsets.UTF_8)
        }
        DiscordProfile.fromJson(raw)?.takeIf { valid(it) }
    }.getOrNull()

    fun write(account: String, profile: DiscordProfile) {
        require(valid(profile))
        val bytes = profile.toJson().toByteArray(Charsets.UTF_8)
        require(bytes.size in 1..16384)
        val storage = file(account)
        val stream = storage.startWrite()
        try {
            stream.write(bytes)
            storage.finishWrite(stream)
        } catch (e: Exception) {
            storage.failWrite(stream)
            throw e
        }
    }

    fun clear(account: String) = file(account).delete()

    companion object {
        internal fun valid(profile: DiscordProfile): Boolean {
            val id = profile.id
            if (!id.matches(Regex("[0-9]{17,20}")) || id.toULongOrNull() == null) return false
            val asset = "(a_)?[0-9a-fA-F]{32}"
            val avatar = Regex("https://cdn[.]discordapp[.]com/avatars/$id/$asset[.]png[?]size=256")
            val defaultAvatar = Regex("https://cdn[.]discordapp[.]com/embed/avatars/[0-5][.]png")
            val banner = Regex("https://cdn[.]discordapp[.]com/banners/$id/$asset[.]png[?]size=512")
            return profile.username.isNotBlank() && profile.username.length <= 128 &&
                profile.displayName.isNotBlank() && profile.displayName.length <= 256 &&
                profile.avatarUrl?.let { avatar.matches(it) || defaultAvatar.matches(it) } == true &&
                (profile.bannerUrl == null || banner.matches(profile.bannerUrl)) &&
                (profile.bannerColor == null || profile.bannerColor in 0..0xFFFFFF) &&
                profile.bio == null && profile.pronouns == null
        }
    }
}

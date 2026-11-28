// DiscordProfile.kt

package com.mochyy.mochymusic.discord

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** The signed-in Discord account, as the Discord page shows it. */
@Serializable
data class DiscordProfile(
    val id: String,
    val username: String,
    val displayName: String,
    val avatarUrl: String? = null,
    val bannerUrl: String? = null,
    /** the banner's colour when there's no banner picture, as 0xRRGGBB */
    val bannerColor: Int? = null,
    val pronouns: String? = null,
    val bio: String? = null,
) {
    fun toJson(): String = json.encodeToString(serializer(), this)

    companion object {
        private val json = Json { ignoreUnknownKeys = true }
        private const val Cdn = "https://cdn.discordapp.com"

        fun fromJson(text: String?): DiscordProfile? =
            text?.let { runCatching { json.decodeFromString(serializer(), it) }.getOrNull() }

        /** Reads the documented current-user endpoint using the identify scope. */
        suspend fun fetch(token: String): DiscordProfile {
            val me = DiscordHttp.get("/users/@me", token)
            check(me.ok) { "Discord didn't share the account (HTTP ${me.code})" }
            return parseCurrentUser(me.body)
        }

        internal fun parseCurrentUser(body: String): DiscordProfile {
            val user = json.parseToJsonElement(body).jsonObject
            val id = user.text("id")?.takeIf { it.matches(Regex("[0-9]{17,20}")) }
                ?: error("Invalid Discord account id")
            val username = user.text("username") ?: error("Missing Discord username")
            return DiscordProfile(
                id = id,
                username = username,
                displayName = user.text("global_name") ?: username,
                avatarUrl = avatarUrl(id, user.asset("avatar")),
                bannerUrl = user.asset("banner")?.let { "$Cdn/banners/$id/$it.png?size=512" },
                bannerColor = user.number("accent_color")?.takeIf { it in 0..0xFFFFFF },
            )
        }

        /** Discord's picture, or the coloured default it gives accounts without one */
        private fun avatarUrl(id: String, hash: String?): String {
            if (hash != null) return "$Cdn/avatars/$id/$hash.png?size=256"
            val index = (id.toULong() shr 22) % 6uL
            return "$Cdn/embed/avatars/$index.png"
        }

        private fun JsonObject.text(key: String): String? =
            this[key]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }

        private fun JsonObject.number(key: String): Int? = this[key]?.jsonPrimitive?.intOrNull

        private fun JsonObject.asset(key: String): String? =
            text(key)?.takeIf { it.matches(Regex("(a_)?[0-9a-fA-F]{32}")) }
    }
}

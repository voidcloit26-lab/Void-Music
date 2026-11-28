package com.mochyy.mochymusic.discord

import org.junit.Assert.*
import org.junit.Test

class DiscordProfileTest {
    private val id = "1553388915300245594"
    private val avatar = "0123456789abcdef0123456789abcdef"
    private val banner = "fedcba9876543210fedcba9876543210"

    @Test fun currentUserFieldsAreMappedToOfficialCdn() {
        val profile = DiscordProfile.parseCurrentUser(
            """{"id":"$id","username":"testuser","global_name":"Test User","avatar":"$avatar","banner":"a_$banner","accent_color":1193046,"bio":"not requested"}"""
        )
        assertEquals(id, profile.id)
        assertEquals("testuser", profile.username)
        assertEquals("Test User", profile.displayName)
        assertEquals("https://cdn.discordapp.com/avatars/$id/$avatar.png?size=256", profile.avatarUrl)
        assertEquals("https://cdn.discordapp.com/banners/$id/a_$banner.png?size=512", profile.bannerUrl)
        assertEquals(1193046, profile.bannerColor)
        assertNull(profile.bio)
        assertNull(profile.pronouns)
    }

    @Test fun absentDisplayNameAndImagesAreSafe() {
        val profile = DiscordProfile.parseCurrentUser(
            """{"id":"$id","username":"testuser","global_name":null,"avatar":null,"banner":null}"""
        )
        assertEquals("testuser", profile.displayName)
        assertTrue(profile.avatarUrl!!.matches(Regex("https://cdn[.]discordapp[.]com/embed/avatars/[0-5][.]png")))
        assertNull(profile.bannerUrl)
    }

    @Test fun rejectsMalformedAccountAndIgnoresInvalidAssetPaths() {
        assertTrue(runCatching {
            DiscordProfile.parseCurrentUser("""{"id":"../evil","username":"testuser"}""")
        }.isFailure)
        assertTrue(runCatching {
            DiscordProfile.parseCurrentUser("""{"id":"$id"}""")
        }.isFailure)
        val profile = DiscordProfile.parseCurrentUser(
            """{"id":"$id","username":"testuser","avatar":"https://example.org/a","banner":"../private","accent_color":-1}"""
        )
        assertTrue(profile.avatarUrl!!.contains("/embed/avatars/"))
        assertNull(profile.bannerUrl)
        assertNull(profile.bannerColor)
    }
}

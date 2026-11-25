package com.mochyy.mochymusic.discord

import org.junit.Assert.*
import org.junit.Test

class NativePresenceMapperTest {
    private val cover = "https://i.ytimg.com/vi/abc/hqdefault.jpg"
    private val mars = "https://discord.gg/marscm"
    private val track = PresenceActivity(
        kind = PresenceKind.LISTENING, name = "VOID Music",
        details = "Track", detailsUrl = null, state = "Artist",
        largeImage = PresencePicture.Web(cover), largeText = "Album",
        smallImage = PresencePicture.Logo, smallText = "OPUS",
        startMs = 1700000000000L, endMs = 1700000300000L,
        buttons = listOf(PresenceActivity.Link("Listen", "https://music.youtube.com/watch?v=abc"),
            PresenceActivity.Link("Other", "https://discord.gg/other")),
    )

    @Test fun preservesTextTimingAndButtons() {
        val result = NativePresenceMapper.map(track, true)
        assertEquals(track.kind, result.kind)
        assertEquals(track.name, result.name)
        assertEquals(track.details, result.details)
        assertEquals(track.state, result.state)
        assertEquals(track.startMs, result.startMs)
        assertEquals(track.endMs, result.endMs)
        assertEquals(cover, result.largeAsset)
        assertEquals("void_music", result.smallAsset)
        assertEquals("OPUS", result.smallText)
        assertEquals(listOf(track.buttons.first(), PresenceActivity.Link("Join MARS Community", mars)), result.buttons)
    }

    @Test fun artworkRequiresConsent() {
        val result = NativePresenceMapper.map(track, false)
        assertEquals("void_music", result.largeAsset)
        assertNull(result.smallAsset)
        assertNull(result.smallText)
    }

    @Test fun rejectsPrivateOrCredentialBearingArtwork() {
        listOf("file:///sdcard/a.jpg", "content://media/1", "http://i.ytimg.com/a",
            "https://i.ytimg.com.evil.example/a", "https://user@i.ytimg.com/a",
            "https://i.ytimg.com/a?token=secret", "https://i.ytimg.com:443/a",
            "https://i.ytimg.com/a#secret", "https://127.0.0.1/a").forEach {
            assertFalse(it, NativePresenceMapper.publicArtwork(it))
        }
        assertTrue(NativePresenceMapper.publicArtwork("https://is3-ssl.mzstatic.com/a.jpg"))
    }

    @Test fun animatedAssetsUsePublicStillOnly() {
        val spin = PresencePicture.Spinning(cover, SpinStyle(8, 25))
        assertEquals(cover, NativePresenceMapper.map(track.copy(largeImage = spin), true).largeAsset)
        assertEquals("void_music", NativePresenceMapper.map(track.copy(largeImage = spin), false).largeAsset)
        assertEquals("void_music", NativePresenceMapper.map(track.copy(largeImage = PresencePicture.Local("content://media/1")), true).largeAsset)
    }

    @Test fun pausedAndInvalidTimestampsDoNotRun() {
        val paused = NativePresenceMapper.map(track.copy(startMs = null, endMs = null), true)
        assertNull(paused.startMs)
        assertNull(paused.endMs)
        val invalid = NativePresenceMapper.map(track.copy(startMs = 10, endMs = 9), true)
        assertNull(invalid.endMs)
    }

    @Test fun communityLinkCannotBeOverridden() {
        val result = NativePresenceMapper.map(track.copy(buttons = listOf(
            PresenceActivity.Link("Fake", "https://music.youtube.com.evil.example/watch?v=abc"),
            PresenceActivity.Link("Wrong", "https://discord.gg/other"))), true)
        assertEquals(listOf(PresenceActivity.Link("Join MARS Community", mars)), result.buttons)
    }

    @Test fun providersAreRestrictedToKnownMusicPages() {
        listOf("https://music.youtube.com/search?q=abc", "https://open.spotify.com/search/abc",
            "https://music.apple.com/search?term=abc", "https://listen.tidal.com/search?q=abc").forEach {
            assertTrue(it, NativePresenceMapper.providerUrl(it))
        }
        assertFalse(NativePresenceMapper.providerUrl("https://music.youtube.com/redirect?q=abc"))
        assertFalse(NativePresenceMapper.providerUrl("https://music.youtube.com@evil.example/watch?v=abc"))
    }
}

package com.mochyy.mochymusic.guardian

import org.junit.Assert.*
import org.junit.Test

class GuardianPlaybackPreferencesTest {
    @Test fun roundTripModes() {
        listOf("off", "one", "all").forEachIndexed { mode, name ->
            for (shuffle in listOf(false, true)) {
                val saved = GuardianPlaybackPreferences.capture(mode, shuffle)
                assertEquals(name, saved.repeat)
                assertEquals(mode, saved.repeatMode())
                assertEquals(saved, GuardianPlaybackPreferences.read(saved.body()))
            }
        }
    }
    @Test fun mergePreservesTheme() {
        val remote = mapOf("theme" to "dark", "repeat" to "off", "shuffle" to false)
        assertEquals(mapOf("theme" to "dark", "repeat" to "all", "shuffle" to true),
            GuardianPlaybackPreferences.merge(remote, GuardianPlaybackPreferences.Saved("all", true)))
    }
    @Test fun incompleteRemoteNotRestored() {
        assertNull(GuardianPlaybackPreferences.read(emptyMap()))
        assertNull(GuardianPlaybackPreferences.read(mapOf("repeat" to "off")))
    }
    @Test fun invalidValuesRejected() {
        assertTrue(runCatching { GuardianPlaybackPreferences.capture(3, false) }.isFailure)
        assertTrue(runCatching { GuardianPlaybackPreferences.read(mapOf("repeat" to "bad", "shuffle" to true)) }.isFailure)
        assertTrue(runCatching { GuardianPlaybackPreferences.read(mapOf("repeat" to "off", "shuffle" to "true")) }.isFailure)
        assertTrue(runCatching { GuardianPlaybackPreferences.merge(mapOf("token" to "invalid"), GuardianPlaybackPreferences.Saved("off", false)) }.isFailure)
    }
}

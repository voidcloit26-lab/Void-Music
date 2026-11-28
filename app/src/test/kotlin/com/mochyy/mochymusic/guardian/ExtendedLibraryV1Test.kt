package com.mochyy.mochymusic.guardian

import org.junit.Assert.*
import org.junit.Test

class ExtendedLibraryV1Test {
    private val album = "MPREb" + "a".repeat(16)
    private val artist = "UC" + "b".repeat(22)
    private val song = "c".repeat(11)

    @Test fun optOutAndEmptyHistoryAreDistinct() {
        val disabled = ExtendedLibraryV1.Snapshot(listOf(album), listOf(artist), null)
        assertNull(ExtendedLibraryV1.normalize(disabled).history)
        assertEquals(emptyList<ExtendedLibraryV1.Play>(),
            ExtendedLibraryV1.normalize(disabled.copy(history = emptyList())).history)
    }

    @Test fun rejectsPrivateIdentifiersAndInvalidHistory() {
        val valid = ExtendedLibraryV1.Snapshot(listOf(album), listOf(artist), null)
        assertTrue(runCatching { ExtendedLibraryV1.normalize(valid.copy(albums = listOf("file:///secret"))) }.isFailure)
        assertTrue(runCatching { ExtendedLibraryV1.normalize(valid.copy(artists = listOf("LA12345678"))) }.isFailure)
        assertTrue(runCatching { ExtendedLibraryV1.normalize(valid.copy(albums = listOf(album, album))) }.isFailure)
        assertFalse(ExtendedLibraryV1.validPlay(ExtendedLibraryV1.Play(song, -1, 3000)))
        assertFalse(ExtendedLibraryV1.validPlay(ExtendedLibraryV1.Play(song, 1000, 0)))
        assertFalse(ExtendedLibraryV1.validPlay(ExtendedLibraryV1.Play("/local/song", 1000, 3000)))
    }

    @Test fun ordersHistoryWithoutDroppingEvents() {
        val first = ExtendedLibraryV1.Play(song, 1000, 500)
        val second = first.copy(timestampMs = 2000)
        val snapshot = ExtendedLibraryV1.Snapshot(listOf(album), listOf(artist), listOf(second, first))
        assertEquals(listOf(first, second), ExtendedLibraryV1.normalize(snapshot).history)
        assertTrue(runCatching { ExtendedLibraryV1.normalize(snapshot.copy(history = listOf(first, first))) }.isFailure)
    }
    @Test fun wireFormatPreservesConsentAndRejectsUnexpectedFields() {
        val snapshot = ExtendedLibraryV1.Snapshot(listOf(album), listOf(artist),
            listOf(ExtendedLibraryV1.Play(song, 1000L, 500L)))
        val wire = ExtendedLibraryV1.body(snapshot)
        assertEquals(snapshot, ExtendedLibraryV1.parse(wire))
        assertNull(ExtendedLibraryV1.parse(wire + ("history" to null)).history)
        assertTrue(runCatching { ExtendedLibraryV1.parse(wire + ("token" to "secret")) }.isFailure)
        assertTrue(runCatching { ExtendedLibraryV1.parse(wire + ("history" to listOf(
            mapOf("song_id" to song, "timestamp_ms" to true, "played_ms" to 500L)))) }.isFailure)
        assertTrue(AccountProofV2.canonicalBody("extended_write",
            mapOf("revision" to 0L, "library" to wire)).contains("timestamp_ms"))
    }
}

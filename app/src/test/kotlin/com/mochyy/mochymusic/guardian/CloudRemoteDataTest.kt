package com.mochyy.mochymusic.guardian

import org.junit.Assert.*
import org.junit.Test

class CloudRemoteDataTest {
    private val body = mapOf(
        "favorites" to listOf("song_a", "legacy_123"),
        "playlists" to listOf(mapOf("id" to "p1", "name" to "Saved", "tracks" to listOf("song_a"))),
        "preferences" to mapOf("theme" to "dark", "shuffle" to true),
    )

    @Test fun legacyIdsCanBeExportedAndReviewed() {
        val snapshot = CloudRemoteData.inspect(1, body)
        assertEquals(2, snapshot.favorites)
        assertEquals(1, snapshot.playlists)
        assertTrue(snapshot.json.contains("song_a"))
        assertTrue(snapshot.digest.matches(Regex("[a-f0-9]{64}")))
    }

    @Test fun digestBindsExactRevisionAndMetadata() {
        val snapshot = CloudRemoteData.inspect(1, body)
        assertEquals(snapshot, CloudRemoteData.inspect(1, body.toList().reversed().toMap()))
        assertNotEquals(snapshot.digest, CloudRemoteData.inspect(2, body).digest)
        assertNotEquals(snapshot.digest, CloudRemoteData.inspect(1, body + ("favorites" to listOf("song_a"))).digest)
    }

    @Test fun rejectsPrivatePathsAndCredentialFields() {
        val invalid = listOf(
            body + ("favorites" to listOf("/private/file.mp3")),
            body + ("preferences" to mapOf("token" to "secret")),
            body + ("favorites" to listOf("duplicate", "duplicate")),
            body + ("history" to emptyList<String>()),
        )
        invalid.forEach { assertTrue(runCatching { CloudRemoteData.inspect(1, it) }.isFailure) }
        assertTrue(runCatching { CloudRemoteData.inspect(0, body) }.isFailure)
    }
}

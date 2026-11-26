package com.mochyy.mochymusic.guardian

fun main() {
    val a = "a".repeat(11); val b = "b".repeat(11); val c = "c".repeat(11)
    fun playlist(id: String = "p", name: String = "Mix", tracks: List<String> = listOf(a,b)) =
        mapOf("id" to id, "name" to name, "tracks" to tracks)
    fun library(favorites: List<String> = listOf(a,b), playlists: List<Map<String,Any>> = listOf(playlist()),
                preferences: Map<String,Any> = mapOf("theme" to "dark")) =
        mapOf("favorites" to favorites,"playlists" to playlists,"preferences" to preferences)
    val original = CloudMetadata.parse(library())
    var checks = 0
    fun verify(value: Boolean) { check(value); checks++ }
    fun rejected(body: Map<String,Any?>) { verify(runCatching { CloudMetadata.parse(body) }.isFailure) }
    verify(original.digest() == CloudMetadata.parse(library(favorites=listOf(b,a))).digest())
    verify(original.digest().matches(Regex("[a-f0-9]{64}")))
    verify(CloudMetadata.parse(library(favorites=listOf(a,b,c),playlists=listOf(playlist(tracks=listOf(a,b,c))))).additiveTo(original))
    verify(!CloudMetadata.parse(library(favorites=listOf(a))).additiveTo(original))
    verify(!CloudMetadata.parse(library(playlists=emptyList())).additiveTo(original))
    verify(!CloudMetadata.parse(library(playlists=listOf(playlist(name="New")))).additiveTo(original))
    verify(!CloudMetadata.parse(library(playlists=listOf(playlist(tracks=listOf(b,a))))).additiveTo(original))
    verify(!CloudMetadata.parse(library(playlists=listOf(playlist(tracks=listOf(a,c,b))))).additiveTo(original))
    verify(!CloudMetadata.parse(library(preferences=mapOf("theme" to "light"))).additiveTo(original))
    verify(CloudMetadata.parse(library(playlists=listOf(playlist(),playlist(id="q")))).digest() == CloudMetadata.parse(library(playlists=listOf(playlist(id="q"),playlist()))).digest())
    verify(CloudMetadata.parse(library(playlists=listOf(playlist(name="a:b")))).digest() != original.digest())
    rejected(library(favorites=listOf(a,a)))
    rejected(library(playlists=listOf(playlist(),playlist())))
    rejected(library(playlists=listOf(playlist(id="LP_LIKED"))))
    rejected(library(preferences=mapOf("shuffle" to "true")))
    rejected(library(favorites=listOf("local/path")))
    rejected(library(playlists=listOf(playlist(name="\uD800"))))
    println("Cloud metadata: $checks checks passed")
}

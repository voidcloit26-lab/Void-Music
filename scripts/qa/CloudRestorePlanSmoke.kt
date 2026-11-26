package com.mochyy.mochymusic.guardian

fun main() {
    val a = "a".repeat(11); val b = "b".repeat(11)
    val p = CloudRestorePlan.Playlist("LPabc", "ਪੰਜਾਬੀ 🎵", listOf(a, b))
    val cloud = CloudRestorePlan.Library(listOf(a), listOf(p))
    fun build(favorites: Set<String> = emptySet(), local: Map<String, CloudRestorePlan.Playlist?> = emptyMap(),
              eligible: Set<String> = setOf(a,b)) = CloudRestorePlan.build(cloud, favorites, local, eligible)
    val fresh = build(); check(fresh.ready && fresh.addFavorites == listOf(a) && fresh.addPlaylists == listOf(p))
    val same = build(setOf(a), mapOf(p.id to p)); check(same.ready && same.addFavorites.isEmpty() && same.addPlaylists.isEmpty())
    val conflict = build(local = mapOf(p.id to p.copy(name = "Changed"))); check(!conflict.ready && conflict.conflictingPlaylists == setOf(p.id))
    check(!build(local = mapOf(p.id to null)).ready)
    val missing = build(eligible = setOf(a)); check(!missing.ready && missing.missingTracks == setOf(b))
    fun reject(library: CloudRestorePlan.Library) { check(runCatching { CloudRestorePlan.validate(library) }.isFailure) }
    reject(cloud.copy(favorites = listOf(a, a)))
    reject(cloud.copy(playlists = listOf(p.copy(id = "LP_LIKED"))))
    reject(cloud.copy(playlists = listOf(p.copy(tracks = listOf("/local/song.mp3")))))
    reject(cloud.copy(playlists = listOf(p, p)))
    println("PASS: 9 restore planner checks")
}

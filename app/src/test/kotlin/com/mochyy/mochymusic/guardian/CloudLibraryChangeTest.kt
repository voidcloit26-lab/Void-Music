package com.mochyy.mochymusic.guardian

import org.junit.Assert.*
import org.junit.Test

class CloudLibraryChangeTest {
    private val a = "aaaaaaaaaaa"
    private val b = "bbbbbbbbbbb"
    private val c = "ccccccccccc"
    private fun playlist(id: String, name: String, vararg tracks: String): Map<String, Any?> =
        mapOf("id" to id, "name" to name, "tracks" to tracks.toList())
    private fun library(favorites: List<String>, playlists: List<Map<String, Any?>>,
        preferences: Map<String, Any?> = emptyMap()): Map<String, Any?> =
        mapOf("favorites" to favorites, "playlists" to playlists, "preferences" to preferences)

    @Test fun reviewCountsRemovalsRenamesAndNewItems() {
        val old = library(listOf(a,b), listOf(playlist("one","Old",a,b), playlist("two","Gone",c)))
        val next = library(listOf(b,c), listOf(playlist("one","Renamed",b,a), playlist("three","New",c)))
        val change = CloudLibraryChange.compare(old,next)
        assertEquals(CloudLibraryChange(1,1,1,1,1), change)
        assertTrue(change.removesOrChanges)
    }

    @Test fun favoriteOrderDoesNotCreateFalseChanges() {
        val old = library(listOf(a,b), listOf(playlist("one","List",a)))
        val next = library(listOf(b,a,c), listOf(playlist("one","List",a)))
        assertEquals(CloudLibraryChange(1,0,0,0,0), CloudLibraryChange.compare(old,next))
    }

    @Test fun emptyReplacementExplicitlyReportsEveryRemoval() {
        val old = library(listOf(a,b), listOf(playlist("one","List",a,b)))
        val next = library(emptyList(), emptyList())
        assertEquals(CloudLibraryChange(0,2,0,1,0), CloudLibraryChange.compare(old,next))
    }

    @Test fun preferencesCannotBeChangedByLibraryReplacement() {
        val old = library(emptyList(), emptyList(), mapOf("shuffle" to false))
        val next = library(emptyList(), emptyList(), mapOf("shuffle" to true))
        assertTrue(runCatching { CloudLibraryChange.compare(old,next) }.isFailure)
    }
}

package com.mochyy.mochymusic.guardian

import org.junit.Assert.*
import org.junit.Test

class LocalLibraryBindingTest {
    private val owner = "a".repeat(32)
    private val other = "b".repeat(32)
    @Test fun firstClaimRequiresConsent() {
        assertEquals(LocalLibraryBinding.Status.UNCLAIMED, LocalLibraryBinding.status(null, owner))
        assertFalse(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.UNCLAIMED, false))
        assertTrue(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.UNCLAIMED, true))
    }
    @Test fun matchingOwnerCanReturnAutomatically() {
        assertEquals(LocalLibraryBinding.Status.MATCH, LocalLibraryBinding.status(owner, owner))
        assertTrue(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.MATCH, false))
        assertTrue(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.MATCH, true))
    }
    @Test fun differentAccountCannotClaimExistingLibrary() {
        assertEquals(LocalLibraryBinding.Status.OTHER, LocalLibraryBinding.status(other, owner))
        assertFalse(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.OTHER, false))
        assertFalse(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.OTHER, true))
    }
    @Test fun malformedStateFailsClosed() {
        assertEquals(LocalLibraryBinding.Status.UNAVAILABLE, LocalLibraryBinding.status("", owner))
        assertEquals(LocalLibraryBinding.Status.UNAVAILABLE, LocalLibraryBinding.status("A".repeat(32), owner))
        assertFalse(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.UNAVAILABLE, false))
        assertFalse(LocalLibraryBinding.canUse(LocalLibraryBinding.Status.UNAVAILABLE, true))
        assertTrue(runCatching { LocalLibraryBinding.status(owner, "invalid") }.isFailure)
    }
}

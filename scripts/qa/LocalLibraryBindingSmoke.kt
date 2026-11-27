package com.mochyy.mochymusic.guardian

fun main() {
    val owner = "a".repeat(32)
    val other = "b".repeat(32)
    val status = LocalLibraryBinding::status
    val canUse = LocalLibraryBinding::canUse
    check(status(null, owner) == LocalLibraryBinding.Status.UNCLAIMED)
    check(status(owner, owner) == LocalLibraryBinding.Status.MATCH)
    check(status(other, owner) == LocalLibraryBinding.Status.OTHER)
    check(status("", owner) == LocalLibraryBinding.Status.UNAVAILABLE)
    check(status("A".repeat(32), owner) == LocalLibraryBinding.Status.UNAVAILABLE)
    check(runCatching { status(owner, "invalid") }.isFailure)
    check(!canUse(LocalLibraryBinding.Status.UNCLAIMED, false))
    check(canUse(LocalLibraryBinding.Status.UNCLAIMED, true))
    check(canUse(LocalLibraryBinding.Status.MATCH, false))
    check(canUse(LocalLibraryBinding.Status.MATCH, true))
    check(!canUse(LocalLibraryBinding.Status.OTHER, false))
    check(!canUse(LocalLibraryBinding.Status.OTHER, true))
    check(!canUse(LocalLibraryBinding.Status.UNAVAILABLE, false))
    check(!canUse(LocalLibraryBinding.Status.UNAVAILABLE, true))
    println("PASS: 14 local library ownership checks")
}

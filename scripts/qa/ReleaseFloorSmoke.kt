package com.mochyy.mochymusic.guardian

fun main() {
    val first = ReleaseFloor.accept(null, 2, "manifest-a".toByteArray())
    check(ReleaseFloor.parse(first.encode()) == first)
    check(ReleaseFloor.accept(first, 2, "manifest-a".toByteArray()) == first)
    check(ReleaseFloor.accept(first, 3, "manifest-b".toByteArray()).sequence == 3L)
    check(runCatching { ReleaseFloor.accept(first, 1, "manifest-a".toByteArray()) }.isFailure)
    check(runCatching { ReleaseFloor.accept(first, 2, "manifest-b".toByteArray()) }.isFailure)
    check(runCatching { ReleaseFloor.parse("02:${first.digest}") }.isFailure)
    check(runCatching { ReleaseFloor.parse("2:invalid") }.isFailure)
    check(runCatching { ReleaseFloor.accept(null, 0, byteArrayOf(1)) }.isFailure)
    check(runCatching { ReleaseFloor.accept(null, 1, byteArrayOf()) }.isFailure)
    println("PASS: 9 release floor checks")
}

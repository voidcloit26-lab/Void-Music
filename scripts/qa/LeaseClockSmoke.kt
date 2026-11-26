package com.mochyy.mochymusic.guardian
fun main() {
    val epoch = 1800000000L
    check(LeaseClock.now(epoch,1000,1,1000,1)==epoch)
    check(LeaseClock.now(epoch,1000,1,1001,1)==epoch+1)
    check(LeaseClock.now(epoch,1000,1,6000,1)==epoch+5)
    check(runCatching { LeaseClock.now(epoch,1000,1,6000,2) }.isFailure)
    check(runCatching { LeaseClock.now(epoch,1000,1,999,1) }.isFailure)
    check(runCatching { LeaseClock.now(epoch,1000,-1,1000,-1) }.isFailure)
    check(runCatching { LeaseClock.now(epoch,1000,1,86401001,1) }.isFailure)
    println("PASS: 7 offline clock checks")
}

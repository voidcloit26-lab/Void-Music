package com.mochyy.mochymusic.guardian

/** Time derived from a fresh authenticated online response, never wall clock.
 * A reboot, unavailable boot counter, or elapsed-clock reset requires online refresh.
 */
internal object LeaseClock {
    fun now(serverEpoch: Long, receivedElapsedMs: Long, receivedBoot: Int,
            elapsedMs: Long, boot: Int): Long {
        require(serverEpoch in 1..253402300799L)
        require(receivedBoot >= 0 && boot == receivedBoot)
        require(receivedElapsedMs >= 0 && elapsedMs >= receivedElapsedMs)
        val delta = elapsedMs - receivedElapsedMs
        require(delta <= 86400000L) { "Online verification required" }
        return serverEpoch + (delta + 999L) / 1000L
    }
}

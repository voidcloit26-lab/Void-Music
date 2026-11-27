package com.mochyy.mochymusic.discord

/** Main-thread request state; native callback status is meaningful only for a pending send. */
internal class PresenceRetry {
    enum class Phase { Idle, Pending, Accepted, Retry }
    var phase = Phase.Idle
        private set
    private var started = 0L
    private var next = 0L
    private var backoff = 5_000L
    private var refresh = false

    fun requestRefresh() { refresh = true }

    fun observe(now: Long, status: Int) {
        if (phase != Phase.Pending) return
        when {
            status == 2 -> { phase = Phase.Accepted; backoff = 5_000L }
            status == 3 || now - started >= 15_000L -> failed(now)
        }
    }

    fun due(now: Long, changed: Boolean): Boolean =
        phase != Phase.Pending && now >= next &&
            (phase == Phase.Idle || phase == Phase.Retry || changed || refresh ||
                (phase == Phase.Accepted && now - started >= 60_000L))

    fun begin(now: Long, intervalSeconds: Int) {
        check(phase != Phase.Pending)
        started = now
        next = now + maxOf(5_000L, intervalSeconds.coerceIn(1, 10) * 1_000L)
        refresh = false
        phase = Phase.Pending
    }

    fun failed(now: Long) {
        phase = Phase.Retry
        next = maxOf(next, now + backoff)
        backoff = (backoff * 2).coerceAtMost(60_000L)
    }

    fun reset() {
        phase = Phase.Idle
        started = 0L; next = 0L; backoff = 5_000L; refresh = false
    }
}

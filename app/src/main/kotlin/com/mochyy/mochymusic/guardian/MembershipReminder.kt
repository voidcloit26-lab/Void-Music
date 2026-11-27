package com.mochyy.mochymusic.guardian

/** Display-only reminder using authenticated server time.
 * Expiry authorization remains independent and signature-based.
 */
internal object MembershipReminder {
    enum class Level { NONE, WEEK, THREE_DAYS, LAST_DAY, EXPIRED }
    fun level(expiresAt: Long?, now: Long, active: Boolean): Level {
        require(now in 1..253402300799L)
        if (expiresAt == null) return Level.NONE
        require(expiresAt in 1..253402300799L)
        if (!active) return if (now >= expiresAt) Level.EXPIRED else Level.NONE
        val remaining = expiresAt - now
        return when {
            remaining <= 0 -> Level.EXPIRED
            remaining <= 86400L -> Level.LAST_DAY
            remaining <= 259200L -> Level.THREE_DAYS
            remaining <= 604800L -> Level.WEEK
            else -> Level.NONE
        }
    }
}

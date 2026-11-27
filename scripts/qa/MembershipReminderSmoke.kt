package com.mochyy.mochymusic.guardian

fun main() {
    val n = 1800000000L
    val day = 86400L
    val level = MembershipReminder::level
    check(level(null,n,true) == MembershipReminder.Level.NONE)
    check(level(n+8*day,n,true) == MembershipReminder.Level.NONE)
    check(level(n+7*day,n,true) == MembershipReminder.Level.WEEK)
    check(level(n+3*day+1,n,true) == MembershipReminder.Level.WEEK)
    check(level(n+3*day,n,true) == MembershipReminder.Level.THREE_DAYS)
    check(level(n+day+1,n,true) == MembershipReminder.Level.THREE_DAYS)
    check(level(n+day,n,true) == MembershipReminder.Level.LAST_DAY)
    check(level(n+1,n,true) == MembershipReminder.Level.LAST_DAY)
    check(level(n,n,true) == MembershipReminder.Level.EXPIRED)
    check(level(n-1,n,false) == MembershipReminder.Level.EXPIRED)
    check(level(n+day,n,false) == MembershipReminder.Level.NONE)
    check(runCatching { level(n,0,true) }.isFailure)
    println("PASS: 12 membership reminder checks")
}

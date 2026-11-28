package com.mochyy.mochymusic.guardian

import android.content.Context

/** Disabled builds never authorize a V2 entitlement. */
internal object GuardianV2Runtime {
    fun allowed(context:Context):Boolean=false
    fun authorizedAccount(context:Context):String?=null
    suspend fun refresh(context:Context):Boolean=false
    fun clearIfLocked(context:Context):Boolean { GuardianGate.changed(); return true }
}

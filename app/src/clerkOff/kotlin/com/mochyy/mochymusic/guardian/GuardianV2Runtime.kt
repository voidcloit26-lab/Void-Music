package com.mochyy.mochymusic.guardian

import android.content.Context

/** Disabled builds never authorize a V2 entitlement. */
internal object GuardianV2Runtime {
    fun allowed(context:Context):Boolean=false
    suspend fun refresh(context:Context):Boolean=false
}

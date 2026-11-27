package com.mochyy.mochymusic.guardian

import android.app.Activity
import android.os.Bundle

/** Disabled manifest component; no Clerk dependency in ordinary builds. */
class ClerkQaActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        finish()
    }
}

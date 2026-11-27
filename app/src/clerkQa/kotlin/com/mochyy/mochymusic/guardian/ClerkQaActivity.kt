package com.mochyy.mochymusic.guardian

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import com.mochyy.mochymusic.BuildConfig

/** Non-exported, explicitly opt-in staging account screen. Never grants V1 playback. */
class ClerkQaActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!BuildConfig.VOID_CLERK_QA_ENABLED || GuardianGate.enforced) {
            finish()
            return
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val initialized = runCatching { ClerkQaBridge.initialize(applicationContext) }.isSuccess
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize()) {
                    if (initialized) {
                        ClerkGuardianQaHost("https://void-guardian-v2-stage.onrender.com")
                    } else {
                        Text("Staging authentication is unavailable. Close this page and retry.")
                    }
                }
            }
        }
    }
}

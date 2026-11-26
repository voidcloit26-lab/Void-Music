package com.mochyy.mochymusic.guardian

import android.content.Context
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.clerk.api.Clerk
import com.clerk.api.network.serialization.onSuccess
import com.clerk.api.session.GetTokenOptions
import com.clerk.ui.auth.AuthView

/**
 * Explicit QA-only bridge. Not installed in the default source set, not
 * invoked by App.onCreate, and not a replacement for Guardian authorization.
 */
internal object ClerkQaBridge {
    @Synchronized
    fun initialize(context: Context, publishableKey: String) {
        require(Regex("pk_test_[A-Za-z0-9+/=_-]{8,512}").matches(publishableKey))
        Clerk.initialize(context.applicationContext, publishableKey = publishableKey)
    }

    suspend fun currentSession(): GuardianAccountClient.Session {
        check(Clerk.isInitialized.value)
        val subject = checkNotNull(Clerk.userFlow.value).id
        val sid = checkNotNull(Clerk.session).id
        var token: String? = null
        Clerk.auth.getToken(GetTokenOptions(template = "void-music-api")).onSuccess { token = it }
        // Do not pair a token with an identity that changed mid-request.
        check(Clerk.userFlow.value?.id == subject && Clerk.session?.id == sid)
        return GuardianAccountClient.Session(checkNotNull(token), subject, sid)
    }

    suspend fun signOut() {
        Clerk.auth.signOut()
    }
}

/** Authentication only. Signed in never means that premium is active. */
@Composable
internal fun ClerkQaAuthScreen(signedIn: @Composable () -> Unit) {
    val initialized by Clerk.isInitialized.collectAsState()
    val user by Clerk.userFlow.collectAsState()
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        when {
            !initialized -> CircularProgressIndicator()
            user == null -> AuthView()
            else -> signedIn()
        }
    }
}

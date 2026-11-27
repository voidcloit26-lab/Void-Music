package com.mochyy.mochymusic.guardian

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.mochyy.mochymusic.R
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.clerk.api.Clerk
import com.clerk.api.network.serialization.ClerkResult
import com.mochyy.mochymusic.BuildConfig
import com.mochyy.mochymusic.App
import com.clerk.ui.auth.AuthView

/**
 * Explicit QA-only bridge. Not installed in the default source set, not
 * invoked by App.onCreate, and not a replacement for Guardian authorization.
 */
internal object ClerkQaBridge {
    @Synchronized
    fun initialize(context: Context, publishableKey: String = BuildConfig.VOID_CLERK_QA_PUBLISHABLE_KEY) {
        require(Regex("pk_test_[A-Za-z0-9+/=_-]{8,512}").matches(publishableKey))
        if (!Clerk.isInitialized.value) Clerk.initialize(context.applicationContext, publishableKey = publishableKey)
    }

    suspend fun currentSession(): GuardianAccountClient.Session {
        check(Clerk.isInitialized.value)
        val subject = checkNotNull(Clerk.userFlow.value).id
        val sid = checkNotNull(Clerk.session).id
        val token = when (val result = Clerk.auth.getToken()) {
            is ClerkResult.Success -> result.value
            is ClerkResult.Failure -> error("Session token unavailable")
        }
        // Do not pair a token with an identity that changed mid-request.
        check(Clerk.userFlow.value?.id == subject && Clerk.session?.id == sid)
        return GuardianAccountClient.Session(token, subject, sid)
    }

    suspend fun signOut() {
        check(Clerk.auth.signOut() is ClerkResult.Success) { "Sign out failed" }
    }
}

/** Authentication only. Signed in never means that premium is active. */
@Composable
internal fun ClerkQaAuthScreen(signedIn: @Composable () -> Unit) {
    val initialized by Clerk.isInitialized.collectAsState()
    val user by Clerk.userFlow.collectAsState()
    val activeSession by Clerk.sessionFlow.collectAsState()
    val initializationError by Clerk.initializationError.collectAsState()
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        when {
            !initialized && initializationError != null -> Text("Authentication unavailable. Reopen the app to retry.")
            !initialized -> CircularProgressIndicator()
            user == null || activeSession == null -> Column(Modifier.fillMaxSize()) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(painter = painterResource(R.drawable.ic_mochy_mark), contentDescription = "VOID Music",
                        modifier = Modifier.size(38.dp), tint = MaterialTheme.colorScheme.onSurface)
                    Text("Welcome to VOID Music", style = MaterialTheme.typography.headlineMedium)
                    Text("Your music. Your account. Sign in or create an account with your verified email.",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Membership activation and device recovery are handled after sign-in.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Box(Modifier.fillMaxWidth().weight(1f)) { AuthView() }
            }
            else -> key(user?.id, activeSession?.id) { signedIn() }
        }
    }
}


/** Composes the registered account screen for an explicitly supplied QA origin.
 * Never invoke from the V1 playback gate; no real service is selected here. */
@Composable
internal fun ClerkGuardianQaHost(origin: String, gateEntry: Boolean = false) {
    ClerkQaAuthScreen {
        val user by Clerk.userFlow.collectAsState()
        val activeSession by Clerk.sessionFlow.collectAsState()
        val subject = user?.id
        val sid = activeSession?.id
        if (subject != null && sid != null) {
            key(subject, sid) {
                val client = remember(origin, subject, sid) {
                    GuardianAccountClient(origin, session = { ClerkQaBridge.currentSession() },
                        expectedSubject = subject, expectedSessionId = sid)
                }
                val context = LocalContext.current
                val lease = remember(client, context.applicationContext) {
                    GuardianQaLease(context, client) {
                        Clerk.userFlow.value?.id == subject && Clerk.session?.id == sid
                    }
                }
                DisposableEffect(lease) {
                    lease.clear()
                    onDispose { lease.close() }
                }
                val cloud = remember(client, context.applicationContext) {
                    GuardianQaCloud((context.applicationContext as App).musicDatabase, client) {
                        Clerk.userFlow.value?.id == subject && Clerk.session?.id == sid
                    }
                }
                val business = remember(subject, sid) { GuardianBusinessQaClient(subject,sid) }
                GuardianAccountQaScreen(client, lease, cloud, business, gateEntry, onSignOut = {
                    lease.clear()
                    ClerkQaBridge.signOut()
                })
            }
        }
    }
}

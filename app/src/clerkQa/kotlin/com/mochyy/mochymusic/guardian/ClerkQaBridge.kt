package com.mochyy.mochymusic.guardian

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.material3.TextButton
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.clerk.api.Clerk
import com.clerk.api.network.serialization.ClerkResult
import com.mochyy.mochymusic.BuildConfig
import com.mochyy.mochymusic.App
import com.clerk.ui.auth.AuthView
import com.clerk.api.ui.ClerkTheme
import com.clerk.api.ui.ClerkColors
import com.clerk.api.ui.ClerkDesign
import com.clerk.api.ui.ClerkTypography
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.imePadding
import com.mochyy.mochymusic.ui.theme.InterFontFamily

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
internal fun ClerkQaAuthScreen(signedIn: @Composable (String) -> Unit) {
    val initialized by Clerk.isInitialized.collectAsState()
    val user by Clerk.userFlow.collectAsState()
    val activeSession by Clerk.sessionFlow.collectAsState()
    val initializationError by Clerk.initializationError.collectAsState()
    var showEmail by remember { mutableStateOf(false) }
    var signup by remember { mutableStateOf(false) }
    var activationCode by remember { mutableStateOf("") }
    // A redeemable credential stays in memory only until handed to the authenticated session.
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        when {
            !initialized && initializationError != null -> Text("Authentication unavailable. Reopen the app to retry.")
            !initialized -> CircularProgressIndicator()
            (user == null || activeSession == null) && !showEmail -> GuardianLoginLanding(onEmail = { signup = false; activationCode = ""; showEmail = true },
                onSignup = { signup = true; activationCode = ""; showEmail = true })
            user == null || activeSession == null -> Column(
                Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).imePadding(),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                val colors = MaterialTheme.colorScheme
                val font = InterFontFamily
                val typography = MaterialTheme.typography
                val palette = remember(colors) {
                    ClerkColors(background = colors.background, foreground = colors.onBackground,
                        primary = colors.primary, primaryForeground = colors.onPrimary,
                        input = colors.surfaceVariant, inputForeground = colors.onSurface,
                        muted = colors.surfaceVariant, mutedForeground = Color(0xFFB0B0B0),
                        border = Color(0xFF333333), ring = colors.primary, danger = colors.error)
                }
                val theme = remember(palette, font, typography) {
                    ClerkTheme(colors = palette, lightColors = palette, darkColors = palette,
                        design = ClerkDesign(borderRadius = 18.dp),
                        typography = ClerkTypography(
                            displaySmall = typography.displaySmall,
                            headlineLarge = typography.headlineLarge,
                            headlineMedium = typography.headlineMedium,
                            titleMedium = typography.titleMedium,
                            titleSmall = typography.titleSmall,
                            bodyLarge = typography.bodyLarge,
                            bodyMedium = typography.bodyMedium,
                            bodySmall = typography.bodySmall,
                            labelMedium = typography.labelMedium,
                            labelSmall = typography.labelSmall))
                }
                Column(Modifier.widthIn(max = 480.dp).fillMaxWidth().padding(horizontal = 24.dp, vertical = 12.dp)) {
                    GuardianBrandHeader("VOID Music", "Your music. Your account.")
                    TextButton(onClick = { showEmail = false; signup = false; activationCode = "" }) { Text("Other sign-in options") }
                    if (signup) {
                        androidx.compose.material3.OutlinedTextField(activationCode,
                            { activationCode = it.trim().take(43) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(), label = { Text("Activation code") },
                            visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation())
                        Text("Create and verify your email account below, then confirm this code to activate premium.", style = typography.bodySmall)
                    }
                }
                Box(Modifier.weight(1f).widthIn(max = 480.dp).fillMaxWidth()) {
                    AuthView(clerkTheme = theme, isDismissible = false)
                }
                Text("Secured by VOID Guardian", style = typography.bodySmall,
                    color = colors.onSurface.copy(alpha = 0.56f),
                    modifier = Modifier.padding(vertical = 8.dp))
            }
            else -> key(user?.id, activeSession?.id) {
                // Capture the pending code for this session only. After successful
                // composition, clear the landing state so a later sign-in cannot
                // inherit a prior account's activation code.
                val sessionCode = remember { if (signup) activationCode else "" }
                androidx.compose.runtime.SideEffect {
                    if (signup || showEmail || activationCode.isNotEmpty()) {
                        activationCode = ""
                        signup = false
                        showEmail = false
                    }
                }
                signedIn(sessionCode)
            }
        }
    }
}


/** Composes the registered account screen for an explicitly supplied QA origin.
 * Never invoke from the V1 playback gate; no real service is selected here. */
@Composable
internal fun ClerkGuardianQaHost(origin: String, gateEntry: Boolean = false) {
    ClerkQaAuthScreen { signupCode ->
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
                    GuardianQaCloud(context.applicationContext, (context.applicationContext as App).musicDatabase, client,
                        ownsLibrary = { account ->
                            GuardianLocalLibraryOwner.status(context.applicationContext, account) == LocalLibraryBinding.Status.MATCH
                        }) {
                        Clerk.userFlow.value?.id == subject && Clerk.session?.id == sid
                    }
                }
                val business = remember(subject, sid) { GuardianBusinessQaClient(subject,sid) }
                GuardianAccountQaScreen(client, lease, cloud, business, gateEntry, initialCode = signupCode, onSignOut = {
                    // Invalidate playback and in-flight sync before remote sign-out.
                    GuardianV2Runtime.clear(context.applicationContext)
                    lease.clear()
                    ClerkQaBridge.signOut()
                })
            }
        }
    }
}

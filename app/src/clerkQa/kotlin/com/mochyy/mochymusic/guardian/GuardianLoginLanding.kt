package com.mochyy.mochymusic.guardian

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.clerk.api.Clerk
import com.clerk.api.network.serialization.ClerkResult
import com.clerk.api.sso.OAuthProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Native VOID landing. Clerk remains the authority for every authentication
 * factor; a returned OAuth response never grants Guardian playback access. */
@Composable
internal fun GuardianLoginLanding(onEmail: () -> Unit, onSignup: () -> Unit) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    GuardianAccountLayout {
        Spacer(Modifier.height(24.dp))
        GuardianBrandHeader("VOID Music", "Your music. Your account.")
        Spacer(Modifier.height(24.dp))
        Text("Welcome to VOID", style = MaterialTheme.typography.headlineLarge)
        Text("Sign in or create an account to continue.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.68f))
        if (error.isNotEmpty()) GuardianAccountNotice(error)
        Button(onClick = {
            if (!busy) {
                busy = true
                error = ""
                scope.launch {
                    try {
                        when (Clerk.auth.signInWithOAuth(OAuthProvider.GOOGLE)) {
                            is ClerkResult.Success -> {
                                // Clerk's actual session/user flows determine completion.
                                // If additional verification is needed, keep SDK UI available.
                                if (Clerk.userFlow.value == null || Clerk.session == null) onEmail()
                            }
                            is ClerkResult.Failure -> error = "Google sign-in did not complete. Try again or continue with email."
                        }
                    } catch (e: CancellationException) {
                        throw e
                    } catch (_: Exception) {
                        error = "Google sign-in is temporarily unavailable. Continue with email or retry."
                    } finally { busy = false }
                }
            }
        }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp),
            shape = RoundedCornerShape(18.dp)) {
            Text(if (busy) "Connecting…" else "Sign in with Google")
        }
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            HorizontalDivider(modifier = Modifier.weight(1f))
            Text("OR", style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            HorizontalDivider(modifier = Modifier.weight(1f))
        }
        OutlinedButton(onClick = onEmail, enabled = !busy,
            modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp), shape = RoundedCornerShape(18.dp)) {
            Text("Sign in with email")
        }
        OutlinedButton(onClick = onSignup, enabled = !busy,
            modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp), shape = RoundedCornerShape(18.dp)) {
            Text("Create an account")
        }
        Text("New members need an activation code. Existing members can sign in directly.",
            modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.56f))
        Spacer(Modifier.height(16.dp))
        Text("Secured by VOID Guardian", modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center, style = MaterialTheme.typography.labelMedium)
    }
}

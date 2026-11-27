package com.mochyy.mochymusic.guardian

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

/** Two membership actions. Purchases are support referrals, not payments. */
@Composable
internal fun GuardianExpiredMembership(busy: Boolean, error: String, onSignOut: (() -> Unit)? = null, redeem: (String) -> Unit) {
    var page by remember { mutableStateOf("expired") }
    var code by remember { mutableStateOf("") }
    var linkError by remember { mutableStateOf("") }
    val uri = LocalUriHandler.current
    fun open(url: String) {
        linkError = ""
        runCatching { uri.openUri(url) }.onFailure {
            linkError = "Could not open Discord. Please open the link in your browser."
        }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("VOID MUSIC", style = MaterialTheme.typography.labelLarge)
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (error.isNotEmpty()) Text(error, color = MaterialTheme.colorScheme.error)
        when (page) {
            "expired" -> {
                Text("Your membership has ended", style = MaterialTheme.typography.headlineMedium)
                Text("Your account, favorites and playlists are preserved. Renew to restore access.")
                Button(onClick = { page = "key" }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                    Text("Enter renewal key")
                }
                OutlinedButton(onClick = { page = "buy" }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                    Text("Buy membership")
                }
            }
            "key" -> {
                Text("Renew your membership", style = MaterialTheme.typography.headlineMedium)
                Text("Enter the renewal key issued for your membership.")
                OutlinedTextField(code, { code = it.trim().take(43) }, singleLine = true,
                    label = { Text("Renewal key") }, visualTransformation = PasswordVisualTransformation(),
                    enabled = !busy, modifier = Modifier.fillMaxWidth())
                Button(onClick = { val entered = code; code = ""; redeem(entered) },
                    enabled = !busy && Regex("[A-Za-z0-9_-]{43}").matches(code),
                    modifier = Modifier.fillMaxWidth()) { Text("Redeem renewal key") }
                TextButton(onClick = { code = ""; page = "expired" }, enabled = !busy) { Text("Back") }
            }
            "buy" -> {
                Text("Buy membership", style = MaterialTheme.typography.headlineMedium)
                Text("Choose how you want to contact VOID for a renewal key. No payment is collected in this app.")
                Button(onClick = { open("https://discord.com/users/1472442073108971575") }, modifier = Modifier.fillMaxWidth()) {
                    Text("Contact owner directly")
                }
                OutlinedButton(onClick = { open("https://discord.gg/marscm") }, modifier = Modifier.fillMaxWidth()) {
                    Text("Join MARS Community")
                }
                Text("How to renew through MARS", style = MaterialTheme.typography.titleMedium)
                Text("1. Join the Discord server.\n2. Open a support ticket in the ticket section.\n3. Tell the owner you want to renew VOID Music.\n4. Follow the owner's instructions, then redeem your renewal key in the app.")
                Text("Never share your password, OTP or recovery code.", style = MaterialTheme.typography.bodySmall)
                if (linkError.isNotEmpty()) Text(linkError, color = MaterialTheme.colorScheme.error)
                TextButton(onClick = { linkError = ""; page = "expired" }) { Text("Back") }
            }
        }
        if (onSignOut != null) {
            TextButton(onClick = { code = ""; onSignOut() }, enabled = !busy,
                modifier = Modifier.fillMaxWidth()) { Text("Sign out or switch account") }
        }
    }
}

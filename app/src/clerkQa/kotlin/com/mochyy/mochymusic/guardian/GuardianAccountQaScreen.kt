package com.mochyy.mochymusic.guardian

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Disconnected QA screen: no playback grant, no production payments. */
@Composable
internal fun GuardianAccountQaScreen(client: GuardianAccountClient, lease: GuardianQaLease, onSignOut: suspend () -> Unit) {
    val scope = rememberCoroutineScope()
    var result by remember(client) { mutableStateOf<JSONObject?>(null) }
    var recovery by remember(client) { mutableStateOf("") }
    var key by remember(client) { mutableStateOf("") }
    var error by remember(client) { mutableStateOf("") }
    var busy by remember(client) { mutableStateOf(false) }
    var newRecovery by remember(client) { mutableStateOf<String?>(null) }
    var confirmRecovery by remember(client) { mutableStateOf(false) }
    var leaseVerified by remember(client) { mutableStateOf(false) }
    var cloudSummary by remember(client) { mutableStateOf<String?>(null) }

    suspend fun refresh() {
        result = client.request("status", emptyMap())
        if (result?.optString("status") != "active") {
            lease.clear()
            leaseVerified = false
        }
    }

    fun run(action: suspend () -> Unit) {
        if (busy) return
        busy = true
        error = ""
        scope.launch {
            try {
                action()
            } catch (e: CancellationException) {
                throw e
            } catch (e: GuardianAccountClient.RequestFailed) {
                if (e.status == 401 || e.status == 403) {
                    result = null
                    lease.clear()
                    leaseVerified = false
                    cloudSummary = null
                }
                error = when (e.status) {
                    401 -> "Sign in again to continue."
                    403 -> "Access was not verified. Check the account or recovery code."
                    409 -> "The account state changed. Refresh before retrying."
                    429 -> "Too many requests. Try again later."
                    else -> "Guardian is unavailable. Refresh before retrying."
                }
            } catch (_: Exception) {
                error = "Could not verify your account. Check your connection."
            } finally {
                busy = false
            }
        }
    }

    LaunchedEffect(client) {
        run { refresh() }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("VOID MUSIC", style = MaterialTheme.typography.headlineMedium)
        Text("Account and membership · QA only", style = MaterialTheme.typography.labelLarge)
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (error.isNotEmpty()) Text(error, color = MaterialTheme.colorScheme.error)
        val account = result
        if (account != null) {
            Text("VOID account", style = MaterialTheme.typography.titleMedium)
            Text(account.optString("account"))
            val status = account.optString("status", "unknown")
            Text("Membership: " + status)
            account.optJSONObject("membership")?.let {
                Text("Plan: " + it.optString("kind"))
                if (!it.isNull("expires_at")) Text("Expires: " +
                    java.text.DateFormat.getDateTimeInstance().format(java.util.Date(it.optLong("expires_at") * 1000L)))
            }
            if (status == "unactivated" || status == "expired") {
                OutlinedTextField(key, { key = it.take(43) }, label = { Text("Membership key") },
                    singleLine = true, visualTransformation = PasswordVisualTransformation(), enabled = !busy,
                    modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    val entered = key
                    key = ""
                    run { client.request("redeem_free", mapOf("code" to entered)); refresh() }
                }, enabled = !busy && Regex("[A-Za-z0-9_-]{43}").matches(key)) { Text("Redeem test key") }
                Text("Paid membership is not available in this test build.")
            }
            if (status != "revoked") OutlinedButton(onClick = {
                run { newRecovery = client.request("rotate_recovery", emptyMap()).getString("recovery") }
            }, enabled = !busy && newRecovery == null) { Text("Replace recovery code") }
            if (status == "active") {
                OutlinedButton(onClick = {
                    run {
                        leaseVerified = false
                        leaseVerified = lease.refresh(account.getString("account"))
                        check(leaseVerified)
                    }
                }, enabled = !busy) { Text("Verify offline membership") }
                OutlinedButton(onClick = {
                    run { leaseVerified = lease.checkCached(account.getString("account")) }
                }, enabled = !busy) { Text("Check cached authorization") }
                Text(if (leaseVerified) "Signed lease verified" else "Offline lease not verified")
            }
            OutlinedButton(onClick = {
                run {
                    cloudSummary = null
                    val remote = client.request("cloud_read", emptyMap())
                    val revision = remote.getLong("revision")
                    require(revision >= 0L)
                    cloudSummary = if (remote.isNull("library")) {
                        require(revision == 0L)
                        "No cloud backup yet"
                    } else {
                        require(revision > 0L)
                        val library = GuardianCloudRestore.parse(remote.getJSONObject("library"))
                        "Revision $revision: ${library.favorites.size} favorites, ${library.playlists.size} playlists"
                    }
                }
            }, enabled = !busy) { Text("Inspect cloud backup") }
            cloudSummary?.let { Text(it) }
            Text("Cloud inspection is read-only. No local library data is uploaded.")
            Text("This screen does not unlock playback. The signed entitlement gate remains separate.")
        } else {
            Button(onClick = {
                run {
                    val created = client.request("register", emptyMap())
                    newRecovery = created.getString("recovery")
                    refresh()
                }
            }, enabled = !busy && newRecovery == null) { Text("Create new VOID account") }
            OutlinedTextField(recovery, { recovery = it.take(43) }, label = { Text("Existing recovery code") },
                singleLine = true, enabled = !busy, visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth())
            Button(onClick = { confirmRecovery = true },
                enabled = !busy && newRecovery == null && Regex("[A-Za-z0-9_-]{43}").matches(recovery)) {
                Text("Recover existing account")
            }
        }
        OutlinedButton(onClick = { run { refresh() } }, enabled = !busy) { Text("Refresh membership") }
        OutlinedButton(onClick = {
            run {
                onSignOut()
                result = null
                key = ""
                recovery = ""
                newRecovery = null
                leaseVerified = false
                cloudSummary = null
            }
        }, enabled = !busy && newRecovery == null) { Text("Sign out") }
    }
    if (confirmRecovery) AlertDialog(
        onDismissRequest = { confirmRecovery = false },
        title = { Text("Replace registered device?") },
        text = { Text("The old device will lose online authorization. Save the replacement recovery code.") },
        confirmButton = {
            TextButton(onClick = {
                confirmRecovery = false
                val entered = recovery
                recovery = ""
                run {
                    val response = client.request("recover", mapOf("recovery" to entered))
                    newRecovery = response.getString("recovery")
                    refresh()
                }
            }) { Text("Replace device") }
        },
        dismissButton = { TextButton(onClick = { confirmRecovery = false }) { Text("Cancel") } }
    )
    newRecovery?.let { value ->
        AlertDialog(onDismissRequest = {},
            title = { Text("Save your recovery code") },
            text = { Text("Keep this code in a secure password manager. It is shown once. Do not share it.\n\n$value") },
            confirmButton = { TextButton(onClick = { newRecovery = null }) { Text("I saved it") } })
    }
}

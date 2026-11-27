package com.mochyy.mochymusic.guardian

import androidx.activity.compose.BackHandler
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
internal fun GuardianAccountQaScreen(client: GuardianAccountClient, lease: GuardianQaLease, cloud: GuardianQaCloud, business: GuardianBusinessQaClient, gateEntry: Boolean, onSignOut: suspend () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = androidx.compose.ui.platform.LocalContext.current
    var recognizedOwner by remember(client) { mutableStateOf(false) }
    var businessOpen by remember(client) { mutableStateOf(false) }
    var result by remember(client) { mutableStateOf<JSONObject?>(null) }
    var linkRequired by remember(client) { mutableStateOf(false) }
    var recovery by remember(client) { mutableStateOf("") }
    var key by remember(client) { mutableStateOf("") }
    var error by remember(client) { mutableStateOf("") }
    var busy by remember(client) { mutableStateOf(false) }
    var newRecovery by remember(client) { mutableStateOf<String?>(null) }
    var confirmRecovery by remember(client) { mutableStateOf(false) }
    var leaseVerified by remember(client) { mutableStateOf(false) }
    var cloudSummary by remember(client) { mutableStateOf<String?>(null) }
    var approvedBackup by remember(client) { mutableStateOf<GuardianQaCloud.FirstBackup?>(null) }
    var approvedRestore by remember(client) { mutableStateOf<GuardianQaCloud.RestorePreview?>(null) }
    var approvedUpdate by remember(client) { mutableStateOf<GuardianQaCloud.UpdatePreview?>(null) }

    suspend fun refresh() {
        linkRequired = false
        try {
            result = client.request("status", emptyMap())
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            result = null
            linkRequired = e is GuardianAccountClient.RequestFailed && e.status == 403
            throw e
        }
        if (result?.optString("status") != "active") {
            lease.clear()
            leaseVerified = false
            if (GuardianGate.v2Enforced) GuardianV2Runtime.clear(context.applicationContext)
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
                    if (e.status == 401) {
                        recognizedOwner = false
                        linkRequired = false
                    }
                    if (e.status == 401 || result?.optString("status") != "expired") result = null
                    lease.clear()
                    leaseVerified = false
                    cloudSummary = null
                    approvedBackup = null
                    approvedRestore = null
                    approvedUpdate = null
                    if (GuardianGate.v2Enforced) GuardianV2Runtime.clear(context.applicationContext)
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

    fun signOutAccount() {
        if (newRecovery != null) return
        run {
            if (GuardianGate.v2Enforced) GuardianV2Runtime.clear(context.applicationContext)
            onSignOut()
            recognizedOwner = false
            businessOpen = false
            result = null
            linkRequired = false
            key = ""
            recovery = ""
            newRecovery = null
            leaseVerified = false
            cloudSummary = null
            approvedBackup = null
            approvedRestore = null
            approvedUpdate = null
        }
    }

    suspend fun refreshIdentity() {
        recognizedOwner = false
        linkRequired = false
        recognizedOwner = client.request("identity_role", emptyMap()).optString("role") == "owner"
        refresh()
    }

    BackHandler(enabled = newRecovery != null) { /* Save the one-time code before leaving. */ }

    LaunchedEffect(client) {
        run {
            refreshIdentity()
            val current = result
            if (gateEntry && GuardianGate.v2Enforced && current?.optString("status") == "active") {
                check(GuardianV2Runtime.authorize(context.applicationContext, client, current.getString("account")))
                GuardianV2Runtime.openMusic(context)
            }
        }
    }

    if (businessOpen && recognizedOwner) {
        GuardianBusinessQaScreen(business) { businessOpen = false }
        return
    }

    if (result?.optString("status") == "expired" && newRecovery == null) {
        GuardianExpiredMembership(busy, error, onSignOut = if (newRecovery == null) ({ signOutAccount() }) else null) { entered ->
            run {
                client.request("redeem_activation", mapOf("code" to entered))
                refresh()
            }
        }
        return
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
            if (recognizedOwner && status == "active") Button(onClick = { businessOpen = true }, enabled = !busy) { Text("Guardian Business") }
            account.optJSONObject("membership")?.let {
                Text("Plan: " + it.optString("kind"))
                if (!it.isNull("expires_at")) Text("Expires: " +
                    java.text.DateFormat.getDateTimeInstance().format(java.util.Date(it.optLong("expires_at") * 1000L)))
                if (!it.isNull("expires_at") && account.has("server_time")) {
                    val level = runCatching { MembershipReminder.level(it.getLong("expires_at"), account.getLong("server_time"), status == "active") }.getOrNull()
                    val notice = when (level) {
                        MembershipReminder.Level.WEEK -> "Your membership expires within 7 days."
                        MembershipReminder.Level.THREE_DAYS -> "Your membership expires within 3 days."
                        MembershipReminder.Level.LAST_DAY -> "Your membership expires within 24 hours."
                        else -> null
                    }
                    notice?.let { message -> Text(message, color = MaterialTheme.colorScheme.tertiary) }
                }
            }
            if (status == "unactivated") {
                OutlinedTextField(key, { key = it.take(43) }, label = { Text("Membership key") },
                    singleLine = true, visualTransformation = PasswordVisualTransformation(), enabled = !busy,
                    modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    val entered = key
                    key = ""
                    run { client.request("redeem_activation", mapOf("code" to entered)); refresh() }
                }, enabled = !busy && Regex("[A-Za-z0-9_-]{43}").matches(key)) { Text("Redeem activation key") }
                Text("No in-app payment. Contact support for membership assistance.")
            }
            if (status != "revoked") OutlinedButton(onClick = {
                run { newRecovery = client.request("rotate_recovery", emptyMap()).getString("recovery") }
            }, enabled = !busy && newRecovery == null) { Text("Replace recovery code") }
            if (status == "active" && GuardianGate.v2Enforced) {
                Button(onClick = {
                    run {
                        check(GuardianV2Runtime.authorize(context.applicationContext, client, account.getString("account")))
                        GuardianV2Runtime.openMusic(context)
                    }
                }, enabled = !busy && newRecovery == null) { Text("Enter VOID Music") }
            }
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
            if (status == "active") {
                OutlinedButton(onClick = {
                    run { approvedBackup = cloud.previewFirst(account.getString("account")) }
                }, enabled = !busy && approvedBackup == null) { Text("Review first cloud backup") }
            }
            if (status == "active") {
                OutlinedButton(onClick = {
                    run { approvedUpdate = cloud.previewUpdate(account.getString("account")) }
                }, enabled = !busy && approvedBackup == null && approvedUpdate == null) {
                    Text("Review backup update")
                }
            }
            OutlinedButton(onClick = {
                run {
                    val preview = cloud.previewRestore(account.getString("account"))
                    approvedRestore = preview?.takeIf { status == "active" && it.plan.ready }
                    cloudSummary = if (preview == null) "No cloud backup yet" else
                        "Restore preview: ${preview.plan.addFavorites.size} favorites, " +
                        "${preview.plan.addPlaylists.size} playlists, " +
                        "${preview.plan.missingTracks.size} missing tracks, " +
                        "${preview.plan.conflictingPlaylists.size} conflicts. No changes made."
                }
            }, enabled = !busy && approvedBackup == null) { Text("Preview restore") }
            Text("No automatic uploads, audio files or overwrites. Only confirm if all reviewed local metadata belongs to you.")
            Text("This screen does not unlock playback. The signed entitlement gate remains separate.")
        } else if (linkRequired) {
            if (recognizedOwner) Button(onClick = {
                run {
                    val created = client.request("register_owner", emptyMap())
                    newRecovery = created.getString("recovery")
                    refresh()
                }
            }, enabled = !busy) { Text("Activate owner lifetime account") }
            Text("Complete your VOID account", style = MaterialTheme.typography.titleMedium)
            Text("This device could not verify a linked account. If you are new, enter the activation key supplied by VOID. Existing members should use account recovery.")
            OutlinedTextField(key, { key = it.trim().take(43) }, label = { Text("Activation key") },
                singleLine = true, visualTransformation = PasswordVisualTransformation(), enabled = !busy,
                modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                val entered = key
                key = ""
                run {
                    val created = client.request("register_with_code", mapOf("code" to entered))
                    newRecovery = created.getString("recovery")
                    refresh()
                }
            }, enabled = !busy && newRecovery == null && Regex("[A-Za-z0-9_-]{43}").matches(key)) {
                Text("Activate my account")
            }
            OutlinedTextField(recovery, { recovery = it.take(43) }, label = { Text("Existing recovery code") },
                singleLine = true, enabled = !busy, visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth())
            Button(onClick = { confirmRecovery = true },
                enabled = !busy && newRecovery == null && Regex("[A-Za-z0-9_-]{43}").matches(recovery)) {
                Text("Recover existing account")
            }
        } else {
            Text(if (busy) "Checking your VOID account…" else "Account status unavailable. Refresh to continue safely.")
        }
        OutlinedButton(onClick = { run { refreshIdentity() } }, enabled = !busy && newRecovery == null) { Text("Refresh membership") }
        OutlinedButton(onClick = {
            signOutAccount()
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
    approvedUpdate?.let { approved ->
        AlertDialog(onDismissRequest = { if (!busy) approvedUpdate = null },
            title = { Text("Update saved library?") },
            text = { Text("Upload additions to backup revision ${approved.revision}. Existing remote metadata must be preserved. Confirm only if this entire local library belongs to your signed-in account.") },
            confirmButton = { TextButton(onClick = {
                approvedUpdate = null
                run {
                    val revision = cloud.confirmUpdate(approved, confirmed = true)
                    cloudSummary = "Backup updated to revision $revision."
                }
            }, enabled = !busy) { Text("Update my backup") } },
            dismissButton = { TextButton(onClick = { approvedUpdate = null }, enabled = !busy) { Text("Cancel") } })
    }
    approvedRestore?.let { approved ->
        AlertDialog(onDismissRequest = { if (!busy) approvedRestore = null },
            title = { Text("Restore saved library?") },
            text = { Text("Add ${approved.plan.addFavorites.size} favorites and ${approved.plan.addPlaylists.size} playlists from this account. Existing items will not be removed or overwritten. Continue only if this local library belongs to you.") },
            confirmButton = { TextButton(onClick = {
                approvedRestore = null
                run {
                    cloud.confirmRestore(approved, confirmed = true)
                    cloudSummary = "Saved library restored without overwriting existing items."
                }
            }, enabled = !busy) { Text("Restore my library") } },
            dismissButton = { TextButton(onClick = { approvedRestore = null }, enabled = !busy) { Text("Cancel") } })
    }
    approvedBackup?.let { approved ->
        val favorites = approved.preview.body["favorites"] as? List<*> ?: emptyList<Any>()
        val playlists = approved.preview.body["playlists"] as? List<*> ?: emptyList<Any>()
        AlertDialog(onDismissRequest = { if (!busy) approvedBackup = null },
            title = { Text("Confirm first cloud backup") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text("Account: ${approved.account}")
                    Text("${favorites.size} favorites, ${playlists.size} playlists, ${approved.preview.excludedEntries} excluded entries.")
                    Text("This sends eligible song IDs and playlist names/track IDs. Local audio and file paths are excluded.")
                    Text("Confirm only if this entire local library belongs to you. Existing remote data cannot be overwritten.")
                    playlists.take(100).forEach { item ->
                        val name = (item as? Map<*, *>)?.get("name") as? String
                        if (name != null) Text(name)
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    approvedBackup = null
                    run {
                        val revision = cloud.confirmFirst(approved, confirmed = true)
                        cloudSummary = "First backup saved at revision $revision."
                    }
                }, enabled = !busy) { Text("I own this library — back up") }
            },
            dismissButton = { TextButton(onClick = { approvedBackup = null }, enabled = !busy) { Text("Cancel") } })
    }
    newRecovery?.let { value ->
        AlertDialog(onDismissRequest = {},
            title = { Text("Save your recovery code") },
            text = { Text("Keep this code in a secure password manager. It is shown once. Do not share it.\n\n$value") },
            confirmButton = { TextButton(onClick = { newRecovery = null }) { Text("I saved it") } })
    }
}

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
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Disconnected QA screen: no playback grant, no production payments. */
@Composable
internal fun GuardianAccountQaScreen(client: GuardianAccountClient, lease: GuardianQaLease, cloud: GuardianQaCloud, business: GuardianBusinessQaClient, gateEntry: Boolean, initialCode: String = "", onSignOut: suspend () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = androidx.compose.ui.platform.LocalContext.current
    var recognizedOwner by remember(client) { mutableStateOf(false) }
    var onboarding by remember(client) { mutableStateOf("") }
    var activationAvailable by remember(client) { mutableStateOf(false) }
    var businessOpen by remember(client) { mutableStateOf(false) }
    var showAdvanced by remember(client) { mutableStateOf(false) }
    var attemptedAutoEntry by remember(client) { mutableStateOf<JSONObject?>(null) }
    var showClaim by remember(client) { mutableStateOf(false) }
    var notice by remember(client) { mutableStateOf("") }
    var profile by remember(client) { mutableStateOf<JSONObject?>(null) }
    var showContact by remember(client) { mutableStateOf(false) }
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var result by remember(client) { mutableStateOf<JSONObject?>(null) }
    var updateState by remember(client) { mutableStateOf<GuardianStableUpdate.Check?>(null) }
    var dismissedRelease by remember(client) { mutableStateOf<Long?>(null) }
    var linkRequired by remember(client) { mutableStateOf(false) }
    var confirmLibraryAccount by remember(client) { mutableStateOf<String?>(null) }
    var recovery by remember(client) { mutableStateOf("") }
    var key by remember(client) { mutableStateOf(initialCode.takeIf { Regex("[A-Za-z0-9_-]{43}").matches(it) } ?: "") }
    var error by remember(client) { mutableStateOf("") }
    var busy by remember(client) { mutableStateOf(false) }
    var newRecovery by remember(client) { mutableStateOf<String?>(null) }
    var confirmRecovery by remember(client) { mutableStateOf(false) }
    var leaseVerified by remember(client) { mutableStateOf(false) }
    var cloudSummary by remember(client) { mutableStateOf<String?>(null) }
    var approvedBackup by remember(client) { mutableStateOf<GuardianQaCloud.FirstBackup?>(null) }
    var approvedRestore by remember(client) { mutableStateOf<GuardianQaCloud.RestorePreview?>(null) }
    var approvedUpdate by remember(client) { mutableStateOf<GuardianQaCloud.UpdatePreview?>(null) }
    var approvedPreferences by remember(client) { mutableStateOf<GuardianQaCloud.PreferencePreview?>(null) }
    var confirmAutoSync by remember(client) { mutableStateOf<String?>(null) }
    var confirmCloudRestore by remember(client) { mutableStateOf<String?>(null) }
    val automaticSyncStatus by GuardianAutomaticSync.status.collectAsState()

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
        if (GuardianStableUpdate.enabled) {
            val verified = GuardianStableUpdate.check(context.applicationContext, client)
            updateState = verified.takeIf { it.decision == "required" ||
                (it.decision == "available" && it.release.sequence != dismissedRelease) }
            if (verified.decision == "required") {
                lease.clear()
                leaseVerified = false
                GuardianV2Runtime.clear(context.applicationContext)
            }
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
        notice = ""
        scope.launch {
            try {
                action()
            } catch (e: CancellationException) {
                throw e
            } catch (e: GuardianAccountClient.RequestFailed) {
                if (e.status == 401 || e.status == 403 || e.status == 426) {
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
                    approvedPreferences = null
                    if (GuardianGate.v2Enforced) GuardianV2Runtime.clear(context.applicationContext)
                }
                error = when (e.status) {
                    401 -> "Your session or verified email could not be confirmed. Refresh first; switch accounts only if the problem persists. (G401)"
                    403 -> "Access was not verified. Check the account or recovery code."
                    400 -> "Account request is incompatible. Refresh or contact VOID support."
                    409 -> "The account state changed. Refresh before retrying."
                    426 -> "A verified update is required. Refresh membership to load the update screen."
                    429 -> "Too many requests. Try again later."
                    503 -> "Guardian could not verify your identity right now. Your sign-in may still be valid. Refresh before retrying. (G503)"
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
            showAdvanced = false
            showClaim = false
            showContact = false
            updateState = null
            dismissedRelease = null
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
                    approvedPreferences = null
        }
    }

    suspend fun refreshIdentity() {
        recognizedOwner = false
        linkRequired = false
        onboarding = ""
        activationAvailable = false
        updateState = null
        val identity = client.request("identity_role", emptyMap())
        recognizedOwner = identity.optString("role") == "owner"
        onboarding = identity.optString("onboarding")
        activationAvailable = identity.optBoolean("activation_available", true)
        if (onboarding == "owner_setup" && recognizedOwner) {
            // Server-recognized, verified owner only. Do not bypass recovery or local library consent.
            val created = client.request("register_owner", emptyMap())
            newRecovery = created.getString("recovery")
            onboarding = "linked"
            refresh()
        } else if (onboarding in setOf("activation_required", "recovery_required", "device_conflict", "configuration_required")) {
            result = null
            lease.clear()
            leaseVerified = false
            if (GuardianGate.v2Enforced) GuardianV2Runtime.clear(context.applicationContext)
            linkRequired = true
        } else {
            refresh()
        }
    }

    BackHandler(enabled = newRecovery != null) { /* Save the one-time code before leaving. */ }

    LaunchedEffect(client) { run { refreshIdentity() } }

    // Enter playback only after verified entitlement and same-account local binding.
    // Recovery code acknowledgement remains a one-time requirement.
    LaunchedEffect(result, busy, newRecovery, updateState, gateEntry) {
        val current = result
        if (!busy && current !== attemptedAutoEntry && newRecovery == null && gateEntry && GuardianGate.v2Enforced &&
            updateState == null && current?.optString("status") == "active" &&
            GuardianLocalLibraryOwner.status(context, current.getString("account")) == LocalLibraryBinding.Status.MATCH) {
            attemptedAutoEntry = current
            run {
                check(GuardianV2Runtime.authorize(context.applicationContext, client, current.getString("account")))
                GuardianV2Runtime.openMusic(context)
            }
        }
    }

    LaunchedEffect(result, gateEntry) {
        val current = result
        profile = null
        if (!gateEntry && current != null) {
            try {
                val loaded = client.request("profile", emptyMap())
                if (loaded.getString("account") == current.getString("account") && result === current) profile = loaded
            } catch (e: CancellationException) { throw e } catch (_: Exception) { /* Optional profile must not block playback. */ }
        }
    }

    val pendingRelease = updateState
    val linkedAccount = result?.optString("account")
    if (pendingRelease != null && linkedAccount != null &&
        Regex("[a-f0-9]{32}").matches(linkedAccount) && newRecovery == null) {
        GuardianUpgradeScreen(pendingRelease.release, pendingRelease.installed, cloud, linkedAccount,
            downloadAndInstall = {
                GuardianStableUpdate.downloadAndInstall(context, client, pendingRelease)
            },
            refreshRelease = { refresh() },
            onOptionalDismiss = {
                if (pendingRelease.decision == "available") {
                    dismissedRelease = pendingRelease.release.sequence
                    updateState = null
                }
            })
        return
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

    GuardianAccountLayout {
        GuardianBrandHeader("Your account", "VOID Music")
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (error.isNotEmpty()) GuardianAccountNotice(error)
        if (notice.isNotEmpty()) Text(notice, color = MaterialTheme.colorScheme.primary)
        val account = result
        if (account != null) {
            Text("VOID Premium", style = MaterialTheme.typography.headlineSmall)
            profile?.let { info ->
                Text(info.getString("email"), style = MaterialTheme.typography.bodyMedium)
                Text("Premium claims: ${info.getInt("total_claims")} · Renewals: ${info.getInt("renewals")}", style = MaterialTheme.typography.bodySmall)
            }
            val status = account.optString("status", "unknown")
            val accountId = account.getString("account")
            val libraryOwner = GuardianLocalLibraryOwner.status(context, accountId)
            val libraryMatches = libraryOwner == LocalLibraryBinding.Status.MATCH
            Text(when (status) {
                "active" -> "Membership active"
                "unactivated" -> "Activation required"
                "revoked", "suspended" -> "Access restricted — contact owner"
                else -> "Membership: $status"
            })
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
            if (status == "active" && GuardianGate.v2Enforced) {
                when (libraryOwner) {
                    LocalLibraryBinding.Status.MATCH -> Button(onClick = {
                        run {
                            check(GuardianV2Runtime.authorize(context.applicationContext, client, accountId))
                            GuardianV2Runtime.openMusic(context)
                        }
                    }, enabled = !busy && newRecovery == null) { Text("Enter VOID Music") }
                    LocalLibraryBinding.Status.UNCLAIMED -> Button(onClick = {
                        confirmLibraryAccount = accountId
                    }, enabled = !busy && newRecovery == null) { Text("Connect my local library") }
                    LocalLibraryBinding.Status.OTHER -> Text("This installation has a different library owner. Sign in to that account. Existing music data has not been changed.", color = MaterialTheme.colorScheme.error)
                    LocalLibraryBinding.Status.UNAVAILABLE -> Text("Local library ownership could not be verified. Access remains locked.", color = MaterialTheme.colorScheme.error)
                }
            }
            if (status == "active" && account.optJSONObject("membership")?.optString("kind") != "lifetime") {
                OutlinedButton(onClick = { showClaim = !showClaim }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                    Text(if (showClaim) "Hide claim code" else "Claim / renew premium")
                }
                if (showClaim) {
                    OutlinedTextField(key, { key = it.trim().take(43) }, label = { Text("Renewal code") },
                        singleLine = true, visualTransformation = PasswordVisualTransformation(), enabled = !busy,
                        modifier = Modifier.fillMaxWidth())
                    Button(onClick = {
                        val entered = key
                        key = ""
                        run {
                            client.request("redeem_activation", mapOf("code" to entered))
                            refresh()
                            showClaim = false
                            notice = "Membership renewed."
                        }
                    }, enabled = !busy && Regex("[A-Za-z0-9_-]{43}").matches(key)) { Text("Claim code") }
                }
            }
            if (status == "active" && libraryMatches && !gateEntry) {
                OutlinedButton(onClick = { confirmCloudRestore = accountId },
                    enabled = !busy && newRecovery == null, modifier = Modifier.fillMaxWidth()) {
                    Text("Restore my saved library")
                }
                Text(when (automaticSyncStatus) {
                    GuardianAutomaticSync.Status.DISABLED -> "Cloud backup: off"
                    GuardianAutomaticSync.Status.ENABLED -> "Cloud backup: on"
                    GuardianAutomaticSync.Status.SYNCING -> "Cloud backup: syncing"
                    GuardianAutomaticSync.Status.REVIEW_REQUIRED -> "Cloud backup: review needed"
                }, style = MaterialTheme.typography.bodySmall)
            }
            OutlinedButton(onClick = { showAdvanced = !showAdvanced }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                Text(if (showAdvanced) "Hide account security & backup" else "Account security & backup")
            }
            if (showAdvanced) {
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
            if (status == "active") {
                OutlinedButton(onClick = {
                    run { approvedBackup = cloud.previewFirst(account.getString("account")) }
                }, enabled = !busy && libraryMatches && approvedBackup == null) { Text("Review first cloud backup") }
            }
            if (status == "active") {
                OutlinedButton(onClick = {
                    run { approvedUpdate = cloud.previewUpdate(account.getString("account")) }
                }, enabled = !busy && libraryMatches && approvedBackup == null && approvedUpdate == null) {
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
            }, enabled = !busy && libraryMatches && approvedBackup == null) { Text("Preview restore") }
            if (status == "active" && libraryMatches) {
                OutlinedButton(onClick = {
                    run { approvedPreferences = cloud.previewPreferences(accountId) }
                }, enabled = !busy && approvedPreferences == null && newRecovery == null &&
                    approvedBackup == null && approvedUpdate == null && approvedRestore == null) { Text("Review saved playback settings") }
                Text("Create a library backup first. Settings changes are separate from music metadata.", style = MaterialTheme.typography.bodySmall)
            }
            if (status == "active" && libraryMatches && GuardianGate.v2Enforced) {
                Text(when (automaticSyncStatus) {
                    GuardianAutomaticSync.Status.DISABLED -> "Automatic backup: off"
                    GuardianAutomaticSync.Status.ENABLED -> "Automatic library backup: on"
                    GuardianAutomaticSync.Status.SYNCING -> "Automatic backup: checking additions"
                    GuardianAutomaticSync.Status.REVIEW_REQUIRED -> "Automatic backup paused. Review your library manually."
                })
                if (automaticSyncStatus == GuardianAutomaticSync.Status.ENABLED ||
                    automaticSyncStatus == GuardianAutomaticSync.Status.SYNCING) {
                    OutlinedButton(onClick = { GuardianV2Runtime.disableAutomaticSync(context) }, enabled = !busy) {
                        Text("Disable automatic backup")
                    }
                } else {
                    OutlinedButton(onClick = { confirmAutoSync = accountId },
                        enabled = !busy && newRecovery == null && approvedBackup == null &&
                            approvedUpdate == null && approvedRestore == null && approvedPreferences == null) {
                        Text("Enable automatic backup")
                    }
                }
            }
            if (!libraryMatches) Text("Local backup and restore require a verified library owner.")
            Text("Audio files stay on this phone. Automatic metadata backup requires your consent; conflicts require review.")
            } // Advanced controls are hidden during normal account use.
        } else if (linkRequired) {
            Text(if (recognizedOwner) "Owner account" else "Complete your VOID account",
                style = MaterialTheme.typography.titleMedium)
            if (onboarding == "configuration_required") {
                Text("Account activation is being configured. Your sign-in succeeded; no membership key is needed until this service is ready.")
            } else if (onboarding == "device_conflict") {
                Text("This device is registered to a different account. Sign in to the original account or contact VOID support.")
            } else {
                if (recognizedOwner && onboarding != "recovery_required") {
                    Text("Your verified owner account includes lifetime access. No activation key is required.")
                    Button(onClick = {
                        run {
                            val created = client.request("register_owner", emptyMap())
                            newRecovery = created.getString("recovery")
                            refresh()
                        }
                    }, enabled = !busy && newRecovery == null) { Text("Activate owner lifetime account") }
                } else if (!recognizedOwner && onboarding != "recovery_required" && activationAvailable) {
                    Text("New members need an activation key supplied by VOID.")
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
                }
                if (onboarding == "recovery_required" || onboarding.isEmpty()) {
                    Text("Recover your existing account on this device. This is not a new membership activation.")
                    OutlinedTextField(recovery, { recovery = it.take(43) }, label = { Text("Existing recovery code") },
                        singleLine = true, enabled = !busy, visualTransformation = PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth())
                    Button(onClick = { confirmRecovery = true },
                        enabled = !busy && newRecovery == null && Regex("[A-Za-z0-9_-]{43}").matches(recovery)) {
                        Text("Recover existing account")
                    }
                }
            }
        } else {
            Text(if (busy) "Checking your VOID account…" else "Account status unavailable. Refresh to continue safely.")
        }
        OutlinedButton(onClick = { showContact = !showContact }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Contact owner / get a code") }
        if (showContact) {
            TextButton(onClick = { runCatching { uri.openUri("https://discord.com/users/1472442073108971575") }.onFailure { error = "Could not open Discord." } }) { Text("Contact on Discord") }
            TextButton(onClick = { runCatching { uri.openUri("https://discord.gg/marscm") }.onFailure { error = "Could not open MARS." } }) { Text("Join MARS Community") }
        }
        TextButton(onClick = { runCatching { uri.openUri("https://voidluxury.in") }.onFailure { error = "Could not open VOID Luxury." } }) { Text("VOID Luxury") }
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
                    approvedPreferences = null
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
    confirmCloudRestore?.let { accountId ->
        AlertDialog(
            onDismissRequest = { confirmCloudRestore = null },
            title = { Text("Restore your music library?") },
            text = { Text("Restore saved favorites and independent playlists from this VOID account. Missing song details will be fetched from the music provider. Existing local music and downloads will not be deleted or overwritten.") },
            confirmButton = { TextButton(onClick = {
                confirmCloudRestore = null
                run {
                    val restored = cloud.restoreAccountLibrary(accountId)
                    notice = if (restored == null) "No saved library found." else "Your saved library has been restored."
                }
            }, enabled = !busy) { Text("Restore") } },
            dismissButton = { TextButton(onClick = { confirmCloudRestore = null }) { Text("Cancel") } }
        )
    }
    confirmAutoSync?.let { accountId ->
        AlertDialog(
            onDismissRequest = { confirmAutoSync = null },
            title = { Text("Enable automatic backup?") },
            text = { Text("Eligible favorites and independent playlists are saved to your VOID account, not Gmail storage. Your choice is remembered on this device for this account. Audio stays on your phone. An existing cloud library must match before synchronization starts. Removals, conflicts and settings changes require review. Sign-out pauses synchronization; you can disable it here.") },
            confirmButton = { TextButton(onClick = {
                confirmAutoSync = null
                run {
                    if (GuardianV2Runtime.enableAutomaticSync(context, accountId)) {
                        cloudSummary = "Automatic library backup enabled for this account on this device."
                    } else {
                        error = "Open your authorized music session first, then return to VOID Account."
                    }
                }
            }, enabled = !busy) { Text("Enable") } },
            dismissButton = { TextButton(onClick = { confirmAutoSync = null }) { Text("Cancel") } }
        )
    }
    approvedPreferences?.let { approved ->
        AlertDialog(
            onDismissRequest = { if (!busy) approvedPreferences = null },
            title = { Text("Saved playback settings") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("On this device: repeat ${approved.local.repeat}, shuffle ${if (approved.local.shuffle) "on" else "off"}")
                    val remote = approved.remote
                    Text(if (remote == null) "Cloud: no complete playback settings saved" else
                        "Cloud: repeat ${remote.repeat}, shuffle ${if (remote.shuffle) "on" else "off"}")
                    Text("Restoration changes stored settings, not your songs. Stop playback first; verify them when you next start music.")
                }
            },
            confirmButton = { TextButton(onClick = {
                approvedPreferences = null
                run { cloudSummary = "Playback settings saved at revision ${cloud.savePreferences(approved, confirmed = true)}." }
            }, enabled = !busy && approved.local != approved.remote) { Text("Back up settings") } },
            dismissButton = {
                Row {
                    TextButton(onClick = { approvedPreferences = null }, enabled = !busy) { Text("Cancel") }
                    TextButton(onClick = {
                        approvedPreferences = null
                        run { cloud.restorePreferences(approved, confirmed = true); cloudSummary = "Saved settings restored. Verify after restarting playback." }
                    }, enabled = !busy && approved.remote != null && approved.remote != approved.local) { Text("Restore") }
                }
            }
        )
    }
    confirmLibraryAccount?.let { accountId ->
        AlertDialog(
            onDismissRequest = { confirmLibraryAccount = null },
            title = { Text("Connect this library?") },
            text = { Text("Only continue if the local music library and downloads belong to your account. This installation can use one account until separate account storage is supported. Existing files are not deleted.") },
            confirmButton = { TextButton(onClick = {
                confirmLibraryAccount = null
                run {
                    check(GuardianV2Runtime.authorize(context.applicationContext, client, accountId, confirmLocalLibrary = true))
                    GuardianV2Runtime.openMusic(context)
                }
            }, enabled = !busy) { Text("Confirm ownership") } },
            dismissButton = { TextButton(onClick = { confirmLibraryAccount = null }) { Text("Cancel") } }
        )
    }
    newRecovery?.let { value ->
        var copyFeedback by remember(value) { mutableStateOf("") }
        AlertDialog(onDismissRequest = {},
            properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false),
            title = { Text("Save your recovery code") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Keep this code in a secure password manager. It is shown once. Do not share it.")
                    Text(value)
                    OutlinedButton(onClick = {
                        copyFeedback = if (GuardianSecretClipboard.copy(context, value)) "Recovery code copied. Paste only into your secure password manager." else "Copy unavailable."
                    }) { Text("Copy recovery code") }
                    if (copyFeedback.isNotEmpty()) Text(copyFeedback)
                }
            },
            confirmButton = { TextButton(onClick = { newRecovery = null }) { Text("I saved it") } })
    }
}

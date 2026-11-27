package com.mochyy.mochymusic.guardian

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Render only after verification of the signed stable release policy.
 * The caller owns the runtime version gate and the verified APK installer.
 * This screen does not grant playback, synthesize an update or store secrets.
 */
@Composable
internal fun GuardianUpgradeScreen(
    release: SignedGuardianPolicy.Release,
    installedVersion: Long,
    cloud: GuardianQaCloud,
    account: String,
    downloadAndInstall: suspend () -> Boolean,
    onOptionalDismiss: () -> Unit
) {
    val decision = release.decision(installedVersion)
    require(decision == "required" || decision == "available")
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember(account, release.sequence) { mutableStateOf(false) }
    var error by remember(account, release.sequence) { mutableStateOf("") }
    var preview by remember(account, release.sequence) { mutableStateOf<GuardianQaCloud.UpgradeBackup?>(null) }
    var receipt by remember(account, release.sequence) { mutableStateOf<GuardianQaCloud.UpgradeReceipt?>(null) }
    var savedRevision by remember(account, release.sequence) { mutableStateOf<Long?>(null) }
    var copied by remember(account, release.sequence) { mutableStateOf(false) }
    var confirmInstall by remember(account, release.sequence) { mutableStateOf(false) }

    fun run(action: suspend () -> Unit) {
        if (busy) return
        busy = true
        error = ""
        scope.launch {
            try { action() }
            catch (e: CancellationException) { throw e }
            catch (e: GuardianAccountClient.RequestFailed) {
                error = when (e.status) {
                    409 -> "The cloud library changed or contains conflicting music. Review your backup before updating."
                    401,403 -> "Account verification required. Your existing data has not been intentionally deleted."
                    429 -> "Too many requests. Try again shortly."
                    else -> "Guardian could not complete the request. Verify your backup before retrying."
                }
            }
            catch (_: Exception) { error = "Could not complete this operation. Keep the current app installed and retry." }
            finally { busy = false }
        }
    }

    BackHandler(enabled = decision == "required" || busy || receipt != null) {
        // No navigation into unsupported playback. Installer confirmation is separate.
    }
    GuardianAccountLayout {
        GuardianBrandHeader("VOID Update", "Secured by VOID Guardian")
        Spacer(Modifier.height(12.dp))
        Text(if (decision == "required") "Update required" else "Update available",
            style = MaterialTheme.typography.headlineLarge)
        Text("A new version of VOID Music is ready. Install it over your current app.")
        Text("Version ${release.versionName} · Build ${release.latest}", style = MaterialTheme.typography.titleMedium)
        Text("Save your music library first. A compatible update keeps local data; a replacement installation may require recovery.",
            style = MaterialTheme.typography.bodyMedium)
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (error.isNotEmpty()) GuardianAccountNotice(error)
        savedRevision?.let { Text("Cloud backup saved · Revision $it") }
        OutlinedButton(onClick = {
            run { preview = cloud.previewUpgradeBackup(account) }
        }, enabled = !busy && receipt == null,
            modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp),
            shape = RoundedCornerShape(18.dp)) {
            Text("Create backup & recovery code")
        }
        Text("Backs up supported favorites and playlists and retains existing cloud preferences. Downloaded audio, local files and unsupported metadata are not included.",
            style = MaterialTheme.typography.bodySmall)
        Button(onClick = { confirmInstall = true }, enabled = !busy && receipt == null,
            modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp),
            shape = RoundedCornerShape(18.dp)) {
            Text("Download & install update")
        }
        if (decision == "available") TextButton(onClick = onOptionalDismiss, enabled = !busy && receipt == null) {
            Text("Later")
        }
    }
    preview?.let { reviewed ->
        AlertDialog(onDismissRequest = { if (!busy) preview = null },
            title = { Text("Review your backup") },
            text = { Text("Save supported library metadata and replace your previous recovery code? Excluded entries: ${reviewed.snapshot.excludedEntries}. Keep the new code private; it can be used only once with the same signed-in account.") },
            confirmButton = { TextButton(onClick = {
                preview = null
                run { receipt = cloud.confirmUpgradeBackup(reviewed); copied = false }
            }, enabled = !busy) { Text("Save & generate code") } },
            dismissButton = { TextButton(onClick = { preview = null }, enabled = !busy) { Text("Cancel") } })
    }
    receipt?.let { value ->
        AlertDialog(onDismissRequest = {},
            properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false),
            title = { Text("Save your recovery code") },
            text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Your backup was saved. This code replaces your earlier recovery code. Store it privately, preferably in a password manager.")
                Text(value.recovery)
                OutlinedButton(onClick = { copied = GuardianSecretClipboard.copy(context, value.recovery) }) {
                    Text(if (copied) "Copied" else "Copy recovery code")
                }
                Text("Sign in with the same account to recover. The code cannot grant membership or owner privileges.")
            } },
            confirmButton = { TextButton(onClick = { savedRevision = value.revision; receipt = null; copied = false }) {
                Text("I saved it")
            } })
    }
    if (confirmInstall) {
        AlertDialog(onDismissRequest = { confirmInstall = false },
            title = { Text("Install verified update?") },
            text = { Text(if (savedRevision == null) "No new backup has been confirmed during this session. Back up first if you might need to migrate. Do not uninstall if Android rejects the update." else "Install without deleting the app. Android will ask you to approve the update.") },
            confirmButton = { TextButton(onClick = {
                confirmInstall = false
                run { if (!downloadAndInstall()) error = "Allow installation from VOID Music in Android settings, then retry." }
            }, enabled = !busy) { Text("Continue") } },
            dismissButton = { TextButton(onClick = { confirmInstall = false }) { Text("Cancel") } })
    }
}

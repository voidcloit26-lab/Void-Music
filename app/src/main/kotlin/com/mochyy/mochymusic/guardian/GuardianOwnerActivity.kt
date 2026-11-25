package com.mochyy.mochymusic.guardian

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.os.PersistableBundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.mochyy.mochymusic.ui.theme.MochyTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Isolated owner UI. The player, activation gate and local entitlement are not changed. */
class GuardianOwnerActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (Build.VERSION.SDK_INT >= 26) window.decorView.importantForAutofill =
            android.view.View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        setContent { MochyTheme { OwnerScreen() } }
    }

    @Composable
    private fun OwnerScreen() {
        val scope = rememberCoroutineScope()
        var email by remember { mutableStateOf("") }
        var password by remember { mutableStateOf("") }
        var token by remember { mutableStateOf("") }
        var busy by remember { mutableStateOf(false) }
        var message by remember { mutableStateOf("") }
        var code by remember { mutableStateOf("") }
        var uses by remember { mutableStateOf("1") }
        var ttl by remember { mutableIntStateOf(86400) }
        var menu by remember { mutableStateOf(false) }
        var invitations by remember { mutableStateOf(emptyList<JSONObject>()) }
        var devices by remember { mutableStateOf(emptyList<JSONObject>()) }
        var pending by remember { mutableStateOf<Pair<String,String>?>(null) }
        val durations = listOf(3600 to "1 hour", 86400 to "24 hours", 604800 to "7 days", 0 to "No expiry")

        fun clearSession() {
            token = ""; password = ""; code = ""; invitations = emptyList(); devices = emptyList()
        }
        suspend fun request(action: String, data: JSONObject = JSONObject()): JSONObject? {
            val result = GuardianOwnerClient.call(action, data, token)
            if (result.status == 200) return result.data
            message = when (result.status) {
                401 -> if (action == "login") "Incorrect email or password." else "Session expired. Sign in again."
                429 -> "Too many attempts. Try again shortly."
                400 -> "Please check your input."
                else -> "Guardian is temporarily unavailable. Try again."
            }
            if (result.status == 401 && action != "login") clearSession()
            return null
        }
        suspend fun refresh() {
            val data = request("list") ?: return
            val inv = data.getJSONArray("invitations")
            val dev = data.getJSONArray("devices")
            invitations = List(inv.length()) { inv.getJSONObject(it) }
            devices = List(dev.length()) { dev.getJSONObject(it) }
            if (data.optBoolean("truncated")) message = "Showing the first 500 records in each list."
        }
        fun runAction(block: suspend () -> Unit) {
            if (busy) return
            busy = true
            message = ""
            scope.launch {
                try { block() }
                catch (e: CancellationException) { throw e }
                catch (_: Exception) { message = "Unable to connect to Guardian. Try again." }
                finally { busy = false }
            }
        }
        Surface(modifier = Modifier.fillMaxSize()) {
            LazyColumn(
                modifier = Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding(),
                contentPadding = PaddingValues(20.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                item {
                    TextButton(onClick = { clearSession(); finish() }, enabled = !busy) { Text("Back") }
                    Text("VOID Guardian", style = MaterialTheme.typography.headlineMedium)
                    Text(if (token.isEmpty()) "Private owner access" else "Owner management", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (busy) item { LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
                if (message.isNotEmpty()) item { Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                if (token.isEmpty()) {
                    item {
                        OutlinedTextField(value = email, onValueChange = { email = it.take(128) },
                            label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), enabled = !busy)
                    }
                    item {
                        OutlinedTextField(value = password, onValueChange = { password = it.take(256) },
                            label = { Text("Guardian password") }, singleLine = true,
                            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), enabled = !busy)
                    }
                    item {
                        Button(modifier = Modifier.fillMaxWidth(), enabled = !busy && email.isNotBlank() && password.isNotEmpty(),
                            onClick = {
                                val data = JSONObject().put("email",email.trim()).put("password",password)
                                password = ""
                                runAction {
                                    val result = request("login",data) ?: return@runAction
                                    val next = result.getString("token")
                                    require(Regex("[A-Za-z0-9_-]{43}").matches(next))
                                    token = next
                                    refresh()
                                }
                            }) { Text("Sign in") }
                        Text("Use your separate Guardian password, not your Google password.", style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { runAction { refresh() } }, enabled = !busy) { Text("Refresh") }
                            OutlinedButton(onClick = { runAction { try { request("logout") } finally { clearSession() } } }, enabled = !busy) { Text("Sign out") }
                        }
                    }
                    item {
                        Card {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text("Generate invitation", style = MaterialTheme.typography.titleLarge)
                                OutlinedTextField(value=uses,onValueChange={uses=it.filter(Char::isDigit).take(4)},label={Text("Number of uses")},
                                    singleLine=true,modifier=Modifier.fillMaxWidth(),keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),enabled=!busy)
                                Box {
                                    OutlinedButton(onClick={menu=true},enabled=!busy) { Text("Expiry: "+durations.first{it.first==ttl}.second) }
                                    DropdownMenu(expanded=menu,onDismissRequest={menu=false}) {
                                        durations.forEach { (seconds,label) -> DropdownMenuItem(text={Text(label)},onClick={ttl=seconds;menu=false}) }
                                    }
                                }
                                Text("Activated devices receive lifetime access unless revoked.",style=MaterialTheme.typography.bodySmall)
                                Button(modifier=Modifier.fillMaxWidth(),enabled=!busy && (uses.toIntOrNull() ?: 0) in 1..1000,onClick={
                                    runAction {
                                        val result=request("generate",JSONObject().put("uses",uses.toInt()).put("ttl",ttl)) ?: return@runAction
                                        code=result.getString("code")
                                        refresh()
                                    }
                                }) { Text("Generate code") }
                            }
                        }
                    }
                    if (code.isNotEmpty()) item {
                        Card {
                            Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                Text("New invitation",style=MaterialTheme.typography.titleMedium)
                                Text(code)
                                Text("Copy now. The original code is not stored for later viewing.",style=MaterialTheme.typography.bodySmall)
                                OutlinedButton(onClick={
                                    val clip=ClipData.newPlainText("Guardian invitation",code)
                                    if (Build.VERSION.SDK_INT>=24) clip.description.extras=PersistableBundle().apply { putBoolean("android.content.extra.IS_SENSITIVE",true) }
                                    (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(clip)
                                    message="Invitation copied."
                                }) { Text("Copy code") }
                            }
                        }
                    }
                    item { Text("Available invitations",style=MaterialTheme.typography.titleLarge); if(invitations.isEmpty()) Text("No active invitations") }
                    items(invitations) { row ->
                        Card { Column(Modifier.padding(16.dp)) {
                            Text("${row.optInt("remaining")} uses remaining")
                            Text(if(row.isNull("expires_at")) "No expiry" else java.text.DateFormat.getDateTimeInstance().format(java.util.Date(row.getLong("expires_at")*1000)))
                            TextButton(enabled=!busy,onClick={pending="cancel" to row.getString("id")}) { Text("Cancel invitation") }
                        } }
                    }
                    item { Text("Activated devices",style=MaterialTheme.typography.titleLarge); if(devices.isEmpty()) Text("No activated devices") }
                    items(devices) { row ->
                        Card { Column(Modifier.padding(16.dp)) {
                            Text("Device "+row.getString("account_id"))
                            Text(if(row.isNull("revoked_at")) "Lifetime access" else "Revoked")
                            if(row.isNull("revoked_at")) TextButton(enabled=!busy,onClick={pending="revoke" to row.getString("account_id")}) { Text("Revoke access") }
                        } }
                    }
                }
            }
            pending?.let { action ->
                AlertDialog(onDismissRequest={pending=null},title={Text(if(action.first=="revoke") "Revoke device access?" else "Cancel invitation?")},
                    text={Text("This action cannot be undone.")},confirmButton={TextButton(onClick={
                        pending=null
                        runAction {
                            val result=request(action.first,JSONObject().put("id",action.second)) ?: return@runAction
                            message=if(result.optBoolean("ok")) "Action completed." else "Already unavailable."
                            refresh()
                        }
                    }) { Text("Confirm") }},dismissButton={TextButton(onClick={pending=null}) { Text("Back") }})
            }
        }
    }
}

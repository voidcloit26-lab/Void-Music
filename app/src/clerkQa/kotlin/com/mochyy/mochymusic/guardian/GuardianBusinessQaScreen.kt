package com.mochyy.mochymusic.guardian

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Privileged QA view; backend must independently check fresh MFA every request. */
@Composable
internal fun GuardianBusinessQaScreen(client: GuardianBusinessQaClient, back: () -> Unit) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var summary by remember { mutableStateOf<JSONObject?>(null) }
    var kind by remember { mutableStateOf("lifetime") }
    var count by remember { mutableStateOf("1") }
    var days by remember { mutableStateOf("30") }
    var ttl by remember { mutableStateOf("7") }
    var codes by remember { mutableStateOf<List<String>>(emptyList()) }
    var list by remember { mutableStateOf<org.json.JSONArray?>(null) }
    var account by remember { mutableStateOf("") }
    var member by remember { mutableStateOf<JSONObject?>(null) }
    var price by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf<String?>(null) }
    fun run(block: suspend () -> Unit) {
        if (busy) return
        busy = true
        error = ""
        scope.launch {
            try { block() }
            catch (e: CancellationException) { throw e }
            catch (e: GuardianAccountClient.RequestFailed) {
                error = if (e.status in listOf(401,403)) "Owner access requires a verified owner account and fresh MFA. Reauthenticate, then retry."
                    else "Guardian Business unavailable. Refresh before retrying."
                if (e.status in listOf(401,403)) { summary = null; codes = emptyList(); list = null; member = null }
            } catch (_: Exception) { error = "Unable to complete request. Check the connection and refresh." }
            finally { busy = false }
        }
    }
    LaunchedEffect(client) { run { summary = client.request("summary") } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("GUARDIAN BUSINESS", style = MaterialTheme.typography.headlineMedium)
        Text("Owner access · staging")
        TextButton(onClick = back, enabled = !busy) { Text("Back") }
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (error.isNotEmpty()) Text(error,color=MaterialTheme.colorScheme.error)
        OutlinedButton(onClick = { run { summary = client.request("summary") } },enabled=!busy) { Text("Refresh") }
        summary?.let { info ->
            Text("Accounts: ${info.optInt("accounts")}")
            Text("Active memberships: ${info.optJSONObject("membership_status")?.optInt("active") ?: 0}")
            Text("Annual reference price: USD " + "%.2f".format(java.util.Locale.US,info.optInt("annual_price_usd_cents")/100.0))
            Text("Create activation codes",style=MaterialTheme.typography.titleLarge)
            for (option in listOf("lifetime","annual","renewal","trial","complimentary")) {
                Row {
                    RadioButton(selected=kind==option,onClick={kind=option},enabled=!busy)
                    Text(option.replaceFirstChar { it.uppercase() },Modifier.padding(top=12.dp))
                }
            }
            OutlinedTextField(count,{count=it.filter(Char::isDigit).take(3)},label={Text("Number of codes (1–100)")},singleLine=true)
            if (kind in listOf("trial","complimentary")) OutlinedTextField(days,{days=it.filter(Char::isDigit).take(3)},label={Text("Membership duration in days")},singleLine=true)
            OutlinedTextField(ttl,{ttl=it.filter(Char::isDigit).take(2)},label={Text("Redemption deadline days (0 = no expiry)")},singleLine=true)
            Button(onClick={
                val data=JSONObject().put("kind",kind).put("count",count.toInt()).put("ttl",if(ttl.toInt()==0) JSONObject.NULL else ttl.toInt()*86400)
                if(kind in listOf("trial","complimentary")) data.put("days",days.toInt())
                run {
                    codes=emptyList()
                    val response=client.request("codes/create",data).getJSONArray("codes")
                    codes=List(response.length()){response.getString(it)}
                }
            },enabled=!busy && codes.isEmpty() && count.toIntOrNull() in 1..100 && ttl.toIntOrNull() in 0..30 &&
                (kind !in listOf("trial","complimentary") || days.toIntOrNull() in 1..365)) { Text("Generate codes") }
            OutlinedButton(onClick={run { list=client.request("codes/list").getJSONArray("codes") }},enabled=!busy) {Text("View activation history")}
            list?.let { rows ->
                for(i in 0 until rows.length()) {
                    val item=rows.getJSONObject(i)
                    Text(item.optString("kind")+" · "+when{
                        !item.isNull("redeemed_at")->"Redeemed"
                        !item.isNull("cancelled_at")->"Cancelled"
                        else->"Issued"
                    })
                    if(item.isNull("redeemed_at") && item.isNull("cancelled_at")) {
                        TextButton(onClick={confirmation="code:"+item.getString("id")},enabled=!busy){Text("Cancel unused code")}
                    }
                }
            }
            Text("Member management",style=MaterialTheme.typography.titleLarge)
            OutlinedTextField(account,{account=it.trim().take(32)},label={Text("VOID account ID")},singleLine=true)
            Button(onClick={run {member=null;member=client.request("member",JSONObject().put("account",account))}},enabled=!busy && Regex("[a-f0-9]{32}").matches(account)){Text("Find member")}
            member?.let { m ->
                Text(m.optString("account")+" · "+m.optString("status"))
                for(state in listOf("suspended","enabled","revoked")) {
                    OutlinedButton(onClick={confirmation="state:"+m.getString("account")+":"+state},enabled=!busy){Text(when(state){"suspended"->"Suspend";"enabled"->"Reinstate";else->"Revoke"})}
                }
            }
            Text("Reference price",style=MaterialTheme.typography.titleLarge)
            OutlinedTextField(price,{price=it.filter(Char::isDigit).take(7)},label={Text("USD cents")},singleLine=true)
            OutlinedButton(onClick={confirmation="price:"+price},enabled=!busy && price.toIntOrNull() in 1..1000000){Text("Change reference price")}
            Text("No in-app payments are enabled.")
        }
    }
    if(codes.isNotEmpty()) AlertDialog(onDismissRequest={},title={Text("Save activation codes")},
        text={Column(Modifier.verticalScroll(rememberScrollState())) { Text("Shown once. Share each code privately with its intended member.");codes.forEach{Text(it)} }},
        confirmButton={TextButton(onClick={codes=emptyList()}){Text("Done")}})
    confirmation?.let { action ->
        AlertDialog(onDismissRequest={confirmation=null},title={Text("Confirm owner action")},
            text={Text("This changes membership or activation state. Continue?")},
            confirmButton={TextButton(onClick={
                confirmation=null
                run {
                    val parts=action.split(':')
                    when(parts[0]){
                        "code"->{client.request("codes/cancel",JSONObject().put("code_id",parts[1]));list=client.request("codes/list").getJSONArray("codes")}
                        "state"->{client.request("state",JSONObject().put("account",parts[1]).put("state",parts[2]));member=client.request("member",JSONObject().put("account",parts[1]))}
                        "price"->{client.request("price",JSONObject().put("cents",parts[1].toInt()));summary=client.request("summary")}
                    }
                }
            }){Text("Confirm")}},
            dismissButton={TextButton(onClick={confirmation=null}){Text("Cancel")}})
    }
}

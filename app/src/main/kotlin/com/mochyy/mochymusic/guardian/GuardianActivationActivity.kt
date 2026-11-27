package com.mochyy.mochymusic.guardian

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import com.mochyy.mochymusic.MainActivity
import com.mochyy.mochymusic.R
import com.mochyy.mochymusic.ui.screens.update.VoidPolicies
import com.mochyy.mochymusic.ui.theme.MochyTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.Locale
import kotlin.math.sin

/** Private activation surface. Motion never substitutes for a verified signed entitlement. */
class GuardianActivationActivity : ComponentActivity() {
    private var opening = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (GuardianGate.v2Enforced) {
            startActivity(Intent(this, ClerkQaActivity::class.java).putExtra("VOID_GATE_ENTRY", true))
            finish()
            return
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (Build.VERSION.SDK_INT >= 26) window.decorView.importantForAutofill =
            android.view.View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        if (GuardianGate.isAllowed(this)) {
            openMusic()
            return
        }
        setContent { MochyTheme { ActivationScreen() } }
    }

    @Composable
    private fun ActivationScreen() {
        val client = remember { GuardianGate.client(this@GuardianActivationActivity) }
        val focus = LocalFocusManager.current
        var code by remember { mutableStateOf("") }
        var busy by remember { mutableStateOf(false) }
        var success by remember { mutableStateOf(false) }
        var status by remember { mutableStateOf(if (client == null) "Activation is unavailable. Contact the owner." else "") }
        var legal by remember { mutableStateOf(false) }
        var entered by remember { mutableStateOf(false) }
        val accent = Color(0xFFA98BFF)
        val normalized = code.trim().uppercase(Locale.ROOT)
        val validCode = Regex("VOID-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}").matches(normalized)
        LaunchedEffect(Unit) { entered = true }
        val entrance = animateFloatAsState(if (entered) 1f else 0f, tween(550, easing = FastOutSlowInEasing), label = "guardian entrance")
        val reveal = animateFloatAsState(if (success) 1f else 0f, tween(420), label = "guardian verified")
        val pulse = rememberInfiniteTransition(label = "guardian ambient")
        val phase = pulse.animateFloat(0f, 1f, infiniteRepeatable(tween(2800, easing = LinearEasing)), label = "guardian waveform")

        fun submit(redeem: Boolean) {
            if (busy || success || client == null || (redeem && !validCode)) return
            focus.clearFocus()
            val input = if (redeem) normalized else ""
            code = ""
            busy = true
            status = ""
            lifecycleScope.launch {
                try {
                    val result = if (redeem) client.redeem(input) else client.refresh()
                    if (result == GuardianClient.Outcome.Active && GuardianGate.isAllowed(this@GuardianActivationActivity)) {
                        success = true
                        delay(420)
                        // Recheck after the animation; never open on an unverified receipt.
                        if (GuardianGate.isAllowed(this@GuardianActivationActivity)) openMusic()
                        else { success = false; status = "Access could not be verified. Try again." }
                    } else {
                        status = when (result) {
                            GuardianClient.Outcome.Denied -> "This invitation is invalid or no longer available."
                            GuardianClient.Outcome.Revoked -> "This device has no active access. Contact the owner."
                            GuardianClient.Outcome.InvalidReceipt -> "Access could not be verified. Contact the owner."
                            GuardianClient.Outcome.ChallengePending -> "A previous verification is still pending. Wait up to two minutes, then retry or restore access. (G403)"
                            GuardianClient.Outcome.RateLimited -> "Too many requests. Try again in one minute. (G429)"
                            GuardianClient.Outcome.Unavailable -> "Guardian is temporarily unavailable. Try again shortly. (G503)"
                            GuardianClient.Outcome.Timeout -> "Guardian is taking longer to respond. Retry, or restore existing access if the invitation was already used. (GTIME)"
                            else -> "Unable to connect to Guardian. Check your connection and try again. (GNET)"
                        }
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (_: Exception) {
                    status = "Unable to verify access. Please try again."
                } finally { busy = false }
            }
        }

        Surface(modifier = Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxSize()) {
                // Draw-only animation: no per-frame layout changes, media, or network work.
                Canvas(Modifier.matchParentSize()) {
                    val t = phase.value
                    val radius = size.minDimension * (0.68f + 0.025f * sin(t * 6.283185f))
                    drawCircle(Brush.radialGradient(
                        colors = listOf(accent.copy(alpha = 0.12f), Color.Transparent),
                        center = Offset(size.width * 0.5f, size.height * 0.17f),
                        radius = radius.coerceAtLeast(1f)
                    ), radius = radius, center = Offset(size.width * 0.5f, size.height * 0.17f))
                }
                Column(
                    modifier = Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()
                        .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Column(
                        modifier = Modifier.widthIn(max = 460.dp).fillMaxWidth().graphicsLayer {
                            alpha = entrance.value
                            translationY = (1f - entrance.value) * 20.dp.toPx()
                        },
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(18.dp)
                    ) {
                        Row(Modifier.clip(CircleShape).background(accent.copy(alpha = 0.10f))
                            .border(1.dp, accent.copy(alpha = 0.22f), CircleShape).padding(horizontal = 14.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(painterResource(if (success) R.drawable.check else R.drawable.lock), null, tint = accent, modifier = Modifier.size(16.dp))
                            Text(if (success) "ACCESS VERIFIED" else "PRIVATE ACCESS", color = accent, style = MaterialTheme.typography.labelMedium)
                        }
                        Box(Modifier.size(124.dp), contentAlignment = Alignment.Center) {
                            Canvas(Modifier.matchParentSize()) {
                                val t = phase.value
                                val r = size.minDimension * 0.46f
                                drawCircle(accent.copy(alpha = 0.12f), radius = r, style = androidx.compose.ui.graphics.drawscope.Stroke(1.dp.toPx()))
                                drawCircle(accent.copy(alpha = 0.24f * (1f - t)), radius = r * (0.72f + t * 0.35f), style = androidx.compose.ui.graphics.drawscope.Stroke(1.dp.toPx()))
                            }
                            Box(Modifier.size(92.dp).clip(RoundedCornerShape(28.dp))
                                .background(Brush.linearGradient(listOf(Color(0xFF25212E), Color(0xFF111115))))
                                .border(1.dp, Color.White.copy(alpha = 0.12f), RoundedCornerShape(28.dp)),
                                contentAlignment = Alignment.Center) {
                                AnimatedContent(targetState = success, label = "guardian mark") { verified ->
                                    if (verified) Icon(painterResource(R.drawable.check), "Verified", tint = accent, modifier = Modifier.size(48.dp))
                                    else Image(painterResource(R.drawable.ic_launcher_mark), "VOID Music", Modifier.size(82.dp))
                                }
                            }
                        }
                        Canvas(Modifier.width(112.dp).height(24.dp)) {
                            val t = phase.value
                            val count = 15
                            val step = size.width / count
                            for (i in 0 until count) {
                                val wave = (sin(t * 6.283185f + i * 0.65f) + 1f) / 2f
                                val h = size.height * (0.17f + 0.65f * wave)
                                drawRoundRect(accent.copy(alpha = if (success) 0.9f else 0.46f), Offset(i * step + step * 0.28f, (size.height-h)/2f),
                                    Size(step * 0.44f, h), CornerRadius(step * 0.22f))
                            }
                        }
                        Text("VOID Music", style = MaterialTheme.typography.headlineLarge, textAlign = TextAlign.Center)
                        Text(if (success) "You're in." else "Your music. Your space.", style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
                        Text(if (success) "Opening your library…" else "Enter your private invitation to unlock this device.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
                        Card(shape = RoundedCornerShape(24.dp),
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF17171B)),
                            modifier = Modifier.fillMaxWidth().border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(24.dp))) {
                            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                                Text("Invitation code", style = MaterialTheme.typography.titleMedium)
                                OutlinedTextField(value = code, onValueChange = { code = it.take(64); status = "" },
                                    label = { Text("Enter or paste code") }, placeholder = { Text("VOID-…") },
                                    singleLine = true, enabled = !busy && !success && client != null,
                                    isError = status.isNotEmpty(),
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(16.dp),
                                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false, imeAction = ImeAction.Done),
                                    keyboardActions = KeyboardActions(onDone = { submit(true) }))
                                Button(onClick = { submit(true) }, enabled = validCode && !busy && !success && client != null,
                                    shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = Color(0xFF170D2D))) {
                                    AnimatedContent(targetState = if (success) "Access verified" else if (busy) "Connecting and verifying…" else "Unlock VOID Music", label = "guardian action") { label ->
                                        Text(label)
                                    }
                                }
                                if (busy && !success) LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = accent)
                                if (success) LinearProgressIndicator(progress = { reveal.value }, modifier = Modifier.fillMaxWidth(), color = accent)
                                if (status.isNotEmpty()) Text(status, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                                TextButton(onClick = { submit(false) }, enabled = !busy && !success && client != null, modifier = Modifier.fillMaxWidth()) {
                                    Text("Restore existing access")
                                }
                            }
                        }
                        Text("Lifetime activation · Offline listening\nRevocations are received when connected.", style = MaterialTheme.typography.bodySmall,
                            textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            TextButton(onClick = { legal = true }) { Text("Legal & Privacy") }
                            TextButton(onClick = { startActivity(Intent(this@GuardianActivationActivity, GuardianOwnerActivity::class.java)) }, enabled = !busy && !success) { Text("Owner access") }
                        }
                    }
                }
            }
        }
        if (legal) AlertDialog(onDismissRequest = { legal = false }, title = { Text("Legal & Privacy") },
            text = { Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) { Text(VoidPolicies.fullText()) } },
            confirmButton = { TextButton(onClick = { legal = false }) { Text("Close") } })
    }

    private fun openMusic() {
        if (opening || !GuardianGate.isAllowed(this)) return
        opening = true
        startActivity(Intent(this, MainActivity::class.java).apply {
            action = Intent.ACTION_MAIN
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        })
        finish()
    }
}

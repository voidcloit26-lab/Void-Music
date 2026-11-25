package com.mochyy.mochymusic.guardian

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.mochyy.mochymusic.MainActivity
import kotlinx.coroutines.launch

/** Separate activation surface; does not load the player, library, or media session. */
class GuardianActivationActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (GuardianGate.isAllowed(this)) {
            openMusic()
            return
        }

        fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(24), dp(52), dp(24), dp(32))
            setBackgroundColor(Color.rgb(15, 15, 20))
        }
        fun text(value: String, size: Float, color: Int = Color.WHITE) =
            TextView(this).apply {
                this.text = value
                textSize = size
                setTextColor(color)
                setPadding(0, 0, 0, dp(16))
            }.also { root.addView(it) }

        text("VOID MUSIC", 30f)
        text("GUARDIAN / PRIVATE ACCESS", 14f, 0xffc3b8ea.toInt())
        text("Enter your invitation code to activate this device. Once activated, offline listening remains available. An online access check is required to receive revocations.", 16f)
        val code = EditText(this).apply {
            hint = "VOID-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setSingleLine(true)
            setTextColor(Color.WHITE)
            setHintTextColor(0xffaaaab5.toInt())
            isSaveEnabled = false
            importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO
        }
        root.addView(code, LinearLayout.LayoutParams(-1, -2))
        val activate = Button(this).apply { text = "Activate device" }
        val restore = Button(this).apply { text = "Check existing activation" }
        root.addView(activate, LinearLayout.LayoutParams(-1, -2))
        root.addView(restore, LinearLayout.LayoutParams(-1, -2))
        val legal = Button(this).apply { text = "Legal & Privacy" }
        root.addView(legal, LinearLayout.LayoutParams(-1, -2))
        legal.setOnClickListener {
            android.app.AlertDialog.Builder(this)
                .setTitle("VOID Music · Legal & Privacy")
                .setMessage(com.mochyy.mochymusic.ui.screens.update.VoidPolicies.fullText())
                .setPositiveButton("Close", null)
                .show()
        }
        val status = text("", 15f)
        setContentView(ScrollView(this).apply {
            setBackgroundColor(Color.rgb(15, 15, 20))
            isFillViewport = true
            addView(root)
        })

        val client = GuardianGate.client(this)
        if (client == null) {
            status.text = "Activation is unavailable in this build. Contact the owner."
            activate.isEnabled = false
            restore.isEnabled = false
            return
        }
        fun submit(redeem: Boolean) {
            activate.isEnabled = false
            restore.isEnabled = false
            val input = if (redeem) code.text.toString() else ""
            code.text.clear()
            status.text = "Verifying device…"
            lifecycleScope.launch {
                val result = if (redeem) client.redeem(input) else client.refresh()
                if (result == GuardianClient.Outcome.Active && GuardianGate.isAllowed(this@GuardianActivationActivity)) {
                    openMusic()
                    return@launch
                }
                status.text = when (result) {
                    GuardianClient.Outcome.Denied -> "Invalid or unavailable invitation, or device proof rejected."
                    GuardianClient.Outcome.Revoked -> "This device has no active access. Contact the owner."
                    GuardianClient.Outcome.InvalidReceipt -> "Server receipt could not be verified. Contact the owner."
                    else -> "Activation service unavailable. Try again."
                }
                activate.isEnabled = true
                restore.isEnabled = true
            }
        }
        activate.setOnClickListener { submit(true) }
        restore.setOnClickListener { submit(false) }
    }

    private fun openMusic() {
        startActivity(Intent(this, MainActivity::class.java).apply {
            action = Intent.ACTION_MAIN
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        })
        finish()
    }
}

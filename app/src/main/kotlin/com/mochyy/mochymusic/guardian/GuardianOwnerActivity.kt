package com.mochyy.mochymusic.guardian

import android.graphics.Color
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import androidx.activity.ComponentActivity
import java.io.ByteArrayInputStream

/**
 * First-party administration only. No native JS bridge, external browsing,
 * credentials in app configuration or authorization decision on the client.
 */
class GuardianOwnerActivity : ComponentActivity() {
    private var panel: WebView? = null
    private val origin = "https://void-guardian-owner-staging.onrender.com"
    private val allowedPaths = setOf("/", "/login", "/logout", "/healthz")
    private fun allowed(uri: Uri): Boolean =
        uri.scheme == "https" && uri.host == "void-guardian-owner-staging.onrender.com" &&
            (uri.port == -1 || uri.port == 443) && uri.userInfo == null &&
            uri.path in allowedPaths && uri.query == null && uri.fragment == null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(15, 15, 20))
        }
        root.addView(Button(this).apply {
            text = "Close · Guardian"
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(-1, -2))
        val view = WebView(this).apply {
            setBackgroundColor(Color.rgb(15, 15, 20))
            isSaveEnabled = false
            importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            settings.javaScriptEnabled = false
            settings.domStorageEnabled = false
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
            CookieManager.getInstance().setAcceptThirdPartyCookies(this, false)
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                    !request.isForMainFrame || !allowed(request.url)

                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                    if (allowed(request.url)) return null
                    return WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden", emptyMap(), ByteArrayInputStream(ByteArray(0)))
                }

                override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                    handler.cancel()
                }
            }
        }
        panel = view
        root.addView(view, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        // Delete only the first-party owner cookie, not music-provider sessions.
        CookieManager.getInstance().setCookie(origin, "__Host-guardian=; Path=/; Secure; HttpOnly; Max-Age=0") {
            if (!isFinishing && panel === view) view.loadUrl("$origin/")
        }
    }

    override fun onDestroy() {
        panel?.let { view ->
            view.stopLoading()
            (view.parent as? android.view.ViewGroup)?.removeView(view)
            view.destroy()
        }
        panel = null
        CookieManager.getInstance().setCookie(origin, "__Host-guardian=; Path=/; Secure; HttpOnly; Max-Age=0")
        CookieManager.getInstance().flush()
        super.onDestroy()
    }
}

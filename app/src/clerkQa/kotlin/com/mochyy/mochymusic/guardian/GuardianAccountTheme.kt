package com.mochyy.mochymusic.guardian

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.mochyy.mochymusic.R

/** Same monochrome palette and typography supplied by MochyTheme to the player. */
@Composable
internal fun GuardianBrandHeader(title: String, subtitle: String) {
    val colors = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp),
        verticalAlignment = Alignment.CenterVertically) {
        val shape = RoundedCornerShape(22.dp)
        Box(Modifier.size(64.dp)
            .background(Brush.linearGradient(listOf(colors.primaryContainer, colors.surface)), shape)
            .border(1.dp, colors.onSurface.copy(alpha = 0.12f), shape),
            contentAlignment = Alignment.Center) {
            Icon(painterResource(R.drawable.ic_mochy_mark), contentDescription = null,
                modifier = Modifier.size(36.dp), tint = colors.onSurface)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Text(subtitle, style = MaterialTheme.typography.bodyMedium,
                color = colors.onSurface.copy(alpha = 0.62f))
        }
    }
}

@Composable
internal fun GuardianAccountLayout(content: @Composable ColumnScope.() -> Unit) {
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)
        .windowInsetsPadding(WindowInsets.safeDrawing).imePadding(), contentAlignment = Alignment.TopCenter) {
        Column(Modifier.widthIn(max = 480.dp).fillMaxWidth()
            .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp), content = content)
    }
}

@Composable
internal fun GuardianAccountNotice(message: String) {
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(18.dp)
    Text(message, modifier = Modifier.fillMaxWidth().background(colors.surfaceVariant, shape)
        .border(1.dp, colors.error.copy(alpha = 0.4f), shape).padding(16.dp),
        style = MaterialTheme.typography.bodyMedium, color = colors.onSurface)
}

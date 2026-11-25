package com.mochyy.mochymusic.ui.player

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.mochyy.mochymusic.R

/** Lightweight translucent shortcut; deliberately shares the existing Audio Lab route. */
@Composable
internal fun AudioLabShortcut(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(16.dp)
    Box(
        modifier = modifier
            .size(48.dp)
            .clip(shape)
            .background(Color.Black.copy(alpha = 0.18f))
            .background(Brush.verticalGradient(listOf(Color.White.copy(alpha = 0.22f), Color.White.copy(alpha = 0.07f))))
            .border(1.dp, Brush.verticalGradient(listOf(Color.White.copy(alpha = 0.36f), Color.White.copy(alpha = 0.12f))), shape)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            painter = painterResource(R.drawable.equalizer),
            contentDescription = "Open Audio Lab",
            tint = Color.White,
            modifier = Modifier.size(22.dp),
        )
    }
}

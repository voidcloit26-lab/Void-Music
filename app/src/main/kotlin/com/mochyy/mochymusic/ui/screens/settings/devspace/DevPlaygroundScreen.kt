// the developer playground page: what the repo did since this build, its issues, and the experimental settings

package com.mochyy.mochymusic.ui.screens.settings.devspace

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.mochyy.mochymusic.BuildConfig
import com.mochyy.mochymusic.R
import com.mochyy.mochymusic.ui.component.SubSettingsScaffold
import com.mochyy.mochymusic.ui.screens.settings.CategoryBubble

const val DevPlaygroundRoute = "developer_playground"

@Composable
fun DevPlaygroundScreen(navController: NavController) {

    SubSettingsScaffold(
        title = stringResource(R.string.dev_playground_title),
        backLabel = stringResource(R.string.dev_spaces_back_label),
        onBack = { navController.navigateUp() },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            CategoryBubble(
                title = stringResource(R.string.dev_experimental_settings_bubble),
                iconRes = R.drawable.biotech,
                onClick = { navController.navigate("experimental_settings") },
            )
        }
    }
}

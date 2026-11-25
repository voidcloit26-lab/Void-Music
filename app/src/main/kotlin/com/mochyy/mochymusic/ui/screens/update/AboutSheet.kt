// about app, upstream credits and license sheets pushed from the version sheet or the mochy page

package com.mochyy.mochymusic.ui.screens.update

import androidx.annotation.DrawableRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.layout
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import coil3.request.ImageRequest
import coil3.request.crossfade
import com.mochyy.mochymusic.BuildConfig
import com.mochyy.mochymusic.R
import com.mochyy.mochymusic.ui.component.PopupSheetState
import com.mochyy.mochymusic.ui.component.RemoteFocus
import com.mochyy.mochymusic.ui.component.pressBounce
import com.mochyy.mochymusic.ui.player.menu.MenuRowSurface
import com.mochyy.mochymusic.ui.screens.donate.showSupportSheet
import com.mochyy.mochymusic.ui.component.sheetHandleRoom

@Immutable
private data class LeadDevEntry(
    val name: String,
    val devSpaceIndex: Int,
    @DrawableRes val fallbackAvatar: Int,
)

@Immutable
private data class CreditEntry(
    val name: String,
    val subtitle: String,
)

@Immutable
private data class LicenseEntry(
    val tag: String,
    val title: String,
    val subtitle: String,
    val url: String,
)

private val LeadDevs =
    listOf(
        LeadDevEntry(
            name = "VOID",
            devSpaceIndex = 0,
            fallbackAvatar = R.drawable.ic_mochy_mark,
        ),
    )

private val BaseCredits =
    listOf(
        CreditEntry(
            name = "realidkroo",
            subtitle = "Original Mochy Music creator and upstream developer",
        ),
        CreditEntry(
            name = "realkeichi",
            subtitle = "Original Mochy Music contributor",
        ),
        CreditEntry(
            name = "vivizzz007",
            subtitle = "Vivimusic dev, The base of this app",
        ),
        CreditEntry(
            name = "Mostafa Alagamy",
            subtitle = "Metrolist dev, The base of vivmusic too",
        ),
    )

private val MoreCredits =
    listOf(
        CreditEntry(
            name = "maxrave-dev",
            subtitle = "SimpMusic · lyrics API provider",
        ),
        CreditEntry(
            name = "Rukamori",
            subtitle = "ArchiveTune · design & architecture inspiration",
        ),
        CreditEntry(
            name = "fast4x",
            subtitle = "RiMusic · YouTube Music InnerTube service wrapper",
        ),
        CreditEntry(
            name = "tranxuanthang",
            subtitle = "LRCLIB · synchronized LRC lyrics provider",
        ),
        CreditEntry(
            name = "monochrome-music",
            subtitle = "Monochrome Music · lossless FLAC streams",
        ),
        CreditEntry(
            name = "Jaakko Pasanen",
            subtitle = "AutoEq · headphone equalizer database",
        ),
        CreditEntry(
            name = "Ibra Al Tabian",
            subtitle = "LyricsPlus · open source lyrics server",
        ),
        CreditEntry(
            name = "Boidushya",
            subtitle = "Better Lyrics API · synced syllable lyrics",
        ),
    )

private val Licenses =
    listOf(
        LicenseEntry(
            tag = "GPL-3.0",
            title = "Mochy Music (original project) · GPL-3.0",
            subtitle = "Free and open-source software · license and corresponding source",
            url = "https://www.gnu.org/licenses/gpl-3.0.html",
        ),
        LicenseEntry(
            tag = "GPL-3.0",
            title = "ViviMusic · GNU General Public License v3.0",
            subtitle = "by vivizzz007 · base project this app was forked from",
            url = "https://www.gnu.org/licenses/gpl-3.0.html",
        ),
        LicenseEntry(
            tag = "GPL-3.0",
            title = "Metrolist · GNU General Public License v3.0",
            subtitle = "by Mostafa Alagamy · base framework",
            url = "https://www.gnu.org/licenses/gpl-3.0.html",
        ),
        LicenseEntry(
            tag = "GPL-3.0",
            title = "SimpMusic · GNU General Public License v3.0",
            subtitle = "by maxrave-dev · lyrics provider integration",
            url = "https://www.gnu.org/licenses/gpl-3.0.html",
        ),
        LicenseEntry(
            tag = "GPL-3.0",
            title = "ArchiveTune · GNU General Public License v3.0",
            subtitle = "by Rukamori · design and architectural inspiration",
            url = "https://www.gnu.org/licenses/gpl-3.0.html",
        ),
        LicenseEntry(
            tag = "GPL-3.0",
            title = "RiMusic · GNU General Public License v3.0",
            subtitle = "by fast4x · InnerTube API wrapper",
            url = "https://www.gnu.org/licenses/gpl-3.0.html",
        ),
        LicenseEntry(
            tag = "MIT",
            title = "LRCLIB · MIT License",
            subtitle = "by tranxuanthang · synchronized lyrics database",
            url = "https://opensource.org/license/mit",
        ),
        LicenseEntry(
            tag = "MIT",
            title = "AutoEq · MIT License",
            subtitle = "by Jaakko Pasanen · headphone correction profiles",
            url = "https://opensource.org/license/mit",
        ),
    )

fun PopupSheetState.showAboutSheet(onOpenDevSpace: (Int) -> Unit = {}) {
    val popup = this
    show(buttonBar = { SheetPrimaryButton(text = stringResource(R.string.done), onClick = popup::dismiss) }) {
        AboutSheetContent(popup = popup, onOpenDevSpace = onOpenDevSpace)
    }
}

fun PopupSheetState.showLegalNoticesSheet() {
    val popup = this
    show(buttonBar = { SheetPrimaryButton(text = stringResource(R.string.done), onClick = popup::dismiss) }) {
        LegalNoticesContent()
    }
}

@Composable
private fun ColumnScope.AboutSheetContent(
    popup: PopupSheetState,
    onOpenDevSpace: (Int) -> Unit,
) {
    val context = LocalContext.current
    val installed = shortVersion(BuildConfig.VERSION_NAME)
    val scrollState = rememberScrollState()
    val ringScrollRangePx = with(LocalDensity.current) { 180.dp.toPx() }

    // the page starts under the sheet's handle now, so the ring and the first row sit that much lower
    val room = sheetHandleRoom()
    Box(Modifier.fillMaxWidth()) {
        // zero-size layout places the spinning ring behind the top icon without pushing the column down
        VersionRing(
            text = "VOID MUSIC $installed",
            scrollProgress = { scrollState.value / ringScrollRangePx },
            modifier =
                Modifier
                    .align(Alignment.TopCenter)
                    .layout { measurable, constraints ->
                        val placeable =
                            measurable.measure(
                                constraints.copy(
                                    minWidth = 0,
                                    minHeight = 0,
                                    maxWidth = Constraints.Infinity,
                                    maxHeight = Constraints.Infinity,
                                ),
                            )
                        layout(0, 0) {
                            placeable.place(x = -placeable.width / 2, y = (room - 166.dp).roundToPx())
                        }
                    },
        )

        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(top = room)
                    .verticalScroll(scrollState),
        ) {
            Spacer(Modifier.height(18.dp))
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Box(
                    modifier =
                        Modifier
                            .size(76.dp)
                            .clip(RoundedCornerShape(22.dp))
                            .background(MenuRowSurface),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        painter = painterResource(R.drawable.ic_mochy_mark),
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(38.dp),
                    )
                }
                Spacer(Modifier.height(14.dp))
                Text(
                    text = "VOID MUSIC",
                    fontSize = 36.sp,
                    lineHeight = 38.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = (-1.4).sp,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "Version $installed · VOID Edition",
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = (-0.4).sp,
                    color = Color.White.copy(alpha = 0.9f),
                )
            }

            Spacer(Modifier.height(18.dp))
            Box(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(20.dp))
                        .background(MenuRowSurface)
                        .padding(horizontal = 18.dp, vertical = 16.dp),
            ) {
                Text(
                    text = "Your music. Your space. An independent music player maintained by VOID.",
                    fontSize = 15.sp,
                    lineHeight = 19.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = (-0.4).sp,
                )
            }

            Spacer(Modifier.height(18.dp))
            SectionHeader("Community & contact")
            Spacer(Modifier.height(8.dp))
            AboutPillRow(text = "Join MARS Community", onClick = { context.openUrl(com.mochyy.mochymusic.core.updater.DiscordUrl) })
            Spacer(Modifier.height(8.dp))
            AboutPillRow(text = "Contact VOID · Owner", onClick = { context.openUrl(com.mochyy.mochymusic.core.updater.OwnerDiscordUrl) })
            Spacer(Modifier.height(12.dp))
            AboutPillRow(
                text = "Legal & Policies",
                onClick = { popup.showLegalNoticesSheet() },
            )
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
private fun ColumnScope.LegalNoticesContent() {
    val context = LocalContext.current
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = sheetHandleRoom())
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("Legal & Policies", fontSize = 25.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold)
        Text("Last updated: 25 November 2026", fontSize = 12.sp)
        VoidPolicies.sections.forEach { (title, body) ->
            SectionHeader(title)
            Text(body, fontSize = 14.sp, lineHeight = 21.sp)
        }
        Text("VOID Music is a modified open-source project. Original copyrights remain with their respective authors.", fontSize = 13.sp)
        var noticesExpanded by remember { mutableStateOf(false) }
        AboutPillRow(text = if (noticesExpanded) "Hide copyright & licenses" else "View copyright & licenses", onClick = { noticesExpanded = !noticesExpanded })
        if (noticesExpanded) {
        SectionHeader("Copyright & attribution")
        Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(MenuRowSurface).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            (BaseCredits + MoreCredits).forEach { credit ->
                Text(credit.name + " — " + credit.subtitle, fontSize = 13.sp, lineHeight = 18.sp)
            }
        }
        SectionHeader("Software licenses")
        Licenses.forEach { entry ->
            AboutPillRow(text = entry.tag + " · " + entry.title.substringBefore(" · "), onClick = { context.openUrl(entry.url) })
            Text(entry.subtitle, fontSize = 12.sp)
        }
        Text("Recipients must receive corresponding source and build instructions as required by the applicable license. Original copyright and license notices remain in the source distribution.", fontSize = 13.sp)
        }
        AboutPillRow(text = "Contact VOID", onClick = { context.openUrl(com.mochyy.mochymusic.core.updater.OwnerDiscordUrl) })
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title,
        fontSize = 15.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = (-0.3).sp,
        color = Color.White.copy(alpha = 0.55f),
    )
}

@Composable
private fun AboutPillRow(
    text: String,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        contentAlignment = Alignment.CenterStart,
        modifier =
            Modifier
                .pressBounce(interaction, pressedScale = 0.97f)
                .fillMaxWidth()
                .height(52.dp)
                .clip(RoundedCornerShape(18.dp))
                .background(Color(0xFF252536))
                .clickable(interactionSource = interaction, indication = RemoteFocus, onClick = onClick)
                .padding(horizontal = 18.dp),
    ) {
        Text(
            text = text,
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = (-0.4).sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun AboutCardButton(
    text: String,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        contentAlignment = Alignment.CenterStart,
        modifier =
            Modifier
                .pressBounce(interaction, pressedScale = 0.97f)
                .fillMaxWidth()
                .height(54.dp)
                .clip(RoundedCornerShape(20.dp))
                .background(MenuRowSurface)
                .clickable(interactionSource = interaction, indication = RemoteFocus, onClick = onClick)
                .padding(horizontal = 18.dp),
    ) {
        Text(
            text = text,
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = (-0.4).sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun PersonRow(
    name: String,
    subtitle: String?,
    avatarUrl: String,
    showArrow: Boolean,
    onClick: () -> Unit,
    @DrawableRes fallbackRes: Int? = null,
) {
    val interaction = remember { MutableInteractionSource() }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier =
            Modifier
                .pressBounce(interaction, pressedScale = 0.98f)
                .fillMaxWidth()
                .clickable(interactionSource = interaction, indication = RemoteFocus, onClick = onClick)
                .padding(horizontal = 16.dp, vertical = 10.dp),
    ) {
        GithubAvatar(
            url = avatarUrl,
            size = 44.dp,
            fallbackRes = fallbackRes,
        )
        Spacer(Modifier.width(14.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = name,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.4).sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (subtitle != null) {
                Text(
                    text = subtitle,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                    letterSpacing = (-0.2).sp,
                    color = Color.White.copy(alpha = 0.65f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (showArrow) {
            Spacer(Modifier.width(10.dp))
            ArrowBadge()
        }
    }
}

@Composable
private fun LicenseCard(
    entry: LicenseEntry,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier =
            Modifier
                .pressBounce(interaction, pressedScale = 0.98f)
                .fillMaxWidth()
                .clip(RoundedCornerShape(22.dp))
                .background(MenuRowSurface)
                .clickable(interactionSource = interaction, indication = RemoteFocus, onClick = onClick)
                .padding(horizontal = 18.dp, vertical = 16.dp),
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = entry.tag,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = (-0.2).sp,
                color = Color.White.copy(alpha = 0.55f),
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = entry.title,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.4).sp,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = entry.subtitle,
                fontSize = 11.5.sp,
                fontWeight = FontWeight.Medium,
                letterSpacing = (-0.2).sp,
                color = Color.White.copy(alpha = 0.55f),
            )
        }
        Spacer(Modifier.width(12.dp))
        ArrowBadge()
    }
}

@Composable
private fun ArrowBadge() {
    Box(
        contentAlignment = Alignment.Center,
        modifier =
            Modifier
                .size(20.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.16f)),
    ) {
        Icon(
            painter = painterResource(R.drawable.arrow_forward),
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.85f),
            modifier = Modifier.size(12.dp),
        )
    }
}

@Composable
private fun GithubAvatar(
    url: String,
    size: Dp,
    modifier: Modifier = Modifier,
    @DrawableRes fallbackRes: Int? = null,
) {
    val context = LocalContext.current
    val request =
        remember(url) {
            ImageRequest
                .Builder(context)
                .data(url)
                .crossfade(true)
                .build()
        }
    val fallback = fallbackRes?.let { painterResource(it) }
    Box(
        modifier =
            modifier
                .size(size)
                .clip(CircleShape)
                .background(Color(0xFFD9D9D9)),
    ) {
        AsyncImage(
            model = request,
            contentDescription = null,
            placeholder = fallback,
            error = fallback,
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize(),
        )
    }
}

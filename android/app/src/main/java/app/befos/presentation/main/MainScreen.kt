package app.befos.presentation.main

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.presentation.discovery.DiscoveryScreen
import app.befos.presentation.matches.MatchListScreen
import app.befos.presentation.profile.ProfileScreen

private enum class Tab(val label: String, val icon: ImageVector) {
    Discover("Подбор", Icons.Filled.Favorite),
    Matches("Пары", Icons.AutoMirrored.Filled.Chat),
    Profile("Профиль", Icons.Filled.Person),
}

@Composable
fun MainScreen(
    onOpenChat: (String) -> Unit,
    onOpenProfile: (String) -> Unit,
    onEditProfile: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenTest: () -> Unit,
    onLoggedOut: () -> Unit,
) {
    // Saveable, not plain remember: NavHost disposes MAIN when the user opens a chat,
    // the editor or settings, and returning to Discovery after editing one's own
    // profile reads as "your place was lost".
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val tabs = Tab.entries

    Scaffold(
        bottomBar = {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .navigationBarsPadding()
                    .padding(horizontal = Spacing.huge, vertical = Spacing.md)
                    .clip(RoundedCornerShape(30.dp))
                    .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.96f))
                    .border(Elev.hairlineWidth, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(30.dp))
                    .height(64.dp),
                horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
            ) {
                tabs.forEachIndexed { index, t ->
                    TabItem(
                        tab = t,
                        selected = tab == index,
                        onClick = { tab = index },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        },
    ) { padding ->
        val contentModifier = Modifier.padding(padding)
        when (tab) {
            0 -> androidx.compose.foundation.layout.Box(contentModifier) {
                DiscoveryScreen(onOpenMatch = onOpenChat, onOpenProfile = onOpenProfile)
            }
            1 -> androidx.compose.foundation.layout.Box(contentModifier) {
                MatchListScreen(onOpenChat = onOpenChat, onGoDiscover = { tab = 0 })
            }
            else -> androidx.compose.foundation.layout.Box(contentModifier) {
                ProfileScreen(
                    onEdit = onEditProfile,
                    onSettings = onOpenSettings,
                    onTest = onOpenTest,
                    onLoggedOut = onLoggedOut,
                )
            }
        }
    }
}

@Composable
private fun TabItem(
    tab: Tab,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val iconTint by animateColorAsState(
        targetValue = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        animationSpec = tween(Motion.Fast),
        label = "tabIconTint",
    )
    val labelTint by animateColorAsState(
        targetValue = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        animationSpec = tween(Motion.Fast),
        label = "tabLabelTint",
    )
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(26.dp))
            .clickable(onClick = onClick)
            .semantics {
                contentDescription = tab.label
                this.selected = selected
            },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Box(
            modifier = Modifier
                .size(34.dp)
                .clip(CircleShape)
                .background(
                    if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else Color.Transparent,
                    CircleShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(tab.icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(21.dp))
        }
        Text(
            tab.label,
            style = MaterialTheme.typography.labelSmall,
            color = labelTint,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

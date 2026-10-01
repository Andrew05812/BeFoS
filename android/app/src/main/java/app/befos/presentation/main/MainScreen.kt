package app.befos.presentation.main

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import app.befos.presentation.discovery.DiscoveryScreen
import app.befos.presentation.matches.MatchListScreen
import app.befos.presentation.profile.ProfileScreen

private enum class Tab(val label: String, val icon: ImageVector) {
    Discover("Подбор", Icons.Filled.Favorite),
    Matches("Пары", Icons.Filled.Chat),
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
    var tab by remember { mutableIntStateOf(0) }
    val tabs = Tab.entries

    Scaffold(
        bottomBar = {
            NavigationBar {
                tabs.forEachIndexed { index, t ->
                    NavigationBarItem(
                        selected = tab == index,
                        onClick = { tab = index },
                        icon = { Icon(t.icon, contentDescription = t.label) },
                        label = { Text(t.label) },
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
                MatchListScreen(onOpenChat = onOpenChat)
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

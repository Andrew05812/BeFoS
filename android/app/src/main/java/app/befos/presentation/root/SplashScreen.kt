package app.befos.presentation.root

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.Coral
import app.befos.core.designsystem.Violet
import app.befos.core.di.beFosViewModel

@Composable
fun SplashScreen(
    onRoute: (RootDestination) -> Unit,
) {
    val vm: RootViewModel = beFosViewModel { RootViewModel(it.authRepository, it.profileRepository) }
    val destination by vm.destination.collectAsState()

    LaunchedEffect(destination) {
        if (destination != RootDestination.LOADING) onRoute(destination)
    }

    Box(
        modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(
                modifier = Modifier.size(88.dp).background(Coral, MaterialTheme.shapes.extraLarge),
                contentAlignment = Alignment.Center,
            ) {
                Text("B", color = Violet, fontSize = MaterialTheme.typography.displayMedium.fontSize, fontWeight = FontWeight.Black)
            }
            Text("BeFoS", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onBackground)
            Text(
                "Совместимость, которую можно объяснить",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

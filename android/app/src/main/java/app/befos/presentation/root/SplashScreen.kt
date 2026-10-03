package app.befos.presentation.root

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
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
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.Ember
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.Iris
import app.befos.core.designsystem.Motion
import app.befos.core.di.beFosViewModel
import kotlinx.coroutines.launch

@Composable
fun SplashScreen(
    onRoute: (RootDestination) -> Unit,
) {
    val vm: RootViewModel = beFosViewModel { RootViewModel(it.authRepository, it.profileRepository) }
    val destination by vm.destination.collectAsState()

    // Entrance animation: logo scales up + fades in, wordmark/tagline follow.
    val logo = remember { Animatable(0f) }
    val text = remember { Animatable(0f) }

    LaunchedEffect(Unit) {
        launch { logo.animateTo(1f, tween(durationMillis = Motion.Hero, easing = FastOutSlowInEasing)) }
        launch {
            text.animateTo(
                1f,
                tween(durationMillis = Motion.Reveal, delayMillis = Motion.Base, easing = FastOutSlowInEasing),
            )
        }
    }

    LaunchedEffect(destination, logo.isRunning, text.isRunning) {
        if (destination == RootDestination.LOADING) return@LaunchedEffect
        // Hold the entrance animation briefly so it never feels like a flash, then route.
        if (!logo.isRunning && !text.isRunning) {
            kotlinx.coroutines.delay(250)
            onRoute(destination)
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(MaterialTheme.colorScheme.background, MaterialTheme.colorScheme.surfaceVariant),
                ),
            ),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(96.dp)
                    .graphicsLayer {
                        val s = 0.7f + 0.3f * logo.value
                        scaleX = s
                        scaleY = s
                        alpha = logo.value
                    }
                    .background(
                        brush = Brush.linearGradient(listOf(Ember, Peach, Iris)),
                        shape = MaterialTheme.shapes.extraLarge,
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "B",
                    color = MaterialTheme.colorScheme.onPrimary,
                    fontSize = MaterialTheme.typography.displayMedium.fontSize,
                    fontWeight = FontWeight.Black,
                )
            }
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.alpha(text.value).graphicsLayer { translationY = (1f - text.value) * 24f },
            ) {
                Text(
                    "BeFoS",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground,
                )
                Text(
                    "Совместимость, которую можно объяснить",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

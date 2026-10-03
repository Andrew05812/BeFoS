package app.befos.core.designsystem

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The mutual-like moment, shared by every screen that can produce it so the event
 * reads the same wherever it happens: photo lands first, score reveals a beat later.
 */
@Composable
fun MatchMoment(
    name: String?,
    photoUrl: String?,
    compatibility: Int?,
    onOpenChat: () -> Unit,
    onDismiss: () -> Unit,
    secondaryLabel: String = "Продолжить просмотр",
) {
    val shell = remember { Animatable(0.86f) }
    val fade = remember { Animatable(0f) }
    val avatarPop = remember { Animatable(0.7f) }
    val reveal = remember { Animatable(0f) }
    val haptics = rememberHaptics()

    LaunchedEffect(Unit) {
        haptics.success()
        launch { shell.animateTo(1f, spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow)) }
        launch { fade.animateTo(1f, tween(Motion.Base)) }
        launch {
            delay(90)
            avatarPop.animateTo(1f, spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMedium))
        }
        launch {
            delay(220)
            reveal.animateTo(1f, tween(Motion.Base))
        }
    }

    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .graphicsLayer {
                    scaleX = shell.value
                    scaleY = shell.value
                    alpha = fade.value
                }
                .clip(MaterialTheme.shapes.extraLarge)
                .background(Brush.verticalGradient(listOf(MatchNightTop, MatchNightBottom)))
                .border(1.dp, Color.White.copy(alpha = 0.10f), MaterialTheme.shapes.extraLarge)
                .padding(Spacing.huge),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            Text(
                text = "ВЗАИМНЫЙ ЛАЙК",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.2.sp,
                color = Color.White.copy(alpha = 0.6f),
            )
            Avatar(
                url = photoUrl,
                modifier = Modifier.graphicsLayer {
                    scaleX = avatarPop.value
                    scaleY = avatarPop.value
                },
                size = 104.dp,
                contentDescription = name,
                initials = name,
            )
            Text(
                text = if (name != null) "Это взаимно — вы и $name" else "Это взаимно!",
                style = MaterialTheme.typography.headlineMedium,
                color = Color.White,
            )
            if (compatibility != null) {
                Column(
                    modifier = Modifier.graphicsLayer { alpha = reveal.value },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    CompatibilityScore(percent = compatibility, size = 132.dp, strokeWidth = 10.dp)
                    Text(
                        // The ring already carries the number; repeating «75%» here would
                        // only add noise. Say what the number means instead.
                        text = compatibilityVerdict(compatibility),
                        style = MaterialTheme.typography.headlineSmall,
                        color = Color.White.copy(alpha = 0.86f),
                        textAlign = TextAlign.Center,
                    )
                }
            }
            AppButton(
                // "Написать Дарья" is ungrammatical — the verb needs the dative case,
                // which we cannot decline for arbitrary names. The name is already in
                // the headline, so the action stays personal without the error.
                text = "Написать сообщение",
                onClick = onOpenChat,
                modifier = Modifier.fillMaxWidth(),
            )
            AppButton(
                text = secondaryLabel,
                onClick = onDismiss,
                variant = AppButtonVariant.Ghost,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

private val MatchNightTop = Color(0xFF241B2E)
private val MatchNightBottom = Color(0xFF171222)

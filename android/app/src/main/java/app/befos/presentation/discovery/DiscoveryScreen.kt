package app.befos.presentation.discovery

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import coil.compose.AsyncImage
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.Avatar
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorRed
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.CompatibilityScore
import app.befos.core.designsystem.SuccessGreen
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.DiscoveryCard
import app.befos.presentation.common.goalLabel
import kotlinx.coroutines.launch

/** Horizontal drag distance (px) past which a released card counts as like/pass. */
private const val SWIPE_THRESHOLD_PX = 280f

@Composable
fun DiscoveryScreen(onOpenMatch: (String) -> Unit, onOpenProfile: (String) -> Unit) {
    val vm: DiscoveryViewModel = beFosViewModel { DiscoveryViewModel(it.discoveryRepository) }
    val state by vm.uiState.collectAsState()

    state.match?.let { outcome ->
        outcome.matchId?.let { matchId ->
            MatchDialog(compatibility = outcome.compatibility, onOpen = {
                vm.dismissMatch()
                onOpenMatch(matchId)
            }, onDismiss = vm::dismissMatch)
        }
    }

    when {
        state.loading -> LoadingState()
        state.error != null && state.cards.isEmpty() -> ErrorState(
            message = state.error ?: "Ошибка",
            title = "Не удалось загрузить анкеты",
            onRetry = vm::load,
        )
        state.isEmpty || state.current == null -> EmptyState(
            title = "Пока никого нет",
            message = "Новые анкеты закончились. Загляните позже — или расширите параметры поиска в профиле.",
            actionLabel = "Обновить",
            onAction = vm::load,
        )
        else -> DiscoveryContent(state, vm, onOpenProfile)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DiscoveryContent(state: DiscoveryUiState, vm: DiscoveryViewModel, onOpenProfile: (String) -> Unit) {
    val card = state.current ?: return
    val scope = rememberCoroutineScope()
    val dragX = remember(card.userId) { Animatable(0f) }
    val density = LocalDensity.current
    // Distance past which a released card flies off screen (well beyond the swipe threshold).
    val flyDistance = with(density) { 1000.dp.toPx() }

    fun fling(right: Boolean) {
        scope.launch {
            dragX.animateTo(
                targetValue = if (right) flyDistance else -flyDistance,
                animationSpec = tween(durationMillis = 260, easing = FastOutSlowInEasing),
            )
            if (right) vm.like() else vm.pass()
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .graphicsLayer {
                    translationX = dragX.value
                    rotationZ = dragX.value / 22f
                    val p = (dragX.value / flyDistance).coerceIn(-1f, 1f)
                    scaleX = 1f - 0.06f * kotlin.math.abs(p)
                    scaleY = 1f - 0.06f * kotlin.math.abs(p)
                    alpha = 1f - 0.35f * kotlin.math.abs(p)
                }
                .pointerInput(card.userId) {
                    detectHorizontalDragGestures(
                        onDragEnd = {
                            when {
                                dragX.value > SWIPE_THRESHOLD_PX -> fling(right = true)
                                dragX.value < -SWIPE_THRESHOLD_PX -> fling(right = false)
                                else -> scope.launch {
                                    dragX.animateTo(0f, spring(dampingRatio = Spring.DampingRatioMediumBouncy))
                                }
                            }
                        },
                        onDragCancel = { scope.launch { dragX.animateTo(0f, spring()) } },
                    ) { change, amount ->
                        change.consume()
                        scope.launch { dragX.snapTo(dragX.value + amount) }
                    }
                },
        ) {
            ProfileCard(card, onOpenProfile = { onOpenProfile(card.userId) })
            SwipeOverlay(dragX = dragX.value, modifier = Modifier.matchParentSize())
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FloatingActionButton(
                onClick = { fling(right = false) },
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
                contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
            ) { Icon(Icons.Filled.Close, contentDescription = "Пропустить") }
            FloatingActionButton(
                onClick = { fling(right = true) },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
            ) { Icon(Icons.Filled.Favorite, contentDescription = "Нравится") }
        }
        if (state.error != null) {
            Text(state.error!!, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
    }
}

/** Directional LIKE / NOPE stamp that fades in as the card is dragged past its threshold. */
@Composable
private fun SwipeOverlay(dragX: Float, modifier: Modifier = Modifier) {
    val progress = (dragX / SWIPE_THRESHOLD_PX).coerceIn(-1.6f, 1.6f)
    val likeAlpha = progress.coerceIn(0f, 1f)
    val nopeAlpha = (-progress).coerceIn(0f, 1f)
    Box(modifier = modifier) {
        if (likeAlpha > 0.01f) {
            Stamp(
                text = "LIKE",
                color = SuccessGreen,
                alpha = likeAlpha,
                rotation = -14f,
                modifier = Modifier.align(Alignment.TopStart),
            )
        }
        if (nopeAlpha > 0.01f) {
            Stamp(
                text = "NOPE",
                color = ErrorRed,
                alpha = nopeAlpha,
                rotation = 14f,
                modifier = Modifier.align(Alignment.TopEnd),
            )
        }
    }
}

@Composable
private fun Stamp(
    text: String,
    color: Color,
    alpha: Float,
    rotation: Float,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .padding(28.dp)
            .graphicsLayer {
                this.alpha = alpha
                rotationZ = rotation
                val s = 0.8f + 0.2f * alpha
                scaleX = s
                scaleY = s
            }
            .border(width = 4.dp, color = color.copy(alpha = alpha), shape = RoundedCornerShape(12.dp))
            .padding(horizontal = 14.dp, vertical = 6.dp),
    ) {
        Text(
            text,
            color = color.copy(alpha = alpha),
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Black,
            letterSpacing = 2.sp,
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileCard(card: DiscoveryCard, onOpenProfile: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxSize().clickable { onOpenProfile() },
        shape = RoundedCornerShape(28.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Box(Modifier.fillMaxSize()) {
            if (!card.photoUrl.isNullOrBlank()) {
                AsyncImage(
                    model = card.photoUrl,
                    contentDescription = card.name,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop,
                )
            } else {
                Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceVariant))
            }

            Box(
                Modifier.fillMaxWidth().align(Alignment.TopEnd).padding(16.dp),
            ) {
                CompatibilityScore(percent = card.compatibility, size = 72.dp, strokeWidth = 6.dp)
            }

            Column(
                modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth()
                    .background(
                        brush = androidx.compose.ui.graphics.Brush.verticalGradient(
                            listOf(androidx.compose.ui.graphics.Color.Transparent, androidx.compose.ui.graphics.Color(0xCC000000)),
                        ),
                    )
                    .padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    "${card.name}, ${card.age}",
                    color = androidx.compose.ui.graphics.Color.White,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "${card.city} · ${goalLabel(card.datingGoal)}",
                    color = androidx.compose.ui.graphics.Color(0xDDFFFFFF),
                    style = MaterialTheme.typography.bodyMedium,
                )
                card.highlight?.let { reason ->
                    Text(
                        text = "Почему показан: $reason",
                        color = androidx.compose.ui.graphics.Color(0xEEFFFFFF),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                    )
                }
                if (card.sharedInterestsCount > 0) {
                    Text(
                        "${card.sharedInterestsCount} общих интересов",
                        color = scoreColor(card.compatibility),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                if (card.interests.isNotEmpty()) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        card.interests.take(5).forEach { name ->
                            InterestChip(
                                label = name,
                                contentColor = Color.White,
                                containerColor = Color(0x33FFFFFF),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MatchDialog(compatibility: Int?, onOpen: () -> Unit, onDismiss: () -> Unit) {
    val scale = remember { Animatable(0.82f) }
    val fade = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        launch { scale.animateTo(1f, spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow)) }
        launch { fade.animateTo(1f, tween(durationMillis = 260)) }
    }
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(28.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            modifier = Modifier
                .fillMaxWidth()
                .graphicsLayer {
                    scaleX = scale.value
                    scaleY = scale.value
                    alpha = fade.value
                },
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Text("Это взаимно!", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                if (compatibility != null) {
                    CompatibilityScore(percent = compatibility, size = 120.dp)
                    Text(
                        "Ваша совместимость $compatibility%",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                AppButton(text = "Открыть чат", onClick = onOpen, modifier = Modifier.fillMaxWidth())
                AppButton(
                    text = "Продолжить просмотр",
                    onClick = onDismiss,
                    secondary = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

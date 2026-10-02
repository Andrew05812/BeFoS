package app.befos.presentation.discovery

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.PersonOutline
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import coil.compose.AsyncImage
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.CompatibilityScore
import app.befos.core.designsystem.DiscoveryCardData
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorRed
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.OverlayIconButton
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.SuccessGreen
import app.befos.core.designsystem.glassSurface
import app.befos.core.designsystem.photoScrim
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.LikeOutcome
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
            MatchDialog(
                compatibility = outcome.compatibility,
                name = state.current?.name,
                photoUrl = state.current?.photoUrl,
                onOpen = {
                    vm.dismissMatch()
                    onOpenMatch(matchId)
                },
                onDismiss = vm::dismissMatch,
            )
        }
    }

    when {
        state.loading -> LoadingState(message = "Ищем подходящие анкеты")
        state.error != null && state.cards.isEmpty() -> ErrorState(
            message = state.error ?: "Ошибка",
            title = "Не удалось загрузить анкеты",
            onRetry = vm::load,
        )
        state.isEmpty || state.current == null -> EmptyState(
            title = "Пока никого нет",
            message = "Новые анкеты закончились. Загляните позже — или расширите параметры поиска в профиле.",
            overline = "Подбор",
            actionLabel = "Обновить",
            onAction = vm::load,
        )
        else -> DiscoveryContent(state, vm, onOpenProfile)
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun DiscoveryContent(state: DiscoveryUiState, vm: DiscoveryViewModel, onOpenProfile: (String) -> Unit) {
    val card = state.current ?: return
    val scope = rememberCoroutineScope()
    val haptics = LocalHapticFeedback.current
    val dragX = remember(card.userId) { Animatable(0f) }
    val density = LocalDensity.current
    val flyDistance = with(density) { 1000.dp.toPx() }

    fun fling(right: Boolean) {
        haptics.performHapticFeedback(HapticFeedbackType.LongPress)
        scope.launch {
            dragX.animateTo(
                targetValue = if (right) flyDistance else -flyDistance,
                animationSpec = tween(durationMillis = 260, easing = FastOutSlowInEasing),
            )
            if (right) vm.like() else vm.pass()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = Spacing.gutter, vertical = Spacing.md),
        verticalArrangement = Arrangement.spacedBy(Spacing.xl),
    ) {
        // Header: overline brand + queue position.
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "ПОДБОР",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = "${state.index + 1} / ${state.cards.size}",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

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
            // Depth: the next candidate waits behind, slightly smaller.
            state.cards.getOrNull(state.index + 1)?.let { next ->
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .padding(top = Spacing.lg)
                        .graphicsLayer { scaleX = 0.94f; scaleY = 0.94f; alpha = 0.55f },
                ) {
                    CardPhoto(
                        DiscoveryCardData(photoUrl = next.photoUrl, name = next.name),
                        onOpenProfile = null,
                    )
                }
            }
            CardPhoto(
                DiscoveryCardData(photoUrl = card.photoUrl, name = card.name),
                onOpenProfile = { onOpenProfile(card.userId) },
                content = { CardOverlay(card, onOpenProfile = { onOpenProfile(card.userId) }) },
            )
            SwipeOverlay(dragX = dragX.value, modifier = Modifier.matchParentSize())
        }

        // Action cluster: pass / like / open profile.
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.xxl, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ActionRing(onClick = { fling(right = false) }, label = "Пропустить") {
                Icon(Icons.Filled.Close, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface)
            }
            ActionRing(onClick = { fling(right = true) }, label = "Нравится", primary = true, big = true) {
                Icon(
                    Icons.Filled.Favorite,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(34.dp),
                )
            }
            ActionRing(onClick = { onOpenProfile(card.userId) }, label = "Подробнее") {
                Icon(Icons.Filled.PersonOutline, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface)
            }
        }
        Text(
            text = "Свайп вправо — нравится · нажмите карточку, чтобы увидеть профиль",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
        if (state.error != null) {
            Text(state.error!!, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
    }
}

/** Full-bleed photo card shell with branded fallback when the photo is missing. */
@Composable
private fun CardPhoto(
    card: DiscoveryCardData,
    onOpenProfile: (() -> Unit)?,
    content: @Composable () -> Unit = {},
) {
    val shape = MaterialTheme.shapes.extraLarge
    Box(
        modifier = Modifier
            .fillMaxSize()
            .clip(shape)
            .then(if (onOpenProfile != null) Modifier.clickable { onOpenProfile() } else Modifier),
    ) {
        var loadFailed by androidx.compose.runtime.remember(card.photoUrl) { androidx.compose.runtime.mutableStateOf(false) }
        if (!card.photoUrl.isNullOrBlank() && !loadFailed) {
            AsyncImage(
                model = card.photoUrl,
                contentDescription = card.name,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
                onError = { loadFailed = true },
            )
        } else {
            // Branded fallback instead of a gray box; initial sits above the info overlay.
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Brush.linearGradient(listOf(IrisTint, EmberTint, Peach))),
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(start = Spacing.lg, top = Spacing.lg, end = Spacing.lg, bottom = 168.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = card.name.trim().firstOrNull()?.uppercase().toString(),
                        style = MaterialTheme.typography.displayLarge,
                        color = Color.White.copy(alpha = 0.9f),
                    )
                }
            }
        }
        content()
        Box(
            Modifier
                .fillMaxSize()
                .border(Elev.hairlineWidth, Color.White.copy(alpha = 0.14f), shape),
        )
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun CardOverlay(card: DiscoveryCard, onOpenProfile: () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        // Compatibility ring on frosted glass, top-right.
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(Spacing.lg)
                .glassSurface(CircleShape),
        ) {
            CompatibilityScore(percent = card.compatibility, size = 66.dp, strokeWidth = 6.dp)
        }
        // Detail shortcut, top-left.
        OverlayIconButton(
            onClick = onOpenProfile,
            contentDescription = "Открыть профиль",
            modifier = Modifier.align(Alignment.TopStart).padding(Spacing.lg),
        ) {
            Icon(Icons.Filled.PersonOutline, contentDescription = null, tint = Color.White)
        }

        // Bottom editorial block over the scrim.
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .background(photoScrim())
                .padding(start = Spacing.xl, end = Spacing.xl, bottom = Spacing.xxl, top = Spacing.huge),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = card.name,
                    color = Color.White,
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                )
                Text(
                    text = ", ${card.age}",
                    color = Color.White.copy(alpha = 0.7f),
                    style = MaterialTheme.typography.displaySmall,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                Box(Modifier.size(7.dp).clip(CircleShape).background(SuccessGreen))
                Text(
                    text = "${card.city} · ${goalLabel(card.datingGoal)}",
                    color = Color.White.copy(alpha = 0.82f),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            card.highlight?.let { reason ->
                Row(
                    modifier = Modifier
                        .padding(top = Spacing.xs)
                        .glassSurface(RoundedCornerShape(14.dp))
                        .padding(horizontal = Spacing.md, vertical = Spacing.sm),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(scoreColor(card.compatibility)))
                    Text(
                        text = reason,
                        color = Color.White,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 2,
                    )
                }
            }
            if (card.interests.isNotEmpty()) {
                FlowRow(
                    modifier = Modifier.padding(top = Spacing.xs),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    card.interests.take(4).forEach { name ->
                        InterestChip(
                            label = name,
                            contentColor = Color.White,
                            containerColor = Color(0x3DFFFFFF),
                        )
                    }
                    if (card.sharedInterestsCount > card.interests.take(4).size) {
                        InterestChip(
                            label = "+${card.sharedInterestsCount}",
                            contentColor = Color.White.copy(alpha = 0.85f),
                            containerColor = Color(0x29FFFFFF),
                        )
                    }
                }
            }
        }
    }
}

/** Round action control with a thin ring; primary variant gets the ember fill. */
@Composable
private fun ActionRing(
    onClick: () -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    primary: Boolean = false,
    big: Boolean = false,
    content: @Composable () -> Unit,
) {
    val haptics = LocalHapticFeedback.current
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed) 0.92f else 1f,
        animationSpec = Motion.pressSpring(),
        label = "actionRingPress",
    )
    val size = if (big) 72.dp else 58.dp
    Box(
        modifier = modifier
            .size(size)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(CircleShape)
            .background(
                if (primary) EmberFill else MaterialTheme.colorScheme.surface,
                CircleShape,
            )
            .border(
                Elev.hairlineWidth,
                if (primary) Color.White.copy(alpha = 0.35f) else MaterialTheme.colorScheme.outlineVariant,
                CircleShape,
            )
            .clickable(interactionSource = interaction, indication = null) {
                haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                onClick()
            }
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        content()
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
                text = "НРАВИТСЯ",
                color = SuccessGreen,
                alpha = likeAlpha,
                rotation = -12f,
                modifier = Modifier.align(Alignment.TopStart),
            )
        }
        if (nopeAlpha > 0.01f) {
            Stamp(
                text = "НЕ СЕЙЧАС",
                color = ErrorRed,
                alpha = nopeAlpha,
                rotation = 12f,
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
            .padding(24.dp)
            .graphicsLayer {
                this.alpha = alpha
                rotationZ = rotation
                val s = 0.82f + 0.18f * alpha
                scaleX = s
                scaleY = s
            }
            .border(width = 2.5.dp, color = color.copy(alpha = alpha), shape = MaterialTheme.shapes.small)
            .background(color.copy(alpha = 0.10f * alpha), MaterialTheme.shapes.small)
            .padding(horizontal = Spacing.lg, vertical = Spacing.sm),
    ) {
        Text(
            text,
            color = color.copy(alpha = alpha),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Black,
            letterSpacing = 2.sp,
        )
    }
}

/** Mutual-like moment: minimal, scale-in, no confetti. */
@Composable
private fun MatchDialog(compatibility: Int?, name: String?, photoUrl: String?, onOpen: () -> Unit, onDismiss: () -> Unit) {
    val scale = remember { Animatable(0.86f) }
    val fade = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        launch { scale.animateTo(1f, spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow)) }
        launch { fade.animateTo(1f, tween(Motion.Base)) }
    }
    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .graphicsLayer {
                    scaleX = scale.value
                    scaleY = scale.value
                    alpha = fade.value
                }
                .clip(MaterialTheme.shapes.extraLarge)
                .background(Brush.verticalGradient(listOf(Color(0xFF241B2E), Color(0xFF171222))))
                .border(1.dp, Color.White.copy(alpha = 0.10f), MaterialTheme.shapes.extraLarge)
                .padding(Spacing.huge),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            Text(
                text = "ВЗАИМНЫЙ ЛАЙК",
                style = MaterialTheme.typography.labelSmall,
                color = Color.White.copy(alpha = 0.6f),
            )
            name?.let {
                Text("Это взаимно — вы и $it", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            } ?: Text("Это взаимно!", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            if (compatibility != null) {
                CompatibilityScore(percent = compatibility, size = 132.dp, strokeWidth = 10.dp)
                Text(
                    "Ваша совместимость $compatibility%",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color.White.copy(alpha = 0.72f),
                )
            }
            AppButton(
                text = if (name != null) "Написать $name" else "Открыть чат",
                onClick = onOpen,
                modifier = Modifier.fillMaxWidth(),
            )
            AppButton(
                text = "Продолжить просмотр",
                onClick = onDismiss,
                variant = AppButtonVariant.Ghost,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

private val EmberFill: Color get() = Color(0xFFF0544F)
private val EmberTint: Color get() = Color(0xFFF0544F)
private val IrisTint: Color get() = Color(0xFF6C4CF1)

package app.befos.presentation.discovery

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.FlowRowOverflow
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.DiscoveryCardData
import app.befos.core.designsystem.DiscoverySkeleton
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorRed
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.MatchMoment
import app.befos.core.designsystem.MonogramFallback
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.OverlayIconButton
import app.befos.core.designsystem.RemotePhoto
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.SuccessGreen
import app.befos.core.designsystem.glassSurface
import app.befos.core.designsystem.GlassScoreBadge
import app.befos.core.designsystem.tabularDigits
import app.befos.core.designsystem.photoScrim
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.LikeOutcome
import app.befos.presentation.common.goalLabel
import kotlinx.coroutines.launch

/** Fraction of the card width past which a released card counts as like/pass. */
private const val SWIPE_THRESHOLD_FRACTION = 0.28f

/** A short but fast flick commits too — that is how a real swipe feels. */
private const val FLICK_VELOCITY_DP_PER_S = 1400f

/** Drag beyond the commit point meets resistance instead of sliding freely. */
private const val DRAG_RESISTANCE = 0.35f

@Composable
fun DiscoveryScreen(onOpenMatch: (String) -> Unit, onOpenProfile: (String) -> Unit) {
    val vm: DiscoveryViewModel = beFosViewModel { DiscoveryViewModel(it.discoveryRepository) }
    val state by vm.uiState.collectAsState()

    state.match?.let { outcome ->
        outcome.matchId?.let { matchId ->
            MatchMoment(
                name = state.current?.name,
                photoUrl = state.current?.photoUrl,
                compatibility = outcome.compatibility,
                onOpenChat = {
                    vm.dismissMatch()
                    onOpenMatch(matchId)
                },
                onDismiss = vm::dismissMatch,
            )
        }
    }

    when {
        state.loading -> DiscoverySkeleton()
        state.error != null && state.cards.isEmpty() -> ErrorState(
            message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
            title = "Не удалось загрузить анкеты",
            onRetry = vm::load,
        )
        state.isEmpty || state.current == null -> EmptyState(
            title = "Анкеты закончились",
            // No search filters exist in this product, so the next step is the honest
            // one: the pool refreshes as people register, not by tweaking settings.
            message = "Мы показали всех, кто подходит вам сейчас. Новые анкеты появляются со временем — попробуйте обновить подбор позже.",
            overline = "Подбор",
            actionLabel = "Обновить подбор",
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
    val haptics = rememberHaptics()
    val dragX = remember(card.userId) { Animatable(0f) }
    val density = LocalDensity.current
    val flyDistance = with(density) { 1000.dp.toPx() }
    var cardWidthPx by remember { mutableFloatStateOf(0f) }
    // Threshold follows the card, not a hardcoded pixel count: on a 320dp screen the
    // old 280px value was nearly half the card, so a swipe felt like it never landed.
    val thresholdPx = (cardWidthPx * SWIPE_THRESHOLD_FRACTION)
        .coerceAtLeast(with(density) { 96.dp.toPx() })
    val flickVelocityPx = with(density) { FLICK_VELOCITY_DP_PER_S.dp.toPx() }

    fun fling(right: Boolean) {
        if (state.busy) return
        haptics.medium()
        scope.launch {
            dragX.animateTo(
                targetValue = if (right) flyDistance else -flyDistance,
                animationSpec = tween(Motion.Base, easing = FastOutSlowInEasing),
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
                style = MaterialTheme.typography.labelLarge.tabularDigits(),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .onSizeChanged { cardWidthPx = it.width.toFloat() }
                .graphicsLayer {
                    val progress = (dragX.value / thresholdPx).coerceIn(-1.6f, 1.6f)
                    translationX = dragX.value
                    // Tilt follows the commit point and tops out at 10°, so the card
                    // leans like paper instead of rotating further the harder you pull.
                    rotationZ = 10f * progress.coerceIn(-1f, 1f)
                    val lean = kotlin.math.abs(progress)
                    scaleX = 1f - 0.05f * lean
                    scaleY = 1f - 0.05f * lean
                    alpha = 1f - 0.22f * lean
                }
                .pointerInput(card.userId, thresholdPx) {
                    var crossed = false
                    // This Compose version hands onDragEnd no velocity, so track it from
                    // the drag events: a paused finger reports zero, which must not throw.
                    var lastMoveNanos = 0L
                    var velocityPxPerS = 0f
                    detectHorizontalDragGestures(
                        onDragEnd = {
                            val past = kotlin.math.abs(dragX.value) >= thresholdPx
                            val thrown = kotlin.math.abs(velocityPxPerS) >= flickVelocityPx &&
                                kotlin.math.abs(dragX.value) >= thresholdPx * 0.4f
                            when {
                                past || thrown -> fling(right = dragX.value > 0)
                                else -> scope.launch { dragX.animateTo(0f, Motion.enterSpring()) }
                            }
                            crossed = false
                        },
                        onDragCancel = {
                            crossed = false
                            velocityPxPerS = 0f
                            scope.launch { dragX.animateTo(0f, Motion.enterSpring()) }
                        },
                    ) { change, amount ->
                        change.consume()
                        val now = System.nanoTime()
                        val deltaSeconds = (now - lastMoveNanos) / 1_000_000_000f
                        velocityPxPerS = when {
                            deltaSeconds <= 0f || deltaSeconds > 0.05f -> 0f
                            else -> amount / deltaSeconds
                        }
                        lastMoveNanos = now
                        val raw = dragX.value + amount
                        // Rubber band past the commit point: the card slows down rather
                        // than sliding an endless distance with the finger.
                        val next = when {
                            raw > thresholdPx -> thresholdPx + (raw - thresholdPx) * DRAG_RESISTANCE
                            raw < -thresholdPx -> -thresholdPx + (raw + thresholdPx) * DRAG_RESISTANCE
                            else -> raw
                        }
                        scope.launch { dragX.snapTo(next) }
                        val nowCrossed = kotlin.math.abs(next) >= thresholdPx * 0.98f
                        if (nowCrossed != crossed) {
                            crossed = nowCrossed
                            if (nowCrossed) haptics.light()
                        }
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
            SwipeOverlay(dragX = dragX.value, thresholdPx = thresholdPx, modifier = Modifier.matchParentSize())
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
            InlineNotice(state.error!!)
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
        // Branded layer sits under the photo: it is both the loading state and the fallback.
        MonogramFallback(
            name = card.name,
            modifier = Modifier.fillMaxSize(),
            badgeSize = 96.dp,
            contentPadding = PaddingValues(start = Spacing.lg, top = Spacing.lg, end = Spacing.lg, bottom = 168.dp),
        )
        if (!card.photoUrl.isNullOrBlank() && !loadFailed) {
            RemotePhoto(
                url = card.photoUrl,
                contentDescription = card.name,
                modifier = Modifier.fillMaxSize(),
                onError = { loadFailed = true },
            )
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
    BoxWithConstraints(Modifier.fillMaxSize()) {
        // Four chips fit on a 392dp phone at normal text size but stack into four rows
        // on a 320dp one, and the bottom block then grows up into the score badge.
        // Large system text does the same to a wide screen, so both fold the list down
        // to one chip plus the counter — the counter is what tells the user there is
        // more, so it must never be the item that falls off the edge.
        val cramped = maxWidth < 300.dp || LocalDensity.current.fontScale > 1.2f
        val chipLimit = when {
            cramped -> 1
            maxWidth < 340.dp -> 3
            else -> 4
        }
        // Score reads as a claim, not a decoration: the number plus what it means.
        GlassScoreBadge(
            percent = card.compatibility,
            size = if (cramped) 48.dp else 62.dp,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(Spacing.lg),
        )
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
                .padding(
                    start = Spacing.xl,
                    end = Spacing.xl,
                    bottom = Spacing.xxl,
                    // The scrim needs less air on a short card: every dp here is a dp
                    // the editorial block climbs toward the score badge.
                    top = if (cramped) Spacing.xxl else Spacing.huge,
                ),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = card.name,
                    color = Color.White,
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                    // A long name must not push the age off the card.
                    modifier = Modifier.weight(1f, fill = false),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
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
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            // Hierarchy: person → compatibility → identity → interests → explanation.
            // The chips used to sit under the explanation sentence, which buried the
            // concrete shared ground under a summary of it.
            if (card.interests.isNotEmpty()) {
                val shown = card.interests.take(chipLimit)
                val hidden = card.interests.size - shown.size
                FlowRow(
                    modifier = Modifier.padding(top = Spacing.xs),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                    maxLines = 2,
                    overflow = FlowRowOverflow.Clip,
                ) {
                    shown.forEach { name ->
                        InterestChip(
                            label = name,
                            contentColor = Color.White,
                            containerColor = Color(0x3DFFFFFF),
                        )
                    }
                    if (hidden > 0) {
                        InterestChip(
                            label = "+$hidden",
                            contentColor = Color.White.copy(alpha = 0.85f),
                            containerColor = Color(0x29FFFFFF),
                        )
                    }
                }
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
                        // Without this the line is cut at the box edge, and a reason
                        // ending in a bare comma reads as a rendering bug.
                        overflow = TextOverflow.Ellipsis,
                    )
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
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .semantics {
                role = Role.Button
                contentDescription = label
            },
        contentAlignment = Alignment.Center,
    ) {
        content()
    }
}

/** Directional LIKE / NOPE stamp that fades in as the card is dragged past its threshold. */
@Composable
private fun SwipeOverlay(dragX: Float, thresholdPx: Float, modifier: Modifier = Modifier) {
    val progress = (dragX / thresholdPx).coerceIn(-1.6f, 1.6f)
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
                text = "ПРОПУСТИТЬ",
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

private val EmberFill: Color get() = Color(0xFFF0544F)

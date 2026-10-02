package app.befos.core.designsystem

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import kotlinx.coroutines.delay

/** Interpolates the brand score gradient for a 0..100 compatibility percent. */
fun scoreColor(percent: Int): Color {
    val p = percent.coerceIn(0, 100) / 100f
    return if (p < 0.5f) {
        lerp(ScoreLow, ScoreMid, p / 0.5f)
    } else {
        lerp(ScoreMid, ScoreHigh, (p - 0.5f) / 0.5f)
    }
}

private fun lerp(a: Color, b: Color, t: Float): Color {
    val f = t.coerceIn(0f, 1f)
    return Color(
        red = a.red + (b.red - a.red) * f,
        green = a.green + (b.green - a.green) * f,
        blue = a.blue + (b.blue - a.blue) * f,
        alpha = a.alpha + (b.alpha - a.alpha) * f,
    )
}

// ---------- Press feedback (shared motion recipe) ----------

@Composable
private fun pressModifier(interaction: MutableInteractionSource): Modifier {
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed) 0.97f else 1f,
        animationSpec = Motion.pressSpring(),
        label = "pressScale",
    )
    return Modifier.graphicsLayer { scaleX = scale; scaleY = scale }
}

// ---------- Avatar ----------

@Composable
fun Avatar(
    url: String?,
    modifier: Modifier = Modifier,
    size: Dp = 56.dp,
    contentDescription: String? = null,
    initials: String? = null,
) {
    if (url.isNullOrBlank()) {
        // Branded fallback: ember→iris gradient with a letter, never a gray box.
        Box(
            modifier = modifier
                .size(size)
                .clip(CircleShape)
                .background(Brush.linearGradient(listOf(Peach, Ember, Iris))),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = initials?.trim()?.firstOrNull()?.uppercase()?.toString() ?: "?",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color.White,
            )
        }
    } else {
        AsyncImage(
            model = url,
            contentDescription = contentDescription,
            modifier = modifier
                .size(size)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceVariant),
            contentScale = ContentScale.Crop,
        )
    }
}

// ---------- Compatibility ----------

/** Gradient compatibility ring with a count-up animation. */
@Composable
fun CompatibilityScore(
    percent: Int,
    modifier: Modifier = Modifier,
    size: Dp = 92.dp,
    strokeWidth: Dp = 8.dp,
    label: String = "$percent%",
) {
    val animated by animateFloatAsState(targetValue = percent.coerceIn(0, 100) / 100f, label = "ring")
    var shown by remember { mutableIntStateOf(0) }
    LaunchedEffect(percent) {
        val from = shown
        val steps = 20
        for (i in 1..steps) {
            val t = i / steps.toFloat()
            val eased = 1f - (1f - t) * (1f - t)
            shown = (from + (percent - from) * eased).toInt()
            delay(16)
        }
        shown = percent.coerceIn(0, 100)
    }
    val color = scoreColor(percent)
    val track = MaterialTheme.colorScheme.surfaceVariant
    Box(modifier = modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = strokeWidth.toPx()
            val diameter = this.size.minDimension - stroke
            val top = (this.size.minDimension - diameter) / 2f
            val arcSize = androidx.compose.ui.geometry.Size(diameter, diameter)
            val arcTop = androidx.compose.ui.geometry.Offset(top, top)
            drawArc(
                color = track,
                startAngle = -90f,
                sweepAngle = 360f,
                useCenter = false,
                topLeft = arcTop,
                size = arcSize,
                style = Stroke(width = stroke, cap = StrokeCap.Round),
            )
            // Soft glow behind the active arc for depth without heavy shadows.
            drawArc(
                brush = compatBrush(ScoreLow, color),
                startAngle = -90f,
                sweepAngle = 360f * animated,
                useCenter = false,
                topLeft = arcTop,
                size = arcSize,
                style = Stroke(width = stroke * 2.2f, cap = StrokeCap.Round),
                alpha = 0.10f,
            )
            drawArc(
                brush = compatBrush(ScoreLow, color),
                startAngle = -90f,
                sweepAngle = 360f * animated,
                useCenter = false,
                topLeft = arcTop,
                size = arcSize,
                style = Stroke(width = stroke, cap = StrokeCap.Round),
            )
        }
        Text(
            text = "$shown%",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = color,
        )
    }
}

/** Score pill for lists/cards: tinted dot + percent. */
@Composable
fun CompatibilityBadge(percent: Int, modifier: Modifier = Modifier, compact: Boolean = false) {
    val color = scoreColor(percent)
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.12f),
        border = BorderStroke(Elev.hairlineWidth, color.copy(alpha = 0.28f)),
        contentColor = color,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(color))
            Text(
                text = if (compact) "$percent%" else "Совместимость $percent%",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

// ---------- States ----------

@Composable
fun LoadingState(modifier: Modifier = Modifier, message: String? = null) {
    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            // Two-tone ember pulse: branded instead of a bare spinner.
            val pulse = remember { Animatable(0.35f) }
            LaunchedEffect(Unit) {
                while (true) {
                    pulse.animateTo(1f, tween(Motion.Slow))
                    pulse.animateTo(0.35f, tween(Motion.Slow))
                }
            }
            Box(contentAlignment = Alignment.Center) {
                Box(
                    Modifier
                        .size(64.dp)
                        .graphicsLayer { alpha = pulse.value * 0.35f }
                        .background(Brush.linearGradient(listOf(Peach, Ember)), CircleShape),
                )
                Box(
                    Modifier
                        .size(44.dp)
                        .graphicsLayer { alpha = 0.65f + pulse.value * 0.35f }
                        .background(MaterialTheme.colorScheme.surface, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(26.dp),
                        strokeWidth = 2.5.dp,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            if (message != null) {
                Text(
                    message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
fun MessagePane(
    text: String,
    modifier: Modifier = Modifier,
    title: String? = null,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
    overline: String? = null,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = Spacing.huge),
        ) {
            // Decorative brand orb: makes empty/error states intentional.
            Box(
                Modifier
                    .size(72.dp)
                    .background(
                        Brush.linearGradient(listOf(EmberSoft, IrisSoft)),
                        CircleShape,
                    )
                    .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    Modifier
                        .size(40.dp)
                        .background(Brush.linearGradient(listOf(Peach, Ember, Iris)), CircleShape),
                )
            }
            if (overline != null) {
                Text(
                    text = overline.uppercase(),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (title != null) {
                Text(
                    title,
                    style = MaterialTheme.typography.headlineMedium,
                    color = MaterialTheme.colorScheme.onBackground,
                    textAlign = TextAlign.Center,
                )
            }
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.Center,
            )
            if (actionLabel != null && onAction != null) {
                Box(Modifier.padding(top = Spacing.sm)) {
                    AppButton(text = actionLabel, onClick = onAction, modifier = Modifier.heightIn(min = 48.dp))
                }
            }
        }
    }
}

@Composable
fun ErrorState(
    message: String,
    modifier: Modifier = Modifier,
    title: String = "Что-то пошло не так",
    onRetry: (() -> Unit)? = null,
) {
    MessagePane(
        text = message,
        modifier = modifier,
        title = title,
        overline = "Ошибка",
        actionLabel = if (onRetry != null) "Повторить" else null,
        onAction = onRetry,
    )
}

@Composable
fun EmptyState(
    title: String,
    message: String,
    modifier: Modifier = Modifier,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
    overline: String? = null,
) {
    MessagePane(
        text = message,
        modifier = modifier,
        title = title,
        overline = overline,
        actionLabel = actionLabel,
        onAction = onAction,
    )
}

// ---------- Buttons & fields ----------

enum class AppButtonVariant { Filled, Tonal, Ghost }

/** Primary CTA: ember gradient, 14dp radius, spring press, loading state. */
@Composable
fun AppButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    secondary: Boolean = false,
    variant: AppButtonVariant = if (secondary) AppButtonVariant.Tonal else AppButtonVariant.Filled,
    leadingIcon: androidx.compose.ui.graphics.vector.ImageVector? = null,
    contentColorOverride: Color? = null,
) {
    val interaction = remember { MutableInteractionSource() }
    val contentAlpha = if (enabled && !loading) 1f else 0.45f
    Surface(
        modifier = modifier
            .then(pressModifier(interaction))
            .heightIn(min = 52.dp),
        shape = MaterialTheme.shapes.small,
        color = Color.Transparent,
        contentColor = contentColorOverride ?: when (variant) {
            AppButtonVariant.Filled -> Color.White
            AppButtonVariant.Tonal -> MaterialTheme.colorScheme.onSurface
            AppButtonVariant.Ghost -> MaterialTheme.colorScheme.primary
        },
    ) {
        val fill: Brush? = when (variant) {
            AppButtonVariant.Filled -> EmberGradient
            else -> null
        }
        val bg = when (variant) {
            AppButtonVariant.Tonal -> MaterialTheme.colorScheme.surfaceVariant
            AppButtonVariant.Ghost -> Color.Transparent
            AppButtonVariant.Filled -> Color.Transparent
        }
        Box(
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer { alpha = contentAlpha }
                .background(bg)
                .then(if (fill != null) Modifier.background(fill) else Modifier)
                .then(
                    if (variant == AppButtonVariant.Ghost) {
                        Modifier.border(
                            1.dp,
                            (contentColorOverride ?: MaterialTheme.colorScheme.primary).copy(alpha = 0.5f),
                            MaterialTheme.shapes.small,
                        )
                    } else {
                        Modifier
                    }
                )
                .clickable(
                    interactionSource = interaction,
                    indication = null,
                    enabled = enabled && !loading,
                    onClick = onClick,
                ),
            contentAlignment = Alignment.Center,
        ) {
            if (loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(22.dp),
                    strokeWidth = 2.5.dp,
                    color = when (variant) {
                        AppButtonVariant.Filled -> Color.White
                        else -> MaterialTheme.colorScheme.onSurface
                    },
                )
            } else if (leadingIcon != null) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    modifier = Modifier.padding(horizontal = Spacing.xxl, vertical = Spacing.md),
                ) {
                    Icon(
                        leadingIcon,
                        contentDescription = null,
                        modifier = Modifier.size(19.dp),
                        tint = androidx.compose.material3.LocalContentColor.current,
                    )
                    Text(
                        text,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            } else {
                Text(
                    text,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(horizontal = Spacing.xxl, vertical = Spacing.md),
                )
            }
        }
    }
}

/** Compact round icon button used on photo overlays. */
@Composable
fun OverlayIconButton(
    onClick: () -> Unit,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    containerColor: Color = Color.White.copy(alpha = 0.14f),
    contentColor: Color = Color.White,
    size: Dp = 44.dp,
    content: @Composable () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        modifier = modifier
            .then(pressModifier(interaction))
            .size(size)
            .clip(CircleShape)
            .background(containerColor)
            .border(1.dp, Color.White.copy(alpha = 0.25f), CircleShape)
            .clickable(interactionSource = interaction, indication = null, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        content()
    }
}

/** Filled tonal input with animated focus — the form primitive for the whole app. */
@Composable
fun AppTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    singleLine: Boolean = true,
    minLines: Int = 1,
    maxLines: Int = 1,
    isPassword: Boolean = false,
    error: String? = null,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
) {
    var focused by remember { mutableStateOf(false) }
    var revealed by remember { mutableStateOf(false) }
    val shape = MaterialTheme.shapes.small
    val borderColor = when {
        error != null -> MaterialTheme.colorScheme.error
        focused -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.outlineVariant
    }
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        Text(
            text = label.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = if (focused) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(start = Spacing.xs),
        )
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .border(
                    width = if (focused || error != null) 1.5.dp else Elev.hairlineWidth,
                    color = borderColor,
                    shape = shape,
                ),
            shape = shape,
            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
        ) {
            Row(
                modifier = Modifier.padding(horizontal = Spacing.lg, vertical = Spacing.md),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                androidx.compose.foundation.text.BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    singleLine = singleLine && maxLines == 1,
                    minLines = minLines,
                    maxLines = maxLines,
                    visualTransformation =
                        if (isPassword && !revealed) PasswordVisualTransformation() else VisualTransformation.None,
                    keyboardOptions =
                        if (isPassword) keyboardOptions.copy(keyboardType = KeyboardType.Password) else keyboardOptions,
                    textStyle = MaterialTheme.typography.bodyLarge.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                    ),
                    modifier = Modifier
                        .weight(1f)
                        .onFocusChanged { focused = it.isFocused },
                    decorationBox = { inner ->
                        Box(contentAlignment = Alignment.CenterStart) {
                            if (value.isEmpty() && placeholder != null) {
                                Text(placeholder, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f))
                            }
                            inner()
                        }
                    },
                )
                if (isPassword) {
                    IconButton(onClick = { revealed = !revealed }) {
                        Icon(
                            imageVector = if (revealed) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                            contentDescription = if (revealed) "Скрыть пароль" else "Показать пароль",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
        if (error != null) {
            Text(
                error,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(start = Spacing.xs),
            )
        }
    }
}

// ---------- Surfaces & structure ----------

/** Tonal panel: white surface + hairline border + soft shadow. */
@Composable
fun AppCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val shape = MaterialTheme.shapes.medium
    val interaction = remember { MutableInteractionSource() }
    Surface(
        modifier = modifier
            .then(if (onClick != null) Modifier.then(pressModifier(interaction)) else Modifier),
        shape = shape,
        color = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        tonalElevation = Elev.card,
        shadowElevation = Elev.card,
        border = BorderStroke(Elev.hairlineWidth, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Box(
            modifier = if (onClick != null) {
                Modifier.clickable(interactionSource = interaction, indication = null, onClick = onClick)
            } else {
                Modifier
            },
        ) {
            content()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppTopBar(
    title: String,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
) {
    TopAppBar(
        title = {
            Text(
                title,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
        },
        modifier = modifier,
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.background.copy(alpha = 0.92f),
        ),
        navigationIcon = {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                }
            }
        },
        actions = actions,
    )
}

@Composable
fun SectionHeader(title: String, modifier: Modifier = Modifier, subtitle: String? = null) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        Text(
            text = title.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (subtitle != null) {
            Text(
                subtitle,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onBackground,
            )
        }
    }
}

/** Pill chip: iris signature when selected, tonal when static. */
@Composable
fun InterestChip(
    label: String,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    onClick: (() -> Unit)? = null,
    containerColor: Color? = null,
    contentColor: Color? = null,
) {
    val shape = RoundedCornerShape(50)
    val bg = containerColor ?: when {
        selected -> MaterialTheme.colorScheme.secondaryContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    val fg = contentColor ?: when {
        selected -> MaterialTheme.colorScheme.onSecondaryContainer
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    val border = if (selected) BorderStroke(1.dp, MaterialTheme.colorScheme.secondary.copy(alpha = 0.45f)) else null
    val interaction = remember { MutableInteractionSource() }
    Surface(
        modifier = modifier.then(if (onClick != null) Modifier.then(pressModifier(interaction)) else Modifier),
        shape = shape,
        color = bg,
        contentColor = fg,
        border = border,
    ) {
        val inner = Modifier.padding(horizontal = Spacing.lg, vertical = Spacing.sm)
        if (onClick != null) {
            Row(
                modifier = inner.clickable(interactionSource = interaction, indication = null, onClick = onClick),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
            ) {
                AnimatedVisibility(visible = selected, enter = scaleIn(tween(Motion.Fast)) + fadeIn(tween(Motion.Fast)), exit = scaleOut(tween(Motion.Fast)) + fadeOut(tween(Motion.Fast))) {
                    Box(Modifier.size(14.dp).clip(CircleShape).background(MaterialTheme.colorScheme.secondary))
                }
                Text(label, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        } else {
            Text(
                label,
                style = MaterialTheme.typography.labelLarge,
                modifier = inner,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

// ---------- Composite cards ----------

@Composable
fun MessageBubble(
    body: String,
    isOwn: Boolean,
    footer: String,
    modifier: Modifier = Modifier,
) {
    val appear = remember { Animatable(0f) }
    LaunchedEffect(Unit) { appear.animateTo(1f, Motion.enterSpring()) }
    val ownBrush = EmberGradient
    Row(
        modifier = modifier
            .fillMaxWidth()
            .graphicsLayer {
                alpha = appear.value
                translationY = (1f - appear.value) * 14.dp.toPx()
                scaleX = 0.96f + 0.04f * appear.value
                scaleY = 0.96f + 0.04f * appear.value
            },
        horizontalArrangement = if (isOwn) Arrangement.End else Arrangement.Start,
    ) {
        val cornerShape = RoundedCornerShape(
            topStart = 20.dp,
            topEnd = 20.dp,
            bottomStart = if (isOwn) 20.dp else 6.dp,
            bottomEnd = if (isOwn) 6.dp else 20.dp,
        )
        Column(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .then(
                    if (isOwn) {
                        Modifier.background(ownBrush, cornerShape)
                    } else {
                        Modifier
                            .background(MaterialTheme.colorScheme.surface, cornerShape)
                            .border(Elev.hairlineWidth, MaterialTheme.colorScheme.outlineVariant, cornerShape)
                    }
                )
                .padding(horizontal = Spacing.lg, vertical = Spacing.md),
        ) {
            Text(
                body,
                color = if (isOwn) Color.White else MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                footer,
                style = MaterialTheme.typography.labelSmall,
                color = if (isOwn) Color.White.copy(alpha = 0.72f) else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.align(Alignment.End),
            )
        }
    }
}

@Composable
fun MatchCard(
    photoUrl: String?,
    name: String,
    subtitle: String,
    compatibility: Int,
    unread: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    AppCard(modifier = modifier.fillMaxWidth(), onClick = onClick) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Avatar(photoUrl, size = 56.dp, contentDescription = name, initials = name)
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (unread > 0) {
                        MaterialTheme.colorScheme.onBackground
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                    fontWeight = if (unread > 0) FontWeight.SemiBold else FontWeight.Normal,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                CompatibilityBadge(compatibility, compact = true)
                if (unread > 0) {
                    Box(
                        Modifier
                            .size(22.dp)
                            .background(EmberGradient, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("$unread", style = MaterialTheme.typography.labelSmall, color = Color.White, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
fun ProfileCard(
    name: String,
    age: Int,
    city: String,
    goal: String,
    compatibility: Int,
    modifier: Modifier = Modifier,
) {
    AppCard(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.xl),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                Text(
                    text = city.uppercase(),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text("$name, $age", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text(goal, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
            }
            CompatibilityScore(percent = compatibility, size = 92.dp, strokeWidth = 9.dp)
        }
    }
}

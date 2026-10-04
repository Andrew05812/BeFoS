package app.befos.core.designsystem

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AutoAwesome
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImagePainter
import coil.compose.rememberAsyncImagePainter
import kotlin.math.roundToInt
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

/**
 * The score in words — same bands the compatibility page uses, so «92%» always
 * reads as the same claim wherever it appears (card, badge, match moment, story).
 */
fun compatibilityVerdict(percent: Int): String = when (percent.coerceIn(0, 100)) {
    in 85..100 -> "Вы очень хорошо подходите"
    in 70..84 -> "Вы хорошо подходите"
    in 55..69 -> "Есть перспектива"
    in 40..54 -> "Стоит узнать друг друга"
    else -> "Вы довольно разные"
}

/** Short adjective for the same bands — for tight slots next to the ring. */
fun compatibilityLevel(percent: Int): String = when (percent.coerceIn(0, 100)) {
    in 85..100 -> "Очень высокая"
    in 70..84 -> "Высокая"
    in 55..69 -> "Хорошая"
    in 40..54 -> "Средняя"
    else -> "Низкая"
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

/**
 * The app's only remote-image primitive. It fades in over whatever sits behind it
 * (a gradient, a monogram), so a photo arriving never pops and a card swap never
 * flashes blank — the old AsyncImage cut straight from placeholder to image.
 * [onError] lets the caller fall back to its branded placeholder.
 */
@Composable
fun RemotePhoto(
    url: String?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    contentScale: ContentScale = ContentScale.Crop,
    onError: (() -> Unit)? = null,
) {
    val painter = rememberAsyncImagePainter(model = url)
    val state = painter.state
    val loaded = state is AsyncImagePainter.State.Success
    val alpha by animateFloatAsState(
        targetValue = if (loaded) 1f else 0f,
        animationSpec = tween(Motion.Base),
        label = "photoFade",
    )
    LaunchedEffect(state) {
        if (state is AsyncImagePainter.State.Error) onError?.invoke()
    }
    Image(
        painter = painter,
        contentDescription = contentDescription,
        modifier = modifier.graphicsLayer { this.alpha = alpha },
        contentScale = contentScale,
    )
}

@Composable
fun Avatar(
    url: String?,
    modifier: Modifier = Modifier,
    size: Dp = 56.dp,
    contentDescription: String? = null,
    initials: String? = null,
) {
    var failed by remember(url) { mutableStateOf(false) }
    if (url.isNullOrBlank() || failed) {
        // Branded fallback: ember→iris gradient with a letter, never a gray box.
        Box(
            modifier = modifier
                .size(size)
                .clip(CircleShape)
                .background(Brush.linearGradient(listOf(Peach, Ember, Iris))),
            contentAlignment = Alignment.Center,
        ) {
            MonogramLetter(
                initials = initials,
                color = Color.White,
                textSize = if (size <= 44.dp) MaterialTheme.typography.titleSmall else MaterialTheme.typography.titleMedium,
                iconSize = size / 2.6f,
            )
        }
    } else {
        RemotePhoto(
            url = url,
            contentDescription = contentDescription,
            onError = { failed = true },
            modifier = modifier
                .size(size)
                .clip(CircleShape)
                .background(Brush.linearGradient(listOf(Peach, Ember, Iris))),
        )
    }
}

/** Initial letter, or the brand spark when there is no name to take a letter from. */
@Composable
private fun MonogramLetter(
    initials: String?,
    color: Color,
    textSize: TextStyle,
    iconSize: Dp,
) {
    val letter = initials?.trim()?.firstOrNull()?.uppercase()?.toString()
    if (letter.isNullOrEmpty()) {
        Icon(
            imageVector = Icons.Filled.AutoAwesome,
            contentDescription = null,
            tint = color,
            modifier = Modifier.size(iconSize),
        )
    } else {
        Text(
            text = letter,
            style = textSize,
            fontWeight = FontWeight.Bold,
            color = color,
        )
    }
}

/**
 * Full-bleed placeholder for a missing or broken photo: duotone field with one
 * restrained frosted monogram badge, so an empty card still looks composed.
 */
@Composable
fun MonogramFallback(
    name: String?,
    modifier: Modifier = Modifier,
    badgeSize: Dp = 88.dp,
    contentPadding: PaddingValues = PaddingValues(0.dp),
) {
    Box(
        modifier = modifier
            .background(Brush.linearGradient(listOf(Iris, Ember, Peach))),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .padding(contentPadding)
                .size(badgeSize)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.16f))
                .border(Elev.hairlineWidth * 2f, Color.White.copy(alpha = 0.32f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            MonogramLetter(
                initials = name,
                color = Color.White.copy(alpha = 0.92f),
                textSize = MaterialTheme.typography.headlineMedium,
                iconSize = badgeSize / 2.4f,
            )
        }
    }
}

// ---------- Compatibility ----------

/**
 * Gradient compatibility ring with a count-up animation.
 *
 * One Animatable drives both the arc and the number, on a single Motion.Slow tween:
 * the ring and the digits always land together, on any frame rate, and the value is
 * settled before the next card can take focus.
 */
@Composable
fun CompatibilityScore(
    percent: Int,
    modifier: Modifier = Modifier,
    size: Dp = 92.dp,
    strokeWidth: Dp = 8.dp,
    onDark: Boolean = false,
) {
    val target = percent.coerceIn(0, 100) / 100f
    val sweep = remember { Animatable(0f) }
    LaunchedEffect(percent) {
        sweep.animateTo(target, tween(Motion.Slow, easing = FastOutSlowInEasing))
    }
    val animated = sweep.value
    val shown = (sweep.value * 100).roundToInt()
    // High scores are iris-purple, which disappears on a photo or the night scrim,
    // so on imagery the whole ring lifts toward white and the digits turn pure white.
    val color = if (onDark) lerp(scoreColor(percent), Color.White, 0.45f) else scoreColor(percent)
    val track = if (onDark) Color.White.copy(alpha = 0.26f) else MaterialTheme.colorScheme.surfaceVariant
    Box(
        modifier = modifier
            .size(size)
            // TalkBack would otherwise read the bare digits mid-animation ("37%… 61%…").
            .clearAndSetSemantics { contentDescription = "Совместимость $percent процентов" },
        contentAlignment = Alignment.Center,
    ) {
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
            style = MaterialTheme.typography.titleLarge.tabularDigits(),
            fontWeight = FontWeight.Bold,
            color = if (onDark) Color.White else color,
        )
    }
}

/**
 * Frosted score badge for imagery: the ring plus the verdict it claims, on one glass
 * surface. Shared by the Discovery card and the public profile hero so both read alike.
 */
@Composable
fun GlassScoreBadge(percent: Int, modifier: Modifier = Modifier, size: Dp = 62.dp) {
    Column(
        modifier = modifier
            .glassSurface(RoundedCornerShape(20.dp))
            .padding(Spacing.md),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.xs),
    ) {
        CompatibilityScore(percent = percent, size = size, strokeWidth = 6.dp, onDark = true)
        Text(
            text = "${compatibilityLevel(percent)} совместимость",
            style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.86f),
            textAlign = TextAlign.Center,
            lineHeight = 14.sp,
            maxLines = 2,
            // No width cap: a fixed 124dp fitted the phrase at default text size and
            // cut the last letters off at 1.3. The badge is TopEnd-anchored, so letting
            // it grow is what keeps the words whole.
            overflow = TextOverflow.Ellipsis,
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
                style = MaterialTheme.typography.labelLarge.tabularDigits(),
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

// ---------- Skeletons ----------

/** Soft pulsing placeholder block; alpha breathes between 0.45 and 0.9. */
@Composable
fun SkeletonBlock(
    modifier: Modifier = Modifier,
    shape: androidx.compose.ui.graphics.Shape = MaterialTheme.shapes.medium,
) {
    val pulse = remember { Animatable(0.45f) }
    LaunchedEffect(Unit) {
        while (true) {
            pulse.animateTo(0.9f, tween(Motion.Slow))
            pulse.animateTo(0.45f, tween(Motion.Slow))
        }
    }
    // surfaceVariant (#F4EDE7) on the cream background is a 6/255 delta — effectively
    // invisible. Tinting onSurfaceVariant gives a readable warm-grey block in both themes.
    val tone = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.18f)
    Box(
        modifier = modifier
            .graphicsLayer { alpha = pulse.value }
            .clip(shape)
            .background(tone),
    )
}

/** Loading composition mirroring the discovery card layout. */
@Composable
fun DiscoverySkeleton(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = Spacing.gutter, vertical = Spacing.md),
        verticalArrangement = Arrangement.spacedBy(Spacing.xl),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            SkeletonBlock(Modifier.width(64.dp).height(12.dp))
            SkeletonBlock(Modifier.width(44.dp).height(12.dp))
        }
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .weight(1f),
            shape = MaterialTheme.shapes.extraLarge,
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.xxl, Alignment.CenterHorizontally),
        ) {
            SkeletonBlock(Modifier.size(56.dp), shape = CircleShape)
            SkeletonBlock(Modifier.size(72.dp), shape = CircleShape)
            SkeletonBlock(Modifier.size(56.dp), shape = CircleShape)
        }
        SkeletonBlock(
            Modifier
                .fillMaxWidth(0.7f)
                .height(12.dp)
                .align(Alignment.CenterHorizontally),
        )
    }
}

/** Loading composition mirroring a row list (matches, recommendations, chat history). */
@Composable
fun ListSkeleton(modifier: Modifier = Modifier, rows: Int = 5) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        repeat(rows) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
            ) {
                SkeletonBlock(Modifier.size(56.dp), shape = CircleShape)
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    SkeletonBlock(Modifier.fillMaxWidth(0.55f).height(14.dp))
                    SkeletonBlock(Modifier.fillMaxWidth(0.8f).height(12.dp))
                }
            }
        }
    }
}

/** Loading composition mirroring the profile content page. */
@Composable
fun ProfileSkeleton(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .height(168.dp),
            shape = MaterialTheme.shapes.large,
        )
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .height(148.dp),
            shape = MaterialTheme.shapes.large,
        )
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .height(96.dp),
            shape = MaterialTheme.shapes.large,
        )
    }
}

/** Loading composition mirroring the public profile: tall hero, then the category card. */
@Composable
fun PublicProfileSkeleton(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
        verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
    ) {
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = Spacing.gutter)
                .aspectRatio(0.82f),
            shape = MaterialTheme.shapes.extraLarge,
        )
        Column(
            modifier = Modifier.padding(horizontal = Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            SkeletonBlock(Modifier.width(196.dp).height(12.dp))
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(236.dp)
                    .clip(MaterialTheme.shapes.large)
                    .background(MaterialTheme.colorScheme.surface)
                    .padding(Spacing.lg),
                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
            ) {
                repeat(3) {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                        SkeletonBlock(Modifier.fillMaxWidth(0.5f).height(12.dp))
                        SkeletonBlock(Modifier.fillMaxWidth().height(10.dp), shape = CircleShape)
                    }
                }
            }
        }
    }
}

/** Loading composition mirroring the one-question test screen. */
@Composable
fun TestSkeleton(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.xl),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            SkeletonBlock(Modifier.width(72.dp).height(20.dp))
            SkeletonBlock(Modifier.width(36.dp).height(14.dp))
        }
        SkeletonBlock(Modifier.fillMaxWidth().height(6.dp), shape = CircleShape)
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            SkeletonBlock(Modifier.fillMaxWidth(0.9f).height(18.dp))
            SkeletonBlock(Modifier.fillMaxWidth(0.65f).height(18.dp))
        }
        repeat(4) {
            SkeletonBlock(
                Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                shape = MaterialTheme.shapes.medium,
            )
        }
    }
}

/** Loading composition mirroring the compatibility story page. */
@Composable
fun CompatibilitySkeleton(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(MaterialTheme.shapes.large)
                .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f))
                .padding(vertical = Spacing.huge),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            SkeletonBlock(Modifier.width(80.dp).height(12.dp))
            SkeletonBlock(Modifier.size(160.dp), shape = CircleShape)
            SkeletonBlock(Modifier.width(180.dp).height(20.dp))
        }
        SkeletonBlock(Modifier.fillMaxWidth(0.4f).height(12.dp))
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .height(200.dp),
            shape = MaterialTheme.shapes.large,
        )
        SkeletonBlock(Modifier.fillMaxWidth(0.4f).height(12.dp))
        SkeletonBlock(
            Modifier
                .fillMaxWidth()
                .height(140.dp),
            shape = MaterialTheme.shapes.large,
        )
    }
}

/** Compact inline banner: error tone for failures, neutral for confirmations. */
@Composable
fun InlineNotice(
    text: String,
    modifier: Modifier = Modifier,
    isError: Boolean = true,
) {
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        textAlign = TextAlign.Center,
        color = if (isError) MaterialTheme.colorScheme.onErrorContainer
        else MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(
                if (isError) MaterialTheme.colorScheme.errorContainer
                else MaterialTheme.colorScheme.surfaceVariant,
            )
            .padding(horizontal = Spacing.md, vertical = Spacing.sm),
    )
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
            // Custom-drawn control: TalkBack must still announce it as a button
            // and read «загружается» instead of silently accepting a tap.
            .semantics {
                role = Role.Button
                when {
                    loading -> stateDescription = "Загружается"
                    !enabled -> stateDescription = "Недоступно"
                }
            }
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
                .fillMaxWidth()
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
    size: Dp = 48.dp,
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
            .semantics { role = Role.Button }
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
    visualTransformation: VisualTransformation = VisualTransformation.None,
    onImeAction: (() -> Unit)? = null,
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
                        if (isPassword && !revealed) PasswordVisualTransformation() else visualTransformation,
                    keyboardOptions =
                        if (isPassword) keyboardOptions.copy(keyboardType = KeyboardType.Password) else keyboardOptions,
                    keyboardActions =
                        if (onImeAction != null) KeyboardActions(onDone = { onImeAction() }) else KeyboardActions.Default,
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

/** Pill chip: ember signature when selected, tonal when static. */
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
        selected -> EmberSoft
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    val fg = contentColor ?: when {
        selected -> EmberDeep
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    val border = if (selected) BorderStroke(1.dp, Ember.copy(alpha = 0.45f)) else null
    val interaction = remember { MutableInteractionSource() }
    val haptics = rememberHaptics()
    Surface(
        modifier = modifier.then(
            if (onClick != null) {
                Modifier
                    .then(pressModifier(interaction))
                    .semantics {
                        role = Role.Button
                        stateDescription = if (selected) "Выбрано" else "Не выбрано"
                    }
            } else {
                Modifier
            },
        ),
        shape = shape,
        color = bg,
        contentColor = fg,
        border = border,
    ) {
        val inner = Modifier
            .then(if (onClick != null) Modifier.heightIn(min = 48.dp) else Modifier)
            .padding(horizontal = Spacing.lg, vertical = Spacing.sm)
        if (onClick != null) {
            Row(
                modifier = inner.clickable(
                    interactionSource = interaction,
                    indication = null,
                    onClick = { haptics.light(); onClick() },
                ),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
            ) {
                // The slot is composed in both states: a chip that grows on tap slides
                // every chip after it sideways, and on a narrow screen that is a re-wrap
                // under the finger. Only paint moves.
                val progress by animateFloatAsState(
                    targetValue = if (selected) 1f else 0f,
                    animationSpec = tween(Motion.Fast),
                    label = "chipSelection",
                )
                Box(
                    Modifier
                        .size(14.dp)
                        .graphicsLayer {
                            scaleX = 0.7f + 0.3f * progress
                            scaleY = 0.7f + 0.3f * progress
                        }
                        .clip(CircleShape)
                        .background(Ember.copy(alpha = progress))
                        .border(1.5.dp, Ember.copy(alpha = 0.30f + 0.70f * progress), CircleShape),
                )
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
    BoxWithConstraints(
        modifier = modifier
            .fillMaxWidth()
            .graphicsLayer {
                alpha = appear.value
                translationY = (1f - appear.value) * 14.dp.toPx()
                scaleX = 0.96f + 0.04f * appear.value
                scaleY = 0.96f + 0.04f * appear.value
            },
        contentAlignment = if (isOwn) Alignment.CenterEnd else Alignment.CenterStart,
    ) {
        val cornerShape = RoundedCornerShape(
            topStart = 20.dp,
            topEnd = 20.dp,
            bottomStart = if (isOwn) 20.dp else 6.dp,
            bottomEnd = if (isOwn) 6.dp else 20.dp,
        )
        Column(
            modifier = Modifier
                // A bubble is as wide as its message, capped at 86% of the thread and
                // 340dp: a one-word reply must not stretch into a full-width banner, and
                // a long one stays inside a readable measure on any screen.
                .widthIn(max = minOf(maxWidth * 0.86f, 340.dp))
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
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(
                body,
                color = if (isOwn) Color.White else MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                footer,
                style = MaterialTheme.typography.labelSmall.tabularDigits(),
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
                        Text("$unread", style = MaterialTheme.typography.labelSmall.tabularDigits(), color = Color.White, fontWeight = FontWeight.Bold)
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

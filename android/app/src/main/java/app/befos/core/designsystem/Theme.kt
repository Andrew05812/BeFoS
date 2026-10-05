package app.befos.core.designsystem

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// ============================================================
// Design tokens: spacing, shapes, elevation, motion.
// Screens must use these instead of ad-hoc dp values.
// ============================================================

/** 4-pt spacing rhythm. Use these steps only. */
object Spacing {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 20.dp
    val xxl = 24.dp
    val huge = 32.dp
    val gutter = 20.dp        // horizontal screen padding
    val section = 40.dp       // vertical gap between content sections
    val hero = 48.dp
}

/** Elevation recipe: light tonal surface + hairline border + soft shadow. */
object Elev {
    val none = 0.dp
    val card = 2.dp
    val raised = 6.dp
    val overlay = 12.dp
    val hairlineWidth = 1.dp
}

/** Motion system — fast, smooth, purposeful. Every duration lives here, not in screens. */
object Motion {
    const val Fast = 140
    const val Base = 240
    const val Slow = 360

    /** Brand tempo: the splash logo and its wordmark land slower than UI content. */
    const val Hero = 650
    const val Reveal = 550

    /** How long an inline notice stays before it dismisses itself. */
    const val Notice = 3500

    fun <T> pressSpring() = spring<T>(
        dampingRatio = Spring.DampingRatioMediumBouncy,
        stiffness = Spring.StiffnessLow,
    )

    fun <T> enterSpring() = spring<T>(
        dampingRatio = Spring.DampingRatioNoBouncy,
        stiffness = Spring.StiffnessMediumLow,
    )

    fun <T> tweenBase(delayMillis: Int = 0) = tween<T>(durationMillis = Base, delayMillis = delayMillis)
}

// Shapes: hierarchy through DIFFERENT radii, not one huge radius everywhere.
val BeFosShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),   // small chips, badges
    small = RoundedCornerShape(14.dp),        // buttons, inputs
    medium = RoundedCornerShape(20.dp),       // cards, sheets
    large = RoundedCornerShape(26.dp),        // hero panels
    extraLarge = RoundedCornerShape(32.dp),   // dialogs, discovery card
)

// Internal, not private: the palette contract that the screens rely on is this scheme's
// token->role mapping, and ContrastPolicyTest has to read it to check that contract.
internal val LightColors = lightColorScheme(
    primary = Ember,
    onPrimary = Color.White,
    primaryContainer = EmberSoft,
    onPrimaryContainer = EmberDeep,
    secondary = Iris,
    onSecondary = Color.White,
    secondaryContainer = IrisSoft,
    onSecondaryContainer = IrisDeep,
    tertiary = Peach,
    onTertiary = Color(0xFF452200),
    tertiaryContainer = Apricot,
    onTertiaryContainer = Color(0xFF452200),
    background = PaperBackground,
    onBackground = InkTextPrimary,
    surface = PaperSurface,
    onSurface = InkTextPrimary,
    surfaceVariant = PaperTonal,
    onSurfaceVariant = InkTextSecondary,
    surfaceContainerHighest = PaperTonalStrong,
    outline = InkOutline,
    outlineVariant = PaperDivider,
    error = ErrorRed,
    onError = Color.White,
    errorContainer = Color(0xFFFFE0E1),
    onErrorContainer = Color(0xFF8C1D22),
)

internal val DarkColors = darkColorScheme(
    primary = Color(0xFFFF8A80),
    onPrimary = Color(0xFF4A0407),
    primaryContainer = Color(0xFF6E2220),
    onPrimaryContainer = EmberSoft,
    secondary = Color(0xFFB7A4FF),
    onSecondary = Color(0xFF220F5E),
    secondaryContainer = Color(0xFF3B2A85),
    onSecondaryContainer = IrisSoft,
    tertiary = Peach,
    onTertiary = Color(0xFF452200),
    background = NightBackground,
    onBackground = NightInk,
    surface = NightSurface,
    onSurface = NightInk,
    surfaceVariant = NightTonal,
    onSurfaceVariant = NightInkSecondary,
    outline = NightOutline,
    outlineVariant = Color(0x26FFFFFF),
    error = Color(0xFFFF8A80),
    onError = Color(0xFF4A0407),
)

@Composable
fun BeFosTheme(
    darkTheme: Boolean = false,
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = BeFosTypography,
        shapes = BeFosShapes,
        content = content,
    )
}

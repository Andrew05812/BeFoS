package app.befos.core.designsystem

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

// ============================================================
// BeFoS visual language — "Warm Ember minimalism".
// Coral/ember = action & brand. Iris violet is reserved as the
// signature color of compatibility DATA. Warm graphite neutrals,
// never pure black/white. One palette, meaningful colors only.
// ============================================================

// Brand — ember
val Ember = Color(0xFFF0544F)
val EmberDeep = Color(0xFFC63B44)
val EmberSoft = Color(0xFFFFE4DF)
val Peach = Color(0xFFFF9A62)
val Apricot = Color(0xFFFFC59E)

// Signature — compatibility data color family (iris)
val Iris = Color(0xFF6C4CF1)
val IrisDeep = Color(0xFF4A2FC4)
val IrisSoft = Color(0xFFEDE7FF)

// Support
val Mint = Color(0xFF2BBF97)
val MintSoft = Color(0xFFD8F5EC)

// Warm graphite neutrals (light)
val PaperBackground = Color(0xFFFAF6F3)
val PaperSurface = Color(0xFFFFFFFF)
val PaperElevated = Color(0xFFFFFFFF)
val PaperTonal = Color(0xFFF4EDE7)
val PaperTonalStrong = Color(0xFFEADFd6)
val PaperDivider = Color(0x143A2F38)
val Hairline = Color(0x1F3A2F38)

val InkTextPrimary = Color(0xFF1B1520)
val InkTextSecondary = Color(0xFF5C5468)
val InkTextTertiary = Color(0xFF9B93A8)
val InkOutline = Color(0xFFDDD2CE)

// Warm graphite neutrals (dark)
val NightBackground = Color(0xFF120E16)
val NightSurface = Color(0xFF1B1522)
val NightElevated = Color(0xFF241D2D)
val NightTonal = Color(0xFF2A2234)
val NightInk = Color(0xFFF4EEF6)
val NightInkSecondary = Color(0xFFB4AAC0)
val NightOutline = Color(0xFF3C3348)

// Semantic
val SuccessGreen = Color(0xFF1FA463)
val WarningAmber = Color(0xFFE1912B)
val ErrorRed = Color(0xFFD9484E)

// Compatibility score gradient stops (0..100).
val ScoreLow = Color(0xFFFF8A5C)
val ScoreMid = Color(0xFFF0544F)
val ScoreHigh = Color(0xFF6C4CF1)

// ------- Named gradients (single source of truth) -------

/** Primary CTA fill — the brand ember. */
val EmberGradient = Brush.linearGradient(listOf(Color(0xFFF6603F), EmberDeep))

/** Hero scrim over photos: transparent → warm ink. */
fun photoScrim(): Brush = Brush.verticalGradient(
    colorStops = arrayOf(
        0f to Color(0x00000000),
        0.45f to Color(0x26000000),
        1f to Color(0xE6000000),
    ),
)

/** Subtle top-edge tint used behind headers/hero sections. */
val HeroTint = Brush.verticalGradient(listOf(EmberSoft.copy(alpha = 0.55f), Color.Transparent))

/** Compatibility signature sweep (iris → ember) for bars and rings. */
fun compatBrush(start: Color, end: Color): Brush = Brush.linearGradient(listOf(start, end))

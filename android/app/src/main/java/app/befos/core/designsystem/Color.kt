package app.befos.core.designsystem

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

// ============================================================
// BeFoS visual language — "Warm Ember minimalism".
// Coral/ember = action & brand. Iris violet is reserved as the
// signature color of compatibility DATA. Warm graphite neutrals,
// never pure black/white. One palette, meaningful colors only.
// ============================================================

// Brand — ember.
// EmberDeep is the ember that carries TEXT: 11..15sp labels on paper, cards and the
// ember-soft chip. It is 4% darker than the pure hue step because at 0xFFC63B44 the
// lightest of those surfaces (EmberSoft) read 4.24:1, under the 4.5 bar for text that
// small. Ember itself stays for fills, bars, icons and numerals of 24sp+, where 3:1 is
// the bar and the brighter red is the point.
val Ember = Color(0xFFF0544F)
val EmberDeep = Color(0xFFBE3941)
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
// ErrorRed carries the 13sp line under an invalid field and the label of the destructive
// action: at 0xFFD9484E that text measured 4.21:1 on a card, under the 4.5 bar. 9% darker
// clears it (4.95:1) and white on the same fill still clears it too.
val SuccessGreen = Color(0xFF1FA463)
val WarningAmber = Color(0xFFE1912B)
val ErrorRed = Color(0xFFC54247)

// Compatibility score gradient stops (0..100).
val ScoreLow = Color(0xFFFF8A5C)
val ScoreMid = Color(0xFFF0544F)
val ScoreHigh = Color(0xFF6C4CF1)

// ------- Named gradients (single source of truth) -------

/** Primary CTA fill — the brand ember.
 *
 *  The light stop is the constraint: a labelLarge 15sp SemiBold white label is not "large
 *  text" under WCAG, so it needs 4.5:1 against every pixel it sits on. At 0xFFF6603F the
 *  white measured 3.15:1 at the light end and 3.98:1 mid-gradient; the stop moved 19%
 *  toward black to 0xFFC74E33 and the label now reads 4.6:1 at its lightest point.
 *
 *  The stops are named because the contract is on the stops, not on the Brush: reading
 *  them back off a Brush in a JVM test is not something worth depending on.
 */
val CtaStopLight = Color(0xFFC74E33)
val CtaStopDeep = EmberDeep
val EmberGradient = Brush.linearGradient(listOf(CtaStopLight, CtaStopDeep))

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

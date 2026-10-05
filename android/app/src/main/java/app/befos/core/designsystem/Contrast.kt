package app.befos.core.designsystem

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import kotlin.math.pow

// ============================================================
// Contrast arithmetic, shared by the theme and by its test.
//
// The app has accent colors that are correct as fills and wrong as text: the brand ember
// is 3.21:1 on paper, which clears the 3:1 bar for a border or a progress arc and does
// not clear the 4.5:1 bar for an 11sp label. These helpers exist so a call site can ask
// for "this hue, dark enough to write with" instead of picking a second token by eye.
// ============================================================

/** WCAG 2.1 relative luminance. Compose stores sRGB channels, which is what the formula wants. */
fun wcagLuminance(color: Color): Double {
    fun channel(v: Float): Double {
        val s = v.toDouble()
        return if (s <= 0.04045) s / 12.92 else ((s + 0.055) / 1.055).pow(2.4)
    }
    return 0.2126 * channel(color.red) + 0.7152 * channel(color.green) + 0.0722 * channel(color.blue)
}

/** Contrast ratio between two opaque colors: 1.0 for identical, 21.0 for black on white. */
fun wcagContrast(foreground: Color, background: Color): Double {
    val a = wcagLuminance(foreground)
    val b = wcagLuminance(background)
    return (maxOf(a, b) + 0.05) / (minOf(a, b) + 0.05)
}

/** What a translucent fill actually paints over an opaque surface. */
fun blend(over: Color, background: Color): Color = Color(
    red = over.red * over.alpha + background.red * (1 - over.alpha),
    green = over.green * over.alpha + background.green * (1 - over.alpha),
    blue = over.blue * over.alpha + background.blue * (1 - over.alpha),
)

/**
 * The same hue walked toward black until it reads at [need] against [background].
 *
 * Only darkening is used: lightening toward white would flip an accent to a pastel and
 * break the pairing with the fill it explains. Returns [color] untouched when it already
 * clears the bar, so the strong accents in the palette stay exactly as they are.
 */
fun ensureTextContrast(color: Color, background: Color, need: Double = 4.5): Color {
    var candidate = color
    // 40 steps of 3% reach 30% of the original brightness; nothing in the palette needs
    // more, and the loop is bounded so an impossible request cannot spin.
    repeat(40) {
        if (wcagContrast(candidate, background) >= need) return candidate
        candidate = lerp(candidate, Color.Black, 0.03f)
    }
    return candidate
}

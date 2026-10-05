package app.befos.core.designsystem

import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The palette's contrast contract, measured with the WCAG 2.1 formula the theme itself
 * uses ([wcagContrast]).
 *
 * Every failure represented here was once a real measurement on a real screen: the ember
 * that fills a CTA is 3.21:1 on paper, which clears the bar for a border and not the bar
 * for an 11sp label, and the white label of that CTA read 3.15:1 against the light stop of
 * the gradient. Screens resolve accents through the color scheme, so the pairs below name
 * actual call-site colors rather than "every color against every other color".
 *
 * Thresholds: 4.5 for text under 18.6sp bold / 24sp regular, 3.0 for large text and for
 * non-text UI such as borders and progress arcs.
 */
class ContrastPolicyTest {

    private val white = Color.White

    /**
     * The card a user actually reads on. [AppCard] is a `Surface` with a tonal elevation, so
     * Material blends the scheme's surface tint into `surface` before any text is drawn —
     * [the test below](pins that blend to a screenshot of a card interior) rather than to the
     * flat `colorScheme.surface`, which is about 8% brighter in ratio than the pixels.
     */
    private val card = blend(LightColors.surfaceTint.copy(alpha = CardTintAlpha), LightColors.surface)

    /**
     * The bottom bar paints `surface` at 96% over the page, so its pixels are a hair off
     * white; the captured bar measured #FFFFFF. Text in it is solved against this, and the
     * selected tab's label is the site that used to be painted with the fill ember at
     * 3.45:1 — an 11sp label does not get the large-text bar.
     */
    private fun navSurface(s: androidx.compose.material3.ColorScheme) =
        blend(s.surface.copy(alpha = 0.96f), s.background)

    private fun check(need: Double, vararg pairs: Triple<String, Color, Color>) {
        val failing = pairs.map { (label, fg, bg) ->
            label to wcagContrast(fg, bg)
        }.filter { it.second < need }.map {
            "${it.first} = ${String.format("%.2f", it.second)} (need $need)"
        }
        assertTrue(failing.joinToString("\n"), failing.isEmpty())
    }

    @Test
    fun `the painted card is the color a screenshot shows`() {
        // Captured from a card interior on emulator-5554 (light theme). If this drifts, the
        // elevation or the tint moved and every text site solved against `card` has to be
        // re-read, because the thresholds are floors.
        val captured = Color(0xFFFEF3F3)
        fun drift(a: Float, b: Float) = Math.abs(a - b) * 255.0
        val channels = listOf(
            drift(card.red, captured.red),
            drift(card.green, captured.green),
            drift(card.blue, captured.blue),
        )
        assertTrue(
            "cardPaintedSurface() gives $card, the capture was #FEF3F3 (drift $channels)",
            channels.all { it <= 1.5 },
        )
    }

    @Test
    fun `small text on light surfaces clears 4_5`() {
        val s = LightColors
        // A field paints its label and its error line over a surface, and the field itself
        // is a translucent tonal fill, so the blended color is the one that matters.
        val field = blend(s.surfaceVariant.copy(alpha = 0.6f), card)
        check(
            4.5,
            Triple("field label when focused", s.onPrimaryContainer, field),
            Triple("field label at rest", s.onSurfaceVariant, field),
            Triple("field value", s.onSurface, field),
            Triple("field error line on a card", s.error, card),
            Triple("field error line on the page", s.error, s.background),
            Triple("profile-card goal line", s.onPrimaryContainer, card),
            Triple("profile hero goal chip over iris tint", s.onPrimaryContainer, IrisSoft),
            Triple("auth mode toggle", s.onPrimaryContainer, s.background),
            Triple("ghost button label", s.onPrimaryContainer, card),
            Triple("selected tab label in the bottom bar", s.onPrimaryContainer, navSurface(s)),
            Triple("unselected tab label in the bottom bar", s.onSurfaceVariant, navSurface(s)),
            Triple("sent confirmation on the ember chip", s.onPrimaryContainer, s.primaryContainer),
            Triple("body copy on the page", s.onBackground, s.background),
            Triple("secondary copy on a card", s.onSurfaceVariant, card),
            Triple("overline label on a tonal chip", s.onSurfaceVariant, s.surfaceVariant),
            Triple("onPrimaryContainer over primaryContainer", s.onPrimaryContainer, s.primaryContainer),
            Triple("onSecondaryContainer over secondaryContainer", s.onSecondaryContainer, s.secondaryContainer),
            Triple("onErrorContainer over errorContainer", s.onErrorContainer, s.errorContainer),
        )
    }

    @Test
    fun `small text on dark surfaces clears 4_5`() {
        val s = DarkColors
        val darkCard = blend(s.surfaceTint.copy(alpha = CardTintAlpha), s.surface)
        val field = blend(s.surfaceVariant.copy(alpha = 0.6f), darkCard)
        check(
            4.5,
            Triple("field label when focused", s.onPrimaryContainer, field),
            Triple("field label at rest", s.onSurfaceVariant, field),
            Triple("field error line", s.error, darkCard),
            Triple("profile-card goal line", s.onPrimaryContainer, darkCard),
            Triple("auth mode toggle", s.onPrimaryContainer, s.background),
            Triple("selected tab label in the bottom bar", s.onPrimaryContainer, navSurface(s)),
            Triple("unselected tab label in the bottom bar", s.onSurfaceVariant, navSurface(s)),
            Triple("body copy on the page", s.onBackground, s.background),
            Triple("secondary copy on a card", s.onSurfaceVariant, darkCard),
        )
    }

    @Test
    fun `large numerals and non-text accents clear 3_0`() {
        val s = LightColors
        check(
            3.0,
            Triple("test counter (displayMedium bold)", s.primary, s.background),
            Triple("answer-coverage percent (headlineSmall bold)", s.primary, card),
            Triple("focused field border", s.primary, card),
            Triple("loading arc on a card", s.primary, card),
            Triple("iris as a large numeral", s.secondary, card),
            Triple("tab icon on its selected pill", s.onPrimaryContainer,
                blend(s.primary.copy(alpha = 0.12f), navSurface(s))),
            Triple("tab icon in the dark theme", DarkColors.onPrimaryContainer,
                blend(DarkColors.primary.copy(alpha = 0.12f),
                    blend(DarkColors.surface.copy(alpha = 0.96f), DarkColors.background))),
        )
    }

    @Test
    fun `white CTA label clears 4_5 on every stop of the fill`() {
        // A gradient has no single background: the label's pixels sit on the light stop,
        // the dark stop and everything between, so all three are checked.
        val mid = blend(CtaStopLight.copy(alpha = 0.5f), CtaStopDeep)
        check(
            4.5,
            Triple("label at the light stop", white, CtaStopLight),
            Triple("label at mid-gradient", white, mid),
            Triple("label at the deep stop", white, CtaStopDeep),
        )
    }

    /**
     * The score hue is a fill, and its low end is bright: ScoreLow is 2.33:1 on a card,
     * under even the large-text bar. Every percent therefore has to survive the text
     * helper that the rings, pills and category rows now call — including the low scores,
     * which are the ones that carry the most explanation.
     */
    @Test
    fun `score is legible as text at every percent`() {
        val smallText = (0..100).map { scoreTextColor(it, card) }
        assertTrue(
            "smallest 4.5:1 pair was ${String.format("%.2f", smallText.minOf { wcagContrast(it, card) })}",
            smallText.all { wcagContrast(it, card) >= 4.5 },
        )
        val largeText = (0..100).map { scoreTextColor(it, card, need = 3.0) }
        assertTrue(
            "smallest 3:1 pair was ${String.format("%.2f", largeText.minOf { wcagContrast(it, card) })}",
            largeText.all { wcagContrast(it, card) >= 3.0 },
        )
        val washed = (0..100).filter { percent ->
            val pill = blend(scoreColor(percent).copy(alpha = 0.12f), card)
            wcagContrast(scoreTextColorOnWash(percent, card), pill) < 4.5
        }
        assertTrue("score pills below 4.5:1 at $washed", washed.isEmpty())
    }

    /**
     * The compatibility hero solves its text against the panel's own gradient. The panel is
     * washed from [IrisSoft] down to the surface, so the ratio a caller computes against
     * `surface` is the easy end: the ember verdict line measures 3.45:1 on white at 50% and
     * 2.87:1 on the IrisSoft stop it is actually drawn over. The digits inside the ring and
     * the verdict line below it are solved against the dark stop, so the whole panel is
     * covered by one number rather than by wherever the text happens to land.
     */
    @Test
    fun `the score text on the iris-washed hero clears its bar on the dark stop`() {
        val verdict = (0..100).map { scoreTextColor(it, IrisSoft, need = 3.0) }
        val low = verdict.filter { wcagContrast(it, IrisSoft) < 3.0 }
        assertTrue("verdict line below 3:1 on IrisSoft at ${low.size} percents", low.isEmpty())
        val digits = (0..100).map { scoreTextColor(it, IrisSoft) }
        val thin = digits.filter { wcagContrast(it, IrisSoft) < 4.5 }
        assertTrue("ring digits below 4.5:1 on IrisSoft at ${thin.size} percents", thin.isEmpty())
    }

    @Test
    fun `darkening a score for text never changes its family`() {
        // The helper may only walk toward black: a hue that drifted toward another stop
        // would make a 40% card read as a 90% one.
        for (percent in 0..100 step 5) {
            val raw = scoreColor(percent)
            val text = ensureTextContrast(raw, card)
            val ratio = wcagContrast(text, raw)
            assertTrue(
                "$percent% drifted too far from its fill color (ratio $ratio)",
                ratio <= 2.6,
            )
            assertTrue(
                "$percent% gained alpha",
                text.alpha == raw.alpha,
            )
        }
    }

    /**
     * The bottom bar is on every screen of the app, and its selected tab used to be painted
     * with the fill ember: 3.45:1 for the label on the bar and 2.98:1 for the icon on its own
     * 12% pill. An 11sp label has no large-text bar to hide behind, and the icon sits under
     * the 3:1 bar for non-text UI. Pinned in both themes, because the theme files are where
     * a future token edit would quietly move these numbers again.
     */
    @Test
    fun `the bottom bar is legible in both themes`() {
        for ((name, s) in listOf("light" to LightColors, "dark" to DarkColors)) {
            val bar = navSurface(s)
            val pill = blend(s.primary.copy(alpha = 0.12f), bar)
            val label = wcagContrast(s.onPrimaryContainer, bar)
            val icon = wcagContrast(s.onPrimaryContainer, pill)
            val unselected = wcagContrast(s.onSurfaceVariant, bar)
            assertTrue("$name selected tab label reads at $label on the bar", label >= 4.5)
            assertTrue("$name selected tab icon reads at $icon on its pill", icon >= 3.0)
            assertTrue("$name unselected tab label reads at $unselected", unselected >= 4.5)
        }
    }

    @Test
    fun `the ember that carries text stays darker than the ember that carries fills`() {
        // The whole accessibility argument for two embers is that the text one is the
        // darker one; a token edit that lightens it back to the brand red breaks 11..15sp
        // labels on every light surface at once.
        assertTrue(
            "EmberDeep must stay darker than Ember",
            wcagLuminance(EmberDeep) < wcagLuminance(Ember),
        )
        assertTrue(
            "EmberDeep must clear 4.5 over the iris-tinted hero panel",
            wcagContrast(EmberDeep, IrisSoft) >= 4.5,
        )
        assertTrue(
            "ErrorRed must clear 4.5 as 13sp text on paper",
            wcagContrast(ErrorRed, PaperBackground) >= 4.5,
        )
    }
}

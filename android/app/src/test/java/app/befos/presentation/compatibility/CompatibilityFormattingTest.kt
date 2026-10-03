package app.befos.presentation.compatibility

import app.befos.core.designsystem.compatibilityVerdict
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Pure formatting/verdict helpers used by the compatibility screen. */
class CompatibilityFormattingTest {

    @Test
    fun `verdict maps score bands to distinct copy`() {
        assertEquals("Вы очень хорошо подходите", compatibilityVerdict(90))
        assertEquals("Вы очень хорошо подходите", compatibilityVerdict(85))
        assertEquals("Вы хорошо подходите", compatibilityVerdict(75))
        assertEquals("Есть перспектива", compatibilityVerdict(60))
        assertEquals("Стоит узнать друг друга", compatibilityVerdict(45))
        assertEquals("Вы довольно разные", compatibilityVerdict(20))
    }

    @Test
    fun `verdict is defined across the whole range`() {
        for (score in 0..100) {
            assertTrue(compatibilityVerdict(score).isNotBlank())
        }
    }

    @Test
    fun `prettifySlug humanises interest slugs`() {
        assertEquals("Road trips", prettifySlug("road_trips"))
        assertEquals("Live music", prettifySlug("live-music"))
        assertEquals("Yoga", prettifySlug("yoga"))
    }
}

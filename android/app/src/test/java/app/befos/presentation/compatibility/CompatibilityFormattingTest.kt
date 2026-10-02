package app.befos.presentation.compatibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Pure formatting/verdict helpers used by the compatibility screen. */
class CompatibilityFormattingTest {

    @Test
    fun `verdict maps score bands to distinct copy`() {
        assertEquals("Вы очень хорошо подходите", verdictFor(90))
        assertEquals("Вы очень хорошо подходите", verdictFor(85))
        assertEquals("Вы хорошо подходите", verdictFor(75))
        assertEquals("Есть перспектива", verdictFor(60))
        assertEquals("Стоит узнать друг друга", verdictFor(45))
        assertEquals("Вы довольно разные", verdictFor(20))
    }

    @Test
    fun `verdict is defined across the whole range`() {
        for (score in 0..100) {
            assertTrue(verdictFor(score).isNotBlank())
        }
    }

    @Test
    fun `prettifySlug humanises interest slugs`() {
        assertEquals("Road trips", prettifySlug("road_trips"))
        assertEquals("Live music", prettifySlug("live-music"))
        assertEquals("Yoga", prettifySlug("yoga"))
    }
}

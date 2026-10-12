package app.befos.presentation.common

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * A band the engine had nothing to compare on carries its neutral half, and the screen used to
 * print that half as "50%" next to the bands two people actually answered. `has_data` is what the
 * pair route now sends along with the percent, and this is the one rule built on it.
 */
class CategoryReadoutTest {

    @Test
    fun `a measured band prints its percent`() {
        assertEquals("50%", categoryReadout(hasData = true, score = 50))
        assertEquals("100%", categoryReadout(hasData = true, score = 100))
        assertEquals("0%", categoryReadout(hasData = true, score = 0))
    }

    @Test
    fun `a band nobody answered prints no percent`() {
        // The engine's neutral value is still 50 underneath; the word replaces it, so the same
        // digits a measured band shows cannot come from a band with no answers.
        assertEquals("нет данных", categoryReadout(hasData = false, score = 50))
        assert(categoryReadout(hasData = false, score = 50) != "50%")
    }
}

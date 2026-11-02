package app.befos.presentation.common

import app.befos.presentation.discovery.likedMeShownWord
import app.befos.presentation.discovery.myLikesShownWord
import app.befos.presentation.discovery.passedShownWord
import app.befos.presentation.matches.matchesShownWord
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The line above a paged list is the first thing a screen reader says, so the case of its noun is not
 * decoration: «показано 1 лайков» tells the account that its own numbers cannot be trusted. The device
 * pass of stage 126 met that sentence over an inbox holding exactly one tap.
 */
class ShownCountWordsTest {
    @Test
    fun `the count line takes the case the number asks for`() {
        assertEquals("Показано 1 лайк — весь список", shownWord(1, truncated = false, "лайк", "лайка", "лайков"))
        assertEquals("Показано 2 лайка — весь список", shownWord(2, truncated = false, "лайк", "лайка", "лайков"))
        assertEquals("Показано 5 лайков — весь список", shownWord(5, truncated = false, "лайк", "лайка", "лайков"))
        assertEquals("Показано 11 лайков — весь список", shownWord(11, truncated = false, "лайк", "лайка", "лайков"))
        assertEquals("Показано 21 лайк — весь список", shownWord(21, truncated = false, "лайк", "лайка", "лайков"))
        assertEquals(
            "Показано 101 касание, и список идёт дальше",
            shownWord(101, truncated = true, "касание", "касания", "касаний"),
        )
        assertEquals(
            "Показано 111 касаний, и список идёт дальше",
            shownWord(111, truncated = true, "касание", "касания", "касаний"),
        )
        assertEquals(
            "Показано 3 пропуска, и список идёт дальше",
            shownWord(3, truncated = true, "пропуск", "пропуска", "пропусков"),
        )
        assertEquals("Показано 1 пара — весь список", shownWord(1, truncated = false, "пара", "пары", "пар"))
        assertEquals("Показано 4 пары — весь список", shownWord(4, truncated = false, "пара", "пары", "пар"))
        assertEquals("Показано 20 пар — весь список", shownWord(20, truncated = false, "пара", "пары", "пар"))
    }

    @Test
    fun `every paged screen says the same sentence about its own rows`() {
        assertEquals("Показано 1 лайк — весь список", likedMeShownWord(1, truncated = false))
        assertEquals("Показано 1 касание, и список идёт дальше", myLikesShownWord(1, truncated = true))
        assertEquals("Показано 1 пропуск — весь список", passedShownWord(1, truncated = false))
        assertEquals("Показано 1 пара, и список идёт дальше", matchesShownWord(1, truncated = true))
        // The numbers the published walk stands on keep the form they were shot with.
        assertEquals("Показано 50 касаний, и список идёт дальше", myLikesShownWord(50, truncated = true))
    }
}

package app.befos.presentation.pair

import app.befos.domain.model.PairNextPlan
import app.befos.domain.model.PairPerson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * The sentences a pair's reading surface puts on its own facts.
 *
 * The rule the whole file is checked against is that this page adds nothing: it names the two people in the
 * order their own document lists them, quotes the hour in the words the pair's other screens already use,
 * and drops a moment it cannot read rather than printing a day nobody formed a pair on. A pair with plans
 * but no agreed hour is not a pair with no plans, and the two sayings of that are kept apart here because
 * the screen cannot afford to guess which one it is showing.
 */
class PairProfileWordsTest {

    private val kyiv = ZoneId.of("Europe/Kyiv")

    @Test
    fun `the two of them are named in the pair's own order`() {
        val people = listOf(PairPerson("u2", "Боря"), PairPerson("u1", "Аня"))
        assertEquals("Боря и Аня", pairPeopleWord(people))
        assertEquals("Аня", pairPeopleWord(listOf(PairPerson("u1", "Аня"))))
        assertNull(pairPeopleWord(emptyList()))
        // A row that carries a name the server left blank names nobody, and the page shows no line rather
        // than a dangling «и».
        assertNull(pairPeopleWord(listOf(PairPerson("u1", "  "))))
    }

    @Test
    fun `the day the pair formed is read on the reader's calendar`() {
        // 20:15 at +03:00 is 17:15 the same day in Kyiv; the day is the fact the screen prints.
        assertEquals(
            "18 апреля 2026",
            pairSinceDay("2026-04-18T20:15:00+03:00", ZoneId.of("Europe/Moscow")),
        )
        assertEquals("18 апреля 2026", pairSinceDay("2026-04-18T17:15:00+00:00", kyiv))
    }

    @Test
    fun `a moment that cannot be read as a day shows no day`() {
        assertNull(pairSinceDay("", kyiv))
        assertNull(pairSinceDay("вчера", kyiv))
        // No hour at all is a date the server did not finish writing, and inventing one would put this
        // build's clock in front of the day a pair actually formed.
        assertNull(pairSinceDay("2026-04-18", kyiv))
    }

    @Test
    fun `the count of plans ends the way Russian needs it to`() {
        assertEquals("1 план", plansTotalWord(1))
        assertEquals("2 плана", plansTotalWord(2))
        assertEquals("5 планов", plansTotalWord(5))
        assertEquals("11 планов", plansTotalWord(11))
        assertEquals("21 план", plansTotalWord(21))
        assertEquals("0 планов", plansTotalWord(0))
    }

    @Test
    fun `the nearest hour is quoted the way the pair's other screens quote it`() {
        val now = ZonedDateTime.of(LocalDate.of(2026, 10, 17).atTime(12, 0), kyiv)
        val planned = PairNextPlan(
            planId = "p7",
            status = "planned",
            startsAt = "2026-10-17T19:00:00+03:00",
        )

        // The same words the chat's plan card and the ideas card print for the same evening.
        assertEquals(
            "Договорились: Сегодня, 19:00",
            nextPlanWord(planned, now),
        )
        assertNull(nextPlanWord(null, now))
        // An hour the pair never agreed to is not an hour the page may print.
        assertNull(nextPlanWord(planned.copy(startsAt = ""), now))
    }

    @Test
    fun `an evening the clock has walked past keeps its words and says it passed`() {
        val now = ZonedDateTime.of(LocalDate.of(2026, 10, 19).atTime(12, 0), kyiv)
        val past = PairNextPlan("p7", "completed", "2026-10-17T19:00:00+03:00")

        val word = nextPlanWord(past, now)!!
        assertTrue(word.contains("Договорились"))
        assertTrue("a spent evening must not read as a standing plan", word.contains("час прошёл"))
    }

    @Test
    fun `a pair with plans and no hour is not told it has nothing`() {
        assertTrue(noPlanWord(0).contains("Ни одного плана"))
        val withPlans = noPlanWord(3)
        assertTrue(withPlans.contains("3 плана"))
        assertTrue(withPlans.contains("не стоит на часе"))
    }
}

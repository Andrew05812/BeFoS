package app.befos.presentation.plans

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

/**
 * The hour picker's choice, kept in the only representation that survives a screen being recreated.
 *
 * Both plan editors on this page held what a person had typed or tapped in `remember`, so turning the phone
 * over threw the sentence away — the note, the place, the chosen evening — and the history screen had
 * already learned the fix. `LocalDate` cannot go into a saved-state bundle, which is why the day travels as
 * days since the epoch: a `Long`, exact, and free of any formatter, locale or zone that could answer a
 * different day than the one the person touched.
 *
 * What the restore may not do is resurrect a choice the list no longer offers. The offered days are
 * generated from this clock and the server refuses an hour that has passed, so a saved day from an evening
 * spent in the editor can leave the week entirely — and a row that is not on the screen cannot be the row
 * being proposed to the pair.
 */
class PlanEditorRestoreTest {

    private val monday = LocalDate.of(2026, 10, 19)
    private val days = listOf(monday, monday.plusDays(1), monday.plusDays(2))
    private val hours = listOf(10, 12, 15, 17, 19, 21)

    @Test
    fun `a saved day comes back as the same day and nothing else`() {
        val saved = HourChoiceRestore.encodeDay(monday)
        assertTrue(
            "the day has to travel as something a bundle holds: was ${saved::class.java.name}",
            java.io.Serializable::class.java.isInstance(saved),
        )
        assertEquals(monday, HourChoiceRestore.decodeDay(saved))
        // Round-tripped through the primitive, seven days apart: no formatter and no zone in the path.
        days.forEach { assertEquals(it, HourChoiceRestore.decodeDay(HourChoiceRestore.encodeDay(it))) }
    }

    @Test
    fun `nothing chosen yet is a number no date ever takes`() {
        assertEquals(HourChoiceRestore.NO_EPOCH_DAY, HourChoiceRestore.encodeDay(null))
        assertNull(HourChoiceRestore.decodeDay(HourChoiceRestore.NO_EPOCH_DAY))
        assertEquals(HourChoiceRestore.NO_HOUR, -1)
        assertNull(HourChoiceRestore.decodeHour(HourChoiceRestore.NO_HOUR))
        assertEquals(21, HourChoiceRestore.decodeHour(21))
    }

    @Test
    fun `a day the list still offers is honoured after the screen is rebuilt`() {
        val saved = HourChoiceRestore.encodeDay(days[2])
        assertEquals(days[2], HourChoiceRestore.pickDay(saved, days))
        assertEquals(17, HourChoiceRestore.pickHour(17, hours))
    }

    @Test
    fun `a day that has walked out of the offered week falls back to the first one on screen`() {
        // The person chose Wednesday; by the time they came back the list starts on Thursday, and the chip
        // they touched is gone. Keeping the choice would put the button's label and the sent instant out of
        // step with anything the screen shows.
        val stale = HourChoiceRestore.encodeDay(days.first())
        val shorter = days.drop(1)
        assertEquals(shorter.first(), HourChoiceRestore.pickDay(stale, shorter))

        val goneHour = HourChoiceRestore.pickHour(10, hours.drop(1))
        assertEquals(12, goneHour)
    }

    @Test
    fun `an unset choice starts on the first row the editor offers`() {
        assertEquals(days.first(), HourChoiceRestore.pickDay(HourChoiceRestore.NO_EPOCH_DAY, days))
        assertEquals(10, HourChoiceRestore.pickHour(HourChoiceRestore.NO_HOUR, hours))
    }

    @Test
    fun `an empty list is answered as empty rather than as a row that does not exist`() {
        // Every hour of today can be behind the clock, and a picker that invented a row here would offer to
        // send an instant the server has already refused.
        assertNull(HourChoiceRestore.pickDay(HourChoiceRestore.NO_EPOCH_DAY, emptyList()))
        assertNull(HourChoiceRestore.pickHour(HourChoiceRestore.NO_HOUR, emptyList()))
        assertNull(HourChoiceRestore.pickDay(HourChoiceRestore.encodeDay(monday), emptyList()))
        assertNull(HourChoiceRestore.pickHour(19, emptyList()))
    }
}

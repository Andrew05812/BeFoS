package app.befos.presentation.plans

import java.time.LocalDate

/**
 * The hour picker's held state, in the representation that survives being saved.
 *
 * The row keeps three answers while a person is choosing: whether the editor is open at all, which day
 * they touched and which hour. Days are `LocalDate`, and a `LocalDate` is not something the platform can
 * put into a saved-state bundle — the registry refuses it at the moment the screen is stopped for
 * recreation, which would take the whole editor down rather than merely lose the choice. So the day
 * travels as whole days since the epoch: a `Long`, exact, round-tripping without a formatter, a locale or
 * a timezone getting between the number and the day it names. Absence is a named sentinel rather than a
 * null, because the value that comes back from a bundle is read as often as the one that went in.
 *
 * This is the same lesson the plan-history note learned
 * ([app.befos.presentation.plans.PlanHistoryScreen]'s `NoteCard`): typed state belongs in
 * `rememberSaveable`, and a value the bundle cannot hold is handed over as one it can. Nothing here
 * interprets a choice — [pickDay] and [pickHour] only keep a stale tap from naming a row the screen no
 * longer offers, which is the rule the editor already applied before it could lose anything.
 */
internal object HourChoiceRestore {

    /** «nobody has touched a day yet» — a number no real date ever takes. */
    const val NO_EPOCH_DAY: Long = Long.MIN_VALUE

    /** «nobody has touched an hour yet» — outside the clock's own range of 0..23. */
    const val NO_HOUR: Int = -1

    /** The day as days since the epoch, or [NO_EPOCH_DAY] when nothing was chosen. */
    fun encodeDay(day: LocalDate?): Long = day?.toEpochDay() ?: NO_EPOCH_DAY

    /** The day a saved number names, or null for [NO_EPOCH_DAY]. */
    fun decodeDay(saved: Long): LocalDate? = if (saved == NO_EPOCH_DAY) null else LocalDate.ofEpochDay(saved)

    /** The hour a saved number names, or null for [NO_HOUR]. */
    fun decodeHour(saved: Int): Int? = if (saved == NO_HOUR) null else saved

    /**
     * Which day the row stands on.
     *
     * A saved day the current list still offers is honoured — that is the whole point of saving it. One it
     * no longer offers is dropped rather than kept: the list is generated from this clock, so an evening
     * spent in the editor can walk the person's saved day out of the week the server would still accept,
     * and a chip that is not on the screen cannot be the one being offered to anybody.
     */
    fun pickDay(saved: Long, days: List<LocalDate>): LocalDate? {
        if (days.isEmpty()) return null
        val restored = decodeDay(saved)
        return if (restored != null && restored in days) restored else days.first()
    }

    /** Which hour the row stands on, under the same rule as the day. */
    fun pickHour(saved: Int, hours: List<Int>): Int? {
        if (hours.isEmpty()) return null
        val restored = decodeHour(saved)
        return if (restored != null && restored in hours) restored else hours.first()
    }
}

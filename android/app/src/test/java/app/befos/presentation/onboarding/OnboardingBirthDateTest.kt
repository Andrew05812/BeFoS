package app.befos.presentation.onboarding

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.TimeZone

/** The birth-date field collects digits; these helpers turn them into a checked ISO date. */
class OnboardingBirthDateTest {

    @Test
    fun `eight digits become an iso date`() {
        assertEquals("1998-05-14", isoBirthDate("19980514"))
    }

    @Test
    fun `impossible calendar days are rejected`() {
        assertNull(isoBirthDate("19980230"))
        assertNull(isoBirthDate("19981301"))
        assertNull(isoBirthDate("19980010"))
    }

    @Test
    fun `short input is not a date yet`() {
        assertNull(isoBirthDate(""))
        assertNull(isoBirthDate("199805"))
    }

    @Test
    fun `error copy names the actual problem`() {
        assertEquals("Укажите дату рождения.", birthDateError(""))
        assertEquals("Введите дату рождения целиком — 8 цифр.", birthDateError("1998"))
        assertEquals("Такой даты не бывает.", birthDateError("19980230"))
        assertEquals("Такой даты не бывает.", birthDateError("29990101"))
        assertNull(birthDateError("19900514"))
    }

    @Test
    fun `anyone under eighteen is turned away`() {
        // A frozen "today" instead of the machine's, so the boundary is the same on every host.
        val today = LocalDate.of(2026, 10, 7)
        assertEquals("BeFoS доступен с 18 лет.", birthDateError("20081008", today))
        assertNull(birthDateError("20081007", today))
        assertNull(birthDateError("19900514", today))
    }

    @Test
    fun `the pre-check does not take the device zone as its today`() {
        // The server counts age on the UTC calendar, so the pre-check has to ask it too: a device
        // fourteen hours behind Greenwich lives a day late for most of the UTC day and would deny
        // the field a person the API is about to admit. Two zones fourteen hours apart on either
        // side of UTC cannot both agree with the UTC date, so a "today" that followed the device
        // zone would return two different dates here.
        val previous = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone(ZoneId.of("+14:00")))
            val ahead = utcToday()
            TimeZone.setDefault(TimeZone.getTimeZone(ZoneId.of("-14:00")))
            val behind = utcToday()
            assertEquals(ahead, behind)
            assertEquals(LocalDate.now(ZoneOffset.UTC), behind)
        } finally {
            TimeZone.setDefault(previous)
        }
    }
}

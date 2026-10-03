package app.befos.presentation.onboarding

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.format.DateTimeFormatter

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
        val justUnder = LocalDate.now().minusYears(18).plusDays(1)
        val justOver = LocalDate.now().minusYears(18).minusDays(1)
        val fmt = DateTimeFormatter.ofPattern("yyyyMMdd")
        assertEquals("BeFoS доступен с 18 лет.", birthDateError(justUnder.format(fmt)))
        assertNull(birthDateError(justOver.format(fmt)))
    }
}

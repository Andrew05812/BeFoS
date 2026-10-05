package app.befos.presentation.common

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The identity line under a name on a card, on a public profile and in the profile hero.
 * A profile can genuinely have no city — a row written before the answer was refused, or
 * one that was never filled in — and the line then has one thing to say, not a separator
 * standing where the second half should be.
 */
class IdentityLineTest {

    @Test
    fun `two answers are joined by one separator`() {
        assertEquals("Москва · Отношения", identityLine("Москва", "relationship"))
    }

    @Test
    fun `a missing city leaves no dangling separator`() {
        assertEquals("Отношения", identityLine("", "relationship"))
        assertEquals("Отношения", identityLine("   ", "relationship"))
    }

    @Test
    fun `a missing goal leaves no dangling separator`() {
        assertEquals("Сочи", identityLine("Сочи", ""))
    }

    @Test
    fun `nothing answered is nothing said`() {
        assertEquals("", identityLine("  ", ""))
    }

    @Test
    fun `surrounding whitespace does not become part of the city`() {
        assertEquals("Тверь · Брак", identityLine("  Тверь ", "marriage"))
    }

    @Test
    fun `an unknown goal code is still shown rather than dropped`() {
        assertEquals("Казань · penpal", identityLine("Казань", "penpal"))
    }
}

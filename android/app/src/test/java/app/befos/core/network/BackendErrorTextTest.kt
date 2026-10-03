package app.befos.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The UI is Russian end to end; the API contract is English. These tests pin the seam
 * between the two so a raw backend sentence can never reach a screen again.
 */
class BackendErrorTextTest {

    private fun cyrillic(text: String) = text.any { it in 'А'..'я' || it == 'ё' || it == 'Ё' }

    @Test
    fun `known backend messages become product copy`() {
        val cases = mapOf(
            "Invalid email or password." to "Не совпали email или пароль. Попробуйте ещё раз.",
            "An account with this email already exists." to "Такой email уже занят. Войдите или попробуйте другой.",
            "Message is too long." to "Сообщение слишком длинное — разбейте его на два.",
            "Unsupported image type. Use JPEG, PNG or WEBP." to "Поддерживаются JPEG, PNG и WEBP.",
            "You cannot act on your own profile." to "Это ваша анкета.",
            "Complete your profile before discovering people." to "Заполните анкету, чтобы увидеть людей.",
        )
        cases.forEach { (backend, expected) ->
            assertEquals(expected, localizeBackendError(backend, "validation_error", 422))
        }
    }

    @Test
    fun `parameterised messages match on their constant prefix`() {
        assertTrue(cyrillic(localizeBackendError("Image exceeds 8 MB limit.", "validation_error", 422)))
        assertTrue(cyrillic(localizeBackendError("Question 7 not found.", "not_found", 404)))
        assertTrue(
            cyrillic(
                localizeBackendError(
                    "Invalid report reason. Allowed: ['spam'].",
                    "validation_error",
                    422,
                )
            )
        )
    }

    @Test
    fun `unseen english never leaks into the ui`() {
        val result = localizeBackendError("Some brand new backend sentence.", "", 500)
        assertFalse(result.contains("brand new"))
        assertTrue(cyrillic(result))
    }

    @Test
    fun `machine code gives a better fallback than the status alone`() {
        assertEquals("Сессия истекла. Войдите снова.", localizeBackendError("Token rotated.", "unauthorized", 401))
        assertEquals("Проверьте введённые данные.", localizeBackendError("Bad field.", "validation_error", 422))
        assertEquals("Не найдено.", localizeBackendError("", "not_found", 404))
    }

    @Test
    fun `transport status copy stays untouched`() {
        assertEquals(defaultHttpMessage(401), localizeBackendError("", "", 401))
        assertEquals(defaultHttpMessage(429), localizeBackendError("", "", 429))
    }
}

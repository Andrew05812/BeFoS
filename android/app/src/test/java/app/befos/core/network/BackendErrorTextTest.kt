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
        assertEquals("Этого здесь нет — возможно, анкету или чат удалили.", localizeBackendError("", "not_found", 404))
    }

    @Test
    fun `a refusal is not sold as a retry`() {
        // Asking again for something the server already refused cannot work, so the one
        // thing this line must not do is send the user back to the tap that was denied.
        val refused = "У вашего аккаунта нет доступа к этому."
        assertFalse(refused.contains("ещё раз"))
        assertEquals(refused, defaultHttpMessage(403))
        assertEquals(refused, localizeBackendError("", "", 403))
        assertEquals(refused, localizeBackendError("", "forbidden", 403))
        assertEquals(refused, localizeBackendError("You do not have access to this resource.", "forbidden", 403))
    }

    @Test
    fun `one failure has one wording whichever route found it`() {
        // The envelope message, the machine code and the bare status all describe the same
        // event; three sentences for it is how a product starts to contradict itself.
        assertEquals("Что-то сломалось с нашей стороны. Попробуйте ещё раз через минуту.", defaultHttpMessage(500))
        for (status in listOf(403, 404, 500)) {
            assertEquals(defaultHttpMessage(status), localizeBackendError("", codeOf(status), status))
        }
        assertEquals(
            defaultHttpMessage(404),
            localizeBackendError("Resource not found.", "not_found", 404),
        )
        assertEquals(
            defaultHttpMessage(500),
            localizeBackendError("Internal Server Error.", "internal_error", 500),
        )
    }

    @Test
    fun `a fallback never reads as a status label`() {
        for (status in listOf(400, 401, 403, 404, 409, 422, 429, 500, 502, 503, -1)) {
            val text = defaultHttpMessage(status)
            assertTrue(text, cyrillic(text))
            assertFalse("[$text] leaks a number", Regex("""\d{3}""").containsMatchIn(text))
            assertTrue("[$text] is a bare label", text.length > 20)
        }
    }

    @Test
    fun `a failure that never reached the wire does not blame the network`() {
        // -1 used to read "Нет подключения к интернету." for any throwable, which told users
        // with working Wi-Fi that their connection was the problem. DNS failing is still
        // named by its own branch; this one only says what it can stand behind.
        val text = friendlyNetworkMessage(IllegalStateException("no engine registered"))
        assertTrue(text, cyrillic(text))
        assertFalse(text.contains("интернет"))
    }

    private fun codeOf(status: Int): String = when (status) {
        403 -> "forbidden"
        404 -> "not_found"
        else -> "internal_error"
    }

    @Test
    fun `an outage reads as an outage and not as a fault or a logout`() {
        // The backend says this when the database is not there. "Ошибка сервера" would blame
        // the app, and anything that reads like a session problem would send the user to
        // the login screen while their tokens are still valid.
        val outage = "BeFoS is sorting itself out for a moment. Try again in a few seconds."
        val expected = "Сервис временно недоступен. Попробуйте ещё раз через несколько секунд."
        assertEquals(expected, localizeBackendError(outage, "database_unavailable", 503))
        assertEquals(expected, localizeBackendError("", "database_unavailable", 503))
        assertFalse(localizeBackendError(outage, "database_unavailable", 503).contains("BeFoS is"))
    }

    @Test
    fun `the socket answers a refused frame with advice, not with the contract text`() {
        // The live socket refuses single frames this client sent. It never says the connection
        // is down — the socket is up and answering — so each of these reads as advice about the
        // message, never as a network problem.
        val cases = mapOf(
            "Invalid frame." to "Сервер не понял это сообщение. Попробуйте ещё раз.",
            "Invalid message body." to "Сообщение не принято. Проверьте текст и отправьте ещё раз.",
            "Unknown message type: typing" to "Сообщение не отправлено. Попробуйте ещё раз.",
            "client_msg_id is longer than 64 characters." to "Сообщение не отправлено. Попробуйте ещё раз.",
        )
        cases.forEach { (backend, expected) ->
            assertEquals(expected, localizeBackendError(backend, "invalid_request", 400))
        }
    }

    @Test
    fun `transport status copy stays untouched`() {
        assertEquals(defaultHttpMessage(401), localizeBackendError("", "", 401))
        assertEquals(defaultHttpMessage(429), localizeBackendError("", "", 429))
    }
}

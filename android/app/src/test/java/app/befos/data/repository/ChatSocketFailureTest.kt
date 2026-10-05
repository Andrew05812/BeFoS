package app.befos.data.repository

import io.ktor.client.plugins.websocket.WebSocketException
import java.net.ConnectException
import java.net.ProtocolException
import java.net.UnknownHostException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What a failed chat dial turns into on screen.
 *
 * Measured against the live API with this same Ktor/OkHttp stack: a socket the server will
 * not grant ends before it opens, as
 * `java.net.ProtocolException: Expected HTTP 101 response but was '403 Forbidden'`. Two
 * defects lived in that one line — the English sentence was handed to the UI as the error
 * text, and it was counted as a network hiccup, so a pair that no longer exists was redialled
 * forever while the status line promised a recovery that could not happen.
 */
class ChatSocketFailureTest {

    private fun cyrillic(text: String) = text.any { it in 'А'..'я' || it == 'ё' || it == 'Ё' }

    private fun refused(status: String) =
        ProtocolException("Expected HTTP 101 response but was '$status'")

    @Test
    fun `a handshake the server refuses is read as a refusal`() {
        assertEquals(403, handshakeStatus(refused("403 Forbidden")))
        assertFalse(retryAfterDialFailure(refused("403 Forbidden")))
    }

    @Test
    fun `a refusal wrapped by the websocket plugin is still found`() {
        val wrapped = WebSocketException("Failed to connect", refused("403 Forbidden"))
        assertEquals(403, handshakeStatus(wrapped))
        assertFalse(retryAfterDialFailure(wrapped))
    }

    @Test
    fun `a dead session on the socket says so and stops dialling`() {
        assertFalse(retryAfterDialFailure(refused("401 Unauthorized")))
        assertEquals("Сессия истекла. Войдите снова.", socketFailureMessage(refused("401 Unauthorized")))
    }

    @Test
    fun `a chat the caller is no longer part of reads as gone, not as broken`() {
        assertEquals("Этот чат больше недоступен.", socketFailureMessage(refused("403 Forbidden")))
    }

    @Test
    fun `a server that failed the handshake is worth another dial`() {
        assertTrue(retryAfterDialFailure(refused("500 Internal Server Error")))
        assertEquals(
            "Что-то сломалось с нашей стороны. Попробуйте ещё раз через минуту.",
            socketFailureMessage(refused("500 Internal Server Error")),
        )
    }

    @Test
    fun `a dial that never reached the server names the network`() {
        assertTrue(retryAfterDialFailure(ConnectException("Connection refused")))
        assertEquals(
            "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.",
            socketFailureMessage(ConnectException("Connection refused")),
        )
        assertEquals("Нет подключения к интернету.", socketFailureMessage(UnknownHostException("no DNS")))
    }

    @Test
    fun `an engine that answers nothing is not mistaken for a refusal`() {
        assertNull(handshakeStatus(ConnectException("Connection refused")))
        assertTrue(retryAfterDialFailure(ConnectException("Connection refused")))
    }

    @Test
    fun `no english protocol text survives the mapping`() {
        val failures = listOf(
            refused("403 Forbidden"),
            refused("401 Unauthorized"),
            refused("503 Service Unavailable"),
            ConnectException("Connection refused (Connection refused)"),
            UnknownHostException("10.0.2.2: Name or service not known"),
            java.net.SocketTimeoutException("Connect timed out"),
        )
        for (e in failures) {
            val text = socketFailureMessage(e)
            assertTrue("$text should be Russian", cyrillic(text))
            for (word in listOf("HTTP", "101", "Forbidden", "refused", "timed out", "Name or service")) {
                assertFalse("[$text] leaks [$word]", text.contains(word))
            }
        }
    }
}

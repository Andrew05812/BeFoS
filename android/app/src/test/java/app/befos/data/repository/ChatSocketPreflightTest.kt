package app.befos.data.repository

import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.ByteReadChannel
import java.util.Base64
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import io.mockk.coEvery
import io.mockk.mockk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What a chat dial asks the backend before it is allowed to knock.
 *
 * The socket carries its token in a query parameter, so the HTTP stack cannot refresh it on a 401
 * the way it refreshes a REST call. The dial therefore sends an authenticated `GET /users/me`
 * first, whose only purpose is to rotate a token that has already expired. Measured on the device
 * that request costs 67…113 ms on a warm path and 670 ms on a cold one, while the backend answers
 * it in 14.8…17.7 ms — and it answered `200` on all six openings the stage recorded, because the
 * token had not expired. The client can read that from the token itself: the access token is a JWT
 * carrying `exp`, and an expiry date is not a secret.
 *
 * The answer must not become weaker authorization. The pair's rows, not the token, decide whether
 * a handshake is granted (`_refusal_reason` on the backend), and a token the client cannot read is
 * treated as expired: the request then goes out exactly as it did before.
 */
class ChatSocketPreflightTest {

    private fun accessToken(expSecondsFromNow: Long): String {
        val exp = System.currentTimeMillis() / 1000 + expSecondsFromNow
        val encoder = Base64.getUrlEncoder().withoutPadding()
        val payload = """{"sub":"f533ac6e","type":"access","exp":$exp}"""
        return "${encoder.encodeToString("""{"alg":"HS256","typ":"JWT"}""".toByteArray())}" +
            ".${encoder.encodeToString(payload.toByteArray())}.not-a-real-signature"
    }

    private fun storeWith(token: String?): TokenStore = mockk<TokenStore>().apply {
        coEvery { current() } returns token?.let { StoredAuth(it, "refresh-token", "user-id") }
    }

    private fun recorder(): Pair<HttpClient, MutableList<String>> {
        val seen = CopyOnWriteArrayList<String>()
        val engine = MockEngine { request ->
            seen += request.url.encodedPath
            if (request.url.protocol.name.startsWith("ws")) {
                // A refused handshake is what the live server answers, and it ends the dial loop
                // after one attempt — the calm the test needs.
                respond(ByteReadChannel(""), HttpStatusCode.Forbidden, headersOf())
            } else {
                respond(
                    ByteReadChannel("{}"),
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
            }
        }
        return HttpClient(engine) { install(WebSockets) } to seen
    }

    /** Runs one dial until the socket has knocked, then takes the collector away. */
    private fun dialOnce(token: String?): List<String> {
        val (client, seen) = recorder()
        return runBlocking {
            val scope = CoroutineScope(coroutineContext + Job())
            val socket = ChatSocket(client, storeWith(token), "3ef56d4b", scope)
            val collector = launch(Dispatchers.Unconfined) { socket.events.collect { } }
            var waited = 0
            while (seen.none { it.contains("/ws/chat/") } && waited < 4_000) {
                delay(20)
                waited += 20
            }
            collector.cancelAndJoin()
            scope.cancel()
            client.close()
            seen.toList()
        }
    }

    @Test
    fun `a token that still has minutes of life left needs no probe request`() {
        val seen = dialOnce(accessToken(1_800))
        assertEquals(emptyList<String>(), seen.filter { it.endsWith("/users/me") })
        assertTrue("the dial itself must still happen: $seen", seen.any { it.contains("/ws/chat/") })
    }

    @Test
    fun `an expired token still buys the probe before the dial`() {
        val seen = dialOnce(accessToken(-120))
        assertEquals(listOf("/api/v1/users/me"), seen.filter { it.endsWith("/users/me") })
    }

    @Test
    fun `a token the client cannot read is probed as if it were expired`() {
        val seen = dialOnce("opaque-session-string")
        assertEquals(listOf("/api/v1/users/me"), seen.filter { it.endsWith("/users/me") })
    }

    @Test
    fun `the probe answers before the handshake is attempted`() {
        val seen = dialOnce(accessToken(-120))
        val probe = seen.indexOfFirst { it.endsWith("/users/me") }
        val knock = seen.indexOfFirst { it.contains("/ws/chat/") }
        assertTrue("probe at $probe, handshake at $knock", probe in 0 until knock)
    }

    @Test
    fun `a token about to expire is still probed`() {
        val now = System.currentTimeMillis() / 1000
        assertTrue(accessTokenNeedsProbe(accessToken(30), now))
        assertFalse(accessTokenNeedsProbe(accessToken(90), now))
    }

    @Test
    fun `a payload without an expiry is read as expired`() {
        val now = System.currentTimeMillis() / 1000
        val encoder = Base64.getUrlEncoder().withoutPadding()
        val noExp = "${encoder.encodeToString("""{"alg":"HS256"}""".toByteArray())}." +
            encoder.encodeToString("""{"sub":"f533ac6e","type":"access"}""".toByteArray())
        assertTrue(accessTokenNeedsProbe(noExp, now))
        assertTrue(accessTokenNeedsProbe(null, now))
    }
}

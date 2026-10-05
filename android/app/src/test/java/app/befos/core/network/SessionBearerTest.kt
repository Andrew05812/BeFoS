package app.befos.core.network

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.get
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The HTTP client is a process-scope singleton and Ktor's bearer provider remembers the token
 * it loaded first. Nothing in the app tells that memory when the session is written, so signing
 * out and signing in as somebody else without a restart left the app calling the API as the
 * previous account: the backend answered for the wrong user and the interface showed a profile
 * that was not the one it was authenticated as. These tests pin the token that actually leaves
 * the device, because every journey in the E2E suite used one account per process and could not
 * see it.
 */
class SessionBearerTest {

    @Test
    fun `switching accounts inside one process changes the token on the next request`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val sent = mutableListOf<String?>()
        val client = createHttpClient(session, engineThat(sent))

        client.get(ApiConfig.api("users/me"))
        session.clear()
        session.login("token-bob", "bob")
        client.get(ApiConfig.api("users/me"))

        assertEquals(listOf("Bearer token-alice", "Bearer token-bob"), sent)
    }

    @Test
    fun `a signed-out app sends no bearer token`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val sent = mutableListOf<String?>()
        val client = createHttpClient(session, engineThat(sent))

        client.get(ApiConfig.api("users/me"))
        session.clear()
        client.get(ApiConfig.api("users/me"))

        assertEquals(listOf("Bearer token-alice", null), sent)
    }

    @Test
    fun `a refresh carries no bearer token and the retried request carries the session`() = runBlocking {
        val session = FakeSession().apply { login("expired-token", "alice") }
        val sent = mutableListOf<Pair<String, String?>>()
        val client = createHttpClient(
            session,
            MockEngine { request ->
                val path = request.url.encodedPath
                sent += path to request.headers[HttpHeaders.Authorization]
                if (path.endsWith("/auth/refresh")) {
                    json("""{"access_token":"fresh-token","refresh_token":"fresh-refresh"}""")
                } else {
                    json("{}", HttpStatusCode.Unauthorized)
                }
            },
        )

        client.get(ApiConfig.api("users/me"))

        // The route that hands out a new session must not go out authenticated with the old one,
        // and the retry has to use the token the session holds after the refresh.
        assertEquals(
            listOf(
                "/api/v1/users/me" to "Bearer expired-token",
                "/api/v1/auth/refresh" to null,
                "/api/v1/users/me" to "Bearer fresh-token",
            ),
            sent,
        )
        assertEquals("fresh-token", session.current()?.accessToken)
    }

    private fun engineThat(sent: MutableList<String?>) = MockEngine { request ->
        sent += request.headers[HttpHeaders.Authorization]
        json("{}")
    }

    private fun MockRequestHandleScope.json(
        body: String,
        status: HttpStatusCode = HttpStatusCode.OK,
    ) = respond(body, status, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))

    private class FakeSession : SessionTokens {
        private var auth: StoredAuth? = null

        override suspend fun current(): StoredAuth? = auth

        override suspend fun updateTokens(accessToken: String, refreshToken: String) {
            auth = StoredAuth(accessToken, refreshToken, auth?.userId ?: "unknown")
        }

        override suspend fun clear() {
            auth = null
        }

        fun login(accessToken: String, userId: String) {
            auth = StoredAuth(accessToken, "refresh-$accessToken", userId)
        }
    }
}

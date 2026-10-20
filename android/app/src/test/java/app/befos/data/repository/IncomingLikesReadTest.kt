package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.SessionTokens
import app.befos.core.network.StoredAuth
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The account's incoming taps, seen from the client's side of the wire.
 *
 * The read is pinned first as a shape: a GET that carries nothing but the session. A list of who
 * tapped the account built from an id the client passes is a door into somebody else's admirers, so
 * the bearer token has to be the only thing naming an inbox. Then the fields the screen draws are
 * pinned, because a row the mapper got wrong cannot be repaired by the layout: the percent is copied
 * out of the response rather than recomputed, and a percent the server did not store stays absent
 * instead of arriving as the zero at the bottom of a scale (defect 72-1).
 *
 * `has_more` is the third thing. The page shows fifty taps and names no cursor, so the flag is the
 * only way the client can tell a full list from a cut one; dropping it in the mapper would let the
 * screen claim it showed everyone who ever tapped.
 */
class IncomingLikesReadTest {

    private class Record(
        val method: String,
        val path: String,
        val bearer: String?,
    )

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

    private fun MockRequestHandleScope.envelope(
        status: HttpStatusCode,
        code: String,
        message: String,
    ) = respond(
        """{"error":{"code":"$code","message":"$message"}}""",
        status,
        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
    )

    /** One client, every request it sends recorded, answering with the given body. */
    private fun clientAnswering(
        session: FakeSession,
        status: HttpStatusCode = HttpStatusCode.OK,
        body: String = "",
        seen: MutableList<Record> = mutableListOf(),
    ) = Pair(
        createHttpClient(session, MockEngine { request ->
            seen += Record(
                method = request.method.value,
                path = request.url.encodedPath,
                bearer = request.headers[HttpHeaders.Authorization],
            )
            respond(body, status, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))
        }),
        seen,
    )

    @Test
    fun `the inbox is read with the session and nothing that names an account`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """
                {"likes":[{"user_id":"b","name":"Борис","age":31,"city":"Казань","photo_url":null,"compatibility":88,"liked_at":"2026-10-19T06:00:00+00:00"}],"has_more":false}
            """.trimIndent(),
        )

        val result = ApiService(client).likedMe()
        client.close()

        assertEquals("GET", seen[0].method)
        assertEquals("/api/v1/discover/liked-me", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
        // Whose inbox this is comes from the token alone: nothing in the URL, nothing in a body.
        assertEquals(1, seen.size)

        val page = (result as ApiResult.Success).data
        assertEquals(listOf("b"), page.likes.map { it.userId })
        assertEquals("Борис", page.likes[0].name)
        assertEquals(31, page.likes[0].age)
        assertEquals("Казань", page.likes[0].city)
        assertEquals(88, page.likes[0].compatibility)
        assertEquals("2026-10-19T06:00:00+00:00", page.likes[0].likedAt)
        assertEquals(false, page.hasMore)
    }

    @Test
    fun `the percent the tap carried arrives and the one nobody measured stays unmeasured`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, _) = clientAnswering(
            session,
            body = """
                {"likes":[
                  {"user_id":"a","name":"Анна","age":29,"city":"Москва","photo_url":"/uploads/a.png","compatibility":73,"liked_at":"2026-10-19T06:00:00+00:00"},
                  {"user_id":"b","name":"Борис","age":31,"city":"Казань","photo_url":null,"compatibility":null,"liked_at":"2026-10-18T06:00:00+00:00"},
                  {"user_id":"c","name":"Вера","age":27,"city":"Тверь","photo_url":"https://cdn.example.com/c.png","liked_at":""}
                ],"has_more":true}
            """.trimIndent(),
        )

        // Read through the repository, because the screen's rows are the domain's: the mapper is where
        // a relative photo path becomes a loadable url and where a stored percent must survive as a
        // number the tapper saw, not as a fresh score of the reader's own.
        val page = (DiscoveryRepositoryImpl(ApiService(client)).likedMe() as ApiResult.Success).data
        client.close()

        assertEquals(3, page.likes.size)
        assertEquals(true, page.truncated)
        assertEquals(73, page.likes[0].compatibility)
        // Null in, null out: neither zero nor a recomputed number. A row written before percents were
        // stored has no claim on the reader, and inventing one points at a match nobody measured.
        assertEquals(null, page.likes[1].compatibility)
        assertEquals(null, page.likes[2].compatibility)
        assertTrue(page.likes[0].photoUrl!!, page.likes[0].photoUrl!!.endsWith("/uploads/a.png"))
        assertNull(page.likes[1].photoUrl)
        assertEquals("https://cdn.example.com/c.png", page.likes[2].photoUrl)
        // A row whose instant the server did not write arrives as no instant, not as a date to print.
        assertEquals("", page.likes[2].likedAt)
    }

    @Test
    fun `a page that stopped at fifty reaches the screen as a page that stopped`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val rows = (1..50).joinToString(",") {
            """{"user_id":"u$it","name":"Анкета $it","age":25,"city":"Москва","photo_url":null,"compatibility":50,"liked_at":"2026-10-19T06:00:00+00:00"}"""
        }
        val (client, _) = clientAnswering(
            session,
            body = """{"likes":[$rows],"has_more":true}""",
        )

        val page = (DiscoveryRepositoryImpl(ApiService(client)).likedMe() as ApiResult.Success).data
        client.close()

        // The server shows fifty rows and names no cursor, so the flag is the only thing separating a
        // complete list from a cut one — and a list that ran out is a different answer from a list of
        // fifty, because the fifty-first person is somebody this screen did not show.
        assertEquals(50, page.likes.size)
        assertEquals(true, page.truncated)
    }

    @Test
    fun `the refusal of the read reaches the person in Russian`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val client = createHttpClient(
            session,
            MockEngine {
                envelope(
                    HttpStatusCode.TooManyRequests,
                    "rate_limited",
                    "Too many requests. Please slow down.",
                )
            },
        )

        val error = ApiService(client).likedMe() as ApiResult.Error
        client.close()

        assertEquals(429, error.code)
        // The English contract sentence must not reach the screen, and the page keeps its rows rather
        // than repainting them from a refusal it cannot answer.
        assertEquals("Слишком много запросов. Подождите немного.", error.message)
    }

    @Test
    fun `the answer given back goes through the door the deck already writes`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """{"match":true,"match_id":"m-7","compatibility":88}""",
        )

        val result = ApiService(client).like("b")
        client.close()

        // No second write path for the same answer: a like given from this page is the like the pair's
        // history would have held had it been given from the deck, so it goes to the same route.
        assertEquals("POST", seen[0].method)
        assertEquals("/api/v1/users/b/like", seen[0].path)
        assertEquals(true, (result as ApiResult.Success).data.match)
        assertEquals("m-7", result.data.matchId)
    }
}

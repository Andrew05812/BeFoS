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
 * Whom the account passed, and the one verb that takes that answer back, seen from the client's side
 * of the wire.
 *
 * The read is pinned first as a shape, the inbox above it was: a GET that carries nothing but the
 * session. A list of people this account dismissed, built from an id the client passes, is a door into
 * somebody else's answers, so the bearer token has to be the only thing naming the list. Then the rows
 * themselves, because a pass row has no percent to carry — it records an absence, and the only facts on
 * it are who the person was and when the card was swiped past.
 *
 * The release is the third thing, and its shape is the bargain: DELETE on the pass the account wrote,
 * answering with the page that survives rather than with a boolean. A client that subtracted the tapped
 * row locally would be guessing what the server holds; the write returns the list, so the screen paints
 * the server's own answer.
 */
class PassedUsersReadTest {

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
    fun `the list of passes is read with the session and nothing that names an account`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """
                {"passed":[{"user_id":"b","name":"Борис","age":31,"city":"Казань","photo_url":null,"passed_at":"2026-10-19T06:00:00+00:00"}],"has_more":false}
            """.trimIndent(),
        )

        val result = ApiService(client).passedUsers()
        client.close()

        assertEquals("GET", seen[0].method)
        assertEquals("/api/v1/discover/passed", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
        // Whose list this is comes from the token alone: nothing in the URL, nothing in a body.
        assertEquals(1, seen.size)

        val page = (result as ApiResult.Success).data
        assertEquals(listOf("b"), page.passed.map { it.userId })
        assertEquals("Борис", page.passed[0].name)
        assertEquals(31, page.passed[0].age)
        assertEquals("Казань", page.passed[0].city)
        assertEquals("2026-10-19T06:00:00+00:00", page.passed[0].passedAt)
        assertEquals(false, page.hasMore)
    }

    @Test
    fun `a pass row arrives with the person and the day, and nothing else invented`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, _) = clientAnswering(
            session,
            body = """
                {"passed":[
                  {"user_id":"a","name":"Анна","age":29,"city":"Москва","photo_url":"/uploads/a.png","passed_at":"2026-10-19T06:00:00+00:00"},
                  {"user_id":"b","name":"Борис","age":31,"city":"Казань","passed_at":"2026-10-18T06:00:00+00:00"},
                  {"user_id":"c","name":"Вера","age":27,"city":"Тверь","photo_url":"https://cdn.example.com/c.png","passed_at":""}
                ],"has_more":true}
            """.trimIndent(),
        )

        // Read through the repository: the screen's rows are the domain's, and the mapper is where a
        // relative photo path becomes a loadable url.
        val page = (DiscoveryRepositoryImpl(ApiService(client)).passed() as ApiResult.Success).data
        client.close()

        assertEquals(3, page.passed.size)
        assertEquals(true, page.truncated)
        assertTrue(page.passed[0].photoUrl!!, page.passed[0].photoUrl!!.endsWith("/uploads/a.png"))
        assertNull(page.passed[1].photoUrl)
        assertEquals("https://cdn.example.com/c.png", page.passed[2].photoUrl)
        // A row whose moment the server did not write arrives as no moment, not as a date to print. The
        // field has no null on this side by design: the screen's own line drops it rather than guessing.
        assertEquals("", page.passed[2].passedAt)
        assertEquals("2026-10-19T06:00:00+00:00", page.passed[0].passedAt)
    }

    @Test
    fun `a page that stopped at fifty reaches the screen as a page that stopped`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val rows = (1..50).joinToString(",") {
            """{"user_id":"u$it","name":"Анкета $it","age":25,"city":"Москва","photo_url":null,"passed_at":"2026-10-19T06:00:00+00:00"}"""
        }
        val (client, _) = clientAnswering(
            session,
            body = """{"passed":[$rows],"has_more":true}""",
        )

        val page = (DiscoveryRepositoryImpl(ApiService(client)).passed() as ApiResult.Success).data
        client.close()

        // The server shows fifty rows and names no cursor, so the flag is the only thing that separates
        // a complete list from a cut one — and the screen has to say which it is holding.
        assertEquals(50, page.passed.size)
        assertEquals(true, page.truncated)
    }

    @Test
    fun `taking a pass back deletes the account's own answer and answers with the list that survives`() =
        runBlocking {
            val session = FakeSession().apply { login("token-alice", "alice") }
            val (client, seen) = clientAnswering(
                session,
                body = """
                    {"passed":[{"user_id":"a","name":"Анна","age":29,"city":"Москва","photo_url":null,"passed_at":"2026-10-19T06:00:00+00:00"}],"has_more":false}
                """.trimIndent(),
            )

            val page = (DiscoveryRepositoryImpl(ApiService(client)).unpass("b") as ApiResult.Success).data
            client.close()

            // DELETE on the pass, named by the person it was about: the same door the deck's swipe wrote
            // through, opened the other way rather than a second write path for one gesture.
            assertEquals("DELETE", seen[0].method)
            assertEquals("/api/v1/users/b/pass", seen[0].path)
            assertEquals("Bearer token-alice", seen[0].bearer)
            // One request, and its answer is the page: the release does not pay for a second read to
            // learn what the write already said.
            assertEquals(1, seen.size)

            assertEquals(listOf("a"), page.passed.map { it.userId })
            assertEquals(false, page.truncated)
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

        val error = ApiService(client).passedUsers() as ApiResult.Error
        client.close()

        assertEquals(429, error.code)
        // The English contract sentence must not reach the screen.
        assertEquals("Слишком много запросов. Подождите немного.", error.message)
    }

    @Test
    fun `a release the server does not hold is said as the list having changed`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val client = createHttpClient(
            session,
            MockEngine {
                envelope(
                    HttpStatusCode.NotFound,
                    "not_found",
                    "You have not passed this user.",
                )
            },
        )

        val error = ApiService(client).unpass("b") as ApiResult.Error
        client.close()

        assertEquals(404, error.code)
        // The same 404 answers an id this account never passed, so the words cannot claim the person was
        // ever here; they send the reader back to the list, the way the unblock refusal does.
        assertEquals("Вы этого человека не пропускали. Обновите список.", error.message)
    }
}

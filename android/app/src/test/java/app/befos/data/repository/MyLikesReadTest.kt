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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Whom the account tapped, and the one verb that takes that tap back, seen from the client's side of
 * the wire.
 *
 * The read is pinned first as a shape, the way the inbox and the pass list were: a GET that carries
 * nothing but the session. A list of people this account liked, built from an id the client passes, is
 * a door into somebody else's hearts, so the bearer token has to be the only thing naming the list.
 * Then the rows themselves, because a tap row is the one list in this app that carries a number it must
 * not recompute — the percent is the reason the tap happened, and a client that derived a fresh one
 * would answer the account's own history with a number that was never anybody's reason.
 *
 * The withdrawal is the third thing, and its shape is the bargain the release of a pass struck: DELETE
 * on the like the account wrote, answering with the page that survives rather than with a boolean. A
 * client that subtracted the tapped row locally would be guessing what the server holds.
 *
 * The fourth is the walk, and it is what stage 123 changed on this side of the wire: the first page is
 * asked for with no query at all, every page after it is asked for by the key the previous answer
 * handed out, and the key is carried whole rather than rebuilt. The screen's «Показать ещё» and its
 * arrival at the end of the list both read that field, so a mapper that dropped it would leave a page
 * that says more exists and cannot reach it — the exact hole this door had until the cursor came.
 */
class MyLikesReadTest {

    private class Record(
        val method: String,
        val path: String,
        val bearer: String?,
        val query: String? = null,
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
                query = request.url.encodedQuery.takeIf { it.isNotEmpty() },
            )
            respond(body, status, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))
        }),
        seen,
    )

    @Test
    fun `the list of taps is read with the session and nothing that names an account`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """
                {"likes":[{"user_id":"b","name":"Борис","age":31,"city":"Казань","photo_url":null,"compatibility":74,"liked_at":"2026-10-19T06:00:00+00:00"}],"has_more":false}
            """.trimIndent(),
        )

        val result = ApiService(client).likedUsers()
        client.close()

        assertEquals("GET", seen[0].method)
        assertEquals("/api/v1/discover/liked", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
        // Whose list this is comes from the token alone: nothing in the URL, nothing in a body. The path
        // differs from the inbox by one word, which is exactly how far apart the two directions are.
        // And the first page asks with no query at all — a client that sent `cursor=` would be teaching
        // the server a shape its own decoder says means «from the newest tap».
        assertNull(seen[0].query)
        assertEquals(1, seen.size)

        val page = (result as ApiResult.Success).data
        assertEquals(listOf("b"), page.likes.map { it.userId })
        assertEquals("Борис", page.likes[0].name)
        assertEquals(31, page.likes[0].age)
        assertEquals("Казань", page.likes[0].city)
        assertEquals(74, page.likes[0].compatibility)
        assertEquals("2026-10-19T06:00:00+00:00", page.likes[0].likedAt)
        assertEquals(false, page.hasMore)
        // A body that names no cursor reads as no cursor, not as an empty one: the screen decides whether
        // to offer «Показать ещё» by this field being absent.
        assertNull(page.nextCursor)
    }

    @Test
    fun `the page behind the first one is asked for by the link the server handed out`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """
                {"likes":[{"user_id":"c","name":"Вера","age":27,"city":"Тверь","photo_url":null,"compatibility":55,"liked_at":"2026-10-17T06:00:00+00:00"}],"has_more":false,"next_cursor":null}
            """.trimIndent(),
        )

        val page = (ApiService(client).likedUsers(cursor = "dGFwOjE3OTI1NDQwMDAwMDAwMDA6YWJj") as ApiResult.Success).data
        client.close()

        assertEquals("GET", seen[0].method)
        assertEquals("/api/v1/discover/liked", seen[0].path)
        // The only thing the client adds between one page and the next is the key, carried whole: a
        // device that rebuilt it from the row's timestamp would be guessing at the server's ordering.
        assertEquals("cursor=dGFwOjE3OTI1NDQwMDAwMDAwMDA6YWJj", seen[0].query)
        assertEquals("Bearer token-alice", seen[0].bearer)
        assertEquals(listOf("c"), page.likes.map { it.userId })
        assertFalse(page.hasMore)
        assertNull(page.nextCursor)
    }

    @Test
    fun `a tap row keeps the percent its card carried and says nothing when none was written`() =
        runBlocking {
            val session = FakeSession().apply { login("token-alice", "alice") }
            val (client, _) = clientAnswering(
                session,
                body = """
                    {"likes":[
                      {"user_id":"a","name":"Анна","age":29,"city":"Москва","photo_url":"/uploads/a.png","compatibility":91,"liked_at":"2026-10-19T06:00:00+00:00"},
                      {"user_id":"b","name":"Борис","age":31,"city":"Казань","compatibility":null,"liked_at":"2026-10-18T06:00:00+00:00"},
                      {"user_id":"c","name":"Вера","age":27,"city":"Тверь","photo_url":"https://cdn.example.com/c.png","liked_at":""}
                    ],"has_more":true}
                """.trimIndent(),
            )

            // Read through the repository: the screen's rows are the domain's, and the mapper is where a
            // relative photo path becomes a loadable url.
            val page = (DiscoveryRepositoryImpl(ApiService(client)).liked() as ApiResult.Success).data
            client.close()

            assertEquals(3, page.likes.size)
            assertEquals(true, page.truncated)
            assertTrue(page.likes[0].photoUrl!!, page.likes[0].photoUrl!!.endsWith("/uploads/a.png"))
            assertNull(page.likes[1].photoUrl)
            assertEquals("https://cdn.example.com/c.png", page.likes[2].photoUrl)
            // The percent arrives as the row wrote it: 91 stays 91, an explicit null stays no number, and
            // a field the server left out stays no number rather than the zero the account never saw.
            assertEquals(91, page.likes[0].compatibility)
            assertNull(page.likes[1].compatibility)
            assertNull(page.likes[2].compatibility)
            assertEquals("", page.likes[2].likedAt)
            assertEquals("2026-10-19T06:00:00+00:00", page.likes[0].likedAt)
        }

    @Test
    fun `a page that stopped at fifty arrives with the link that goes past it`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val rows = (1..50).joinToString(",") {
            """{"user_id":"u$it","name":"Анкета $it","age":25,"city":"Москва","photo_url":null,"compatibility":60,"liked_at":"2026-10-19T06:00:00+00:00"}"""
        }
        val (client, _) = clientAnswering(
            session,
            body = """{"likes":[$rows],"has_more":true,"next_cursor":"dGFwOjE3OTI1NDQwMDAwMDAwMDA6YWJj"}""",
        )

        val page = (DiscoveryRepositoryImpl(ApiService(client)).liked() as ApiResult.Success).data
        client.close()

        // The flag says the list is longer than what is here, and the key is what makes that survivable:
        // a screen that shows both and holds neither has the same hole stage 116 shipped with.
        assertEquals(50, page.likes.size)
        assertEquals(true, page.truncated)
        assertEquals("dGFwOjE3OTI1NDQwMDAwMDAwMDA6YWJj", page.nextCursor)
    }

    @Test
    fun `taking a tap back deletes the account's own row and answers with the list that survives`() =
        runBlocking {
            val session = FakeSession().apply { login("token-alice", "alice") }
            val (client, seen) = clientAnswering(
                session,
                body = """
                    {"likes":[{"user_id":"a","name":"Анна","age":29,"city":"Москва","photo_url":null,"compatibility":62,"liked_at":"2026-10-19T06:00:00+00:00"}],"has_more":true,"next_cursor":"dGFwOnR3bw"}
                """.trimIndent(),
            )

            val page = (DiscoveryRepositoryImpl(ApiService(client)).unlike("b") as ApiResult.Success).data
            client.close()

            // DELETE on the like, named by the person it was about: the same door the deck's heart wrote
            // through, opened the other way rather than a second write path for one gesture.
            assertEquals("DELETE", seen[0].method)
            assertEquals("/api/v1/users/b/like", seen[0].path)
            assertEquals("Bearer token-alice", seen[0].bearer)
            // One request, and its answer is the page: the withdrawal does not pay for a second read to
            // learn what the write already said.
            assertEquals(1, seen.size)

            assertEquals(listOf("a"), page.likes.map { it.userId })
            assertEquals(true, page.truncated)
            // The page a write answers with has to be turnable: a row that left through the top of the
            // list would otherwise strand the screen at fifty with the walk it had just been on gone.
            assertEquals("dGFwOnR3bw", page.nextCursor)
            assertEquals(62, page.likes[0].compatibility)
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

        val error = ApiService(client).likedUsers() as ApiResult.Error
        client.close()

        assertEquals(429, error.code)
        // The English contract sentence must not reach the screen.
        assertEquals("Слишком много запросов. Подождите немного.", error.message)
    }

    @Test
    fun `a withdrawal the server does not hold is said as the list having changed`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val client = createHttpClient(
            session,
            MockEngine {
                envelope(
                    HttpStatusCode.NotFound,
                    "not_found",
                    "You have not liked this user.",
                )
            },
        )

        val error = ApiService(client).unlike("b") as ApiResult.Error
        client.close()

        assertEquals(404, error.code)
        // The same 404 answers an id this account never tapped, so the words cannot claim the person was
        // ever here; they send the reader back to the list, the way the release of a pass does.
        assertEquals("Вы этого человека не лайкали. Обновите список.", error.message)
    }

    @Test
    fun `the two directions of the tap have two paths and one row shape`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """{"likes":[],"has_more":false}""",
        )

        ApiService(client).likedMe()
        ApiService(client).likedUsers()
        client.close()

        // «Кого вы лайкнули» and «Кто вас лайкнул» are one table read two ways, so the client must not be
        // able to confuse them: two paths, neither of them the other's, and no identifier on either.
        assertEquals(
            listOf("/api/v1/discover/liked-me", "/api/v1/discover/liked"),
            seen.map { it.path },
        )
        assertEquals(listOf("GET", "GET"), seen.map { it.method })
    }
}

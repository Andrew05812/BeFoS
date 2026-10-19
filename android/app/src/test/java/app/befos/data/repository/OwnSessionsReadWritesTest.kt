package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.SessionTokens
import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import app.befos.core.network.befosUserAgent
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The account's own devices, seen from the client's side of the wire.
 *
 * Three doors are pinned here, and the shape of each is the part a screen cannot repair later. The read
 * is a GET with nothing in it but the session: a list built from an id the client passes is a door into
 * somebody else's sessions, so the bearer token has to be the only thing naming an account. The two
 * writes are POSTs to paths that carry the row's identity in the URL, and both answer 204 — a client
 * that expected a body would report a failure on a request the server completed.
 *
 * The parsing is pinned with it, because the screen draws its rows out of these fields. The device
 * string arrives exactly as the server stored it, which is what the person has to recognise; a blank
 * one arrives as nothing rather than as an invented name. `has_more` survives the mapper: a list that
 * ran out is a different answer from a list of one, and the first row the client silently drops is the
 * stranger's device.
 *
 * What a session costs the device is the third thing. Ending another row leaves this device signed in;
 * ending every row takes its tokens with it, because the row the request stands on is among those the
 * write ends and the answer carries no fresh pair.
 */
class OwnSessionsReadWritesTest {

    private class Record(
        val method: String,
        val path: String,
        val bearer: String?,
        val agent: String?,
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
                agent = request.headers[HttpHeaders.UserAgent],
            )
            respond(body, status, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))
        }),
        seen,
    )

    @Test
    fun `the list is read with the session and nothing that names an account`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(
            session,
            body = """
                {"sessions":[{"id":"s-1","device":"Pixel 7, Android 14","signed_in_at":"2026-10-18T20:00:00+00:00","expires_at":"2026-11-17T20:00:00+00:00","current":true}],"has_more":false}
            """.trimIndent(),
        )

        val result = ApiService(client).sessions()
        client.close()

        assertEquals("GET", seen[0].method)
        assertEquals("/api/v1/auth/sessions", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
        // The account is named by the token alone. Nothing in the URL, and nothing in a body a GET
        // would not carry anyway.
        assertEquals(1, seen.size)

        val page = (result as ApiResult.Success).data
        assertEquals(listOf("s-1"), page.sessions.map { it.id })
        assertEquals("Pixel 7, Android 14", page.sessions[0].device)
        assertEquals(true, page.sessions[0].current)
        assertEquals(false, page.hasMore)
    }

    @Test
    fun `the words the server says about a row arrive in the screen's own fields`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, _) = clientAnswering(
            session,
            body = """
                {"sessions":[
                  {"id":"s-1","device":"SM-A525F","signed_in_at":"2026-10-19T07:00:00+00:00","expires_at":"2026-11-18T07:00:00+00:00","current":false},
                  {"id":"s-2","device":null,"signed_in_at":"","expires_at":"","current":false},
                  {"id":"s-3","device":"   ","signed_in_at":"","expires_at":"","current":false}
                ],"has_more":true}
            """.trimIndent(),
        )

        // Read through the repository, because the screen's rows are the domain's: the mapper is where a
        // whitespace-only device string stops being a name.
        val page = (AuthRepositoryImpl(ApiService(client), mockk(relaxed = true)).sessions()
            as ApiResult.Success).data
        client.close()

        assertEquals(3, page.sessions.size)
        assertEquals(true, page.hasMore)
        // The string the device sent is the person's own to recognise, so the client does not rewrite
        // it — and a row that said nothing stays nameless rather than being given a brand.
        assertEquals("SM-A525F", page.sessions[0].device)
        assertEquals(null, page.sessions[1].device)
        assertEquals(null, page.sessions[2].device)
        // Neither row is marked as this one: the badge comes from the server's claim about the token,
        // never from the newest row.
        assertEquals(listOf(false, false, false), page.sessions.map { it.current })
        assertEquals("", page.sessions[1].signedInAt)
    }

    @Test
    fun `a row is ended through the door that carries its own id`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(session, HttpStatusCode.NoContent)

        val result = ApiService(client).revokeSession("s-9")
        client.close()

        assertEquals(ApiResult.Success(Unit), result)
        assertEquals("POST", seen[0].method)
        assertEquals("/api/v1/auth/sessions/s-9/revoke", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
    }

    @Test
    fun `every session ends through one door that names no row`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(session, HttpStatusCode.NoContent)

        val result = ApiService(client).revokeAllSessions()
        client.close()

        assertEquals(ApiResult.Success(Unit), result)
        assertEquals("POST", seen[0].method)
        assertEquals("/api/v1/auth/sessions/revoke-all", seen[0].path)
    }

    @Test
    fun `the refusal of a row the server does not hold reaches the person in Russian`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val client = createHttpClient(
            session,
            MockEngine {
                envelope(
                    HttpStatusCode.NotFound,
                    "not_found",
                    "No live session with this id for this account.",
                )
            },
        )

        val error = ApiService(client).revokeSession("s-gone") as ApiResult.Error
        client.close()

        assertEquals(404, error.code)
        // The English contract sentence must not reach the screen, and the advice has to be the one the
        // row can actually take: read the list again, since its own line just changed under the tap.
        assertEquals("Этой сессии уже нет. Обновите список устройств.", error.message)
    }

    @Test
    fun `ending another device leaves this one signed in`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        coEvery { api.revokeSession("s-other") } returns ApiResult.Success(Unit)

        val result = AuthRepositoryImpl(api, store).endSession("s-other")

        assertEquals(ApiResult.Success(Unit), result)
        // The 204 says nothing about which row it cut, and the repository has no way to know that the
        // one it cut was this device's — clearing here would be a guess that logs a person out.
        coVerify(exactly = 0) { store.clear() }
    }

    @Test
    fun `ending every device takes this one with it`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        coEvery { api.revokeAllSessions() } returns ApiResult.Success(Unit)

        val result = AuthRepositoryImpl(api, store).endEverySession()

        assertEquals(ApiResult.Success(Unit), result)
        coVerify(exactly = 1) { store.clear() }
    }

    @Test
    fun `a refused sweep leaves the stored session exactly where it was`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        coEvery { api.revokeAllSessions() } returns ApiResult.Error(401, "Сессия истекла. Войдите снова.")

        val result = AuthRepositoryImpl(api, store).endEverySession()

        assertEquals(401, (result as ApiResult.Error).code)
        coVerify(exactly = 0) { store.clear() }
    }

    @Test
    fun `the device says what it is instead of arriving as the library's own name`() {
        // Every install used to arrive as `ktor-client`, which is the engine's fingerprint rather than a
        // device: three phones of one account read as three identical lines, and the person cannot tell
        // which one to cut off.
        assertEquals(
            "BeFoS/1.0.0 (Pixel 7, Android 14)",
            befosUserAgent("1.0.0", "Pixel 7", "14"),
        )
        // A build that has no version of its own still names the platform it runs on.
        assertEquals("BeFoS/dev (Nexus 5, Android 6.0.1)", befosUserAgent("", "Nexus 5", "6.0.1"))
        // A device that reports nothing is not a crash on the way out — every request runs through
        // here, and a JVM unit test reads these fields as null.
        assertEquals("BeFoS/1.0.0 (Android)", befosUserAgent("1.0.0", null, null))
        assertEquals("BeFoS/1.0.0 (Android)", befosUserAgent("1.0.0", "  ", "  "))
        // A header line is ASCII, and the string is built word by word: a model written in another
        // script drops out and the line stays well-formed, rather than leaving the parenthetical with
        // a half-word or a dangling comma the person reads as a broken name.
        assertEquals("BeFoS/1.0.0 (Android 11)", befosUserAgent("1.0.0", "смартфон", "11"))
        assertFalse(befosUserAgent("1.0.0", "SM-A525F", "11").contains(", ,"))
    }

    @Test
    fun `the header that leaves the device is the one the account will read back`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(session, HttpStatusCode.NoContent)

        ApiService(client).revokeSession("s-1")
        client.close()

        // The stored string is what the list of devices is built out of, so the client's own header has
        // to be on the wire — not the engine's default. On the JVM the device fields read null, which is
        // exactly the case that must still produce a usable line rather than no header at all.
        val agent = seen[0].agent
        assertTrue("actual: $agent", agent != null && agent.startsWith("BeFoS/"))
        assertTrue("actual: $agent", agent!!.contains("(Android)"))
    }
}

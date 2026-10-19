package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.SessionTokens
import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What the password door looks like from the client's side of the wire, and what a device keeps after
 * the server says the word changed.
 *
 * Three things are worth pinning here rather than trusting the route's existence. The body has to
 * carry the three keys the backend declares — a renamed key is not a refusal the person can read, it
 * is a 422 about a field they never touched. The write has to go out authenticated, because this door
 * names no account in its body and the bearer token is the only thing saying whose word is being
 * replaced. And the answer is a 204 with no body: the client that asked is holding a session the same
 * write ended, so the repository must not leave a token pair in storage that can no longer be
 * refreshed.
 *
 * The two refusals the door can give are pinned too, because the person has to be told which one they
 * met. The server's English contract text never reaches the screen; the auth wording for both was
 * already in the client's translation table before this stage opened the door.
 */
class PasswordRotationWritesTest {

    private class Record(
        val method: String,
        val path: String,
        val bearer: String?,
        val body: String,
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

    @Test
    fun `the door is written to with the session and the three words the server asks for`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val seen = mutableListOf<Record>()
        val client = createHttpClient(
            session,
            MockEngine { request ->
                seen += Record(
                    method = request.method.value,
                    path = request.url.encodedPath,
                    bearer = request.headers[HttpHeaders.Authorization],
                    body = (request.body as? TextContent)?.text.orEmpty(),
                )
                respond("", HttpStatusCode.NoContent)
            },
        )

        val result = ApiService(client).changePassword("OldWord123", "NewWord123", "NewWord123")
        client.close()

        assertEquals(ApiResult.Success(Unit), result)
        assertEquals(1, seen.size)
        assertEquals("POST", seen[0].method)
        assertEquals("/api/v1/auth/change-password", seen[0].path)
        // Unlike the refresh door, this one goes out authenticated: the account it can reach is the
        // one the bearer token names, and nothing in the body carries a user id to try.
        assertEquals("Bearer token-alice", seen[0].bearer)

        // The three names the backend's schema declares, and no fourth. The order they arrive in is
        // the serialiser's own and carries no meaning on the wire, so the set is what gets held: a
        // renamed or dropped key is the failure a person cannot read, because the 422 names a field
        // they never touched.
        assertEquals(
            setOf("old_password", "new_password", "password_confirm"),
            Regex("\"([a-z_]+)\":").findAll(seen[0].body).map { it.groupValues[1] }.toSet(),
        )
        assertTrue(seen[0].body, seen[0].body.contains("\"old_password\":\"OldWord123\""))
        assertTrue(seen[0].body, seen[0].body.contains("\"new_password\":\"NewWord123\""))
        assertTrue(seen[0].body, seen[0].body.contains("\"password_confirm\":\"NewWord123\""))
    }

    @Test
    fun `a wrong old word is refused in the product's own words and says nothing about the new one`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val client = createHttpClient(
            session,
            MockEngine {
                envelope(HttpStatusCode.Unauthorized, "unauthorized", "Current password is incorrect.")
            },
        )

        val result = ApiService(client).changePassword("NotTheirWord1", "NewWord123", "NewWord123")
        client.close()

        val error = result as ApiResult.Error
        assertEquals(401, error.code)
        assertEquals("Текущий пароль указан неверно.", error.message)
    }

    @Test
    fun `the ceiling the auth doors share is named rather than swallowed`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val client = createHttpClient(
            session,
            MockEngine { envelope(HttpStatusCode.TooManyRequests, "rate_limited", "") },
        )

        val result = ApiService(client).changePassword("OldWord123", "NewWord123", "NewWord123")
        client.close()

        // The door inherits the 20-a-minute auth window, so a person who taps retry inside it meets a
        // refusal that has to say so — otherwise the screen reads as a broken password.
        val error = result as ApiResult.Error
        assertEquals(429, error.code)
        assertEquals("Слишком много запросов. Подождите немного.", error.message)
    }

    @Test
    fun `an accepted rotation takes the stored session with it`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        coEvery { api.changePassword(any(), any(), any()) } returns ApiResult.Success(Unit)

        val result = AuthRepositoryImpl(api, store).changePassword("OldWord123", "NewWord123", "NewWord123")

        assertEquals(ApiResult.Success(Unit), result)
        coVerify(exactly = 1) { store.clear() }
    }

    @Test
    fun `a refused rotation leaves the stored session exactly where it was`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        coEvery { api.changePassword(any(), any(), any()) } returns
            ApiResult.Error(401, "Текущий пароль указан неверно.")

        val result = AuthRepositoryImpl(api, store).changePassword("NotTheirWord1", "NewWord123", "NewWord123")

        assertEquals(401, (result as ApiResult.Error).code)
        // The server changed nothing about the account when it refused, so the device may not either:
        // a person who mistypes their old word stays signed in on this phone and on every other one.
        coVerify(exactly = 0) { store.clear() }
    }
}

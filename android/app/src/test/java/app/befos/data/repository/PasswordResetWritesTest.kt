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
import io.mockk.slot
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The recovery doors seen from the client's side of the wire.
 *
 * Three claims are worth testing rather than trusting, and each is the kind that fails silently.
 *
 * The first is that both doors go out **without** a bearer token even when this device is signed in
 * as somebody else. `core/network/HttpClientFactory.kt` keeps a list of session-less auth routes,
 * and a door missing from that list still works — it simply carries a token the server does not ask
 * for, and the failure that follows is a refresh attempt on a 401 in the middle of a lockout.
 *
 * The second is the body key set. A renamed key is not a refusal a person can read: the backend
 * answers 422 about a field nobody touched, and the screen repeats it as «проверьте введённые
 * данные». Order carries no meaning on the wire, so the set is what is held.
 *
 * The third is that the server's one merged refusal for a code — never existed, already used, too
 * late — arrives in the product's own words. It reaches this file as an English contract sentence
 * and leaves as Russian copy, which is the only way to notice that the translation table has no
 * entry for it and would answer «Сессия истекла. Войдите снова.» on a screen that is already
 * outside the account.
 */
class PasswordResetWritesTest {

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
    fun `the letter is asked for without a session, and the answer is read as a window`() = runBlocking {
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
                respond(
                    """{"accepted":true,"expires_in_seconds":1800}""",
                    HttpStatusCode.Accepted,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
            },
        )

        val result = ApiService(client).requestPasswordReset("person@example.test")
        client.close()

        assertEquals(1, seen.size)
        assertEquals("POST", seen[0].method)
        assertEquals("/api/v1/auth/password-reset/request", seen[0].path)
        // The door a locked-out person stands in front of cannot require a session, and this device
        // is signed in as somebody else while testing it: a bearer stamped here would be a claim
        // about an account the request never named.
        assertNull("the request door carried a bearer: ${seen[0].bearer}", seen[0].bearer)
        assertEquals(setOf("email"), Regex("\"([a-z_]+)\":").findAll(seen[0].body).map { it.groupValues[1] }.toSet())
        assertTrue(seen[0].body, seen[0].body.contains("\"email\":\"person@example.test\""))

        val data = (result as ApiResult.Success).data
        assertEquals(true, data.accepted)
        assertEquals(1800, data.expiresInSeconds)
    }

    @Test
    fun `the code is spent without a session and the empty answer is not a decode failure`() = runBlocking {
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

        val result = ApiService(client)
            .confirmPasswordReset("ABCD-EFGH-JKLM", "BrandNewWord9", "BrandNewWord9")
        client.close()

        assertEquals(ApiResult.Success(Unit), result)
        assertEquals("/api/v1/auth/password-reset/confirm", seen[0].path)
        assertNull("the confirm door carried a bearer: ${seen[0].bearer}", seen[0].bearer)
        assertEquals(
            setOf("code", "new_password", "password_confirm"),
            Regex("\"([a-z_]+)\":").findAll(seen[0].body).map { it.groupValues[1] }.toSet(),
        )
    }

    @Test
    fun `the one refusal of a code arrives in the product's own words`() = runBlocking {
        val session = FakeSession()
        val client = createHttpClient(
            session,
            MockEngine {
                envelope(
                    HttpStatusCode.Unauthorized,
                    "unauthorized",
                    "The code did not work. Ask for a new letter.",
                )
            },
        )

        val result = ApiService(client).confirmPasswordReset("ABCD-EFGH-JKLM", "BrandNewWord9", "BrandNewWord9")
        client.close()

        val error = result as ApiResult.Error
        assertEquals(401, error.code)
        // Not «Сессия истекла. Войдите снова.»: that sentence belongs to a device that was signed in
        // and lost it, and this person was never inside the account. The fallback for an unknown code
        // would have said exactly that, which is how this line came to be pinned here.
        assertEquals("Код не подошёл. Запросите новое письмо.", error.message)
    }

    @Test
    fun `an accepted code takes the stored session with it`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        coEvery { api.confirmPasswordReset(any(), any(), any()) } returns ApiResult.Success(Unit)

        val result = AuthRepositoryImpl(api, store)
            .confirmPasswordReset("ABCD-EFGH-JKLM", "BrandNewWord9", "BrandNewWord9")

        assertEquals(ApiResult.Success(Unit), result)
        coVerify(exactly = 1) { store.clear() }
    }

    @Test
    fun `a refused code leaves the stored session alone`() = runBlocking {
        val api: ApiService = mockk()
        val store: TokenStore = mockk(relaxed = true)
        val email = slot<String>()
        coEvery { api.requestPasswordReset(capture(email)) } returns
            ApiResult.Success(app.befos.data.model.PasswordResetAcceptedDto(true, 1800))
        coEvery { api.confirmPasswordReset(any(), any(), any()) } returns
            ApiResult.Error(401, "Код не подошёл. Запросите новое письмо.")

        val repository = AuthRepositoryImpl(api, store)
        repository.requestPasswordReset("person@example.test")
        val result = repository.confirmPasswordReset("ABCD-EFGH-JKLM", "BrandNewWord9", "BrandNewWord9")

        assertEquals("person@example.test", email.captured)
        assertTrue(result is ApiResult.Error)
        coVerify(exactly = 0) { store.clear() }
    }
}

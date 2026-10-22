package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.SessionTokens
import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import app.befos.domain.model.AccountExport
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The account's own file, seen from the client's side of the wire (stage 121).
 *
 * One door is pinned here, and it is the only door through which this product hands a person their own
 * rows: `GET /api/v1/users/me/export` answers with the whole document as bytes, and everything the
 * screen later says about that file — how many rows it carries, which sections were cut, whether the
 * account holds anything at all — is read out of those bytes. Two properties are therefore worth
 * pinning on the client.
 *
 * The first is that the request names no account. The bearer token is the only thing that says whose
 * rows were gathered; a path that took a user id would be a door into somebody else's file, and the
 * client must not be the thing that opens it.
 *
 * The second is that the numbers the card prints are the document's, not the client's guesses. Row
 * counts come from the file's own `counts`, the cut names come from `limits.truncated`, and the size is
 * the length of the payload that actually arrived. A parser that quietly defaulted a missing section to
 * zero would report an empty account out of a file that holds a year of messages.
 *
 * A payload that cannot be read is a failure rather than an empty file, and a refusal stays a refusal
 * even though it arrived with bytes in it: the screen must never offer to save the server's error text
 * as somebody's account.
 */
class AccountExportReadTest {

    private class Record(
        val method: String,
        val path: String,
        val bearer: String?,
    )

    private class FakeSession : SessionTokens {
        private var auth: StoredAuth? = null

        override suspend fun current(): StoredAuth? = auth

        override suspend fun updateTokens(accessToken: String, refreshToken: String) {
            auth = StoredAuth(accessToken, "refresh-$accessToken", auth?.userId ?: "unknown")
        }

        override suspend fun clear() {
            auth = null
        }

        fun login(accessToken: String, userId: String) {
            auth = StoredAuth(accessToken, "refresh-$accessToken", userId)
        }
    }

    /** The thirteen counts the door answers with, in the order the backend writes them. */
    private val lived = listOf(
        "photos" to 1,
        "questionnaire_answers" to 1,
        "questionnaire_categories" to 1,
        "taps_given" to 1,
        "taps_received" to 0,
        "taps_passed" to 1,
        "deck" to 1,
        "pairs" to 1,
        "chats" to 1,
        "plans" to 0,
        "blocks" to 0,
        "complaints" to 1,
        "sessions" to 1,
    )

    private val fresh = lived.map { it.first to 0 }

    /**
     * A document shaped the way the route shapes it: the metadata a reader needs, the counts the card
     * reads, and the ceiling the file carries with itself.
     */
    private fun documentOf(
        counts: List<Pair<String, Int>> = lived,
        truncated: List<String> = emptyList(),
        generatedAt: String = "2026-10-22T15:04:05.123456+00:00",
    ): String = buildString {
        append("{\"format\":\"befos.account-export/1\"")
        append(",\"generated_at\":\"").append(generatedAt).append("\"")
        append(",\"account\":{\"user_id\":\"u-1\",\"email\":\"anna@example.test\"}")
        append(",\"profile\":{\"name\":\"Анна\",\"birth_date\":\"1996-05-10\"}")
        append(",\"chats\":[{\"match_id\":\"m-1\",\"lines\":[{\"id\":\"l-1\",\"recalled\":true}]}]")
        append(",\"counts\":{")
        append(counts.joinToString(",") { "\"${it.first}\":${it.second}" })
        append("},\"limits\":{\"rows_per_section\":500,\"truncated\":[")
        append(truncated.joinToString(",") { "\"$it\"" })
        append("]}}")
    }

    private fun session() = FakeSession().apply { login("token-alice", "alice") }

    private fun clientAnswering(
        status: HttpStatusCode = HttpStatusCode.OK,
        body: String,
        seen: MutableList<Record> = mutableListOf(),
    ): Pair<HttpClient, MutableList<Record>> = Pair(
        createHttpClient(session(), MockEngine { request ->
            seen += Record(
                method = request.method.value,
                path = request.url.encodedPath,
                bearer = request.headers[HttpHeaders.Authorization],
            )
            respond(
                body,
                status,
                Headers.build {
                    append(HttpHeaders.ContentType, ContentType.Application.Json.toString())
                    append(HttpHeaders.ContentDisposition, "attachment; filename=\"befos-account-u-1.json\"")
                },
            )
        }),
        seen,
    )

    @Test
    fun `the file is asked for with the session and nothing that names an account`() = runBlocking {
        val (client, seen) = clientAnswering(body = documentOf())

        val result = ApiService(client).exportAccount()
        client.close()

        assertEquals("GET", seen[0].method)
        assertEquals("/api/v1/users/me/export", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
        // One request for the whole document: the file is not assembled from a page walk the client
        // could half-finish, and a half-gathered export reads exactly like a complete one.
        assertEquals(1, seen.size)
        assertTrue(result is ApiResult.Success<*>)
    }

    @Test
    fun `the rows the card counts are the rows the document counted`() = runBlocking {
        val (client, _) = clientAnswering(body = documentOf())

        val export = (ProfileRepositoryImpl(ApiService(client)).exportAccount() as ApiResult.Success<AccountExport>).data
        client.close()

        assertEquals(13, export.sections.size)
        // Names and numbers arrive in the order the file wrote them, so the card can list them without
        // re-inventing a section order the backend never promised.
        assertEquals(lived, export.sections.map { it.name to it.rows })
        assertEquals(10, export.totalRows)
    }

    @Test
    fun `the size the card prints is the length of the bytes that arrived`() = runBlocking {
        val body = documentOf()
        val (client, _) = clientAnswering(body = body)

        val export = (ProfileRepositoryImpl(ApiService(client)).exportAccount() as ApiResult.Success<AccountExport>).data
        client.close()

        assertEquals(body.toByteArray(Charsets.UTF_8).size, export.sizeBytes)
        assertEquals("2026-10-22T15:04:05.123456+00:00", export.generatedAt)
    }

    @Test
    fun `the name the save dialog suggests carries the day the server wrote, not the account number`() {
        val export = accountExportOf(documentOf().toByteArray(Charsets.UTF_8))

        assertNotNull(export)
        // The header's own name carries the user id, and a file that leaves the phone should not: the
        // day is the part a person recognises as their own, and the server's stamp is the only source.
        assertEquals("befos-account-2026-10-22.json", export!!.fileName)
    }

    @Test
    fun `a stamp the client cannot read leaves the name plain rather than inventing a day`() {
        val export = accountExportOf(documentOf(generatedAt = "вечер зачёта").toByteArray(Charsets.UTF_8))

        assertNotNull(export)
        assertEquals("befos-account.json", export!!.fileName)
    }

    @Test
    fun `a cut section is named by the document rather than noticed by arithmetic`() {
        val export = accountExportOf(
            documentOf(
                counts = lived.map { if (it.first == "chats") it.first to 4000 else it },
                truncated = listOf("chats"),
            ).toByteArray(Charsets.UTF_8),
        )

        assertNotNull(export)
        assertEquals(listOf("chats"), export!!.truncated)
        // The count of a capped section is the number of rows that stand rather than the number the
        // ceiling let through, so the card can say «выгружено не всё» and still name the whole.
        assertEquals(4000, export.sections.first { it.name == "chats" }.rows)
    }

    @Test
    fun `an account with nothing beyond its own setup is named as one`() {
        val export = accountExportOf(documentOf(counts = fresh).toByteArray(Charsets.UTF_8))

        assertNotNull(export)
        assertEquals(true, export!!.isFreshAccount)
        assertEquals(0, export.totalRows)
    }

    @Test
    fun `a file that holds one tap is not named an empty account`() {
        val export = accountExportOf(documentOf().toByteArray(Charsets.UTF_8))

        assertEquals(false, export!!.isFreshAccount)
    }

    @Test
    fun `a device row alone is not activity`() {
        // The account signs in somewhere, so `sessions` is never zero while the file is being read; a
        // card that counted it would call every fresh account a lived one.
        val alone = fresh.map { if (it.first == "sessions") it.first to 1 else it }
        val export = accountExportOf(documentOf(counts = alone).toByteArray(Charsets.UTF_8))

        assertEquals(true, export!!.isFreshAccount)
    }

    @Test
    fun `bytes that are not the document are a failure and not an empty file`() = runBlocking {
        val (client, _) = clientAnswering(body = """{"format":"befos.account-export/1"}""")

        val result = ProfileRepositoryImpl(ApiService(client)).exportAccount()
        client.close()

        // A payload whose `counts` never arrived cannot be reported as «ноль строк»: the screen would
        // offer to save an empty account over a file the client simply did not read.
        assertTrue(result is ApiResult.Error)
        assertEquals(-2, (result as ApiResult.Error).code)
    }

    @Test
    fun `text that is not json at all is a failure rather than a crash`() = runBlocking {
        val (client, _) = clientAnswering(body = "<html>502</html>")

        val result = ProfileRepositoryImpl(ApiService(client)).exportAccount()
        client.close()

        assertTrue(result is ApiResult.Error)
    }

    @Test
    fun `a refusal stays a refusal even though it arrived with bytes in it`() = runBlocking {
        val (client, _) = clientAnswering(
            status = HttpStatusCode.Unauthorized,
            body = """{"error":{"code":"unauthorized","message":"User no longer exists"}}""",
        )

        val result = ApiService(client).exportAccount()
        client.close()

        assertEquals(401, (result as ApiResult.Error).code)
        // Two things a screen cannot repair: the server's English, and a refusal wearing the shape of a
        // file. Either one would be drawn as a document the person could save.
        assertFalse(result.message.contains("User no longer exists"))
        assertFalse(result.message.contains("attachment"))
    }
}

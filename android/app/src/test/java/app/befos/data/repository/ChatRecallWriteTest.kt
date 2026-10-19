package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.SessionTokens
import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import app.befos.domain.repository.ChatEvent
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.http.content.TextContent
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Taking back a typed line, seen from the client's side of the wire.
 *
 * The write is a DELETE whose whole argument is the two ids in its path, and it answers 204. Both
 * shapes are the part a screen cannot repair afterwards: a client that expected a body would report
 * a failure on a request the server completed, and a row named by anything other than its own path
 * would be a door into somebody else's thread. The bearer token is the only thing that says whose
 * line it is, and the server decides from it whether the row belongs to the caller.
 *
 * The refusal is pinned with it, because the route says one sentence for four cases — the partner's
 * line, a page of the pair's plan, a line already taken, an id that never was. None of them may
 * arrive on screen in English, and the pair that no longer exists has to keep its own words: the
 * advice there is to read the list of pairs again, which is not what a person does about a line.
 *
 * The frame is the third thing. The erasure reaches the other device only through the socket, so the
 * frame has to arrive as its own event rather than as an unknown key the parser throws away.
 */
class ChatRecallWriteTest {

    private class Record(
        val method: String,
        val path: String,
        val bearer: String?,
        val textBody: String?,
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

    private fun MockRequestHandleScope.refusal(
        status: HttpStatusCode,
        code: String,
        message: String,
    ) = respond(
        """{"error":{"code":"$code","message":"$message"}}""",
        status,
        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
    )

    /** One client, every request it sends recorded, answering with the given status and body. */
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
                textBody = (request.body as? TextContent)?.text,
            )
            respond(body, status, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))
        }),
        seen,
    )

    @Test
    fun `a line is taken back through the door that names its pair and itself`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, seen) = clientAnswering(session, HttpStatusCode.NoContent)

        val result = ApiService(client).recallMessage("m-1", "s-9")
        client.close()

        assertEquals(ApiResult.Success(Unit), result)
        assertEquals(1, seen.size)
        assertEquals("DELETE", seen[0].method)
        assertEquals("/api/v1/matches/m-1/messages/s-9", seen[0].path)
        assertEquals("Bearer token-alice", seen[0].bearer)
        // The two ids are the whole request. A body here would be a third way to name a row, and the
        // one the server would have to distrust.
        assertEquals(null, seen[0].textBody)
    }

    @Test
    fun `a line the caller does not hold is refused in the screen's own words`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, _) = clientAnswering(
            session,
            HttpStatusCode.NotFound,
            """{"error":{"code":"not_found","message":"Message not found."}}""",
        )

        val error = ApiService(client).recallMessage("m-1", "s-gone") as ApiResult.Error
        client.close()

        assertEquals(404, error.code)
        // Four cases answer with this one sentence, so it must not name a cause the person cannot
        // check — only the thing they can still do about it: nothing, the line is not there to take.
        assertEquals("Эту строку уже нельзя забрать.", error.message)
    }

    @Test
    fun `a pair that is gone keeps its own sentence when the line is erased`() = runBlocking {
        val session = FakeSession().apply { login("token-alice", "alice") }
        val (client, _) = clientAnswering(
            session,
            HttpStatusCode.NotFound,
            """{"error":{"code":"not_found","message":"Match not found."}}""",
        )

        val error = ApiService(client).recallMessage("m-gone", "s-9") as ApiResult.Error
        client.close()

        // One route, two refusals that ask for different acts: the row of the pair is on another
        // screen than the row of the line, and merging their words would send the person back to a
        // list they were never looking at.
        assertEquals("Пара не найдена. Обновите список.", error.message)
    }

    @Test
    fun `the repository hands both ids through in the order the door reads them`() = runBlocking {
        val api: ApiService = mockk()
        coEvery { api.recallMessage("m-7", "s-3") } returns ApiResult.Success(Unit)

        val repo = ChatRepositoryImpl(api, mockk(relaxed = true), mockk(relaxed = true), mockk(relaxed = true))

        assertEquals(ApiResult.Success(Unit), repo.recall("m-7", "s-3"))
        coVerify(exactly = 1) { api.recallMessage("m-7", "s-3") }
    }

    /** A socket that never dials: only the frame reader is being looked at here. */
    private fun parser(userId: String = "alice"): ChatSocket {
        val store: TokenStore = mockk {
            coEvery { current() } returns StoredAuth("token-alice", "refresh", userId)
        }
        return ChatSocket(mockk(relaxed = true), store, "m-1", mockk<CoroutineScope>(relaxed = true))
    }

    @Test
    fun `the frame announcing an erasure arrives as its own event`() = runBlocking {
        val event = parser().parse("""{"type":"message_recalled","match_id":"m-1","message_id":"s-9"}""")

        assertEquals(ChatEvent.Recalled("s-9"), event)
    }

    @Test
    fun `a frame that names no row is still a frame the reader answers`() {
        // A key the server forgot to send is read as an empty id, the way every other field of this
        // parser is read: the alternative is a thrown element, and a dropped frame means a line that
        // stays on screen after the server has erased it.
        runBlocking {
            assertEquals(ChatEvent.Recalled(""), parser().parse("""{"type":"message_recalled"}"""))
        }
    }

    @Test
    fun `an erased line does not come back as a new one`() = runBlocking {
        // The same frame carries no body and no sender, so nothing here can be drawn as a bubble: the
        // event is the id alone, and the thread's own row is what disappears.
        val event = parser().parse(
            """{"type":"message_recalled","match_id":"m-1","message_id":"s-9","sender_id":"bob"}""",
        )

        assertEquals(ChatEvent.Recalled("s-9"), event)
        assertEquals(ChatEvent.Recalled::class, event!!::class)
    }
}

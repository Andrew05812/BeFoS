package app.befos.core.network

import app.befos.data.remote.ApiService
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.HttpTimeoutCapability
import io.ktor.client.plugins.HttpTimeoutConfig
import io.ktor.client.plugins.timeout
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import java.io.InputStream
import java.net.ServerSocket
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Until now the client declared exactly one wait — the connect — and let everything after it fall
 * to a default it never named. Measured on this stack with the shipped client (the JVM probes
 * described in docs/ARCHITECTURE.md, run through `:app:testDebugUnitTest`): a backend that accepts
 * the connection and stays silent was ended at 10 063 ms by OkHttp's inherited ten-second timeout,
 * and the failure text said `socket_timeout=unknown`, so the bound the app's own comment leaned on
 * belonged to the engine and not to the deployment; a response that trickles under that default was
 * not ended at all — it was still being read at 80 034 ms, which holds a screen's spinner open for
 * as long as the connection keeps producing bytes; and a photo upload on a link that drained
 * 2.4 MB in 37 s was ended by the same inherited default at 10 123 ms while bytes were still moving.
 */
class ClientTimeoutBoundsTest {

    private class FakeSession : SessionTokens {
        override suspend fun current(): StoredAuth? = null
        override suspend fun updateTokens(accessToken: String, refreshToken: String) = Unit
        override suspend fun clear() = Unit
    }

    /** Accepts the connection and never answers: a hung backend, or a proxy that lost its upstream. */
    private fun silentServer(): ServerSocket = fakeServer { _, input ->
        while (input.read() != -1) { }
    }

    /** Answers headers at once, then one chunk every 300 ms, forever. */
    private fun tricklingServer(): ServerSocket = fakeServer { socket, input ->
        readHead(input)
        val out = socket.getOutputStream()
        out.write("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n".toByteArray())
        out.flush()
        var tick = 0
        while (true) {
            Thread.sleep(300)
            val payload = """{"tick":$tick}"""
            out.write((payload.toByteArray().size.toString(16) + "\r\n" + payload + "\r\n").toByteArray())
            out.flush()
            tick++
        }
    }

    private fun fakeServer(handler: (java.net.Socket, InputStream) -> Unit): ServerSocket {
        val server = ServerSocket(0, 16, java.net.InetAddress.getByName("127.0.0.1"))
        Thread {
            while (!server.isClosed) {
                val socket = try {
                    server.accept()
                } catch (_: Exception) {
                    break
                }
                Thread {
                    runCatching { handler(socket, socket.getInputStream()) }
                    runCatching { socket.close() }
                }.apply { isDaemon = true }.start()
            }
        }.apply { isDaemon = true }.start()
        return server
    }

    private fun readHead(input: InputStream) {
        val head = StringBuilder()
        while (!head.endsWith("\r\n\r\n")) {
            val one = input.read()
            if (one == -1) return
            head.append(one.toChar())
        }
    }

    @Test
    fun the_silence_bound_is_the_app_s_number_not_the_engine_s() = runBlocking {
        val server = silentServer()
        val started = System.currentTimeMillis()
        val failure = runCatching {
            withTimeout(30_000) {
                val client = createHttpClient(FakeSession())
                client.get("http://127.0.0.1:${server.localPort}/")
            }
        }.exceptionOrNull()
        server.close()
        val elapsed = System.currentTimeMillis() - started

        requireNotNull(failure)
        val text = generateSequence(failure) { it.cause }
            .joinToString(" ") { "${it::class.java.name} ${it.message}" }
        // The declared value has to appear in the failure: `socket_timeout=unknown` is what the
        // inherited default looked like, and while the call died on it no test, no log and no
        // reader could tell which bound ended the call or what to change.
        assertTrue("expected the declared socket bound in: $text", text.contains("socket_timeout=10000"))
        assertTrue("waited $elapsed ms for a bound of 10 s", elapsed in 9_000..14_000)
    }

    @Test
    fun a_response_that_trickles_is_ended_by_the_whole_call_ceiling() = runBlocking {
        val server = tricklingServer()
        val url = "http://127.0.0.1:${server.localPort}/"
        val client = createHttpClient(FakeSession())

        // The ceiling bounds the whole call, so it ends a body whose individual reads never exceed
        // the per-read bound. 1.5 s here is the same knob the shipped client declares at 35 s, and
        // the probe that sized this stage watched that declared ceiling end a slow upload at
        // 35 098 ms while bytes were still moving.
        val cut = runCatching {
            withTimeout(20_000) {
                client.get(url) { timeout { requestTimeoutMillis = 1_500 } }.bodyAsText()
            }
        }.exceptionOrNull()
        assertNotNull(
            "a trickling response was served in full despite the ceiling: ${cut?.message}",
            unwrap(cut),
        )

        // Control on the same server: without the ceiling the very same body keeps arriving, so the
        // cut above came from the ceiling and not from the harness or the fake.
        val control = runCatching {
            withTimeout(6_000) {
                client.get(url) {
                    timeout {
                        requestTimeoutMillis = HttpTimeoutConfig.INFINITE_TIMEOUT_MS
                        socketTimeoutMillis = HttpTimeoutConfig.INFINITE_TIMEOUT_MS
                    }
                }.bodyAsText()
            }
        }.exceptionOrNull()
        server.close()
        client.close()

        // The only thing that stops the control is the harness itself, still waiting on a body that
        // had not failed — which is exactly the shape the shipped client had at 80 034 ms.
        assertEquals(
            "the unbounded control ended in a real failure instead of still waiting: ${control?.message}",
            kotlinx.coroutines.TimeoutCancellationException::class.java,
            control?.javaClass,
        )
    }

    @Test
    fun every_call_carries_the_bounds_the_app_declares_and_the_photo_raises_its_own() = runBlocking {
        val seen = mutableMapOf<String, HttpTimeoutConfig?>()
        val client = createHttpClient(FakeSession(), MockEngine { request ->
            seen[request.url.segments.last()] = request.getCapabilityOrNull(HttpTimeoutCapability)
            json("{}", HttpStatusCode.NotFound)
        })

        val api = ApiService(client)
        api.getTests()
        api.uploadPhoto(ByteArray(1024).inputStream(), "image/jpeg")
        client.close()

        // An ordinary call is bounded by what the client declares, and the numbers a reader sees
        // here are the numbers that ended the calls above. A phase left undeclared arrives as null,
        // which is what let the silent answer be cut by a bound the app never named.
        val tests = seen["tests"]
        assertNotNull("an ordinary call reached the engine with no bounds at all", tests)
        assertBound("a connect bound", 5_000L, tests?.connectTimeoutMillis)
        assertBound("a per-read bound", 10_000L, tests?.socketTimeoutMillis)
        assertBound("a whole-call ceiling", 35_000L, tests?.requestTimeoutMillis)

        // The photo call carries its own raise, because its duration is a property of the uplink:
        // with the client's ceiling it was measured ending at 35 098 ms while 2.4 MB were still
        // moving, and the shipped client killed the same upload at 10 123 ms.
        val photo = seen["photo"]
        assertNotNull("the photo request carries no timeout declaration of its own", photo)
        assertBound("the photo uplink bound", 60_000L, photo?.socketTimeoutMillis)
        assertBound("the photo whole-call ceiling", 600_000L, photo?.requestTimeoutMillis)
    }

    /** Ktor wraps a ceiling cut in its own exception type; find it whatever the engine wrapped. */
    private fun unwrap(error: Throwable?): Throwable? =
        generateSequence(error) { it.cause }
            .firstOrNull { it is HttpRequestTimeoutException || it is java.io.IOException }

    /** A phase the app does not declare arrives as null, which is the engine's default taking over. */
    private fun assertBound(what: String, expected: Long, actual: Long?) {
        assertNotNull("$what is missing, so the engine's unnamed default bounds this call instead", actual)
        assertEquals("$what", expected, actual)
    }

    private fun MockRequestHandleScope.json(
        body: String,
        status: HttpStatusCode,
    ) = respond(body, status, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))
}

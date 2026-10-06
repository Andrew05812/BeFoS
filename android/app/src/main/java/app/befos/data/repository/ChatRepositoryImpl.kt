package app.befos.data.repository

import app.befos.core.network.ApiConfig
import app.befos.core.network.ApiResult
import app.befos.core.network.TokenStore
import app.befos.core.network.befosJson
import app.befos.core.network.defaultHttpMessage
import app.befos.core.network.friendlyNetworkMessage
import app.befos.core.network.localizeBackendError
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.remote.ApiService
import app.befos.domain.model.Message
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.get
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.merge
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * A resilient WebSocket connection to a single match. Incoming frames are
 * published to [events]; outgoing typing is written to the live session.
 *
 * The socket is dialled only while somebody is collecting [events] and is shut down when
 * the last collector goes away. Dialling at construction time instead left one reconnect
 * loop per match the user ever opened running for the life of the process — and after a
 * logout those loops kept probing for an access token that could never return.
 */
class ChatSocket(
    private val client: HttpClient,
    private val tokenStore: TokenStore,
    private val matchId: String,
    private val scope: CoroutineScope,
) {
    private val _events = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 64)

    /**
     * Connection lives in a StateFlow, not in the event stream: a StateFlow re-states the
     * truth to every new collector, so the indicator can only be as wrong as the socket
     * itself, never stuck at whatever was broadcast while the screen was closed.
     */
    private val _connected = MutableStateFlow(false)

    private val collectors = AtomicInteger(0)
    private val lifecycle = Any()

    @Volatile
    private var session: io.ktor.client.plugins.websocket.DefaultClientWebSocketSession? = null

    @Volatile
    private var job: Job? = null

    val events: Flow<ChatEvent> = flow {
        if (collectors.incrementAndGet() == 1) start()
        try {
            emitAll(
                merge(
                    _connected.map { if (it) ChatEvent.Connected else ChatEvent.Disconnected },
                    _events,
                )
            )
        } finally {
            if (collectors.decrementAndGet() == 0) stop()
        }
    }

    private fun start() {
        synchronized(lifecycle) {
            if (job?.isActive != true) job = scope.launch { dialLoop() }
        }
    }

    private fun stop() {
        synchronized(lifecycle) {
            job?.cancel()
            job = null
            session = null
        }
        _connected.value = false
    }

    private suspend fun CoroutineScope.dialLoop() {
        var failures = 0
        var tokenlessStreak = 0
        while (isActive) {
            val token = freshAccessToken()
            if (token == null) {
                // Either signed out or the token store has not answered yet. Both are worth
                // another attempt on the capped schedule, but not forever: a missing token is
                // not a network hiccup a retry can fix. The next collector to arrive starts
                // the loop again from scratch, so ending it costs nothing a real visit cannot
                // undo.
                tokenlessStreak++
                if (!keepDialing(tokenlessStreak)) return
                failures++
                delay(reconnectBackoffMs(failures))
                continue
            }
            tokenlessStreak = 0
            var opened = false
            try {
                client.webSocket(urlString = "${ApiConfig.wsUrl(matchId)}?token=$token") {
                    session = this
                    _connected.value = true
                    opened = true
                    for (frame in incoming) {
                        if (frame is Frame.Text) {
                            parse(frame.readText())?.let { _events.tryEmit(it) }
                        }
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (e: Exception) {
                _events.tryEmit(ChatEvent.Error(socketFailureMessage(e)))
                // An authorization answer is the pair's state, not the network's: no amount of
                // redialling turns a refused handshake into a room.
                if (!retryAfterDialFailure(e)) return
            } finally {
                session = null
                _connected.value = false
            }
            failures = if (opened) 0 else failures + 1
            delay(reconnectBackoffMs(failures))
        }
    }

    /**
     * The socket authorizes via a token query param, which cannot trigger the
     * Ktor refresh flow on 401. A cheap authenticated call rotates an expired
     * access token before the socket dials, avoiding a 403 reconnect loop.
     */
    private suspend fun freshAccessToken(): String? {
        runCatching { client.get(ApiConfig.api("users/me")).body<JsonObject>() }
        return tokenStore.current()?.accessToken
    }

    suspend fun sendTyping(typing: Boolean) {
        val payload = buildJsonObject {
            put("type", "typing")
            put("typing", typing)
        }
        session?.outgoing?.send(Frame.Text(payload.toString()))
    }

    private suspend fun parse(text: String): ChatEvent? {
        val obj = runCatching { befosJson.parseToJsonElement(text) as JsonObject }.getOrNull() ?: return null
        val me = tokenStore.current()?.userId
        return when (obj["type"]?.jsonPrimitive?.content) {
            "message" -> {
                val senderId = obj["sender_id"]?.jsonPrimitive?.content ?: return null
                ChatEvent.IncomingMessage(
                    Message(
                        id = obj["id"]?.jsonPrimitive?.content ?: "",
                        matchId = obj["match_id"]?.jsonPrimitive?.content ?: matchId,
                        senderId = senderId,
                        body = obj["body"]?.jsonPrimitive?.content ?: "",
                        createdAt = obj["created_at"]?.jsonPrimitive?.content ?: "",
                        isRead = obj["is_read"]?.jsonPrimitive?.boolean ?: false,
                        isOwn = senderId == me,
                    ),
                )
            }
            "typing" -> ChatEvent.Typing(
                userId = obj["user_id"]?.jsonPrimitive?.content ?: "",
                typing = obj["typing"]?.jsonPrimitive?.boolean ?: true,
            )
            "read" -> ChatEvent.Read(obj["user_id"]?.jsonPrimitive?.content ?: "")
            "presence" -> ChatEvent.Presence(
                userId = obj["user_id"]?.jsonPrimitive?.content ?: "",
                online = obj["online"]?.jsonPrimitive?.boolean ?: false,
            )
            // A frame error concerns a frame this client sent while the socket was healthy, so
            // it is worded as a refused request, never as a lost connection.
            "error" -> ChatEvent.Error(
                localizeBackendError(obj["message"]?.jsonPrimitive?.content.orEmpty(), "invalid_request", 400),
            )
            else -> null
        }
    }
}

/**
 * The status a websocket handshake was refused with, or null when the dial never got an
 * answer. Measured against the live API with this same Ktor/OkHttp stack: a pair the server
 * will not grant — deleted match, blocked caller, expired session — surfaces as
 * `java.net.ProtocolException: Expected HTTP 101 response but was '403 Forbidden'`. The
 * status survives only inside that English sentence, so it is read out here instead of being
 * handed to the screen as the engine wrote it.
 */
internal fun handshakeStatus(e: Throwable): Int? =
    generateSequence(e) { it.cause }
        .firstNotNullOfOrNull { Regex("was '(\\d{3})").find(it.message.orEmpty())?.groupValues?.get(1)?.toIntOrNull() }

/**
 * Product copy for a dial that failed. A refused handshake answers with the reason the pair
 * is gone, and everything else goes through the same network wording the REST calls use, so
 * no English protocol text reaches the UI from either path.
 */
internal fun socketFailureMessage(e: Throwable): String = when (val status = handshakeStatus(e)) {
    null -> friendlyNetworkMessage(e)
    401 -> "Сессия истекла. Войдите снова."
    403 -> CHAT_CLOSED
    else -> defaultHttpMessage(status)
}

/** Whether the dial loop may pay for another attempt: a server that answered 401 or 403 will answer the same way. */
internal fun retryAfterDialFailure(e: Throwable): Boolean = handshakeStatus(e) !in setOf(401, 403)

private const val CHAT_CLOSED = "Этот чат больше недоступен."

/**
 * A dropped socket that never opened is retried 4, 8, 16 and then 30 s apart rather than
 * every two seconds, so an unreachable backend costs one dial per half minute. A socket
 * that did open restarts the schedule: losing a live connection is worth a fast retry.
 */
internal fun reconnectBackoffMs(failures: Int): Long =
    (BASE_BACKOFF_MS * (1L shl failures.coerceIn(0, 4))).coerceAtMost(MAX_BACKOFF_MS)

/**
 * How many attempts in a row may find no access token before the dial loop ends. The streak
 * resets on any token, so a cold start that reads the store a moment late is not counted
 * against it; six capped attempts span about a minute and a half.
 */
internal fun keepDialing(tokenlessStreak: Int): Boolean = tokenlessStreak < MAX_TOKENLESS_DIALS

private const val BASE_BACKOFF_MS = 2_000L
private const val MAX_BACKOFF_MS = 30_000L
private const val MAX_TOKENLESS_DIALS = 6

class ChatRepositoryImpl(
    private val api: ApiService,
    private val client: HttpClient,
    private val tokenStore: TokenStore,
    private val scope: CoroutineScope,
) : ChatRepository {

    private val sockets = mutableMapOf<String, ChatSocket>()

    private fun socketFor(matchId: String): ChatSocket = synchronized(sockets) {
        sockets.getOrPut(matchId) { ChatSocket(client, tokenStore, matchId, scope) }
    }

    override suspend fun history(matchId: String, beforeId: String?): ApiResult<List<Message>> =
        api.getMessages(matchId, beforeId = beforeId).map { page -> page.messages.map { it.toDomain() } }

    override suspend fun send(matchId: String, body: String, clientMsgId: String?): ApiResult<Message> =
        api.sendMessage(matchId, body, clientMsgId).map { it.toDomain() }

    override suspend fun markRead(matchId: String): ApiResult<Unit> = api.markRead(matchId)

    override fun socket(matchId: String): Flow<ChatEvent> = socketFor(matchId).events

    override suspend fun sendTyping(matchId: String, typing: Boolean) =
        socketFor(matchId).sendTyping(typing)
}

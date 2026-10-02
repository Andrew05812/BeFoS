package app.befos.data.repository

import app.befos.core.network.ApiConfig
import app.befos.core.network.ApiResult
import app.befos.core.network.TokenStore
import app.befos.core.network.befosJson
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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * A resilient WebSocket connection to a single match. Incoming frames are
 * published to [events]; outgoing messages/typing are written to the live
 * session. The connection loop reconnects with a fixed backoff while active.
 */
class ChatSocket(
    private val client: HttpClient,
    private val tokenStore: TokenStore,
    private val matchId: String,
    private val scope: CoroutineScope,
) {
    private val _events = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 64)
    val events: Flow<ChatEvent> = _events.asSharedFlow()

    @Volatile
    private var session: io.ktor.client.plugins.websocket.DefaultClientWebSocketSession? = null

    @Volatile
    private var started = false

    fun start() {
        if (started) return
        started = true
        scope.launch {
            while (isActive) {
                try {
                    val token = freshAccessToken()
                    if (token == null) {
                        delay(RECONNECT_DELAY_MS)
                        continue
                    }
                    client.webSocket(urlString = "${ApiConfig.wsUrl(matchId)}?token=$token") {
                        session = this
                        _events.tryEmit(ChatEvent.Connected)
                        for (frame in incoming) {
                            if (frame is Frame.Text) {
                                parse(frame.readText())?.let { _events.tryEmit(it) }
                            }
                        }
                    }
                } catch (e: Exception) {
                    _events.tryEmit(ChatEvent.Error(e.message ?: "Ошибка соединения"))
                } finally {
                    session = null
                    _events.tryEmit(ChatEvent.Disconnected)
                }
                delay(RECONNECT_DELAY_MS)
            }
        }
    }

    /**
     * The socket authorizes via a token query param, which cannot trigger the
     * Ktor refresh flow on 401. A cheap authenticated call rotates an expired
     * access token before the socket dials, avoiding a 403 reconnect loop.
     */
    private suspend fun freshAccessToken(): String? {
        val probe = ApiConfig.absolute("users/me")
        if (probe != null) runCatching { client.get(probe).body<JsonObject>() }
        return tokenStore.current()?.accessToken
    }

    suspend fun sendMessage(body: String, clientMsgId: String) {
        val payload = buildJsonObject {
            put("type", "message")
            put("body", body)
            put("client_msg_id", clientMsgId)
        }
        session?.outgoing?.send(Frame.Text(payload.toString()))
    }

    suspend fun sendTyping(typing: Boolean) {
        val payload = buildJsonObject {
            put("type", "typing")
            put("typing", typing)
        }
        session?.outgoing?.send(Frame.Text(payload.toString()))
    }

    suspend fun sendRead() {
        val payload = buildJsonObject { put("type", "read") }
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
            "error" -> ChatEvent.Error(obj["message"]?.jsonPrimitive?.content ?: "Ошибка")
            else -> null
        }
    }

    private companion object {
        const val RECONNECT_DELAY_MS = 2_000L
    }
}

class ChatRepositoryImpl(
    private val api: ApiService,
    private val client: HttpClient,
    private val tokenStore: TokenStore,
    private val scope: CoroutineScope,
) : ChatRepository {

    private val sockets = mutableMapOf<String, ChatSocket>()

    private fun socketFor(matchId: String): ChatSocket = synchronized(sockets) {
        sockets.getOrPut(matchId) {
            ChatSocket(client, tokenStore, matchId, scope).also { it.start() }
        }
    }

    override suspend fun history(matchId: String, beforeId: String?): ApiResult<List<Message>> =
        api.getMessages(matchId, beforeId = beforeId).map { page -> page.messages.map { it.toDomain() } }

    override suspend fun send(matchId: String, body: String): ApiResult<Message> =
        api.sendMessage(matchId, body).map { it.toDomain() }

    override suspend fun markRead(matchId: String): ApiResult<Unit> = api.markRead(matchId)

    override fun socket(matchId: String): Flow<ChatEvent> = socketFor(matchId).events

    override suspend fun sendViaSocket(matchId: String, body: String, clientMsgId: String) =
        socketFor(matchId).sendMessage(body, clientMsgId)

    override suspend fun sendTyping(matchId: String, typing: Boolean) =
        socketFor(matchId).sendTyping(typing)
}

package app.befos.presentation.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatUiState(
    val loading: Boolean = true,
    val messages: List<Message> = emptyList(),
    val draft: String = "",
    val sending: Boolean = false,
    val otherTyping: Boolean = false,
    val otherOnline: Boolean = false,
    val connected: Boolean = false,
    val partnerName: String? = null,
    val historyError: String? = null,
    val sendError: String? = null,
    /**
     * Why the socket is not live, in the same product voice as every other failure. Null until
     * the dial answers: a drop that ended cleanly leaves the generic reconnecting line.
     */
    val socketReason: String? = null,
    /**
     * Whether the server refuses this thread as one that does not exist. A read of a dissolved
     * pair is not a page that failed to arrive: the refusal is the pair's state, so another read
     * of the same id pays for the same answer, and a screen that keeps offering one promises what
     * cannot happen. Only a read of the thread sets it, and only a page that arrived takes it back.
     */
    val gone: Boolean = false,
)

class ChatViewModel(
    private val chatRepository: ChatRepository,
    private val matchRepository: MatchRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private var socketJob: Job? = null

    /**
     * The one send attempt that has not been answered yet, named by the app. The name is
     * what lets a retry of a lost response reuse the stored message instead of writing a
     * second copy; it belongs to exactly the text that failed, so an edit ends it.
     */
    private var pendingAttempt: PendingAttempt? = null

    private data class PendingAttempt(val body: String, val clientMsgId: String)

    private var socketWasDown = false

    private var partnerJob: Job? = null

    init {
        loadHistory()
        observeSocket()
        loadPartner()
    }

    /**
     * The header names the conversation, and `init` is the only other thing that asks for the name.
     * Opening a thread while the network was down therefore left it anonymous for the rest of the
     * screen's life: the refusal was dropped without a word and nothing ever asked again. A
     * connection is the moment the network is known to answer, so that is when the missing name is
     * asked for — once per connection, never while a read of it is already in flight, and not at
     * all once the name is already on screen.
     */
    private fun loadPartner() {
        if (_uiState.value.partnerName != null || partnerJob?.isActive == true) return
        partnerJob = viewModelScope.launch {
            when (val result = matchRepository.partner(matchId)) {
                is ApiResult.Success -> _uiState.update { it.copy(partnerName = result.data.name) }
                // Nothing to tell the person: the header keeps its own word for a partner whose
                // name has not arrived, and the next connection retries it.
                is ApiResult.Error -> Unit
            }
        }
    }

    private fun loadHistory() {
        viewModelScope.launch {
            when (val result = chatRepository.history(matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        gone = false,
                        messages = result.data.sortedBy { m -> m.createdAt },
                        historyError = null,
                    )
                }
                // The read itself writes the receipt and tells the partner's socket, so a page
                // that arrived needs no second call — and a page that did not arrive must not
                // claim a backlog the person never saw.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        loading = false,
                        historyError = result.message,
                        gone = it.gone || isEndOfThread(result.code),
                    )
                }
            }
        }
    }

    fun retryHistory() {
        // A thread that is already on screen keeps showing while its replacement is fetched:
        // blanking it would trade the bubbles the reader is looking at for a skeleton.
        _uiState.update { it.copy(loading = it.messages.isEmpty(), historyError = null) }
        loadHistory()
    }

    private fun observeSocket() {
        socketJob = viewModelScope.launch {
            chatRepository.socket(matchId).collect { event ->
                when (event) {
                    is ChatEvent.IncomingMessage -> upsert(event.message)
                    is ChatEvent.Typing -> _uiState.update { it.copy(otherTyping = event.typing) }
                    is ChatEvent.Read -> _uiState.update { st ->
                        st.copy(messages = st.messages.map { if (it.isOwn) it.copy(isRead = true) else it })
                    }
                    is ChatEvent.Presence -> _uiState.update { it.copy(otherOnline = event.online) }
                    is ChatEvent.Connected -> {
                        _uiState.update { it.copy(connected = true, socketReason = null) }
                        if (socketWasDown) {
                            socketWasDown = false
                            fillGap()
                        }
                        loadPartner()
                    }
                    is ChatEvent.Disconnected -> {
                        // The connection lives in a StateFlow, which re-states its current value to
                        // every new collector, so the first frame of a screen can be `Disconnected`
                        // while the socket has never been up. Only losing a connection this screen
                        // has actually had leaves a page nobody has read.
                        if (_uiState.value.connected) socketWasDown = true
                        _uiState.update { it.copy(connected = false, otherTyping = false) }
                    }
                    // A frame the server refused while the socket is healthy says nothing the
                    // user can act on; the same text while the socket is down is the reason the
                    // reconnect has not finished, and the status line says it for them.
                    is ChatEvent.Error -> _uiState.update {
                        if (it.connected) it else it.copy(socketReason = event.message)
                    }
                }
            }
        }
    }

    /**
     * What arrived while the socket was down exists only in the database, so the gap is
     * filled from the newest page instead of being guessed at. The first `Connected` of a
     * screen is not a gap: the history load that came with it is the same read.
     */
    private fun fillGap() {
        viewModelScope.launch {
            when (val result = chatRepository.history(matchId)) {
                is ApiResult.Success -> _uiState.update { state ->
                    val known = state.messages.mapTo(HashSet()) { it.id }
                    val fresh = result.data.filterNot { it.id in known }
                    if (fresh.isEmpty()) state.copy(gone = false, historyError = null)
                    else state.copy(
                        messages = (state.messages + fresh).sortedBy { it.createdAt },
                        otherTyping = false,
                        historyError = null,
                        gone = false,
                    )
                }
                // The status pill has just said the link is back, so a page that did not come
                // through it cannot go unmentioned: the gap stays real until the read answers,
                // and naming it is what gives the retry something to act on. A page the pair
                // refuses outright is not a gap the next read closes.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        historyError = result.message,
                        gone = it.gone || isEndOfThread(result.code),
                    )
                }
            }
        }
    }

    private fun upsert(message: Message) {
        _uiState.update { state ->
            if (state.messages.any { it.id == message.id }) return@update state
            val next = (state.messages + message).sortedBy { it.createdAt }
            state.copy(messages = next, otherTyping = false)
        }
        if (!message.isOwn) {
            viewModelScope.launch { chatRepository.markRead(matchId) }
        }
    }

    fun onDraftChange(v: String) {
        val wasTyping = _uiState.value.draft.isNotBlank()
        // A failed send keeps its name only while the text that failed sits untouched; once
        // the person edits, the next send is a new message and must be free to store.
        pendingAttempt = pendingAttempt?.takeIf { it.body == v.trim() }
        _uiState.update { it.copy(draft = v) }
        // One frame per blank/non-blank transition instead of one per keystroke.
        if (wasTyping != v.isNotBlank()) viewModelScope.launch { sendTypingHint(v.isNotBlank()) }
    }

    /**
     * A typing frame is a hint about the composer, not the message: the partner's indicator, not
     * their inbox. The socket that carries it can be closing right now — Ktor's write channel
     * answers a send after its session ended with `ClosedSendChannelException` — and neither call
     * site is on the path a message travels, which goes over HTTP. Letting that exception out of
     * `send` threw between `sending = true` and the request, so the typed text was already off the
     * screen, the send button was already disabled, and the refusal the person needed to see never
     * arrived; letting it out of the keystroke frame escaped the coroutine as an unhandled
     * exception over an indicator. The `finally` that drops that session also drops `_connected`,
     * so the link is still reported by the status line — a hint is all this swallows.
     */
    private suspend fun sendTypingHint(typing: Boolean) {
        try {
            chatRepository.sendTyping(matchId, typing)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // `ChatRepository.sendTyping` has these two call sites and nothing else, and the
            // product has no retry for an indicator — the message it travels beside is the part
            // that owes the person an answer.
        }
    }

    fun send() {
        val body = _uiState.value.draft.trim()
        if (body.isEmpty() || _uiState.value.sending) return
        val attempt = pendingAttempt?.takeIf { it.body == body }
            ?: PendingAttempt(body, UUID.randomUUID().toString())
        pendingAttempt = attempt
        _uiState.update { it.copy(sending = true, draft = "", sendError = null) }
        viewModelScope.launch {
            sendTypingHint(false)
            when (val result = chatRepository.send(matchId, attempt.body, attempt.clientMsgId)) {
                is ApiResult.Success -> {
                    pendingAttempt = null
                    upsert(result.data)
                    _uiState.update { it.copy(sending = false) }
                }
                // The attempt keeps its name: an unanswered send may have stored the message,
                // and a retry under the same name is the difference between one copy and two.
                is ApiResult.Error -> _uiState.update {
                    it.copy(sending = false, draft = attempt.body, sendError = result.message)
                }
            }
        }
    }

    fun dismissSendError() {
        _uiState.update { it.copy(sendError = null) }
    }

    override fun onCleared() {
        super.onCleared()
        socketJob?.cancel()
    }
}

/**
 * Whether a refused thread read ends the conversation instead of pausing it.
 *
 * The status is the only part of the answer that separates the two, and `ApiResult.Error` carries
 * it. Measured on the live stand (`s72_d11_block_pair.txt`, прогон 03:17:13…03:17:16 UTC): after
 * one partner blocks, every read of the pair answers 404 on both sides, because
 * `ChatService._require_membership` raises the same `NotFoundError` for a row that is not there as
 * for a row that is not yours. A transport failure is worded by the client as -1, and a session
 * that has run out as 401 — both can answer differently on the next read, so neither ends a thread.
 */
private fun isEndOfThread(code: Int): Boolean = code == 404

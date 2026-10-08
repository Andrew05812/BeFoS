package app.befos.presentation.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import java.util.UUID
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

    init {
        loadHistory()
        observeSocket()
        loadPartner()
    }

    /** The header names the conversation; a failure just leaves the generic title. */
    private fun loadPartner() {
        viewModelScope.launch {
            val result = matchRepository.partner(matchId)
            if (result is ApiResult.Success) {
                _uiState.update { it.copy(partnerName = result.data.name) }
            }
        }
    }

    private fun loadHistory() {
        viewModelScope.launch {
            when (val result = chatRepository.history(matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, messages = result.data.sortedBy { m -> m.createdAt }, historyError = null)
                }
                // The read itself writes the receipt and tells the partner's socket, so a page
                // that arrived needs no second call — and a page that did not arrive must not
                // claim a backlog the person never saw.
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, historyError = result.message) }
            }
        }
    }

    fun retryHistory() {
        _uiState.update { it.copy(loading = true, historyError = null) }
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
            val result = chatRepository.history(matchId)
            if (result !is ApiResult.Success) return@launch
            _uiState.update { state ->
                val known = state.messages.mapTo(HashSet()) { it.id }
                val fresh = result.data.filterNot { it.id in known }
                if (fresh.isEmpty()) state
                else state.copy(
                    messages = (state.messages + fresh).sortedBy { it.createdAt },
                    otherTyping = false,
                )
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
        if (wasTyping != v.isNotBlank()) viewModelScope.launch { chatRepository.sendTyping(matchId, v.isNotBlank()) }
    }

    fun send() {
        val body = _uiState.value.draft.trim()
        if (body.isEmpty() || _uiState.value.sending) return
        val attempt = pendingAttempt?.takeIf { it.body == body }
            ?: PendingAttempt(body, UUID.randomUUID().toString())
        pendingAttempt = attempt
        _uiState.update { it.copy(sending = true, draft = "", sendError = null) }
        viewModelScope.launch {
            chatRepository.sendTyping(matchId, false)
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

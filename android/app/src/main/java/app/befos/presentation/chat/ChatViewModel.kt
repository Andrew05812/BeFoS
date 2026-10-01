package app.befos.presentation.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
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
    val error: String? = null,
)

class ChatViewModel(
    private val chatRepository: ChatRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private var socketJob: Job? = null

    init {
        loadHistory()
        observeSocket()
    }

    private fun loadHistory() {
        viewModelScope.launch {
            when (val result = chatRepository.history(matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, messages = result.data.sortedBy { m -> m.createdAt })
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
            chatRepository.markRead(matchId)
        }
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
                    is ChatEvent.Error -> Unit
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
        _uiState.update { it.copy(draft = v) }
        viewModelScope.launch { chatRepository.sendTyping(matchId, v.isNotBlank()) }
    }

    fun send() {
        val body = _uiState.value.draft.trim()
        if (body.isEmpty() || _uiState.value.sending) return
        _uiState.update { it.copy(sending = true, draft = "", error = null) }
        viewModelScope.launch {
            chatRepository.sendTyping(matchId, false)
            when (val result = chatRepository.send(matchId, body)) {
                is ApiResult.Success -> {
                    upsert(result.data)
                    _uiState.update { it.copy(sending = false) }
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(sending = false, draft = body, error = result.message)
                }
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        socketJob?.cancel()
    }
}

package app.befos.presentation.chat

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val events = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 16)
    private val repo: ChatRepository = mockk {
        every { socket(any()) } returns events
    }
    // The header name is cosmetic here; every case keeps the "Чат" fallback.
    private val matchRepo: MatchRepository = mockk {
        coEvery { partner(any()) } returns ApiResult.Error(404, "no partner")
    }

    private fun message(id: String, own: Boolean, body: String = "hi") = Message(
        id = id, matchId = "m1", senderId = if (own) "me" else "them",
        body = body, createdAt = "2026-01-01T00:00:0$id", isRead = false, isOwn = own,
    )

    @Test
    fun `history loads sorted messages`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(listOf(message("2", false), message("1", true)))
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("1", "2"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `send appends returned message and clears draft`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "привет") } returns ApiResult.Success(message("9", true, "привет"))

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("привет")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("", vm.uiState.value.draft)
        assertEquals(listOf("9"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `socket echo of own sent message is deduplicated`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "hey") } returns ApiResult.Success(message("5", true, "hey"))

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("hey")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Backend echoes the same message over the socket.
        events.tryEmit(ChatEvent.IncomingMessage(message("5", true, "hey")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(1, vm.uiState.value.messages.size)
    }

    @Test
    fun `incoming message from other party is appended`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        events.tryEmit(ChatEvent.IncomingMessage(message("7", false, "здорово")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.messages.any { it.id == "7" })
    }

    @Test
    fun `connection state tracks socket connect and disconnect`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Not connected until the socket opens.
        assertEquals(false, vm.uiState.value.connected)

        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.connected)

        // A typing indicator is cleared when the socket drops.
        events.tryEmit(ChatEvent.Typing(userId = "them", typing = true))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.otherTyping)

        events.tryEmit(ChatEvent.Disconnected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.connected)
        assertEquals(false, vm.uiState.value.otherTyping)
    }
}

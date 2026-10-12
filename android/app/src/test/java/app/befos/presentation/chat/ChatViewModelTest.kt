package app.befos.presentation.chat

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.ClosedSendChannelException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.merge
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
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
        coEvery { repo.send("m1", "привет", any()) } returns ApiResult.Success(message("9", true, "привет"))

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("привет")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("", vm.uiState.value.draft)
        assertEquals(listOf("9"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `a rejected send puts the text back on screen`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "too long", any()) } returns
            ApiResult.Error(422, "Сообщение слишком длинное — разбейте его на два.")

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("too long")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A message the server refused must not silently vanish with the draft.
        assertEquals("too long", vm.uiState.value.draft)
        assertEquals("Сообщение слишком длинное — разбейте его на два.", vm.uiState.value.sendError)
        assertTrue(vm.uiState.value.messages.isEmpty())
    }

    @Test
    fun `a double tap on send posts one message`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "hey", any()) } coAnswers {
            delay(50)
            ApiResult.Success(message("5", true, "hey"))
        }

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("hey")
        vm.send()
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repo.send("m1", "hey", any()) }
        assertEquals(listOf("5"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `a retry of a send that never got an answer keeps the same name`() = runTest {
        val names = mutableListOf<String?>()
        var attempts = 0
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "again", captureNullable(names)) } coAnswers {
            attempts++
            // The first answer is a transport failure: the request may or may not have
            // reached the server, which is exactly what a named send is for.
            if (attempts == 1) ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")
            else ApiResult.Success(message("9", true, "again"))
        }

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("again")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, names.size)
        assertEquals(1, names.distinct().size)
        assertTrue(names.first() != null)
        assertEquals(listOf("9"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `a send retyped after an edit is a new message`() = runTest {
        val names = mutableListOf<String?>()
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "again", captureNullable(names)) } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(message("9", true, "again")),
        )

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("again")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        // The person edits the text and puts it back: the next send is their intent, not a
        // retry of the old one, so it must be free to store.
        vm.onDraftChange("ага")
        vm.onDraftChange("again")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, names.size)
        assertEquals(2, names.distinct().size)
    }

    @Test
    fun `socket echo of own sent message is deduplicated`() = runTest {        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit
        coEvery { repo.send("m1", "hey", any()) } returns ApiResult.Success(message("5", true, "hey"))

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

    @Test
    fun `a socket that will not open says why on the status line`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing is connected yet, so the generic line stands until the dial answers.
        assertEquals(null, vm.uiState.value.socketReason)

        events.tryEmit(ChatEvent.Error("Этот чат больше недоступен."))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The reason replaces the promise of a recovery that cannot happen.
        assertEquals("Этот чат больше недоступен.", vm.uiState.value.socketReason)
        assertEquals(false, vm.uiState.value.connected)
    }

    @Test
    fun `a socket that came back stops repeating the old reason`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        events.tryEmit(ChatEvent.Error("Сервер не отвечает. Попробуйте ещё раз."))
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.connected)
        assertEquals(null, vm.uiState.value.socketReason)
    }

    @Test
    fun `a frame the server refuses over a live socket does not claim the link is down`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Error("Сообщение не отправлено. Попробуйте ещё раз."))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The socket is up and answered; a status line about a lost connection would be false.
        assertEquals(true, vm.uiState.value.connected)
        assertEquals(null, vm.uiState.value.socketReason)
    }

    @Test
    fun `a reconnect reads the messages that arrived while the socket was down`() = runTest {
        coEvery { repo.history("m1", any()) } returnsMany listOf(
            ApiResult.Success(listOf(message("1", false, "привет"))),
            ApiResult.Success(listOf(message("1", false, "привет"), message("2", false, "пока"))),
        )
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("1"), vm.uiState.value.messages.map { it.id })

        // The first Connected is the socket opening behind a history load that already
        // happened, so it reads nothing again.
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 1) { repo.history("m1", any()) }

        events.tryEmit(ChatEvent.Disconnected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("1", "2"), vm.uiState.value.messages.map { it.id })
        coVerify(exactly = 2) { repo.history("m1", any()) }
    }

    @Test
    fun `a reconnect that finds nothing new leaves the thread alone`() = runTest {
        val known = listOf(message("1", false, "привет"))
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(known)
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onDraftChange("черновик")

        events.tryEmit(ChatEvent.Disconnected)
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("1"), vm.uiState.value.messages.map { it.id })
        assertEquals("черновик", vm.uiState.value.draft)
    }

    @Test
    fun `opening a chat does not ask for the receipt the read already wrote`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(listOf(message("1", false)))
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 0) { repo.markRead(any()) }

        // The same holds for the retry button: it re-reads the page, and the read marks again.
        vm.retryHistory()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("1"), vm.uiState.value.messages.map { it.id })
        coVerify(exactly = 0) { repo.markRead(any()) }
    }

    @Test
    fun `a chat that did not load does not claim its backlog was read`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Error(0, "no network")
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.historyError != null)
        coVerify(exactly = 0) { repo.markRead(any()) }
    }

    @Test
    fun `a message arriving over the socket is still marked read`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing re-reads the page here, so this receipt has no other way to travel.
        events.tryEmit(ChatEvent.IncomingMessage(message("7", false, "пока")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("7"), vm.uiState.value.messages.map { it.id })
        coVerify(exactly = 1) { repo.markRead("m1") }

        events.tryEmit(ChatEvent.IncomingMessage(message("8", true, "ага")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 1) { repo.markRead("m1") }
    }

    @Test
    fun `a socket opening for the first time does not read the page again`() = runTest {
        // `ChatSocket` keeps the connection in a StateFlow, and a StateFlow re-states its current
        // value to every new collector: a screen that joins before the dial answers is handed
        // `Disconnected` as its first frame although the socket was never up. The shared flow the
        // other cases use cannot say that, so this one builds the stream the way production does.
        val connection = MutableStateFlow(false)
        val frames = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 16)
        val dialingRepo: ChatRepository = mockk {
            every { socket(any()) } returns merge(
                connection.map { if (it) ChatEvent.Connected else ChatEvent.Disconnected },
                frames,
            )
            coEvery { history("m1", any()) } returns ApiResult.Success(listOf(message("1", false, "привет")))
            coEvery { markRead("m1") } returns ApiResult.Success(Unit)
            coEvery { sendTyping(any(), any()) } returns Unit
        }

        val vm = ChatViewModel(dialingRepo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The dial answers. Nothing arrived while the screen waited for the page it already has.
        connection.value = true
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.connected)
        assertEquals(listOf("1"), vm.uiState.value.messages.map { it.id })
        coVerify(exactly = 1) { dialingRepo.history("m1", any()) }
    }

    @Test
    fun `a socket that was up and came back still reads what arrived between`() = runTest {
        val connection = MutableStateFlow(false)
        val frames = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 16)
        val dialingRepo: ChatRepository = mockk {
            every { socket(any()) } returns merge(
                connection.map { if (it) ChatEvent.Connected else ChatEvent.Disconnected },
                frames,
            )
            coEvery { history("m1", any()) } returnsMany listOf(
                ApiResult.Success(listOf(message("1", false, "привет"))),
                ApiResult.Success(listOf(message("1", false, "привет"), message("2", false, "пока"))),
            )
            coEvery { markRead("m1") } returns ApiResult.Success(Unit)
            coEvery { sendTyping(any(), any()) } returns Unit
        }

        val vm = ChatViewModel(dialingRepo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        connection.value = true
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 1) { dialingRepo.history("m1", any()) }

        // A connection this screen really had, lost and won back: the page it never showed is
        // still only in the database.
        connection.value = false
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.connected)

        connection.value = true
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.connected)
        assertEquals(listOf("1", "2"), vm.uiState.value.messages.map { it.id })
        coVerify(exactly = 2) { dialingRepo.history("m1", any()) }
    }

    @Test
    fun `a typing frame the socket cannot carry still sends the message`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping("m1", true) } returns Unit
        coEvery { repo.sendTyping("m1", false) } throws ClosedSendChannelException("WebSocket Session is closed")
        coEvery { repo.send("m1", "hey", any()) } returns ApiResult.Success(message("9", true, "hey"))

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("hey")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repo.send("m1", "hey", any()) }
        assertEquals(listOf("9"), vm.uiState.value.messages.map { it.id })
        assertFalse(vm.uiState.value.sending)
    }

    @Test
    fun `a typing frame that fails on the first keystroke leaves the draft on screen`() = runTest {
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping("m1", true) } throws ClosedSendChannelException("WebSocket Session is closed")
        coEvery { repo.sendTyping("m1", false) } returns Unit
        coEvery { repo.send("m1", "hey", any()) } returns ApiResult.Success(message("9", true, "hey"))

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("hey")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("hey", vm.uiState.value.draft)

        // The indicator is gone; the screen that carries it is not. A scope cancelled by the throw
        // would silently ignore this send, so the message itself is the proof of survival.
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repo.send("m1", "hey", any()) }
        assertEquals(listOf("9"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `a send the server refuses names its own reason when the typing frame failed too`() = runTest {
        // The two failures travel together: the socket is down, so the hint throws, and the server
        // answers the HTTP send with its own refusal. Only the second one is worth showing, and
        // only if the first is allowed to pass without taking the request down with it.
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } throws ClosedSendChannelException("WebSocket Session is closed")
        coEvery { repo.send("m1", "too long", any()) } returns
            ApiResult.Error(422, "Сообщение слишком длинное — разбейте его на два.")

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("too long")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("too long", vm.uiState.value.draft)
        assertEquals("Сообщение слишком длинное — разбейте его на два.", vm.uiState.value.sendError)
    }

    @Test
    fun `a retry after a typing frame the socket could not carry keeps the same name`() = runTest {
        val names = mutableListOf<String?>()
        var attempts = 0
        coEvery { repo.history("m1", any()) } returns ApiResult.Success(emptyList())
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } throws ClosedSendChannelException("WebSocket Session is closed")
        coEvery { repo.send("m1", "again", captureNullable(names)) } coAnswers {
            attempts++
            if (attempts == 1) ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")
            else ApiResult.Success(message("9", true, "again"))
        }

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.onDraftChange("again")
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.send()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A hint that could not fly is not a new message: the retry must reuse the name.
        assertEquals(2, names.size)
        assertEquals(1, names.distinct().size)
        assertTrue(names.first() != null)
        assertEquals(listOf("9"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `a gap read that fails after reconnect names itself instead of staying silent`() = runTest {
        coEvery { repo.history("m1", any()) } returnsMany listOf(
            ApiResult.Success(listOf(message("1", false, "привет"))),
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
        )
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        events.tryEmit(ChatEvent.Disconnected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The pill says the link is back, so the read that failed behind it has to say so too:
        // without a named failure the unseen messages are simply a thread that never happened.
        assertEquals(true, vm.uiState.value.connected)
        assertEquals(
            "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.",
            vm.uiState.value.historyError,
        )
    }

    @Test
    fun `a failed gap read leaves the open thread and the draft alone`() = runTest {
        coEvery { repo.history("m1", any()) } returnsMany listOf(
            ApiResult.Success(listOf(message("1", false, "привет"))),
            ApiResult.Error(-1, "Сервер недоступен."),
        )
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        vm.onDraftChange("черновик")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        events.tryEmit(ChatEvent.Disconnected)
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("1"), vm.uiState.value.messages.map { it.id })
        assertEquals("черновик", vm.uiState.value.draft)
    }

    @Test
    fun `retrying a thread that is already on screen does not blank it`() = runTest {
        coEvery { repo.history("m1", any()) } returnsMany listOf(
            ApiResult.Success(listOf(message("1", false, "привет"))),
            ApiResult.Error(-1, "Сервер недоступен."),
            ApiResult.Success(listOf(message("1", false, "привет"), message("2", false, "пока"))),
        )
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Disconnected)
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.retryHistory()

        // The notice sits over a thread the reader is looking at. Fetching its replacement must
        // not trade the bubbles for a skeleton on the way.
        assertFalse(vm.uiState.value.loading)
        assertEquals(listOf("1"), vm.uiState.value.messages.map { it.id })
    }

    @Test
    fun `a gap page that arrives after a failed read closes the notice`() = runTest {
        coEvery { repo.history("m1", any()) } returnsMany listOf(
            ApiResult.Success(listOf(message("1", false, "привет"))),
            ApiResult.Error(-1, "Сервер недоступен."),
            ApiResult.Success(listOf(message("1", false, "привет"), message("2", false, "пока"))),
        )
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Disconnected)
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.historyError != null)

        vm.retryHistory()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.historyError)
        assertEquals(listOf("1", "2"), vm.uiState.value.messages.map { it.id })
        assertEquals(false, vm.uiState.value.loading)
    }

    @Test
    fun `a message that flies in over the socket does not retire an unread gap page`() = runTest {
        coEvery { repo.history("m1", any()) } returnsMany listOf(
            ApiResult.Success(listOf(message("1", false, "привет"))),
            ApiResult.Error(-1, "Сервер недоступен."),
        )
        coEvery { repo.markRead("m1") } returns ApiResult.Success(Unit)
        coEvery { repo.sendTyping(any(), any()) } returns Unit

        val vm = ChatViewModel(repo, matchRepo, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        events.tryEmit(ChatEvent.Disconnected)
        events.tryEmit(ChatEvent.Connected)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // One bubble arriving live says nothing about the rest of the page that did not
        // arrive: the notice stays until the read itself answers.
        events.tryEmit(ChatEvent.IncomingMessage(message("3", false, "там?")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("1", "3"), vm.uiState.value.messages.map { it.id })
        assertTrue(vm.uiState.value.historyError != null)
    }
}

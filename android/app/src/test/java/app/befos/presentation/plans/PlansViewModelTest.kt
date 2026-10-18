package app.befos.presentation.plans

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.domain.model.MessagePlan
import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.PlanRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * A plan is one entity the other half moves too, so the page reads it back after every write that
 * landed and never keeps its own answer of the pair's hour. What a refused tap must do is the other
 * half of the contract: the card stays exactly where it was, the reason the server gave is named on
 * that card, and no second request is sent for a decision the pair has already made.
 *
 * The pair's hour also moves while nobody is looking at this page — on the other half's screen — and
 * the thread's plan lines are the only notice the open page gets. Which lines count as that notice is
 * the part no row of the plan answers: a sentence somebody typed says nothing about the arrangement,
 * and this person's own move was already read back by the write that made it.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PlansViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private fun plan(
        status: String = PlanStatuses.PLANNED,
        id: String = "p1",
        place: String? = null,
        note: String? = null,
    ) = Plan(
        id = id,
        title = "Поход в кино", description = null, note = note, place = place,
        status = status, startsAt = "2026-10-17T19:00:00+03:00", pendingHour = null, pendingBy = null,
        myDecision = PlanDecisions.JOINED, iAttended = false,
        partnerId = "them", partnerName = "Анна",
        partnerDecision = PlanDecisions.JOINED, partnerAttended = false,
        hourPassed = false, needsMyAnswer = false, canCancel = true,
    )

    private fun repo(first: ApiResult<List<Plan>> = ApiResult.Success(listOf(plan()))) = mockk<PlanRepository> {
        coEvery { plans("m1") } returns first
        coEvery { accept(any()) } returns ApiResult.Success(Unit)
        coEvery { decline(any()) } returns ApiResult.Success(Unit)
        coEvery { restoreDecline(any()) } returns ApiResult.Success(Unit)
        coEvery { offerHour(any(), any()) } returns ApiResult.Success(Unit)
        coEvery { confirmHour(any(), any()) } returns ApiResult.Success(Unit)
        coEvery { editWords(any(), any(), any(), any(), any()) } returns ApiResult.Success(Unit)
        coEvery { cancel(any()) } returns ApiResult.Success(Unit)
        coEvery { restore(any()) } returns ApiResult.Success(Unit)
        coEvery { markAttended(any()) } returns ApiResult.Success(Unit)
        coEvery { undoAttended(any()) } returns ApiResult.Success(Unit)
    }

    // The thread the pair's plan writes into. The page reads this flow rather than the plan routes,
    // so a test says what the other half's screen did by putting a line on it.
    private val live = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 8)

    private fun chat() = mockk<ChatRepository> {
        every { socket("m1") } returns live
    }

    /**
     * A line of the pair's thread, as the socket delivers it.
     *
     * `kind` stays a string the test picks: what the page answers to is the plan having written the
     * line, not this build knowing the word the server used for the move.
     */
    private fun line(kind: String, own: Boolean) = ChatEvent.IncomingMessage(
        Message(
            id = "l1", matchId = "m1", senderId = if (own) "me" else "them",
            body = "Поход в кино", createdAt = "2026-10-16T05:00:00+03:00",
            isRead = false, isOwn = own, kind = kind,
            plan = MessagePlan(
                activityId = 7, activityTitle = "Поход в кино",
                whenIso = "2026-10-17T19:00:00+03:00", planId = "p1", isLatest = true,
            ),
        ),
    )

    private fun viewModel(
        repository: PlanRepository = repo(),
        thread: ChatRepository = chat(),
    ): PlansViewModel {
        val vm = PlansViewModel(repository, thread, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `opening the page reads the pair's plans once`() {
        val repository = repo()
        val vm = viewModel(repository)

        assertFalse(vm.uiState.value.loading)
        assertEquals(listOf("p1"), vm.uiState.value.plans.map { it.id })
        assertNull(vm.uiState.value.error)
        coVerify(exactly = 1) { repository.plans("m1") }
    }

    @Test
    fun `a tap that lands is one request and the page read back`() {
        val repository = repo()
        val vm = viewModel(repository)

        vm.accept("p1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repository.accept("p1") }
        // The reload is what retires the pair's own doubt: the server answers whose hour the plan
        // stands on, and this visit's tap is not a fact worth keeping after it.
        coVerify(exactly = 2) { repository.plans("m1") }
        assertTrue(vm.uiState.value.busy.isEmpty())
        assertTrue(vm.uiState.value.tapErrors.isEmpty())
    }

    @Test
    fun `a second tap on a plan that is still answering sends nothing`() {
        val repository = repo()
        coEvery { repository.accept("p1") } coAnswers {
            delay(200)
            ApiResult.Success(Unit)
        }
        val vm = viewModel(repository)

        vm.accept("p1")
        vm.accept("p1")
        assertTrue(vm.uiState.value.busy.contains("p1"))

        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repository.accept("p1") }
    }

    @Test
    fun `a refused tap names its card, says why and keeps the row standing`() {
        val repository = repo()
        coEvery { repository.decline("p1") } returns ApiResult.Error(409, "Пара уже договорилась о другом часе.")
        val vm = viewModel(repository)

        vm.decline("p1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        val state = vm.uiState.value
        assertEquals(
            "Не удалось отклонить идею. Пара уже договорилась о другом часе.",
            state.tapErrors["p1"],
        )
        // Nothing changed on the server, so nothing is asked back: the card stays where the tap can be
        // made again, and the pair's other rows are not dragged into a read that answers nothing.
        coVerify(exactly = 1) { repository.plans("m1") }
        assertTrue(state.plans.isNotEmpty())
        assertTrue(state.busy.isEmpty())
    }

    @Test
    fun `a refusal without a reason still says what did not land`() {
        val repository = repo()
        coEvery { repository.cancel("p1") } returns ApiResult.Error(500, "")
        val vm = viewModel(repository)

        vm.cancel("p1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The client's own line is the sentence this card can be trusted to finish; an empty reason
        // must not leave a bare space behind the verb.
        assertEquals("Не удалось отменить план.", vm.uiState.value.tapErrors["p1"])
    }

    @Test
    fun `a write that lands ends the doubt the last refusal left`() {
        val repository = mockk<PlanRepository> {
            coEvery { plans("m1") } returnsMany listOf(
                ApiResult.Success(listOf(plan())),
                ApiResult.Success(listOf(plan())),
            )
            coEvery { cancel("p1") } returns ApiResult.Error(409, "План уже отменён.")
            coEvery { restore("p1") } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(repository)

        vm.cancel("p1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.tapErrors.isNotEmpty())

        vm.restore("p1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.tapErrors.isEmpty())
    }

    @Test
    fun `an hour offered by this person leaves as the row chose it`() {
        val repository = repo()
        val vm = viewModel(repository)

        vm.offerHour("p1", "2026-10-18T19:00:00+03:00")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Not a minute off, not a zone re-derived: the instant the card put on screen is the instant
        // the pair agrees to.
        coVerify(exactly = 1) { repository.offerHour("p1", "2026-10-18T19:00:00+03:00") }
    }

    @Test
    fun `a plan the page cannot read keeps its last honest row and says so`() {
        val repository = mockk<PlanRepository> {
            coEvery { plans("m1") } returnsMany listOf(
                ApiResult.Success(listOf(plan())),
                ApiResult.Error(500, "Сервер не ответил."),
            )
        }
        val vm = viewModel(repository)

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The cards the pair already read are the truth of a minute ago; a failed refresh says it
        // could not refresh rather than emptying the page and pretending the pair has no plans.
        assertEquals("Сервер не ответил.", vm.uiState.value.error)
        assertEquals(listOf("p1"), vm.uiState.value.plans.map { it.id })
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a plan line from the other half moves the cards with no tap on this page`() {
        val repository = mockk<PlanRepository> {
            coEvery { plans("m1") } returnsMany listOf(
                ApiResult.Success(listOf(plan(status = PlanStatuses.PLANNED))),
                ApiResult.Success(listOf(plan(status = PlanStatuses.COMPLETED))),
            )
        }
        val vm = viewModel(repository)

        live.tryEmit(line(MessageKinds.PLAN_COMPLETED, own = false))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The frame is the whole notice: the pair does not have to leave and come back, and the page
        // does not have to be told twice by a skeleton — the row simply becomes the other one.
        coVerify(exactly = 2) { repository.plans("m1") }
        assertEquals(listOf(PlanStatuses.COMPLETED), vm.uiState.value.plans.map { it.status })
        assertNull(vm.uiState.value.outdated)
    }

    @Test
    fun `a plan line this build has no word for still moves the page`() {
        val repository = mockk<PlanRepository> {
            coEvery { plans("m1") } returnsMany listOf(
                ApiResult.Success(listOf(plan())),
                ApiResult.Success(listOf(plan(status = PlanStatuses.RESCHEDULED))),
            )
        }
        val vm = viewModel(repository)

        // A newer server can name a move this copy has never seen. A page that only listened to the
        // kinds it knows would keep showing the old hour as the pair's current one — the arrangement
        // moved, and the screen that could not read the word is exactly the one that has to reread.
        live.tryEmit(line("plan_moved_by_a_newer_server", own = false))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 2) { repository.plans("m1") }
        assertEquals(listOf(PlanStatuses.RESCHEDULED), vm.uiState.value.plans.map { it.status })
    }

    @Test
    fun `a sentence the other half typed leaves the plan where it stands`() {
        val repository = repo()
        val vm = viewModel(repository)

        live.tryEmit(line(MessageKinds.TEXT, own = false))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Somebody said a word to their pair. Nothing about the arrangement moved, so a read here
        // would be a request that answers nothing.
        coVerify(exactly = 1) { repository.plans("m1") }
        assertEquals(listOf("p1"), vm.uiState.value.plans.map { it.id })
    }

    @Test
    fun `this person's own plan line asks for no second read`() {
        val repository = repo()
        val vm = viewModel(repository)

        // The write that put this line in the thread already read the page back; the frame arriving
        // afterwards is the same fact coming home, and a second read would be the pair paying twice.
        live.tryEmit(line(MessageKinds.PLAN_AGREED, own = true))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repository.plans("m1") }
    }

    @Test
    fun `a move the page cannot read back is named and its rows stay`() {
        val repository = mockk<PlanRepository> {
            coEvery { plans("m1") } returnsMany listOf(
                ApiResult.Success(listOf(plan())),
                ApiResult.Error(500, "Сервер не ответил."),
                ApiResult.Success(listOf(plan(status = PlanStatuses.COMPLETED))),
            )
        }
        val vm = viewModel(repository)

        live.tryEmit(line(MessageKinds.PLAN_CANCELLED, own = false))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The socket has now said the arrangement moved and this copy did not get the new one. The
        // rows stay — they are what the pair last saw the server agree on — but they are named as that.
        assertEquals(PLAN_NOT_CURRENT_WORD, vm.uiState.value.outdated)
        assertEquals(listOf("p1"), vm.uiState.value.plans.map { it.id })

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.outdated)
        assertEquals(listOf(PlanStatuses.COMPLETED), vm.uiState.value.plans.map { it.status })
    }

    /**
     * The pair's own two words — where, and what they said about it — leave as the two fields the
     * contract splits, and the card decides which of them moved by reading the row it already holds.
     * A save therefore has four shapes worth pinning: both words new, one word new while the other
     * stays off the wire, a field rubbed clean travelling as its own erasure, and a tap that moved
     * neither costing no request at all.
     */
    @Test
    fun `a saved place and note leave as the two fields the contract splits`() {
        val repository = repo()
        val vm = viewModel(repository)

        vm.saveWords("p1", "Кофейня у парка", "Возьму зонт")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) {
            repository.editWords("p1", "Кофейня у парка", "Возьму зонт", false, false)
        }
        coVerify(exactly = 2) { repository.plans("m1") }
        assertTrue(vm.uiState.value.busy.isEmpty())
        assertTrue(vm.uiState.value.tapErrors.isEmpty())
    }

    @Test
    fun `a word the person left as the row holds it is not sent back to be written again`() {
        val repository = repo(
            ApiResult.Success(
                listOf(plan(place = "Кофейня у парка", note = null)),
            ),
        )
        coEvery { repository.editWords("p1", null, "Позвоню у входа", false, false) } returns
            ApiResult.Success(Unit)
        val vm = viewModel(repository)

        // The editor prefills the place with the stored word, so a save that changed only the note has
        // to leave the place out; sending it would put the other half's row through a write nobody asked for.
        vm.saveWords("p1", "Кофейня у парка", "Позвоню у входа")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repository.editWords("p1", null, "Позвоню у входа", false, false) }
    }

    @Test
    fun `a field rubbed clean goes out as its own erasure`() {
        val repository = repo(
            ApiResult.Success(
                listOf(plan(place = "Кофейня у парка", note = "Возьму зонт")),
            ),
        )
        // Stubbed as the exact call: `any()` on the two word fields would not answer a save that
        // carries a null, and a save that clears a word is exactly a call that carries one.
        coEvery { repository.editWords("p1", null, null, true, false) } returns ApiResult.Success(Unit)
        val vm = viewModel(repository)

        // Blank text is not what the server accepts for a place, so the erasure is said by its flag —
        // and the note, still holding its stored word, is not touched by this tap.
        vm.saveWords("p1", "", "Возьму зонт")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repository.editWords("p1", null, null, true, false) }
        coVerify(exactly = 2) { repository.plans("m1") }
    }

    @Test
    fun `a tap that moved neither of the two words costs the pair no request`() {
        val repository = repo(ApiResult.Success(listOf(plan(place = "Кофейня у парка", note = null))))
        val vm = viewModel(repository)

        vm.saveWords("p1", "  Кофейня у парка ", "")

        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Whitespace around a word is the same word, and an empty field over a plan that never named
        // one has nothing to erase: the tap is dropped rather than paid for with a save that could
        // only answer «ничего не изменилось».
        coVerify(exactly = 0) { repository.editWords(any(), any(), any(), any(), any()) }
        coVerify(exactly = 1) { repository.plans("m1") }
        assertTrue(vm.uiState.value.busy.isEmpty())
    }

    @Test
    fun `a second save on a plan that is still answering sends nothing`() {
        val repository = repo()
        coEvery { repository.editWords(any(), any(), any(), any(), any()) } coAnswers {
            delay(200)
            ApiResult.Success(Unit)
        }
        val vm = viewModel(repository)

        vm.saveWords("p1", "Кофейня у парка", "Возьму зонт")
        vm.saveWords("p1", "Библиотека", "Возьму зонт")
        assertTrue(vm.uiState.value.busy.contains("p1"))

        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The card holds one write at a time: two saves for one plan would ask the pair to hold whichever
        // of the two the server answered last.
        coVerify(exactly = 1) { repository.editWords(any(), any(), any(), any(), any()) }
    }

    @Test
    fun `a refused save names its card, says why and asks for no read`() {
        val repository = repo()
        coEvery { repository.editWords(any(), any(), any(), any(), any()) } returns
            ApiResult.Error(409, "Эта встреча уже закрыта — отменена, состоялась или отклонена. Менять в ней нечего.")
        val vm = viewModel(repository)

        vm.saveWords("p1", "Кофейня у парка", "Возьму зонт")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(
            "Не удалось сохранить слова плана. Эта встреча уже закрыта — отменена, состоялась или " +
                "отклонена. Менять в ней нечего.",
            vm.uiState.value.tapErrors["p1"],
        )
        coVerify(exactly = 1) { repository.plans("m1") }
        assertTrue(vm.uiState.value.busy.isEmpty())
    }

    @Test
    fun `a word for a plan this page does not hold is dropped, not sent at a stranger's row`() {
        val repository = repo()
        val vm = viewModel(repository)

        vm.saveWords("gone", "Кофейня у парка", "Возьму зонт")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The id came from a card this visit no longer has. Asking the server about it would be a write
        // aimed at a row this person never read.
        coVerify(exactly = 0) { repository.editWords(any(), any(), any(), any(), any()) }
        assertTrue(vm.uiState.value.busy.isEmpty())
    }
}

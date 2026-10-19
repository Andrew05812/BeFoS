package app.befos.presentation.plans

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.domain.repository.PlanRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The plan's chronology, read once and read again only when the person asks.
 *
 * The page is opened from a card the list already holds, and the server answers the plan with its own
 * journal lines attached, so one read carries both — which is why this screen holds no socket of its
 * own: the pair's plans page is already listening to the thread, and a second listener would make the
 * person read one change twice. What the view model is still answerable for is the four endings a read
 * has: nothing read yet, a chronology, a refusal with no rows behind it, and a refusal over the rows
 * this device did manage to read.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PlanHistoryViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private fun line(kind: String, id: String) = Message(
        id = id, matchId = "m1", senderId = "them",
        body = "План двигался", createdAt = "2026-10-15T12:00:00+03:00",
        isRead = true, isOwn = false, kind = kind,
    )

    private fun repo(vararg pages: ApiResult<List<Message>>) = mockk<PlanRepository> {
        coEvery { history("p1") } returnsMany pages.toList()
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    private fun opened(vararg pages: ApiResult<List<Message>>): Pair<PlanHistoryViewModel, PlanRepository> {
        val repository = repo(*pages)
        val vm = PlanHistoryViewModel(repository, "p1")
        advance()
        return vm to repository
    }

    @Test
    fun `opening the page asks for the plan once and keeps the order the pair lived it`() {
        val oldest = line(MessageKinds.PLAN_PROPOSED, "l1")
        val newest = line(MessageKinds.PLAN_AGREED, "l2")
        val (vm, repository) = opened(ApiResult.Success(listOf(oldest, newest)))

        assertFalse(vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
        // The server writes the lines in the order they happened and the page shows them that way: a
        // chronology this client re-sorted would put the screen's layout above the pair's record.
        assertEquals(listOf("l1", "l2"), vm.uiState.value.events.map { it.id })
        coVerify(exactly = 1) { repository.history("p1") }
    }

    @Test
    fun `a chronology the server cannot answer is named instead of shown as an untouched plan`() {
        val (vm, _) = opened(ApiResult.Error(404, "План не найден."))

        assertFalse(vm.uiState.value.loading)
        assertEquals("План не найден.", vm.uiState.value.error)
        // Empty rows plus no error would read as «this plan never moved», which is a different claim
        // about the pair than a read that failed.
        assertTrue(vm.uiState.value.events.isEmpty())
    }

    @Test
    fun `a read that fails over kept rows leaves them standing and says they may be old`() {
        val read = listOf(line(MessageKinds.PLAN_AGREED, "l1"))
        val (vm, _) = opened(ApiResult.Success(read), ApiResult.Error(500, "Сервер не ответил."))

        vm.load()
        advance()

        // The rows are the last chronology this device has, and the pair may have moved the plan since
        // — the screen shows both facts, so the person is not left with a record that looks current.
        assertEquals(read, vm.uiState.value.events)
        assertEquals("Сервер не ответил.", vm.uiState.value.error)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a retry replaces the old chronology and retires the doubt`() {
        val (vm, _) = opened(
            ApiResult.Success(listOf(line(MessageKinds.PLAN_AGREED, "l1"))),
            ApiResult.Error(500, "Сервер не ответил."),
            ApiResult.Success(listOf(line(MessageKinds.PLAN_CANCELLED, "l2"))),
        )

        vm.load()
        advance()
        assertEquals("Сервер не ответил.", vm.uiState.value.error)

        vm.load()
        advance()

        assertNull(vm.uiState.value.error)
        assertEquals(listOf("l2"), vm.uiState.value.events.map { it.id })
    }

    @Test
    fun `the read is asked of the plan the card named, and of no other`() {
        val repository = mockk<PlanRepository> {
            coEvery { history(any()) } returns ApiResult.Success(emptyList())
        }
        PlanHistoryViewModel(repository, "p1")
        advance()

        // The plan id is the whole address of the record: no person is named, and no second plan is
        // touched by opening one. The server decides whose chronology this is.
        coVerify(exactly = 1) { repository.history("p1") }
        coVerify(exactly = 0) { repository.history("p2") }
    }

    @Test
    fun `the page is loading before the first answer, not empty`() {
        val repository = mockk<PlanRepository> {
            coEvery { history("p1") } coAnswers { ApiResult.Success(emptyList()) }
        }
        val vm = PlanHistoryViewModel(repository, "p1")

        // A chronology that has not arrived is not a plan nobody moved: the skeleton and the empty
        // sentence are different claims, and the first frame has to make the first one.
        assertTrue(vm.uiState.value.loading)
        assertTrue(vm.uiState.value.events.isEmpty())

        advance()
        assertFalse(vm.uiState.value.loading)
    }
}

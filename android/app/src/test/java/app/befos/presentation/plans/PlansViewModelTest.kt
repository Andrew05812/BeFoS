package app.befos.presentation.plans

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import app.befos.domain.repository.PlanRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.runTest
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
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PlansViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private fun plan(status: String = PlanStatuses.PLANNED, id: String = "p1") = Plan(
        id = id,
        title = "Поход в кино", description = null, note = null, place = null,
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
        coEvery { cancel(any()) } returns ApiResult.Success(Unit)
        coEvery { restore(any()) } returns ApiResult.Success(Unit)
        coEvery { markAttended(any()) } returns ApiResult.Success(Unit)
        coEvery { undoAttended(any()) } returns ApiResult.Success(Unit)
    }

    private fun viewModel(repository: PlanRepository = repo()): PlansViewModel {
        val vm = PlansViewModel(repository, "m1")
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
}

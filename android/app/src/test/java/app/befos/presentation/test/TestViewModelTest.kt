package app.befos.presentation.test

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Option
import app.befos.domain.model.Question
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.TestRepository
import io.mockk.CapturingSlot
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test

/**
 * The test flow as a user actually taps it: fast, twice on the last answer, and with a
 * change of mind about an earlier one.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TestViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val catalog = listOf(
        Question(1, "ценности", "v1", "Вопрос 1", listOf(Option(11, "да"), Option(12, "нет"))),
        Question(2, "цели", "g1", "Вопрос 2", listOf(Option(21, "да"), Option(22, "нет"))),
    )

    private val progress = TestProgress(answered = 2, total = 2, percent = 100, remaining = 0, completed = true)
    private val scores = listOf(CategoryScore("ценности", "Ценности", 80, 0.5))

    private val sent: CapturingSlot<Map<Int, Int>> = slot()

    private val repo: TestRepository = mockk {
        coEvery { questions() } returns ApiResult.Success(catalog)
        coEvery { submitAnswers(capture(sent)) } returns ApiResult.Success(progress)
        coEvery { complete() } returns ApiResult.Success(scores)
    }

    @Test
    fun `a double tap on the last answer scores the test once`() = runTest {
        val vm = TestViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.select(11)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Both halves of a double tap land before the coroutine gets a turn.
        vm.select(21)
        vm.select(22)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { repo.submitAnswers(any()) }
        coVerify(exactly = 1) { repo.complete() }
        assertEquals(mapOf(1 to 11, 2 to 21), sent.captured)
        assertNotNull(vm.uiState.value.result)
        assertEquals(false, vm.uiState.value.submitting)
    }

    @Test
    fun `changing an earlier answer sends one answer per question`() = runTest {
        val vm = TestViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.select(11)
        vm.back()
        vm.select(12)
        vm.select(21)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(mapOf(1 to 12, 2 to 21), sent.captured)
        coVerify(exactly = 1) { repo.submitAnswers(any()) }
    }
}

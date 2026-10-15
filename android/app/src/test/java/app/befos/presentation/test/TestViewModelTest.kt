package app.befos.presentation.test

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Option
import app.befos.domain.model.Question
import app.befos.domain.model.TestCatalog
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.TestRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The test flow as a user actually walks it: opening a questionnaire they left halfway, changing
 * their mind, tapping twice, and tapping where the network does not answer.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TestViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val progress = TestProgress(answered = 2, total = 2, percent = 100, remaining = 0, completed = true)
    private val scores = TestProfile(categories = listOf(CategoryScore("values", "Ценности", 80, 0.5)))

    /** Every write the flow makes, plus whether the server is answering them. */
    private class Wire(var offline: Boolean = false) {
        val writes = mutableListOf<Map<Int, Int>>()
    }

    /** The catalogue as the route answers it: `marks` are the questions already holding an answer. */
    private fun catalogOf(vararg marks: Pair<Int, Int>): TestCatalog {
        val stored = marks.toMap()
        return TestCatalog(
            questions = listOf(
                Question(
                    id = 1,
                    category = "values",
                    trait = "v1",
                    text = "Вопрос 1",
                    options = listOf(Option(11, "да"), Option(12, "нет")),
                    selectedOptionId = stored[1],
                ),
                Question(
                    id = 2,
                    category = "values",
                    trait = "v2",
                    text = "Вопрос 2",
                    options = listOf(Option(21, "да"), Option(22, "нет")),
                    selectedOptionId = stored[2],
                ),
            ),
            categories = listOf(CategoryProgress("values", "Ценности", 2, stored.size)),
        )
    }

    private fun repo(loaded: TestCatalog, wire: Wire): TestRepository = mockk<TestRepository> {
        coEvery { catalog() } returns ApiResult.Success(loaded)
        coEvery { submitAnswers(any()) } answers {
            val body: Map<Int, Int> = firstArg()
            wire.writes += body
            if (wire.offline) ApiResult.Error(0, "Нет связи") else ApiResult.Success(progress)
        }
        coEvery { complete() } returns ApiResult.Success(scores)
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `an untouched test opens on its first question`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(catalogOf(), wire))
        advance()

        assertEquals(0, vm.uiState.value.index)
        assertEquals(0, vm.uiState.value.storedOnArrival)
        assertTrue(wire.writes.isEmpty())
    }

    @Test
    fun `a test left halfway opens on the question the server has no answer for`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(catalogOf(1 to 11), wire))
        advance()

        // The screen used to reopen on question one, so reaching the unanswered question meant
        // tapping past the answered ones — and every such tap overwrote the earlier answer.
        assertEquals(1, vm.uiState.value.index)
        assertEquals(mapOf(1 to 11), vm.uiState.value.answers)
        assertEquals(1, vm.uiState.value.storedOnArrival)
        // Opening is a read: nothing the person already answered is re-posted on its way in.
        assertTrue(wire.writes.isEmpty())
    }

    @Test
    fun `the category of the question the flow opens on reports how far it has come`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(catalogOf(1 to 11), wire))
        advance()

        assertEquals(listOf(CategoryProgress("values", "Ценности", 2, 1)), vm.uiState.value.categories)
        assertNotNull(vm.uiState.value.currentCategory)
        assertEquals("Ценности", vm.uiState.value.currentCategory?.label)
        assertEquals(2, vm.uiState.value.currentCategory?.total)
    }

    @Test
    fun `a tap is written before the person moves to the next question`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(catalogOf(), wire))
        advance()

        vm.select(11)
        advance()

        assertEquals(listOf(mapOf(1 to 11)), wire.writes)
        assertEquals(1, vm.uiState.value.index)
        assertTrue(vm.uiState.value.unsaved.isEmpty())
        assertNull(vm.uiState.value.pendingNotice)
    }

    @Test
    fun `a tap that did not reach the server stays visible and comes back on retry`() = runTest {
        val wire = Wire(offline = true)
        val vm = TestViewModel(repo(catalogOf(), wire))
        advance()

        vm.select(11)
        advance()

        // The choice is not taken away: it is on screen, and the notice says it is not stored yet.
        assertEquals(mapOf(1 to 11), vm.uiState.value.unsaved)
        assertNotNull(vm.uiState.value.pendingNotice)
        assertEquals(1, vm.uiState.value.index)

        wire.offline = false
        vm.retryRecords()
        advance()

        assertEquals(listOf(mapOf(1 to 11), mapOf(1 to 11)), wire.writes)
        assertTrue(vm.uiState.value.unsaved.isEmpty())
        assertNull(vm.uiState.value.pendingNotice)
    }

    @Test
    fun `a test the server would not take leaves its answers named as unsaved`() = runTest {
        val wire = Wire(offline = true)
        val testRepo = repo(catalogOf(), wire)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()
        vm.select(21)
        advance()

        // The finish batch is the one request that scores the test; when it does not land, the
        // person is left holding two taps the profile has never seen — and the flow must not
        // pretend the test is over.
        assertNotNull(vm.uiState.value.error)
        assertNull(vm.uiState.value.result)
        coVerify(exactly = 0) { testRepo.complete() }
        assertEquals(mapOf(1 to 11, 2 to 21), vm.uiState.value.unsaved)
        assertNotNull(vm.uiState.value.pendingNotice)
    }

    @Test
    fun `a change of mind while the first write is still on the wire keeps the newer answer`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(catalogOf(), wire))
        advance()

        // Neither reply has arrived yet when the person goes back and taps the other option.
        vm.select(11)
        vm.back()
        vm.select(12)
        advance()

        assertEquals(listOf(mapOf(1 to 11), mapOf(1 to 12)), wire.writes)
        // The older reply confirms nothing the person still stands on, so only the newer tap leaves
        // the pending set — and by the time both have landed the newest answer is the stored one.
        assertTrue(vm.uiState.value.unsaved.isEmpty())
        assertEquals(mapOf(1 to 12), vm.uiState.value.answers)
    }

    @Test
    fun `a double tap on the last answer scores the test once`() = runTest {
        val wire = Wire()
        val testRepo = repo(catalogOf(), wire)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()

        // Both halves of a double tap land before the coroutine gets a turn.
        vm.select(21)
        vm.select(22)
        advance()

        coVerify(exactly = 1) { testRepo.complete() }
        assertEquals(mapOf(1 to 11, 2 to 21), wire.writes.last())
        assertNotNull(vm.uiState.value.result)
        assertEquals(false, vm.uiState.value.submitting)
        assertTrue(vm.uiState.value.unsaved.isEmpty())
    }

    @Test
    fun `changing an earlier answer reaches the batch that finishes the test`() = runTest {
        val wire = Wire()
        val testRepo = repo(catalogOf(), wire)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()
        vm.back()
        vm.select(12)
        advance()
        vm.select(21)
        advance()

        // The finish batch carries the changed choice, not the one it replaced.
        assertEquals(mapOf(1 to 12, 2 to 21), wire.writes.last())
        assertEquals(
            listOf(mapOf(1 to 11), mapOf(1 to 12), mapOf(1 to 12, 2 to 21)),
            wire.writes,
        )
        coVerify(exactly = 1) { testRepo.complete() }
        assertNotNull(vm.uiState.value.result)
    }
}

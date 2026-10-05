package app.befos.presentation.matches

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.MatchSummary
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MatchesViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: MatchRepository = mockk()

    private fun match(id: String, unread: Int = 0) = MatchSummary(
        matchId = id, userId = "u-$id", name = "Анна", age = 28, city = "Москва",
        photoUrl = null, compatibility = 80, lastMessage = null, lastMessageAt = null,
        unread = unread,
    )

    @Test
    fun `a refresh that fails over a loaded list keeps it and says it may be old`() = runTest {
        coEvery { repo.matches() } returnsMany listOf(
            ApiResult.Success(listOf(match("m1"))),
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
        )

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.matches.size)

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The list stays — a pair that vanished from the answer is not a pair that ended.
        assertEquals(1, vm.uiState.value.matches.size)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)
        // It is a warning, not a replacement: the blocking error state stays unused.
        assertEquals(null, vm.uiState.value.error)
    }

    @Test
    fun `a failed refresh does not flash the skeleton`() = runTest {
        coEvery { repo.matches() } returnsMany listOf(
            ApiResult.Success(listOf(match("m1"))),
            ApiResult.Error(-1, "Нет подключения к интернету."),
        )

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.refreshSilently()
        // The check is made before the call returns, while a loading flag would blank the tab.
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a refresh that fails with nothing to show is the screen error`() = runTest {
        coEvery { repo.matches() } returnsMany listOf(
            ApiResult.Success(emptyList()),
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
        )

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(0, vm.uiState.value.matches.size)

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // An empty tab has no cached content to warn about, so the failure takes the screen:
        // "no pairs yet" would be a claim about the server, not a question to it.
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.error)
        assertEquals(null, vm.uiState.value.refreshError)
    }

    @Test
    fun `a refresh that lands clears the warning`() = runTest {
        coEvery { repo.matches() } returnsMany listOf(
            ApiResult.Success(listOf(match("m1"))),
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(listOf(match("m1", unread = 2), match("m2"))),
        )

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.matches.size)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(2, vm.uiState.value.matches.size)
        assertEquals(null, vm.uiState.value.refreshError)
    }

    @Test
    fun `a retry from the warning asks the server again`() = runTest {
        coEvery { repo.matches() } returnsMany listOf(
            ApiResult.Success(listOf(match("m1"))),
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(listOf(match("m1"), match("m2"))),
        )

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 3) { repo.matches() }
        assertEquals(2, vm.uiState.value.matches.size)
    }
}

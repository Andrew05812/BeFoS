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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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

    @Test
    fun `a row tap arms the dialog and cancelling writes nothing`() = runTest {
        coEvery { repo.matches() } returns ApiResult.Success(listOf(match("m1"), match("m2")))

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(2, vm.uiState.value.matches.size)

        vm.askDissolve(match("m1"))
        assertEquals("m1", vm.uiState.value.confirmDissolve?.matchId)

        vm.cancelDissolve()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Dismissing is not a slow yes: the list still holds both pairs and nothing was written.
        assertNull(vm.uiState.value.confirmDissolve)
        assertEquals(2, vm.uiState.value.matches.size)
        coVerify(exactly = 0) { repo.dissolve(any()) }
    }

    @Test
    fun `the row leaves only once the server says the pair is ended`() = runTest {
        coEvery { repo.matches() } returns ApiResult.Success(listOf(match("m1"), match("m2")))
        coEvery { repo.dissolve("m1") } returns ApiResult.Success(Unit)

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askDissolve(match("m1"))
        vm.confirmDissolve()
        // Before the answer lands the dialog is closed and the write is out, but the row is still
        // on the screen: 204 carries no list, so only the server's confirmation can repaint the tab.
        assertEquals(2, vm.uiState.value.matches.size)
        assertTrue(vm.uiState.value.dissolveBusy)

        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("m2"), vm.uiState.value.matches.map { it.matchId })
        assertFalse(vm.uiState.value.dissolveBusy)
        assertEquals("Пара убрана. Переписка и планы не вернутся.", vm.uiState.value.dissolveNotice)
        assertFalse(vm.uiState.value.dissolveNoticeIsError)
    }

    @Test
    fun `a refused dissolve keeps the row and says the server's words`() = runTest {
        coEvery { repo.matches() } returns ApiResult.Success(listOf(match("m1"), match("m2")))
        coEvery { repo.dissolve("m1") } returns ApiResult.Error(404, "Пара не найдена.")

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askDissolve(match("m1"))
        vm.confirmDissolve()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A row the server still holds has to stay visible with a working tap — the refusal is
        // shown in the server's own words, not wrapped in a local sentence about success.
        assertEquals(listOf("m1", "m2"), vm.uiState.value.matches.map { it.matchId })
        assertEquals("Пара не найдена.", vm.uiState.value.dissolveNotice)
        assertTrue(vm.uiState.value.dissolveNoticeIsError)
        assertFalse(vm.uiState.value.dissolveBusy)
    }

    @Test
    fun `a row tap while a dissolve is out is dropped`() = runTest {
        coEvery { repo.matches() } returns ApiResult.Success(listOf(match("m1"), match("m2")))
        coEvery { repo.dissolve("m1") } returns ApiResult.Success(Unit)

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askDissolve(match("m1"))
        vm.confirmDissolve()
        // The write has been started but not answered — this is the frame the guard is for.
        vm.askDissolve(match("m2"))
        assertNull(vm.uiState.value.confirmDissolve)

        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 1) { repo.dissolve(any()) }
        assertEquals(listOf("m2"), vm.uiState.value.matches.map { it.matchId })
    }

    @Test
    fun `a confirm with no dialog open asks the server nothing`() = runTest {
        coEvery { repo.matches() } returns ApiResult.Success(listOf(match("m1")))

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.confirmDissolve()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The dialog is the only way to name a pair for this write; tapping where no dialog stands
        // must not dissolve an arbitrary row.
        coVerify(exactly = 0) { repo.dissolve(any()) }
        assertEquals(1, vm.uiState.value.matches.size)
        assertFalse(vm.uiState.value.dissolveBusy)
    }

    @Test
    fun `the notice is taken back when the screen is done showing it`() = runTest {
        coEvery { repo.matches() } returns ApiResult.Success(listOf(match("m1"), match("m2")))
        coEvery { repo.dissolve("m1") } returns ApiResult.Success(Unit)

        val vm = MatchesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.askDissolve(match("m1"))
        vm.confirmDissolve()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Пара убрана. Переписка и планы не вернутся.", vm.uiState.value.dissolveNotice)

        vm.clearDissolveNotice()
        // The sentence goes; the list keeps the server's answer — a cleared notice is not a reset tab.
        assertNull(vm.uiState.value.dissolveNotice)
        assertEquals(1, vm.uiState.value.matches.size)
    }
}

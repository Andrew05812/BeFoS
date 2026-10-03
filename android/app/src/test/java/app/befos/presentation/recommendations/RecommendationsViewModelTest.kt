package app.befos.presentation.recommendations

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Activity
import app.befos.domain.model.Message
import app.befos.domain.model.Recommendation
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RecommendationsViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val cinema = Activity(id = 7, slug = "cinema", title = "Поход в кино", description = null, category = "culture")
    private val rec = Recommendation(activity = cinema, score = 63, position = 1, reasons = emptyList())

    private val proposal = Message(
        id = "p1", matchId = "m1", senderId = "me", body = "Идея для нас: Поход в кино. Что скажете?",
        createdAt = "2026-01-01T00:00:00", isRead = false, isOwn = true,
    )

    private fun matchRepo() = mockk<MatchRepository> {
        coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
        coEvery { selectRecommendation("m1", 7) } returns ApiResult.Success(Unit)
    }

    private fun chatRepo(result: ApiResult<Message> = ApiResult.Success(proposal)) = mockk<ChatRepository> {
        coEvery { send("m1", any()) } returns result
    }

    private fun viewModel(
        match: MatchRepository = matchRepo(),
        chat: ChatRepository = chatRepo(),
    ): RecommendationsViewModel {
        val vm = RecommendationsViewModel(match, chat, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `proposal reaches the chat before the choice is recorded`() = runTest {
        val match = matchRepo()
        val chat = chatRepo()
        val vm = viewModel(match, chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { chat.send("m1", "Идея для нас: Поход в кино. Что скажете?") }
        coVerify { match.selectRecommendation("m1", 7) }
        assertTrue(vm.uiState.value.selected.contains(7))
        assertNull(vm.uiState.value.selectError)
    }

    @Test
    fun `failed proposal rolls back and never records a choice`() = runTest {
        val match = matchRepo()
        val chat = chatRepo(ApiResult.Error(0, "Нет соединения"))
        val vm = viewModel(match, chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.selected.isEmpty())
        assertEquals("Нет соединения", vm.uiState.value.selectError)
        coVerify(exactly = 0) { match.selectRecommendation(any(), any()) }
    }

    @Test
    fun `tapping the same idea twice sends it once`() = runTest {
        val chat = chatRepo()
        val vm = viewModel(chat = chat)

        vm.select(7, cinema.title)
        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { chat.send(any(), any()) }
    }
}

package app.befos.presentation.discovery

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.DiscoveryPage
import app.befos.domain.model.LikeOutcome
import app.befos.domain.repository.DiscoveryRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class DiscoveryViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: DiscoveryRepository = mockk()

    private fun card(id: String) = DiscoveryCard(
        userId = id, name = id, age = 25, city = "Москва", about = null,
        datingGoal = "relationship", photoUrl = null, interests = emptyList(),
        compatibility = 80, sharedInterestsCount = 2,
    )

    private fun pageOf(vararg ids: String, nextCursor: String? = null, hasMore: Boolean = false) =
        ApiResult.Success(
            DiscoveryPage(ids.map(::card), nextCursor, hasMore)
        )

    @Test
    fun `like without match advances to next card`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")
        coEvery { repo.like("a") } returns ApiResult.Success(LikeOutcome(matched = false, matchId = null, compatibility = null))
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("a", vm.uiState.value.current?.userId)

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("b", vm.uiState.value.current?.userId)
        assertNull(vm.uiState.value.match)
    }

    @Test
    fun `mutual like surfaces match dialog`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.like("a") } returns ApiResult.Success(LikeOutcome(matched = true, matchId = "m1", compatibility = 91))

        val vm = DiscoveryViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.match)
        assertEquals("m1", vm.uiState.value.match?.matchId)
        // Card should not advance until the dialog is dismissed.
        assertEquals("a", vm.uiState.value.current?.userId)

        vm.dismissMatch()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNull(vm.uiState.value.match)
        assertEquals("b", vm.uiState.value.current?.userId)
    }

    @Test
    fun `the next page is asked for with the cursor the server returned`() = runTest {
        coEvery { repo.feed(any(), null) } returns pageOf("a", "b", nextCursor = "r1", hasMore = true)
        coEvery { repo.feed(any(), "r1") } returns pageOf("c", nextCursor = "r2", hasMore = false)
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("a", "b"), vm.uiState.value.cards.map { it.userId })

        // Two swipes put the viewer near the end of the first page, which is where the
        // next page is asked for.
        vm.pass()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "b", "c"), vm.uiState.value.cards.map { it.userId })
        coVerify(exactly = 1) { repo.feed(any(), "r1") }
    }

    @Test
    fun `a deck that said it was over is not asked again`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", nextCursor = null, hasMore = false)
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.pass()
        vm.pass()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // One call for the page itself; swiping past its end must not keep requesting a
        // second one, because the answer that there is nothing more has already been given.
        coVerify(exactly = 1) { repo.feed(any(), any()) }
        assertEquals(listOf("a", "b"), vm.uiState.value.cards.map { it.userId })
    }

    @Test
    fun `feed error surfaces message`() = runTest {
        coEvery { repo.feed(any(), any()) } returns ApiResult.Error(-1, "Нет подключения к интернету.")
        val vm = DiscoveryViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Нет подключения к интернету.", vm.uiState.value.error)
    }
}

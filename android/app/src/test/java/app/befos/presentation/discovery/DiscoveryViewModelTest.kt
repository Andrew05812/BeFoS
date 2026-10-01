package app.befos.presentation.discovery

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.LikeOutcome
import app.befos.domain.repository.DiscoveryRepository
import io.mockk.coEvery
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

    @Test
    fun `like without match advances to next card`() = runTest {
        coEvery { repo.feed(any(), any()) } returns ApiResult.Success(listOf(card("a"), card("b"), card("c")))
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
        coEvery { repo.feed(any(), any()) } returns ApiResult.Success(listOf(card("a"), card("b")))
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
    fun `feed error surfaces message`() = runTest {
        coEvery { repo.feed(any(), any()) } returns ApiResult.Error(-1, "Нет подключения к интернету.")
        val vm = DiscoveryViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Нет подключения к интернету.", vm.uiState.value.error)
    }
}

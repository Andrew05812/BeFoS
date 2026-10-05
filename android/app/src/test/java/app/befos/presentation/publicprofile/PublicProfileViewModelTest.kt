package app.befos.presentation.publicprofile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.safety.AnsweredUsers
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PublicProfileViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val profiles: ProfileRepository = mockk()
    private val discovery: DiscoveryRepository = mockk()
    private val safety: SafetyRepository = mockk()
    private val answered: AnsweredUsers = mockk()

    private fun profile() = PublicProfile(
        userId = "u-1", name = "Аня", age = 27, city = "Казань", about = null,
        datingGoal = "relationship", gender = "female", interests = emptyList(),
        photoUrls = emptyList(), compatibility = 74, categories = emptyList(),
        sharedInterests = emptyList(),
    )

    private fun viewModel(): PublicProfileViewModel {
        coEvery { profiles.publicProfile("u-1") } returns ApiResult.Success(profile())
        every { answered.publish(any()) } returns Unit
        return PublicProfileViewModel(profiles, discovery, safety, answered, "u-1")
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `a block tap asks before anything is sent`() = runTest {
        val vm = viewModel()
        advance()

        vm.askBlock()
        advance()

        // Blocking deletes the pair and every message in it, and the app has no way back,
        // so the icon in the top bar may not be the last thing between a person and that.
        assertEquals(true, vm.uiState.value.blockDialog)
        coVerify(exactly = 0) { safety.block(any()) }
        assertEquals(false, vm.uiState.value.gone)
    }

    @Test
    fun `cancelling the question leaves the profile open`() = runTest {
        val vm = viewModel()
        advance()

        vm.askBlock()
        vm.cancelBlock()
        advance()

        assertEquals(false, vm.uiState.value.blockDialog)
        assertEquals(false, vm.uiState.value.gone)
        coVerify(exactly = 0) { safety.block(any()) }
    }

    @Test
    fun `confirming sends one block for the profile being viewed`() = runTest {
        val sent = slot<String>()
        coEvery { safety.block(capture(sent)) } returns ApiResult.Success(Unit)
        val vm = viewModel()
        advance()

        vm.askBlock()
        vm.confirmBlock()
        advance()

        assertEquals("u-1", sent.captured)
        assertEquals(false, vm.uiState.value.blockDialog)
        assertEquals(true, vm.uiState.value.gone)
        coVerify(exactly = 1) { safety.block(any()) }
    }

    @Test
    fun `a refused block keeps the profile on screen with the reason`() = runTest {
        coEvery { safety.block("u-1") } returns ApiResult.Error(422, "Нельзя применить это к себе.")
        val vm = viewModel()
        advance()

        vm.confirmBlock()
        advance()

        // A block that never happened must not navigate away as if it had: the person would
        // leave the screen believing the stranger is gone.
        assertEquals(false, vm.uiState.value.gone)
        assertEquals("Нельзя применить это к себе.", vm.uiState.value.error)
        assertEquals(false, vm.uiState.value.busy)
    }

    @Test
    fun `a block that worked is told to the deck`() = runTest {
        coEvery { safety.block("u-1") } returns ApiResult.Success(Unit)
        val vm = viewModel()
        advance()

        vm.confirmBlock()
        advance()

        // The deck holds its page of cards in memory while this screen is open. Without the
        // answer travelling back, the next card is the person just removed, and tapping them
        // answers «Профиль не найден».
        verify(exactly = 1) { answered.publish("u-1") }
    }

    @Test
    fun `a pass that worked is told to the deck`() = runTest {
        coEvery { discovery.pass("u-1") } returns ApiResult.Success(Unit)
        val vm = viewModel()
        advance()

        vm.pass()
        advance()

        verify(exactly = 1) { answered.publish("u-1") }
    }

    @Test
    fun `a like that worked is told to the deck`() = runTest {
        coEvery { discovery.like("u-1") } returns ApiResult.Success(
            LikeOutcome(matched = false, matchId = null, compatibility = null)
        )
        val vm = viewModel()
        advance()

        vm.like()
        advance()
        verify(exactly = 1) { answered.publish("u-1") }
    }

    @Test
    fun `a like that matched is told to the deck too`() = runTest {
        coEvery { discovery.like("u-1") } returns ApiResult.Success(
            LikeOutcome(matched = true, matchId = "m1", compatibility = 88)
        )
        val vm = viewModel()
        advance()

        vm.like()
        advance()
        // The match dialog keeps the profile open, but the like itself is already recorded.
        verify(exactly = 1) { answered.publish("u-1") }
    }

    @Test
    fun `an answer that never happened leaves the deck holding the card`() = runTest {
        coEvery { safety.block("u-1") } returns ApiResult.Error(403, "Не получилось.")
        val vm = viewModel()
        advance()

        vm.confirmBlock()
        advance()

        verify(exactly = 0) { answered.publish(any()) }
    }
}

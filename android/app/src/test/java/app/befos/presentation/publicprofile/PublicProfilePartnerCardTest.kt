package app.befos.presentation.publicprofile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.repository.TestRepository
import app.befos.domain.safety.AnsweredUsers
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/**
 * A pair reads each other's card through the route that answers a pair.
 *
 * The deck route filters by «Скрыть из подбора» and `tests/test_match_detail_after_partner_hides.py`
 * pins that it stays so: an id copied out of a link must not open a withdrawn profile. That makes it
 * the wrong route for the person sitting in the chat the card was opened from, which is why
 * `PublicProfileScreen` gains a `matchId` and this test asks which repository the card came from.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PublicProfilePartnerCardTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val profiles: ProfileRepository = mockk()
    private val discovery: DiscoveryRepository = mockk()
    private val safety: SafetyRepository = mockk()
    private val answered: AnsweredUsers = mockk()
    private val matches: MatchRepository = mockk()
    private val tests: TestRepository = mockk()

    private fun card(id: String) = PublicProfile(
        userId = id, name = "Борис", age = 31, city = "Казань", about = "О себе.",
        datingGoal = "relationship", gender = "male", interests = listOf("бег"),
        photoUrls = emptyList(), compatibility = 68, categories = emptyList(),
        sharedInterests = emptyList(),
    )

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    private fun partnerVm(matchId: String): PublicProfileViewModel {
        every { answered.publish(any()) } returns Unit
        return PublicProfileViewModel(
            profiles, discovery, safety, answered, matches, tests, userId = "", matchId = matchId,
        )
    }

    @Test
    fun `a partner card is read through the pair route and never through the deck`() = runTest {
        // The deck route is the one that answers 404 once the partner hides, so a card opened from
        // a live chat must not depend on it.
        coEvery { matches.partner("m-1") } returns ApiResult.Success(card("u-9"))

        val vm = partnerVm("m-1")
        advance()

        assertEquals("Борис", vm.uiState.value.profile?.name)
        assertEquals(true, vm.uiState.value.partner)
        coVerify(exactly = 1) { matches.partner("m-1") }
        coVerify(exactly = 0) { profiles.publicProfile(any()) }
    }

    @Test
    fun `the route that named the person is the route the safety write targets`() = runTest {
        // Opened by a pair there is no user id in the arguments at all: the id arrives with the
        // card, and blocking or reporting has to go to that id rather than to the empty string.
        coEvery { matches.partner("m-1") } returns ApiResult.Success(card("u-9"))
        val blocked = slot<String>()
        coEvery { safety.block(capture(blocked)) } returns ApiResult.Success(Unit)

        val vm = partnerVm("m-1")
        advance()
        vm.askBlock()
        vm.confirmBlock()
        advance()

        assertEquals("u-9", blocked.captured)
        assertEquals(true, vm.uiState.value.gone)
    }

    @Test
    fun `a report from a partner card names the partner the pair route answered with`() = runTest {
        coEvery { matches.partner("m-1") } returns ApiResult.Success(card("u-9"))
        val reported = slot<String>()
        coEvery { safety.report(capture(reported), any(), any()) } returns ApiResult.Success(Unit)

        val vm = partnerVm("m-1")
        advance()
        vm.openReport()
        vm.setReportReason("spam")
        vm.submitReport()
        advance()

        assertEquals("u-9", reported.captured)
    }

    @Test
    fun `a stranger card still arrives by the deck route`() = runTest {
        // The pair path is added, not substituted: the Discovery card opens the same screen with a
        // user id, and that read has to keep the deck's rule.
        coEvery { profiles.publicProfile("u-1") } returns ApiResult.Success(card("u-1"))
        every { answered.publish(any()) } returns Unit

        val vm = PublicProfileViewModel(
            profiles, discovery, safety, answered, matches, tests, userId = "u-1",
        )
        advance()

        assertEquals(false, vm.uiState.value.partner)
        coVerify(exactly = 1) { profiles.publicProfile("u-1") }
        coVerify(exactly = 0) { matches.partner(any()) }
    }
}

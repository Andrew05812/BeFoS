package app.befos.presentation.publicprofile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.TestProgress
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
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

/**
 * The read behind an empty band on somebody else's card.
 *
 * A band without data on this screen is the one thing the reader can still change, and what it can
 * be changed into comes from their own section counts — so the card has to ask the test route for
 * them. It asks the way the pair page does: only when there is a band to explain. The rule matters
 * more here than on a pair page, because a card of the deck is opened again and again while a person
 * swipes, and each open would otherwise pay for a read whose answer is never printed.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PublicProfileEmptyBandTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val profiles: ProfileRepository = mockk()
    private val discovery: DiscoveryRepository = mockk()
    private val safety: SafetyRepository = mockk()
    private val answered: AnsweredUsers = mockk()
    private val matches: MatchRepository = mockk()

    private val sections = listOf(
        CategoryProgress("values", "Ценности", 5, 2),
        CategoryProgress("communication", "Общение", 5, 0),
    )

    private fun card(vararg bands: Pair<String, Boolean>) = PublicProfile(
        userId = "u-9", name = "Борис", age = 31, city = "Казань", about = "О себе.",
        datingGoal = "relationship", gender = "male", interests = listOf("бег"),
        photoUrls = emptyList(), compatibility = 68,
        categories = bands.map { (key, hasData) -> CategoryScore(key, key, 50, 0.2, hasData) },
        sharedInterests = emptyList(),
    )

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    private fun strangerVm(bands: PublicProfile, tests: TestRepository): PublicProfileViewModel {
        coEvery { profiles.publicProfile("u-9") } returns ApiResult.Success(bands)
        every { answered.publish(any()) } returns Unit
        return PublicProfileViewModel(profiles, discovery, safety, answered, matches, tests, userId = "u-9")
    }

    private fun progress(result: ApiResult<TestProgress>) = mockk<TestRepository> {
        coEvery { progress() } returns result
    }

    @Test
    fun `a card with every band measured asks nothing of the test route`() = runTest {
        val repo = progress(ApiResult.Success(TestProgress(2, 10, 20, 8, false, sections)))
        val vm = strangerVm(card("values" to true), repo)
        advance()

        assertEquals(68, vm.uiState.value.profile?.compatibility)
        assertNull(vm.uiState.value.sections)
        coVerify(exactly = 0) { repo.progress() }
    }

    @Test
    fun `an empty band buys one read of the sections, not one per band`() = runTest {
        val repo = progress(ApiResult.Success(TestProgress(2, 10, 20, 8, false, sections)))
        val vm = strangerVm(card("values" to false, "communication" to false, "interests" to false), repo)
        advance()

        // Two empty bands of the reader's own sections, and one read answers both: the counts belong
        // to the reader and do not depend on which card is open.
        assertEquals(sections, vm.uiState.value.sections)
        coVerify(exactly = 1) { repo.progress() }
    }

    @Test
    fun `counts that never arrive leave the band named but unexplained`() = runTest {
        val repo = progress(ApiResult.Error(500, "Сервер не ответил"))
        val vm = strangerVm(card("values" to false), repo)
        advance()

        // `emptyList()` and `null` are different states on purpose: with no counts the screen still
        // prints the caption and the band, but it must not match a band to a section it has not seen.
        assertEquals(emptyList<CategoryProgress>(), vm.uiState.value.sections)
        coVerify(exactly = 1) { repo.progress() }
    }

    @Test
    fun `a card that did not load asks nothing`() = runTest {
        coEvery { profiles.publicProfile("u-9") } returns ApiResult.Error(404, "Профиль не найден.")
        every { answered.publish(any()) } returns Unit
        val repo = progress(ApiResult.Success(TestProgress(2, 10, 20, 8, false, sections)))

        val vm = PublicProfileViewModel(profiles, discovery, safety, answered, matches, repo, userId = "u-9")
        advance()

        assertNull(vm.uiState.value.profile)
        assertNull(vm.uiState.value.sections)
        assertEquals("Профиль не найден.", vm.uiState.value.error)
        coVerify(exactly = 0) { repo.progress() }
    }

    @Test
    fun `a partner card asks the pair route for its bands and the test route for its gaps`() = runTest {
        coEvery { matches.partner("m-1") } returns ApiResult.Success(card("values" to false))
        every { answered.publish(any()) } returns Unit
        val repo = progress(ApiResult.Success(TestProgress(2, 10, 20, 8, false, sections)))

        val vm = PublicProfileViewModel(
            profiles, discovery, safety, answered, matches, repo, userId = "", matchId = "m-1",
        )
        advance()

        // The empty band of a partner card is explained by the same counts, so the one wording the
        // two screens share needs them on both routes.
        assertEquals(true, vm.uiState.value.partner)
        assertEquals(sections, vm.uiState.value.sections)
        coVerify(exactly = 1) { repo.progress() }
    }
}

package app.befos.presentation.pair

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.PairNextPlan
import app.befos.domain.model.PairPerson
import app.befos.domain.model.PairProfile
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The pair's reading of itself, in the four states the route can leave it in.
 *
 * The screen is one read of one document, so the transitions worth pinning are few and each has a reason:
 * the page opens on a skeleton rather than on an empty profile (a pair that has not loaded is not a pair
 * with nothing to show); a 404 is `gone` and never a retry, because asking again for a dissolved pair is
 * the dead control this app has already removed from the chat, the partner card and the map; and a
 * transient refusal stays retryable, which is the difference the flag exists to keep.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PairProfileViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val matchId = "11111111-1111-1111-1111-111111111111"

    private val profile = PairProfile(
        matchId = matchId,
        since = "2026-04-18T20:15:00+03:00",
        people = listOf(PairPerson("u1", "Аня"), PairPerson("u2", "Боря")),
        compatibility = Compatibility(
            overall = 62,
            categories = listOf(
                CategoryScore("values", "Ценности", 88, 0.25),
                CategoryScore("interests", "Интересы", 50, 0.05, hasData = false),
            ),
            strengths = emptyList(),
            differences = emptyList(),
            sharedInterests = listOf("jazz"),
            engineVersion = 3,
            bandsMeasured = 5,
            bandsTotal = 7,
            measuredWeight = 0.85,
            starter = "Начните с общего интереса: «jazz»",
        ),
        plansTotal = 2,
        plan = PairNextPlan("p7", "planned", "2026-10-17T19:00:00+03:00"),
    )

    private fun repository(result: suspend () -> ApiResult<PairProfile>) = mockk<MatchRepository> {
        coEvery { pairProfile(matchId) } coAnswers { result() }
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `the page opens on a skeleton, with nothing decided about the pair yet`() {
        val vm = PairProfileViewModel(repository { ApiResult.Success(profile) }, matchId)

        assertTrue(vm.uiState.value.loading)
        assertNull(vm.uiState.value.data)
        assertFalse(vm.uiState.value.gone)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `the document the pair was answered with is what the screen draws`() {
        val vm = PairProfileViewModel(repository { ApiResult.Success(profile) }, matchId)
        advance()

        val state = vm.uiState.value
        assertFalse(state.loading)
        assertFalse(state.gone)
        assertEquals(profile, state.data)
        // Nothing here re-counts the pair: the two people, the completeness and the plan all arrive written.
        assertEquals(listOf("Аня", "Боря"), state.data!!.people.map { it.name })
        assertEquals(5, state.data!!.compatibility.bandsMeasured)
        assertEquals("p7", state.data!!.plan?.planId)
    }

    @Test
    fun `a pair the server no longer has is gone, and saying so is the only thing left to do`() {
        val vm = PairProfileViewModel(
            repository { ApiResult.Error(404, "Этого здесь нет — возможно, анкету или чат удалили.") },
            matchId,
        )
        advance()

        val state = vm.uiState.value
        assertTrue(state.gone)
        assertFalse(state.loading)
        assertNull(state.data)
        // The screen's rule follows from the flag: `gone` is what tells it not to offer a retry.
        assertTrue(state.error!!.isNotEmpty())
    }

    @Test
    fun `a refusal that is not about the pair staying is worth asking again`() {
        val vm = PairProfileViewModel(repository { ApiResult.Error(503, "Сервер не отвечает.") }, matchId)
        advance()

        assertFalse(vm.uiState.value.gone)
        assertEquals("Сервер не отвечает.", vm.uiState.value.error)
    }

    @Test
    fun `a retry asks the same route again and re-reads what it answers now`() {
        var answer: ApiResult<PairProfile> = ApiResult.Error(500, "Сервер не ответил")
        val repo = mockk<MatchRepository>()
        coEvery { repo.pairProfile(matchId) } coAnswers { answer }
        val vm = PairProfileViewModel(repo, matchId)
        advance()
        assertNull(vm.uiState.value.data)

        answer = ApiResult.Success(profile)
        vm.load()
        advance()

        assertEquals(profile, vm.uiState.value.data)
        assertNull("a read that came back must not keep yesterday's failure on screen", vm.uiState.value.error)
        coVerify(exactly = 2) { repo.pairProfile(matchId) }
    }

    @Test
    fun `a pair with nothing standing on an hour is drawn as that pair, not as an empty plan`() {
        val noPlan = profile.copy(plansTotal = 0, plan = null)
        val vm = PairProfileViewModel(repository { ApiResult.Success(noPlan) }, matchId)
        advance()

        assertNull(vm.uiState.value.data?.plan)
        assertEquals(0, vm.uiState.value.data?.plansTotal)
    }
}

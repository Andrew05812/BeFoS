package app.befos.presentation.compatibility

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.TestRepository
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The four things this page can be, and the fifth it can be told it is.
 *
 * `gone` is the shape stage 125 had to copy in: the compatibility route answers 404 for a pair that has
 * dissolved, and the screen used to fold that into the same branch as a timeout — which left a «Повторить»
 * button standing over a read that can never succeed. The chat learned this the hard way, the pair pages
 * after it, and this page is the last of the four with the same dead control.
 *
 * The opened band lives here for the same kind of reason as the completeness counts do: what a person is
 * reading is not a momentary arrangement of pixels, and a rotation that closed it would leave the screen
 * claiming a pair's data in fewer words than the person had asked for.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class CompatibilityStatesTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val matchId = "11111111-1111-1111-1111-111111111111"

    private val document = Compatibility(
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
    )

    private fun matches(result: suspend () -> ApiResult<Compatibility>) = mockk<MatchRepository> {
        coEvery { compatibility(matchId) } coAnswers { result() }
    }

    // The document below holds one band the engine did not compare, which is exactly the case that buys the
    // extra read of the questionnaire's counts. The read is stubbed rather than left strict: this file is
    // about which of the four states the page lands in, and the counts themselves belong to
    // `CompatibilityViewModelTest`.
    private val tests = mockk<TestRepository> {
        coEvery { progress() } returns ApiResult.Success(
            TestProgress(
                answered = 6,
                total = 9,
                percent = 67,
                remaining = 3,
                completed = false,
                categories = listOf(CategoryProgress("interests", "Интересы", 4, 0)),
            ),
        )
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `the page starts on a skeleton and nothing else`() {
        val vm = CompatibilityViewModel(matches { ApiResult.Success(document) }, tests, matchId)

        // Nothing has run yet: the skeleton is the first thing the screen is handed, not a fallback.
        assertTrue(vm.uiState.value.loading)
        assertNull(vm.uiState.value.data)
        assertFalse(vm.uiState.value.gone)
    }

    @Test
    fun `a document that arrived keeps the completeness it arrived with`() {
        val vm = CompatibilityViewModel(matches { ApiResult.Success(document) }, tests, matchId)
        advance()

        val state = vm.uiState.value
        assertFalse(state.loading)
        assertEquals(62, state.data?.overall)
        assertEquals(3, state.data?.engineVersion)
        assertEquals(5, state.data?.bandsMeasured)
        assertEquals(7, state.data?.bandsTotal)
        assertEquals(0.85, state.data?.measuredWeight!!, 1e-9)
        assertEquals("Начните с общего интереса: «jazz»", state.data?.starter)
        assertNull(state.error)
        assertFalse(state.gone)
    }

    @Test
    fun `a timeout is a failure the person can ask again about`() {
        val vm = CompatibilityViewModel(matches { ApiResult.Error(500, "Сервер не ответил") }, tests, matchId)
        advance()

        val state = vm.uiState.value
        assertFalse(state.loading)
        assertNull(state.data)
        assertEquals("Сервер не ответил", state.error)
        // Retryable, and the screen's own rule: a gone pair and a refused read are not the same branch.
        assertFalse(state.gone)
    }

    @Test
    fun `a 404 says the pair is gone rather than that the read might come back`() {
        val vm = CompatibilityViewModel(
            matches { ApiResult.Error(404, "Этого здесь нет — возможно, анкету или чат удалили.") },
            tests,
            matchId,
        )
        advance()

        val state = vm.uiState.value
        assertTrue("a dissolved pair must be drawn as gone, not as an error with a retry", state.gone)
        assertFalse(state.loading)
        assertNull(state.data)
        assertTrue(state.error!!.isNotEmpty())
    }

    @Test
    fun `a retry of a read that came back stops being gone`() {
        var failure = ApiResult.Error(404, "Пары больше нет") as ApiResult<Compatibility>
        val repo = mockk<MatchRepository>()
        coEvery { repo.compatibility(matchId) } coAnswers { failure }
        val vm = CompatibilityViewModel(repo, tests, matchId)
        advance()
        assertTrue(vm.uiState.value.gone)

        // The pair re-formed under the same id, or the read was refused for a moment and the next answer
        // came: whatever the reason, `gone` is this response's claim and not a flag the screen remembers.
        failure = ApiResult.Success(document)
        vm.load()
        advance()

        assertFalse(vm.uiState.value.gone)
        assertEquals(document, vm.uiState.value.data)
    }

    @Test
    fun `opening a band keeps it open, and opening it again closes it`() {
        val vm = CompatibilityViewModel(matches { ApiResult.Success(document) }, tests, matchId)
        advance()
        assertNull(vm.uiState.value.expandedBand)

        vm.toggleBand("values")
        assertEquals("values", vm.uiState.value.expandedBand)

        vm.toggleBand("interests")
        assertEquals("interests", vm.uiState.value.expandedBand)

        vm.toggleBand("interests")
        assertNull(vm.uiState.value.expandedBand)
    }

    @Test
    fun `a reload clears the pair being gone and keeps the band the person opened`() {
        val repo = mockk<MatchRepository>()
        coEvery { repo.compatibility(matchId) } returns ApiResult.Success(document)
        val vm = CompatibilityViewModel(repo, tests, matchId)
        advance()
        vm.toggleBand("values")

        vm.load()
        advance()

        // `gone` is cleared by the same rule that keeps the band: this state belongs to the answer that has
        // just been asked for, and nothing the person did to an earlier one.
        assertFalse(vm.uiState.value.gone)
        assertEquals("values", vm.uiState.value.expandedBand)
    }
}

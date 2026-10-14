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
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * What the pair page pays for the explanation of an empty band.
 *
 * The section counts come from a route the compatibility call does not touch, so the screen asks for
 * them only when it has a band to explain: a pair with every category measured must not put an extra
 * read on the page the scale probe has already priced. A refusal of that read leaves the bands as
 * they were — named, and without counts the screen never received.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class CompatibilityViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val matchId = "11111111-1111-1111-1111-111111111111"

    /** `empty` names the bands the engine left without data. */
    private fun pair(vararg empty: String) = Compatibility(
        overall = 62,
        categories = listOf(
            CategoryScore("values", "Ценности", 70, 0.3),
            CategoryScore("personality", "Личность", 55, 0.2),
            CategoryScore("communication", "Общение", 50, 0.2, hasData = "communication" !in empty),
            CategoryScore("interests", "Интересы", 50, 0.15, hasData = "interests" !in empty),
        ),
        strengths = emptyList(),
        differences = emptyList(),
        sharedInterests = emptyList(),
    )

    private val sections = listOf(
        CategoryProgress("values", "Ценности", 5, 5),
        CategoryProgress("communication", "Общение", 4, 1),
    )

    private fun matches(data: ApiResult<Compatibility>) = mockk<MatchRepository> {
        coEvery { compatibility(matchId) } returns data
    }

    private fun tests(progress: ApiResult<TestProgress>) = mockk<TestRepository> {
        coEvery { progress() } returns progress
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `a pair with every band measured asks nothing of the test route`() {
        val repo = tests(ApiResult.Success(TestProgress(0, 9, 0, 9, false, sections)))
        val vm = CompatibilityViewModel(matches(ApiResult.Success(pair())), repo, matchId)
        advance()

        assertTrue(vm.uiState.value.data!!.categories.all { it.hasData })
        assertNull(vm.uiState.value.sections)
        coVerify(exactly = 0) { repo.progress() }
    }

    @Test
    fun `an empty band buys one read of the sections, not one per band`() {
        val repo = tests(ApiResult.Success(TestProgress(6, 9, 67, 3, false, sections)))
        val vm = CompatibilityViewModel(matches(ApiResult.Success(pair("communication", "interests"))), repo, matchId)
        advance()

        assertEquals(vm.uiState.value.sections, sections)
        coVerify(exactly = 1) { repo.progress() }
    }

    @Test
    fun `a section read that failed leaves the bands without counts`() {
        val repo = tests(ApiResult.Error(0, "Нет связи"))
        val vm = CompatibilityViewModel(matches(ApiResult.Success(pair("communication"))), repo, matchId)
        advance()

        // Empty, not null: the screen has the answer to «which section fills this band» and the
        // answer is that no counts arrived, so it prints the band and no numbers.
        assertEquals(emptyList<CategoryProgress>(), vm.uiState.value.sections)
        assertEquals(4, vm.uiState.value.data!!.categories.size)
    }

    @Test
    fun `a pair page that did not load asks nothing`() {
        val repo = tests(ApiResult.Success(TestProgress(0, 9, 0, 9, false, sections)))
        val vm = CompatibilityViewModel(matches(ApiResult.Error(500, "Сервер не ответил")), repo, matchId)
        advance()

        assertNull(vm.uiState.value.data)
        assertNull(vm.uiState.value.sections)
        assertEquals("Сервер не ответил", vm.uiState.value.error)
        coVerify(exactly = 0) { repo.progress() }
    }
}

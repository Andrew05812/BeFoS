package app.befos.presentation.test

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.core.network.befosJson
import app.befos.data.mapper.toDomain
import app.befos.data.model.TestResultDto
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.KIND_CHOICE
import app.befos.domain.model.Option
import app.befos.domain.model.Question
import app.befos.domain.model.TestCatalog
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.model.TraitAxis
import app.befos.domain.repository.TestRepository
import app.befos.presentation.universe.UniverseLayout
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * What the finished questionnaire says about the positions its bands were averaged from.
 *
 * The card under «Профиль совместимости готов» promises «Расчёт прозрачный: те же ответы всегда дают
 * тот же профиль» and then prints five percents. Twenty-one positions went into those five numbers,
 * and none of them reached the screen: the route scored the answers, kept the trait vector it had
 * just built, and answered with the averages alone. So the one place a person reads their own axis
 * positions was the Compatibility Universe of a pair — and a person who finished the questionnaire
 * on their first evening, before any pair exists, had no way to check the profile every later
 * compatibility score is computed from. They could not even tell which side of an axis an answer had
 * landed on, while the map of a match shows exactly that for the same stored answers.
 *
 * What the checks below pin: every band carries the positions it was averaged from, in the order the
 * route sent them; a band the person never answered carries none; an axis is printed with the percent
 * the universe map prints for the same value and with the word the server gave it, never a word the
 * client re-derived; and a response from a server that predates the field still paints its bands.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FinishedProfileNamesItsAxesTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val family = TraitAxis("values", "family", "Семья", 0.8, "семья в приоритете")
    private val career = TraitAxis("values", "career", "Карьера", 0.3, "работа без фанатизма")
    private val outdoor = TraitAxis("leisure", "outdoor", "Активный отдых", 1.0, "на природе/активно")

    /** The route's own order: bands as the engine sorted them, axes as the vector walked the taxonomy. */
    private val profile = TestProfile(
        categories = listOf(
            CategoryScore("values", "Ценности", 55, 0.0),
            CategoryScore("leisure", "Досуг", 100, 0.0),
        ),
        axes = listOf(family, career, outdoor),
    )

    private fun card(id: Int, section: String) = Question(
        id = id,
        category = section,
        trait = "t$id",
        text = "Вопрос $id",
        kind = KIND_CHOICE,
        options = listOf(Option(id * 10 + 1, "да"), Option(id * 10 + 2, "нет")),
        selectedOptionId = null,
    )

    private fun catalogue() = TestCatalog(
        questions = listOf(card(1, "values"), card(2, "leisure")),
        categories = listOf(
            CategoryProgress("values", "Ценности", 1, 0),
            CategoryProgress("leisure", "Досуг", 1, 0),
        ),
    )

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `each band holds the positions it was averaged from`() {
        val bands = bandsWithAxes(profile)

        assertEquals(listOf("values", "leisure"), bands.map { it.band.category })
        assertEquals(listOf(family, career), bands[0].axes)
        assertEquals(listOf(outdoor), bands[1].axes)
    }

    @Test
    fun `a band the person never answered holds no positions and opens nothing`() {
        val measured = TestProfile(
            categories = listOf(
                CategoryScore("values", "Ценности", 55, 0.0),
                // The engine left this band out of the vector entirely, so it has no positions to
                // show and the card must not offer a disclosure over an empty list.
                CategoryScore("leisure", "Досуг", 50, 0.0, hasData = false),
            ),
            axes = listOf(family, career),
        )

        val bands = bandsWithAxes(measured)

        assertEquals(listOf("values", "leisure"), bands.map { it.band.category })
        assertEquals(listOf(2, 0), bands.map { it.axes.size })
    }

    @Test
    fun `a profile from a server that never named its axes still paints its bands`() {
        val bands = bandsWithAxes(TestProfile(categories = profile.categories))

        assertEquals(listOf("values", "leisure"), bands.map { it.band.category })
        assertTrue(bands.all { it.axes.isEmpty() })
    }

    @Test
    fun `an axis is printed with the percent the universe map prints for the same answer`() {
        listOf(family, career, outdoor).forEach { axis ->
            val printed = axisLine(axis).substringAfter(": ").substringBefore("%")
            assertEquals(UniverseLayout.percentOf(axis.value.toFloat()).toString(), printed)
        }
    }

    @Test
    fun `an axis keeps the word the server gave it instead of one the client re-derives`() {
        // Half of the scale reads «умеренно» wherever the taxonomy puts the value, so a client that
        // worked the word out of the number again would disagree with the map it is quoting.
        val middling = TraitAxis("values", "family", "Семья", 0.34, "своё слово")

        assertEquals("Семья: 34% — своё слово", axisLine(middling))
    }

    @Test
    fun `a response that names its axes reaches the screen with them`() {
        val decoded = befosJson.decodeFromString<TestResultDto>(
            """{"categories": [{"category": "values", "label": "Ценности", "score": 55, "weight": 0.0,
                  "has_data": true}],
                "axes": [{"category": "values", "trait": "family", "label": "Семья", "value": 0.8,
                  "side": "семья в приоритете"}],
                "completed_at": null}"""
        ).toDomain()

        assertEquals(listOf("values"), decoded.categories.map { it.category })
        assertEquals(listOf(family), decoded.axes)
    }

    @Test
    fun `a response that does not name them is still read as the profile it was`() {
        val fromOldServer = befosJson.decodeFromString<TestResultDto>(
            """{"categories": [{"category": "values", "label": "Ценности", "score": 55, "weight": 0.0}],
                "completed_at": null}"""
        ).toDomain()

        assertEquals(listOf("values"), fromOldServer.categories.map { it.category })
        assertTrue(fromOldServer.axes.isEmpty())
    }

    @Test
    fun `the profile the route comes back with keeps its positions on the finished screen`() = runTest {
        val testRepo = mockk<TestRepository> {
            coEvery { catalog() } returns ApiResult.Success(catalogue())
            coEvery { submitAnswers(any()) } returns ApiResult.Success(
                TestProgress(answered = 2, total = 2, percent = 100, remaining = 0, completed = true)
            )
            coEvery { complete() } returns ApiResult.Success(profile)
        }
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()
        vm.select(21)
        advance()

        // The last card is answered, so the flow scored the questionnaire and this is the profile the
        // person is shown: the same positions the route sent, not only the averages of them.
        assertEquals(profile, vm.uiState.value.result)
        assertEquals(listOf(family, career, outdoor), vm.uiState.value.result?.axes)
    }
}

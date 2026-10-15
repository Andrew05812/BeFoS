package app.befos.presentation.profile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.core.network.befosJson
import app.befos.data.mapper.toDomain
import app.befos.data.model.TestProfileDto
import app.befos.data.model.TestResultDto
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.model.TraitAxis
import app.befos.domain.repository.TestRepository
import app.befos.presentation.test.axisLine
import app.befos.presentation.test.bandsWithAxes
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.time.ZoneId
import kotlin.coroutines.Continuation

/**
 * Reading one's own compatibility profile back, long after the evening it was scored.
 *
 * Measured before this screen existed: `TestProfile` was produced by `POST /tests/complete` and
 * consumed by nothing else — no route, no entry, no way to reopen it. A person who finished the
 * questionnaire, closed the app and came back a week later had the profile on the server and not
 * one place to read it, while the same stored answers were still visible to their partner in the
 * universe map of a pair.
 *
 * What the checks below pin, in the order the screen can fail them:
 *
 *  1. The screen paints what the engine stores — the bands, the positions under them, and the
 *     moment the profile was last rebuilt — without scoring anything on the way in.
 *  2. The read and the scoring agree: the same stored profile reaches both screens as the same
 *     lines, so a person cannot see two numbers for one set of answers.
 *  3. Absence is named as absence. A profile the engine never scored stays empty, a counter that
 *     did not arrive is not printed as «0%», and no percent is put on screen that the server did
 *     not give.
 *  4. The gaps come from the route that counts sections, so this screen is not a third place that
 *     counts answered questions its own way.
 *  5. Coming back from the questionnaire replaces numbers the engine rescored while the person was
 *     away; a refresh that fails keeps the old ones and says they may be old.
 *  6. Privacy, at the shape of the call: nothing in the client can name whose profile it wants.
 *     The backend half of that — 401 for an anonymous read, no identifier in the path — is pinned
 *     on the server side.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MyProfileReadBackTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val family = TraitAxis("values", "family", "Семья", 0.8, "семья в приоритете")
    private val career = TraitAxis("values", "career", "Карьера", 0.3, "работа без фанатизма")
    private val outdoor = TraitAxis("leisure", "outdoor", "Активный отдых", 1.0, "на природе/активно")

    private val stored = TestProfile(
        categories = listOf(
            CategoryScore("values", "Ценности", 55, 0.0),
            CategoryScore("leisure", "Досуг", 100, 0.0),
        ),
        axes = listOf(family, career, outdoor),
        updatedAt = "2026-03-05T09:30:00.337135Z",
    )

    private fun progress(answered: Int, sections: List<CategoryProgress>) = TestProgress(
        answered = answered,
        total = 21,
        percent = answered * 100 / 21,
        remaining = 21 - answered,
        completed = answered >= 21,
        categories = sections,
    )

    private val twoSections = listOf(
        CategoryProgress("values", "Ценности", 8, 8),
        CategoryProgress("leisure", "Досуг", 13, 5),
    )

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    private fun opened(
        profile: ApiResult<TestProfile> = ApiResult.Success(stored),
        progress: ApiResult<TestProgress> = ApiResult.Success(progress(13, twoSections)),
    ): MyProfileViewModel {
        val repo = mockk<TestRepository> {
            coEvery { profile() } returns profile
            coEvery { progress() } returns progress
        }
        val vm = MyProfileViewModel(repo)
        advance()
        return vm
    }

    @Test
    fun `the read puts the stored bands, positions and moment on the screen without scoring`() = runTest {
        val vm = opened()

        assertEquals(stored, vm.uiState.value.profile)
        assertEquals(listOf(family, career), bandsWithAxes(vm.uiState.value.profile!!)[0].axes)
        assertEquals("2026-03-05T09:30:00.337135Z", vm.uiState.value.profile?.updatedAt)
        // Reading is not finishing: the route that writes would rescore and re-rank the deck.
        assertEquals(false, vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `the same stored profile reaches the finish card and this screen as the same lines`() {
        // One body, read through both DTOs. The scoring route and the reading route answer with the
        // same two lists built by the same server-side function; the client has to keep them the
        // same way too, or one set of answers gets printed two ways depending on which screen the
        // person happens to be standing on.
        val body = """{"categories": [{"category": "values", "label": "Ценности", "score": 55, "weight": 0.0,
                  "has_data": true}, {"category": "leisure", "label": "Досуг", "score": 100, "weight": 0.0,
                  "has_data": true}],
                "axes": [{"category": "values", "trait": "family", "label": "Семья", "value": 0.8,
                  "side": "семья в приоритете"},
                  {"category": "values", "trait": "career", "label": "Карьера", "value": 0.3,
                  "side": "работа без фанатизма"},
                  {"category": "leisure", "trait": "outdoor", "label": "Активный отдых", "value": 1.0,
                  "side": "на природе/активно"}]}"""

        val fromScoring = befosJson.decodeFromString(TestResultDto.serializer(), body).toDomain()
        val fromReading = befosJson.decodeFromString(TestProfileDto.serializer(), body).toDomain()

        fun readout(profile: TestProfile): List<String> =
            bandsWithAxes(profile).flatMap { (band, axes) ->
                listOf("${band.label} ${band.score}%") + axes.map(::axisLine)
            }

        assertEquals(fromScoring.categories, fromReading.categories)
        assertEquals(fromScoring.axes, fromReading.axes)
        assertEquals(readout(stored.copy(updatedAt = null)), readout(fromScoring))
        assertEquals(readout(fromScoring), readout(fromReading))
    }

    @Test
    fun `a profile the engine has never scored stays empty instead of a screen of zeros`() = runTest {
        val vm = opened(profile = ApiResult.Success(TestProfile(categories = emptyList(), axes = emptyList())))

        assertTrue(vm.uiState.value.profile!!.categories.isEmpty())
        assertTrue(vm.uiState.value.profile!!.axes.isEmpty())
        assertNull(vm.uiState.value.profile!!.updatedAt)
        // The head word is the one place a zero could slip in as a measurement of nothing.
        assertEquals(false, measuredWord(0).any { it.isDigit() })
    }

    @Test
    fun `a server that never named the moment gets no date`() {
        val moscow = ZoneId.of("Europe/Moscow")

        // The wire sends the engine's clock in UTC with microseconds; the person reads it on theirs.
        val line = updatedAtWord("2026-03-05T09:30:00.337135Z", moscow)!!
        assertTrue(line, line.startsWith("Обновлён "))
        assertTrue(line, line.contains("2026"))
        assertTrue(line, line.contains("12:30"))
        assertEquals(false, line.contains("09:30"))

        assertNull(updatedAtWord(null, moscow))
        assertNull(updatedAtWord("", moscow))
        assertNull(updatedAtWord("вечер зачёта", moscow))
    }

    @Test
    fun `the gaps come from the route that counts sections`() = runTest {
        val vm = opened()

        assertEquals(listOf("leisure"), vm.uiState.value.openSections.map { it.key })
        assertEquals(13, vm.uiState.value.answered)
        assertEquals(21, vm.uiState.value.total)
        assertEquals(8, vm.uiState.value.openSections[0].total - vm.uiState.value.openSections[0].answered)
    }

    @Test
    fun `a counter that did not land is named, not printed as nothing answered`() = runTest {
        val vm = opened(progress = ApiResult.Error(-1, "Нет подключения к интернету."))

        assertEquals(null, vm.uiState.value.progress)
        assertEquals(true, vm.uiState.value.progressFailed)
        // A 0% here reads as «вы не ответили ни на один», and the truth is the screen could not ask.
        assertEquals(false, coverageWord(vm.uiState.value.answered, vm.uiState.value.total, failed = true).any { it.isDigit() })
        // The profile itself is independent of the counter and stays readable.
        assertEquals(listOf("values", "leisure"), vm.uiState.value.profile?.categories?.map { it.category })
    }

    @Test
    fun `coming back from the questionnaire replaces the numbers the engine rescored`() = runTest {
        val rescored = stored.copy(
            categories = listOf(CategoryScore("values", "Ценности", 70, 0.0), stored.categories[1]),
            updatedAt = "2026-04-02T18:05:00.000001Z",
        )
        val repo = mockk<TestRepository>()
        coEvery { repo.profile() } returns ApiResult.Success(stored) andThen ApiResult.Success(rescored)
        coEvery { repo.progress() } returns ApiResult.Success(progress(13, twoSections))

        val vm = MyProfileViewModel(repo)
        advance()
        assertEquals(55, vm.uiState.value.profile?.categories?.first()?.score)

        vm.refreshSilently()
        advance()

        assertEquals(70, vm.uiState.value.profile?.categories?.first()?.score)
        assertEquals("2026-04-02T18:05:00.000001Z", vm.uiState.value.profile?.updatedAt)
        assertNull(vm.uiState.value.refreshError)
    }

    @Test
    fun `a refresh that fails keeps the numbers on screen and says they may be old`() = runTest {
        val repo = mockk<TestRepository> {
            coEvery { profile() } returns ApiResult.Success(stored)
            coEvery { progress() } returns ApiResult.Success(progress(13, twoSections))
        }
        val vm = MyProfileViewModel(repo)
        advance()
        coEvery { repo.profile() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")
        coEvery { repo.progress() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        vm.refreshSilently()
        advance()

        assertEquals(stored, vm.uiState.value.profile)
        assertEquals(13, vm.uiState.value.answered)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a first read that fails replaces the screen instead of noting over a blank`() = runTest {
        val vm = opened(profile = ApiResult.Error(401, "Сессия истекла. Войдите снова."))

        assertNull(vm.uiState.value.profile)
        assertEquals("Сессия истекла. Войдите снова.", vm.uiState.value.error)
        assertNull(vm.uiState.value.refreshError)
    }

    @Test
    fun `the entry appears once there is a profile to read and hides when the counter failed`() {
        // Nothing measured means the screen would have nothing to show but its own emptiness.
        assertEquals(false, myProfileEntryVisible(answered = 0, failed = false))
        // A counter that did not answer cannot promise there is anything behind the door.
        assertEquals(false, myProfileEntryVisible(answered = 8, failed = true))
        assertEquals(true, myProfileEntryVisible(answered = 1, failed = false))
        assertEquals(true, myProfileEntryVisible(answered = 21, failed = false))
    }

    @Test
    fun `the section gap words quote the counts the server gave`() {
        val untouched = CategoryProgress("leisure", "Досуг", 13, 0)
        val partly = CategoryProgress("leisure", "Досуг", 13, 5)

        assertTrue(sectionGapWord(untouched), sectionGapWord(untouched).contains("не начат"))
        assertTrue(sectionGapWord(untouched), sectionGapWord(untouched).contains("13"))
        assertEquals("Пройти «Досуг»", gapCtaWord(untouched))

        assertTrue(sectionGapWord(partly), sectionGapWord(partly).contains("5 из 13"))
        assertTrue(sectionGapWord(partly), sectionGapWord(partly).contains("8"))
        assertEquals("Продолжить «Досуг»", gapCtaWord(partly))
    }

    @Test
    fun `nothing in the client can name whose profile it asks for`() {
        // The person's own profile is the one route in this slice that takes no identifier at all:
        // the token decides it. A partner's profile is the contrasting case — it does take one.
        assertEquals(listOf(Continuation::class.java), parameterTypes("app.befos.domain.repository.TestRepository", "profile"))
        assertEquals(listOf(Continuation::class.java), parameterTypes("app.befos.data.remote.ApiService", "getProfile"))
        assertTrue(
            "publicProfile is the route that names a person, so the check above is not vacuous",
            parameterTypes("app.befos.domain.repository.ProfileRepository", "publicProfile").contains(String::class.java),
        )
    }

    private fun parameterTypes(className: String, methodName: String): List<Class<*>> =
        Class.forName(className).declaredMethods
            .single { it.name == methodName }
            .parameterTypes
            .toList()
}

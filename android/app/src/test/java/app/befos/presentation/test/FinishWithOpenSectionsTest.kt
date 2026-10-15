package app.befos.presentation.test

import app.befos.MainDispatcherRule
import app.befos.core.designsystem.answersWord
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Option
import app.befos.domain.model.Question
import app.befos.domain.model.TestCatalog
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.TestRepository
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * What the flow answers when a person taps the last card of the questionnaire while whole sections
 * of it are still empty — and what the line under the counter counts while they answer.
 *
 * The two come from the same response the client was already throwing away. A band the person was
 * sent into opens on its own first unanswered card (`startIndex`), so a person who came from an
 * empty stripe of the compatibility screen walks that band and reaches the last card of the test
 * without ever touching the sections that stand before it. The server then refuses to score the
 * questionnaire — `TestService.complete` answers only on a full set — and until this stage the
 * screen printed the one mapped sentence «Пройдите тест до конца, чтобы увидеть результат», which
 * names neither the number the server just counted nor the section to walk into. The same ignored
 * responses carried the per-section counts, so the line that prints «ЦЕННОСТИ · 0 из 2» kept the
 * numbers it arrived with for the whole session: a person who answered one card of a two-card
 * section read zero, and the one number the screen could show them about their own work stayed a
 * lie until reload.
 *
 * Every number asserted below is one this fake server counted, the way the route counts it: marks
 * from stored answers plus the batch just written, sections over the same catalogue.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FinishWithOpenSectionsTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val scores = TestProfile(categories = listOf(CategoryScore("leisure", "Досуг", 80, 0.0)))

    private fun card(id: Int, section: String, marked: Boolean) = Question(
        id = id,
        category = section,
        trait = "t$id",
        text = "Вопрос $id",
        options = listOf(Option(id * 10 + 1, "да"), Option(id * 10 + 2, "нет")),
        selectedOptionId = if (marked) id * 10 + 1 else null,
    )

    /**
     * The band the person was sent into, with a section before it they never touched. «Досуг» is
     * where the empty stripe of the compatibility screen put them; «Ценности» sits ahead of it in
     * the catalogue, so walking the band to its end never reaches those cards.
     */
    private fun halves() = TestCatalog(
        questions = listOf(
            card(1, "values", marked = false),
            card(2, "values", marked = false),
            card(3, "leisure", marked = false),
            card(4, "leisure", marked = false),
        ),
        categories = listOf(
            CategoryProgress("values", "Ценности", 2, 0),
            CategoryProgress("leisure", "Досуг", 2, 0),
        ),
    )

    /** One card per section, the person entered the questionnaire on its own and answered both. */
    private fun twoSections() = TestCatalog(
        questions = listOf(card(1, "values", marked = false), card(2, "leisure", marked = false)),
        categories = listOf(
            CategoryProgress("values", "Ценности", 1, 0),
            CategoryProgress("leisure", "Досуг", 1, 0),
        ),
    )

    /**
     * The route's own rule over one store: a write marks the question, the counts come from the
     * marks, and `/tests/complete` answers only when every active question holds one.
     */
    private class Server(
        private val catalogue: TestCatalog,
        private val profile: TestProfile,
    ) {
        val marks = mutableMapOf<Int, Int>()
        val writes = mutableListOf<Map<Int, Int>>()
        var offline = false
        var scoreFailure: ApiResult<TestProfile>? = null

        init {
            catalogue.questions.forEach { q -> q.selectedOptionId?.let { marks[q.id] = it } }
        }

        fun progress(): TestProgress {
            val total = catalogue.questions.size
            return TestProgress(
                answered = marks.size,
                total = total,
                percent = if (total == 0) 0 else marks.size * 100 / total,
                remaining = total - marks.size,
                completed = total > 0 && marks.size >= total,
                categories = catalogue.categories.map { band ->
                    val ofSection = catalogue.questions.filter { it.category == band.key }
                    CategoryProgress(
                        band.key, band.label, ofSection.size,
                        ofSection.count { marks.containsKey(it.id) },
                    )
                },
            )
        }

        fun submit(body: Map<Int, Int>): ApiResult<TestProgress> {
            writes += body
            if (offline) return ApiResult.Error(0, "Нет связи")
            marks.putAll(body)
            return ApiResult.Success(progress())
        }

        fun complete(): ApiResult<TestProfile> {
            scoreFailure?.let { return it }
            val state = progress()
            return if (state.completed) {
                ApiResult.Success(profile)
            } else {
                ApiResult.Error(
                    422,
                    "Test is not finished yet (${state.answered}/${state.total}).",
                )
            }
        }
    }

    private fun repo(catalogue: TestCatalog, server: Server): TestRepository = mockk<TestRepository> {
        coEvery { catalog() } returns ApiResult.Success(catalogue)
        coEvery { submitAnswers(any()) } answers { server.submit(firstArg()) }
        coEvery { complete() } coAnswers { server.complete() }
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    /** Sent into the second band of the catalogue, so the first one is walked past on the way in. */
    private fun walkIntoBand(server: Server): TestViewModel {
        val vm = TestViewModel(repo(halves(), server), startSection = "leisure")
        advance()
        return vm
    }

    @Test
    fun `a refused finish names the sections the server still counts short`() = runTest {
        val server = Server(halves(), scores)
        val vm = walkIntoBand(server)

        assertEquals(2, vm.uiState.value.index)
        vm.select(31)
        advance()
        // The last card of the questionnaire: the tap that answers it is the tap that tries to score.
        vm.select(41)
        advance()

        assertEquals(listOf(CategoryProgress("values", "Ценности", 2, 0)), vm.uiState.value.openSections)
        assertNull(vm.uiState.value.result)
        // The mapped server sentence said «пройдите тест до конца» and nothing else; the counts the
        // writes came back with say which end is short, so the raw refusal is no longer what reads.
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `the invitation quotes only numbers this response carried`() {
        val line = unfinishedWord(
            answered = 3,
            total = 4,
            open = listOf(
                CategoryProgress("leisure", "Досуг", 2, 1),
                CategoryProgress("values", "Ценности", 5, 2),
            ),
        )

        assertTrue(line, line.contains("3 ${answersWord(3)} из 4"))
        assertTrue(line, line.contains("Досуг — 1 из 2"))
        assertTrue(line, line.contains("Ценности — 2 из 5"))
        // A percent would be a second unit for a count the screen already holds in answers.
        assertFalse(line, line.contains("%"))
        // The person was sent here by their own gap, not by a partner's silence.
        assertFalse(line, line.contains("партн"))
    }

    @Test
    fun `the invitation offers the first section the server left open`() {
        val label = continueSectionWord(CategoryProgress("leisure", "Досуг", 2, 1))

        assertTrue(label, label.contains("Досуг"))
        assertTrue(label, label.startsWith("Продолжить"))
    }

    @Test
    fun `continue walks into the open section instead of back to question one`() = runTest {
        val server = Server(halves(), scores)
        val vm = walkIntoBand(server)
        vm.select(31)
        advance()
        vm.select(41)
        advance()

        assertEquals(3, vm.uiState.value.index)
        vm.goToFirstOpenSection()
        advance()

        // The values cards are the ones the server counted short, and the first of them holds no
        // answer — so the walk goes there, not back to the leisure cards the person just tapped.
        assertEquals(0, vm.uiState.value.index)
        assertEquals("Вопрос 1", vm.uiState.value.current?.text)
        assertTrue(vm.uiState.value.openSections.isEmpty())
        assertNull(vm.uiState.value.error)
        assertEquals(listOf(mapOf(3 to 31), mapOf(3 to 31, 4 to 41)), server.writes)
    }

    @Test
    fun `walking over a card one has already answered leaves it as it was`() = runTest {
        val server = Server(halves(), scores)
        val vm = walkIntoBand(server)
        vm.select(31)
        advance()
        vm.select(41)
        advance()
        vm.goToFirstOpenSection()
        advance()

        // The invitation put the person on the first empty values card.
        vm.select(11)
        advance()
        assertEquals(1, vm.uiState.value.index)

        // Back over the card tapped a moment ago and past it again. The section the server still
        // counts short is this one, so the press moves on rather than asking for a profile — and
        // passing one's own answer reads it, it does not choose it a second time.
        vm.back()
        advance()
        assertEquals(0, vm.uiState.value.index)
        vm.next()
        advance()
        assertEquals(1, vm.uiState.value.index)

        assertEquals(mapOf(3 to 31, 4 to 41), vm.uiState.value.answers.filterKeys { it >= 3 })
        assertEquals(
            listOf(mapOf(3 to 31), mapOf(3 to 31, 4 to 41), mapOf(1 to 11)),
            server.writes,
        )
    }

    @Test
    fun `a complete questionnaire gets no invitation`() = runTest {
        val server = Server(twoSections(), scores)
        val vm = TestViewModel(repo(twoSections(), server))
        advance()

        vm.select(11)
        advance()
        vm.select(21)
        advance()

        assertNotNull(vm.uiState.value.result)
        assertTrue(vm.uiState.value.openSections.isEmpty())
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a refusal the counts cannot explain is still the server's own`() = runTest {
        val server = Server(twoSections(), scores)
        val vm = TestViewModel(repo(twoSections(), server))
        advance()

        // The person answers both cards, so the counts the writes came back with say the
        // questionnaire is closed...
        vm.select(11)
        advance()
        // ...and yet scoring fails for a reason those counts do not show. An invented invitation
        // would answer a failure the client cannot see with numbers that do not describe it.
        server.scoreFailure = ApiResult.Error(500, "Сервер не ответил")
        vm.select(21)
        advance()

        assertEquals(true, server.progress().completed)
        assertTrue(vm.uiState.value.openSections.isEmpty())
        assertEquals("Сервер не ответил", vm.uiState.value.error)
        assertNull(vm.uiState.value.result)
    }

    @Test
    fun `the section line counts the answers the server confirmed`() = runTest {
        val server = Server(halves(), scores)
        val vm = TestViewModel(repo(halves(), server))
        advance()

        val values = { vm.uiState.value.categories.first { it.key == "values" } }
        assertEquals(0, values().answered)
        assertEquals(0, vm.uiState.value.currentCategory?.answered)

        vm.select(11)
        advance()

        // The line's whole purpose is what is still empty in this section, and the tap above is
        // stored: reading 0 из 2 after it told the person their own answer had not landed.
        assertEquals(1, values().answered)
        assertEquals(1, vm.uiState.value.currentCategory?.answered)
        // The section nobody has touched yet keeps the count its own writes left it with.
        assertEquals(0, vm.uiState.value.categories.first { it.key == "leisure" }.answered)
    }

    @Test
    fun `a tap the server never saw does not move the section count`() = runTest {
        val server = Server(halves(), scores).apply { offline = true }
        val vm = TestViewModel(repo(halves(), server))
        advance()

        vm.select(11)
        advance()

        // The choice stays on screen and the count does not move with it: the number next to the
        // section label is what the server holds, and a person reading 1 из 2 here would believe
        // the answer that did not land is in their profile.
        assertEquals(0, vm.uiState.value.categories.first { it.key == "values" }.answered)
        assertNotNull(vm.uiState.value.pendingNotice)

        server.offline = false
        vm.retryRecords()
        advance()

        assertEquals(1, vm.uiState.value.categories.first { it.key == "values" }.answered)
        assertNull(vm.uiState.value.pendingNotice)
    }

    @Test
    fun `the line that explains where the person was sent keeps the numbers it opened with`() = runTest {
        val server = Server(halves(), scores)
        val vm = walkIntoBand(server)

        assertEquals(2, vm.uiState.value.index)
        assertEquals(0, vm.uiState.value.openedBand?.answered)

        vm.select(31)
        advance()

        // The live count moved into the section; the sentence about why the screen did not open on
        // question one is about the arrival, and rewriting it mid-walk would make it a second
        // counter that disagrees with the first by design.
        assertEquals(1, vm.uiState.value.categories.first { it.key == "leisure" }.answered)
        assertEquals(0, vm.uiState.value.openedBand?.answered)
        assertEquals("Досуг", vm.uiState.value.openedBand?.label)
    }
}

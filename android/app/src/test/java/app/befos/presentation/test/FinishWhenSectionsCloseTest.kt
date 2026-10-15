package app.befos.presentation.test

import app.befos.MainDispatcherRule
import app.befos.core.designsystem.answersWord
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.KIND_CHOICE
import app.befos.domain.model.KIND_SCALE
import app.befos.domain.model.Option
import app.befos.domain.model.Question
import app.befos.domain.model.TestCatalog
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.TestRepository
import io.mockk.coEvery
import io.mockk.coVerify
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
 * What the flow offers the person who closed the last empty section in the middle of the catalogue.
 *
 * A questionnaire is complete when its answers are, not when its cards run out — but the client
 * asked the server for a profile only from the last card of the list (`questions.lastIndex`). That
 * held while the only way in was the beginning: walking the cards in order, the person reached the
 * end at the same moment they filled the last gap. Two later stages broke the coincidence. A band
 * of the compatibility screen sends the person into one section and out of the flow's order, and the
 * invitation after a refused scoring attempt walks them back into whichever section was short, so
 * both leave them standing on an already-answered card with every question of the questionnaire now
 * holding an answer — and with the button in front of them still reading «Далее», because the card
 * they are on is the third of five. What was left was to page through one's own answers to the end
 * of the test in order to be scored.
 *
 * The counts the person's own writes came back with already said the sections were closed, so the
 * screen has a signal for this that is not a position. Every number below is one this fake server
 * counted the way `TestService.progress` counts it: marks from stored answers plus the batch just
 * written, sections over the same catalogue.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FinishWhenSectionsCloseTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val scores = TestProfile(categories = listOf(CategoryScore("values", "Ценности", 80, 0.5)))

    private fun card(id: Int, section: String, marked: Boolean, scale: Boolean = false) = Question(
        id = id,
        category = section,
        trait = "t$id",
        text = "Вопрос $id",
        kind = if (scale) KIND_SCALE else KIND_CHOICE,
        options = if (scale) (1..4).map { Option(id * 10 + it, "уровень $it") }
        else listOf(Option(id * 10 + 1, "да"), Option(id * 10 + 2, "нет")),
        selectedOptionId = if (marked) id * 10 + 1 else null,
    )

    /**
     * The two «Ценности» cards are the gap; «Досуг» was filled on an earlier visit and sits behind
     * them, so the test ends at card five while the last empty card is the second one.
     */
    private fun valuesFirst() = TestCatalog(
        questions = listOf(
            card(1, "values", marked = false),
            card(2, "values", marked = false),
            card(3, "leisure", marked = true),
            card(4, "leisure", marked = true),
            card(5, "leisure", marked = true),
        ),
        categories = listOf(
            CategoryProgress("values", "Ценности", 2, 0),
            CategoryProgress("leisure", "Досуг", 3, 3),
        ),
    )

    /** The same questionnaire from a catalogue that does not report its sections. */
    private fun withoutSections() = TestCatalog(
        questions = valuesFirst().questions,
        categories = emptyList(),
    )

    /** Stage 86's shape: sent into the second band, with the first one left standing empty. */
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

    /** Every card but the last is answered, so the flow opens on the last card and ends there. */
    private fun gapAtTheEnd() = TestCatalog(
        questions = listOf(
            card(1, "values", marked = true),
            card(2, "values", marked = true),
            card(3, "leisure", marked = true),
            card(4, "leisure", marked = true),
            card(5, "leisure", marked = false, scale = true),
        ),
        categories = listOf(
            CategoryProgress("values", "Ценности", 2, 2),
            CategoryProgress("leisure", "Досуг", 3, 2),
        ),
    )

    /** `/tests/answers` marks the questions and answers with the counts; `/tests/complete` is the route's rule. */
    private class Server(private val catalogue: TestCatalog, private val profile: TestProfile) {
        val marks = mutableMapOf<Int, Int>()
        val writes = mutableListOf<Map<Int, Int>>()

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
            marks.putAll(body)
            return ApiResult.Success(progress())
        }

        fun complete(): ApiResult<TestProfile> {
            val state = progress()
            return if (state.completed) ApiResult.Success(profile)
            else ApiResult.Error(422, "Test is not finished yet (${state.answered}/${state.total}).")
        }
    }

    private fun repo(catalogue: TestCatalog, server: Server): TestRepository = mockk<TestRepository> {
        coEvery { catalog() } returns ApiResult.Success(catalogue)
        coEvery { submitAnswers(any()) } answers { server.submit(firstArg()) }
        coEvery { complete() } coAnswers { server.complete() }
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `closing the last empty section leaves the person on their own answered card`() = runTest {
        val catalogue = valuesFirst()
        val server = Server(catalogue, scores)
        val testRepo = repo(catalogue, server)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()
        vm.select(21)
        advance()

        // The card under the person is the third of five, and the questionnaire has no gap left:
        // the counts the two writes came back with closed the section the walk was about.
        assertEquals(2, vm.uiState.value.index)
        assertEquals(4, vm.uiState.value.questions.lastIndex)
        assertTrue(vm.uiState.value.questionnaireClosed)
        // Filling the last gap does not score anything by itself — the person was not asked to stop.
        assertNull(vm.uiState.value.result)
        coVerify(exactly = 0) { testRepo.complete() }
    }

    @Test
    fun `the press asks for the profile from a card that is not the end of the test`() = runTest {
        val catalogue = valuesFirst()
        val server = Server(catalogue, scores)
        val testRepo = repo(catalogue, server)
        val vm = TestViewModel(testRepo)
        advance()
        vm.select(11)
        advance()
        vm.select(21)
        advance()

        assertTrue(vm.uiState.value.finishesOnNext)
        vm.next()
        advance()

        assertNotNull(vm.uiState.value.result)
        coVerify(exactly = 1) { testRepo.complete() }
        assertEquals(2, vm.uiState.value.index)
        assertEquals(false, vm.uiState.value.submitting)
        assertNull(vm.uiState.value.error)
        // The batch that scored the test is the person's own set of taps, and nothing that was
        // already stored got re-posted to make the questionnaire look closed.
        assertEquals(mapOf(1 to 11, 2 to 21, 3 to 31, 4 to 41, 5 to 51), server.writes.last())
    }

    @Test
    fun `while a section is still short the same press pages to the next card`() = runTest {
        val catalogue = valuesFirst()
        val server = Server(catalogue, scores)
        val testRepo = repo(catalogue, server)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()

        // One card of the section still holds nothing, so there is no profile to ask for yet.
        assertFalse(vm.uiState.value.questionnaireClosed)
        vm.back()
        advance()
        assertEquals(0, vm.uiState.value.index)

        vm.next()
        advance()

        assertEquals(1, vm.uiState.value.index)
        assertNull(vm.uiState.value.result)
        coVerify(exactly = 0) { testRepo.complete() }
        // The pass over the card just tapped neither chose it again nor wrote it twice.
        assertEquals(listOf(mapOf(1 to 11)), server.writes)
    }

    @Test
    fun `a catalogue that reports no sections is still finished at its own last card`() = runTest {
        val catalogue = withoutSections()
        val server = Server(catalogue, scores)
        val testRepo = repo(catalogue, server)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()
        vm.select(21)
        advance()

        // The client knows both cards are answered, and still asks for nothing: the counts the
        // server confirms are the only basis for offering a profile, and this response has none.
        assertFalse(vm.uiState.value.questionnaireClosed)
        vm.next()
        advance()
        assertEquals(3, vm.uiState.value.index)
        assertNull(vm.uiState.value.result)
        coVerify(exactly = 0) { testRepo.complete() }

        vm.next()
        advance()
        assertEquals(4, vm.uiState.value.index)
        vm.next()
        advance()

        assertNotNull(vm.uiState.value.result)
        coVerify(exactly = 1) { testRepo.complete() }
    }

    @Test
    fun `the invitation counts down as the person fills the section it named`() = runTest {
        val catalogue = halves()
        val server = Server(catalogue, scores)
        val vm = TestViewModel(repo(catalogue, server), startSection = "leisure")
        advance()
        vm.select(31)
        advance()
        vm.select(41)
        advance()

        assertEquals(listOf(CategoryProgress("values", "Ценности", 2, 0)), vm.uiState.value.openSections)

        // The person did not take the invitation but walked back over their own cards and answered
        // the section from there.
        vm.back()
        vm.back()
        advance()
        assertEquals(1, vm.uiState.value.index)
        vm.select(21)
        advance()

        // The line was built from the counts, and the counts moved: keeping the numbers the refusal
        // arrived with would print an empty section under the answer that just filled part of it.
        assertEquals(listOf(CategoryProgress("values", "Ценности", 2, 1)), vm.uiState.value.openSections)
        assertFalse(vm.uiState.value.questionnaireClosed)
    }

    @Test
    fun `the invitation goes away when the last write closes the section it named`() = runTest {
        val catalogue = halves()
        val server = Server(catalogue, scores)
        val testRepo = repo(catalogue, server)
        val vm = TestViewModel(testRepo, startSection = "leisure")
        advance()
        vm.select(31)
        advance()
        vm.select(41)
        advance()
        vm.back()
        vm.back()
        advance()
        vm.select(21)
        advance()

        // Back past the card just answered to the one still empty, and fill it.
        vm.back()
        vm.back()
        advance()
        assertEquals(0, vm.uiState.value.index)
        vm.select(11)
        advance()

        // Nothing is left to walk into, so the invitation is gone — and the button that stands where
        // «Далее» stood now scores the questionnaire from the second card of four.
        assertTrue(vm.uiState.value.openSections.isEmpty())
        assertTrue(vm.uiState.value.questionnaireClosed)
        assertEquals(1, vm.uiState.value.index)
        assertNull(vm.uiState.value.error)

        vm.next()
        advance()

        assertNotNull(vm.uiState.value.result)
        // The refused attempt and the press that closed the questionnaire: the second one is the
        // profile this stage made reachable from the middle of the list.
        coVerify(exactly = 2) { testRepo.complete() }
        assertEquals(mapOf(3 to 31, 4 to 41, 2 to 21, 1 to 11), server.writes.last())
    }

    @Test
    fun `the last card keeps the finish it always had`() = runTest {
        val catalogue = halves()
        val server = Server(catalogue, scores)
        val vm = TestViewModel(repo(catalogue, server), startSection = "leisure")
        advance()

        vm.select(31)
        advance()

        // Two of four cards empty, and the position rule is untouched: standing on the last card of
        // the list is still enough on its own to ask for the profile.
        assertFalse(vm.uiState.value.questionnaireClosed)
        assertTrue(vm.uiState.value.finishesOnNext)
        assertEquals(3, vm.uiState.value.index)
    }

    @Test
    fun `the line about finishing from here quotes only the counts the writes carried`() {
        val line = closedQuestionnaireWord(answered = 5, total = 5)

        assertTrue(line, line.contains("5 ${answersWord(5)} из 5"))
        // It explains the button that is on screen, so it has to name it the way the button reads.
        assertTrue(line, line.contains("Завершить"))
        // A percent would be a second unit for a count the screen already holds in answers, and a
        // partner would be a promise no response in this flow ever made.
        assertFalse(line, line.contains("%"))
        assertFalse(line, line.contains("партн"))
    }

    @Test
    fun `closing the questionnaire on its last card needs no explanation`() = runTest {
        val catalogue = gapAtTheEnd()
        val server = Server(catalogue, scores)
        val testRepo = repo(catalogue, server)
        val vm = TestViewModel(testRepo)
        advance()

        // The only card without an answer is the last one, so the flow opened there.
        assertEquals(4, vm.uiState.value.index)
        assertFalse(vm.uiState.value.questionnaireClosed)
        assertFalse(vm.uiState.value.explainsEarlyFinish)

        // A level released on a scale stores without moving anyone: this is the one way a person
        // ends up closed and standing on the last card at the same time.
        vm.slide(51)
        advance()

        assertTrue(vm.uiState.value.questionnaireClosed)
        assertTrue(vm.uiState.value.finishesOnNext)
        // Explaining a finishing button on the card that has always finished would apologise for a
        // position the person is not in.
        assertFalse(vm.uiState.value.explainsEarlyFinish)

        vm.next()
        advance()

        assertNotNull(vm.uiState.value.result)
        coVerify(exactly = 1) { testRepo.complete() }
    }
}

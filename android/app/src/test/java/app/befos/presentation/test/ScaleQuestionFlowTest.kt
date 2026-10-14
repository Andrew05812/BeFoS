package app.befos.presentation.test

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.core.network.befosJson
import app.befos.data.mapper.toDomain
import app.befos.data.model.OptionDto
import app.befos.data.model.QuestionDto
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.TestCatalog
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
 * The questionnaire as a person walks it once some of its questions are set with a thumb instead of
 * tapped as cards.
 *
 * A card cannot mean anything but an answer, so a tap is allowed to move the flow on. A released
 * thumb is not: the person who drags past the level they meant comes back to it, and a flow that
 * turned every release into a page turn would be four taps wearing a slider. So a release stores and
 * stays, and «Далее» is what moves — which makes three things worth pinning: that a question nobody
 * has touched cannot be paged past with an invented answer, that the level the thumb was left on is
 * the one the server is told about and the one the person comes back to, and that a response which
 * never mentions how a question is asked is still answerable.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ScaleQuestionFlowTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val progress = TestProgress(answered = 2, total = 2, percent = 100, remaining = 0, completed = true)
    private val scores = listOf(CategoryScore("values", "Ценности", 80, 0.5))

    /** Every write the flow makes, in the order it makes them. */
    private class Wire {
        val writes = mutableListOf<Map<Int, Int>>()
    }

    // The fixtures are built as the route answers and mapped the way the app maps, because which
    // shape a question arrives in is exactly what this stage changed: a catalogue assembled already
    // in domain classes would leave every check below unable to see a mapper that lost the kind.
    private fun question(
        id: Int,
        trait: String,
        text: String,
        optionIds: List<Int>,
        stored: Int?,
        scale: Boolean,
    ) = QuestionDto(
        id = id,
        category = "values",
        trait = trait,
        text = text,
        position = 0,
        kind = if (scale) "scale" else "choice",
        options = optionIds.mapIndexed { i, oid -> OptionDto(oid, "$text — ${i + 1}", i) },
        selectedOptionId = stored,
    ).toDomain()

    /** One section asked two ways: a gradation on a scale, its neighbour on cards. */
    private fun scaleFirst(stored: Map<Int, Int> = emptyMap()) = TestCatalog(
        questions = listOf(
            question(1, "family", "Насколько для вас важна семья?", listOf(11, 12, 13, 14), stored[1], scale = true),
            question(2, "career", "Какую роль играет работа?", listOf(21, 22), stored[2], scale = false),
        ),
        categories = listOf(CategoryProgress("values", "Ценности", 2, stored.size)),
    )

    /** The same section with the scale last, because finishing is where the two shapes meet. */
    private fun scaleLast() = TestCatalog(
        questions = listOf(
            question(1, "career", "Какую роль играет работа?", listOf(11, 12), null, scale = false),
            question(2, "family", "Насколько для вас важна семья?", listOf(21, 22, 23, 24), null, scale = true),
        ),
        categories = listOf(CategoryProgress("values", "Ценности", 2, 0)),
    )

    /** A test long enough that going back over one's own answers does not reach its end. */
    private fun threeDeep() = TestCatalog(
        questions = scaleFirst().questions +
            question(3, "growth", "Стремитесь ли вы к саморазвитию?", listOf(31, 32), null, scale = false),
        categories = listOf(CategoryProgress("values", "Ценности", 3, 0)),
    )

    private fun repo(loaded: TestCatalog, wire: Wire): TestRepository = mockk<TestRepository> {
        coEvery { catalog() } returns ApiResult.Success(loaded)
        coEvery { submitAnswers(any()) } answers {
            wire.writes += firstArg<Map<Int, Int>>()
            ApiResult.Success(progress)
        }
        coEvery { complete() } returns ApiResult.Success(scores)
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `a question the server calls a scale reaches the screen with its own stops`() = runTest {
        val vm = TestViewModel(repo(scaleFirst(), Wire()))
        advance()

        assertTrue(vm.uiState.value.questions[0].isScale)
        // A thumb needs the question's own options to stand on: a scale that arrived without them
        // would be a slider over nothing, and the person would have no level to set.
        assertEquals(listOf(11, 12, 13, 14), vm.uiState.value.questions[0].options.map { it.id })
        assertFalse(vm.uiState.value.questions[1].isScale)
    }

    @Test
    fun `a response that does not mention the kind is still answered with cards`() {
        // The compatibility this stage has to keep: a server from before the field sends questions
        // with no `kind` at all, and a client that read that as an unknown shape would leave the
        // person looking at a question they cannot answer.
        val fromOldServer = befosJson.decodeFromString<QuestionDto>(
            """{"id": 7, "category": "values", "trait": "family", "text": "Вопрос",
               "position": 0, "options": [{"id": 71, "text": "да", "position": 0}]}"""
        )
        val fromNewServer = befosJson.decodeFromString<QuestionDto>(
            """{"id": 7, "category": "values", "trait": "family", "text": "Вопрос", "kind": "scale",
               "position": 0, "options": [{"id": 71, "text": "да", "position": 0}]}"""
        )

        assertEquals("choice", fromOldServer.toDomain().kind)
        assertFalse(fromOldServer.toDomain().isScale)
        assertTrue(fromNewServer.toDomain().isScale)
    }

    @Test
    fun `a released level is stored and leaves the person on the same question`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(scaleFirst(), wire))
        advance()

        vm.slide(13)
        advance()

        // Setting a level is a write the same size as a tap's, and it is paid before the person asks
        // to move: an app closed on that question still holds what they set there.
        assertEquals(listOf(mapOf(1 to 13)), wire.writes)
        assertEquals(mapOf(1 to 13), vm.uiState.value.answers)
        assertEquals(0, vm.uiState.value.index)
        assertTrue(vm.uiState.value.unsaved.isEmpty())
        assertNull(vm.uiState.value.pendingNotice)
    }

    @Test
    fun `Далее moves on without paying for a second write`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(scaleFirst(), wire))
        advance()

        vm.slide(13)
        advance()
        vm.next()
        advance()

        assertEquals(listOf(mapOf(1 to 13)), wire.writes)
        assertEquals(1, vm.uiState.value.index)
        assertEquals("Какую роль играет работа?", vm.uiState.value.current?.text)
    }

    @Test
    fun `a thumb nobody has released cannot be paged past`() = runTest {
        val wire = Wire()
        val testRepo = repo(scaleFirst(), wire)
        val vm = TestViewModel(testRepo)
        advance()

        vm.next()
        advance()

        // A person standing on a question they have not set has no answer to carry forward, and a
        // flow that moved anyway would either invent a level or skip the axis — either way their
        // profile would say something they never chose.
        assertEquals(0, vm.uiState.value.index)
        assertTrue(wire.writes.isEmpty())
        assertNull(vm.uiState.value.result)
        coVerify(exactly = 0) { testRepo.complete() }
    }

    @Test
    fun `Завершить on the last question scores the test with the level the person set`() = runTest {
        val wire = Wire()
        val testRepo = repo(scaleLast(), wire)
        val vm = TestViewModel(testRepo)
        advance()

        vm.select(11)
        advance()
        assertEquals(1, vm.uiState.value.index)

        vm.slide(23)
        advance()
        // The scale is the last question here, so the test ends on the person's press and not on the
        // release that set the level.
        assertNull(vm.uiState.value.result)
        coVerify(exactly = 0) { testRepo.complete() }

        vm.next()
        advance()

        assertEquals(listOf(mapOf(1 to 11), mapOf(2 to 23), mapOf(1 to 11, 2 to 23)), wire.writes)
        coVerify(exactly = 1) { testRepo.complete() }
        assertNotNull(vm.uiState.value.result)
        assertEquals(false, vm.uiState.value.submitting)
        assertTrue(vm.uiState.value.unsaved.isEmpty())
    }

    @Test
    fun `a level corrected before moving on is the one the batch carries`() = runTest {
        val wire = Wire()
        val testRepo = repo(scaleFirst(), wire)
        val vm = TestViewModel(testRepo)
        advance()

        // The thumb dragged past the level meant and came back — the ordinary case a card flow never
        // has, because a mis-tap on a card is a page turn.
        vm.slide(11)
        vm.slide(12)
        advance()
        vm.next()
        advance()
        vm.select(21)
        advance()

        assertEquals(mapOf(1 to 12, 2 to 21), wire.writes.last())
        coVerify(exactly = 1) { testRepo.complete() }
        assertEquals(12, vm.uiState.value.answers[1])
    }

    @Test
    fun `going back to a scale returns to the stop the person left it on`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(threeDeep(), wire))
        advance()

        vm.slide(14)
        advance()
        vm.next()
        vm.select(21)
        advance()
        // Two questions were left behind: the card tapped a moment ago and the scale before it.
        vm.back()
        vm.back()

        assertEquals(0, vm.uiState.value.index)
        assertEquals(14, vm.uiState.value.answers[1])
        // Reaching one's own earlier answer reads it, it does not re-post it: the third write would
        // be a change nobody made.
        assertEquals(listOf(mapOf(1 to 14), mapOf(2 to 21)), wire.writes)
    }

    @Test
    fun `a test left halfway on a scale opens where the person stopped`() = runTest {
        val wire = Wire()
        val vm = TestViewModel(repo(scaleFirst(mapOf(1 to 12)), wire))
        advance()

        // The scale question came back marked, so the flow resumes past it and the stop the person
        // set is what they see when they go back — not the middle of the line.
        assertEquals(1, vm.uiState.value.index)
        assertEquals(12, vm.uiState.value.answers[1])
        assertEquals(1, vm.uiState.value.storedOnArrival)
        assertTrue(wire.writes.isEmpty())
    }
}

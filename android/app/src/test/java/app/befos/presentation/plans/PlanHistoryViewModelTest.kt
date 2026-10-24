package app.befos.presentation.plans

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.domain.model.PlanHistory
import app.befos.domain.repository.PlanRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The plan's chronology and its reader's own word, asked in one request and written one at a time.
 *
 * The page is opened from a card the list already holds, and the server answers the plan with its own
 * journal lines and the reader's remark attached, so one read carries both — which is why this screen
 * holds no socket of its own: the pair's plans page is already listening to the thread, and a second
 * listener would make the person read one change twice. What the view model is answerable for is the
 * four endings a read has — nothing read yet, a chronology, a refusal with no rows behind it, and a
 * refusal over the rows this device did manage to read — and the endings a private write has, which
 * the checks below name one by one.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PlanHistoryViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private fun line(kind: String, id: String) = Message(
        id = id, matchId = "m1", senderId = "them",
        body = "План двигался", createdAt = "2026-10-15T12:00:00+03:00",
        isRead = true, isOwn = false, kind = kind,
    )

    private fun read(vararg ids: String, note: String? = null): ApiResult<PlanHistory> =
        ApiResult.Success(PlanHistory(ids.map { line(MessageKinds.PLAN_AGREED, it) }, myNote = note))

    private fun refused(code: Int, text: String): ApiResult<PlanHistory> = ApiResult.Error(code, text)

    private fun repo(vararg pages: ApiResult<PlanHistory>) = mockk<PlanRepository> {
        coEvery { history("p1") } returnsMany pages.toList()
        coEvery { saveNote(any(), any()) } returns ApiResult.Success(Unit)
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    private fun opened(
        vararg pages: ApiResult<PlanHistory>,
    ): Pair<PlanHistoryViewModel, PlanRepository> {
        val repository = repo(*pages)
        val vm = PlanHistoryViewModel(repository, "p1")
        advance()
        return vm to repository
    }

    @Test
    fun `opening the page asks for the plan once and keeps the order the pair lived it`() {
        val oldest = line(MessageKinds.PLAN_PROPOSED, "l1")
        val newest = line(MessageKinds.PLAN_AGREED, "l2")
        val (vm, repository) = opened(
            ApiResult.Success(PlanHistory(listOf(oldest, newest), myNote = null))
        )

        assertFalse(vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
        // The server writes the lines in the order they happened and the page shows them that way: a
        // chronology this client re-sorted would put the screen's layout above the pair's record.
        assertEquals(listOf("l1", "l2"), vm.uiState.value.events.map { it.id })
        coVerify(exactly = 1) { repository.history("p1") }
    }

    @Test
    fun `the read that carries the chronology carries the persons own word with it`() {
        val (vm, repository) = opened(read("l1", note = "взять билеты"))

        assertEquals("взять билеты", vm.uiState.value.myNote)
        // One request answers both questions. A page that asked for the remark separately would pay a
        // second read for a field the first answer already held.
        coVerify(exactly = 1) { repository.history("p1") }
    }

    @Test
    fun `a plan nobody has written a word about is empty rather than unread`() {
        val (vm, _) = opened(read("l1"))

        assertNull(vm.uiState.value.myNote)
        assertNull(vm.uiState.value.error)
        assertEquals(PLAN_NOTE_EMPTY_WORD, planNoteWord(vm.uiState.value.myNote))
    }

    @Test
    fun `a chronology the server cannot answer is named instead of shown as an untouched plan`() {
        val (vm, _) = opened(refused(404, "План не найден."))

        assertFalse(vm.uiState.value.loading)
        assertEquals("План не найден.", vm.uiState.value.error)
        // Empty rows plus no error would read as «this plan never moved», which is a different claim
        // about the pair than a read that failed.
        assertTrue(vm.uiState.value.events.isEmpty())
    }

    @Test
    fun `a read that fails over kept rows leaves them standing and says they may be old`() {
        val (vm, _) = opened(read("l1"), refused(500, "Сервер не ответил."))

        vm.load()
        advance()

        // The rows are the last chronology this device has, and the pair may have moved the plan since
        // — the screen shows both facts, so the person is not left with a record that looks current.
        assertEquals(listOf("l1"), vm.uiState.value.events.map { it.id })
        assertEquals("Сервер не ответил.", vm.uiState.value.error)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a retry replaces the old chronology and retires the doubt`() {
        val (vm, _) = opened(
            read("l1"),
            refused(500, "Сервер не ответил."),
            ApiResult.Success(
                PlanHistory(listOf(line(MessageKinds.PLAN_CANCELLED, "l2")), myNote = null)
            ),
        )

        vm.load()
        advance()
        assertEquals("Сервер не ответил.", vm.uiState.value.error)

        vm.load()
        advance()

        assertNull(vm.uiState.value.error)
        assertEquals(listOf("l2"), vm.uiState.value.events.map { it.id })
    }

    @Test
    fun `the read is asked of the plan the card named, and of no other`() {
        val repository = mockk<PlanRepository> {
            coEvery { history(any()) } returns ApiResult.Success(
                PlanHistory(emptyList(), myNote = null)
            )
        }
        PlanHistoryViewModel(repository, "p1")
        advance()

        // The plan id is the whole address of the record: no person is named, and no second plan is
        // touched by opening one. The server decides whose chronology this is.
        coVerify(exactly = 1) { repository.history("p1") }
        coVerify(exactly = 0) { repository.history("p2") }
    }

    @Test
    fun `the page is loading before the first answer, not empty`() {
        val repository = mockk<PlanRepository> {
            coEvery { history("p1") } coAnswers {
                ApiResult.Success(PlanHistory(emptyList(), myNote = null))
            }
        }
        val vm = PlanHistoryViewModel(repository, "p1")

        // A chronology that has not arrived is not a plan nobody moved: the skeleton and the empty
        // sentence are different claims, and the first frame has to make the first one.
        assertTrue(vm.uiState.value.loading)
        assertTrue(vm.uiState.value.events.isEmpty())

        advance()
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a saved word is written once and read back without turning the page into a skeleton`() {
        val (vm, repository) = opened(read("l1", note = "взять билеты"), read("l1", note = "билеты"))

        vm.saveNote("взять билеты и подъезд с торца")
        advance()

        val sent = slot<String>()
        coVerify(exactly = 1) { repository.saveNote("p1", capture(sent)) }
        assertEquals("взять билеты и подъезд с торца", sent.captured)
        // Quiet refresh: the rows the person is reading stay where they were and only the remark
        // catches up with the server. A skeleton here would blink the record away to prove a save.
        assertFalse(vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
        assertEquals("билеты", vm.uiState.value.myNote)
    }

    @Test
    fun `a word emptied by hand is sent as an erasure, not as a request nobody made`() {
        val (vm, repository) = opened(read("l1", note = "взять билеты"))

        vm.saveNote("   ")
        advance()

        // The erasure is a request of its own: the note route replaces the field, so nothing sent means
        // «стёрто». A client that could not say it would leave the person rubbing the field clean and
        // reading the old word back on the next visit.
        coVerify(exactly = 1) { repository.saveNote("p1", null) }
    }

    @Test
    fun `a word nobody changed asks for nothing`() {
        val (vm, repository) = opened(read("l1", note = "взять билеты"))

        vm.saveNote("  взять билеты  ")
        advance()

        coVerify(exactly = 0) { repository.saveNote(any(), any()) }
    }

    @Test
    fun `a refused write keeps the word the server holds and names the reason beside it`() {
        val repository = mockk<PlanRepository> {
            coEvery { history("p1") } returns ApiResult.Success(
                PlanHistory(listOf(line(MessageKinds.PLAN_AGREED, "l1")), myNote = "взять билеты")
            )
            coEvery { saveNote(any(), any()) } returns ApiResult.Error(
                404, "Этого плана в вашей паре уже нет."
            )
        }
        val vm = PlanHistoryViewModel(repository, "p1")
        advance()

        vm.saveNote("подъезд с торца")
        advance()

        // The page keeps the stored word rather than the typed one: painting a refusal as a save would
        // leave the person reading a sentence the server never took.
        assertEquals("взять билеты", vm.uiState.value.myNote)
        assertFalse(vm.uiState.value.noteBusy)
        val shown = vm.uiState.value.noteError.orEmpty()
        assertTrue(shown.startsWith(PLAN_NOTE_REFUSED_WORD))
        assertTrue(shown.contains("Этого плана"))
        assertFalse(shown.contains("подъезд"))
    }

    @Test
    fun `a second tap on a word still being written sends nothing`() {
        val repository = mockk<PlanRepository> {
            coEvery { history("p1") } returns ApiResult.Success(
                PlanHistory(listOf(line(MessageKinds.PLAN_AGREED, "l1")), myNote = "взять билеты")
            )
            coEvery { saveNote(any(), any()) } coAnswers {
                delay(200)
                ApiResult.Success(Unit)
            }
        }
        val vm = PlanHistoryViewModel(repository, "p1")
        advance()

        vm.saveNote("первое слово")
        vm.saveNote("второе слово")
        assertTrue(vm.uiState.value.noteBusy)

        advance()

        // Busy until the answer arrives, so the second tap is refused by the screen rather than paid
        // for with a second write of the same remark.
        coVerify(exactly = 1) { repository.saveNote(any(), any()) }
        assertFalse(vm.uiState.value.noteBusy)
    }

    @Test
    fun `a word longer than the server would take never reaches the network`() {
        val (vm, repository) = opened(read("l1", note = "взять билеты"))
        val tooLong = "а".repeat(PLAN_NOTE_LIMIT + 1)

        vm.saveNote(tooLong)
        advance()

        coVerify(exactly = 0) { repository.saveNote(any(), any()) }
        assertEquals(PLAN_NOTE_LIMIT_WORD, planNoteOverfall(tooLong))
        assertFalse(canSavePlanNote("взять билеты", tooLong))
    }
}

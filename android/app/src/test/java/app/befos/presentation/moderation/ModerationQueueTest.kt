package app.befos.presentation.moderation

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.ReportCard
import app.befos.domain.model.ReportDetail
import app.befos.domain.model.ReportReviewRow
import app.befos.domain.model.ReportedAccount
import app.befos.domain.model.ReportsPage
import app.befos.domain.model.Reporter
import app.befos.domain.model.ReviewOutcome
import app.befos.domain.repository.ModerationRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.time.ZoneId

/**
 * The moderation queue: what the screen asks the three protected routes for, and what it paints from
 * each answer.
 *
 * Stage 102 wrote the queue's server half and left it reachable only by `curl`; stage 103 gave it the
 * screen. The three routes read a queue that is being written while it is read, so every check here is
 * about the client keeping up honestly: a filter that goes into the request rather than trimming a page
 * locally, a next page walked by the cursor the server returned, a decision that re-reads both halves it
 * changes instead of patching the row it hoped for, and a read that never answered named as one rather
 * than drawn as an empty queue. No device is needed for any of that; which chip is painted where, and
 * whether the dialog fits under the keyboard, stay for the hand.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ModerationQueueTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val moderation: ModerationRepository = mockk()

    private fun account(
        name: String? = "Нина",
        age: Int? = 30,
        city: String? = "Казань",
        deleted: Boolean = false,
    ) = ReportedAccount(
        userId = "u-nina", name = name, age = age, city = city,
        isDeleted = deleted, isHidden = false, isModerator = false,
    )

    private fun card(
        id: String,
        status: String = "open",
        reason: String = "harassment",
        createdAt: String = "2026-10-17T09:00:00Z",
        reported: ReportedAccount = account(),
        reporterName: String? = "Лев",
    ) = ReportCard(
        id = id,
        reason = reason,
        details = "писал оскорбления в чате",
        status = status,
        createdAt = createdAt,
        reported = reported,
        reporter = Reporter(userId = "u-lev", name = reporterName),
    )

    private fun page(vararg ids: String, next: String? = null, hasMore: Boolean = false) =
        ReportsPage(reports = ids.map { card(it) }, nextCursor = next, hasMore = hasMore)

    private fun detail(
        id: String,
        status: String = "open",
        allowed: List<String> = listOf("dismissed", "reviewed", "resolved"),
        reviews: List<ReportReviewRow> = emptyList(),
    ) = ReportDetail(
        card = card(id, status),
        updatedAt = "2026-10-17T09:00:00Z",
        reviews = reviews,
        allowedNextStatuses = allowed,
    )

    private fun row(
        moderatorName: String? = "Олег",
        from: String = "open",
        to: String = "reviewed",
        decidedAt: String = "2026-10-17T10:00:00Z",
        comment: String? = "анкета проверена",
    ) = ReportReviewRow(
        id = "h1", moderatorId = "u-oleg", moderatorName = moderatorName,
        fromStatus = from, toStatus = to, comment = comment, decidedAt = decidedAt,
    )

    /** A queue holding `r1` and `r2`, already read, with nothing else standing behind it. */
    private fun queue(vararg ids: String): ModerationViewModel {
        coEvery { moderation.page(null, null) } returns ApiResult.Success(page(*ids))
        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    private fun idsOf(state: ModerationUiState) = state.reports.map { it.id }

    @Test
    fun `the first page is asked for with no filter and no cursor`() = runTest {
        val vm = queue("r1", "r2")

        coVerify(exactly = 1) { moderation.page(null, null) }
        assertEquals(listOf("r1", "r2"), idsOf(vm.uiState.value))
        assertFalse(vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a queue that never answered is named, not drawn as an empty one`() = runTest {
        coEvery { moderation.page(null, null) } returns
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // «Жалоб нет» and «мы не узнали» are different answers, and the screen picks between them on
        // this flag alone: an empty list without it would tell a moderator that nobody complained.
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.error)
        assertTrue(vm.uiState.value.reports.isEmpty())
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a filter chip asks the server for its own rows instead of trimming the page`() = runTest {
        val vm = queue("r1", "r2")
        coEvery { moderation.page("reviewed", null) } returns
            ApiResult.Success(ReportsPage(reports = listOf(card("r2", "reviewed")), nextCursor = null, hasMore = false))

        vm.setFilter("reviewed")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The queue is paged, so a filter applied to the page in hand would hide rows the server still
        // holds behind the cursor and report a status as empty because its rows had not been reached.
        coVerify(exactly = 1) { moderation.page("reviewed", null) }
        assertEquals(listOf("r2"), idsOf(vm.uiState.value))
    }

    @Test
    fun `a filter that is already the filter asks the server nothing`() = runTest {
        val vm = queue("r1")

        vm.setFilter(null)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { moderation.page(any(), any()) }
    }

    @Test
    fun `the panel does not outlive the filter that no longer holds its row`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))
        coEvery { moderation.page("resolved", null) } returns ApiResult.Success(page())

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.setComment("сначала посмотрим")
        vm.chooseStatus("resolved")

        vm.setFilter("resolved")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A decision about a complaint the new filter excludes would read as part of the set the chip
        // names, so the filter closes it rather than leaving two lists one screen apart.
        assertNull(vm.uiState.value.detail)
        assertEquals("", vm.uiState.value.comment)
        assertEquals("", vm.uiState.value.chosenStatus)
    }

    @Test
    fun `the next page follows the cursor the last page returned`() = runTest {
        coEvery { moderation.page(null, null) } returns
            ApiResult.Success(page("r1", next = "r1", hasMore = true))
        coEvery { moderation.page(null, "r1") } returns
            ApiResult.Success(page("r2", next = "r2", hasMore = false))

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The cursor is the last row's id, not a position: the queue is written while it is read, and an
        // offset would show the same complaint twice as soon as one ahead of it arrived.
        coVerify(exactly = 1) { moderation.page(null, "r1") }
        assertEquals(listOf("r1", "r2"), idsOf(vm.uiState.value))
        assertEquals("r2", vm.uiState.value.nextCursor)
        assertFalse(vm.uiState.value.hasMore)
    }

    @Test
    fun `a queue that says it holds nothing more is not asked again`() = runTest {
        coEvery { moderation.page(null, null) } returns
            ApiResult.Success(page("r1", next = "r1", hasMore = false))

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { moderation.page(any(), any()) }
    }

    @Test
    fun `a second show-more while the first is out is one read`() = runTest {
        coEvery { moderation.page(null, null) } returns
            ApiResult.Success(page("r1", next = "r1", hasMore = true))
        val gate = CompletableDeferred<ApiResult<ReportsPage>>()
        coEvery { moderation.page(null, "r1") } coAnswers { gate.await() }

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()

        coVerify(exactly = 1) { moderation.page(null, "r1") }
        assertTrue(vm.uiState.value.loadingMore)

        gate.complete(ApiResult.Success(page("r2")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("r1", "r2"), idsOf(vm.uiState.value))
        assertFalse(vm.uiState.value.loadingMore)
    }

    @Test
    fun `a lost page keeps the rows it drew and says the queue may be out of date`() = runTest {
        coEvery { moderation.page(null, null) } returns
            ApiResult.Success(page("r1", next = "r1", hasMore = true))
        coEvery { moderation.page(null, "r1") } returns
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A queue read halfway is still a queue read: the rows the server already gave stay on screen
        // and the line under them says which half is missing.
        assertEquals(listOf("r1"), idsOf(vm.uiState.value))
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)
        assertNull(vm.uiState.value.error)
        assertFalse(vm.uiState.value.loadingMore)
    }

    @Test
    fun `opening a complaint paints the history and the statuses the server named`() = runTest {
        val vm = queue("r1")
        val served = detail("r1", allowed = listOf("reviewed"))
        coEvery { moderation.detail("r1") } returns ApiResult.Success(served)

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The choices are read, not derived: computing «neither resolved nor dismissed» locally is one
        // line shorter and is how a second copy of the transition table starts.
        assertEquals(served, vm.uiState.value.detail)
        assertEquals(listOf("reviewed"), vm.uiState.value.detail?.allowedNextStatuses)
        assertFalse(vm.uiState.value.detailLoading)
        assertEquals("", vm.uiState.value.chosenStatus)
    }

    @Test
    fun `a complaint whose read left says so and leaves no panel`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns
            ApiResult.Error(404, "Этой жалобы уже нет в очереди. Обновите список.")

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.detail)
        assertFalse(vm.uiState.value.detailLoading)
        assertEquals("Этой жалобы уже нет в очереди. Обновите список.", vm.uiState.value.detailError)
    }

    @Test
    fun `a tap on a status the server no longer offers writes nothing`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1", allowed = listOf("reviewed")))

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("dismissed")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 0) { moderation.review(any(), any(), any()) }
        assertEquals("Этот статус жалобе уже недоступен. Обновите жалобу.", vm.uiState.value.decisionError)
    }

    @Test
    fun `a decision sends the note the moderator wrote, trimmed`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))
        coEvery { moderation.review(any(), any(), any()) } returns
            ApiResult.Success(ReviewOutcome("r1", "reviewed", "2026-10-17T11:00:00Z"))

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("reviewed")
        vm.setComment("  анкета проверена, парня предупредили  ")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { moderation.review("r1", "reviewed", "анкета проверена, парня предупредили") }
    }

    @Test
    fun `a note of nothing is sent as nothing rather than as a blank line`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))
        coEvery { moderation.review(any(), any(), any()) } returns
            ApiResult.Success(ReviewOutcome("r1", "reviewed", "2026-10-17T11:00:00Z"))

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("reviewed")
        vm.setComment("   ")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The server reads a missing note and a note of spaces as the same nothing when it is closing a
        // complaint; for a move that needs none, sending the spaces would put a blank line in the
        // history the next moderator has to read past.
        coVerify(exactly = 1) { moderation.review("r1", "reviewed", null) }
    }

    @Test
    fun `a decision re-reads the complaint and the queue it was drawn from`() = runTest {
        coEvery { moderation.page(null, null) } returnsMany listOf(
            ApiResult.Success(page("r1", "r2")),
            ApiResult.Success(page("r2")),
        )
        coEvery { moderation.detail("r1") } returnsMany listOf(
            ApiResult.Success(detail("r1")),
            ApiResult.Success(detail("r1", status = "resolved", allowed = emptyList(), reviews = listOf(row(to = "resolved")))),
        )
        coEvery { moderation.review("r1", "resolved", "анкета проверена") } returns
            ApiResult.Success(ReviewOutcome("r1", "resolved", "2026-10-17T11:00:00Z"))

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("resolved")
        vm.setComment("анкета проверена")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Neither half is patched from the write's own answer: the row leaves a filtered queue because
        // of the status it now holds, and a complaint that moved has different statuses left to it and
        // one more line of history, which is the record the next moderator reads.
        coVerify(exactly = 2) { moderation.detail("r1") }
        coVerify(exactly = 2) { moderation.page(null, null) }
        assertEquals(listOf("r2"), idsOf(vm.uiState.value))
        assertEquals("resolved", vm.uiState.value.detail?.card?.status)
        assertEquals(emptyList<String>(), vm.uiState.value.detail?.allowedNextStatuses)
        assertEquals(1, vm.uiState.value.detail?.reviews?.size)
        assertEquals("", vm.uiState.value.comment)
        assertEquals("", vm.uiState.value.chosenStatus)
    }

    @Test
    fun `a decision the other moderator beat keeps the panel and repeats the refusal`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))
        coEvery { moderation.review("r1", "resolved", "анкета проверена") } returns
            ApiResult.Error(409, "Жалоба уже в этом статусе.")

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("resolved")
        vm.setComment("анкета проверена")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing was written, so nothing is re-read: the note stays typed and the complaint stands as it
        // was, and the line the screen prints is the server's own reason rather than a status fallback.
        assertEquals("Жалоба уже в этом статусе.", vm.uiState.value.decisionError)
        assertEquals("анкета проверена", vm.uiState.value.comment)
        assertEquals("resolved", vm.uiState.value.chosenStatus)
        coVerify(exactly = 1) { moderation.detail("r1") }
        coVerify(exactly = 1) { moderation.page(any(), any()) }
        assertFalse(vm.uiState.value.deciding)
    }

    @Test
    fun `one decision travels at a time`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))
        val gate = CompletableDeferred<ApiResult<ReviewOutcome>>()
        coEvery { moderation.review(any(), any(), any()) } coAnswers { gate.await() }

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("reviewed")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.decide()

        // The button is disabled while the write is out; the guard here is what holds the promise when a
        // tap slips through the frame, because two writes would be two history rows for one decision.
        coVerify(exactly = 1) { moderation.review(any(), any(), any()) }
        assertTrue(vm.uiState.value.deciding)

        gate.complete(ApiResult.Success(ReviewOutcome("r1", "reviewed", "2026-10-17T11:00:00Z")))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.deciding)
    }

    @Test
    fun `a queue that will not re-read after a decision says so rather than going silent`() = runTest {
        coEvery { moderation.page(null, null) } returnsMany listOf(
            ApiResult.Success(page("r1", "r2")),
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
        )
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))
        coEvery { moderation.review(any(), any(), any()) } returns
            ApiResult.Success(ReviewOutcome("r1", "resolved", "2026-10-17T11:00:00Z"))

        val vm = ModerationViewModel(moderation)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("resolved")
        vm.decide()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The decision landed and the queue behind it may now hold a row that has moved; the screen keeps
        // the rows it has and names the read that did not come back.
        assertEquals(listOf("r1", "r2"), idsOf(vm.uiState.value))
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a note longer than the server's bound is cut before it can be refused`() = runTest {
        val vm = queue("r1")

        vm.setComment("а".repeat(MaxReviewComment + 500))

        // The number is the server's `MAX_COMMENT`; pasting a whole evening's account would otherwise
        // come back as a validation line the reader cannot act on.
        assertEquals(MaxReviewComment, vm.uiState.value.comment.length)
    }

    @Test
    fun `closing the panel throws away the note typed into it`() = runTest {
        val vm = queue("r1")
        coEvery { moderation.detail("r1") } returns ApiResult.Success(detail("r1"))

        vm.openDetail("r1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.chooseStatus("resolved")
        vm.setComment("не сохранено")
        vm.closeDetail()

        assertNull(vm.uiState.value.detail)
        assertEquals("", vm.uiState.value.comment)
        assertEquals("", vm.uiState.value.chosenStatus)
        assertNull(vm.uiState.value.decisionError)
        coVerify(exactly = 0) { moderation.review(any(), any(), any()) }
    }

    @Test
    fun `a row names an erased account instead of the name it no longer has`() {
        assertEquals("Анкета удалена", queueAccusedWord(card("r1", reported = account(deleted = true))))
        assertEquals("Нина", queueAccusedWord(card("r1")))
        assertEquals("Анкета без имени", queueAccusedWord(card("r1", reported = account(name = null))))
    }

    @Test
    fun `a row's second line is the reason and whatever the account still answers`() {
        assertEquals("Оскорбления · 30 · Казань", queueFactsWord(card("r1")))
        // An erased account answers no age and no city, and the separator only joins two things that
        // were both answered — a dangling « · » would read as a value the server left out by damage.
        assertEquals(
            "Спам",
            queueFactsWord(card("r1", reason = "spam", reported = account(age = null, city = "  "))),
        )
        assertEquals("Другое · 22", queueFactsWord(card("r1", reason = "other", reported = account(age = 22, city = null))))
    }

    @Test
    fun `a witness line that cannot read its day drops the day, not the person`() {
        val moscow = ZoneId.of("Europe/Moscow")
        assertEquals("Жалоба от Лев · 17 октября 2026", queueWitnessWord(card("r1"), moscow))
        assertEquals("Жалоба от Лев", queueWitnessWord(card("r1", createdAt = "вечер зачёта"), moscow))
        assertEquals(
            "Жалоба от аккаунта без имени",
            queueWitnessWord(card("r1", createdAt = "", reporterName = null), moscow),
        )
    }

    @Test
    fun `a history line names the hand and both statuses in Russian`() {
        val moscow = ZoneId.of("Europe/Moscow")
        assertEquals(
            "Олег: Новая → На рассмотрении · 17 октября 2026",
            reviewRowWord(row(), moscow),
        )
        assertEquals(
            "Модератор: Новая → Решена",
            reviewRowWord(row(moderatorName = null, to = "resolved", decidedAt = ""), moscow),
        )
    }
}

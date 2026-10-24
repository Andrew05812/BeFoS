package app.befos.presentation.plans

/**
 * The one word about a plan that belongs to a single person, said the way the pair reads it.
 *
 * `shared_plan_members.personal_note` lives on the reader's own member row, is returned to its author
 * alone, and never enters the pair's shared card or their journal — those are the server's rules, and
 * the sentences below are the same rules told to the person typing. A field that hides where it goes
 * is read as another note the pair shares, and the words a person chooses for it change accordingly.
 *
 * The ceiling is stated here rather than discovered on the wire: the route refuses a longer word, and
 * a page that let the person write 900 characters and then said «не удалось» would blame the network
 * for a limit the product set itself.
 */

/** The same ceiling `PlanPersonalNoteIn` holds; the two are paired by a test, not by memory. */
const val PLAN_NOTE_LIMIT = 500

const val PLAN_NOTE_OVERLINE = "Только для вас"
const val PLAN_NOTE_EMPTY_WORD = "Своего слова пока нет."
const val PLAN_NOTE_PRIVATE_WORD =
    "Его видите только вы: в общую заметку пары оно не попадает, и партнёр его не читает."
const val PLAN_NOTE_LIMIT_WORD = "Слово длиннее 500 знаков — сервер его не примет."
const val PLAN_NOTE_SAVE_WORD = "Сохранить"
const val PLAN_NOTE_CLEAR_WORD = "Снять слово"
const val PLAN_NOTE_EDIT_WORD = "Записать своё слово"

/** What the person's typing means for the remark the server holds. */
enum class PlanNoteChange {
    NOTHING,

    /** Write or replace the word with what was typed. */
    WRITE,

    /**
     * Take the word back.
     *
     * Said apart from [NOTHING] on purpose: the note route replaces its one field, so an empty body
     * means «стёрто» and not «не трогать». A client that could not tell the two apart would leave the
     * person rubbing a field clean and reading the old word back on the next visit.
     */
    CLEAR,
}

data class PlanNoteEdit(val change: PlanNoteChange, val note: String? = null) {
    /** True when the tap has nothing to say, so there is no request to make and no line to report. */
    val nothingChanged: Boolean get() = change == PlanNoteChange.NOTHING
}

/**
 * The write behind the save, read against the word the server already holds.
 *
 * Compared with the stored text rather than with empty, because the editor starts from what the plan
 * says: a person who opened it, looked, and closed it sent their own word back as a change. Whitespace
 * is the erasure, not a blank string — the route keeps no room for a word made of spaces, and the
 * phone must not ask it to.
 */
fun planNoteEdit(stored: String?, typed: String?): PlanNoteEdit {
    val text = typed?.trim()
    val kept = stored?.trim()
    return when {
        text.isNullOrEmpty() ->
            if (kept.isNullOrEmpty()) PlanNoteEdit(PlanNoteChange.NOTHING)
            else PlanNoteEdit(PlanNoteChange.CLEAR)
        text == kept -> PlanNoteEdit(PlanNoteChange.NOTHING)
        else -> PlanNoteEdit(PlanNoteChange.WRITE, text)
    }
}

/** The sentence the field shows while the typed text is still sendable, or the reason it is not. */
fun planNoteOverfall(text: String): String? =
    if (text.trim().length > PLAN_NOTE_LIMIT) PLAN_NOTE_LIMIT_WORD else null

/** What the page prints for a remark that has not been read yet, or that nobody wrote. */
fun planNoteWord(stored: String?): String = stored?.takeIf { it.isNotBlank() } ?: PLAN_NOTE_EMPTY_WORD

/** Whether the save the person is looking at can land at all. */
fun canSavePlanNote(stored: String?, typed: String?): Boolean =
    !planNoteEdit(stored, typed).nothingChanged && planNoteOverfall(typed.orEmpty()) == null

package app.befos.presentation.common

/**
 * When a paged list is allowed to ask for its next page.
 *
 * Stage 126 put this decision inline in each of the four paged screens, and stage 128 measured what that
 * decision is actually made of — the scroll position — and found it untestable where it mattered. A walk of
 * «Кто вас лайкнул» under a screen reader pressed `KEYCODE_PAGE_DOWN` fourteen times and the tree never
 * moved: the same six rows stayed on screen, no page was appended, and the walk reported the foot sentence
 * as missing. A real vertical drag does move the same list (rows 46..51 became 44..50), so the ask belongs
 * to the scroll position and to nothing else.
 *
 * Two shapes, because the four doors are not built the same way.
 *
 * [shouldAskForMoreByPixels] serves the two lists that draw every row they hold in a `Column` with
 * `verticalScroll` (the inbox and the pass list): the only distance they know is in pixels.
 * [shouldAskForMoreByIndex] serves the two `LazyColumn` lists (the account's own taps and the pairs): they
 * count rows, because they only compose the visible ones.
 *
 * Both keep the two rules stage 123 learned on a device whose database was down. A list that does not even
 * overflow the screen has already reached its end, so it asks too — otherwise a short list would sit at its
 * foot forever without ever noticing the rest behind it. And once a page has refused, the automatic walk
 * stops: [canLoadMore] is the screen's own gate, and repeating a refusal is the verb on the notice, not
 * something to do to a person while they read.
 */

/** Pixels of foot the two `verticalScroll` lists treat as "close enough to ask"; one screen-height less a
 * hand, so the page is usually in by the time the thumb stops. */
const val PAGE_PREFETCH_PX_DP: Int = 160

/** Rows the two `LazyColumn` lists treat as "close enough to ask". */
const val PAGE_PREFETCH_ITEMS: Int = 3

fun shouldAskForMoreByPixels(
    canLoadMore: Boolean,
    maxScroll: Int,
    scroll: Int,
    prefetchPx: Int,
): Boolean = canLoadMore && (maxScroll - scroll <= prefetchPx || maxScroll == 0)

fun shouldAskForMoreByIndex(
    canLoadMore: Boolean,
    totalItems: Int,
    lastVisibleIndex: Int,
    prefetchItems: Int,
): Boolean = canLoadMore && totalItems > 0 && lastVisibleIndex >= totalItems - prefetchItems

/**
 * The description a row's verb gets when a screen reader reads the button alone.
 *
 * The button and the name it belongs to are siblings in the row, so a bare label («Нравится», «Забрать
 * лайк», «Вернуть в подбор») answers with a verb and nobody. Every paged screen used to assemble the
 * sentence by its own copy of the same template; three copies is how one screen starts saying something the
 * others do not, and the sentence is the row's accessibility contract, not decoration.
 *
 * A person with no name gets the verb alone: «Лайк в ответ для» is a sentence that ends on a preposition,
 * and the app has already been caught once leaving a dangling joiner on a missing city.
 */
fun namedVerbOnRow(verb: String, person: String): String =
    if (person.isBlank()) verb else "$verb для $person"

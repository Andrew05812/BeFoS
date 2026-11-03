package app.befos.presentation.common

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The one rule that decides when a paged list asks for its next page, taken out of the four screens that had
 * it inline.
 *
 * Stage 128 measured these screens under a screen reader and found that the moment of asking is exactly the
 * part no JVM test had held. The walk of stage 127 pressed `KEYCODE_PAGE_DOWN` fourteen times on «Кто вас
 * лайкнул» and the tree never moved: the same six rows stayed on screen, no page was appended, and the walk
 * reported the foot sentence as missing. A real vertical drag does move the same list (rows 46..51 became
 * 44..50), so the ask belongs to the scroll position, and what the screens read is that position — a pixel
 * offset in the two `Column`+`verticalScroll` lists and a row index in the two `LazyColumn` lists.
 *
 * Two shapes, one behavior each. A pixel list has no items to count, so its foot is `maxValue - value`;
 * an index list knows its rows, so its foot is the last visible index. Both must keep the two facts stage
 * 123 learned on a device whose database was down: a list that does not even overflow the screen has
 * already reached its end, and once a page refused, the automatic walk stops asking — the verb on the
 * notice is the person's, not the loop's.
 */
class PagePrefetchTest {

    private val prefetchPx = 900

    @Test
    fun `a pixel list that does not overflow the screen has already reached its foot`() {
        assertTrue(shouldAskForMoreByPixels(canLoadMore = true, maxScroll = 0, scroll = 0, prefetchPx = prefetchPx))
    }

    @Test
    fun `a pixel list asks one screen-height of pixels before the bottom, not after it`() {
        assertTrue(shouldAskForMoreByPixels(true, maxScroll = 10_000, scroll = 10_000 - prefetchPx, prefetchPx))
        assertTrue(shouldAskForMoreByPixels(true, maxScroll = 10_000, scroll = 10_000 - 10, prefetchPx))
        assertFalse(shouldAskForMoreByPixels(true, maxScroll = 10_000, scroll = 10_000 - prefetchPx - 1, prefetchPx))
    }

    @Test
    fun `a pixel list far above its foot asks for nothing`() {
        assertFalse(shouldAskForMoreByPixels(true, maxScroll = 10_000, scroll = 0, prefetchPx = prefetchPx))
    }

    @Test
    fun `while a page is on the wire the same foot position asks once`() {
        assertFalse(shouldAskForMoreByPixels(canLoadMore = false, maxScroll = 10_000, scroll = 10_000, prefetchPx))
        assertFalse(shouldAskForMoreByPixels(canLoadMore = false, maxScroll = 0, scroll = 0, prefetchPx))
    }

    @Test
    fun `an index list asks when the last visible row is inside the prefetch band`() {
        assertTrue(shouldAskForMoreByIndex(true, totalItems = 50, lastVisibleIndex = 50 - 3, prefetchItems = 3))
        assertTrue(shouldAskForMoreByIndex(true, totalItems = 50, lastVisibleIndex = 49, prefetchItems = 3))
        assertFalse(shouldAskForMoreByIndex(true, totalItems = 50, lastVisibleIndex = 40, prefetchItems = 3))
    }

    @Test
    fun `an index list with nothing in it asks for nothing`() {
        assertFalse(shouldAskForMoreByIndex(true, totalItems = 0, lastVisibleIndex = -1, prefetchItems = 3))
    }

    @Test
    fun `an index list whose walk was refused stops asking at the same foot`() {
        assertFalse(shouldAskForMoreByIndex(canLoadMore = false, totalItems = 50, lastVisibleIndex = 49,
            prefetchItems = 3))
    }

    @Test
    fun `the two shapes agree about the same physical position`() {
        // 50 rows of 300 px in a 1000 px viewport: the foot is at maxScroll 14 000, and the last visible row
        // of that geometry is 46. Both rules must answer the same way at that moment — that agreement is what
        // a reader crossing from one list to another actually feels.
        val maxScroll = 50 * 300 - 1000
        assertTrue(shouldAskForMoreByPixels(true, maxScroll, scroll = maxScroll - 900, prefetchPx = 900))
        assertTrue(shouldAskForMoreByIndex(true, totalItems = 50, lastVisibleIndex = 46, prefetchItems = 3))
    }
}

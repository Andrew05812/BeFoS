/**
 * The navigation graph is built once, on the first frame of the app, and nothing in this module's unit
 * suite ever built it.
 *
 * That is how `app.befos` reached a device dead on arrival: `Routes.RECOMMENDATIONS` declares its
 * optional focus idea as `NavType.IntType` with `nullable = true`, and `NavArgument` refuses the pair —
 * the exception the library throws says it plainly, «integer does not allow nullable values». The
 * declaration runs while `NavHost` registers its destinations, so the crash is not on the road from a
 * chat card to the ideas page. It is on the road from the launcher icon to the first screen, and every
 * route behind it — the deck, the lists, the settings, this stage's own page of the account's taps —
 * never gets a chance to answer anything. 724 checks stayed green across the whole of it, because a
 * ViewModel test never asks the graph to exist.
 *
 * So the checks below ask the graph to exist, on the JVM, from the same declarations the composable
 * calls pass to `composable(route, arguments = …)`:
 *
 *  - every route's arguments have to build, which is where the illegal pair shows up;
 *  - every declared name has to be a placeholder of its own route and every placeholder has to be
 *    declared, because the second mismatch of the same kind crashes the same frame with a different
 *    message («Argument 'x' is not found in the route pattern»);
 *  - the idea a chat card puts into a route has to be the idea the page reads back, digits in and
 *    `Int` out, with a route built without one reading as `null` rather than as the row numbered zero.
 */
package app.befos.presentation.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NavigationArgumentsTest {

    /**
     * The whole graph, in the order its routes are declared.
     *
     * Building this map is the check: `navArgument { … }.build()` runs while the list is assembled, so
     * an illegal type/nullable pair throws here exactly as it throws inside `NavHost`.
     */
    @Test
    fun `every route's arguments build the way the navigator builds them on the first frame`() {
        val declared = NavArguments.byRoute()

        assertTrue("the graph declares no routes at all", declared.isNotEmpty())
        for ((route, arguments) in declared) {
            assertTrue(
                "route $route is registered with arguments = … but declares none",
                arguments.isNotEmpty(),
            )
        }
    }

    @Test
    fun `every declared argument is a placeholder of its own route and back`() {
        for ((route, arguments) in NavArguments.byRoute()) {
            val placeholders = PLACEHOLDER.findAll(route).map { it.groupValues[1] }.toList()
            val names = arguments.map { it.name }
            for (name in names) {
                assertTrue(
                    "route $route declares argument '$name', which its pattern does not offer",
                    placeholders.contains(name),
                )
            }
            for (name in placeholders) {
                assertTrue(
                    "route $route asks for {$name} but declares no argument for it",
                    names.contains(name),
                )
            }
        }
    }

    @Test
    fun `the idea a card puts into the route is the idea the page reads back`() {
        val opened = Routes.recommendations("pair-1", 7)
        assertEquals(
            "route $opened reaches the page as something else than the id it carries",
            7,
            NavArguments.focusActivityId(opened.queryActivityValue()),
        )
    }

    @Test
    fun `a route built without the idea reads as nothing rather than as idea zero`() {
        val opened = Routes.recommendations("pair-1")
        assertNull("route $opened carries an idea the page would go looking for", opened.queryActivityValue())
        assertNull(NavArguments.focusActivityId(opened.queryActivityValue()))
        // `getInt` on an absent optional answers 0, and 0 is a row the page would go looking for.
        assertNull(NavArguments.focusActivityId(""))
        assertNull(NavArguments.focusActivityId("activity"))
    }

    /** The value the `activity` query key carries in a built route, or `null` when it carries none. */
    private fun String.queryActivityValue(): String? =
        QUERY_VALUE.findAll(this)
            .firstOrNull { it.groupValues[1] == Routes.ACTIVITY_ARG }
            ?.groupValues?.get(2)

    private companion object {
        val PLACEHOLDER = Regex("\\{(\\w+)}")

        // `?name=value` — the same shape the route builder writes, read here rather than trusted.
        val QUERY_VALUE = Regex("[?&](\\w+)=([^&]*)")
    }
}

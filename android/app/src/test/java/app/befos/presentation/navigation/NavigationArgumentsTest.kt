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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Modifier

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
            NavArguments.focusActivityId(opened.queryValue(Routes.ACTIVITY_ARG)),
        )
    }

    @Test
    fun `a route built without the idea reads as nothing rather than as idea zero`() {
        val opened = Routes.recommendations("pair-1")
        assertNull("route $opened carries an idea the page would go looking for", opened.queryValue(Routes.ACTIVITY_ARG))
        assertNull(NavArguments.focusActivityId(opened.queryValue(Routes.ACTIVITY_ARG)))
        // `getInt` on an absent optional answers 0, and 0 is a row the page would go looking for.
        assertNull(NavArguments.focusActivityId(""))
        assertNull(NavArguments.focusActivityId("activity"))
    }

    /**
     * Routes that ask for a value are taken from `Routes`, not from this file's own list.
     *
     * `byRoute()` is the enumeration every check above reads, and an enumeration written by hand can
     * just be left behind: a new route carrying `{id}` with its `navArgument` written inline in
     * `BeFosNavHost` would keep this file green — the arguments would build, they would just never be
     * looked at here, which is how the graph came to be unbuildable on a device while 724 checks stayed
     * green. So the placeholder routes are gathered off `Routes` itself, and each one has to stand in
     * `byRoute()` under exactly the names its pattern offers.
     */
    @Test
    fun `every route that asks for a value is declared where this suite can build it`() {
        val patterns = routePatterns()
        val declared = NavArguments.byRoute()

        assertTrue("в `Routes` нет ни одного маршрута с местом под значение", patterns.isNotEmpty())
        for ((field, pattern) in patterns) {
            val arguments = declared[pattern]
            assertNotNull(
                "`Routes.$field` = «$pattern» просит значение и не стоит в `NavArguments.byRoute()` — " +
                    "его аргументы объявляются там, где их никто не собирает",
                arguments,
            )
            assertEquals(
                "`Routes.$field` предлагает не те имена, чем объявляет",
                PLACEHOLDER.findAll(pattern).map { it.groupValues[1] }.sorted().toList(),
                arguments!!.map { it.name }.sorted().toList(),
            )
        }
        for (pattern in declared.keys) {
            assertTrue(
                "`NavArguments.byRoute()` держит «$pattern», которого в `Routes` больше нет",
                patterns.any { (_, value) -> value == pattern },
            )
        }
    }

    /**
     * The other three optional values of the graph, read back the way the routes were built.
     *
     * `activity` already had this pair of checks because it is the one the device crash went through.
     * `section`, `draft` and `plan` are the same shape — a route assembled with a value the destination
     * looks up — and they are lost the same way: a builder that drops its argument opens the screen at
     * its beginning, and the person lands one screen away from what they tapped.
     */
    @Test
    fun `a route built with its optional value gives that value back to the page that reads it`() {
        assertEquals("relationships", Routes.test("relationships").queryValue(Routes.SECTION_ARG))
        // `matchId` живёт в пути, а не в query, — его читает не ключ, а то место, куда паттерн ставит
        // свой `{matchId}`. Без этого пара «карточка → нить» расходится молча: маршрут собирается,
        // отличается от паттерна только сегментом, и `NavHost` находит под ним другую нить.
        assertEquals("chat/m1", Routes.chat("m1").pathPart())
        assertEquals("chat/m1", Routes.chat("m1", "cGVpdmV0").pathPart())
        assertEquals("plans/m1", Routes.plans("m1", "p7").pathPart())
        assertEquals("Привет", Routes.chat("m1", "Привет").queryValue(Routes.DRAFT_ARG))
        assertEquals("p7", Routes.plans("m1", "p7").queryValue(Routes.PLAN_ARG))

        // Без значения — ничего, а не пустая строка: экран по пустой строке ищет раздел, которого нет.
        assertNull(Routes.test().queryValue(Routes.SECTION_ARG))
        assertNull(Routes.chat("m1").queryValue(Routes.DRAFT_ARG))
        assertNull(Routes.plans("m1").queryValue(Routes.PLAN_ARG))
    }

    /** The route without its query: the part that has to match the pattern's path placeholder. */
    private fun String.pathPart(): String = substringBefore("?")

    /** The value one query key of a built route carries, or `null` when the route carries none. */
    private fun String.queryValue(key: String): String? =
        QUERY_VALUE.findAll(this)
            .firstOrNull { it.groupValues[1] == key }
            ?.groupValues?.get(2)

    /** Every `const val` of [Routes] that is a route pattern with a placeholder inside it. */
    private fun routePatterns(): List<Pair<String, String>> =
        Routes::class.java.fields
            .filter { it.type == String::class.java && Modifier.isStatic(it.modifiers) }
            .map { it.name to it.get(null) as String }
            .filter { (_, pattern) -> pattern.contains('{') }
            .sortedBy { (field, _) -> field }

    private companion object {
        val PLACEHOLDER = Regex("\\{(\\w+)}")

        // `?name=value` — the same shape the route builder writes, read here rather than trusted.
        val QUERY_VALUE = Regex("[?&](\\w+)=([^&]*)")
    }
}

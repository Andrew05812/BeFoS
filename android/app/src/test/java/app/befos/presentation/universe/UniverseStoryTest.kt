package app.befos.presentation.universe

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.data.mapper.toDomain
import app.befos.data.model.UniverseDto
import app.befos.domain.model.Connection
import app.befos.domain.model.Universe
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * Stage 79.3 gives one map document three readings: the two worlds, the band-by-band analysis and a
 * story the pair can send away from the app. Two rules hold all of it together.
 *
 * The first is the one the stage exists for: the shared reading must carry no answer of either
 * person. The sentences come from the engine already stripped to aggregates, so the client's only
 * job is to add nothing — no name it knows, no axis label it could have taken from a node.
 *
 * The second is the rule the whole map lives by: switching reading must not become a second source
 * of numbers. All three modes read the same `Universe`, so no tap on the switcher refetches, and the
 * analysis reuses the caption the canvas already prints instead of forming its own percent.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class UniverseStoryTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val matches: MatchRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun node(
        key: String,
        label: String,
        kind: Connection,
        hasData: Boolean = true,
    ) = UniverseNode(
        key = key, label = label, aValue = if (hasData) 0.9 else null, bValue = if (hasData) 0.7 else null,
        hasData = hasData, connection = kind, evidence = "узел $label: 90 против 70",
        confidence = if (hasData) 40 else 0, suggestion = "Совет узла $label", questions = emptyList(),
    )

    private fun layer(
        category: String,
        label: String,
        score: Int,
        weight: Double,
        nodes: List<UniverseNode>,
        hasData: Boolean = true,
    ) = UniverseLayer(
        category = category, label = label, score = score, weight = weight, hasData = hasData,
        coverage = if (nodes.isEmpty()) 0.0 else nodes.count { it.hasData }.toDouble() / nodes.size,
        confidence = if (hasData) 40 else 0, nodes = nodes,
    )

    private fun universe(
        story: List<String> = listOf("Мы совпадаем на 68%.", "Ценности — 70%."),
    ) = Universe(
        overall = 68, engineVersion = 4, aUserId = "u-a", bUserId = "u-b",
        layers = listOf(
            layer("interests", "Интересы", 50, 0.10, listOf(node("hiking", "Хайкинг", Connection.HARMONY))),
            layer("values", "Ценности", 70, 0.22, listOf(node("family", "Семья", Connection.HARMONY))),
            layer(
                "lifestyle", "Образ жизни", 50, 0.18,
                listOf(node("smoking", "Курение", Connection.UNKNOWN, hasData = false)),
                hasData = false,
            ),
        ),
        story = story,
    )

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `the story the engine wrote reaches the screen without being rewritten`() {
        val json = """
            {"overall":68,"engine_version":4,"a_user_id":"u-a","b_user_id":"u-b",
             "layers":[],"story":["Мы совпадаем на 68%.","Ценности — 70%.","Цели знакомства — 40%."]}
        """.trimIndent()
        val decoded = Json.decodeFromString<UniverseDto>(json).toDomain()
        assertEquals(
            listOf("Мы совпадаем на 68%.", "Ценности — 70%.", "Цели знакомства — 40%."),
            decoded.story,
        )
    }

    @Test
    fun `a map from a server that has no story yet still decodes`() {
        val json = """{"overall":68,"a_user_id":"u-a","b_user_id":"u-b","layers":[]}"""
        assertTrue(Json.decodeFromString<UniverseDto>(json).toDomain().story.isEmpty())
    }

    @Test
    fun `the shared text is the engine's sentences plus the caveat and nothing else`() {
        val state = UniverseUiState(
            loading = false,
            data = universe(),
            aName = "Аня",
            bName = "Боря",
        )
        val text = storyShareText(state.data!!.story)

        state.data!!.story.forEach { line -> assertTrue("lost: $line", text.contains(line)) }
        assertTrue(text.contains(STORY_TITLE))
        assertTrue(text.contains(MAP_DISCLAIMER))
        // What must NOT be there: the names this client resolved for the two worlds, and the axis
        // labels it could have taken from any node. Both are individual answers' clothing.
        assertFalse(text.contains("Аня"))
        assertFalse(text.contains("Боря"))
        state.data!!.layers.flatMap { it.nodes }.forEach { node ->
            assertFalse("the share carries ${node.label}", text.contains(node.label))
            assertFalse("the share carries the advice line", text.contains(node.suggestion))
            assertFalse("the share carries evidence", text.contains(node.evidence))
        }
    }

    @Test
    fun `an empty story shares an honest emptiness rather than a bare title`() {
        val text = storyShareText(emptyList())
        assertTrue(text.contains(STORY_TITLE))
        assertTrue(text.contains(MAP_DISCLAIMER))
        // The screen keeps the button disabled in this case; the text itself must not pretend.
        assertEquals(2, text.split("\n\n").size)
    }

    @Test
    fun `the analysis puts the heaviest band first and keeps the server order on ties`() {
        val layers = universe().layers
        val ordered = analysisOrder(layers)
        assertEquals(layers.size, ordered.size)
        assertEquals(listOf("Ценности", "Образ жизни", "Интересы"), ordered.map { it.label })

        val tied = listOf(
            layer("values", "Ценности", 70, 0.22, emptyList()),
            layer("lifestyle", "Образ жизни", 60, 0.22, emptyList()),
            layer("interests", "Интересы", 50, 0.22, emptyList()),
        )
        assertEquals(
            "equal weights must not reshuffle the bands the map drew",
            tied.map { it.label },
            analysisOrder(tied).map { it.label },
        )
    }

    @Test
    fun `the analysis names a band it cannot score without a percent`() {
        val unmeasured = universe().layers.first { !it.hasData }
        assertFalse(
            "an unscored band is shown as ${bandCaption(unmeasured)}",
            bandCaption(unmeasured).contains('%'),
        )
        assertEquals("сравнения не было", assuranceWord(unmeasured.confidence, compared = false))
    }

    @Test
    fun `the three readings are named differently on the switcher`() {
        val words = UniverseMode.entries.map(::modeWord)
        assertEquals(words.size, words.distinct().size)
        words.forEach { assertTrue("blank chip: $it", it.isNotBlank()) }
    }

    @Test
    fun `switching reading does not fetch a second document`() {
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe())
        coEvery { profiles.me() } returns ApiResult.Error(500, "нет")
        coEvery { matches.partner("m1") } returns ApiResult.Error(500, "нет")

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()
        val before = vm.uiState.value.data
        assertNotNull("the document arrived before the first switch", before)

        UniverseMode.entries.forEach { vm.setMode(it); advance() }

        assertEquals(UniverseMode.Story, vm.uiState.value.mode)
        assertSame("every reading has to show the same document", before, vm.uiState.value.data)
        coVerify(exactly = 1) { matches.universe("m1") }
    }

    @Test
    fun `switching reading keeps the node the pair already opened`() {
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe())
        coEvery { profiles.me() } returns ApiResult.Error(500, "нет")
        coEvery { matches.partner("m1") } returns ApiResult.Error(500, "нет")

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()
        vm.select("family")
        vm.setMode(UniverseMode.Analysis)
        advance()

        assertEquals("family", vm.uiState.value.selectedKey)
        assertEquals("Семья", vm.uiState.value.selected()?.node?.label)
        assertNotEquals(UniverseMode.Map, vm.uiState.value.mode)
    }
}

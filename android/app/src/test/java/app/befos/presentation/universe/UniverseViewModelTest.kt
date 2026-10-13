package app.befos.presentation.universe

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Connection
import app.befos.domain.model.Interest
import app.befos.domain.model.Profile
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Universe
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import io.mockk.coEvery
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
 * The screen state behind the map. Two rules hold this together: a pair that is gone must not be
 * offered a retry that cannot succeed, and the two worlds must be labelled by the ids the server
 * sent rather than by whoever is holding the phone.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class UniverseViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val matches: MatchRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun node(key: String, a: Double?, b: Double?, kind: Connection) = UniverseNode(
        key = key, label = key, aValue = a, bValue = b, hasData = a != null && b != null,
        connection = kind, evidence = "evidence of $key",
    )

    private fun universe(aId: String = "u-a", bId: String = "u-b") = Universe(
        overall = 68,
        engineVersion = 4,
        aUserId = aId,
        bUserId = bId,
        layers = listOf(
            UniverseLayer(
                category = "values",
                label = "Ценности",
                score = 70,
                weight = 0.22,
                hasData = true,
                coverage = 0.5,
                nodes = listOf(
                    node("honesty", 0.9, 0.86, Connection.HARMONY),
                    node("spontaneity", 0.4, 0.1, Connection.DISCUSSION),
                    node("ambition", 0.7, null, Connection.UNKNOWN),
                ),
            ),
            UniverseLayer(
                category = "interests",
                label = "Интересы",
                score = 50,
                weight = 0.1,
                hasData = true,
                coverage = 1.0,
                nodes = listOf(node("hiking", 1.0, 1.0, Connection.HARMONY)),
            ),
        ),
    )

    private fun profile(userId: String, name: String) = Profile(
        userId = userId, name = name, age = 30, city = "Москва", gender = "female",
        about = null, datingGoal = "relation", photoUrls = emptyList(),
        interests = listOf(Interest("hiking", "Хайкинг", "outdoor")),
        lifestyle = emptyMap(), ageMin = 25, ageMax = 40, genderPreference = listOf("male"),
    )

    private fun publicProfile(userId: String, name: String) = PublicProfile(
        userId = userId, name = name, age = 32, city = "Тверь", about = null,
        datingGoal = "relation", gender = "male", interests = listOf("Хайкинг"),
        photoUrls = emptyList(), compatibility = 68, categories = emptyList(),
        sharedInterests = emptyList(),
    )

    private fun stubNames(aId: String = "u-a", bId: String = "u-b") {
        coEvery { profiles.me() } returns ApiResult.Success(profile(bId, "Я"))
        coEvery { matches.partner("m1") } returns ApiResult.Success(publicProfile(aId, "Партнёр"))
    }

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    @Test
    fun `the worlds are labelled by the ids the map carries, not by who is asking`() {
        // The pair-global order puts the requester on the RIGHT, so a client that assumed
        // "a is me" would print my own name over my partner's answers.
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe(aId = "u-partner", bId = "u-me"))
        coEvery { profiles.me() } returns ApiResult.Success(profile("u-me", "Я"))
        coEvery { matches.partner("m1") } returns ApiResult.Success(publicProfile("u-partner", "Партнёр"))

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()

        assertEquals("Партнёр", vm.uiState.value.aName)
        assertEquals("Я", vm.uiState.value.bName)
    }

    @Test
    fun `a loaded map stops loading and keeps every number the server sent`() = runTest {
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe())
        stubNames()

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()

        val state = vm.uiState.value
        assertFalse(state.loading)
        assertNull(state.error)
        assertEquals(68, state.data?.overall)
        assertEquals(4, state.data?.engineVersion)
        assertEquals(70, state.data?.layers?.first()?.score)
    }

    @Test
    fun `a pair that no longer exists answers without a retry it cannot serve`() = runTest {
        coEvery { matches.universe("m1") } returns ApiResult.Error(404, "Пара больше не существует.")

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()

        val state = vm.uiState.value
        assertFalse(state.loading)
        assertTrue("404 must drop the dead «Повторить»", state.gone)
        assertEquals("Пара больше не существует.", state.error)
        assertNull(state.data)
    }

    @Test
    fun `a transport failure keeps the retry offer`() = runTest {
        coEvery { matches.universe("m1") } returns
            ApiResult.Error(-1, "Не получилось связаться с сервером. Проверьте соединение.")

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()

        val state = vm.uiState.value
        assertFalse("a network miss is worth retrying", state.gone)
        assertNotNull(state.error)
    }

    @Test
    fun `a name that cannot be resolved leaves the map drawn and anonymous`() = runTest {
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe())
        coEvery { profiles.me() } returns ApiResult.Error(500, "Сервер недоступен.")
        coEvery { matches.partner("m1") } returns ApiResult.Error(500, "Сервер недоступен.")

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()

        assertNotNull(vm.uiState.value.data)
        assertNull(vm.uiState.value.aName)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `tapping the same mark again closes it`() = runTest {
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe())
        stubNames()

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()

        vm.select("spontaneity")
        assertEquals("spontaneity", vm.uiState.value.selectedKey)
        assertEquals("spontaneity", vm.uiState.value.selected()?.node?.key)
        assertEquals("values", vm.uiState.value.selected()?.layer?.category)

        vm.select("spontaneity")
        assertNull(vm.uiState.value.selectedKey)
        assertNull(vm.uiState.value.selected())
    }

    @Test
    fun `the filter picks the kind and drops a selection that is no longer on screen`() = runTest {
        coEvery { matches.universe("m1") } returns ApiResult.Success(universe())
        stubNames()

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()
        assertEquals(4, vm.uiState.value.visibleNodes().size)

        vm.select("honesty")
        vm.setFilter(Connection.DISCUSSION)

        assertEquals(listOf("spontaneity"), vm.uiState.value.visibleNodes().map { it.key })
        assertNull("a hidden node cannot stay expanded", vm.uiState.value.selected())

        vm.setFilter(null)
        assertEquals(4, vm.uiState.value.visibleNodes().size)
    }

    @Test
    fun `reload clears the gone flag so a restored pair can be opened again`() = runTest {
        coEvery { matches.universe("m1") } returnsMany listOf(
            ApiResult.Error(404, "Пара больше не существует."),
            ApiResult.Success(universe()),
        )
        stubNames()

        val vm = UniverseViewModel(matches, profiles, "m1")
        advance()
        assertTrue(vm.uiState.value.gone)

        vm.load()
        advance()
        assertFalse(vm.uiState.value.gone)
        assertNotNull(vm.uiState.value.data)
    }
}

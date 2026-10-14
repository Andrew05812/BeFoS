package app.befos.presentation.universe

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Connection
import app.befos.domain.model.Universe
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class UniverseUiState(
    val loading: Boolean = true,
    val data: Universe? = null,
    val error: String? = null,
    /**
     * The pair asked for a map the server does not have (404). `error` still carries the text to
     * show, but the screen must not offer «Повторить»: retrying a match that is not ours, or does
     * not exist, returns the same 404, and the chat of a dissolved pair is the case stage 72-11
     * named for this exact dead button.
     */
    val gone: Boolean = false,
    val selectedKey: String? = null,
    /** Filter over the connection types; null shows every band the pair has. */
    val filter: Connection? = null,
    /**
     * Which of stage 79.3's three readings the screen shows. All three read this same `data`, so
     * switching never fetches and never recomputes: the map, the band-by-band analysis and the
     * shareable story are one document seen three ways.
     */
    val mode: UniverseMode = UniverseMode.Map,
    /**
     * Who owns the left and the right world, in the pair's own `a`/`b` order. Resolved from the
     * two ids the map answers with, never assumed: the map is pair-global, so the requester is
     * not automatically `a`. Null while the names have not arrived, and the screen labels the
     * worlds by side instead of guessing a name.
     */
    val aName: String? = null,
    val bName: String? = null,
) {
    /** Nodes of the whole map, in the order the server returned them, after the filter. */
    fun visibleNodes(): List<UniverseNode> {
        val universe = data ?: return emptyList()
        return universe.layers.flatMap { it.nodes }.filter { filter == null || it.connection == filter }
    }

    /** Which band and node the tapped mark belongs to, or null when nothing is expanded. */
    fun selected(): Selection? {
        val key = selectedKey ?: return null
        val universe = data ?: return null
        return universe.layers.firstNotNullOfOrNull { layer ->
            layer.nodes.firstOrNull { it.key == key }?.let { Selection(layer, it) }
        }
    }
}

/** The three readings of one map document (stage 79.3). */
enum class UniverseMode { Map, Analysis, Story }

data class Selection(val layer: UniverseLayer, val node: UniverseNode)

class UniverseViewModel(
    private val matchRepository: MatchRepository,
    private val profileRepository: ProfileRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(UniverseUiState())
    val uiState: StateFlow<UniverseUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, gone = false) }
        viewModelScope.launch {
            when (val result = matchRepository.universe(matchId)) {
                is ApiResult.Success -> {
                    _uiState.update { it.copy(loading = false, data = result.data) }
                    loadNames(result.data)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, error = result.message, gone = result.code == 404)
                }
            }
        }
    }

    /**
     * Names the two worlds by matching the ids the map carries against the two questionnaires
     * this client can read: my own and the partner's. A failure here is not an error state — the
     * map is already drawn and correct, only anonymous — so the labels simply stay unset and the
     * screen falls back to naming the sides.
     */
    private suspend fun loadNames(universe: Universe) {
        val me = profileRepository.me()
        val partner = matchRepository.partner(matchId)
        val byId = mutableMapOf<String, String>()
        if (me is ApiResult.Success) byId[me.data.userId] = me.data.name
        if (partner is ApiResult.Success) byId[partner.data.userId] = partner.data.name
        _uiState.update {
            it.copy(
                aName = byId[universe.aUserId],
                bName = byId[universe.bUserId],
            )
        }
    }

    /**
     * Tapping a mark opens the node that owns it. Tapping the same node again closes it, so the
     * map has one control that both expands and collapses the evidence.
     */
    fun select(key: String?) {
        _uiState.update { it.copy(selectedKey = if (it.selectedKey == key) null else key) }
    }

    fun setFilter(filter: Connection?) {
        _uiState.update { it.copy(filter = filter, selectedKey = null) }
    }

    /**
     * Switching reading is a pure view change: the tapped node stays tapped, because the analysis
     * and the map describe the same document, and no second request is made.
     */
    fun setMode(mode: UniverseMode) {
        _uiState.update { it.copy(mode = mode) }
    }
}

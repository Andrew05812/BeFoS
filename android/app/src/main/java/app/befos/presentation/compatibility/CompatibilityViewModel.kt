package app.befos.presentation.compatibility

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.Compatibility
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.TestRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * What the pair's reading of its own compatibility holds at a moment.
 *
 * [gone] is the pair having stopped existing, not a page that failed: the same 404 the chat and the other
 * pair pages answer with, and the reason the screen must not offer «Повторить» — asking again for a pair
 * that is gone is the dead button stage 72-11 removed from the chat, and the pair pages after it.
 *
 * [expandedBand] is which band the person opened to read what it measures. It lives here rather than in
 * composition state because the detail is a claim about the pair's data: a rotation that folded the band
 * back up and left the person with a list and no reason they opened it would be the same loss the plan
 * editors kept making until they moved their drafts out of `remember`.
 */
data class CompatibilityUiState(
    val loading: Boolean = true,
    val data: Compatibility? = null,
    // How far the person has come in each section of the questionnaire, and null while that is not
    // known. An empty band is explained by the counts of its own section, so the screen must be
    // able to tell «there is no section for this band» from «the counts never arrived».
    val sections: List<CategoryProgress>? = null,
    val error: String? = null,
    val gone: Boolean = false,
    val expandedBand: String? = null,
)

class CompatibilityViewModel(
    private val matchRepository: MatchRepository,
    private val testRepository: TestRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(CompatibilityUiState())
    val uiState: StateFlow<CompatibilityUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, gone = false) }
        viewModelScope.launch {
            when (val result = matchRepository.compatibility(matchId)) {
                is ApiResult.Success -> {
                    _uiState.update { it.copy(loading = false, data = result.data) }
                    readSections(result.data)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, error = result.message, gone = result.code == 404)
                }
            }
        }
    }

    /**
     * Opens the band, or closes it when the same one is already open — one control for both, so the list
     * never has to grow a second affordance a person has to find before they can put the first away.
     */
    fun toggleBand(category: String) {
        _uiState.update {
            it.copy(expandedBand = if (it.expandedBand == category) null else category)
        }
    }

    /**
     * The test route is asked only when the pair page has a band to explain. A pair with every
     * category measured never pays for the extra read, and the compatibility route keeps the price
     * the scale probe has already put on it.
     */
    private suspend fun readSections(data: Compatibility) {
        if (data.categories.none { !it.hasData }) return
        when (val result = testRepository.progress()) {
            is ApiResult.Success -> _uiState.update { it.copy(sections = result.data.categories) }
            // The counts did not arrive: the bands stay named and unexplained rather than being
            // given a section they cannot be matched to.
            is ApiResult.Error -> _uiState.update { it.copy(sections = emptyList()) }
        }
    }
}

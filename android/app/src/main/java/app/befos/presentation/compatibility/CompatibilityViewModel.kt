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

data class CompatibilityUiState(
    val loading: Boolean = true,
    val data: Compatibility? = null,
    // How far the person has come in each section of the questionnaire, and null while that is not
    // known. An empty band is explained by the counts of its own section, so the screen must be
    // able to tell «there is no section for this band» from «the counts never arrived».
    val sections: List<CategoryProgress>? = null,
    val error: String? = null,
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
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = matchRepository.compatibility(matchId)) {
                is ApiResult.Success -> {
                    _uiState.update { it.copy(loading = false, data = result.data) }
                    readSections(result.data)
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
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

package app.befos.presentation.pair

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.PairProfile
import app.befos.domain.repository.MatchRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * One reading of one pair, held where a rotation cannot lose it.
 *
 * [gone] is the pair having stopped existing rather than the read having failed — the same 404 the chat,
 * the partner card and the pair's map answer a stranger or a dissolved pair with. It is a separate flag
 * because the screen has to be able to refuse its own «Повторить»: retrying a pair that is gone returns
 * the same answer forever, which is the dead control this app already removed from the chat and from the
 * other pair pages.
 */
data class PairProfileUiState(
    val loading: Boolean = true,
    val data: PairProfile? = null,
    val error: String? = null,
    val gone: Boolean = false,
)

class PairProfileViewModel(
    private val matchRepository: MatchRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PairProfileUiState())
    val uiState: StateFlow<PairProfileUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    /**
     * The one request this screen makes. The compatibility document rides inside the answer rather than
     * being fetched again, so the digest the pair reads here and the detail they read on the compatibility
     * page cannot be two calculations of a pair that answered in between.
     */
    fun load() {
        _uiState.update { it.copy(loading = true, error = null, gone = false) }
        viewModelScope.launch {
            when (val result = matchRepository.pairProfile(matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, data = result.data)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, error = result.message, gone = result.code == 404)
                }
            }
        }
    }
}

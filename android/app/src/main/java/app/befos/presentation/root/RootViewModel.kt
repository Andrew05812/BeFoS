package app.befos.presentation.root

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class RootDestination { LOADING, AUTH, ONBOARDING, MAIN }

class RootViewModel(
    private val authRepository: AuthRepository,
    private val profileRepository: ProfileRepository,
) : ViewModel() {

    private val _destination = MutableStateFlow(RootDestination.LOADING)
    val destination: StateFlow<RootDestination> = _destination.asStateFlow()

    init {
        resolve()
    }

    fun resolve() {
        _destination.value = RootDestination.LOADING
        viewModelScope.launch {
            val auth = authRepository.current()
            if (auth == null) {
                _destination.value = RootDestination.AUTH
                return@launch
            }
            when (val result = profileRepository.me()) {
                is ApiResult.Success -> {
                    val profile = result.data
                    val onboarded = profile.name.isNotBlank() &&
                        profile.interests.isNotEmpty() &&
                        profile.datingGoal.isNotBlank()
                    _destination.value =
                        if (onboarded) RootDestination.MAIN else RootDestination.ONBOARDING
                }
                is ApiResult.Error -> {
                    // A 401 means the stored session is no longer valid.
                    if (result.code == 401) {
                        authRepository.logout()
                        _destination.value = RootDestination.AUTH
                    } else {
                        _destination.value = RootDestination.MAIN
                    }
                }
            }
        }
    }
}

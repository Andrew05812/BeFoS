package app.befos.presentation.editprofile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Interest
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.repository.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class EditProfileUiState(
    val loading: Boolean = true,
    val saving: Boolean = false,
    val allInterests: List<Interest> = emptyList(),
    val name: String = "",
    val city: String = "",
    val about: String = "",
    val datingGoal: String = "relationship",
    val gender: String = "male",
    val selectedInterests: Set<String> = emptySet(),
    val ageMin: Int = 18,
    val ageMax: Int = 60,
    val genderPreference: Set<String> = emptySet(),
    val error: String? = null,
    val loadFailed: Boolean = false,
    /**
     * The interest catalogue did not arrive, so the picker is empty for a reason the user can
     * act on. Without it the section reads as a screen that lost their interests.
     */
    val interestsFailed: Boolean = false,
    val saved: Boolean = false,
)

class EditProfileViewModel(private val profileRepository: ProfileRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(EditProfileUiState())
    val uiState: StateFlow<EditProfileUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            when (val result = profileRepository.me()) {
                is ApiResult.Success -> {
                    val p = result.data
                    _uiState.update {
                        it.copy(
                            loading = false,
                            loadFailed = false,
                            name = p.name,
                            city = p.city,
                            about = p.about ?: "",
                            datingGoal = p.datingGoal,
                            gender = p.gender,
                            selectedInterests = p.interests.map { i -> i.slug }.toSet(),
                            ageMin = p.ageMin,
                            ageMax = p.ageMax,
                            genderPreference = p.genderPreference.toSet(),
                        )
                    }
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, loadFailed = true, error = result.message)
                }
            }
            loadInterests()
        }
    }

    /**
     * Kept apart from [load] on purpose: a retry of the catalogue must not re-read the
     * profile, which would overwrite what the user has already typed.
     */
    fun loadInterests() {
        viewModelScope.launch {
            when (val interests = profileRepository.interests()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(allInterests = interests.data, interestsFailed = false)
                }
                is ApiResult.Error -> _uiState.update { it.copy(interestsFailed = true) }
            }
        }
    }

    fun onNameChange(v: String) = _uiState.update { it.copy(name = v, error = null) }
    fun onCityChange(v: String) = _uiState.update { it.copy(city = v, error = null) }
    fun onAboutChange(v: String) = _uiState.update { it.copy(about = v, error = null) }
    fun setDatingGoal(v: String) = _uiState.update { it.copy(datingGoal = v) }
    fun setGender(v: String) = _uiState.update { it.copy(gender = v) }
    fun setAgeRange(min: Int, max: Int) = _uiState.update { it.copy(ageMin = min, ageMax = max) }

    fun toggleInterest(slug: String) = _uiState.update {
        val next = it.selectedInterests.toMutableSet()
        if (!next.add(slug)) next.remove(slug)
        it.copy(selectedInterests = next)
    }

    fun toggleGenderPreference(v: String) = _uiState.update {
        val next = it.genderPreference.toMutableSet()
        if (!next.add(v)) next.remove(v)
        it.copy(genderPreference = next)
    }

    fun save() {
        val s = _uiState.value
        if (s.saving) return
        if (s.name.isBlank()) return _uiState.update { it.copy(error = "Укажите имя.") }
        if (s.city.isBlank()) return _uiState.update { it.copy(error = "Укажите город.") }
        _uiState.update { it.copy(saving = true, error = null) }
        viewModelScope.launch {
            val data = ProfileUpdateData(
                name = s.name.trim(),
                city = s.city.trim(),
                about = s.about.trim(),
                datingGoal = s.datingGoal,
                gender = s.gender,
                interests = s.selectedInterests.toList(),
                ageMin = s.ageMin,
                ageMax = s.ageMax,
                genderPreference = s.genderPreference.toList(),
            )
            when (val result = profileRepository.update(data)) {
                is ApiResult.Success -> _uiState.update { it.copy(saving = false, saved = true) }
                is ApiResult.Error -> _uiState.update { it.copy(saving = false, error = result.message) }
            }
        }
    }
}

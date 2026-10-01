package app.befos.presentation.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Interest
import app.befos.domain.model.OnboardingData
import app.befos.domain.repository.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class OnboardingUiState(
    val step: Int = 0,
    val interests: List<Interest> = emptyList(),
    val interestsLoading: Boolean = true,
    val name: String = "",
    val birthDate: String = "",
    val city: String = "",
    val gender: String = "male",
    val about: String = "",
    val datingGoal: String = "relationship",
    val selectedInterests: Set<String> = emptySet(),
    val ageMin: Int = 18,
    val ageMax: Int = 60,
    val genderPreference: Set<String> = emptySet(),
    val submitting: Boolean = false,
    val error: String? = null,
    val done: Boolean = false,
)

class OnboardingViewModel(private val profileRepository: ProfileRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(OnboardingUiState())
    val uiState: StateFlow<OnboardingUiState> = _uiState.asStateFlow()

    init {
        loadInterests()
    }

    private fun loadInterests() {
        viewModelScope.launch {
            when (val result = profileRepository.interests()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(interests = result.data, interestsLoading = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(interestsLoading = false, error = result.message)
                }
            }
        }
    }

    fun onNameChange(v: String) = _uiState.update { it.copy(name = v, error = null) }
    fun onBirthDateChange(v: String) = _uiState.update { it.copy(birthDate = v, error = null) }
    fun onCityChange(v: String) = _uiState.update { it.copy(city = v, error = null) }
    fun onAboutChange(v: String) = _uiState.update { it.copy(about = v, error = null) }
    fun setGender(v: String) = _uiState.update { it.copy(gender = v) }
    fun setDatingGoal(v: String) = _uiState.update { it.copy(datingGoal = v) }
    fun setAgeRange(min: Int, max: Int) = _uiState.update { it.copy(ageMin = min, ageMax = max) }

    fun toggleInterest(slug: String) = _uiState.update {
        val next = it.selectedInterests.toMutableSet()
        if (!next.add(slug)) next.remove(slug)
        it.copy(selectedInterests = next, error = null)
    }

    fun toggleGenderPreference(v: String) = _uiState.update {
        val next = it.genderPreference.toMutableSet()
        if (!next.add(v)) next.remove(v)
        it.copy(genderPreference = next)
    }

    fun next() {
        val s = _uiState.value
        when (s.step) {
            0 -> {
                if (s.name.isBlank()) return fail("Укажите имя.")
                if (!isValidDate(s.birthDate)) return fail("Дата рождения в формате ГГГГ-ММ-ДД.")
                if (s.city.isBlank()) return fail("Укажите город.")
                _uiState.update { it.copy(step = 1, error = null) }
            }
            1 -> {
                if (s.ageMin > s.ageMax) return fail("Минимальный возраст больше максимального.")
                _uiState.update { it.copy(step = 2, error = null) }
            }
            2 -> {
                if (s.selectedInterests.size < 3) return fail("Выберите минимум 3 интереса.")
                submit()
            }
        }
    }

    fun back() = _uiState.update { if (it.step > 0) it.copy(step = it.step - 1, error = null) else it }

    private fun fail(msg: String) = _uiState.update { it.copy(error = msg) }

    private fun isValidDate(v: String): Boolean {
        val parts = v.split("-")
        if (parts.size != 3) return false
        val (y, m, d) = parts
        if (y.length != 4) return false
        val year = y.toIntOrNull() ?: return false
        val month = m.toIntOrNull() ?: return false
        val day = d.toIntOrNull() ?: return false
        return year in 1900..2100 && month in 1..12 && day in 1..31
    }

    private fun submit() {
        val s = _uiState.value
        _uiState.update { it.copy(submitting = true, error = null) }
        viewModelScope.launch {
            val data = OnboardingData(
                name = s.name.trim(),
                birthDate = s.birthDate.trim(),
                city = s.city.trim(),
                gender = s.gender,
                about = s.about.trim().ifBlank { null },
                datingGoal = s.datingGoal,
                interests = s.selectedInterests.toList(),
                lifestyle = emptyMap(),
                ageMin = s.ageMin,
                ageMax = s.ageMax,
                genderPreference = s.genderPreference.toList(),
            )
            when (val result = profileRepository.onboarding(data)) {
                is ApiResult.Success -> _uiState.update { it.copy(submitting = false, done = true) }
                is ApiResult.Error -> _uiState.update { it.copy(submitting = false, error = result.message) }
            }
        }
    }
}

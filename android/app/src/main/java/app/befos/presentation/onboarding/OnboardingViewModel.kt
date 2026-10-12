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
import java.time.LocalDate
import java.time.Period
import java.time.ZoneOffset

data class OnboardingUiState(
    val step: Int = 0,
    val interests: List<Interest> = emptyList(),
    val interestsLoading: Boolean = true,
    val interestsFailed: Boolean = false,
    val name: String = "",
    // Digits only (YYYYMMDD); the field renders them with separators via a visual transformation.
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

    /** Public because the step that needs the catalogue offers a retry of exactly this read. */
    fun loadInterests() {
        _uiState.update { it.copy(interestsLoading = true, interestsFailed = false) }
        viewModelScope.launch {
            when (val result = profileRepository.interests()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(interests = result.data, interestsLoading = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(interestsLoading = false, interestsFailed = true)
                }
            }
        }
    }

    fun onNameChange(v: String) = _uiState.update { it.copy(name = v, error = null) }
    fun onBirthDateChange(v: String) = _uiState.update {
        it.copy(birthDate = v.filter(Char::isDigit).take(8), error = null)
    }
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
                birthDateError(s.birthDate)?.let { return fail(it) }
                if (s.city.isBlank()) return fail("Укажите город.")
                _uiState.update { it.copy(step = 1, error = null) }
            }
            1 -> _uiState.update { it.copy(step = 2, error = null) }
            2 -> {
                if (s.selectedInterests.size < 3) {
                    // The same short list means two different things, and only one of them the
                    // person can fix by looking for more chips.
                    return fail(
                        if (s.interestsFailed) {
                            "Список интересов не загрузился. Повторите попытку."
                        } else {
                            "Выберите минимум 3 интереса."
                        }
                    )
                }
                submit()
            }
        }
    }

    fun back() = _uiState.update { if (it.step > 0) it.copy(step = it.step - 1, error = null) else it }

    private fun fail(msg: String) = _uiState.update { it.copy(error = msg) }

    private fun submit() {
        val s = _uiState.value
        if (s.submitting) return
        _uiState.update { it.copy(submitting = true, error = null) }
        viewModelScope.launch {
            val data = OnboardingData(
                name = s.name.trim(),
                birthDate = isoBirthDate(s.birthDate) ?: s.birthDate,
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

/** ISO date built from the 8 digits typed in the birth-date field, or null if no such day exists. */
fun isoBirthDate(digits: String): String? {
    if (digits.length != 8) return null
    val iso = "${digits.take(4)}-${digits.substring(4, 6)}-${digits.substring(6)}"
    return runCatching { LocalDate.parse(iso).toString() }.getOrNull()
}

/** Why the typed birth date cannot be accepted yet, or null when it can. */
fun birthDateError(digits: String, today: LocalDate = utcToday()): String? {
    if (digits.isBlank()) return "Укажите дату рождения."
    if (digits.length < 8) return "Введите дату рождения целиком — 8 цифр."
    val iso = isoBirthDate(digits) ?: return "Такой даты не бывает."
    val date = LocalDate.parse(iso)
    if (date.isAfter(today)) return "Такой даты не бывает."
    if (Period.between(date, today).years < 18) return "BeFoS доступен с 18 лет."
    return null
}

/** The calendar the server counts age on — UTC, so the device's zone cannot disagree with it. */
fun utcToday(): LocalDate = LocalDate.now(ZoneOffset.UTC)

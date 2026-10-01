package app.befos.core.di

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import app.befos.BeFoSApplication

@Composable
fun appContainer(): AppContainer {
    val context = LocalContext.current
    return (context.applicationContext as BeFoSApplication).container
}

@Composable
inline fun <reified VM : ViewModel> beFosViewModel(
    crossinline create: (AppContainer) -> VM,
): VM {
    val container = appContainer()
    return viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = create(container) as T
        },
    )
}

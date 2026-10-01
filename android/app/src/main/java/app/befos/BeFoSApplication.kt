package app.befos

import android.app.Application
import app.befos.core.di.AppContainer

class BeFoSApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}

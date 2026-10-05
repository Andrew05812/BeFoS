import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Release signing is opt-in: create android/keystore.properties (see
// keystore.properties.example) outside of version control. Without it the
// release variant builds unsigned instead of silently reusing the debug key.
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) keystorePropsFile.inputStream().use { load(it) }
}

fun envOrProp(name: String, camel: String): String? =
    System.getenv(name) ?: providers.gradleProperty(camel).orNull

val apiBaseUrl = envOrProp("BEFOS_API_BASE_URL", "befos.apiBaseUrl")
val wsBaseUrl = envOrProp("BEFOS_WS_BASE_URL", "befos.wsBaseUrl")
// Local emulator defaults; production backends are served over https/wss.
val debugApiUrl = apiBaseUrl ?: "http://10.0.2.2:8000/"
val debugWsUrl = wsBaseUrl ?: "ws://10.0.2.2:8000/"
val requestingRelease = gradle.startParameter.taskNames.any {
    it.contains("Release", ignoreCase = true) || it.contains("Bundle", ignoreCase = true)
}

android {
    namespace = "app.befos"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.befos"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (keystorePropsFile.exists()) {
            create("release") {
                storeFile = file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            // Backend base URL. For the Android emulator, 10.0.2.2 maps to the host loopback.
            buildConfigField("String", "API_BASE_URL", "\"$debugApiUrl\"")
            buildConfigField("String", "WS_BASE_URL", "\"$debugWsUrl\"")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (keystorePropsFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
            if (requestingRelease && (apiBaseUrl == null || wsBaseUrl == null)) {
                throw GradleException(
                    "Release builds require BEFOS_API_BASE_URL and BEFOS_WS_BASE_URL " +
                        "(env vars or -Pbefos.apiBaseUrl / -Pbefos.wsBaseUrl) pointing at your " +
                        "https:// and wss:// backend. Local emulator defaults must not ship in release.",
                )
            }
            buildConfigField("String", "API_BASE_URL", "\"${apiBaseUrl ?: debugApiUrl}\"")
            buildConfigField("String", "WS_BASE_URL", "\"${wsBaseUrl ?: debugWsUrl}\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.foundation)
    implementation(libs.compose.animation)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)

    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.auth)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.client.websockets)
    implementation(libs.ktor.client.logging)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.coil.compose)

    testImplementation(libs.junit)
    testImplementation(libs.ktor.client.mock)
    testImplementation(libs.mockk)
    testImplementation(libs.turbine)
    testImplementation(libs.kotlinx.coroutines.test)

    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)
}

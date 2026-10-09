plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "app.websave"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.websave"
        minSdk = 26
        targetSdk = 34
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "1.0." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    // chave fixa: permite instalar versões novas por cima sem desinstalar
    signingConfigs {
        create("fixa") {
            storeFile = file("websave.keystore")
            storePassword = "websave"
            keyAlias = "websave"
            keyPassword = "websave"
        }
    }
    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("fixa") }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("fixa")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            install("yt-dlp")
            install("certifi")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.2")
}

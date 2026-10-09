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
        // 64-bit and 32-bit ARM: covers older and entry-level phones too
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    // fixed key: lets new versions install over the old one without uninstalling
    signingConfigs {
        create("fixed") {
            storeFile = file("websave.keystore")
            storePassword = "websave"
            keyAlias = "websave"
            keyPassword = "websave"
        }
    }
    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("fixed") }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("fixed")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    // QuickJS ships as libqjs.so so Android extracts it to an executable folder
    packaging { jniLibs { useLegacyPackaging = true } }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

chaquopy {
    defaultConfig {
        // 3.11 is the newest Python that Chaquopy builds for 32-bit ARM
        version = "3.11"
        // ship compiled bytecode so the app starts faster on slow phones
        pyc {
            src = true
            pip = true
            stdlib = true
        }
        pip {
            install("yt-dlp")
            install("yt-dlp-ejs")
            install("certifi")
            install("pillow")
            install("mutagen")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.2")
}

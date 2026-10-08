import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    kotlin("jvm") version "2.4.20"
    id("org.jetbrains.intellij.platform") version "2.19.0"
}

group = "io.github.pedronveloso"

version = providers.gradleProperty("pluginVersion").get()

repositories {
    mavenCentral()
    intellijPlatform { defaultRepositories() }
}

val kotlinFormatter = configurations.create("kotlinFormatter")

dependencies {
    add(kotlinFormatter.name, "com.facebook:ktfmt:0.64")
    intellijPlatform {
        val localStudio = providers.gradleProperty("studioLocalPath")
        if (localStudio.isPresent) {
            local(localStudio.get())
        } else {
            androidStudio(providers.gradleProperty("studioVersion").get())
        }
        bundledPlugins("com.intellij.java", "org.jetbrains.kotlin", "org.jetbrains.plugins.yaml")
        bundledModule("intellij.json")
        bundledModule("intellij.json.backend")
        bundledModule("intellij.yaml.backend")
        testFramework(TestFrameworkType.Platform)
        testFramework(TestFrameworkType.Plugin.Java)
        pluginVerifier()
    }
    testImplementation("junit:junit:4.13.2")
}

kotlin { jvmToolchain(21) }

intellijPlatform {
    pluginConfiguration {
        name = "AASG"
        ideaVersion {
            sinceBuild = "261.26222.65"
            untilBuild = "261.*"
        }
    }
    pluginVerification {
        ides { current() }
    }
}

tasks.jar {
    from(rootProject.file("../LICENSE")) { into("META-INF") }
}

tasks.test {
    maxHeapSize = "2g"
    systemProperty("idea.is.unit.test", "true")
    systemProperty(
        "aasg.javac",
        javaToolchains
            .compilerFor { languageVersion = JavaLanguageVersion.of(21) }
            .get()
            .executablePath
            .asFile
            .path,
    )
    val pilotSources =
        mapOf(
            "altSeaPath" to
                "app/src/androidTest/java/app/altsea/feature/screenshots/PlayStoreScreenshotCaptureTest.kt",
            "lazulitePath" to
                "app/src/androidTest/java/com/pedronveloso/lazulite/e2e/HomeScreenshotCaptureTest.kt",
        )
    val pilotPaths = pilotSources.keys.map { providers.gradleProperty(it).isPresent }
    require(pilotPaths.all { it } || pilotPaths.none { it }) {
        "Pilot smoke tests require both -PaltSeaPath and -PlazulitePath."
    }
    if (pilotPaths.none { it }) exclude("**/AasgPilotSmokeTest.class")
    for ((property, source) in pilotSources) {
        providers.gradleProperty(property).orNull?.let {
            systemProperty(property, it)
            inputs.files(file("$it/aasg.yaml"), file("$it/$source"))
        }
    }
}

val kotlinFiles =
    fileTree(projectDir) {
        include("src/**/*.kt", "*.gradle.kts")
    }

for (taskName in listOf("formatKotlin", "checkKotlinFormat")) {
    tasks.register<JavaExec>(taskName) {
        group = "verification"
        description =
            "${if (taskName == "formatKotlin") "Format" else "Check"} Kotlin source formatting"
        classpath = kotlinFormatter
        mainClass = "com.facebook.ktfmt.cli.Main"
        args("--kotlinlang-style")
        if (taskName == "checkKotlinFormat") args("--dry-run", "--set-exit-if-changed")
        args(kotlinFiles.files.sortedBy { it.path }.map { it.path })
    }
}
